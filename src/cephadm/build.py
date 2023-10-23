#!/usr/bin/python3
"""Build cephadm from one or more files into a standalone executable.
"""
# TODO: If cephadm is being built and packaged within a format such as RPM
# do we have to do anything special wrt passing in the version
# of python to build with? Even with the intermediate cmake layer?

import argparse
import compileall
import json
import logging
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HAS_ZIPAPP = False
try:
    import zipapp

    HAS_ZIPAPP = True
except ImportError:
    pass


log = logging.getLogger(__name__)


_ZIPAPP_REQS = "zipapp-reqs.txt"
_VALID_VERS_VARS = [
    "CEPH_GIT_VER",
    "CEPH_GIT_NICE_VER",
    "CEPH_RELEASE",
    "CEPH_RELEASE_NAME",
    "CEPH_RELEASE_TYPE",
]


_DEP_SRC_PIP = "pip"
_DEP_SRC_RPM = "rpm"


class DependencyOpts:
    enabled = False
    requirements = _ZIPAPP_REQS
    mode = _DEP_SRC_PIP

    def __init__(self, bundled_dependencies):
        if bundled_dependencies in ("", "none"):
            return
        assert bundled_dependencies in (_DEP_SRC_PIP, _DEP_SRC_RPM)
        self.mode = bundled_dependencies
        self.enabled = True
        log.debug(f'Dependencies: {self.enabled}')
        log.debug(f'Dependencies Source: {self.mode}')

    def __bool__(self):
        return self.enabled and os.path.isfile(self.requirements)


class DependencyInfo:
    def __init__(self):
        self._deps = []
        self._reqs = {}

    def read_reqs(self, path):
        with open(path) as fh:
            self.load_reqs(fh.readlines())

    def load_reqs(self, lines):
        for line in lines:
            if line.startswith('#'):
                continue
            pname = line.split(None)[0]
            self._reqs[pname] = line.strip()

    @property
    def requested_packages(self):
        return self._reqs.keys()

    def add(self, name, **fields):
        vals = {'name': name}
        vals.update({k: v for k, v in fields.items() if v is not None})
        if name in self._reqs:
            vals['requirements_entry'] = self._reqs[name]
        self._deps.append(vals)

    def save(self, path):
        with open(path, 'w') as fh:
            json.dump(self._deps, fh)


def _reexec(python):
    """Switch to the selected version of python by exec'ing into the desired
    python path.
    Sets the _BUILD_PYTHON_SET env variable as a sentinel to indicate exec has
    been performed.
    """
    env = os.environ.copy()
    env["_BUILD_PYTHON_SET"] = python
    os.execvpe(python, [python, __file__] + sys.argv[1:], env)


def _did_rexec():
    """Returns true if the process has already exec'ed into the desired python
    version.
    """
    return bool(os.environ.get("_BUILD_PYTHON_SET", ""))


def _build(dest, src, versioning_vars=None, deps=None):
    """Build the binary."""
    os.chdir(src)
    tempdir = pathlib.Path(tempfile.mkdtemp(suffix=".cephadm.build"))
    log.debug("working in %s", tempdir)
    dinfo = None
    try:
        if deps:
            dinfo = _install_deps(deps, tempdir)
        log.info("Copying contents")
        # cephadmlib is cephadm's private library of modules
        shutil.copytree(
            "cephadmlib", tempdir / "cephadmlib", ignore=_ignore_cephadmlib
        )
        # cephadm.py is cephadm's main script for the "binary"
        # this must be renamed to __main__.py for the zipapp
        shutil.copy("cephadm.py", tempdir / "__main__.py")
        mdir = tempdir / "_cephadmmeta"
        mdir.mkdir(parents=True, exist_ok=True)
        (mdir / "__init__.py").touch(exist_ok=True)
        if versioning_vars:
            generate_version_file(versioning_vars, mdir / "version.py")
        if dinfo:
            dinfo.save(mdir / "deps.json")
        _compile(dest, tempdir)
    finally:
        shutil.rmtree(tempdir)


def _ignore_cephadmlib(source_dir, names):
    # shutil.copytree callback: return the list of names *to ignore*
    return [
        name
        for name in names
        if name.endswith(
            ("~", ".old", ".swp", ".pyc", ".pyo", ".so", "__pycache__")
        )
    ]


def _compile(dest, tempdir):
    """Compile the zipapp."""
    log.info("Byte-compiling py to pyc")
    compileall.compile_dir(
        tempdir,
        maxlevels=16,
        legacy=True,
        quiet=1,
        workers=0,
    )
    # TODO we could explicitly pass a python version here
    log.info("Constructing the zipapp file")
    try:
        zipapp.create_archive(
            source=tempdir,
            target=dest,
            interpreter=sys.executable,
            compressed=True,
        )
        log.info("Zipapp created with compression")
    except TypeError:
        # automatically fall back to uncompressed
        zipapp.create_archive(
            source=tempdir,
            target=dest,
            interpreter=sys.executable,
        )
        log.info("Zipapp created without compression")


def _install_deps(deps, tempdir):
    if deps.mode == _DEP_SRC_PIP:
        return _install_pip_deps(tempdir)
    if deps.mode == _DEP_SRC_RPM:
        return _install_rpm_deps(deps, tempdir)
    raise ValueError(f'unexpected deps mode: {deps.mode}')


def _install_rpm_deps(deps, tempdir):
    log.info("Installing dependencies using RPMs")
    dinfo = DependencyInfo()
    dinfo.read_reqs(deps.requirements)
    log.warning("Ignoring versions specified in the requirements file")
    for pkg in dinfo.requested_packages:
        log.info(f"Looking for rpm package for: {pkg!r}")
        _deps_from_rpm(deps, pkg, tempdir, dinfo)
    return dinfo


