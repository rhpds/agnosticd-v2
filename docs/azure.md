# Azure OpenShift deployments

Use `config: openshift-cluster` and `cloud_provider: azure`. The Azure collection
supplies a Linux bastion and the provider-specific OpenShift infrastructure.
Two installation methods are supported:

- `host_ocp4_deploy_installation_method: openshift_install` for self-managed IPI.
- `host_ocp4_deploy_installation_method: aro` for standard Azure Red Hat OpenShift.

The implementation is in
[`agnosticd.cloud_provider_azure`](https://github.com/rhpds/cloud_provider_azure).
Its local checkout is `../agnosticd-v2-collections/rhpds/cloud_provider_azure`.
Every collection role has its own README and a commented `defaults/main.yml`.
The v2 `host_ocp4_deploy` role is a thin installation-method dispatcher; it does
not contain Azure API logic. Set `aro_deploy_hcp: true` to use the hosted-control-plane preview path.

## Choose and copy a sample

All samples document their variables inline and contain no credentials:

- [ARO sample](../ansible/configs/openshift-cluster/sample_vars/openshift-cluster-aro-azure.yml):
  replace the version marker with an exact regional ARO release and use the
  `aro_*` sizing/network variables.
- [ARO HCP preview sample](../ansible/configs/openshift-cluster/sample_vars/openshift-cluster-aro-hcp-azure.yml):
  use a new GUID, a supported HCP region and an exact advertised HCP release.
  It defaults to two workers and temporary administrative kubeconfig access.
- [IPI sample](../ansible/configs/openshift-cluster/sample_vars/openshift-cluster-azure.yml):
  choose the shared installer version, supply a Red Hat pull secret, and use the
  IPI machine size/count variables. Keep installer state for destruction.

Copy one to your own variables directory, replace the example `guid`, DNS zone
and region, and place real credentials in Vault or a separate protected file.
Use different GUIDs when testing the two methods as separate deployments. Do
not reuse a GUID to change installation method or ownership boundaries.

## Sandbox credentials and region

The sandbox allocation system is outside this implementation. Before provision
it must supply a subscription, service principal, existing sandbox resource group
and an already-delegated child DNS zone. The collection preserves that group,
zone and principal on destruction. It never allocates or returns subscriptions,
creates tenant applications, or edits the parent-zone delegation.

For flat input, a separate secrets file must supply:

```yaml
azure_subscription: <subscription UUID>
azure_service_principal_id: <application/client UUID>
azure_service_principal_password: <secret>
azure_tenant: <tenant UUID or domain>
azure_resource_group: <existing sandbox resource group>
```

Set the remaining flat input in your non-secret config:

```yaml
azure_region: eastus
azure_dns_zone: <actual delegated child zone>
```

Use the location code `eastus`, not the display name `East US`. This selects the
location of new deployment resources. The existing sandbox resource group's
metadata location may differ: an `eastus` sandbox group and its delegated DNS
zone can support a new `eastus2` HCP deployment. No sandbox cleanup or relocation
is needed for that difference. Existing deployment ownership and region-change
guards still apply to deployment resources.

Alternatively, supply exactly one complete nested credential:

```yaml
azure_sandbox:
  credentials:
  - subscription_id: <subscription UUID>
    app_id: <application/client UUID>
    password: <secret>
    tenant: <tenant UUID or domain>
    resource_group: <existing sandbox resource group>
    azure_region: eastus
```

A defined `azure_sandbox` is authoritative, including its region. Its fields
are not filled from flat variables. Omit the variable entirely for flat input;
null, `{}` or an empty credential list is invalid. Flat `azure_subscription_id`
and `azure_tenant_id` are aliases only when the canonical fields are undefined.
`azure_application` and `sandbox_name` are optional sandbox metadata, not
authentication inputs. The provisioning CLI uses the supplied credentials in an
isolated session rather than the controller's existing interactive login.

## Bastion and RHEL configuration

Both methods first provision `bastion-<guid>` with an SSH key generated/recovered
by the shared v2 provision-key roles. The `openshift-cluster` config selects PAYG
RHEL 10; the collection's standalone image default is RHEL 9. Both use SSH user `azure`,
`Standard_D2s_v5`, a 64 GiB Premium OS disk and a static public IP. The provisioned
bastion is added to `groups.bastions`, and v2 generates SSH configuration that
selects the proper provision key for its VM-name inventory target.

Use `azure_bastion_user`, `azure_bastion_vm_size`, `azure_bastion_ssh_source` and
the complete `azure_bastion_image` mapping shown in each sample. To select a new
RHEL 10 VM, use `sku: 10-lvm-gen2` with publisher `RedHat`, offer `RHEL` and a
chosen image version. A successful existing ARM deployment is reused; changing
the image mapping does not reimage that bastion. Choose image/SKU availability
and repository registration settings appropriate to the subscription.

The samples disable shared Satellite/RHN registration for the PAYG image's
repository integration. If your image/environment uses either registration
method, enable the corresponding shared role and supply its existing variables
and secrets. The Azure CLI installer needs working DNF repositories, outbound
access to Microsoft packages, and privilege escalation on the bastion.
Optional student setup is performed by the normal bastion role before ARO copies
the resulting kubeconfig to that user's home.

## Select OpenShift inputs

| Purpose | Standard ARO | Self-managed IPI |
| --- | --- | --- |
| Version | `aro_version`: exact regional release | `host_ocp4_installer_version`: shared installer channel or exact release |
| Control-plane VM size | `aro_master_vm_size` | `control_plane_instance_type` |
| Worker VM size | `aro_worker_vm_size` | `worker_instance_type` |
| Worker count | `aro_worker_count`, at least 3 | `worker_instance_count` |
| Cluster identity | `aro_identity_mode` | Supplied sandbox service principal |
| Pull secret | Optional `ocp4_pull_secret` | Required `ocp4_pull_secret` JSON text |
| Cluster API/ingress DNS | Azure-managed | Based on `cluster_name` and `cluster_dns_zone` |

ARO defaults to `managed_identity`, three `Standard_D8s_v5` control-plane nodes
and three `Standard_D4s_v5` workers with 128 GiB worker disks. Its preflight
checks region/version, provider registrations, VM SKU restrictions and both
regional and family vCPU quota, including one extra control-plane-sized bootstrap
machine. The default layout needs 44 available vCPUs for that check, beyond
existing usage. Provider registration can be performed by the install operation
when needed. Quota and SKU availability remain subscription/region-specific.

ARO creation uses Azure CLI/API calls. The ARO role downloads only `oc` and
`kubectl` for the exact selected `aro_version`; it does not invoke the shared
`host_ocp4_installer` role or download `openshift-install`. The IPI
`host_ocp4_installer_version` setting cannot override ARO's client version.
`aro_client_download_url` and `aro_client_install_dir` are documented overrides
for a trusted client mirror/archive and the bastion installation directory.

Inspect ARO versions with the read-only command:

```console
az aro get-versions --location eastus --output table
```

Set `aro_identity_mode: service_principal` only when the supplied principal and
directory permissions satisfy that mode. Managed-identity mode still uses the
sandbox principal to authenticate the provisioning operation. The mode changes
the cluster identity, not the source of Ansible authentication.

For IPI, `cluster_dns_zone` must equal the delegated Azure zone. The sample sets
it explicitly because the generic config default prepends `guid` to `base_domain`;
the Azure child zone commonly already includes the GUID. ARO's assigned API and
ingress domains are not changed by setting `base_domain`.

## Provision, lifecycle and destruction

Use your normal v2 runner/execution environment so the provider collection and
shared roles/collections are installed. The provider dependency installer sources
the collection's Git repository. When testing local source instead, build/install
that collection into the controller's `ANSIBLE_COLLECTIONS_PATH`; ensure the
runner is actually using the new build rather than a cached installed version.
Rebuild the public execution environment when its Azure CLI pin changes.

With a prepared Ansible environment, the playbook entrypoints are:

```console
ansible-playbook -i localhost, ansible/main.yml -e @/path/to/azure-config.yml -e @/path/to/azure-secrets.yml
ansible-playbook -i localhost, ansible/lifecycle.yml -e @/path/to/azure-config.yml -e @/path/to/azure-secrets.yml -e ACTION=status -e output_dir=/path/to/restored-output
ansible-playbook -i localhost, ansible/destroy.yml -e @/path/to/azure-config.yml -e @/path/to/azure-secrets.yml -e ACTION=destroy -e output_dir=/path/to/restored-output
```

The paths are placeholders. Use the real existing output directory for later
jobs. Lifecycle `ACTION` accepts `start`, `stop`, or `status`. Status is written
to `<output_dir>/status.txt`. ARO power actions affect only the bastion and report
the managed cluster status; they never power Azure-managed cluster VMs. IPI power
actions also affect the self-managed cluster VMs.

The normal provisioning flow is:

1. Normalize credentials/settings and record exact ownership boundaries.
2. Create/reuse the owned bastion infrastructure and `bastion` A record.
3. Discover bastion inventory, generate SSH configuration and configure the guest.
4. For IPI, prepare the installer group, credential file and Azure YAML fragments.
   For ARO, dispatch to the collection's `host_ocp4_aro_install` role.
5. Export kubeconfig/access information for shared v2 workloads.

Destruction restores the same context, starts machines needed for cleanup,
removes configured external workloads, deletes the cluster, then deletes owned
bastion infrastructure and its DNS record. Destroy preparation sets
`azure_lifecycle_action: start` while retaining the global `ACTION: destroy`.
For ARO, deletion runs on the controller and removes the owned cluster group only
after the ARO API deletion succeeds. It also removes an owned leftover group
when cluster creation never happened. For IPI, the shared installer performs
cluster destruction from its preserved bastion directory/state.

The infrastructure destroy role refuses to delete the bastion while the cluster
resource group remains. Existing unowned resource groups or unowned `bastion`
DNS records are also refused. Do not remove these checks to force cleanup or put
unrelated resources into deployment-owned groups. Repeated completed cleanup is
a no-op. If IPI state is lost, recover it before retrying destruction.

## Artifacts and diagnostics

Keep the original variables and private output archive together. It contains
SSH private keys, installer artifacts, access files and
`<config>_<guid>_azure_ownership.json`. That ownership record is non-secret but
identifies the original subscription, tag, exact group IDs and DNS record.
Changes to these boundaries are rejected. ARO node sizes may change before
cluster creation after an absence check; an existing cluster's recorded sizes are
preserved for lifecycle and destroy jobs.

After a completed destroy, a provision retry can replace archived cluster settings,
including region, architecture and worker count, after read-only checks confirm
that the infrastructure, cluster and ARO-managed groups are all absent.
The subscription, project, group names and DNS ownership must still match.
Existing deployment resources prevent settings changes. Lifecycle/destroy jobs
require the original archived settings. Mismatch errors list the changed
public inputs and their archived/requested values. Sandbox validation completes
before the ownership archive is written; do not delete the archive to force a
retry past the checks.

ARO exports `<config>_<guid>_kubeconfig` and
`<config>_<guid>_kubeadmin-password` under `output_dir` with mode `u=rw,go=`. Bastion
copies remain available to its login user and optionally the student user.
The temporary bastion ARO CLI session is removed even after installation failure.
IPI's `~/.azure/osServicePrincipal.json` is retained for later installer use.

Do not log the normalized credential mapping, protected ARO result, kubeconfig,
password or IPI credential file. Public preflight errors include only selected
region/sizes and structured SKU restrictions or required/available quota. A failed
ARO cluster requires diagnosis and explicit destruction rather than automatic
recreation. Ownership failures require restoring the original context or an
explicitly reviewed repair, not silently adopting resources.

## Documentation and verification

Start with the collection's [role index](https://github.com/rhpds/cloud_provider_azure#roles)
and each role's README/defaults. Ansible magic variables (`hostvars`, `groups`,
loop items) come from Ansible; connection variables come from inventory. Generated
provider facts are documented as outputs rather than user-facing overrides.

