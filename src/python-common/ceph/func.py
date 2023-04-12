
from typing import List, Dict, Any, Callable, Tuple, Optional, Union
from typing import NamedTuple
import inspect


class HandleCommandResult(NamedTuple):
    """
    Tuple containing the result of `handle_command()`

    Only write to stderr if there is an error, or in extraordinary circumstances

    Avoid having `ceph foo bar` commands say "did foo bar" on success unless there
    is critical information to include there.

    Everything programmatically consumable should be put on stdout
    """
    retval: int = 0             # return code. E.g. 0 or -errno.EINVAL
    stdout: str = ""            # data of this result.
    stderr: str = ""            # Typically used for error messages.


HandlerFuncType = Callable[..., Tuple[int, str, str]]

class CephCLIFunction:
    """CephCLIFunction objects represent callables that can be invoked
    using the MGRs command handling functionality. This object encapsulates
    the parameters that can be provided when the function is called
    as a JSON/cli interface.
    """
    def __init__(
        self,
        func: HandlerFuncType,
        prefix: str,
        perm: str,
        poll: bool
    ):
        self.func = func
        self.prefix = prefix
        self.perm = perm
        self.poll = poll

        self._supports_inbuf = False
        self._desc = ""
        self._process()

    def _process(self):
        f, extra_args = _extract_target_func(self.func)
        self._desc = (inspect.getdoc(f) or '').replace('\n', ' ')
        sig = inspect.signature(f)
        positional = True
        self._ceph_args = []
        for param in sig.parameters.values():
            print("XXX", param, param.kind)
            if self._ignore(param):
                continue
            if (param.kind == param.KEYWORD_ONLY
                or param.kind == param.VAR_KEYWORD
                or param.name == 'format'
                or param.annotation is Optional[bool]
                or param.annotation is bool):
                positional = False
            print("XX2", param, param.kind)
            self._ceph_args.append(self._param_info(param, positional))
        print("CC", self._ceph_args)


    def _ignore(self, param: inspect.Parameter) -> bool:
        return (param.name in ["_", "self"]
                or param.kind == param.VAR_KEYWORD
                or param.kind == param.VAR_POSITIONAL)

    def _param_info(self, param: inspect.Parameter, positional: bool):
       if param.annotation is param.empty:
           raise ValueError(f"type annotation required for {param.name}")


    def apply(
        self,
        args: List[Any],
        inbuf: Optional[str],
        cmd: Dict[str, Any]
    ) -> Union[HandleCommandResult, Tuple[int, str, str]]:
        assert self.func
        kwargs = self._cmd_to_kwargs(cmd)
        if inbuf:
            if not self.supports_inbuf:
                return -errno.EINVAL, '', 'Invalid command: Input file data (-i) not supported'
            kwargs['inbuf'] = inbuf
        return self.func(*args, **kwargs)

    def dump_cmd(self) -> Dict[str, Union[str, bool]]:
        return {
            'cmd': '{} {}'.format(self.prefix, self.ceph_arg_spec()),
            'desc': self.desc,
            'perm': self.perm,
            'poll': self.poll,
        }


def _extract_target_func(
    f: HandlerFuncType
) -> Tuple[HandlerFuncType, Dict[str, Any]]:
    """In order to interoperate with other decorated functions,
    we need to find the original function which will provide
    the main set of arguments. While we descend through the
    stack of wrapped functions, gather additional arguments
    the decorators may want to provide.
    """
    # use getattr to keep mypy happy
    wrapped = getattr(f, "__wrapped__", None)
    if not wrapped:
        return f, {}
    extra_args: Dict[str, Any] = {}
    while wrapped is not None:
        extra_args.update(getattr(f, "extra_args", {}))
        f = wrapped
        wrapped = getattr(f, "__wrapped__", None)
    return f, extra_args



def foobar(speed: int, location: str = 'home', inbuf: Optional[str] = None):
    pass
CephCLIFunction(foobar, "foobar", "rw", False)

def foobar2():
    pass
CephCLIFunction(foobar2, "foobar", "rw", False)

def foobar3(*args, **kwargs):
    pass
CephCLIFunction(foobar3, "foobar", "rw", False)

def foobar4(dippy: str, /, snail: int, warp: Optional[str]=None):
    pass
CephCLIFunction(foobar4, "foobar", "rw", False)

def foobar5(rip:str, *, tear: Optional[bool]=None):
    pass
CephCLIFunction(foobar5, "foobar", "rw", False)

class Doop:
    def foobar(self, cheese: str, cats: int):
        pass
CephCLIFunction(Doop.foobar, "foobar", "rw", False)
