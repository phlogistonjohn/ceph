from itertools import chain
from typing import (
    Any,
    Dict,
    List,
    Optional,
    TypeVar,
    Type,
    Tuple,
    Generic,
    Annotated,
)
import dataclasses
import enum

from .proto import Simplified

T = TypeVar('T')


try:  # pragma: no cover
    from typing import get_args
except ImportError:  # pragma: no cover

    def get_args(t: Any) -> Tuple:
        try:
            return t.__args__
        except AttributeError:
            return tuple()


class ResourceError(Exception):
    pass


class MissingFieldError(KeyError, ResourceError):
    def __init__(self, fname: str) -> None:
        self.fname = fname

    def __str__(self) -> str:
        return f'field {self.fname!r} not found in source data'


class InvalidFieldError(ValueError, ResourceError):
    def __init__(self, fname: str) -> None:
        self.fname = fname

    def __str__(self) -> str:
        return f'field {self.fname!r} has invalid type'


class MissingResourceTypeError(ValueError, ResourceError):
    def __init__(self, data: Simplified) -> None:
        self.data = data

    def __str__(self) -> str:
        return 'source data is missing a resource_type field'


class InvalidResourceTypeError(ValueError, ResourceError):
    def __init__(self, *, expected: str = '', actual: str = '') -> None:
        self.expected = expected
        self.actual = actual

    def __str__(self) -> str:
        msg = f'invalid resource type value: {self.actual!r}'
        if self.expected:
            msg += f'; expected: {self.expected!r}'
        return msg


@dataclasses.dataclass
class Extras:
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


