import base64
import contextlib
import enum
import functools
import os
import pathlib
import time

import cephutil

import smbclient
from smbprotocol.header import NtStatus
import smbprotocol.open
import smbprotocol.file_info
import smbprotocol.security_descriptor
import smbprotocol.tree


class SMBTestHost:
    """Host configuration wrapper."""

    def __init__(self, data):
        self._server_data = data

    @property
    def ip_address(self):
        return self._server_data.get('ip_address', '')

    @property
    def name(self):
        return self._server_data.get('name', '')


class SMBTestServer(SMBTestHost):
    """Server configuration wrapper."""

    @property
    def port(self):
        return 445

    @property
    def ssh_user(self):
        return self._server_data.get('user', '')


class SMBTestConf:
    """Global test configuration wrapper."""

    def __init__(self, data):
        self._data = data

    @property
    def shares(self):
        return self._data['smb_shares']

    @property
    def username(self):
        users = self._data.get('smb_users', [])
        if users and users[0] and (un := users[0].get('username')):
            return un
        return r'domain1\bwayne'

    @property
    def password(self):
        users = self._data.get('smb_users', [])
        if users and users[0] and (pw := users[0].get('password')):
            return pw
        return base64.b64decode(b'MTExNVJvc2Uu').decode()

    @property
    def server(self):
        nodes = self._data.get('smb_nodes', [])
        return SMBTestServer(nodes[0])

    @property
    def admin_node(self):
        return SMBTestServer(self._data.get('admin_node', {}))

    @property
    def ssh_user(self):
        uname = self.admin_node.ssh_user
        assert uname, 'no ssh_user found'
        return uname

    @property
    def ssh_admin_host(self):
        return self.admin_node.ip_address

    def clients(self):
        clients = self._data.get('client_nodes') or []
        return [SMBTestHost(node_info) for node_info in clients]

    @property
    def default_client(self):
        # ideally we check that this is *our* ip or name, but we'll just wing
        # it for now until we really need to check
        return self.clients()[0]

    @property
    def testdir(self):
        return self._data.get('testdir') or os.path.expanduser('~/cephtest')

    @property
    def params(self):
        return self._data.get('params') or {}


@contextlib.contextmanager
def connection(conf, share, username=None, password=None):
    """Return a PathWrapper connecting to the given share."""
    server = conf.server.ip_address
    port = conf.server.port
    username = conf.username if username is None else username
    password = conf.password if password is None else password

    session = smbclient.register_session(
        server=server,
        port=port,
        username=username,
        password=password,
    )

    # monkey patch
    acl_revision_cls = smbprotocol.security_descriptor.AclRevision
    r3 = None
    for attr in vars(acl_revision_cls):
        if attr.startswith('_'):
            continue
        if getattr(acl_revision_cls, attr, None) == 3:
            r3 = attr
    if not r3:
        r3 = 'ACL_REVISION_SAMBA'
        setattr(acl_revision_cls, r3, 3)

    try:
        spath = pathlib.PureWindowsPath(f'//{server}/{share}')
        yield PathWrapper(spath, session=session)
    finally:
        smbclient.delete_session(server, port)


