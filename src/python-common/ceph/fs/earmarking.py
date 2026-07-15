"""
Module: CephFS Volume Earmarking

This module provides the `CephFSVolumeEarmarking` class, which is designed to manage the earmarking
of subvolumes within a CephFS filesystem. The earmarking mechanism allows
administrators to tag specific subvolumes with identifiers that indicate their intended use
such as NFS or SMB, ensuring that only one file service is assigned to a particular subvolume
at a time. This is crucial to prevent data corruption in environments where
mixed protocol support (NFS and SMB) is not yet available.

Key Features:
- **Set Earmark**: Assigns an earmark to a subvolume.
- **Get Earmark**: Retrieves the existing earmark of a subvolume, if any.
- **Remove Earmark**: Removes the earmark from a subvolume, making it available for reallocation.
- **Validate Earmark**: Ensures that the earmark follows the correct format and only uses
supported top-level scopes.
"""

import base64
import sys
import errno
import enum
import logging
import uuid

from typing import (
    Any,
    Dict,
    List,
    NamedTuple,
    Optional,
    Protocol,
    TYPE_CHECKING,
    Tuple,
    Type,
    Union,
    cast,
)

if sys.version_info >= (3, 11):  # pragma: no cover
    from typing import Self
elif TYPE_CHECKING:  # pragma: no cover
    from typing_extensions import Self
else:  # pragma: no cover
    # fallback type that should be ignored at runtime
    Self = Any  # type: ignore

log = logging.getLogger(__name__)

XATTR_SUBVOLUME_EARMARK_NAME = 'user.ceph.subvolume.earmark'


class EarmarkTopScope(enum.Enum):
    MIXED = "mixed"
    NFS = "nfs"
    SMB = "smb"


class FSOperations(Protocol):
    """Protocol class representing the file system operations earmarking
    classes will perform.
    """

    def setxattr(
        self, path: str, key: str, value: bytes, flags: int
    ) -> None: ...

    def getxattr(self, path: str, key: str) -> bytes: ...


class EarmarkContents(Protocol):
    @property
    def top(self) -> EarmarkTopScope: ...

    @property
    def subsections(self) -> List[str]: ...

    def __str__(self) -> str: ...

    def upgrades(self, other: 'EarmarkContents') -> bool: ...

    @classmethod
    def parse(cls, value: str) -> Self: ...


class EarmarkError(Exception):
    pass


class EarmarkException(EarmarkError):
    def __init__(self, error_code: int, error_message: str) -> None:
        self.errno = error_code
        self.error_str = error_message

    def to_tuple(self) -> Tuple[int, Optional[str], str]:
        return self.errno, "", self.error_str

    def __str__(self) -> str:
        return f"{self.errno} ({self.error_str})"


class EarmarkParseError(ValueError, EarmarkError):
    pass


class EarmarkConflictError(EarmarkError):
    def __init__(
        self, msg: str, current: Any = None, wanted: Any = None
    ) -> None:
        super().__init__(msg)
        self.current_earmark = current
        self.wanted_earmark = wanted


class NFSEarmark(NamedTuple):
    top: EarmarkTopScope
    # to be backwards compatible we allow freeform subsections in nfs
    # (for now) but we may want to get stricter about this in the
    # future since this is never used in practice
    subsections: List[str]

    def __str__(self) -> str:
        return f'{self.top.value}'

    @classmethod
    def parse(cls, value: str) -> Self:
        """Given an earmark string, return a new NFSEarmark object or raise an
        EarmarkParseError if the string is not a valid nfs earmark.
        """
        parts = value.split('.')
        if parts[0] != EarmarkTopScope.NFS.value:
            raise EarmarkParseError(
                f'wrong top scope for NFS earmark: {value!r}'
            )
        for part in parts[1:]:
            if not part:
                raise EarmarkParseError(
                    f'empty subsection in NFS earmark: {value!r}'
                )
        return cls(EarmarkTopScope.NFS, parts[1:])

    @classmethod
    def default(cls) -> Self:
        """Return a new NFSEarmark with default values."""
        return cls(EarmarkTopScope.NFS, [])

    def __eq__(self, other: Any) -> bool:
        """Equality check."""
        if isinstance(other, str):
            try:
                _other = self.parse(other)
            except EarmarkParseError:
                return False
        elif isinstance(other, self.__class__):
            _other = other
        else:
            return NotImplemented
        return (
            self.top is _other.top and self.subsections == _other.subsections
        )

    def upgrades(self, current: EarmarkContents) -> bool:
        """Returns true if this earmark can be used to upgrade the current
        earmark value applied to some path.
        """
        if self.top != current.top:
            raise EarmarkConflictError(
                f'earmark has already been set by {current.top.value}',
                current,
                self,
            )
        # No need to upgrade nfs at this time
        return False


