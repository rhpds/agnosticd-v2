SANDBOX=142
GUID=wk418
VARS=openshift-cluster-418

OUTPUT_DIR_ROOT=../agnosticd-v2-output
OUTPUT_DIR=$(GUID)
PLAYBOOK_DIR=ansible
SECRETS_DIR=../agnosticd-v2-secrets
# AWS Sandbox credentials
SECRETS=secrets-sandbox$(SANDBOX)
SECRETS_FILE=$(SECRETS_DIR)/$(SECRETS).yml

VARS_DIR=../agnosticd-v2-vars
VARS_FILE=$(VARS_DIR)/$(VARS).yml

TARGET ?= bastion
ROLE ?= test-empty-role

EXTRA_ARGS=
USER_EXTRA_ARGS=
# Adjust to taste

.SILENT: setup my-env ssh-target

help: ## Show this help - technically unnecessary as `make` alone will do
	@egrep -h '\s##\s' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", ($$2=="" ? "" : $$1 ),  $$2}' 

# Thanks to victoria.dev for the above syntax
# https://victoria.dev/blog/how-to-create-a-self-documenting-makefile/

env: ## Confirm env setup
	@echo "\n\nActivate a virtualenv if required\n"
	@type python3
	@printf "Python3 version is: "
	@python3 --version
	@type ansible
	@ansible --version
	@printf "ENV VARS containing ANSIBLE: "
	@-env | grep ANSIBLE || echo "None"

ansible-navigator-execute: ## Execute ansible-playbook with PLAYBOOK of choice
	mkdir -p $(OUTPUT_DIR_ROOT)/$(OUTPUT_DIR); \
	export ANSIBLE_LOG_PATH=/output_dir_root/$(OUTPUT_DIR)/$(GUID).log; \
	ansible-navigator run ansible/main.yml \
		--extra-vars ACTION=provision \
		--extra-vars @/vars/$(VARS).yml \
		--extra-vars @/secrets/$(SECRETS).yml \
		--extra-vars @/secrets/secrets.yml \
		--extra-vars guid=$(GUID) \
		--extra-vars output_dir=/output_dir_root/$(OUTPUT_DIR) \
		--mode stdout \
		$(USER_EXTRA_ARGS) $(EXTRA_ARGS)

	# export ANSIBLE_DEBUG=1; \
		# --extra-vars host_ocp4_installer_install_openshift=false \

ansible-navigator-destroy: ## Execute ansible-playbook with PLAYBOOK of choice
	mkdir -p $(OUTPUT_DIR_ROOT)/$(OUTPUT_DIR); \
	export ANSIBLE_LOG_PATH=$(OUTPUT_DIR_ROOT)/$(OUTPUT_DIR)/$(GUID).log; \
	ansible-navigator run ansible/destroy.yml \
		--extra-vars ACTION=destroy \
		--extra-vars @/vars/$(VARS).yml \
		--extra-vars @/secrets/$(SECRETS).yml \
		--extra-vars @/secrets/secrets.yml \
		--extra-vars guid=$(GUID) \
		--extra-vars output_dir=/output_dir_root/$(OUTPUT_DIR) \
		--mode stdout \
		$(USER_EXTRA_ARGS) $(EXTRA_ARGS)
