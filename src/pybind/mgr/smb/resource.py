from typing import Any, Dict, List, Optional, TypeVar, Type, Tuple, Generic, Annotated
import dataclasses
import enum

from .proto import Simplified

T = TypeVar('T')


try:
    from typing import get_args
except ImportError:
    def get_args(t: Any) -> Tuple:
        try:
            return t.__args__
        except AttributeError:
            return tuple()


@dataclasses.dataclass
class ResourceOptions:
    # embedded: combine the data for an object with that of its parent
    embedded: bool = False
    # keep_none: if true, none objects will appear in the simple data output.
    # if false, the value and key will be elided
    keep_none: bool = False
    # keep_false: if true, "falsy" objects will appear in the simple data output.
    # if false, the value and key will be elided
    keep_false: bool = True
    #
    alt_keys: Optional[List[str]] = None


class _typeinfo:
    def __init__(self, target_type: Any) -> None:
        print("TYPEINFO", target_type)
        self.target_type = target_type
        self._args = getattr(self.target_type, '__args__', None)
        self._origin = getattr(self.target_type, '__origin__', None)
        self._meta = getattr(self.target_type, '__metadata__', None)

    def is_optional(self) -> bool:
        return any(t is type(None) for t in self._args)

    def resource_opts(self) -> ResourceOptions:
        meta = self._meta or []
        try:
            return [a for a in meta if isinstance(a, ResourceOptions)][0]
        except IndexError:
            return ResourceOptions()

    def unwrap(self) -> '_typeinfo':
        if self._args is None:
            return self.__class__(self.target_type)
        nnt = [t for t in self._args if t is not type(None)][0]
        return self.__class__(nnt)

    def takes(self, *target_types: Any) -> bool:
        return self._origin in target_types

    def __repr__(self) -> str:
        return f'_typeinfo({self.target_type!r})'


class _Source:
    def __init__(self, data: Simplified, depth: int = 1) -> None:
        self.data = data
        self.depth = depth
        self.count = 1
        print('__SRC', self.data, self.depth)

    def __getitem__(self, key) -> Any:
        value = self.data[key]
        return self.__class__(value, self.depth + 1)

    def select(self, keys) -> Any:
        for key in keys:
            print('KEEEEYYY', key)
            try:
                return self[key]
            except KeyError:
                pass
        raise KeyError(keys[0])

    def reuse(self):
        self.count += 1
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.count -= 1
        print('__EXIT', self.depth, self.count)


def _assemble(type_info: _typeinfo, fname: str, source: _Source) -> Any:
    ropts = type_info.resource_opts()
    # determine if we're moving down the "tree" or not
    try:
        tgt = source.select([fname] + (ropts.alt_keys or []))
    except KeyError:
        if ropts.embedded:
            tgt = source.reuse()
        else:
            raise

    innert = type_info.unwrap()
    _as = getattr(innert.target_type, '_assemble_simplified', None)
    _fs = getattr(innert.target_type, 'from_simplified', None)
    with tgt:
        if _as:
            return _as(tgt)
        elif _fs:
            return _fs(tgt.data)
        if isinstance(tgt.data, list):
            assert innert.takes(list, List), f'invalid type: {itype!r}'
            return [_unsimplify(v, innert.target_type) for v in tgt.data]
        if isinstance(tgt.data, dict):
            # keys must be simple types
            assert innert.takes(dict, Dict), f'invalid type: {itype!r}'
            return {_unsimplify(k, None):_unsimplify(v, innert.target_type) for k, v in tgt.data.items()}
        if issubclass(innert.target_type, enum.Enum):
            return innert.target_type(tgt.data)
        if isinstance(tgt.data, (str, int, float)):
            return tgt.data
        if tgt.data is None and type_info.optional:
            return None
    raise TypeError(tgt.data)


