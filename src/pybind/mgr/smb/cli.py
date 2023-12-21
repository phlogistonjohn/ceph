from typing import Any, Callable

from mgr_module import CLICommand
import object_format


class _cmdlet:
    def __init__(self, func: Callable, cmd: Callable) -> None:
        self._func = func
        self.command = cmd

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._func(*args, **kwargs)


class Command:
    """A combined decorator and descriptor. Sets up the common parts of the
    CLICommand and object formatter.
    As a descriptor, it returns objects that can be called and wrap the
    "normal" function but also have a `.command` attribute so the CLI wrapped
    version can also be used under the same namespace.

    Example:
    >>> class Example:
    ...     @Command('share', 'foo', perm='r')
    ...     def foo(self):
    ...         return {'test': 1}
    ...
    >>> ex = Example()
    >>> assert ex.foo() == {'test': 1}
    >>> assert ex.foo.command(format='yaml') == (0, "test: 1\\n", "")
    """
    def __init__(self, scope: str, suffix: str, perm: str) -> None:
        self._scope = scope
        self._suffix = suffix
        self._perm = perm

    def __call__(self, func: Callable) -> 'Command':
        self._func = func
        cc = CLICommand(f'smb {self._scope} {self._suffix}', perm=self._perm)
        rsp = object_format.Responder()
        self._command = cc(rsp(func))
        return self

    def __get__(self, obj: Any, objtype: Any = None) -> _cmdlet:
        return _cmdlet(
            self._func.__get__(obj, objtype),
            self._command.__get__(obj, objtype),
        )
