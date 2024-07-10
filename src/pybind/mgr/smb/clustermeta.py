from typing import TYPE_CHECKING, Dict, Iterator, List, Optional, TypedDict

import contextlib
import logging

from . import rados_store
from .proto import Simplified

if TYPE_CHECKING:  # pragma: no cover
    from mgr_module import MgrModule


log = logging.getLogger(__name__)


ClusterNodeEntry = TypedDict(
    'ClusterNodeEntry',
    {'pnn': int, 'identity': str, 'node': str, 'state': str},
)

CephDaemonInfo = TypedDict(
    'CephDaemonInfo',
    {'daemon_type': str, 'daemon_id': str, 'hostname': str, 'host_ip': str},
)

RankMap = Dict[int, Dict[int, Optional[str]]]
DaemonMap = Dict[str, CephDaemonInfo]


class ClusterMeta:
    def __init__(self) -> None:
        self._data: Simplified = {'nodes': [], '_source': 'cephadm'}

    def _nodes(self) -> List[ClusterNodeEntry]:
        return [node for node in self._data['nodes']]

    def _pnn_max(self) -> int:
        return max((n['pnn'] for n in self._nodes()), default=0)

    def to_simplified(self) -> Simplified:
        return self._data

    def load(self, data: Simplified) -> None:
        if not data:
            return
        assert 'nodes' in data
        self._data = data

    def sync_ranks(self, rank_map: RankMap, daemon_map: DaemonMap) -> None:
        """Convert cephadm's ranks and node info into something sambacc
        can understand and manage for ctdb.
        """
        log.info('rank_map=%r, daemon_map=%r', rank_map, daemon_map)
        log.info('current data: %r', self._data)


@contextlib.contextmanager
def rados_object(mgr: 'MgrModule', uri: str) -> Iterator[ClusterMeta]:
    """Return a cluster meta object that will store persistent data in rados."""
    pool, ns, objname = rados_store.parse_uri(uri)
    store = rados_store.RADOSConfigStore.init(mgr, pool)

    cmeta = ClusterMeta()
    previous = {}
    entry = store[ns, objname]
    try:
        # with entry.locked() ?
        previous = entry.get()
    except KeyError:
        log.debug('no previous object %s found', uri)
    cmeta.load(previous)
    yield cmeta
    # with entry.locked(): entry.put(cmeta.to_simplified())
