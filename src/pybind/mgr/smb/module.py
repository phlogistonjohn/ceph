import logging

from typing import Any, Dict, List, Optional

from mgr_module import MgrModule, Option

import orchestrator

from . import cli
from . import cluster
from . import shares
from . import config_store
from .proto import ConfigStore
from . import resourcelib


log = logging.getLogger(__name__)


class Module(orchestrator.OrchestratorClientMixin, MgrModule):
    MODULE_OPTIONS: List[Option] = []

    def __init__(self, *args: str, **kwargs: Any) -> None:
        private_store = kwargs.pop('private_store', None)
        public_store = kwargs.pop('public_store', None)
        super().__init__(*args, **kwargs)
        self._private_store = private_store or config_store.FakeConfigStore()
        self._public_store = public_store or config_store.FakeConfigStore()

    def _clusters(self) -> 'cluster.SMBClusterManager':
        return cluster.FakeSMBClusterManager(
            private_store=self._private_store,
            public_store=self._public_store,
        )

    @cli.SMBCommand('apply', perm='rw')
    def apply(self, inbuf: str) -> 'Results':
        return self._handler.apply_all(resourcelib.load(inbuf))

    @cli.SMBCommand('cluster ls', perm='r')
    def cluster_ls(self) -> List[str]:
        return [c.cluster_id for c in self._handler.clusters()]

    @cli.SMBCommand('share ls', perm='r')
    def share_ls(self, cluster_id: str) -> List[Dict[str, str]]:
        return [s.share_id for s in self._handler.shares() if s.cluster_id == cluster_id]

    @cli.SMBCommand('share info', perm='r')
    def share_info(self, cluster_id: str) -> Dict[str, str]:
        return {}

    @cli.SMBCommand('share create', perm='rw')
    def share_create(
        self,
        cluster_id: str,
        share_id: str,
        path: str,
        cephfs_volume: str,
        name: str = '',
        subvolume: str = '',
        readonly: bool = False,
    ) -> 'shares.SMBShareStatus':
        share = shares.present_share(
            cluster_id=cluster_id,
            share_id=share_id,
            name=name,
            path=path,
            volume=cephfs_volume,
            subvolume=subvolume,
            readonly=readonly,
        )
        return self._handler.apply(share)

    @cli.SMBCommand('share rm', perm='rw')
    def share_rm(self, cluster_id: str, share_id: str) -> 'shares.SMBShareStatus':
        share = shares.removed_share(cluster_id, share_id)
        return self._handler.apply(share)

    @cli.SMBCommand('cluster get-config', perm='rw')
    def share_dump_config(self, cluster_id: str) -> Dict[str, Any]:
        return self._handler.generate_config(cluster_id)
