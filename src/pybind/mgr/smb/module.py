import logging

from typing import Any, Dict, List, Optional

from mgr_module import MgrModule, Option

import orchestrator

from . import cli
from . import cluster
from . import shares
from . import config_store


log = logging.getLogger(__name__)

CLUSTER = 'cluster'
SHARE = 'share'


class Module(orchestrator.OrchestratorClientMixin, MgrModule):
    MODULE_OPTIONS: List[Option] = []

    def __init__(self, *args: str, **kwargs: Any) -> None:
        private_store = kwargs.pop('private_store', None)
        public_store = kwargs.pop('public_store', None)
        super().__init__(*args, **kwargs)
        self._init_stores(private_store, public_store)

    def _init_stores(
        self,
        private_store: Optional[config_store.ConfigStore],
        public_store: Optional[config_store.ConfigStore],
    ) -> None:
        self._private_store = private_store or config_store.FakeConfigStore()
        self._public_store = public_store or config_store.FakeConfigStore()

    def _clusters(self) -> cluster.SMBClusterManager:
        return cluster.FakeSMBClusterManager(
            private_store=self._private_store,
            public_store=self._public_store,
        )

    @cli.Command(CLUSTER, 'ls', perm='r')
    def cluster_ls(self) -> List[str]:
        return list(self._clusters())

    @cli.Command(SHARE, 'ls', perm='r')
    def share_ls(self, cluster_id: str) -> List[Dict[str, str]]:
        return [
            {'share_id': s.share_id, 'name': s.name, 'path': s.path}
            for s in self._clusters()[cluster_id].shares()
        ]

    @cli.Command(SHARE, 'info', perm='r')
    def share_info(self, cluster_id: str) -> Dict[str, str]:
        return {}

    @cli.Command(SHARE, 'create', perm='rw')
    def share_create(
        self,
        cluster_id: str,
        share_id: str,
        path: str,
        cephfs_volume: str,
        name: str = '',
        subvolume: str = '',
        readonly: bool = False,
    ) -> shares.SMBShareStatus:
        to_create = shares.share_to_create(
            share_id=share_id,
            name=name,
            path=path,
            subsystem=shares.SubSystem.CEPHFS,
            volume=cephfs_volume,
            subvolume=subvolume,
            readonly=readonly,
        )
        smb_cluster = self._clusters()[cluster_id]
        return smb_cluster.shares().apply([to_create]).one()

    @cli.Command(SHARE, 'rm', perm='rw')
    def share_rm(self, cluster_id: str, name: str) -> shares.SMBShareStatus:
        to_delete = shares.share_to_delete(name)
        smb_cluster = self._clusters()[cluster_id]
        return smb_cluster.shares().apply([to_delete]).one()

    @cli.Command(SHARE, 'apply', perm='rw')
    def share_apply(self, cluster_id: str, inbuf: str) -> shares.ApplyResults:
        share_configs = shares.from_text(inbuf)
        smb_cluster = self._clusters()[cluster_id]
        return smb_cluster.shares().apply(share_configs)

    @cli.Command(SHARE, 'dump-config', perm='rw')
    def share_dump_config(self, cluster_id: str) -> Dict[str, Any]:
        smb_cluster = self._clusters()[cluster_id]
        return smb_cluster.shares().configuration()
