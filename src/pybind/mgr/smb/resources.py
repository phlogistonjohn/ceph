from typing import Optional, List, Dict

from . import resourcelib
from .resourcelib import Annotated


_embedded = resourcelib.Extras(embedded=True)
_quiet = resourcelib.Extras(keep_false=False)
_alt_share_id = resourcelib.Extras(alt_keys=['share_id'])


@resource.component()
class CephFSStorage:
    volume: str
    path: str = '/'
    subvolumegroup: Annotated[str, _quiet] = ''
    subvolume: Annotated[str, _quiet] = ''
    provider: CephFSStorageProvider = CephFSStorageProvider.KERNEL_MOUNT

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


@resource.component()
class ShareSettings:
    name: Annotated[str, _alt_share_id]
    path: str = ''
    readonly: bool = False
    browseable: bool = True
    cephfs: Optional[CephFSStorage] = None

    def validate(self) -> None:
        if self.subsystem == SubSystem.CEPHFS and not self.cephfs:
            raise ValueError('cephfs configuration missing')

    @property
    def subsystem(self) -> SubSystem:
        if not self.cephfs:
            raise ValueError('cephfs configuration missing')
        return SubSystem.CEPHFS


@resource.resource('ceph.smb.share')
class Share:
    cluster_id: str
    share_id: str
    intent: Intent = Intent.PRESENT
    share: Annotated[SMBShareSettings, _embedded] = None

    def validate(self) -> None:
        if not self.share_id:
            raise ValueError('share_id requires a value')
        if not self.share and self.intent == Intent.PRESENT:
            raise ValueError('share settings are required for present intent')


@resourcelib.component()
class JoinSource:
    source_type: JoinSourceType
    username: str = ''
    password: str = ''
    uri: str = ''
    ref: str = ''


@resourcelib.component()
class UserGroupSource:
    source_type: UserGroupSourceType
    users: List[Simplified]
    groups: List[Simplified]
    uri: str = ''
    ref: str = ''


@resourcelib.component()
class DomainSettings:
    realm: str
    join_sources: List[JoinSource]


@resourcelib.component()
class InstanceSettings:
    auth_mode: AuthMode
    domain_settings: Optional[DomainSettings] = None
    user_group_settings: Optional[List[UserGroupSource]] = None


@resourcelib.resource('ceph.smb.cluster')
class Cluster:
    cluster_id: str
    intent: Intent = Intent.PRESENT
    settings: Annotated[SMBInstanceSettings, _embedded] = None


@resourcelib.component()
class JoinAuthValues:
    username: str
    password: str


@resourcelib.resource('ceph.smb.join.auth')
class JoinAuth:
    auth_id: str
    intent: Intent = Intent.PRESENT
    values: Optional[JoinAuthValues] = None


DEMO = """
---
resource_type: ceph.smb.cluster
cluster_id: chacha
auth_mode: active-directory
domain_settings:
  realm: CEPH.SINK.TEST
  join_sources:
    - source_type: reference
      ref: jsrc1
    - source_type: inline
      username: Administrator
      password: fallb4kP4ssw0rd
---
resource_type: ceph.smb.share
cluster_id: chacha
share_id: s1
cephfs
  volume: cephfs
  path: /
---
resource_type: ceph.smb.share
cluster_id: chacha
share_id: s2
name: My Second Share
cephfs:
  volume: cephfs
  subvolume: cool/beans
---
resource_type: ceph.smb.share
cluster_id: chacha
share_id: s0
intent: removed
# deleted this test share
---
resource_type: ceph.smb.join.auth
auth_id: bob
values:
  username: BobTheAdmin
  password: someJunkyPassw0rd
---
resource_type: ceph.smb.join.auth
auth_id: alice
intent: removed
# alice left the company
"""
