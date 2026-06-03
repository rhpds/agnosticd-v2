# host_ocp4_hcp_cnv_onprem_install

Creates an OpenShift cluster using Hosted Control Planes (HCP) on an on-prem management cluster with OpenShift Virtualization (CNV/KubeVirt).

## Purpose

This role automates the creation of guest OpenShift clusters on a bare-metal management cluster that has HyperShift and OpenShift Virtualization installed. It is designed for **on-prem environments** where AWS Route53 and external ACME certificate issuers are not available.

The role was modeled on the `hcp-vm` cluster running on `fusion.isys.hpc.dc.uq.edu.au` (OCP 4.20, KubeVirt platform, baseDomainPassthrough DNS, HighlyAvailable control plane, lvms-hcp-etcd storage).

### How it differs from the existing `host-ocp4-hcp-cnv-install` role

| Aspect | Existing role | This role |
|---|---|---|
| DNS | Route53 (AWS) required | baseDomainPassthrough (default) or nsupdate |
| Certificates | cert-manager ACME ClusterIssuer | Not needed (passthrough handles it) |
| Auth to mgmt cluster | `sandbox_hcp.*` nested credentials | Direct token or username/password |
| HA policy | SingleReplica | HighlyAvailable (configurable) |
| etcd storage | `ocs-external-storagecluster-ceph-rbd` | Configurable (default: `lvms-hcp-etcd`) |
| etcd encryption | Not configured | aescbc enabled by default |
| Worker autorepair | Disabled | Enabled |
| Network multiqueue | Not set | Enabled |

## Prerequisites

The management cluster must have:

- **OpenShift Virtualization (CNV)** operator installed and healthy
- **HyperShift** operator (via Multicluster Engine) installed
- **Storage classes** for etcd (`lvms-hcp-etcd`) and VM disks (`ocs-storagecluster-ceph-rbd`)
- **MetalLB** or equivalent for LoadBalancer services (API server)
- Sufficient compute capacity for the guest cluster VMs

## Quick Start

### 1. Create a playbook

```yaml
# deploy-hcp.yml
---
- name: Deploy On-Prem HCP Cluster
  hosts: localhost
  connection: local
  gather_facts: false
  roles:
    - host_ocp4_hcp_cnv_onprem_install
```

### 2. Create a vars file

Copy and edit the sample: `bin/templates/hcp-cnv-onprem.yml`

### 3. Create a secrets file

Copy and edit the sample: `bin/templates/hcp-cnv-onprem-secrets.yml`

### 4. Run

```bash
ansible-playbook deploy-hcp.yml \
  -e @bin/templates/hcp-cnv-onprem.yml \
  -e @bin/templates/hcp-cnv-onprem-secrets.yml \
  -e guid=mycluster1
```

## Variables

### Required

| Variable | Description |
|---|---|
| `hcp_onprem_mgmt_api_url` | Management cluster API URL |
| `hcp_onprem_mgmt_token` **or** `hcp_onprem_mgmt_username` + `hcp_onprem_mgmt_password` | Auth credentials |
| `hcp_onprem_base_domain` | Base domain (e.g., `apps.fusion.isys.hpc.dc.uq.edu.au`) |
| `ocp4_pull_secret` | Red Hat pull secret (JSON) |
| `guid` | Unique identifier for this cluster |

### Cluster Configuration

| Variable | Default | Description |
|---|---|---|
| `hcp_onprem_cluster_name` | `hcp-{{ guid }}` | HostedCluster resource name |
| `hcp_onprem_cluster_version` | `4.20` | OCP version (`x.y` for latest, `x.y.z` for specific) |
| `hcp_onprem_namespace` | `clusters` | Namespace for HCP resources |
| `hcp_onprem_channel` | `fast-4.20` | Update channel |

### Worker Sizing

| Variable | Default | Description |
|---|---|---|
| `hcp_onprem_worker_cores` | `32` | vCPUs per worker VM |
| `hcp_onprem_worker_memory` | `64Gi` | RAM per worker VM |
| `hcp_onprem_worker_root_volume_size` | `300Gi` | Disk per worker VM |
| `hcp_onprem_worker_count` | `3` | Number of worker VMs |
| `hcp_onprem_worker_autoscale` | `false` | Enable autoscaling |
| `hcp_onprem_worker_min_count` | `3` | Min workers (autoscale) |
| `hcp_onprem_worker_max_count` | `10` | Max workers (autoscale) |

### DNS

| Variable | Default | Description |
|---|---|---|
| `hcp_onprem_dns_method` | `passthrough` | `passthrough` or `nsupdate` |
| `hcp_onprem_nsupdate_server` | `""` | DNS server for nsupdate |
| `hcp_onprem_nsupdate_zone` | `""` | DNS zone for nsupdate |
| `hcp_onprem_nsupdate_key_name` | `""` | TSIG key name |
| `hcp_onprem_nsupdate_key_secret` | `""` | TSIG key secret |

