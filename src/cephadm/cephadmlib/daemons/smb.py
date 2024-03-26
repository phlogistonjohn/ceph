import enum
import json
import logging
import pathlib
import socket

from typing import List, Dict, Tuple, Optional, Any

from .. import context_getters
from .. import daemon_form
from .. import data_utils
from .. import deployment_utils
from .. import file_utils
from ..constants import DEFAULT_SMB_IMAGE
from ..container_daemon_form import ContainerDaemonForm, daemon_to_container
from ..container_engines import Podman
from ..container_types import (
    CephContainer,
    InitContainer,
    Namespace,
    SidecarContainer,
    enable_shared_namespaces,
)
from ..context import CephadmContext
from ..daemon_identity import DaemonIdentity, DaemonSubIdentity
from ..deploy import DeploymentType
from ..exceptions import Error
from ..net_utils import EndPoint


logger = logging.getLogger()


class Features(enum.Enum):
    DOMAIN = 'domain'
    CLUSTERED = 'clustered'
    FSMOUNTS = 'fsmounts'

    @classmethod
    def valid(cls, value: str) -> bool:
        # workaround for older python versions
        try:
            cls(value)
            return True
        except ValueError:
            return False


class Config:
    instance_id: str
    source_config: str
    samba_debug_level: int
    debug_delay: int
    domain_member: bool
    clustered: bool
    fsmounts: bool
    join_sources: List[str]
    custom_dns: List[str]
    smb_port: int
    ceph_config_entity: str
    fs_auth_entities: List[str]
    vhostname: str

    def __init__(
        self,
        *,
        instance_id: str,
        source_config: str,
        domain_member: bool,
        clustered: bool,
        fsmounts: bool = False,
        samba_debug_level: int = 0,
        debug_delay: int = 0,
        join_sources: Optional[List[str]] = None,
        custom_dns: Optional[List[str]] = None,
        smb_port: int = 0,
        ceph_config_entity: str = 'client.admin',
        fs_auth_entities: Optional[List[str]] = None,
        vhostname: str = '',
    ) -> None:
        self.instance_id = instance_id
        self.source_config = source_config
        self.domain_member = domain_member
        self.clustered = clustered
        self.fsmounts = fsmounts
        self.samba_debug_level = samba_debug_level
        self.debug_delay = debug_delay
        self.join_sources = join_sources or []
        self.custom_dns = custom_dns or []
        self.smb_port = smb_port
        self.ceph_config_entity = ceph_config_entity
        self.fs_auth_entities = fs_auth_entities or []
        self.vhostname = vhostname

    def __str__(self) -> str:
        return (
            f'SMB Config[id={self.instance_id},'
            f' source_config={self.source_config},'
            f' domain_member={self.domain_member},'
            f' clustered={self.clustered}]'
        )


def _container_dns_args(cfg: Config) -> List[str]:
    cargs = []
    for dns in cfg.custom_dns:
        cargs.append(f'--dns={dns}')
    if cfg.vhostname:
        cargs.append(f'--hostname={cfg.vhostname}')
    return cargs


class SambaContainerCommon:
    image: Optional[str] = None
    entrypoint: Optional[str] = None
    privileged: bool = False

    def __init__(
        self,
        cfg: Config,
    ) -> None:
        self.cfg = cfg

    def name(self) -> str:
        raise NotImplementedError('samba container name')

    def envs(self) -> Dict[str, str]:
        cfg_uris = [self.cfg.source_config]
        environ = {
            'SAMBA_CONTAINER_ID': self.cfg.instance_id,
            'SAMBACC_CONFIG': json.dumps(cfg_uris),
        }
        if self.cfg.ceph_config_entity:
            environ['SAMBACC_CEPH_ID'] = f'name={self.cfg.ceph_config_entity}'
        return environ

    def envs_list(self) -> List[str]:
        return [f'{k}={v}' for (k, v) in self.envs().items()]

    def args(self) -> List[str]:
        args = []
        if self.cfg.samba_debug_level:
            args.append(f'--samba-debug-level={self.cfg.samba_debug_level}')
        if self.cfg.debug_delay:
            args.append(f'--debug-delay={self.cfg.debug_delay}')
        return args

    def container_args(self) -> List[str]:
        return []


