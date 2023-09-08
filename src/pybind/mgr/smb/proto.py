import sys

from typing import TYPE_CHECKING, Dict, Any, List


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
