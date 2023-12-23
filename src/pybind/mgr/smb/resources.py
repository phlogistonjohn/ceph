from typing import Optional, List, Dict

from . import resourcelib
from .resourcelib import Annotated
from .enums import (
    AuthMode,
    CephFSStorageProvider,
    Intent,
    JoinSourceType,
    SubSystem,
    UserGroupSourceType,
)
from .proto import Simplified


_embedded = resourcelib.Extras(embedded=True)
_quiet = resourcelib.Extras(keep_false=False)
_alt_share_id = resourcelib.Extras(alt_keys=['share_id'])


@resourcelib.component()
class CephFSStorage:
    volume: str
    path: str = '/'
    subvolumegroup: Annotated[str, _quiet] = ''
    subvolume: Annotated[str, _quiet] = ''
    provider: CephFSStorageProvider = CephFSStorageProvider.SAMBA_VFS

    def __post_init__(self) -> None:
        if '/' in self.subvolume and not self.subvolumegroup:
            try:
                svg, sv = self.subvolume.split('/')
                self.subvolumegroup = svg
                self.subvolume = sv
            except ValueError:
                raise ValueError(
                    'invalid subvolume value: {self.subvolume!r}'
                )

    def validate(self) -> None:
        if not self.volume:
            raise ValueError('volume requires a value')
        if '/' in self.subvolumegroup:
            raise ValueError(
                'invalid subvolumegroup value: {self.subvolumegroup!r}'
            )
        if '/' in self.subvolume:
            raise ValueError('invalid subvolume value: {self.subvolume!r}')


@resourcelib.component()
class ShareSettings:
    name: Annotated[str, _alt_share_id]
    readonly: bool = False
    browseable: bool = True
    cephfs: Optional[CephFSStorage] = None

    @property
    def subsystem(self) -> SubSystem:
        if not self.cephfs:
            raise ValueError('cephfs configuration missing')
        return SubSystem.CEPHFS


@resourcelib.resource('ceph.smb.share')
class Share:
    cluster_id: str
    share_id: str
    intent: Intent = Intent.PRESENT
    share: Annotated[Optional[ShareSettings], _embedded] = None

    def __post_init__(self):
        # because share settings are embedded and use share_id as an alt key
        # for the name we filter out unusable share settings if intent
        # is removed
        if (
            self.intent == Intent.REMOVED
            and self.share
            and not self.share.cephfs
        ):
            self.share = None

    def validate(self) -> None:
        if not self.share_id:
            raise ValueError('share_id requires a value')
        if not self.share and self.intent == Intent.PRESENT:
            raise ValueError('share settings are required for present intent')


@resourcelib.component()
class JoinSource:
    source_type: JoinSourceType
    username: Annotated[str, _quiet] = ''
    password: Annotated[str, _quiet] = ''
    uri: Annotated[str, _quiet] = ''
    ref: Annotated[str, _quiet] = ''


@resourcelib.component()
class UserGroupSource:
    source_type: UserGroupSourceType
    users: List[Simplified]
    groups: List[Simplified]
    uri: Annotated[str, _quiet] = ''
    ref: Annotated[str, _quiet] = ''


@resourcelib.component()
class DomainSettings:
    realm: str
    join_sources: List[JoinSource]


@resourcelib.component()
class ClusterSettings:
    auth_mode: AuthMode
    domain_settings: Optional[DomainSettings] = None
    user_group_settings: Optional[List[UserGroupSource]] = None

    def validate(self):
        if self.auth_mode == AuthMode.ACTIVE_DIRECTORY:
            if not self.domain_settings:
                raise ValueError(
                    'domain settings are required for active directory mode'
                )
            if self.user_group_settings:
                raise ValueError(
                    'user & group settings not supported for active directory mode'
                )
        if self.auth_mode == AuthMode.USER:
            if not self.user_group_settings:
                raise ValueError(
                    'user & group settings required for user auth mode'
                )
            if self.domain_settings:
                raise ValueError(
                    'domain settings not supported for user auth mode'
                )


@resourcelib.resource('ceph.smb.cluster')
class Cluster:
    cluster_id: str
    intent: Intent = Intent.PRESENT
    settings: Annotated[Optional[ClusterSettings], _embedded] = None


@resourcelib.component()
class JoinAuthValues:
    username: str
    password: str


@resourcelib.resource('ceph.smb.join.auth')
class JoinAuth:
    auth_id: str
    intent: Intent = Intent.PRESENT
    values: Optional[JoinAuthValues] = None
