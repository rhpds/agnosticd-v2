"""Run the installer readiness tasks against local Kubernetes API fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

REPO = Path(__file__).resolve().parents[2]
TASK_DIR = REPO / 'ansible/roles/host_ocp4_agent_installer/tasks'

STUB = '''#!/usr/bin/python
import json
import os
from pathlib import Path
from ansible.module_utils.basic import AnsibleModule

module = AnsibleModule(argument_spec={
    'api_version': {'type': 'str'},
    'kind': {'type': 'str'},
    'kubeconfig': {'type': 'str'},
    'validate_certs': {'type': 'bool'},
})
if module.params['kubeconfig'] != '/guest-output/openshift-cluster_test_kubeconfig':
    module.fail_json(msg='Readiness must query the installed guest cluster')
root = Path(os.environ['AGENT_READINESS_FIXTURES'])
fixtures = json.loads((root / 'fixtures.json').read_text())
kind = module.params['kind']
state = root / (kind + '.count')
count = int(state.read_text()) if state.exists() else 0
state.write_text(str(count + 1))
responses = fixtures[kind]
response = responses[min(count, len(responses) - 1)]
if response.get('failed'):
    module.fail_json(msg='Simulated transient API failure')
module.exit_json(changed=False, **response)
'''


def resource(name, conditions, **extra):
    return {'metadata': {'name': name}, 'status': {'conditions': [
        {'type': kind, 'status': status} for kind, status in conditions.items()
    ]}, **extra}


def healthy_fixtures(workers=1):
    pools = [resource('master', {'Updated': 'True', 'Updating': 'False', 'Degraded': 'False'})]
    # SNO/compact clusters may expose an empty worker pool; accept it if healthy.
    pools.append(resource('worker', {'Updated': 'True', 'Updating': 'False', 'Degraded': 'False'}))
    operators = [resource(name, {'Available': 'True', 'Progressing': 'False', 'Degraded': 'False'})
                 for name in ['machine-config', 'network', 'authentication']]
    nodes = [resource(str(i), {'Ready': 'True'}, spec={}) for i in range(3 + workers)]
    return {kind: [{'resources': values}] for kind, values in [
        ('MachineConfigPool', pools), ('ClusterOperator', operators), ('Node', nodes)
    ]}


class AgentReadinessTests(unittest.TestCase):
    def run_fixture(self, fixtures, workers=1, control_planes=3, succeeds=True, failed_task=None):
        with tempfile.TemporaryDirectory(prefix='agent-readiness-') as tmp:
            root = Path(tmp)
            module_dir = root / 'ansible_collections/kubernetes/core/plugins/modules'
            module_dir.mkdir(parents=True)
            (module_dir / 'k8s_info.py').write_text(STUB)
            (root / 'fixtures.json').write_text(json.dumps(fixtures))
            tasks = yaml.safe_load((TASK_DIR / 'wait_cluster_ready.yml').read_text())
            # Only shorten polling for tests; execute the real module arguments and until expressions.
            for task in tasks:
                task.update(retries=1, delay=0)
            playbook = root / 'readiness.yml'
            playbook.write_text(yaml.safe_dump([{
                'name': 'Exercise agent readiness', 'hosts': 'localhost',
                'connection': 'local', 'gather_facts': False,
                'vars': {'output_dir': '/guest-output', 'config': 'openshift-cluster',
                         'guid': 'test', 'control_plane_instance_count': control_planes,
                         'worker_instance_count': workers},
                'tasks': [{'name': 'Set controller output directory',
                           'ansible.builtin.set_fact': {'output_dir': '/guest-output'}}] + tasks,
            }], sort_keys=False))
            config = root / 'ansible.cfg'
            config.write_text('[defaults]\nretry_files_enabled = false\n')
            env = dict(os.environ)
            env.update(ANSIBLE_CONFIG=str(config), ANSIBLE_COLLECTIONS_PATH=str(root),
                       ANSIBLE_LOCAL_TEMP=str(root / 'local'), ANSIBLE_REMOTE_TEMP=str(root / 'remote'),
                       AGENT_READINESS_FIXTURES=str(root))
            result = subprocess.run([sys.executable, '-m', 'ansible.cli.playbook',
                                     '-i', 'localhost,', str(playbook)],
                                    cwd=root, env=env, capture_output=True, text=True,
                                    check=False, timeout=60)
            output = result.stdout + result.stderr
            self.assertNotIn('Finalization of task args', output)
            self.assertNotIn('Error while evaluating conditional', output)
            if succeeds:
                self.assertEqual(result.returncode, 0, output)
                self.assertTrue((root / 'Node.count').exists(), output)
            else:
                self.assertNotEqual(result.returncode, 0, output)
                self.assertIn(failed_task, output)
                self.assertIn('FAILED!', output)
            return {kind: int((root / (kind + '.count')).read_text())
                    for kind in fixtures if (root / (kind + '.count')).exists()}

    def test_healthy_multinode_and_compact_clusters(self):
        for workers in [0, 1]:
            with self.subTest(workers=workers):
                self.run_fixture(healthy_fixtures(workers), workers=workers)

    def test_sno_without_worker_pool(self):
        fixtures = healthy_fixtures(0)
        fixtures['MachineConfigPool'][0]['resources'].pop()
        fixtures['Node'][0]['resources'] = fixtures['Node'][0]['resources'][:1]
        self.run_fixture(fixtures, workers=0, control_planes=1)

    def test_unhealthy_or_missing_conditions_block_handoff(self):
        cases = [
            ('MachineConfigPool', 'Updated', 'False'),
            ('MachineConfigPool', 'Updating', 'True'),
            ('MachineConfigPool', 'Degraded', 'True'),
            ('ClusterOperator', 'Available', 'False'),
            ('ClusterOperator', 'Progressing', 'True'),
            ('ClusterOperator', 'Degraded', 'True'),
            ('Node', 'Ready', 'False'),
            ('Node', 'Ready', 'Unknown'),
        ]
        task_names = {'MachineConfigPool': 'Wait for MachineConfigPools',
                      'ClusterOperator': 'Wait for all ClusterOperators',
                      'Node': 'Wait for all expected nodes'}
        for kind, condition, value in cases:
            with self.subTest(kind=kind, condition=condition, value=value):
                fixtures = healthy_fixtures()
                for entry in fixtures[kind][0]['resources'][-1]['status']['conditions']:
                    if entry['type'] == condition:
                        entry['status'] = value
                self.run_fixture(fixtures, succeeds=False, failed_task=task_names[kind])
        for kind in task_names:
            with self.subTest(missing_conditions=kind):
                fixtures = healthy_fixtures()
                fixtures[kind][0]['resources'][-1]['status']['conditions'] = []
                self.run_fixture(fixtures, succeeds=False, failed_task=task_names[kind])

    def test_cordoned_and_missing_nodes_block_handoff(self):
        for cordoned in [True, False]:
            with self.subTest(cordoned=cordoned):
                fixtures = healthy_fixtures()
                nodes = fixtures['Node'][0]['resources']
                if cordoned:
                    nodes[-1]['spec']['unschedulable'] = True
                else:
                    nodes.pop()
                self.run_fixture(fixtures, succeeds=False, failed_task='Wait for all expected nodes')

    def test_empty_results_and_missing_required_pools_block_handoff(self):
        for kind in ['MachineConfigPool', 'ClusterOperator', 'Node']:
            with self.subTest(empty=kind):
                fixtures = healthy_fixtures()
                fixtures[kind][0]['resources'] = []
                self.run_fixture(fixtures, succeeds=False, failed_task='Wait for')
        for pool in ['master', 'worker']:
            with self.subTest(missing_pool=pool):
                fixtures = healthy_fixtures()
                fixtures['MachineConfigPool'][0]['resources'] = [
                    p for p in fixtures['MachineConfigPool'][0]['resources']
                    if p['metadata']['name'] != pool]
                self.run_fixture(fixtures, succeeds=False, failed_task='Wait for MachineConfigPools')

    def test_transient_api_errors_are_retried(self):
        fixtures = healthy_fixtures()
        for responses in fixtures.values():
            responses.insert(0, {'failed': True})
        counts = self.run_fixture(fixtures)
        self.assertEqual(counts, {'MachineConfigPool': 2, 'ClusterOperator': 2, 'Node': 2})

    def test_gate_runs_after_clusterversion_and_before_console(self):
        tasks = yaml.safe_load((TASK_DIR / 'wait_install.yml').read_text())
        names = [task['name'] for task in tasks]
        gate = names.index('Wait for installed cluster readiness before handing off to workloads')
        self.assertGreater(gate, names.index('Wait for ClusterVersion installation to complete'))
        self.assertLess(gate, names.index('Determine console URL'))
        self.assertEqual(tasks[gate]['ansible.builtin.include_tasks'], 'wait_cluster_ready.yml')


if __name__ == '__main__':
    unittest.main()
