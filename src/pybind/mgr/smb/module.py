import logging

from typing import Any, Dict, List

from mgr_module import MgrModule, CLICommand, Option

import object_format
import orchestrator


log = logging.getLogger(__name__)


class Module(orchestrator.OrchestratorClientMixin, MgrModule):
    MODULE_OPTIONS: List[Option] = []

    def __init__(self, *args: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @CLICommand('smb cluster ls', perm='r')
    @object_format.Responder()
    def _cmd_cluster_ls(self) -> List[str]:
        return ['fake', 'foobar']

    @CLICommand('smb share ls', perm='r')
    @object_format.Responder()
    def _cmd_share_ls(self, cluster_id: str) -> List[Dict[str, str]]:
        return [
            {'name': 'hello', 'path': '/'},
            {'name': 'world', 'path': '/'},
        ]
