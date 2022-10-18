#!/bin/bash
#
# Build ceph in a container, creating the container environment if necessary.
# Use a build recipe (-r) to automatically perform a build step. Otherwise,
# pass CLI args after -- terminator to run whatever command you want in
# the build container.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${0}")" && pwd)"
CEPH_ROOT="$SCRIPT_DIR/../.."

DISTRO=centos8
TAG=
CONTAINER_NAME="ceph-build"
BUILD_CTR=yes
BUILD=yes
BUILD_DIR=build
HOMEDIR=/build
DNF_CACHE=
EXTRA_ARGS=()
BUILD_ARGS=()

show_help() {
    echo "build-in-container.sh:"
    echo "    --help                Show help"
    grep "###:" "${0}" | grep -v sed | sed 's,.*###: ,    ,'
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

# get_recipe extends BUILD_ARGS with commands to execute the named recipe.
# Exits on an invalid recipe.
get_recipe() {
    case "$1" in
        configure)
            BUILD_ARGS+=(bash -c '. /opt/rh/gcc-toolset-11/enable && cd /build && . ./src/script/run-make.sh && configure')
        ;;
        build)
            BUILD_ARGS+=(bash -c '. /opt/rh/gcc-toolset-11/enable && cd /build && . ./src/script/run-make.sh && build vstart')
        ;;
        build-tests)
            BUILD_ARGS+=(bash -c '. /opt/rh/gcc-toolset-11/enable && cd /build && . ./src/script/run-make.sh && build tests')
        ;;
        run-tests)
            BUILD_ARGS+=(bash -c '. /opt/rh/gcc-toolset-11/enable && cd /build && . ./run-make-check.sh && cd $BUILD_DIR && run')
        ;;
        make-srpm)
            BUILD_ARGS+=(bash -c 'cd /build && ./make-srpm.sh')
        ;;
        rpmbuild)
            BUILD_ARGS+=(bash -c 'rpmbuild --rebuild -D"_topdir /build/_rpm" /build/ceph-*.src.rpm')
        ;;
        *)
            echo "invalid recipe: $1" >&2
            exit 2
        ;;
    esac
}

build_ceph() {
    engine="$(get_engine)"
    cmd=("${engine}" run --name ceph_build --rm)
    case "$engine" in
        *podman)
            cmd+=("--pids-limit=-1")
        ;;
    esac
    cmd+=("${EXTRA_ARGS[@]}")
    cmd+=(-v "$PWD:$HOMEDIR")
    cmd+=(-e "HOMEDIR=$HOMEDIR")
    cmd+=(-e "BUILD_DIR=$BUILD_DIR")
    if [ -d "$HOME/.ccache" ]; then
        cmd+=(-v "$HOME/.ccache:$HOMEDIR/.ccache")
        cmd+=(-e "CCACHE_DIR=$HOMEDIR/.ccache")
    fi
    cmd+=("$CONTAINER_NAME:$TAG")

    "${cmd[@]}" "$@"
}

parse_cli() {
    CLI="$(getopt -o hd:t:x:b:r: --long help,distro:,tag:,name:,no-build,no-container-build,dnf-cache:,build-dir:,recipe: -n "$0" -- "$@")"
    eval set -- "${CLI}"
    while true ; do
        case "$1" in
            ###: -d / --distro=<VALUE>
            ###:     Specify a distro image or short name (eg. centos8)
            -d|--distro)
                DISTRO="$2"
                shift
                shift
            ;;
            ###: -t / --tag=<VALUE>
            ###:     Specify a container tag (eg. main)
            -t|--tag)
                TAG="$2"
                shift
                shift
            ;;
            ###: --name=<VALUE>
            ###:     Specify a container name (default: ceph-build)
            --name)
                CONTAINER_NAME="$2"
                shift
                shift
            ;;
            ###: --dnf-cache=<VALUE>
            ###:     Enable dnf caching in given dir (build container)
            --dnf-cache)
                DNF_CACHE="$2"
                shift
                shift
            ;;
            ###: -b / --build-dir=<VALUE>
            ###:     Specify (relative) build directory to use (ceph build)
            -b|--build-dir)
                BUILD_DIR="$2"
                shift
                shift
            ;;
            ###: -x<ARG>
            ###:     Pass extra argument to container run command
            -x)
                EXTRA_ARGS+=("$2")
                shift
                shift
            ;;
            ###: -r / --recipe=<VALUE>
            ###:     Ceph build recipe to use. If not provided, the remaining
            ###:     arguments will be executed directly as a build commmand.
            -r|--recipe)
                build_recipe="$2"
                shift
                shift
            ;;
            ###: --no-build
            ###:     Skip building Ceph
            --no-build)
                BUILD=no
                shift
            ;;
            ###: --no-container-build
            ###:     Skip constructing a build container
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
    set -x

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
        if [ "${build_recipe}" ]; then
            get_recipe "${build_recipe}"
        fi
        build_ceph "${BUILD_ARGS[@]}"
    fi
}

if [ "$0" = "$BASH_SOURCE" ]; then
    build_in_container "$@"
fi
