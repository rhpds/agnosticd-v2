"""Exercise the real ARO dispatcher with a harmless local installer stub."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]


class AroDispatchTests(unittest.TestCase):
    def run_dispatch(self, install):
        with tempfile.TemporaryDirectory(prefix='aro-dispatch-') as tmp:
            root = Path(tmp)
            role = root / 'ansible_collections/agnosticd/cloud_provider_azure/roles/host_ocp4_aro_install/tasks'
            role.mkdir(parents=True)
            (role / 'main.yml').write_text('''---

- name: Verify installer inherits bastion delegation
  ansible.builtin.assert:
    that:
    - "'bastion-test' in ansible_delegated_vars"
    - inventory_hostname == 'localhost'

- name: Mark installer invocation
  ansible.builtin.set_fact:
    aro_dispatch_ran: true

- name: Verify installer tasks can explicitly delegate back to controller
  delegate_to: localhost
  ansible.builtin.assert:
    that: "'localhost' in ansible_delegated_vars"
''')
            playbook = root / 'dispatch.yml'
            playbook.write_text('''---

- name: Exercise ARO installation dispatch without Azure access
  hosts: localhost
  connection: local
  gather_facts: false
  vars:
    host_ocp4_deploy_installation_method: aro
  tasks:

  - name: Add local bastion stub
    ansible.builtin.add_host:
      name: bastion-test
      groups: bastions
      ansible_connection: local

  - name: Invoke real deployment dispatcher
    ansible.builtin.include_role:
      name: host_ocp4_deploy

  - name: Verify installation flag is honored
    ansible.builtin.assert:
      that: (aro_dispatch_ran | default(false)) == (host_ocp4_deploy_install_ocp4 | bool)
''')
            config = root / 'ansible.cfg'
            config.write_text('[defaults]\nretry_files_enabled = false\n')
            env = dict(os.environ)
            env.update(ANSIBLE_CONFIG=str(config), ANSIBLE_COLLECTIONS_PATH=str(root),
                       ANSIBLE_ROLES_PATH=str(REPO / 'ansible/roles'),
                       ANSIBLE_LOCAL_TEMP=str(root / 'local'), ANSIBLE_REMOTE_TEMP=str(root / 'remote'))
            result = subprocess.run([sys.executable, '-m', 'ansible.cli.playbook', str(playbook),
                                     '-e', json.dumps({'host_ocp4_deploy_install_ocp4': install})],
                                    cwd=root, env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_installer_runs_on_bastion_and_allows_controller_overrides(self):
        self.run_dispatch(True)

    def test_installation_can_be_disabled(self):
        self.run_dispatch(False)


if __name__ == '__main__':
    unittest.main()