### HA and Storage

| Variable | Default | Description |
|---|---|---|
| `hcp_onprem_controller_availability` | `HighlyAvailable` | Control plane HA policy |
| `hcp_onprem_infra_availability` | `HighlyAvailable` | Infrastructure HA policy |
| `hcp_onprem_etcd_storage_class` | `lvms-hcp-etcd` | StorageClass for etcd PVCs |
| `hcp_onprem_etcd_pvc_size` | `8Gi` | etcd PVC size |

### Authentication

| Variable | Default | Description |
|---|---|---|
| `hcp_onprem_auth_method` | `htpasswd` | Auth method |
| `hcp_onprem_admin_user` | `admin` | Cluster admin username |
| `hcp_onprem_admin_password` | `""` | Admin password (auto-generated if empty) |
| `hcp_onprem_user_count` | `0` | Number of regular users |
| `hcp_onprem_user_password` | `""` | Common password (random per user if empty) |

## Output Variables

After a successful deployment, the role sets the following facts that can be used in subsequent tasks or roles:

| Variable | Description | Example |
|---|---|---|
| `hcp_onprem_result_cluster_name` | HostedCluster resource name | `hcp-test01` |
| `hcp_onprem_result_api_url` | Guest cluster API server URL | `https://10.120.96.116:6443` |
| `hcp_onprem_result_console_url` | Guest cluster console URL | `https://console-openshift-console.apps...` |
| `hcp_onprem_result_ingress_domain` | Guest cluster apps domain | `apps.hcp-test01.apps.fusion...` |
| `hcp_onprem_result_lb_ip` | MetalLB LoadBalancer IP assigned | `10.120.96.116` |
| `hcp_onprem_result_kubeconfig_path` | Path to guest kubeconfig file | `/tmp/kubeconfig-hcp-test01` |
| `hcp_onprem_result_kubeconfig_b64` | Base64-encoded guest kubeconfig | (for passing to other roles) |
| `hcp_onprem_result_admin_user` | Cluster admin username | `admin` |
| `hcp_onprem_result_admin_password` | Cluster admin password | (auto-generated) |
| `hcp_onprem_result_user_passwords` | List of regular user passwords | `['pass1', 'pass2']` |
| `hcp_onprem_result_worker_count` | Number of ready worker nodes | `2` |
| `hcp_onprem_result_ocp_version` | Resolved OCP version | `4.20.8` |
| `hcp_onprem_result_namespace` | HCP resources namespace | `clusters` |
| `hcp_onprem_result_control_plane_namespace` | Control plane pods namespace | `clusters-hcp-test01` |

### Using output variables in a playbook

```yaml
- name: Deploy and configure cluster
  hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - name: Deploy HCP cluster
      ansible.builtin.include_role:
        name: host_ocp4_hcp_cnv_onprem_install

    - name: Use cluster info in subsequent tasks
      ansible.builtin.debug:
        msg: |
          Cluster {{ hcp_onprem_result_cluster_name }} is ready!
          API: {{ hcp_onprem_result_api_url }}
          Login: oc login -u {{ hcp_onprem_result_admin_user }} -p {{ hcp_onprem_result_admin_password }}
```

## Destroying a Cluster

```yaml
# destroy-hcp.yml
---
- name: Destroy On-Prem HCP Cluster
  hosts: localhost
  connection: local
  gather_facts: false
  roles:
    - host_ocp4_hcp_cnv_onprem_destroy
```

```bash
ansible-playbook destroy-hcp.yml \
  -e hcp_onprem_mgmt_api_url="https://api.fusion.isys.hpc.dc.uq.edu.au:6443" \
  -e hcp_onprem_mgmt_token="sha256~YOUR_TOKEN" \
  -e guid=mycluster1
```

## Testing

### Syntax check
```bash
ansible-playbook deploy-hcp.yml --syntax-check
```

### Deploy a small test cluster
```bash
ansible-playbook deploy-hcp.yml \
  -e @bin/templates/hcp-cnv-onprem.yml \
  -e @bin/templates/hcp-cnv-onprem-secrets.yml \
  -e guid=test01 \
  -e hcp_onprem_worker_cores=8 \
  -e hcp_onprem_worker_memory=16Gi \
  -e hcp_onprem_worker_root_volume_size=100Gi \
  -e hcp_onprem_worker_count=2 \
  -e hcp_onprem_controller_availability=SingleReplica \
  -e hcp_onprem_infra_availability=SingleReplica
```

### Verify
```bash
oc get hostedclusters -n clusters
oc get nodepools -n clusters
oc get vms -n clusters-hcp-test01
```

### Clean up
```bash
ansible-playbook destroy-hcp.yml \
  -e hcp_onprem_mgmt_api_url="https://api.fusion.isys.hpc.dc.uq.edu.au:6443" \
  -e hcp_onprem_mgmt_token="sha256~YOUR_TOKEN" \
  -e guid=test01
```
