# Chained EE Container Group Fix

## TL;DR

All `chained-*` EE images fail 100% of jobs on AAP 2.4 container groups (OCP/k8s).
The same images work fine on bare-metal AAP. The fix is in
[agnosticd/agnosticd-v2#133](https://github.com/agnosticd/agnosticd-v2/pull/133).

## Background: How AAP Runs Jobs

AAP has two execution models for running playbooks:

### Bare-metal execution nodes

```
AAP Controller → receptor → execution node → ansible-runner → ansible-playbook
```

- The EE image provides the Python/collection environment
- `ansible-runner` on the **host** handles orchestration
- The EE entrypoint runs with full access to job data (inventory, extravars)
  because receptor writes them to disk before invoking ansible-runner

### Container groups (OCP/k8s)

```
AAP Controller → receptor → k8s pod (EE image) → ansible-runner worker → ansible-playbook
```

- The pod is started with: `ansible-runner worker --private-data-dir=/runner`
- The EE image IS the runtime — the entrypoint and ansible-runner inside the
  image handle everything
- Job data (inventory, extravars, project) arrives **via receptor stdin** after
  `ansible-runner worker` starts — it is NOT on disk when the entrypoint runs

## The Bug: Entrypoint AAP Detection

The chained EE entrypoint has logic to install dynamic dependencies (cloud
provider collections, config-specific roles) before the playbook runs. It detects
AAP by looking for `-u root` in the command arguments:

```bash
# Detect AAP environment
for ((i = 1; i < ${#args[@]}; i++)); do
    if [[ "${args[i]}" == "-u" && "${args[i+1]}" == "root" ]]; then
        AAP=1
        break
    fi
done
```

On **bare metal**, the arguments include `-u root` → detection works → the
entrypoint installs dependencies using `/runner/env/extravars` (already on disk)
→ playbook runs successfully.

On **container groups**, the arguments are `ansible-runner worker
--private-data-dir=/runner` — no `-u root` → falls into the ansible-navigator
branch → runs `shift 2` → calls:

```
ansible-playbook install_dynamic_dependencies.yml --private-data-dir=/runner
```

`--private-data-dir` is not a valid `ansible-playbook` argument → crash:

```
ansible-playbook: error: unrecognized arguments: --private-data-dir=/runner
```

Every job immediately fails with status `error`.

## Why Not Just Fix the Detection?

Simply detecting `ansible-runner worker` and skipping the dependency install
would fix the crash, but jobs would then fail because the dynamically-installed
collections (like `agnosticd.cloud_provider_aws`) are missing.

### Why not install dependencies in setup_runtime.yml?

We tried adding `install_dynamic_dependencies.yml` as the first play in
`setup_runtime.yml`. The dependencies install successfully, but ansible-core
resolves collection FQCN references **at playbook parse time**, not at task
execution time. Since `destroy.yml` uses `import_playbook: setup_runtime.yml`
(static import), ansible-core parses all playbooks upfront — before any tasks
run. Collections installed mid-playbook are invisible to `include_role` calls
that reference them.

This is why the entrypoint approach works on bare metal: dependencies are
installed **before** `ansible-playbook` is called, so they're available at
parse time.

## The Fix: ansible-playbook Wrapper

On container groups, we need dependencies installed:
- **After** ansible-runner unpacks job data (so extravars/inventory exist)
- **Before** ansible-playbook parses the real playbook (so collections are found)

The fix intercepts the exact moment between these two events:

1. The entrypoint detects Kubernetes via the `KUBERNETES_SERVICE_HOST` env var
   (injected by k8s into every pod — if set, we're in a container group, not
   on bare metal)
2. It creates a thin `ansible-playbook` wrapper in `/runner/.ep-wrapper/bin/`
   (a writable directory — OCP runs containers as random non-root UIDs,
   so `/usr/local/bin/` is not writable)
3. Prepends the wrapper dir to `$PATH` so it shadows the real `ansible-playbook`
4. When `ansible-runner worker` finishes unpacking job data and calls
   `ansible-playbook`, the wrapper intercepts:
   - Runs `install_dynamic_dependencies.yml` with the now-available inventory
     and extravars
   - Execs the real `ansible-playbook` with the original arguments
5. The real `ansible-playbook` starts with all collections already installed

```
entrypoint
  ├── Checks KUBERNETES_SERVICE_HOST env var
  ├── Creates wrapper in /runner/.ep-wrapper/bin/ansible-playbook
  ├── Prepends to PATH
  └── exec ansible-runner worker --private-data-dir=/runner
        └── ansible-runner unpacks job data via receptor
            └── Calls "ansible-playbook" (finds wrapper via PATH)
                ├── Wrapper: runs install_dynamic_dependencies.yml
                └── Wrapper: exec real-ansible-playbook <original args>
                      └── Playbook runs with all collections available
```

### Why KUBERNETES_SERVICE_HOST?

We considered several detection approaches:

| Approach | Pros | Cons |
|---|---|---|
| Check args for `ansible-runner worker` | Matches exact AWX behavior | Depends on AWX hardcoded args format |
| Check `ANSIBLE_RUNNER_KEEPALIVE_SECONDS` | Set by AWX on container group pods | Only set when the AWX setting is enabled; not guaranteed |
| Check `AWX_ISOLATED_DATA_DIR` | AWX-specific | Only set during playbook execution, not at entrypoint time |
| **Check `KUBERNETES_SERVICE_HOST`** | **Injected by k8s into every pod; always present** | **Would match non-AAP pods, but those don't use this entrypoint** |

`KUBERNETES_SERVICE_HOST` is the simplest and most reliable: if it's set, we're
in a k8s pod and not on a bare-metal execution node. The entrypoint is only used
by AAP/agnosticd EE images, so matching non-AAP pods is not a concern.

### Additional change: ansible.cfg

The dynamic dependency installer writes collections to
`/runner/requirements_collections`. This path was set via the
`ANSIBLE_COLLECTIONS_PATH` environment variable by the entrypoint on bare metal,
but the env var is not inherited through the ansible-runner worker → ansible-playbook
chain on container groups. Adding the path directly to `ansible.cfg` ensures it
works in all execution contexts.

## Impact

| Execution Context | Before | After |
|---|---|---|
| Container groups (OCP) | 100% `error` | Works (tested on prod0) |
| Bare-metal execution nodes | Works | No change (`-u root` path unchanged) |
| ansible-navigator | Works | No change (navigator path unchanged) |

## Files Changed

- `tools/execution_environments/ee-multicloud-public/entrypoint.sh` — container
  group detection + wrapper installation
- `ansible.cfg` — add `/runner/requirements_collections` to `collections_path`

## How to Verify

```bash
# Build test image
podman build --platform linux/amd64 \
  -t quay.io/<your-ns>/ee-multicloud:test-pr-133 \
  -f - tools/execution_environments/ee-multicloud-public <<'EOF'
FROM quay.io/agnosticd/ee-multicloud:chained-2026-02-23
COPY entrypoint.sh /usr/local/bin/entrypoint
EOF

# Push and create an EE in AAP pointing to the test image
# Run any job that uses a chained EE on a container group
# Verify: status should be "failed" or "successful", NOT "error"
```

## Root Cause Investigation Trail

1. All 9 failed jobs on prod0 shared the same error:
   `Failed to JSON parse a line from worker stream` with
   `ansible-playbook: error: unrecognized arguments: --private-data-dir=/runner`
2. Same EE images work on bare-metal us-east-2 (30,000+ successful jobs)
3. Bare metal uses execution nodes (`is_container_group=False`), OCP uses
   container groups (`is_container_group=True`)
4. On bare metal, the host's `ansible-runner` handles execution; on container
   groups, the EE's own entrypoint and `ansible-runner worker` handle execution
5. The chained EE entrypoint (from `agnosticd/agnosticd-v2`, not
   `redhat-cop/agnosticd`) has dynamic dependency install logic that doesn't
   account for container group invocation
6. The `install_dynamic_dependencies.yml` playbook referenced in the entrypoint
   doesn't even exist in the image — it comes from the git project synced by AAP
7. Even after fixing detection, collection FQCN resolution at parse time requires
   deps installed before `ansible-playbook` starts, leading to the wrapper approach
