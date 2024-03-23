"""tincam is the tiny cephfs auto mounter
"""
from typing import Optional, List, Any

import argparse
import time
import json
import pathlib
import subprocess
import errno
import logging


logger = logging.getLogger()


ROOT_DIR = '/srv'


class Request:
    def __init__(
        self, what: str, where: str, options: Optional[List[str]]
    ) -> None:
        self._what = what
        self._where = pathlib.Path(where)
        self._options = [v for v in (options or []) if v]

    @property
    def options(self) -> str:
        opts = set(self._options)
        opts.add('noexec')
        opts.add('_netdev')
        return ','.join(sorted(opts))

    @property
    def what(self) -> str:
        return self._what

    @property
    def where(self) -> pathlib.Path:
        return self._where

    def in_root(self, root: pathlib.Path) -> bool:
        try:
            self._where.relative_to(root)
            return True
        except ValueError:
            return False

    def __str__(self) -> str:
        return f'MountRequest({self.what} -> {self.where}, options={self.options})'


def mount_volume(path: pathlib.Path, request: Request) -> None:
    cmd = [
        'mount',
        '-t',
        'ceph',
        '-o',
        request.options,
        request.what,
        str(path),
    ]
    logger.warning('%r', cmd)
    subprocess.run(cmd, check=True)


def unmount_volume(path: pathlib.Path) -> None:
    cmd = ['umount', str(path)]
    logger.warning('%r', cmd)
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


def update_mounts(requests: List[Request], root: pathlib.Path) -> None:
    logger.warning('Updating mounts')
    root_stat = root.stat()
    mounted = set()
    for req in requests:
        logger.warning('Updating request: %s', req)
        if not req.in_root(root):
            raise ValueError(f'bad request: {req} not in {root}')
        mnt_path = pathlib.Path(req.where)
        mnt_path.mkdir(exist_ok=True)
        path_stat = mnt_path.stat()
        if root_stat.st_dev != path_stat.st_dev:
            mounted.add(mnt_path)
            continue
        logger.warning('Going to mount on: %s', mnt_path)
        mount_volume(mnt_path, req)
        mounted.add(mnt_path)

    for path in root.iterdir():
        logger.warning('Checking: %s', path)
        if path in mounted:
            continue  # this is expected mount
        path_stat = path.stat()
        if root_stat.st_dev != path_stat.st_dev:
            unmount_volume(path)
        logger.warning('Removing: %s', path)
        _remove_dir(path)


def unmount_volumes(root: pathlib.Path) -> None:
    update_mounts([], root)


def get_requests(cli: Any) -> List[Request]:
    requests: List[Request] = []
    source = getattr(cli, 'source', None)
    if source:
        requests += read_source(source)
    what = getattr(cli, 'what', None)
    where = getattr(cli, 'where', None)
    options = (getattr(cli, 'options', '') or '').split(',')
    if what and where:
        requests.append(Request(what, where, options))
    return requests


def read_source(source_path: pathlib.Path) -> List[Request]:
    with open(source_path, 'r') as fh:
        data = json.load(fh)
    requests = []
    for request in data:
        if 'type' in request and request['type'] != 'ceph':
            raise ValueError(
                f'unexpected file system type: {request["type"]}'
            )
        requests.append(
            Request(
                what=request['what'],
                where=request['where'],
                options=request.get('options'),
            )
        )
    return requests


def cli_arguments(parser: Any) -> None:
    parser.add_argument('--cleanup', action='store_true')
    parser.add_argument('--interval', default=0, type=int)
    parser.add_argument('--root', default=ROOT_DIR)
    parser.add_argument('--source', nargs='?')
    parser.add_argument('--options', '-o')
    parser.add_argument('what', nargs='?')
    parser.add_argument('where', nargs='?')


def main() -> None:
    parser = argparse.ArgumentParser()
    cli_arguments(parser)
    cli = parser.parse_args()

    if cli.what and not cli.where:
        raise ValueError(
            'directly mounting a file system requires a mount location'
        )

    logger.warning('cli: %s', cli)

    cleanup_volumes = cli.cleanup
    root = pathlib.Path(cli.root)
    try:
        while True:
            reqs = get_requests(cli)
            update_mounts(reqs, root=root)
            if not cli.interval:
                break
            time.sleep(cli.interval)
    except Exception:
        logger.warning('!!!!')
        unmount_volumes(root=root)
        raise
    except KeyboardInterrupt:
        cleanup_volumes = True

    if cleanup_volumes:
        unmount_volumes(root=root)


if __name__ == '__main__':
    main()
