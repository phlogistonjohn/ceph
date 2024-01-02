import sys

from typing import TYPE_CHECKING, Dict, Any, List, Tuple, Collection, Iterator


# this uses a version check as opposed to a try/except because this
# form makes mypy happy and try/except doesn't.
if sys.version_info >= (3, 8):
    from typing import Protocol
elif TYPE_CHECKING:  # pragma: no cover
    # typing_extensions will not be available for the real mgr server
    from typing_extensions import Protocol
else:  # pragma: no cover
    # fallback type that is acceptable to older python on prod. builds
    class Protocol:  # type: ignore
        pass


Simplified = Dict[str, Any]
SimplifiedList = List[Simplified]


class ConfigResource(Protocol):
    def read(self) -> str:
        ...  # pragma: no cover

    def write(self, content: str) -> None:
        ...  # pragma: no cover

    @property
    def uri(self) -> str:
        ...  # pragma: no cover


class ConfigStore(Protocol):
    def __getitem__(self, key: Tuple[str, str]) -> ConfigResource:
        ...  # pragma: no cover

    def namespaces(self) -> Collection[str]:
        ...  # pragma: no cover

    def contents(self, ns: str) -> Collection[str]:
        ...  # pgrama: no cover

    def __iter__(self) -> Iterator[Tuple[str, str]]:
        ...  # pragma: no cover
