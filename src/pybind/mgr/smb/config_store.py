from typing import Tuple, Collection, Iterator, Dict, TYPE_CHECKING

import rados

from .proto import Protocol

if TYPE_CHECKING:  # pragma: no cover
    from mgr_module import MgrModule

_CHUNK_SIZE = 32 * 1024
SMB_POOL = '.smb'


class RADOSConfigStore:
    def __init__(self, rados: rados.Rados, pool: str = SMB_POOL) -> None:
        self._pool = pool
        self._rados = rados

    def __getitem__(self, key: Tuple[str, str]) -> 'RADOSConfigResource':
        ns, okey = key
        return RADOSConfigResource(self._rados, self._pool, ns, okey)

    def namespaces(self) -> Collection[str]:
        return {item[0] for item in self}

    def contents(self, ns: str) -> Collection[str]:
        return [item[1] for item in self if ns == item[0]]

    def __iter__(self) -> Iterator[Tuple[str, str]]:
        out = []
        with self._rados.open_ioctx(self._pool) as ioctx:
            ioctx.set_namespace(rados.LIBRADOS_ALL_NSPACES)
            for obj in ioctx.list_objects():
                out.append((obj.nspace, obj.key))
        return iter(out)

    def _init_pool(self, mgr: 'MgrModule') -> None:
        pools = mgr.get_osdmap().dump().get('pools', [])
        pool_names = {p['pool_name'] for p in pools}
        if self._pool in pool_names:
            return
        mgr.check_mon_command(
            {
                'prefix': 'osd pool create',
                'pool': self._pool,
                'yes_i_really_mean_it': True,
            }
        )
        mgr.check_mon_command(
            {
                'prefix': 'osd pool application enable',
                'pool': self._pool,
                'app': 'nfs',
            }
        )

    @classmethod
    def init(
        cls, mgr: 'MgrModule', pool: str = SMB_POOL
    ) -> 'RADOSConfigStore':
        rados_store = cls(mgr.rados, pool=pool)
        rados_store._init_pool(mgr)
        return rados_store


class RADOSConfigResource:
    def __init__(
        self, rados: rados.Rados, pool: str, ns: str, key: str
    ) -> None:
        self._rados = rados
        self._pool = pool
        self._ns = ns
        self._key = key

    @property
    def uri(self) -> str:
        return f'rados://{self._pool}/{self._ns}/{self._key}'

    def read(self) -> str:
        with self._rados.open_ioctx(self._pool) as ioctx:
            ioctx.set_namespace(self._ns)
            try:
                return ioctx.read(self._key, _CHUNK_SIZE).decode()
            except rados.ObjectNotFound:
                return ''

    def write(self, content: str) -> None:
        data = content.encode('utf-8')
        assert len(data) < _CHUNK_SIZE
        with self._rados.open_ioctx(self._pool) as ioctx:
            ioctx.set_namespace(self._ns)
            ioctx.write_full(self._key, data)


class FakeConfigStore:
    def __init__(self) -> None:
        self._data: Dict[Tuple[str, str], str] = {}

    def __getitem__(self, key: Tuple[str, str]) -> 'FakeConfigResource':
        return FakeConfigResource(self, key[0], key[1])

    def namespaces(self) -> Collection[str]:
        return {k[0] for k in self._data.keys()}

    def contents(self, ns: str) -> Collection[str]:
        return {k[1] for k in self._data.keys() if k[0] == ns}

    def __iter__(self) -> Iterator[Tuple[str, str]]:
        return iter(self._data.keys())


class FakeConfigResource:
    def __init__(self, store: FakeConfigStore, ns: str, name: str) -> None:
        self._store = store
        self._ns = ns
        self._name = name

    def read(self) -> str:
        return self._store._data[(self._ns, self._name)]

    def write(self, content: str) -> None:
        self._store._data[(self._ns, self._name)] = content

    @property
    def uri(self) -> str:
        return f'fake-resource:{self._ns}/{self._name}'


class ConfigResource(Protocol):
    # __init__(self, rados, pool, namespace, key)
    # uri=rados://pool/cluster_id/key
    #
    # __init__(self, cephfs, volume, path, key)
    # uri=cephfs://volume/path/to/cluster_dir/key
    #
    # __init__(self, key) # mon store proxied thru module
    # uri=ceph-mgr:smb/share/config-dump/cluster_id
    #

    def read(self) -> str:
        ...  # pragma: no cover

    def write(self, content: str) -> None:
        ...  # pragma: no cover

    @property
    def uri(self) -> str:
        ...  # pragma: no cover


class ConfigStore(Protocol):
    def __getitem__(self, key: Tuple[str, str]) -> ConfigResource:
        ...  # pragma: no cover

    def namespaces(self) -> Collection[str]:
        ...  # pragma: no cover

    def contents(self, ns: str) -> Collection[str]:
        ...  # pgrama: no cover

    def __iter__(self) -> Iterator[Tuple[str, str]]:
        ...  # pragma: no cover