class ResourceType:
    """A read-only property of a class acting as a resource type. When accessed,
    returns the name of the resource type.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def __get__(self, obj: Any, objtype: Any = None) -> str:
        return self.name


_RESOURCES: Dict[str, Type[T]] = {}


def to_simplified(obj: T) -> Simplified:
    return _to_simplified(_typeinfo(type(obj)), obj)


def from_simplified(cls: Type[T], data: Simplified) -> T:
    return _from_object(_typeinfo(cls), _Source(data))


def resource(
    resource_name: str, registry: Optional[Dict[str, Type[T]]] = None
) -> Type[T]:
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


def get_resource(
    resource_name, registry: Optional[Dict[str, Type[T]]] = None
) -> Type[T]:
    if registry is None:
        registry = _RESOURCES
    try:
        return registry[resource_name]
    except KeyError:
        raise InvalidResourceTypeError(actual=resource_name)


def load(data: Simplified) -> List[Any]:
    print("LOADD", data)
    # Given a bare list/iterator. Assume it contains loadable objects.
    if not isinstance(data, dict):
        return list(chain.from_iterable(load(v) for v in data))
    # Given a "list object"
    if 'resource_type' not in data and 'resources' in data:
        rl = data['resources']
        if not isinstance(rl, list):
            raise TypeError(res)
        return list(chain.from_iterable(load(v) for v in rl))
    # anything else must be a "self describing" object with a resource_type
    # value
    if 'resource_type' not in data:
        raise MissingResourceTypeError(data)
    rcls = get_resource(data['resource_type'])
    return [rcls.from_simplified(data)]


###############################################################


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
            cls._from_simplfied_object = classmethod(_from_cls_object)
        return cls

    return _decorator


class _typeinfo:
    def __init__(self, target_type: Any) -> None:
        print("TYPEINFO", target_type)
        self._meta = getattr(target_type, '__metadata__', None)
        # if the target type is Annotated we just want the metadata (our
        # cusomization params) and the underlying type.
        if self._meta:
            target_type = target_type.__origin__
        self.target_type = target_type
        self._args = getattr(self.target_type, '__args__', None)
        self._origin = getattr(self.target_type, '__origin__', None)

    def is_optional(self) -> bool:
        if self._args is None:
            return False
        return any(t is type(None) for t in self._args)

    def extras(self) -> Extras:
        meta = self._meta or []
        try:
            return [a for a in meta if isinstance(a, Extras)][0]
        except IndexError:
            return Extras()

    def unwrap(self) -> '_typeinfo':
        if self._args is None:
            return self
        nnt = [t for t in self._args if t is not type(None)][0]
        return self.__class__(nnt)

    def unwrap_optional(self) -> '_typeinfo':
        if not self.is_optional():
            return self
        return self.unwrap()

    def unwrap_dict(self) -> Tuple['_typeinfo', '_typeinfo']:
        assert self._args and len(self._args) == 2
        kt, vt = self._args
        return self.__class__(kt), self.__class__(vt)

    def takes(self, *target_types: Any) -> bool:
        if self._origin:
            return self._origin in target_types
        return self.target_type in target_types

    def __repr__(self) -> str:
        return f'_typeinfo({self.target_type!r})'


def _to_simplified(type_info: _typeinfo, obj: Any) -> Simplified:
    result: Simplified = {}
    rtype = getattr(obj, 'resource_type', None)
    if rtype is not None:
        result['resource_type'] = rtype
    for fld in dataclasses.fields(obj):
        type_info = _typeinfo(fld.type)
        sv = _simplify_field(_typeinfo(fld.type), getattr(obj, fld.name))
        extras = type_info.extras()
        if extras.embedded and isinstance(sv, dict):
            result.update(sv)
        elif (
            sv
            or (sv is None and extras.keep_none)
            or (sv is not None and not sv and extras.keep_false)
        ):
            result[fld.name] = sv
    return result


def _simplify_field(type_info: _typeinfo, obj: Any) -> Simplified:
    ts = getattr(obj, 'to_simplified', None)
    if ts:
        return ts()
    if isinstance(obj, list):
        assert type_info.unwrap_optional().takes(list, List)
        childttype = type_info.unwrap_optional().unwrap()
        return [_simplify_field(childttype, v) for v in obj]
    if isinstance(obj, dict):
        assert type_info.unwrap_optional().takes(dict, Dict)
        kt, vt = type_info.unwrap_optional().unwrap_dict()
        return {
            _simplify_field(kt, k): _simplify_field(vt, v)
            for k, v in obj.items()
        }
    if isinstance(obj, str):
        return str(obj)
    if isinstance(obj, (int, float)):
        return obj
    if obj is None:
        assert type_info.is_optional()
        return None
    raise TypeError(obj)


_nodefault = object()


class _Source:
    def __init__(self, data: Simplified) -> None:
        self.data = data

    def __getitem__(self, key) -> '_Source':
        return self.__class__(self.data[key])

    def get(self, *keys: str, default=_nodefault) -> '_Source':
        for key in keys:
            try:
                return self[key]
            except KeyError:
                pass
        if default is _nodefault:
            raise KeyError(key)
        return self.__class__(default)

    def get_or_borrow(self, *keys: str) -> '_Source':
        try:
            return self.get(*keys)
        except KeyError:
            return self.borrow()

    def borrow(self) -> '_Source':
        return self

    def contents(self) -> List['_Source']:
        return [self.__class__(v) for v in self.data]

    def dict_contents(self) -> List[Tuple['_Source', '_Source']]:
        return [
            (self.__class__(k), self.__class__(v))
            for k, v in self.data.items()
        ]

    def __repr__(self) -> str:
        return f'<_Source({self.data!r}) at {id(self):0x}>'


def _xt(f):
    def _func(*args, **kwargs):
        print(f'\ncall: {f}', args, kwargs)
        return f(*args, **kwargs)

    return _func


@_xt
def _from_cls_object(cls: Any, source: _Source) -> Any:
    return _from_object(_typeinfo(cls), source)


@_xt
def _from_object(type_info: _typeinfo, source: _Source) -> Any:
    try:
        fields = dataclasses.fields(type_info.target_type)
        _assert_resource_type(type_info, source)
    except TypeError:
        return _from_scalar(type_info, source)
    kw = {}
    for fld in fields:
        print("from object fld-->", fld.name)
        try:
            kw[fld.name] = _from_object_field(
                _typeinfo(fld.type), source, fld.name
            )
        except MissingFieldError:
            pass
    print("NEW", type_info.target_type, '(', kw, ')')
    obj = type_info.target_type(**kw)
    validate = getattr(obj, 'validate', None)
    if validate:
        validate()
    return obj


@_xt
def _from_object_field(
    type_info: _typeinfo, source: _Source, fname: str
) -> Any:
    is_optional = type_info.is_optional()
    extras = type_info.extras()
    innert = type_info.unwrap_optional()
    if extras.embedded:
        tgt = source.get_or_borrow(fname, *(extras.alt_keys or []))
    else:
        kw = {'default': None} if is_optional else {}
        try:
            tgt = source.get(fname, *(extras.alt_keys or []), **kw)
        except KeyError as err:
            raise MissingFieldError(fname) from err
    print('field data CHOSE:', tgt)

    if tgt.data is None and is_optional:
        return None

    _fso = getattr(innert.target_type, '_from_simplfied_object', None)
    _fss = getattr(innert.target_type, 'from_simplified', None)
    print('__methods__>', _fso, _fss)
    try:
        if _fso and source.data is not None:
            # _from_simplfied_object is semi-private and supports the direct use
            # of a source
            return _fso(tgt)
        if _fss and source.data is not None:
            # from_simplified is the fully public version and doesn't know anything
            # about our special source type
            return _fss(tgt.data)
    except TypeError:
        # handle the case of an optional embedded object that is missing
        # required fields.
        # TODO: this catches the TypeError raised by calling cls(**kw) in
        # _from_object, should this be tightened up with a different exc type?
        if is_optional and extras.embedded:
            return None
        raise
    if innert.takes(list, List):
        assert isinstance(tgt.data, list)
        return [_from_object(innert.unwrap(), sv) for sv in tgt.contents()]
    if innert.takes(dict, Dict):
        assert isinstance(tgt.data, dict)
        kt, vt = innert.unwrap_dict()
        return {
            _from_scalar(kt, sk): _from_object(vt, sv)
            for sk, sv in tgt.dict_contents()
        }
    try:
        return _from_scalar(innert, tgt, optional=is_optional)
    except TypeError:
        raise InvalidFieldError(fname)


@_xt
def _from_scalar(
    type_info: _typeinfo, source: _Source, optional: bool = False
) -> Any:
    value = source.data
    if value is None and (optional or type_info.is_optional()):
        return None
    if issubclass(type_info.target_type, enum.Enum):
        return type_info.target_type(value)
    if isinstance(value, (str, int, float)):
        return value
    raise TypeError(value)


@_xt
def _assert_resource_type(type_info: _typeinfo, source: _Source) -> None:
    expected_rt = getattr(type_info.target_type, 'resource_type', None)
    if not expected_rt:
        return
    print('resource_type=', expected_rt)
    try:
        curr_resource_type = source['resource_type'].data
    except KeyError:
        raise MissingResourceTypeError(source.data)
    if expected_rt != curr_resource_type:
        raise InvalidResourceTypeError(expected=expected_rt, actual=curr_resource_type)