def _assemble_simplified(cls: Type[T], src: _Source) -> T:
    kw = {}
    expected_rt = getattr(cls, 'resource_type', None)
    if expected_rt:
        print('resource_type=', expected_rt)
        try:
            curr_resource_type = src['resource_type'].data
        except KeyError:
            raise ValueError('missing resource type')
        if expected_rt != curr_resource_type:
            raise ValueError(f'unexpected resource type: {curr_resource_type!r}')

    for fld in dataclasses.fields(cls):
        print("MMM", fld.name)
        try:
            obj = _assemble(_typeinfo(fld.type), fld.name, src)
            kw[fld.name] = obj
        except KeyError:
            pass

    print("KW", kw)
    obj = cls(**kw)
    validate = getattr(obj, 'validate', None)
    if validate:
        validate()
    return obj


def _simplify(type_info: _typeinfo, obj: Any) -> Simplified:
    if isinstance(obj, list):
        return [_simplify(v) for v in obj]
    if isinstance(obj, dict):
        return {_simplify(k):_simplify(v) for k, v in obj.items()}
    if isinstance(obj, str):
        return str(obj)
    if isinstance(obj, (int, float)):
        return obj
    if obj is None:
        return None
    ts = getattr(obj, 'to_simplified', None)
    if ts:
        return ts()
    raise TypeError(obj)


def to_simplified(obj: T) -> Simplified:
    result: Simplified = {}
    rtype = getattr(obj, 'resource_type', None)
    if rtype is not None:
        result['resource_type'] = rtype
    for fld in dataclasses.fields(obj):
        type_info = _typeinfo(fld.type)
        sv = _simplify(_typeinfo(fld.type), getattr(obj, fld.name))
        ropts = type_info.resource_opts()
        if ropts.embedded and isinstance(sv, dict):
            result.update(sv)
        elif sv is None and ropts.keep_none:
            result[fld.name] = sv
        elif not sv and ropts.keep_false:
            result[fld.name] = sv
        elif sv:
            result[fld.name] = sv
    return result


def from_simplified(cls: Type[T], data: Simplified) -> T:
    return _assemble_simplified(cls, _Source(data))


class ResourceType:
    def __init__(self, name: str) -> None:
        self.name = name

    def __get__(self, obj: Any, objtype: Any = None) -> str:
        return self.name


def _resourceclass(resource_name: str):
    def _decorator(cls: Any) -> Any:
        cls = dataclasses.dataclass(cls)
        if resource_name:
            cls.resource_type = ResourceType(resource_name)
        cls._conversions = {}
        if getattr(cls, 'to_simplified', None) is None:
            cls.to_simplified = to_simplified
        if getattr(cls, 'from_simplified', None) is None:
            cls.from_simplified = classmethod(from_simplified)
            cls._assemble_simplified = classmethod(_assemble_simplified)
        return cls
    return _decorator


_RESOURCES: Dict[str, Type[T]] = {}


def resource(resource_name: str, registry: Optional[Dict[str, Type[T]]] = None) -> Type[T]:
    assert resource_name
    decf = _resourceclass(resource_name)
    def _decorator(cls: Any) -> Any:
        cls = decf(cls)
        nonlocal registry
        if registry is None:
            registry = _RESOURCES
        if resource_name in registry:
            raise KeyError(f'{resource_name} already used')
        registry[resource_name] = cls
        return cls
    return _decorator


def component():
    return _resourceclass('')


def get_resource(resource_name, registry: Optional[Dict[str, Type[T]]] = None) -> Type[T]:
    if registry is None:
        registry = _RESOURCES
    try:
        return registry[resource_name]
    except KeyError:
        raise ValueError(f'no matching resource_type: {resource_name}')


def load(data: Simplified) -> Any:
    print("DD", data)
    if 'resource_type' not in data and 'resources' in data:
        res = data['resources']
        if not isinstance(res, list):
            raise TypeError(res)
        out = []
        for item in res:
            out.extend(load(item))
        return out
    if 'resource_type' not in data:
        raise ValueError('no resource_type')
    rcls = get_resource(data['resource_type'])
    return [rcls.from_simplified(data)]


@component()
class Bonk:
    label: str
    height: int
    width: int
    length: int


@resource('ceph.smb.example')
class Example:
    name: str
    serial_num: str
    weight: int = 0
    contents: Optional[List[Bonk]] = None