Offline unit/integration checks use synthetic credentials and a fake Azure CLI.
They cover credential forms, ownership checks, rendering, delegation, protected
failure diagnostics and ordered/repeated destruction. They do not certify live
Azure policy, quota, Marketplace or ARO service behavior. Validate provision,
rerun, access, workloads, lifecycle and cleanup in the intended subscription
before relying on a new deployment configuration.

Sandbox allocation/release, parent delegation, Windows bastions, private ARO
endpoints, external OIDC configuration and migration of existing v1 deployments remain
outside this implementation.

## HCP preview deployments

Self-managed Azure IPI and standard ARO have completed live provisioning tests.
HCP remains experimental: the latest live test created a ready control plane,
but the worker pool failed with Azure `DeadlineExceeded` and
`hypershift node pool not cached yet`. No worker VMs appeared. The underlying
cause remains under engineering investigation; offline test success does not
establish that HCP provisioning works. Leave `aro_deploy_hcp: false` for the
validated standard ARO path. A larger Ansible timeout cannot recover an Azure
operation that has already reached terminal state `Failed`.

Use the annotated `openshift-cluster-aro-hcp-azure.yml` sample for a new GUID.
`aro_deploy_hcp` defaults false; enabling it retains the ARO installation method
and roles while selecting a separate HCP provider branch in the Azure collection.
It defaults to two D4s_v5 workers and one node pool in logical zone 1, managed
identities, public API/ingress and an owned customer-managed encryption key.
Use a supported HCP region such as eastus2; the sandbox group may be elsewhere. The
existing eastus classic example is not an HCP-region default.

HCP exports a temporary admin kubeconfig rather than a kubeadmin password.
It expires after 24 hours. After restoring the original variables/archive,
initializing the Azure provider on localhost and discovering/configuring bastion
SSH access, run `agnosticd.cloud_provider_azure.host_ocp4_aro_hcp_credentials`
on that bastion to refresh controller, login-user and optional student copies.
Expiry is in `<config>_<guid>_hcp_credentials.json`. Regular user/console login
requires external OIDC, which is deferred. No HCP password is published.

Destroy waits for node pools, cluster and managed-group cleanup before deleting
owned network/identity/encryption prerequisites. The vault is soft-deleted for
seven days and never purged automatically; a verified same-deployment archive
permits recovery for a provision retry. Architecture changes require a provision
run to verify that all archived deployment groups are absent. Keep the ownership
archive; do not delete it to bypass architecture or identity checks.
