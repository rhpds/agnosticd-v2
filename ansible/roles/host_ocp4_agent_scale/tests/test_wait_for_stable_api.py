"""Run the native Ansible API guard against a mock oc; never access a cluster.

python3 -m unittest discover -s ansible/roles/host_ocp4_agent_scale/tests -v
Uses ansible-playbook on PATH, or uvx --from ansible-core as a fallback.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROLE = Path(__file__).resolve().parents[1]
PLAYBOOK = ([shutil.which("ansible-playbook")] if shutil.which("ansible-playbook")
            else ["uvx", "--from", "ansible-core", "ansible-playbook"])


class StableApiTests(unittest.TestCase):
    def run_guard(self, nodes=None, latest=8, mode="healthy", unhealthy=False,
                  window=0):
        if nodes is None:
            nodes = [{"nodeName": "master", "currentRevision": 8}]
        for index, node in enumerate(nodes):
            node.setdefault("nodeName", "master-" + str(index))
        conditions = [
            {"type": "Available", "status": "True"},
            {"type": "Progressing", "status": "True" if unhealthy else "False"},
            {"type": "Degraded", "status": "False"},
        ]
        operators = {"items": [
            {"metadata": {"name": n}, "status": {"conditions": conditions}}
            for n in ("kube-apiserver", "authentication", "ingress")
        ]}
        apiserver = {"status": {"latestAvailableRevision": latest, "nodeStatuses": nodes}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "operators.json").write_text(json.dumps(operators))
            (root / "apiserver.json").write_text(json.dumps(apiserver))
            mock = root / "oc"
            mock.write_text("#!" + sys.executable + "\n" + '''
import json, pathlib, sys
root = pathlib.Path(__file__).parent
mode = (root / 'mode').read_text()
args = ' '.join(sys.argv[1:])
if 'readyz' in args:
    if mode == 'down': sys.exit(1)
    if mode == 'recover' and not (root / 'failed-once').exists():
        (root / 'failed-once').touch()
        sys.exit(1)
    print('ok')
elif 'clusteroperators' in args:
    print('invalid-json' if mode == 'malformed' else (root / 'operators.json').read_text())
elif 'kubeapiserver.operator.openshift.io' in args:
    print((root / 'apiserver.json').read_text())
else:
    sys.exit(90)
''')
            mock.chmod(0o700)
            (root / "mode").write_text(mode)
            # JSON is valid YAML. Short test deadlines/windows only; production
            # task files and predicates are included without modifications.
            play = [{"hosts": "localhost", "connection": "local",
                     "gather_facts": False, "vars": {
                         "ansible_python_interpreter": sys.executable,
                         "agent_scale_oc_binary": str(mock),
                         "agent_scale_install_dir": tmp,
                         "agent_scale_api_timeout": 8 if mode == "recover" or window else 3,
                         "agent_scale_api_poll": 1,
                         "agent_scale_api_stability_window": window,
                     }, "tasks": [{"ansible.builtin.include_tasks": str(
                         ROLE / "tasks/wait_for_stable_api.yml")}] }]
            path = root / "play.yml"
            path.write_text(json.dumps(play))
            return subprocess.run(
                PLAYBOOK + ["-i", "localhost,", str(path)],
                capture_output=True, text=True, timeout=45,
                env={**os.environ, "ANSIBLE_CONFIG": str(root / "ansible.cfg"),
                     "ANSIBLE_NOCOLOR": "1"},
            )

    def test_idle_target_representations(self):
        for target in ("omitted", None, 0, 8):
            with self.subTest(target=target):
                node = {"nodeName": "master", "currentRevision": 8}
                if target != "omitted":
                    node["targetRevision"] = target
                result = self.run_guard(nodes=[node])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pending_rollout_is_rejected_with_revisions(self):
        result = self.run_guard(nodes=[{"currentRevision": 8, "targetRevision": 9}])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target=9", result.stdout)

    def test_outdated_node_is_rejected(self):
        result = self.run_guard(nodes=[{"currentRevision": 7, "targetRevision": 0}])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("current=7", result.stdout)

    def test_missing_revision_status_is_rejected(self):
        result = self.run_guard(nodes=[])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing latest API revision or node status", result.stdout)

    def test_every_node_must_be_current(self):
        result = self.run_guard(nodes=[{"currentRevision": 8}, {"currentRevision": 7}])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("current=7", result.stdout)

    def test_operator_failure_is_identified(self):
        result = self.run_guard(unhealthy=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("authentication not settled", result.stdout)

    def test_unreachable_api_is_identified(self):
        result = self.run_guard(mode="down")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("API /readyz request failed", result.stdout)

    def test_malformed_response_fails_closed(self):
        result = self.run_guard(mode="malformed")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("ISO generation", result.stdout.split("PLAY RECAP")[0][-100:])

    def test_transient_api_failure_can_recover(self):
        result = self.run_guard(mode="recover")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("API /readyz request failed", result.stdout)

    def test_healthy_window_requires_multiple_samples(self):
        result = self.run_guard(window=2)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGreaterEqual(result.stdout.count("TASK [Read API readiness"), 2)


if __name__ == "__main__":
    unittest.main()