class SMBEarmark(NamedTuple):
    top: EarmarkTopScope
    cluster_id: str

    @property
    def subsections(self) -> List[str]:
        """Return earmark subsections as a list of strings."""
        return [] if not self.cluster_id else ['cluster', self.cluster_id]

    def __str__(self) -> str:
        earmark = f'{self.top.value}'
        if self.cluster_id:
            earmark = f'{earmark}.cluster.{self.cluster_id}'
        return earmark

    @classmethod
    def parse(cls, value: str) -> Self:
        """Given an earmark string, return a new SMBEarmark object or raise an
        EarmarkParseError if the string is not a valid smb earmark.
        """
        cid = ''
        parts = value.split('.')
        if parts[0] != EarmarkTopScope.SMB.value:
            raise EarmarkParseError(
                f'wrong top scope for SMB earmark: {value!r}'
            )
        if len(parts) > 3:
            raise EarmarkParseError(
                f'too many subsections for SMB earmark: {value!r}'
            )
        elif len(parts) == 3:
            cflag, cid = parts[1:]
            if cflag != 'cluster' or not cid:
                raise EarmarkParseError(
                    f'invalid subsection in SMB earmark: {value!r}'
                )
        elif len(parts) == 2:
            raise EarmarkParseError(
                f'too few subsections for SMB earmark: {value!r}'
            )
        return cls(EarmarkTopScope.SMB, cid)

    @classmethod
    def from_cluster_id(cls, cluster_id: str) -> Self:
        """Given an smb cluster_id, return a new SMBEarmark object."""
        return cls(EarmarkTopScope.SMB, cluster_id)

    def __eq__(self, other: Any) -> bool:
        """Equality check."""
        if isinstance(other, str):
            try:
                _other = self.parse(other)
            except EarmarkParseError:
                return False
        elif isinstance(other, self.__class__):
            _other = other
        else:
            return NotImplemented
        return self.top is _other.top and self.cluster_id == _other.cluster_id

    def upgrades(self, current: EarmarkContents) -> bool:
        """Returns true if this earmark can be used to upgrade the current
        earmark value applied to some path.
        """
        if self.top != current.top:
            raise EarmarkConflictError(
                f'earmark has already been set by {current.top.value}',
                current,
                self,
            )
        ce = cast(SMBEarmark, current)
        if not ce.cluster_id:
            return True
        if ce.cluster_id == self.cluster_id:
            return False
        raise EarmarkConflictError(
            f'earmark has already been set by smb cluster {ce.cluster_id}',
            current,
            self,
        )


class Proto(enum.Enum):
    NFS = 'nfs'
    SMB = 'smb'


class PseduoUSSID(enum.Enum):
    NEW = 'NEW'
    ANY = 'ANY'


class EarmarkVersion(NamedTuple):
    version: int
    level: str
    revision: int

    def __str__(self) -> str:
        return f'v{self.version}{self.level}{self.revision}'

    @classmethod
    def parse(cls, value: str) -> Self:
        if value[0] != 'v':
            raise EarmarkParseError(
                f'invalid version: {value!r}: missing prefix'
            )
        rest = value[1:]
        pos = -1
        for sep in ('a', 'b', 'r'):
            pos = rest.find(sep)
            if pos > 0:
                break
        if pos < 0:
            raise EarmarkParseError(
                f'invalid version: {value!r}: missing level'
            )
        v, l, r = rest[:pos], rest[pos], rest[pos + 1 :]
        if not v.isdigit():
            raise EarmarkParseError(
                f'invalid version: {value!r}: invalid version number'
            )
        if not r.isdigit():
            raise EarmarkParseError(
                f'invalid version: {value!r}: invalid revision number'
            )
        ev = cls(int(v), l, int(r))
        try:
            ev.check()
        except ValueError as err:
            raise EarmarkParseError(f'invalid version: {value!r}: {err}')
        return ev

    def check(self):
        if not (isinstance(self.version, int) and self.version >= 0):
            raise ValueError("invalid version number")
        if not (isinstance(self.revision, int) and self.revision >= 0):
            raise ValueError("invalid revision number")
        if self.level not in ('a', 'b', 'r'):
            raise ValueError("invalid level")


