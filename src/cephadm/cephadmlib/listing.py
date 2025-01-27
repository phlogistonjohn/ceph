# listing.py - listings and status of current daemons

import os
import logging

from typing import TypedDict, Union, Optional, Iterator, List

from .context import CephadmContext
from .daemon_identity import DaemonIdentity
from .data_utils import get_legacy_daemon_fsid, is_fsid


logger = logging.getLogger()


_LEGACY_DAEMON_TYPES = ['mon', 'osd', 'mds', 'mgr', 'rgw']

LEGACY = 'legacy'
VERSION1 = 'cephadm:v1'


class BasicDaemonStatus(TypedDict):
    style: str
    name: str
    fsid: str
    systemd_unit: str


class LegacyDaemonEntry:
    fsid: str
    daemon_type: str
    name: str
    status: BasicDaemonStatus

    def __init__(
        self,
        fsid: str,
        daemon_type: str,
        name: str,
        status: BasicDaemonStatus,
    ) -> None:
        self.fsid = fsid
        self.daemon_type = daemon_type
        self.name = name
        self.status = status


class DaemonEntry:
    identity: DaemonIdentity
    status: BasicDaemonStatus

    def __init__(
        self, identity: DaemonIdentity, status: BasicDaemonStatus
    ) -> None:
        self.identity = identity
        self.status = status


def daemons(
    ctx: CephadmContext,
    legacy_dir: Optional[str] = None,
) -> Iterator[Union[LegacyDaemonEntry, DaemonEntry]]:
    """Iterate over the daemons in the current node."""
    data_dir = ctx.data_dir
    if legacy_dir is not None:
        data_dir = os.path.abspath(legacy_dir + data_dir)

    if not os.path.exists(data_dir):
        # data_dir (/var/lib/ceph typically) is missing. Return empty list.
        logger.warning('%s is missing: no daemon listing available', data_dir)
        return

    for dirname in os.listdir(data_dir):
        if dirname in _LEGACY_DAEMON_TYPES:
            daemon_type = dirname
            for entry in os.listdir(os.path.join(data_dir, dirname)):
                if '-' not in entry:
                    continue  # invalid entry
                (cluster, daemon_id) = entry.split('-', 1)
                fsid = get_legacy_daemon_fsid(
                    ctx,
                    cluster,
                    daemon_type,
                    daemon_id,
                    legacy_dir=legacy_dir,
                )
                legacy_unit_name = 'ceph-%s@%s' % (daemon_type, daemon_id)
                yield LegacyDaemonEntry(
                    fsid=fsid or '',
                    daemon_type=daemon_type,
                    name=legacy_unit_name,
                    status={
                        'style': LEGACY,
                        'name': '%s.%s' % (daemon_type, daemon_id),
                        'fsid': fsid if fsid is not None else 'unknown',
                        'systemd_unit': legacy_unit_name,
                    },
                )
        elif is_fsid(dirname):
            assert isinstance(dirname, str)
            fsid = dirname
            cluster_dir = os.path.join(data_dir, fsid)
            for entry in os.listdir(cluster_dir):
                if not (
                    '.' in entry
                    and os.path.isdir(os.path.join(cluster_dir, entry))
                ):
                    continue  # invalid entry
                identity = DaemonIdentity.from_name(fsid, entry)
                yield DaemonEntry(
                    identity=identity,
                    status={
                        'style': VERSION1,
                        'name': identity.daemon_name,
                        'fsid': fsid,
                        'systemd_unit': identity.unit_name,
                    },
                )


def daemons_matching(
    ctx: CephadmContext,
    legacy_dir: Optional[str] = None,
    daemon_name: Optional[str] = None,
    type_of_daemon: Optional[str] = None,
) -> Iterator[Union[LegacyDaemonEntry, DaemonEntry]]:
    for entry in daemons(ctx, legacy_dir):
        if isinstance(entry, LegacyDaemonEntry):
            if type_of_daemon and type_of_daemon != entry.daemon_type:
                continue
        elif isinstance(entry, DaemonEntry):
            if daemon_name and daemon_name != entry.identity.daemon_name:
                continue
            if (
                type_of_daemon
                and type_of_daemon != entry.identity.daemon_type
            ):
                continue
        else:
            raise ValueError(f'unexpected entry type: {entry}')
        yield entry


def daemons_summary(
    ctx: CephadmContext,
    legacy_dir: Optional[str] = None,
    daemon_name: Optional[str] = None,
    type_of_daemon: Optional[str] = None,
) -> List[BasicDaemonStatus]:
    return [
        e.status
        for e in daemons_matching(
            ctx,
            legacy_dir,
            daemon_name=daemon_name,
            type_of_daemon=type_of_daemon,
        )
    ]