class PathWrapper:
    """Object that wraps the share connection and path within the share to act
    similarly to a pathlib.Path.
    """

    def __init__(self, share_path, *, session, root=None):
        self.share_path = share_path
        self._session = session
        self._root = str(root if root else share_path)

    def _child(self, sub):
        return self.__class__(sub, session=self._session, root=self._root)

    def __truediv__(self, other):
        return self._child(self.share_path / other)

    @property
    def rel_path(self):
        return self.share_path.relative_to(self._root)

    def listdir(self, **kwargs):
        """List directory contents."""
        return smbclient.listdir(str(self.share_path), **kwargs)

    def mkdir(self, exist_ok=False):
        """Create a new directory."""
        # TODO: parents=False
        if exist_ok:
            try:
                return smbclient.mkdir(str(self.share_path))
            except OSError as err:
                code = getattr(err, 'ntstatus', None)
                if code == NtStatus.STATUS_OBJECT_NAME_COLLISION:
                    return
                raise
        return smbclient.mkdir(str(self.share_path))

    def rmdir(self):
        """Remove a directory."""
        return smbclient.rmdir(str(self.share_path))

    def open(self, mode='r'):
        """Open a file."""
        return smbclient.open_file(str(self.share_path), mode=mode)

    def read_text(self):
        """Open the file in text mode, read it, and close the file."""
        with self.open() as fh:
            return fh.read()

    def write_text(self, txt):
        """Open the file in text mode, write to it, and close the file."""
        with self.open(mode='w') as fh:
            fh.write(txt)

    def write_bytes(self, data):
        """Open the file in binary mode, write bytes to it, and close the file."""
        with self.open(mode='wb') as fh:
            fh.write(data)

    def unlink(self):
        """Unlink (remove) a file."""
        smbclient.remove(str(self.share_path))

    def _tree_connect(self):
        # sn = self._root.rsplit('\\', 1)[-1] or '\\'
        sn = self._root
        while sn[-1] == '\\':
            sn = sn[:-1]
        print('SN', sn)
        for tc in self._session.tree_connect_table.values():
            if sn in tc.share_name.lower():
                return tc, True
        tc = smbprotocol.tree.TreeConnect(self._session, sn)
        tc.connect()
        assert tc.tree_connect_id in self._session.tree_connect_table
        return tc, False

    def get_security_descriptor(self):
        tc, _ = self._tree_connect()
        _open = smbprotocol.open
        x = str(self.rel_path)
        if x == '.':
            x = ''
        with contextlib.closing(_open.Open(tc, x)) as opath:
            opath.create(
                impersonation_level=_open.ImpersonationLevel.Impersonation,
                desired_access=_open.DirectoryAccessMask.READ_CONTROL,
                file_attributes=0,
                share_access=(
                    _open.ShareAccess.FILE_SHARE_READ
                    | _open.ShareAccess.FILE_SHARE_WRITE
                ),
                create_disposition=_open.CreateDisposition.FILE_OPEN,
                create_options=0,
            )
            req = _open.SMB2QueryInfoRequest()
            req['info_type'] = _open.InfoType.SMB2_0_INFO_SECURITY
            req['file_id'] = opath.file_id
            req["additional_information"] = (
                _open.InfoAdditionalInformation.OWNER_SECURTIY_INFORMATION
                | _open.InfoAdditionalInformation.GROUP_SECURITY_INFORMATION
                | _open.InfoAdditionalInformation.DACL_SECURITY_INFORMATION
            )
            req["output_buffer_length"] = 65536

            # Send request and receive response
            _conn = tc.session.connection
            request = _conn.send(
                req, tc.session.session_id, tc.tree_connect_id
            )
            response = _conn.receive(request)

            qr = _open.SMB2QueryInfoResponse()
            qr.unpack(response["data"].get_value())

            sd = smbprotocol.security_descriptor.SMB2CreateSDBuffer()
            sd.unpack(qr["buffer"].get_value())

        return SecurityDescriptor.load(sd)

    def set_security_descriptor(self, sd):
        tc, _ = self._tree_connect()
        _open = smbprotocol.open
        x = str(self.rel_path)
        if x == '.':
            x = ''

        smb_sd = smbprotocol.security_descriptor.SMB2CreateSDBuffer()
        assert not sd.owner, "not supported"
        assert not sd.group, "not supported"
        smb_sd["control"].set_flag(
            smbprotocol.security_descriptor.SDControl.SELF_RELATIVE
        )
        smb_sd.set_dacl(sd.d_acl_to_protocol())

        with contextlib.closing(_open.Open(tc, x)) as opath:
            opath.create(
                impersonation_level=_open.ImpersonationLevel.Impersonation,
                desired_access=_open.DirectoryAccessMask.WRITE_DAC,
                file_attributes=0,
                share_access=(
                    _open.ShareAccess.FILE_SHARE_READ
                    | _open.ShareAccess.FILE_SHARE_WRITE
                ),
                create_disposition=_open.CreateDisposition.FILE_OPEN,
                create_options=0,
            )
            req = _open.SMB2SetInfoRequest()
            req['info_type'] = _open.InfoType.SMB2_0_INFO_SECURITY
            req['file_id'] = opath.file_id
            req["additional_information"] = (
                _open.InfoAdditionalInformation.DACL_SECURITY_INFORMATION
            )
            req["buffer"] = smb_sd

            # Send request and receive response
            _conn = tc.session.connection
            request = _conn.send(
                req, tc.session.session_id, tc.tree_connect_id
            )
            response = _conn.receive(request)
            print(response)
        return





