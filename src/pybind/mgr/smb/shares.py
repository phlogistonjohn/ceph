from typing import Any, Iterator, Iterable, List, Optional, Dict, Tuple, Annotated
import json
import pathlib

from . import config_store
from .proto import Protocol, Simplified, SimplifiedList
from .enums import CephFSStorageProvider, SubSystem, Intent, State



SMBShare = str


#@resource.resource('ceph.smb.status.share')
class SMBShareStatus:
    share: SMBShare
    # state is a str so we can report one-off custom states if needed,
    # generally though, we want to use known values from the State enum.
    state: str
    # ceph errno if there was a problem with the change being applied
    errno: int

    def xxx_to_simplified(self) -> Simplified:
        """Return a simplified & serializable representation for the
        SMBShareStatus.
        """
        status: Simplified = {'state': self.state}
        if self.errno != 0:
            status['errno'] = abs(self.errno)
        return {
            'share_id': self.share.share_id,
            'name': self.share.name,
            'path': self.share.path,
            'status': status,
        }


class ApplyResults:
    values: List[SMBShareStatus]

    def __init__(self) -> None:
        self.values = []

    def __iter__(self) -> Iterator[SMBShareStatus]:
        return iter(self.values)

    def add(self, share: SMBShare, *, state: str, errno: int = 0) -> None:
        self.values.append(SMBShareStatus(share, state=state, errno=errno))

    def one(self) -> SMBShareStatus:
        return self.values[0]

    def to_simplified(self) -> SimplifiedList:
        return [v.to_simplified() for v in self.values]


class ClusterProperties(Protocol):
    @property
    def ident(self) -> str:
        ...  # pragma: no cover

    def config_options(self) -> Dict[str, str]:
        ...  # pragma: no cover


class FakeSMBShareManager:
    def __init__(
        self,
        cluster: ClusterProperties,
        *,
        private_store: config_store.ConfigStore,
        public_store: config_store.ConfigStore
    ) -> None:
        self._cluster = cluster
        self._private_store = private_store
        self._public_store = public_store
        self._shares: List[SMBShare] = []
        self._load()

    @property
    def _shares_key(self) -> Tuple[str, str]:
        return (self._cluster.ident, 'smb.shares')

    @property
    def _config_key(self) -> Tuple[str, str]:
        return (self._cluster.ident, 'configuration')

    def _save(self) -> None:
        self._private_store[self._shares_key].write(
            json.dumps([s.to_simplified() for s in self._shares])
        )
        self._public_store[self._config_key].write(
            json.dumps(self.configuration())
        )

    def _fetch(self) -> List[SMBShare]:
        try:
            data = json.loads(self._private_store[self._shares_key].read())
        except KeyError:
            return []
        return [SMBShare.from_dict(s) for s in data]

    def _load(self) -> None:
        self._shares = self._fetch()

    def __iter__(self) -> Iterator[SMBShare]:
        return iter(self._shares)

    def __getitem__(self, share_id: str) -> SMBShare:
        smap = {s.share_id: s for s in self._shares}
        return smap[share_id]

    def apply(self, intents: Iterable[SMBShare]) -> ApplyResults:
        results = ApplyResults()
        for si in intents:
            if si.intent == Intent.REMOVED:
                self._remove(results, si)
            elif si.intent == Intent.PRESENT:
                self._create(results, si)
        self._save()
        return results

    def _remove(self, results: ApplyResults, si: SMBShare) -> None:
        assert si.intent == Intent.REMOVED
        smap = {s.share_id: idx for idx, s in enumerate(self._shares)}
        removeme = smap.pop(si.share.share_id, None)
        if removeme is None:
            results.add(si.share, state=str(State.NOT_PRESENT))
        else:
            share = self._shares[removeme]
            del self._shares[removeme]
            results.add(share, state=str(State.REMOVED))

    def _create(self, results: ApplyResults, si: SMBShare) -> None:
        assert si.intent == Intent.PRESENT
        smap = {s.share_id: idx for idx, s in enumerate(self._shares)}
        if si.share.share_id not in smap:
            # create new
            self._shares.append(si.share)
            results.add(si.share, state=str(State.CREATED))
        else:
            idx = smap[si.share.share_id]
            share = self._shares[idx]
            # compare and optionally update
            if si.share == share:
                results.add(si.share, state=str(State.PRESENT))
            else:
                self._shares[idx] = si.share
                results.add(si.share, state=str(State.UPDATED))

    def configuration(self) -> Simplified:
        return {
            'samba-container-config': "v0",
            'configs': {
                self._cluster.ident: {
                    'instance_name': 'FAKE',
                    'instance_features': [],
                    'shares': [s.name for s in self._shares],
                    'globals': ['default', self._cluster.ident],
                },
            },
            'shares': {s.name: _options(s) for s in self._shares},
            'globals': {
                'default': {
                    'server min protocol': 'SMB2',
                    'load printers': 'No',
                    'printing': 'bsd',
                    'printcap name': '/dev/null',
                    'disable spoolss': 'Yes',
                },
                self._cluster.ident: self._cluster.config_options(),
            },
        }


def _options(share: SMBShare) -> Dict[str, Dict[str, str]]:
    return {
        'options': {
            'path': share.path,
            'read only': _yn(share.readonly),
            'browseable': _yn(share.browseable),
            'cephmeta:id': share.share_id,
            'cephmeta:name': share.name,
        }
    }


def _yn(value: bool) -> str:
    return 'Yes' if value else 'No'


def share_to_create(
    share_id: str,
    name: str,
    path: str,
    subsystem: SubSystem,
    volume: str,
    subvolume: str = '',
    readonly: bool = False,
) -> SMBShare:
    storage = CephFSStorage.from_options(
        volume=volume,
        subvolume=subvolume,
        path=path,
    )
    share = SMBShare.from_options(
        share_id=share_id,
        name=name,
        readonly=readonly,
        subsystem=SubSystem(subsystem),
        cephfs=storage,
    )
    return SMBShare(
        intent=Intent.PRESENT,
        share=share,
    )


def share_to_delete(share_id: str) -> SMBShare:
    share = SMBShareStub(share_id=share_id, name='')
    return SMBShare(
        intent=Intent.REMOVED,
        share=share,
    )


def from_text(buf: str) -> List[SMBShare]:
    pass
    # TODO: make this yaml capable and sensible
    # data = json.loads(buf)
    # return resource.load(data)
    # return from_request_objects(data)


def from_request_objects(data: Simplified) -> List[SMBShare]:
    object_type = data.pop('object_type', '')
    if not object_type:
        raise MissingRequirement('missing object_type field')
    if object_type == 'ceph-smb-share-list':
        assert isinstance(data['values'], list)
        return [SMBShare.from_dict(d) for d in data['values']]
    if object_type == 'ceph-smb-share':
        return [SMBShare.from_dict(data)]
    raise MissingRequirement('incorrect object_type')


class SMBShareManager(Protocol):
    def __iter__(self) -> Iterator[SMBShare]:
        ...  # pragma: no cover

    def __getitem__(self, share_id: str) -> SMBShare:
        ...  # pragma: no cover

    def apply(self, intents: Iterable[SMBShare]) -> ApplyResults:
        ...  # pragma: no cover

    def configuration(self) -> Simplified:
        ...  # pragma: no cover