class MixedProtoEarmark(NamedTuple):
    top: EarmarkTopScope
    version: EarmarkVersion
    protos: Tuple[Proto]
    ussid: Union[uuid.UUID, PseduoUSSID]

    def _version_str(self) -> str:
        return str(self.version)

    def _protos_str(self) -> str:
        return '_'.join(sorted(p.value for p in self.protos))

    def _ussid_str(self) -> str:
        if isinstance(self.ussid, PseduoUSSID):
            return self.ussid.value
        return base64.b64encode(self.ussid.bytes, _B64ALT)[:-2].decode()

    @property
    def subsections(self) -> List[str]:
        """Return earmark subsections as a list of strings."""
        return [self._version_str(), self._protos_str(), self._ussid_str()]

    def __str__(self) -> str:
        out = [self.top.value] + self.subsections
        assert not any('.' in p for p in out)
        return '.'.join(out)

    @classmethod
    def parse(cls, value: str) -> Self:
        """Given an earmark string, return a new SMBEarmark object or raise an
        EarmarkParseError if the string is not a valid smb earmark.
        """
        cid = ''
        parts = value.split('.')
        if parts[0] != EarmarkTopScope.MIXED.value:
            raise EarmarkParseError(
                f'wrong top scope for mixed earmark: {value!r}'
            )
        if len(parts) < 2:
            raise EarmarkParseError(
                f'missing version in mixed earmark: {value!r}'
            )
        version = EarmarkVersion.parse(parts[1])
        if len(parts) < 4:
            raise EarmarkParseError(
                f'missing subsections in mixed earmark: {value!r}'
            )
        protos = [Proto(p) for p in parts[2].split('_')]
        if parts[3] in (PseduoUSSID.NEW.value, PseduoUSSID.ANY.value):
            ussid = PseduoUSSID(parts[3])
        else:
            bss = parts[3].encode() + b'=='
            try:
                ussid = uuid.UUID(bytes=base64.b64decode(bss, _B64ALT))
            except ValueError:
                raise EarmarkParseError(
                    f'invalid ussid in mixed earmark: {value!r}'
                )
        mpe = cls(EarmarkTopScope.MIXED, version, protos, ussid)
        try:
            mpe.check()
        except ValueError as err:
            raise EarmarkParseError(str(err))
        return mpe

    @classmethod
    def from_ussid(
        cls,
        ussid: Union[uuid.UUID, PseduoUSSID],
        protos: Optional[Tuple[Proto]] = None,
    ) -> Self:
        """Given an smb cluster_id, return a new SMBEarmark object."""
        if not protos:
            protos = (Proto.NFS, Proto.SMB)
        mpe = cls(EarmarkTopScope.MIXED, _known_versions[-1], protos, ussid)
        mpe.check()
        return mpe

    def check_version(self) -> None:
        if self.version not in _known_versions:
            raise ValueError('unknown version')

    def check_protos(self) -> None:
        for _proto in self.protos:
            if _proto not in Proto:
                raise ValueError(f'invalid protocol value: {_proto}')
        if list(self.protos) != sorted(self.protos, key=lambda p: p.value):
            raise ValueError('incorrect proto ordering')

    def check(self) -> None:
        self.check_version()
        self.check_protos()

    def __eq__(self, other: Any) -> bool:
        """Equality check."""
        if isinstance(other, str):
            try:
                _other = self.parse(other)
            except EarmarkParseError:
                return False
        elif isinstance(other, self.__class__):
            _other = other
        else:
            return NotImplemented
        return (
            self.top is _other.top
            and self.version == _other.version
            and self.protos == _other.protos
            and self.ussid == _other.ussid
        )

    def upgrades(self, current: EarmarkContents) -> bool:
        """Returns true if this earmark can be used to upgrade the current
        earmark value applied to some path.
        """
        # TODO: allow upgrading "smb" earmarks (no cluster assigned) and nfs
        # earmarks ?
        if self.top != current.top:
            raise EarmarkConflictError(
                f'earmark has already been set by {current.top.value}',
                current,
                self,
            )
        ce = cast(MixedProtoEarmark, current)
        # version check
        if self.version < current.version:
            raise EarmarkConflictError(
                f'can not downgrade earmark', current, self
            )
        if self.protos != current.protos:
            raise EarmarkConflictError(
                f'can not change protocols for current earmark', current, self
            )
        if self.ussid is PseduoUSSID.NEW:
            return True
        raise EarmarkConflictError(
            f'earmark has already been assigned a unique security settings ID',
            current,
            self,
        )


_B64ALT = b'-_'

_proto_versions: Dict[Proto, EarmarkVersion] = {
    Proto.NFS: EarmarkVersion(0, "a", 0),
    Proto.SMB: EarmarkVersion(0, "a", 0),
}
_known_versions: List[EarmarkVersion] = [EarmarkVersion(0, 'a', 0)]

_earmark_types: Dict[EarmarkTopScope, Type[EarmarkContents]] = {
    EarmarkTopScope.NFS: NFSEarmark,
    EarmarkTopScope.SMB: SMBEarmark,
    EarmarkTopScope.MIXED: MixedProtoEarmark,
}


