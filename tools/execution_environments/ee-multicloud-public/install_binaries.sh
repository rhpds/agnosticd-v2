#!/bin/sh
set -ue

cd /tmp

# initArch discovers the architecture for this system.
ARCH=$(uname -m)
case $ARCH in
    armv5*) ARCH="armv5";;
    armv6*) ARCH="armv6";;
    armv7*) ARCH="arm";;
    aarch64) ARCH="arm64";;
    x86) ARCH="386";;
    x86_64) ARCH="amd64";;
    i686) ARCH="386";;
    i386) ARCH="386";;
esac

echo "Detected architecture: ${ARCH}"

# OC
# Install rhel8 version of oc
# https://access.redhat.com/solutions/7077895
version=stable
tarball=openshift-client-linux-${ARCH}-rhel8.tar.gz
url="https://mirror.openshift.com/pub/openshift-v4/${ARCH}/clients/ocp/${version}/${tarball}"
curl -s -L "${url}" -o ${tarball}
tar xzf ${tarball}
install -t /usr/bin oc kubectl
rm ${tarball}

# Bitwarden
# DISCLAIMER: BW doesn't support ARM64 yet, so this is just a placeholder
url="https://vault.bitwarden.com/download/?app=cli&platform=linux"
curl -s -L "${url}" -o bw.zip
unzip bw.zip
install -t /usr/bin bw
rm bw bw.zip

# AWS CLI
curl -s -L "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o awscliv2.zip

unzip -q awscliv2.zip
./aws/install

rm awscliv2.zip
rm -rf aws

# helm (extract with Python to avoid system tar "Cannot open: Invalid argument" on overlay fs in buildah)
HELM_TAG=$(curl -sL https://get.helm.sh/helm3-latest-version | grep -E '^v[0-9]' || true)
HELM_TAG=${HELM_TAG:-v3.20.0}
HELM_DIST="helm-${HELM_TAG}-linux-${ARCH}.tar.gz"
curl -sSL "https://get.helm.sh/${HELM_DIST}" -o "/tmp/${HELM_DIST}"
python3 -c "
import tarfile
with tarfile.open('/tmp/${HELM_DIST}', 'r:gz') as tf:
    tf.extractall('/tmp')
"
install -t /usr/bin "/tmp/linux-${ARCH}/helm"
rm -rf "/tmp/linux-${ARCH}" "/tmp/${HELM_DIST}"

# IBM Cloud CLI (extract with Python to avoid system tar "Cannot open: Invalid argument" on overlay fs in buildah)
IBM_CLI_VERSION=$(curl -sL https://api.github.com/repos/IBM-Cloud/ibm-cloud-cli-release/releases/latest 2>/dev/null | jq -r '.tag_name // empty' | sed 's/^v//')
IBM_CLI_VERSION=${IBM_CLI_VERSION:-2.41.1}
# IBM uses amd64, arm64, 386, ppc64le, s390x - our ARCH already matches for main platforms
IBM_ARCH="${ARCH}"
case "${ARCH}" in
    armv5|armv6|arm) IBM_ARCH="arm64";;  # no 32-bit arm, use arm64 as best effort
esac
IBM_TGZ="IBM_Cloud_CLI_${IBM_CLI_VERSION}_${IBM_ARCH}.tar.gz"
curl -fsSL "https://download.clis.cloud.ibm.com/ibm-cloud-cli-dn/${IBM_CLI_VERSION}/${IBM_TGZ}" -o "/tmp/${IBM_TGZ}"
python3 -c "
import tarfile
with tarfile.open('/tmp/${IBM_TGZ}', 'r:gz') as tf:
    tf.extractall('/tmp')
"
IBM_DIR=$(find /tmp -maxdepth 1 -type d -name 'IBM_Cloud_CLI*' 2>/dev/null | head -1)
if [ -n "${IBM_DIR}" ] && [ -f "${IBM_DIR}/bin/ibmcloud" ]; then
    rm -rf /opt/ibmcloud
    mv "${IBM_DIR}" /opt/ibmcloud
    ln -sf /opt/ibmcloud/bin/ibmcloud /usr/bin/ibmcloud
fi
rm -f "/tmp/${IBM_TGZ}"

# Install all plugins, best effort
export IBMCLOUD_HOME=/opt/ibmcloud
ibmcloud plugin install --all || true
ibmcloud config --check-version=false
