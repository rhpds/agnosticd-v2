# host_ocp4_deploy

Dispatch OpenShift installation to the task file selected by
`host_ocp4_deploy_installation_method`. The common `openshift-cluster` software
play invokes this role after infrastructure and bastion preparation.

[defaults/main.yml](defaults/main.yml) documents the installation-method selector
and `host_ocp4_deploy_install_ocp4` flag. Provider-specific options belong to the
selected installer role or cloud-provider collection.

## Azure Red Hat OpenShift

Select standard ARO with:

```yaml
cloud_provider: azure
host_ocp4_deploy_installation_method: aro
host_ocp4_deploy_install_ocp4: true
```

The Azure provider must already have run `initialize` on localhost, provisioned
the Linux bastion and added it to `groups.bastions` with usable SSH configuration.
The ARO task file delegates an enclosing block to the first bastion and includes
`agnosticd.cloud_provider_azure.host_ocp4_aro_install` within that block. Ansible
does not accept `delegate_to` directly on an `include_role` task. The collection
role can explicitly delegate selected tasks back to the controller.

Set `aro_version` to an exact supported regional release. VM sizing, identity
mode, CIDRs, credential handling, access artifacts and installation retries are
documented by the Azure collection's `initialize` and `host_ocp4_aro_install`
role READMEs/defaults. `groups` is Ansible's inventory magic variable, not an input
to declare or replace in this role's defaults.

Setting `host_ocp4_deploy_install_ocp4: false` skips the ARO installer include.
The dispatcher still expects a bastion inventory group for delegation. It does
not verify that an existing cluster is healthy or restore a missing kubeconfig.

ARO destruction is separate: the Azure config's destroy playbook calls
`agnosticd.cloud_provider_azure.host_ocp4_aro_destroy` on localhost before the
owned bastion infrastructure is deleted. The installation dispatcher does not
handle deletion. Hosted control planes use the same dispatcher with
`aro_deploy_hcp: true`; the Azure collection selects that experimental branch.
See the Azure guide for its current validation status.

See [the Azure guide](../../../docs/azure.md) and the commented
[ARO sample](../../configs/openshift-cluster/sample_vars/openshift-cluster-aro-azure.yml).