def parse_earmark(value: str) -> Optional[EarmarkContents]:
    """Given an earmark string return an EarmarkContents object from
    parsing the string. If the value is empty return None.
    If the value can not be parsed raise EarmarkParseError.
    """
    if not value:
        return None
    _top = value.split('.', 1)[0]
    try:
        top = EarmarkTopScope(_top)
    except ValueError:
        raise EarmarkParseError(f"Invalid top-level scope: {_top}")
    return _earmark_types[top].parse(value)


class CephFSVolumeEarmarking:
    def __init__(self, fs: FSOperations, path: str) -> None:
        self.fs = fs
        self.path = path

    def _handle_cephfs_error(
        self, e: Exception, action: str
    ) -> Optional[str]:
        if isinstance(e, ValueError):
            raise EarmarkException(
                errno.EINVAL, f"Invalid earmark specified: {e}"
            ) from e
        elif isinstance(e, OSError):
            if e.errno == errno.ENODATA:
                # Return empty string when earmark is not set
                log.info(
                    f"No earmark set for the path while {action}. Returning empty result."
                )
                return ''
            else:
                raise EarmarkException(-e.errno, e.strerror) from e
        else:
            raise EarmarkException(
                errno.EFAULT, f"Unexpected error {action} earmark: {e}"
            ) from e

    def _validate_earmark(self, earmark: Union[str, EarmarkContents]) -> bool:
        """
        Validates the earmark. If the earmark is a string, it will be parsed
        and checked.

        :param earmark: The earmark string to validate.
        :return: True if valid, False otherwise.
        """
        if not isinstance(earmark, str):
            return True
        try:
            parse_earmark(earmark)
        except EarmarkParseError:
            return False
        return True

    def get_earmark(self) -> Optional[str]:
        """Get an earmark string or None if no earmark is set on the current
        path.
        """
        try:
            earmark_value = self.fs.getxattr(
                self.path, XATTR_SUBVOLUME_EARMARK_NAME
            ).decode('utf-8')
            return earmark_value
        except Exception as e:
            return self._handle_cephfs_error(e, "getting")

    def get_parsed_earmark(self) -> Optional[EarmarkContents]:
        """Get a parsed earmark object or None if no earmark is set on the
        current path.
        """
        earmark_value = self.get_earmark()
        if earmark_value is None:
            return None
        return parse_earmark(earmark_value)

    def set_earmark(self, earmark: Union[str, EarmarkContents]) -> None:
        """Set the given earmark value on the current path."""
        # Validate the earmark before attempting to set it
        if not self._validate_earmark(earmark):
            raise EarmarkException(
                errno.EINVAL,
                f"Invalid earmark specified: '{earmark}'. "
                "A valid earmark should either be empty or start with 'nfs' or 'smb', "
                "followed by dot-separated non-empty components or simply set "
                "'smb.cluster.{cluster_id}' for the smb intra-cluster scope.",
            )

        try:
            self.fs.setxattr(
                self.path,
                XATTR_SUBVOLUME_EARMARK_NAME,
                str(earmark).encode('utf-8'),
                0,
            )
            log.info(f"Earmark '{earmark}' set on {self.path}.")
        except Exception as e:
            self._handle_cephfs_error(e, "setting")

    def clear_earmark(self) -> None:
        """Remove the earmark value from the current path."""
        self.set_earmark("")

    def test_and_set(
        self, earmark: EarmarkContents
    ) -> Tuple[bool, Optional[EarmarkContents]]:
        """Perform a test-and-set operation on the earmark value for the given
        path. If the new earmark is accepted the function returns (True, <new
        earmark>), if the earmark does not need updating the function return
        (False, <current earmark>). If the earmark is not compatible raise an
        EarmarkConflictError exception.
        """
        current = self.get_parsed_earmark()
        if not _upgrade_earmark(current, earmark):
            return False, current
        self.set_earmark(earmark)
        return True, earmark


def _upgrade_earmark(
    current: Optional[EarmarkContents],
    wanted: EarmarkContents,
) -> bool:
    """Given two earmarks, current and wanted, return True if the wanted
    earmark is an "upgrade" from the current earmark.
    If the current earmark is None/falsey then the earmark may be upgraded.
    If the earmarks are equal they do not need to be upgraded (returns false).
    Otherwise, the `upgrades` method of the wanted earmark will be passed
    the current earmark.
    This function will raise a EarmarkConflictError if the earmarks are
    totally incompatible.
    """
    if not current:
        return True
    if current == wanted:
        return False
    return wanted.upgrades(current)
