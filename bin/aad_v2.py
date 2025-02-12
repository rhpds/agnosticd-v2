import os
import sys
import argparse
import subprocess

# Directories
VARS_DIR = "../agnosticd-v2-vars"
SECRETS_DIR = "../agnosticd-v2-secrets"
VENV_DIR = "../agnosticd-v2-virtualenv"
OUTPUT_DIR_ROOT = "../agnosticd-v2-output"


def command_exists(command):
    """Check if a command exists on the system."""
    return (
        subprocess.call(
            ["which", command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        == 0
    )


def print_usage():
    """Prints usage instructions."""
    print(
        """
Usage:
  python aad_v2.py action [--guid GUID --config CONFIG --account ACCOUNT]
  python aad_v2.py action [-g GUID -c CONFIG -a ACCOUNT]

Examples:
  python aad_v2.py setup
  python aad_v2.py provision --guid wkaws --config openshift-cluster --account sandbox1275
  python aad_v2.py destroy --guid wkaws --config openshift-cluster --account sandbox1275
    """
    )


def setup_environment():
    """Set up the environment for AgnosticD V2."""
    print("AgnosticD V2 Setup")

    if not command_exists("podman"):
        sys.exit("ERROR: Podman must be installed.")

    # Ensure directories exist
    for directory in [OUTPUT_DIR_ROOT, SECRETS_DIR, VARS_DIR]:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")

    if command_exists("python3.11"):
        if not os.path.exists(VENV_DIR):
            print("Creating virtual environment...")
            subprocess.run(["python3.11", "-m", "venv", VENV_DIR])
        print("Activating virtual environment...")
        subprocess.run(["source", f"{VENV_DIR}/bin/activate"], shell=True)
        subprocess.run(["pip", "install", "--upgrade", "pip", "ansible-navigator"])
    else:
        sys.exit("ERROR: Python 3.11 must be installed.")


def run_ansible_navigator(action, guid, config, account):
    """Runs Ansible Navigator with the given parameters."""
    output_dir = os.path.join(OUTPUT_DIR_ROOT, guid)
    os.makedirs(output_dir, exist_ok=True)

    env_vars = {
        "ANSIBLE_LOG_PATH": f"{output_dir}/{guid}.log",
        "ANSIBLE_NAVIGATOR_PLAYBOOK_ARTIFACT_SAVE_AS": output_dir,
    }

    cmd = [
        "ansible-navigator",
        "run",
        f"ansible/{'main.yml' if action == 'provision' else 'destroy.yml'}",
        "--extra-vars",
        f"ACTION={action}",
        "--extra-vars",
        f"guid={guid}",
        "--extra-vars",
        f"uuid={guid}",
        "--extra-vars",
        f"@{VARS_DIR}/{config}.yml",
        "--extra-vars",
        f"@{SECRETS_DIR}/secrets-{account}.yml",
        "--extra-vars",
        f"@{SECRETS_DIR}/secrets.yml",
        "--extra-vars",
        f"output_dir={output_dir}",
        "--mode",
        "stdout",
    ]

    subprocess.run(cmd, env={**os.environ, **env_vars})


def main():
    parser = argparse.ArgumentParser(description="AgnosticD V2 Script")
    parser.add_argument(
        "action", choices=["setup", "provision", "destroy"], help="Action to perform"
    )
    parser.add_argument("-g", "--guid", help="GUID")
    parser.add_argument("-c", "--config", help="Configuration name")
    parser.add_argument("-a", "--account", help="Account name")

    args = parser.parse_args()

    if args.action == "setup":
        setup_environment()
    elif args.action in ["provision", "destroy"]:
        if not args.guid or not args.config or not args.account:
            print("ERROR: Missing required parameters.")
            print_usage()
            sys.exit(1)
        run_ansible_navigator(args.action, args.guid, args.config, args.account)
    else:
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
