from typing import Optional, Iterable, List, Any, Union

import enum
import errno
import json
import logging
import os
import pathlib
import subprocess
import time

PathLike = Union[os.PathLike, str]


logger = logging.getLogger()


class Request:
    def __init__(
        self,
        fstype: str,
        source: str,
        name: str,
        options: Optional[Iterable[str]] = None,
    ) -> None:
        self.fstype = fstype
        self.source = source
        self.name = name
        self.options = [v for v in (options or []) if v]

    @property
    def mount_options(self) -> str:
        opts = set(self.options)
        opts.add('noexec')
        opts.add('_netdev')
        return ','.join(sorted(opts))

    def __repr__(self) -> str:
        return (
            'Request('
            f'{self.fstype!r}, {self.source!r}, {self.name!r}, {self.options!r}'
            ')'
        )


class CephFSRequest(Request):
    def __init__(
        self,
        source: str,
        name: str,
        options: Optional[Iterable[str]] = None,
    ) -> None:
        super().__init__('ceph', source, name, options)

    @classmethod
    def parse(cls, value: str) -> 'CephFSRequest':
        kwargs = {}
        if value.startswith('{') and value.endswith('}'):
            kwargs = json.loads(value)
            return cls(**kwargs)
        parts = value.split(';')
        for part in parts:
            if part.startswith('source='):
                kwargs['source'] = part.split('=', 1)[1]
            if part.startswith('name='):
                kwargs['name'] = part.split('=', 1)[1]
            if part.startswith('options='):
                kwargs['options'] = part.split('=', 1)[1]
        return cls(**kwargs)


class PlaceholderRequest(Request):
    def __init__(
        self,
        name: str,
    ) -> None:
        super().__init__('none', '<unknown>', name, None)


class ManagedMounts:
    def __init__(self, rootdir: PathLike) -> None:
        self._rootdir = pathlib.Path(rootdir)
        self._requests: List[Request] = []

    def add(self, req: Request) -> None:
        if req.name in {r.name for r in self._requests}:
            raise KeyError(f'{req.name} already in use')
        self._requests.append(req)

    def flush(self) -> None:
        self._requests = []

    def scan(self) -> None:
        root_stat = self._rootdir.stat()
        mounted_paths = [
            path
            for path in self._rootdir.iterdir()
            if not _same_fs(self._rootdir, path, parent_stat=root_stat)
        ]
        for path in mounted_paths:
            if path.name not in {r.name for r in self._requests}:
                self.add(PlaceholderRequest(path.name))

    def update(self) -> None:
        logger.info('Updating mounts')
        root_stat = self._rootdir.stat()
        expected = set()
        for req in self._requests:
            mnt_path = self._rootdir / req.name
            mnt_path.mkdir(exist_ok=True)
            if _same_fs(self._rootdir, mnt_path, parent_stat=root_stat):
                # (new) unmounted dir
                _mount(mnt_path, req)
            expected.add(mnt_path)
        for path in self._rootdir.iterdir():
            if path in expected:
                logger.debug('expected path: %r', path)
                continue
            if _same_fs(self._rootdir, path, parent_stat=root_stat):
                continue
            _unmount(path)
            _remove_dir(path)
        logger.info('Done updating mounts')


def _same_fs(
    parent: pathlib.Path,
    path: pathlib.Path,
    parent_stat: Optional[os.stat_result] = None,
    path_stat: Optional[os.stat_result] = None,
) -> bool:
    parent_stat = parent_stat or parent.stat()
    path_stat = path_stat or path.stat()
    return parent_stat.st_dev == path_stat.st_dev


def _mount(path: pathlib.Path, req: Request) -> None:
    cmd = [
        'mount',
        '-t',
        req.fstype,
        '-o',
        req.mount_options,
        req.source,
        str(path),
    ]
    logger.debug('_mount: %r', cmd)
    subprocess.run(cmd, check=True)


def _unmount(path: pathlib.Path) -> None:
    cmd = ['umount', str(path)]
    logger.debug('_unmount: %r', cmd)
    subprocess.run(cmd, check=True)
    time.sleep(0.2)


def _remove_dir(path: pathlib.Path, max_tries: int = 30) -> None:
    for _ in range(max_tries):
        try:
            path.rmdir()
            return
        except OSError as err:
            if getattr(err, 'errno', 0) != errno.EBUSY:
                raise
            last_err = err
            time.sleep(0.2)
    raise last_err


class Modes(str, enum.Enum):
    MOUNT = 'mount'
    CLEANUP = 'cleanup'
    MONITOR = 'monitor'

    def __str__(self) -> str:
        return self.value


def cli_arguments(parser: Any) -> None:
    parser.add_argument('--location')
    parser.add_argument('--cephfs', action='append', type=CephFSRequest.parse)
    parser.add_argument(
        '-m',
        '--mode',
        choices=[str(v) for v in (Modes.MOUNT, Modes.CLEANUP, Modes.MONITOR)],
        default=Modes.MOUNT,
    )
    parser.add_argument('--monitor-delay', type=int, default=60)


def manage_mounts(
    location: str, mode: str, requests: List[Request], delay_sec: int = 60
) -> None:
    _mode = Modes(mode)
    mm = ManagedMounts(location)
    if _mode is Modes.CLEANUP:
        mm.update()
        return
    if _mode is Modes.MOUNT:
        for req in requests:
            mm.add(req)
        mm.scan()
        mm.update()
        return
    if _mode is Modes.MONITOR:
        for req in requests:
            mm.add(req)
        try:
            while True:
                mm.update()
                time.sleep(delay_sec)
        except KeyboardInterrupt:
            pass
        finally:
            mm.flush()
            mm.update()