class ACEType(enum.Enum):
    ALLOW = 0x00
    DENY = 0x01
    AUDIT = 0x02

class _flagsEnum(enum.Enum):
    @classmethod
    def parse(cls, value):
        _flags = []
        for flag in cls:
            if flag.value & value == flag.value:
                _flags.append(flag.name)
        return _flags

    @classmethod
    def join(cls, value):
        _flags = cls.parse(value)
        if not _flags:
            return '0'
        return '|'.join(sorted(_flags))

    def __or__(self, other):
        if isinstance(other, _flagsEnum):
            other = other.value
        return self.value | int(other)


class ACEFlags(enum.Enum):
    OBJECT_INHERIT = 0x01
    CONTAINER_INHERIT = 0x02
    NO_PROPAGATE_INHERIT = 0x04
    INHERIT_ONLY = 0x08
    INHERITED_ACE = 0x10
    VALID_INHERIT = 0x0f
    SUCCESSFUL_ACCESS = 0x40
    FAILED_ACCESS = 0x80


class ShortACEFlags(_flagsEnum):
    "Compatible with flags emitted by smbcacls"
    OI = ACEFlags.OBJECT_INHERIT.value
    CI = ACEFlags.CONTAINER_INHERIT.value
    NP = ACEFlags.NO_PROPAGATE_INHERIT.value
    IO = ACEFlags.INHERIT_ONLY.value
    ID = ACEFlags.INHERITED_ACE.value
    SA = ACEFlags.SUCCESSFUL_ACCESS.value
    FA = ACEFlags.FAILED_ACCESS.value


class AccessMask(_flagsEnum):
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    GENERIC_EXECUTE = 0x20000000
    GENERIC_ALL = 0x10000000
    MAXIMUM_ALLOWED = 0x02000000
    ACCESS_SYSTEM_SECURITY = 0x01000000
    SYNCHRONIZE = 0x00100000
    WRITE_OWNER = 0x00080000
    WRITE_DACL = 0x00040000
    READ_CONTROL = 0x00020000
    DELETE = 0x00010000

    @classmethod
    def join(cls, value):
        full = 0x001f01ff
        if full & value == full:
            return 'FULL'
        return super(AccessMask, cls).join(value)


class ACE:
    def __init__(self, *, ace_type, ace_flags, mask, sid):
        self.ace_type = ace_type
        self.ace_flags = ace_flags
        self.mask = mask
        self.sid = sid

    @classmethod
    def load(cls, smb_ace):
        ace_type = ACEType(smb_ace["ace_type"].get_value())
        ace_flags = smb_ace["ace_flags"].get_value()
        mask = smb_ace["mask"].get_value()
        sid = str(smb_ace["sid"])
        return cls(ace_type=ace_type, ace_flags=ace_flags, mask=mask, sid=sid)

    def __str__(self):
        return (
            f'{self.__class__.__name__}('
            f'ace_type={self.ace_type!r},'
            f' ace_flags={ShortACEFlags.join(self.ace_flags)},'
            f' mask={AccessMask.join(self.mask)},'
            f' sid={self.sid!r}'
            ')'
        )

    __repr__ = __str__

    def to_protocol(self):
        if self.ace_type is ACEType.ALLOW:
            ace = smbprotocol.security_descriptor.AccessAllowedAce()
        else:
            ace = smbprotocol.security_descriptor.AccessDeniedAce()
        ace["ace_flags"] = int(self.ace_flags)
        ace["mask"] = int(self.mask)
        p_sid = smbprotocol.security_descriptor.SIDPacket()
        p_sid.from_string(self.sid)
        ace["sid"] = p_sid
        return ace