class SMBDContainer(SambaContainerCommon):
    def name(self) -> str:
        return 'smbd'

    def args(self) -> List[str]:
        return super().args() + ['run', 'smbd']

    def container_args(self) -> List[str]:
        cargs = []
        if self.cfg.smb_port:
            cargs.append(f'--publish={self.cfg.smb_port}:{self.cfg.smb_port}')
        cargs.extend(_container_dns_args(self.cfg))
        return cargs


class WinbindContainer(SambaContainerCommon):
    def name(self) -> str:
        return 'winbindd'

    def args(self) -> List[str]:
        return super().args() + ['run', 'winbindd']


class ConfigInitContainer(SambaContainerCommon):
    def name(self) -> str:
        return 'config'

    def args(self) -> List[str]:
        return super().args() + ['init']


class MustJoinContainer(SambaContainerCommon):
    def name(self) -> str:
        return 'mustjoin'

    def args(self) -> List[str]:
        args = super().args() + ['must-join']
        for join_src in self.cfg.join_sources:
            args.append(f'-j{join_src}')
        return args

    def container_args(self) -> List[str]:
        cargs = _container_dns_args(self.cfg)
        return cargs


class ConfigWatchContainer(SambaContainerCommon):
    def name(self) -> str:
        return 'configwatch'

    def args(self) -> List[str]:
        return super().args() + ['update-config', '--watch']


class FSMountContainer(SambaContainerCommon):
    def __init__(
        self,
        cfg: Config,
        *,
        ceph_image: str = 'quay.io/phlogistonjohn/ceph:dev',
    ) -> None:
        super().__init__(cfg)
        self.entrypoint = 'bash'
        self.image = ceph_image
        self.privileged = True

    def name(self) -> str:
        return 'fsmount'

    def args(self) -> List[str]:
        api_user = self.cfg.ceph_config_entity
        if api_user.startswith('client.'):
            api_user = api_user.split('.', 1)[-1]
        fs_user = self.cfg.fs_auth_entities[0]
        if fs_user.startswith('client.'):
            fs_user = fs_user.split('.', 1)[-1]
        return [
            '-c',
            (
                'unzip -o /usr/sbin/cephadm cephadmlib/tincam.py'
                ' && exec python3 cephadmlib/tincam.py'
                ' --interval=30'
                ' --auto-cephfs'
                f' --api-user={api_user}'
                f' --fs-user={fs_user}'
            ),
        ]


class ContainerLayout:
    init_containers: List[SambaContainerCommon]
    primary: SambaContainerCommon
    supplemental: List[SambaContainerCommon]

    def __init__(
        self,
        init_containers: List[SambaContainerCommon],
        primary: SambaContainerCommon,
        supplemental: List[SambaContainerCommon],
    ) -> None:
        self.init_containers = init_containers
        self.primary = primary
        self.supplemental = supplemental


