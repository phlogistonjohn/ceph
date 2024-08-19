import argparse
import logging
import os
import pathlib
import shutil
import shlex
import subprocess

log = logging.getLogger()


DISTROS = [
    "ubuntu22.04",
    "centos9",
    "centos8",
]


def _cmdstr(cmd):
    return " ".join(shlex.quote(c) for c in cmd)


def _run(cmd, *args, **kwargs):
    log.info("Executing command: %s", _cmdstr(cmd))
    return subprocess.run(cmd, *args, **kwargs)


def _container_cmd(ctx, args):
    rm_container = not ctx.cli.keep_container
    cmd = [
        ctx.container_engine,
        "run",
        "--name=ceph_build",
    ]
    if rm_container:
        cmd.append("--rm")
    if "podman" in ctx.container_engine:
        cmd.append("--pids-limit=-1")
    if ctx.map_user:
        cmd.append("--user=0")
    cwd = pathlib.Path(".").absolute()
    cmd += [
        f"--volume={cwd}:{ctx.cli.homedir}:Z",
        f"-eHOMEDIR={ctx.cli.homedir}",
    ]
    if ctx.cli.build_dir:
        cmd.append(f"-eBUILD_DIR={ctx.cli.build_dir}")
    for extra_arg in ctx.cli.extra or []:
        cmd.append(extra_arg)
    cmd.append(ctx.image_name)
    cmd.extend(args)
    return cmd


def _git_command(ctx, args):
    cmd = ['git']
    cmd.extend(args)
    return cmd


def _git_current_branch(ctx):
    cmd = _git_command(ctx, ['rev-parse',  '--abbrev-ref', 'HEAD'])
    res = _run(cmd, check=True, capture_output=True)
    return res.stdout.decode('utf8').strip()


class Steps:
    DNF_CACHE = "dnfcache"
    CONTAINER = "container"
    CONFIGURE = "configure"
    BUILD = "build"
    BUILD_TESTS = "buildtests"
    TESTS = "tests"
    FREE_FORM = "free_form"


class Context:
    def __init__(self, cli):
        self.cli = cli
        self._engine = None
        self.distro_cache_name = ""

    @property
    def container_engine(self):
        if self._engine is not None:
            return self._engine
        if self.cli.container_engine:
            return cli.container_engine

        for ctr_eng in ["podman", "docker"]:
            if shutil.which(ctr_eng):
                break
        else:
            raise RuntimeError("no container engine found")
        log.debug("found container engine: %r", ctr_eng)
        self._engine = ctr_eng
        return self._engine

    @property
    def image_name(self):
        return "ceph-build:" + self.target_tag()

    def target_tag(self):
        if self.cli.tag:
            return self.cli.tag
        try:
            branch = _git_current_branch(self).replace('/', '-')
        except subprocess.CalledProcessError:
            branch = 'UNKNOWN'
        return f"{branch}.{self.cli.distro}"

    @property
    def from_image(self):
        return {
            "centos9": "quay.io/centos/centos:stream9",
            "centos8": "quay.io/centos/centos:stream8",
            "ubuntu22.04": "docker.io/ubuntu:22.04",
        }[self.cli.distro]

    @property
    def dnf_cache_dir(self):
        if self.cli.dnf_cache_path and self.distro_cache_name:
            return (
                pathlib.Path(self.cli.dnf_cache_path) / self.distro_cache_name
            )
        return None

    @property
    def map_user(self):
        # TODO: detect if uid mapping is needed
        return os.getuid() != 0


class Builder:
    _steps = {}

    def __init__(self):
        self._did_steps = set()

    def wants(self, step, ctx, *, force=False, top=False):
        log.info("want to execute build step: %s", step)
        if ctx.cli.no_prereqs and not top:
            log.info("Running prerequisite steps disabled")
            return
        if step in self._did_steps:
            log.info("step already done: %s", step)
            return
        self._steps[step](ctx)
        self._did_steps.add(step)
        log.info("step done: %s", step)

    def available_steps(self):
        return [str(k) for k in self._steps]

    @classmethod
    def set(self, step):
        def wrap(f):
            self._steps[step] = f
            f._for_step = step
            return f

        return wrap


@Builder.set(Steps.DNF_CACHE)
def dnf_cache_dir(ctx):
    if ctx.cli.distro not in ["centos9"]:
        return
    if not ctx.cli.dnf_cache_path:
        return

    ctx.distro_cache_name = f"_ceph_{ctx.cli.distro}"
    cache_dir = ctx.dnf_cache_dir
    (cache_dir / "lib").mkdir(parents=True, exist_ok=True)
    (cache_dir / "cache").mkdir(parents=True, exist_ok=True)
    (cache_dir / ".DNF_CACHE").touch(exist_ok=True)


