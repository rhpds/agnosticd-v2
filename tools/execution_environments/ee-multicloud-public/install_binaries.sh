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

# helm (manual install to avoid get-helm-3 script's tar -C extraction failing on overlay fs in buildah)
HELM_TAG=$(curl -sL https://get.helm.sh/helm3-latest-version | grep -E '^v[0-9]' || true)
HELM_TAG=${HELM_TAG:-v3.20.0}
HELM_DIST="helm-${HELM_TAG}-linux-${ARCH}.tar.gz"
curl -sSL "https://get.helm.sh/${HELM_DIST}" -o "/tmp/${HELM_DIST}"
# Extract in /tmp without -C to avoid "tar: Cannot open: Invalid argument" in container overlay builds
cd /tmp && tar xzf "${HELM_DIST}"
install -t /usr/bin "/tmp/linux-${ARCH}/helm"
rm -rf "/tmp/linux-${ARCH}" "/tmp/${HELM_DIST}"

# IBM Cloud binary
curl -fsSL https://clis.cloud.ibm.com/install/linux | sh

# Install all plugins, best effort
export IBMCLOUD_HOME=/opt/ibmcloud
mkdir -p /opt/ibmcloud
ibmcloud plugin install --all || true
ibmcloud config --check-version=false