@daemon_form.register
class SMB(ContainerDaemonForm):
    """Provides a form for SMB containers."""

    daemon_type = 'smb'
    default_image = DEFAULT_SMB_IMAGE

    @classmethod
    def for_daemon_type(cls, daemon_type: str) -> bool:
        return cls.daemon_type == daemon_type

    def __init__(self, ctx: CephadmContext, ident: DaemonIdentity):
        assert ident.daemon_type == self.daemon_type
        self._identity = ident
        self._instance_cfg: Optional[Config] = None
        self._files: Dict[str, str] = {}
        self._raw_configs: Dict[str, Any] = context_getters.fetch_configs(ctx)
        self._config_keyring = context_getters.get_config_and_keyring(ctx)
        self._cached_layout: Optional[ContainerLayout] = None
        self.smb_port = 445
        logger.debug('Created SMB ContainerDaemonForm instance')

    def validate(self) -> None:
        if self._instance_cfg is not None:
            return

        configs = self._raw_configs
        instance_id = configs.get('cluster_id', '')
        source_config = configs.get('config_uri', '')
        join_sources = configs.get('join_sources', [])
        custom_dns = configs.get('custom_dns', [])
        instance_features = configs.get('features', [])
        files = data_utils.dict_get(configs, 'files', {})
        ceph_config_entity = configs.get('config_auth_entity', '')
        fs_auth_entities = configs.get('fs_auth_entities', [])
        vhostname = configs.get('virtual_hostname', '')

        if not instance_id:
            raise Error('invalid instance (cluster) id')
        if not source_config:
            raise Error('invalid configuration source uri')
        invalid_features = {
            f for f in instance_features if not Features.valid(f)
        }
        if invalid_features:
            raise Error(
                f'invalid instance features: {", ".join(invalid_features)}'
            )
        if Features.CLUSTERED.value in instance_features:
            raise NotImplementedError('clustered instance')
        if not vhostname:
            # if a virtual hostname is not provided, generate one by prefixing
            # the cluster/instanced id to the system hostname
            hname = socket.getfqdn()
            vhostname = f'{instance_id}-{hname}'

        self._instance_cfg = Config(
            instance_id=instance_id,
            source_config=source_config,
            join_sources=join_sources,
            custom_dns=custom_dns,
            domain_member=Features.DOMAIN.value in instance_features,
            clustered=Features.CLUSTERED.value in instance_features,
            fsmounts=Features.FSMOUNTS.value in instance_features,
            samba_debug_level=6,
            smb_port=self.smb_port,
            ceph_config_entity=ceph_config_entity,
            fs_auth_entities=fs_auth_entities,
            vhostname=vhostname,
        )
        self._files = files
        logger.debug('SMB Instance Config: %s', self._instance_cfg)
        logger.debug('Configured files: %s', self._files)

    @property
    def _cfg(self) -> Config:
        self.validate()
        assert self._instance_cfg
        return self._instance_cfg

    @property
    def instance_id(self) -> str:
        return self._cfg.instance_id

    @property
    def source_config(self) -> str:
        return self._cfg.source_config

    @classmethod
    def create(cls, ctx: CephadmContext, ident: DaemonIdentity) -> 'SMB':
        return cls(ctx, ident)

    @property
    def identity(self) -> DaemonIdentity:
        return self._identity

    def uid_gid(self, ctx: CephadmContext) -> Tuple[int, int]:
        return 0, 0

    def config_and_keyring(
        self, ctx: CephadmContext
    ) -> Tuple[Optional[str], Optional[str]]:
        return self._config_keyring

    def _layout(self) -> ContainerLayout:
        if self._cached_layout:
            return self._cached_layout
        init_ctrs: List[SambaContainerCommon] = []
        ctrs: List[SambaContainerCommon] = []

        init_ctrs.append(ConfigInitContainer(self._cfg))
        ctrs.append(ConfigWatchContainer(self._cfg))

        if self._cfg.domain_member:
            init_ctrs.append(MustJoinContainer(self._cfg))
            ctrs.append(WinbindContainer(self._cfg))

        if self._cfg.fsmounts:
            ctrs.append(FSMountContainer(self._cfg))

        smbd = SMBDContainer(self._cfg)
        self._cached_layout = ContainerLayout(init_ctrs, smbd, ctrs)
        return self._cached_layout

    def _to_init_container(
        self, ctx: CephadmContext, smb_ctr: SambaContainerCommon
    ) -> InitContainer:
        volume_mounts: Dict[str, str] = {}
        container_args: List[str] = smb_ctr.container_args()
        self.customize_container_mounts(ctx, volume_mounts)
        # XXX: is this needed? if so, can this be simplified
        if isinstance(ctx.container_engine, Podman):
            ctx.container_engine.update_mounts(ctx, volume_mounts)
        identity = DaemonSubIdentity.from_parent(
            self.identity, smb_ctr.name()
        )
        return InitContainer(
            ctx,
            entrypoint='',
            image=ctx.image or self.default_image,
            identity=identity,
            args=smb_ctr.args(),
            container_args=container_args,
            envs=smb_ctr.envs_list(),
            volume_mounts=volume_mounts,
        )

    def _to_sidecar_container(
        self, ctx: CephadmContext, smb_ctr: SambaContainerCommon
    ) -> SidecarContainer:
        volume_mounts: Dict[str, str] = {}
        container_args: List[str] = smb_ctr.container_args()
        self.customize_container_mounts(ctx, volume_mounts)
        shared_ns = {
            Namespace.ipc,
            Namespace.network,
            Namespace.pid,
        }
        if isinstance(ctx.container_engine, Podman):
            # XXX: is this needed? if so, can this be simplified
            ctx.container_engine.update_mounts(ctx, volume_mounts)
            # docker doesn't support sharing the uts namespace with other
            # containers. It may not be entirely needed on podman but it gives
            # me warm fuzzies to make sure it gets shared.
            shared_ns.add(Namespace.uts)
        enable_shared_namespaces(
            container_args, self.identity.container_name, shared_ns
        )
        identity = DaemonSubIdentity.from_parent(
            self.identity, smb_ctr.name()
        )
        image = smb_ctr.image or ctx.image or self.default_image
        entrypoint = smb_ctr.entrypoint or ''
        return SidecarContainer(
            ctx,
            entrypoint=entrypoint,
            image=image,
            identity=identity,
            container_args=container_args,
            args=smb_ctr.args(),
            envs=smb_ctr.envs_list(),
            volume_mounts=volume_mounts,
            init=False,
            privileged=smb_ctr.privileged,
            remove=True,
        )

    def container(self, ctx: CephadmContext) -> CephContainer:
        ctr = daemon_to_container(ctx, self, host_network=False)
        # We want to share the IPC ns between the samba containers for one
        # instance.  Cephadm's default, host ipc, is not what we want.
        # Unsetting it works fine for podman but docker (on ubuntu 22.04) needs
        # to be expliclty told that ipc of the primary container must be
        # shareable.
        ctr.ipc = 'shareable'
        return deployment_utils.to_deployment_container(ctx, ctr)

    def init_containers(self, ctx: CephadmContext) -> List[InitContainer]:
        return [
            self._to_init_container(ctx, smb_ctr)
            for smb_ctr in self._layout().init_containers
        ]

    def sidecar_containers(
        self, ctx: CephadmContext
    ) -> List[SidecarContainer]:
        return [
            self._to_sidecar_container(ctx, smb_ctr)
            for smb_ctr in self._layout().supplemental
        ]

    def customize_container_envs(
        self, ctx: CephadmContext, envs: List[str]
    ) -> None:
        clayout = self._layout()
        envs.extend(clayout.primary.envs_list())

    def customize_process_args(
        self, ctx: CephadmContext, args: List[str]
    ) -> None:
        clayout = self._layout()
        args.extend(clayout.primary.args())

    def customize_container_args(
        self, ctx: CephadmContext, args: List[str]
    ) -> None:
        args.extend(self._layout().primary.container_args())

    def customize_container_mounts(
        self,
        ctx: CephadmContext,
        mounts: Dict[str, str],
    ) -> None:
        self.validate()
        data_dir = pathlib.Path(self.identity.data_dir(ctx.data_dir))
        etc_samba_ctr = str(data_dir / 'etc-samba-container')
        lib_samba = str(data_dir / 'lib-samba')
        run_samba = str(data_dir / 'run')
        config = str(data_dir / 'config')
        keyring = str(data_dir / 'keyring')
        mounts[etc_samba_ctr] = '/etc/samba/container:z'
        mounts[lib_samba] = '/var/lib/samba:z'
        mounts[run_samba] = '/run:z'  # TODO: make this a shared tmpfs
        mounts[config] = '/etc/ceph/ceph.conf:z'
        mounts[keyring] = '/etc/ceph/keyring:z'
        if self._cfg.fsmounts:
            srv_dir = str(data_dir / 'srv')
            mounts[srv_dir] = '/srv:shared'

    def customize_container_endpoints(
        self, endpoints: List[EndPoint], deployment_type: DeploymentType
    ) -> None:
        if not any(ep.port == self.smb_port for ep in endpoints):
            endpoints.append(EndPoint('0.0.0.0', self.smb_port))

    def prepare_data_dir(self, data_dir: str, uid: int, gid: int) -> None:
        self.validate()
        ddir = pathlib.Path(data_dir)
        file_utils.makedirs(ddir / 'etc-samba-container', uid, gid, 0o770)
        file_utils.makedirs(ddir / 'lib-samba', uid, gid, 0o770)
        file_utils.makedirs(ddir / 'run', uid, gid, 0o770)
        if self._cfg.fsmounts:
            file_utils.makedirs(ddir / 'srv', uid, gid, 0o771)
        if self._files:
            file_utils.populate_files(data_dir, self._files, uid, gid)
