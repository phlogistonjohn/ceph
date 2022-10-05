#!/bin/bash

# This script expects to be run during the construction of a container The
# resulting container has all the dependencies and tools installed needed to
# build ceph. It DOES NOT and is not expected to build ceph during the
# container build.

# The script assumes the following environment variables are present during
# the container build:
# CEPH_BRANCH
# DISTRO
# CLEAN_DNF (for dnf based distros, ignored on others)

set -e
export LOCALE=C
cd /src/ceph

case "${CEPH_BRANCH}~${DISTRO}" in
    *~*centos*stream8)
        dnf install -y java-1.8.0-openjdk-headless
        source ./src/script/run-make.sh
        prepare
        if [ "${CLEAN_DNF}" != no ]; then
            dnf clean all
            rm -rf /var/cache/dnf/*
        fi
    ;;
    *)
        echo "Unknown branch or build: ${CEPH_BRANCH}~${DISTRO}" >&2
        exit 2
    ;;
esac



