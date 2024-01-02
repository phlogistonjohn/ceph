from typing import Iterator, Dict, List, Optional, Annotated
import json

from .enums import AuthMode, JoinSourceType, UserGroupSourceType, Intent
from .proto import Protocol, Simplified
from . import config_store
from . import shares
from . import resource


'''
class SMBCluster(Protocol):
    def shares(self) -> shares.SMBShareManager:
        ...  # pragma: no cover


class SMBClusterManager(Protocol):
    def __iter__(self) -> Iterator[str]:
        ...  # pragma: no cover

    def __getitem__(self, cluster_id: str) -> SMBCluster:
        ...  # pragma: no cover



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
'''
