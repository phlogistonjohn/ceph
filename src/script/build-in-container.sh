#!/bin/bash

set -ex

SCRIPT_DIR="$(cd "$(dirname "${0}")" && pwd)"
CEPH_ROOT="$SCRIPT_DIR/../.."

DISTRO=centos8
TAG=
CONTAINER_NAME="ceph-build"
BUILD_CTR=yes
BUILD=yes
HOMEDIR=/build
DNF_CACHE=
EXTRA_ARGS=()
BUILD_ARGS=()

show_help() {
    echo "build-in-container.sh:"
    echo "  --help                Show help"
    echo "  --distro              Specify a distro image or short name (centos8)"
    echo "  --tag                 Specify a container tag"
    echo "  --name                Specify a container name (default ${CONTAINER_NAME})"
    echo "  --dnf-cache           Enable dnf caching in given dir"
    echo "  -e                    Extra build argument"
    echo "  --no-build            Skip ceph build"
    echo "  --no-container-build  Skip building build container"
    echo ""
}

get_engine() {
    if command -v podman >/dev/null 2>&1; then
        echo podman
        return 0
    fi
    if command -v docker >/dev/null 2>&1; then
        echo docker
        return 0
    fi
    echo "ERROR: no container engine found" >&2
    return 2
}

build_container() {
    engine="$(get_engine)"
    cmd=("${engine}" build -t "${CONTAINER_NAME}:${TAG}" --build-arg JENKINS_HOME="$HOMEDIR")
    if [ "$DISTRO" ]; then
        cmd+=(--build-arg DISTRO="${DISTRO}")
    fi
    if [ -d "$HOME/.ccache" ]; then
        cmd+=(-v "$HOME/.ccache:$HOMEDIR/.ccache")
    fi
    if [ "$DNF_CACHE" ]; then
        mkdir -p "$DNF_CACHE/lib" "$DNF_CACHE/cache"
        cmd+=(-v "$DNF_CACHE/lib:/var/lib/dnf"
              -v "$DNF_CACHE/cache:/var/cache/dnf"
              --build-arg CLEAN_DNF=no)
    fi
    cmd+=(-f Dockerfile.build .)

    "${cmd[@]}"
}

build_ceph() {
    engine="$(get_engine)"
    cmd=("${engine}" run --name ceph_build --rm)
    cmd+=("${EXTRA_ARGS[@]}")
    cmd+=(-v "$PWD:$HOMEDIR")
    cmd+=("$CONTAINER_NAME:$TAG")

    "${cmd[@]}" "$@"
}

parse_cli() {
    CLI="$(getopt -o hd:t:e: --long help,distro:,tag:,name:,no-build,no-container-build,dnf-cache: -n "$0" -- "$@")"
    eval set -- "${CLI}"
    while true ; do
        case "$1" in
            -d|--distro)
                DISTRO="$2"
                shift
                shift
            ;;
            -t|--tag)
                TAG="$2"
                shift
                shift
            ;;
            --name)
                CONTAINER_NAME="$2"
                shift
                shift
            ;;
            --dnf-cache)
                DNF_CACHE="$2"
                shift
                shift
            ;;
            -e)
                EXTRA_ARGS+=("$2")
                shift
                shift
            ;;
            --no-build)
                BUILD=no
                shift
            ;;
            --no-container-build)
                BUILD_CTR=no
                shift
            ;;
            -h|--help)
                show_help
                exit 0
            ;;
            --)
                shift
                BUILD_ARGS+=("$@")
                break
            ;;
            *)
                echo "unknown option: $1" >&2
                exit 2
            ;;
        esac
    done
}

build_in_container() {
    parse_cli "$@"

    case "$DISTRO" in
        ubuntu22.04)
            DISTRO_NAME="ubuntu22.044"
            DISTRO="docker.io/ubuntu:22.04"
        ;;
        centos9|centos?stream9)
            DISTRO_NAME="centos9"
            DISTRO="quay.io/centos/centos:stream9"
        ;;
        centos8|centos?stream8)
            DISTRO_NAME="centos8"
            DISTRO="quay.io/centos/centos:stream8"
        ;;
        *)
            DISTRO_NAME="custom"
        ;;
    esac

    if [ -z "${TAG}" ]; then
        GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
        TAG="${GIT_BRANCH}.${DISTRO_NAME}"
    fi

    cd "$CEPH_ROOT"
    if [ "$BUILD_CTR" = yes ]; then
        build_container
    fi
    if [ "$BUILD" = yes ]; then
        build_ceph "${BUILD_ARGS[@]}"
    fi
}

build_in_container "$@"
