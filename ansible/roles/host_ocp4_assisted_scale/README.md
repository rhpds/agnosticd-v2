# host_ocp4_assisted_scale

This Ansible role scales an existing OpenShift cluster that was deployed using the Red Hat Assisted Installer. It adds additional worker nodes to a running cluster by creating new KubeVirt virtual machines and integrating them through the Assisted Installer service.

## Overview

The role performs the following operations:

1. Queries the current worker node count in the target cluster
2. Imports the existing cluster into Assisted Installer (if not already imported)
3. Generates MAC addresses for the new worker nodes
4. Creates a new infrastructure environment for the scale operation
5. Downloads and prepares the installation ISO as a PVC
6. Creates new worker VMs on KubeVirt with the installation media
7. Waits for the new hosts to register with Assisted Installer
8. Approves Certificate Signing Requests (CSRs) for the new nodes
9. Scales the IngressController to match the new worker count
10. Optionally configures worker-only mode (when `worker_only: true`)

## Requirements

- Ansible 2.9 or higher
- Access to an existing OpenShift cluster deployed via Assisted Installer
- Access to a sandbox OpenShift cluster running KubeVirt (where the VMs will be created)
- Red Hat Assisted Installer offline token
- The following Ansible collections:
  - `kubernetes.core`
  - `kubevirt.core`
  - `rhpds.assisted_installer`
  - `community.general`

## Role Variables

### Required Variables

| Variable | Description |
|----------|-------------|
| `openshift_api_url` | API URL of the target OpenShift cluster to scale |
| `openshift_cluster_admin_token` | Admin token for the target cluster |
| `sandbox_openshift_api_url` | API URL of the sandbox cluster hosting KubeVirt |
| `sandbox_openshift_api_key` | API key for the sandbox cluster |
| `ai_offline_token` | Red Hat Assisted Installer offline token |
| `worker_instance_count` | Number of worker nodes to add |

### Default Variables (from defaults/main.yml)

| Variable | Default | Description |
|----------|---------|-------------|
| `cluster_name` | `"cluster-{{ guid.split('-')[0] if '-' in guid else guid }}"` | Name of the cluster |
| `ocp4_pull_secret` | `"{{ ocp4_ai_pull_secret }}"` | OpenShift pull secret |
| `ai_pull_secret` | (derived from `ocp4_pull_secret`) | Formatted pull secret for Assisted Installer |
| `ai_offline_token` | `"{{ ocp4_ai_offline_token }}"` | Assisted Installer offline token |
| `ai_cluster_name` | `"{{ guid }}"` | Cluster name for Assisted Installer |
| `ai_ocp_namespace` | `"{{ sandbox_openshift_namespace \| default(env_type + '-' + guid) }}"` | Namespace for the OpenShift VMs |
| `ai_cluster_iso_type` | `minimal-iso` | Type of installation ISO to generate |
| `ai_network_prefix` | `10.10.10` | Network prefix for the cluster network |
| `ai_workers_macs` | `[]` | MAC addresses for worker interfaces (auto-generated) |
| `ai_workers_macs2` | `[]` | MAC addresses for secondary worker interfaces (auto-generated) |
| `ai_ocp_vmname_worker_prefix` | `"worker-{{ cluster_name }}"` | Prefix for worker VM names |
| `ai_storage_class` | `ocs-storagecluster-ceph-rbd` | Storage class for worker PVCs |
| `ai_configure_hosts` | `[]` | Host configuration data (auto-populated) |

### Optional Variables

| Variable | Description |
|----------|-------------|
| `ai_workers_cores` | Number of CPU cores per worker VM |
| `ai_workers_memory` | Memory allocation per worker VM |
| `ai_attach_workers_networks` | Additional networks to attach to workers |
| `ai_attach_workers_macs` | MAC addresses for additional networks |
| `ai_workers_extra_disks` | Extra disk definitions for workers |
| `ai_install_use_network` | Override network name for installation |
| `worker_only` | When `true`, remove worker role from control-plane nodes and mark masters non-schedulable (default: `false`) |
| `worker_drain_control_plane` | When `true` (requires `worker_only`), drain existing workloads from control-plane nodes onto new workers (default: `false`) |

## Dependencies

None.

## Example Playbook

### Basic Usage

```yaml
---
- name: Scale OpenShift cluster
  hosts: localhost
  roles:
    - role: host_ocp4_assisted_scale
      vars:
        openshift_api_url: "https://api.cluster.example.com:6443"
        openshift_cluster_admin_token: "{{ vault_cluster_token }}"
        sandbox_openshift_api_url: "https://api.sandbox.example.com:6443"
        sandbox_openshift_api_key: "{{ vault_sandbox_token }}"
        ai_offline_token: "{{ vault_ai_token }}"
        worker_instance_count: 2
```

### Advanced Usage with Custom Resources