class SecurityDescriptor:
    def __init__(self, *, owner, group, d_acl=None, s_acl=None):
        self.owner = owner
        self.group = group
        self.d_acl = d_acl
        self.s_acl = s_acl

    @classmethod
    def load(cls, smb_sd):
        owner = str(smb_sd.get_owner())
        group = str(smb_sd.get_group())
        dacl = smb_sd.get_dacl()
        unpacked_d_acl = [ACE.load(a) for a in dacl['aces']]
        return cls(owner=owner, group=group, d_acl=unpacked_d_acl)

    def __str__(self):
        assert not self.s_acl
        return (
            f'{self.__class__.__name__}(owner={self.owner!r},'
            f' group={self.group!r},'
            f' d_acl={self.d_acl!r},'
            '...)'
        )

    def d_acl_to_protocol(self):
        acl = smbprotocol.security_descriptor.AclPacket()
        acl["aces"] = [a.to_protocol() for a in self.d_acl]
        return acl


def _get_resources(smb_cfg, rtype):
    jres = cephutil.cephadm_shell_cmd(
        smb_cfg,
        ["ceph", "smb", "show", "--results=full", rtype],
        load_json=True,
    )
    assert jres.obj
    obj = jres.obj
    assert 'resources' in obj
    resources = obj['resources']
    assert len(resources) > 0
    return resources


def get_shares(smb_cfg):
    """Get all SMB shares."""
    resources = _get_resources(smb_cfg, "ceph.smb.share")
    assert all(r['resource_type'] == 'ceph.smb.share' for r in resources)
    return resources


def get_ug(smb_cfg):
    """Get all users and groups resources."""
    resources = _get_resources(smb_cfg, "ceph.smb.usersgroups")
    assert all(r['resource_type'] == 'ceph.smb.usersgroups' for r in resources)
    return resources


def get_share_by_id(smb_cfg, cluster_id, share_id):
    """Get a specific share by cluster_id and share_id."""
    shares = _get_resources(smb_cfg, f"ceph.smb.share.{cluster_id}.{share_id}")
    assert len(shares) == 1
    share = shares[0]
    assert share['cluster_id'] == cluster_id and share['share_id'] == share_id
    return share


def _apply(smb_cfg, resources, immediate=False, check=None, load_json=True):
    jres = cephutil.cephadm_shell_cmd(
        smb_cfg,
        ['ceph', 'smb', 'apply', '-i-'],
        input_json={'resources': resources},
        load_json=load_json,
    )
    if check:
        ret = check(jres)
    else:
        ret = jres
    # sleep to ensure the settings got applied in smbd
    # TODO: make this more dynamic somehow
    if not immediate:
        time.sleep(60)
    return ret


def _res_check(jres):
    assert jres.returncode == 0
    assert jres.obj and jres.obj.get('success')
    assert 'results' in jres.obj
    _results = jres.obj['results']
    assert len(_results) == 1, "more than one result found"
    _result = _results[0]
    assert 'resource' in _result
    resources_ret = _result['resource']
    return resources_ret


def apply_share_config(smb_cfg, share, immediate=False):
    """Apply share configuration via the apply command."""

    def _check(jres):
        resources_ret = _res_check(jres)
        assert resources_ret['resource_type'] == 'ceph.smb.share'
        return resources_ret

    rr = _apply(smb_cfg, [share], immediate=immediate, check=_check)
    return rr


def apply_resource(
    smb_cfg,
    resource,
    immediate=False,
):
    """Apply a single generic resource via the apply command."""

    rr = _apply(smb_cfg, [resource], immediate=immediate, check=_res_check)
    return rr


def _res_check_many(jres, count):
    assert jres.returncode == 0
    assert jres.obj and jres.obj.get('success')
    assert 'results' in jres.obj
    _results = jres.obj['results']
    assert len(_results) == count
    return jres.obj


def apply_resources(
    smb_cfg,
    resources,
    immediate=False,
):
    """Apply resources via the apply command."""

    _check = functools.partial(_res_check_many, count=len(resources))
    rr = _apply(smb_cfg, resources, immediate=immediate, check=_check)
    return rr


def apply_resources_unchecked(
    smb_cfg,
    resources,
    immediate=False,
):
    """Apply resources via the apply command. Do not assert result is OK."""

    return _apply(
        smb_cfg,
        resources,
        immediate=immediate,
        load_json=cephutil.LoadJSON.BOTH,
    )