def _deps_from_rpm(deps, pkg, tempdir, dinfo):
    dist = f'python3dist({pkg})'.lower()
    try:
        res = subprocess.run(
            ['rpm', '-q', '--whatprovides', dist],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as err:
        log.error(f"Command failed: {err.args[1]!r}")
        log.error(f"An installed RPM package for {pkg} was not found")
        sys.exit(1)
    rpmname = res.stdout.strip().decode('utf8')
    res = subprocess.run(
        ['rpm', '-q', '--qf', '%{version} %{release} %{epoch}\\n', rpmname],
        check=True,
        capture_output=True,
    )
    vers = res.stdout.decode('utf8').splitlines()[0].split()
    log.info(f"RPM Package: {rpmname} ({vers})")
    dinfo.add(
        pkg,
        rpm_name=rpmname,
        version=vers[0],
        rpm_release=vers[1],
        rpm_epoch=vers[2],
        package_source='rpm',
    )
    res = subprocess.run(
        ['rpm', '-ql', rpmname], check=True, capture_output=True
    )
    paths = [l.decode('utf8') for l in res.stdout.splitlines()]
    top_level = None
    for path in paths:
        if path.endswith('top_level.txt'):
            top_level = pathlib.Path(path)
    if not top_level:
        raise ValueError('top_level not found')
    meta_dir = top_level.parent
    pkg_dirs = [
        top_level.parent.parent / p
        for p in top_level.read_text().splitlines()
    ]
    meta_dest = tempdir / meta_dir.name
    log.info(f"Copying {meta_dir} to {meta_dest}")
    shutil.copytree(meta_dir, meta_dest, ignore=_ignore_cephadmlib)
    for pkg_dir in pkg_dirs:
        pkg_dest = tempdir / pkg_dir.name
        log.info(f"Copying {pkg_dir} to {pkg_dest}")
        shutil.copytree(pkg_dir, pkg_dest, ignore=_ignore_cephadmlib)


def _install_pip_deps(tempdir):
    """Install dependencies with pip."""
    # TODO we could explicitly pass a python version here
    log.info("Installing dependencies using pip")
    # best effort to disable compilers, packages in the zipapp
    # must be pure python.
    env = os.environ.copy()
    env['CC'] = '/bin/false'
    env['CXX'] = '/bin/false'
    # apparently pip doesn't have an API, just a cli.
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-binary",
            ":all:",
            "--requirement",
            _ZIPAPP_REQS,
            "--target",
            tempdir,
        ],
        env=env,
    )
    # record info about what deps we are bundling in
    dinfo = DependencyInfo()
    dinfo.read_reqs(_ZIPAPP_REQS)
    res = subprocess.run(
        ['pip', 'list', '--format=json', '--path', tempdir],
        check=True,
        capture_output=True,
    )
    pkgs = json.loads(res.stdout)
    for pkg in pkgs:
        dinfo.add(
            pkg['name'],
            version=pkg['version'],
            package_source='pip',
        )
    return dinfo


def generate_version_file(versioning_vars, dest):
    log.info("Generating version file")
    log.debug("versioning_vars=%r", versioning_vars)
    with open(dest, "w") as fh:
        print("# GENERATED FILE -- do not edit", file=fh)
        for key, value in versioning_vars:
            print(f"{key} = {value!r}", file=fh)


def version_kv_pair(value):
    if "=" not in value:
        raise argparse.ArgumentTypeError(f"not a key=value pair: {value!r}")
    key, value = value.split("=", 1)
    if key not in _VALID_VERS_VARS:
        raise argparse.ArgumentTypeError(f"Unexpected key: {key!r}")
    return key, value


def main():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("cephadm/build.py: %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)

    log.debug("argv: %r", sys.argv)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "dest", help="Destination path name for new cephadm binary"
    )
    parser.add_argument(
        "--source", help="Directory containing cephadm sources"
    )
    parser.add_argument(
        "--python", help="The path to the desired version of python"
    )
    parser.add_argument(
        "--set-version-var",
        "-S",
        type=version_kv_pair,
        dest="version_vars",
        action="append",
        help="Set a key=value pair in the generated version info file",
    )
    parser.add_argument(
        "--bundled-dependencies",
        "-B",
        choices=(_DEP_SRC_PIP, _DEP_SRC_RPM, "none"),
        default="pip",
        help="Source for bundled dependencies",
    )
    args = parser.parse_args()

    if not _did_rexec() and args.python:
        _reexec(args.python)

    log.info(
        "Python Version: {v.major}.{v.minor}.{v.micro}".format(
            v=sys.version_info
        )
    )
    log.info("Args: %s", vars(args))
    if not HAS_ZIPAPP:
        # Unconditionally display an error that the version of python
        # lacks zipapp (probably too old).
        print("error: zipapp module not found", file=sys.stderr)
        print(
            "(zipapp is available in Python 3.5 or later."
            " are you using a new enough version?)",
            file=sys.stderr,
        )
        sys.exit(2)
    if args.source:
        source = pathlib.Path(args.source).absolute()
    else:
        source = pathlib.Path(__file__).absolute().parent
    dest = pathlib.Path(args.dest).absolute()
    log.info("Source Dir: %s", source)
    log.info("Destination Path: %s", dest)
    _build(
        dest,
        source,
        versioning_vars=args.version_vars,
        deps=DependencyOpts(args.bundled_dependencies),
    )


if __name__ == "__main__":
    main()