```yaml
---
- name: Scale OpenShift cluster with custom worker configuration
  hosts: localhost
  roles:
    - role: host_ocp4_assisted_scale
      vars:
        openshift_api_url: "https://api.cluster.example.com:6443"
        openshift_cluster_admin_token: "{{ vault_cluster_token }}"
        sandbox_openshift_api_url: "https://api.sandbox.example.com:6443"
        sandbox_openshift_api_key: "{{ vault_sandbox_token }}"
        ai_offline_token: "{{ vault_ai_token }}"
        worker_instance_count: 3
        ai_workers_cores: 8
        ai_workers_memory: "16Gi"
        ai_storage_class: "ocs-storagecluster-ceph-rbd"
        ai_attach_workers_networks:
          - "storage-network"
```

### Worker-Only Mode (Dedicated Workers)

```yaml
---
- name: Scale OpenShift cluster with dedicated workers
  hosts: localhost
  roles:
    - role: host_ocp4_assisted_scale
      vars:
        openshift_api_url: "https://api.cluster.example.com:6443"
        openshift_cluster_admin_token: "{{ vault_cluster_token }}"
        sandbox_openshift_api_url: "https://api.sandbox.example.com:6443"
        sandbox_openshift_api_key: "{{ vault_sandbox_token }}"
        ai_offline_token: "{{ vault_ai_token }}"
        worker_instance_count: 2
        worker_only: true
        worker_drain_control_plane: true
```

This will add 2 worker nodes, mark control-plane nodes as non-schedulable, remove the worker label from them, drain existing workloads onto the new workers, and uncordon the control-plane nodes.

## Architecture

### Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Query current worker count                              │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Import cluster to Assisted Installer                    │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Generate MAC addresses & network config                 │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Create infrastructure environment & download ISO         │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Create worker VMs on KubeVirt                           │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Wait for hosts to register with Assisted Installer      │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Approve CSRs & wait for nodes to join cluster           │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. Scale IngressController to match worker count           │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ 9. Configure worker-only mode (optional)                   │
└─────────────────────────────────────────────────────────────┘
```

## Tasks Breakdown

### Main Tasks (`tasks/main.yaml`)

- Gets current worker node count from the target cluster
- Imports the cluster into Assisted Installer
- Updates DNS domain for SNO (Single Node OpenShift) if applicable
- Generates unique MAC addresses for new worker interfaces
- Creates static network configuration
- Creates infrastructure environment with installation ISO
- Creates PVC for the installation ISO
- Creates worker VMs on KubeVirt
- Configures host roles and installation disks
- Waits for hosts to be ready in Assisted Installer
- Triggers CSR approval process

### CSR Approval Tasks (`tasks/approve_csr_nodes.yaml`)

- Retrieves pending Certificate Signing Requests
- Approves CSRs via Kubernetes API
- Monitors node readiness
- Recursively approves additional CSRs as they appear
- Scales IngressController replicas to match worker count

### Worker-Only Mode (`tasks/worker_only.yaml`)

- Sets `mastersSchedulable: false` on the Scheduler object
- Retrieves control-plane nodes
- Removes the `node-role.kubernetes.io/worker` label from control-plane nodes
- Optionally drains workloads from control-plane nodes (when `worker_drain_control_plane: true`)
- Uncordons control-plane nodes after drain (taint prevents new scheduling)

### Worker VM Creation (`tasks/kubevirt/create_workers.yaml`)

- Configures VM network interfaces and MAC addresses
- Adds additional networks if specified
- Creates data volumes for root disk and installation media
- Configures VM specifications (CPU, memory, disks)
- Creates the KubeVirt VirtualMachine resource
- Waits for VM to reach Running state

## Templates

### `installation-iso.yaml.j2`

Jinja2 template for creating a PVC that contains the Assisted Installer ISO image.

### `static_network_config_full.yaml.j2`

Jinja2 template for generating static network configuration for the new worker nodes.

## Notes

- The role supports both SNO (Single Node OpenShift) and multi-node cluster scaling
- MAC addresses are automatically generated using a deterministic algorithm based on cluster name and worker index
- The role uses a recursive approach for CSR approval to handle the multiple rounds of CSRs that appear during node bootstrap
- Worker VMs are configured with live migration support (`evictionStrategy: LiveMigrate`)
- The role assumes KubeVirt is available on the sandbox cluster for hosting worker VMs

## Troubleshooting

### Workers Not Appearing in Assisted Installer

- Verify network connectivity between the KubeVirt cluster and Assisted Installer service
- Check that the installation ISO downloaded correctly
- Ensure MAC addresses are unique and not conflicting with existing VMs

### CSR Approval Fails

- Verify the `openshift_cluster_admin_token` has sufficient permissions
- Check that the API URL is accessible from the Ansible control node
- Review pending CSRs manually: `oc get csr`

### VM Creation Fails

- Verify the storage class exists and has available capacity
- Check that the sandbox cluster has sufficient resources (CPU, memory)
- Ensure the namespace exists on the sandbox cluster

## License

Apache License 2.0

## Author Information

This role is part of AgnosticD, maintained by Red Hat.

