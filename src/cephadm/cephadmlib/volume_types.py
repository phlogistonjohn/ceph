# volume_types.py - container volume and mount types

from typing import List, Optional, Union, Tuple, Protocol, Iterable

import dataclasses
import enum
import os


class NamedVolume(Protocol):
    """Protocol object for any named volume."""

    @property
    def name(self) -> str:
        ...


class VolumeMount(Protocol):
    """Basic container volume/bind mounting protocol. Can be used to generate
    --volume/-v options for podman and docker.
    """

    def vol_mapping(self) -> Tuple[str, str]:
        ...

    def vol_flags(self) -> List[str]:
        ...


class FileSystemMount(Protocol):
    """Advanced container file system mounting protocol. Can be used to
    generate --mount options for podman and docker.
    """

    def fs_type(self) -> str:
        ...

    def fs_mount_options(self) -> List[Tuple[str, str]]:
        ...


Mountable = Union[VolumeMount, FileSystemMount]
MountSource = Union[str, os.PathLike, NamedVolume]
MountDestination = Union[str, os.PathLike]


class RelabelOpt(str, enum.Enum):
    """Used to specify if selinux relabeling should be done and how."""

    DEFAULT = ''  # no relabeling
    SHARED = 'z'
    PRIVATE = 'Z'


@dataclasses.dataclass
class VolumeSettings:
    """A volume object managed by podman/docker."""

    # name of the volume
    name: str
    # driver for the volume (empty string for default)
    driver: str = ''
    # volume_type specifies the fs/volume type (empty string for default)
    volume_type: str = ''
    # device or string controlling the fs source (empty string for default)
    device: str = ''
    # mount_options additional mount options for this volume
    mount_options: Optional[List[str]] = None


@dataclasses.dataclass
class Mount:
    """A basic mount for a podman/docker container."""

    # source can be a string, path, or named volume object
    source: MountSource
    # destination can be a string or path
    destination: MountDestination
    # read_only indicates if the container mount is read only
    read_only: bool = False
    # relabel indicates if selinux relabeling is needed
    relabel: RelabelOpt = RelabelOpt.DEFAULT
    # extra_options allows one to specify additional options not currently
    # supported by the type. If you use this a lot consider extending the
    # object
    extra_options: Optional[List[str]] = None

    def vol_mapping(self) -> Tuple[str, str]:
        """The source and destination pair."""
        if isinstance(self.source, os.PathLike) or isinstance(
            self.source, str
        ):
            src = str(self.source)
        else:
            src = self.source.name
        dst = str(self.destination)
        return src, dst

    def vol_flags(self) -> List[str]:
        """Volume flags."""
        flags = []
        if self.read_only:
            flags.append('ro')
        if self.relabel is not RelabelOpt.DEFAULT:
            flags.append(str(self.relabel.value))
        if self.extra_options:
            flags.extend(str(o) for o in self.extra_options)
        return flags


def mount_arguments(mounts: Iterable[Mountable]) -> List[str]:
    """Convert mountable objects into a list of arguments for podman/docker."""
    return [_mount_option(m) for m in mounts]


def _mount_option(mount: Mountable) -> str:
    _fs_type = getattr(mount, 'fs_type', None)
    _fs_mo = getattr(mount, 'fs_mount_options', None)
    if _fs_type and _fs_mo:
        # it is a FileSystemMount. use that style
        return _fs_mount_option(_fs_type(), _fs_mo())
    _vol_mapping = getattr(mount, 'vol_mapping', None)
    _vol_flags = getattr(mount, 'vol_flags', None)
    if _vol_mapping and _vol_flags:
        src, dst = _vol_mapping()
        return _vol_mount_option(src, dst, _vol_flags())
    raise TypeError(f'invalid mount option: {mount}')


def _fs_mount_option(
    fs_type: str, fs_mount_options: List[Tuple[str, str]]
) -> str:
    options = [('type', fs_type)]
    options.extend(fs_mount_options)
    args = ','.join(f'{k}={v}' for (k, v) in options)
    return f'--mount={args}'


def _vol_mount_option(src: str, dst: str, vol_flags: List[str]) -> str:
    _options = ''
    if vol_flags:
        _options = ':' + ','.join(vol_flags)
    return f'--volume={src}:{dst}{_options}'