@Builder.set(Steps.CONTAINER)
def build_container(ctx):
    ctx.build.wants(Steps.DNF_CACHE, ctx)
    cmd = [
        ctx.container_engine,
        "build",
        "-t",
        ctx.image_name,
        f"--build-arg=JENKINS_HOME={ctx.cli.homedir}",
    ]
    if ctx.cli.distro:
        cmd.append(f"--build-arg=DISTRO={ctx.from_image}")
    if ctx.dnf_cache_dir:
        cmd += [
            f"--volume={ctx.dnf_cache_dir}/lib:/var/lib/dnf:Z",
            f"--volume={ctx.dnf_cache_dir}:/var/cache/dnf:Z",
            "--build-arg=CLEAN_DNF=no",
        ]
    cmd += ["-f", "Dockerfile.build", "."]
    _run(cmd, check=True)


@Builder.set(Steps.CONFIGURE)
def bc_configure(ctx):
    ctx.build.wants(Steps.CONTAINER, ctx)
    cmd = _container_cmd(
        ctx,
        [
            "bash",
            "-c",
            f"cd {ctx.cli.homedir} && source ./src/script/run-make.sh && has_build_dir || configure",
        ],
    )
    _run(cmd, check=True)


@Builder.set(Steps.BUILD)
def bc_build(ctx):
    ctx.build.wants(Steps.CONFIGURE, ctx)
    cmd = _container_cmd(
        ctx,
        [
            "bash",
            "-c",
            f"cd {ctx.cli.homedir} && source ./src/script/run-make.sh && enable_compiler_env && build vstart",
        ],
    )
    _run(cmd, check=True)


@Builder.set(Steps.BUILD_TESTS)
def bc_build_tests(ctx):
    ctx.build.wants(Steps.CONFIGURE, ctx)
    cmd = _container_cmd(
        ctx,
        [
            "bash",
            "-c",
            f"cd {ctx.cli.homedir} && source ./src/script/run-make.sh && enable_compiler_env && build tests",
        ],
    )
    _run(cmd, check=True)


@Builder.set(Steps.TESTS)
def bc_run_tests(ctx):
    ctx.build.wants(Steps.BUILD_TESTS, ctx)
    cmd = _container_cmd(
        ctx,
        [
            "bash",
            "-c",
            f"cd {ctx.cli.homedir} && source ./run-make-check.sh && enable_compiler_env && build && run",
        ],
    )
    _run(cmd, check=True)


def parse_cli(build_step_names):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug", action="store_true", help="Emit debugging level logging"
    )
    parser.add_argument(
        "--container-engine",
        help="Select container engine to use (eg. podman, docker)",
    )
    parser.add_argument(
        "--cwd", help="Change working directory before executing commands"
    )
    parser.add_argument(
        "--distro",
        "-d",
        choices=DISTROS,
        default="centos9",
        help="Specify a distro short name",
    )
    parser.add_argument("--tag", "-t", help="Specify a container tag")
    parser.add_argument("--name", help="Specify a container name")
    parser.add_argument(
        "--homedir", default="/build", help="Container image home/build dir"
    )
    parser.add_argument(
        "--dnf-cache-path", help="DNF caching using provided base dir"
    )
    parser.add_argument("--build-dir", "-b", help="Specify a build directory")
    parser.add_argument(
        "--extra",
        "-x",
        action="append",
        help="Specify an extra argument to pass to container command",
    )
    parser.add_argument(
        "--keep-container",
        action="store_true",
        help="Skip removing container after executing command",
    )
    parser.add_argument(
        "--no-prereqs",
        "-P",
        action="store_true",
        help="Do not execute any prerequisite steps. Only execute specified steps",
    )
    parser.add_argument(
        "--execute",
        "-e",
        dest="steps",
        action='append',
        choices=build_step_names,
        help="Execute the target build step(s)",
    )
    cli, rest = parser.parse_known_args()
    cli.remaining_args = rest
    return cli


def _src_root():
    return pathlib.Path(__file__).parent.parent.parent.absolute()


def _setup_logging(cli):
    level = logging.DEBUG if cli.debug else logging.INFO
    logger = logging.getLogger()
    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("{asctime}: {levelname}: {message}", style="{")
    )
    handler.setLevel(level)
    logger.addHandler(handler)


def main():
    builder = Builder()
    cli = parse_cli(builder.available_steps())
    _setup_logging(cli)

    os.chdir(cli.cwd or _src_root())
    ctx = Context(cli)
    ctx.build = builder
    for step in cli.steps or [Steps.BUILD]:
        ctx.build.wants(step, ctx, top=True)


if __name__ == "__main__":
    main()
