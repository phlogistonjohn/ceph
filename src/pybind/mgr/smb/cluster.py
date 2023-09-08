from typing import Iterator, Dict, List, Optional
import dataclasses
import json

from .enums import AuthMode, JoinSourceType, UserGroupSourceType, Intent
from .proto import Protocol, Simplified
from . import config_store
from . import shares


class SMBCluster(Protocol):
    def shares(self) -> shares.SMBShareManager:
        ...  # pragma: no cover


class SMBClusterManager(Protocol):
    def __iter__(self) -> Iterator[str]:
        ...  # pragma: no cover

    def __getitem__(self, cluster_id: str) -> SMBCluster:
        ...  # pragma: no cover


@dataclasses.dataclass
class JoinSource:
    source_type: JoinSourceType
    username: str = ''
    password: str = ''
    uri: str = ''
    reference: str = ''

    def to_simplified(self) -> Simplified:
        out: Simplified = {'source_type': str(self.source_type)}
        if self.source_type == JoinSourceType.PASSWORD:
            out['username'] = self.username
            out['password'] = self.password
        else:
            raise NotImplementedError()
        return out

    @classmethod
    def from_dict(cls, data: Simplified) -> 'JoinSource':
        source_type = JoinSourceType(data['source_type'])
        if source_type == JoinSourceType.PASSWORD:
            return cls(
                source_type=source_type,
                username=data['username'],
                password=data['password'],
            )
        raise NotImplementedError()


@dataclasses.dataclass
class UserGroupSource:
    source_type: UserGroupSourceType
    users: List[Simplified]
    groups: List[Simplified]
    uri: str = ''
    reference: str = ''

    def to_simplified(self) -> Simplified:
        out: Simplified = {'source_type': str(self.source_type)}
        if self.source_type == UserGroupSourceType.INLINE:
            if self.users:
                out['users'] = self.users
            if self.groups:
                out['groups'] = self.groups
        else:
            raise NotImplementedError()
        return out

    @classmethod
    def from_dict(cls, data: Simplified) -> 'UserGroupSource':
        source_type = UserGroupSourceType(data['source_type'])
        if source_type == UserGroupSourceType.INLINE:
            iusers = data.get('users', [])
            igroups = data.get('groups', [])
        else:
            raise NotImplementedError()
        return cls(
            source_type=source_type,
            users=iusers,
            groups=igroups,
        )


@dataclasses.dataclass
class DomainSettings:
    realm: str
    join_sources: List[JoinSource]

    def to_simplified(self) -> Simplified:
        return {
            'realm': str(self.realm),
            'join_sources': [
                s.to_simplified() for s in self.join_sources
            ]
        }

    @classmethod
    def from_dict(cls, data: Simplified) -> 'DomainSettings':
        realm = data['realm']
        jsrc = data['join_sources']
        assert isinstance(jsrc, list)
        return cls(
            realm=realm,
            join_sources=[JoinSource.from_dict(d) for d in jsrc],
        )


@dataclasses.dataclass
class UserGroupSettings:
    user_group_sources: List[UserGroupSource]

    def to_simplified(self) -> Simplified:
        return {
            'user_group_sources': [
                s.to_simplified() for s in self.user_group_sources
            ]
        }

    @classmethod
    def from_dict(cls, data: Simplified) -> 'UserGroupSettings':
        usrc = data['user_group_sources']
        assert isinstance(usrc, list)
        return cls(
            user_group_sources=[UserGroupSource.from_dict(d) for d in usrc],
        )


@dataclasses.dataclass
class SMBInstanceSettings:
    auth_mode: AuthMode
    domain_settings: Optional[DomainSettings] = None
    user_group_settings: Optional[UserGroupSettings] = None

    def to_simplified(self) -> Simplified:
        out: Simplified = {'auth_mode': str(self.auth_mode)}
        if self.auth_mode == AuthMode.USER:
            assert self.user_group_settings
            usettings = self.user_group_settings.to_simplified()
            out['user_group_settings'] = usettings
        elif self.auth_mode == AuthMode.ACTIVE_DIRECTORY:
            assert self.domain_settings
            out['domain_settings'] = self.domain_settings.to_simplified()
        return out

    @classmethod
    def from_dict(cls, data: Simplified) -> 'SMBInstanceSettings':
        usettings = dsettings = None
        auth_mode = AuthMode(data.get('auth_mode', AuthMode.USER))
        if auth_mode == AuthMode.USER:
            usettings = UserGroupSettings.from_dict(
                data.get('user_group_settings', {})
            )
        elif auth_mode == AuthMode.ACTIVE_DIRECTORY:
            dsettings = DomainSettings.from_dict(
                data.get('domain_settings', {})
            )
        return cls(
            auth_mode=auth_mode,
            domain_settings=dsettings,
            user_group_settings=usettings,
        )


@dataclasses.dataclass
class SMBClusterIntent(SMBCluster):
    intent: Intent
    cluster_id: str
    settings: SMBInstanceSettings

    def to_simplified(self) -> Simplified:
        out = self.settings.to_simplified()
        out['cluster_id'] = self.cluster_id
        out['intent'] = str(self.intent)
        return out

    @classmethod
    def from_dict(cls, data: Simplified) -> 'SMBClusterIntent':
        return cls(
            intent=Intent(data.get('intent', Intent.PRESENT)),
            cluster_id=data['cluster_id'],
            settings=SMBInstanceSettings.from_dict(data),
        )


@dataclasses.dataclass
class ClusterRequest:
    object_type: str
    values: List[SMBClusterIntent]

    @classmethod
    def from_dict(cls, data: Simplified) -> 'ClusterRequest':
        try:
            object_type = data['object_type']
        except KeyError:
            raise shares.MissingRequirement('missing object_type field')
        if object_type == 'ceph-smb-cluster-list':
            assert isinstance(data['values'], list)
            values = [SMBClusterIntent.from_dict(d) for d in data['values']]
        elif object_type == 'ceph-smb-cluster':
            values = [SMBClusterIntent.from_dict(data)]
        else:
            raise shares.MissingRequirement('incorrect object_type')
        return cls(object_type=object_type, values=values)

    @classmethod
    def from_text(cls, buf: str) -> 'ClusterRequest':
        # TODO: make this yaml capable and sensible
        return cls.from_dict(json.loads(buf))


class FakeSMBCluster:
    def __init__(
        self,
        cluster_id: str,
        *,
        private_store: config_store.ConfigStore,
        public_store: config_store.ConfigStore
    ) -> None:
        self.cluster_id = cluster_id
        self._private_store = private_store
        self._public_store = public_store

    @property
    def ident(self) -> str:
        return self.cluster_id

    def config_options(self) -> Dict[str, str]:
        return {}

    def shares(self) -> shares.SMBShareManager:
        return shares.FakeSMBShareManager(
            self,
            public_store=self._public_store,
            private_store=self._private_store,
        )


class FakeSMBClusterManager:
    def __init__(
        self,
        *,
        private_store: config_store.ConfigStore,
        public_store: config_store.ConfigStore
    ) -> None:
        self._private_store = private_store
        self._public_store = public_store

    def __iter__(self) -> Iterator[str]:
        return iter(['foo', 'bar'])

    def __getitem__(self, cluster_id: str) -> SMBCluster:
        return FakeSMBCluster(
            cluster_id,
            public_store=self._public_store,
            private_store=self._private_store,
        )
