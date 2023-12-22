from typing import Optional, List, Dict

import dataclasses
import enum

import pytest

import smb.resourcelib as rlib


@rlib.component()
class tclass1:
    foo: str
    bar: int
    baz: rlib.Annotated[str, rlib.Extras(keep_false=False)]
    quux: Optional[List[int]] = None
    womble: rlib.Annotated[Optional[int], rlib.Extras(keep_none=True)] = None
    tags: Optional[Dict[str, int]] = None


@rlib.component()
class tclass2:
    name: str
    xyz: tclass1


@rlib.component()
class tclass3:
    artists: List[str]
    kind: str = ''


@rlib.resource('test.res.one')
class ResOne:
    zim: str
    zam: Optional[str] = None
    jam: Optional[tclass2] = None


@rlib.resource('test.res.two')
class ResTwo:
    aaa: str
    bbb: List[tclass1]
    ccc: Dict[str, str]
    ddd: rlib.Annotated[tclass3, rlib.Extras(embedded=True)]


class _flavor(str, enum.Enum):
    vanilla = 'vanilla'
    strawberry = 'strawberry'
    cherry = 'cherry'
    unset = ''

    def __str__(self) -> str:
        return self.value


@rlib.resource('test.res.three')
class ResThree:
    one: ResOne
    two: Optional[ResTwo] = None
    flavor: _flavor = _flavor.unset


def test_typeinfo():
    fmap = {
        f.name: rlib._typeinfo(f.type) for f in dataclasses.fields(tclass1)
    }
    assert 'foo' in fmap
    assert 'bar' in fmap
    assert 'baz' in fmap

    assert not fmap['foo'].is_optional()
    assert not fmap['bar'].is_optional()
    assert not fmap['baz'].is_optional()
    assert fmap['quux'].is_optional()
    assert fmap['womble'].is_optional()

    assert fmap['foo'].extras().keep_false == True
    assert fmap['baz'].extras().keep_false == False
    assert fmap['bar'].extras().keep_none == False
    assert fmap['womble'].extras().keep_none == True

    assert fmap['foo'].unwrap_optional() is fmap['foo']
    assert fmap['quux'].unwrap_optional() is not fmap['foo']
    assert fmap['quux'].unwrap_optional().takes(list, List)
    assert fmap['quux'].unwrap_optional().unwrap_optional().takes(list, List)
    assert fmap['baz'].unwrap_optional() is fmap['baz']

    assert fmap['quux'].unwrap().takes(list, List)
    assert fmap['quux'].unwrap().unwrap().takes(int)
    assert fmap['foo'].unwrap() is fmap['foo']

    assert fmap['tags'].unwrap_optional().takes(dict, Dict)
    tkt, tvt = fmap['tags'].unwrap_optional().unwrap_dict()
    assert tkt.takes(str)
    assert tvt.takes(int)

    assert '_typeinfo' in f'{fmap["foo"]}'


def test_get_resource():
    r1 = rlib.get_resource('test.res.one')
    assert r1 is ResOne

    with pytest.raises(ValueError, match='foo.bar'):
        rlib.get_resource('foo.bar')


def test_resouce_type_name_reuse_blocked():
    with pytest.raises(KeyError):

        @rlib.resource('test.res.one')
        class FakeOne:
            zzz: int


@pytest.mark.parametrize(
    "params",
    [
        # basic use of a single non-nesting resource component
        {
            'obj': tclass1(
                foo='okthen',
                bar='chocolate',
                baz='guitar',
                womble=77,
                tags={'red': 2, 'green': 6},
            ),
            'expected': {
                'foo': 'okthen',
                'bar': 'chocolate',
                'baz': 'guitar',
                'womble': 77,
                'tags': {
                    'red': 2,
                    'green': 6,
                },
            },
        },
        # test simplifying a resource object
        {
            'obj': ResOne(
                zim='yes',
                jam=tclass2(
                    name='nothing',
                    xyz=tclass1(
                        foo='',
                        bar='chocolate',
                        baz='',
                        tags={'red': 2, 'green': 6},
                    ),
                ),
            ),
            'expected': {
                'resource_type': 'test.res.one',
                'zim': 'yes',
                'jam': {
                    'name': 'nothing',
                    'xyz': {
                        'foo': '',
                        'bar': 'chocolate',
                        'womble': None,
                        'tags': {
                            'red': 2,
                            'green': 6,
                        },
                    },
                },
            },
        },
        # a resource object that does some embedding
        {
            'obj': ResTwo(
                aaa='hello',
                bbb=[tclass1(foo='child', bar='', baz='', womble=88)],
                ccc={},
                ddd=tclass3(['da Vinci', 'Picasso'], 'painting'),
            ),
            'expected': {
                'resource_type': 'test.res.two',
                'aaa': 'hello',
                'bbb': [
                    {'foo': 'child', 'bar': '', 'womble': 88},
                ],
                'ccc': {},
                'artists': ['da Vinci', 'Picasso'],
                'kind': 'painting',
            },
        },
    ],
)
def test_to_simplified(params):
    obj = params.get('obj')
    sdata = obj.to_simplified()
    assert params['expected'] == sdata


@pytest.mark.parametrize(
    "params",
    [
        # round trip a simple single-level type
        {
            'target_type': tclass1,
            'data': {
                'foo': 'zowie',
                'bar': 12,
                'baz': 'fickle',
            },
            'expected': {
                'foo': 'zowie',
                'bar': 12,
                'baz': 'fickle',
                'womble': None,
            },
        },
        # again, but with different values
        {
            'target_type': tclass1,
            'data': {
                'foo': 'howdy',
                'bar': 22,
                'baz': 'zombo',
                'quux': [1, 9, 88],
                'womble': 909,
                'tags': {'eggs': 400, 'beans': 200},
            },
            'expected': {
                'foo': 'howdy',
                'bar': 22,
                'baz': 'zombo',
                'quux': [1, 9, 88],
                'womble': 909,
                'tags': {'eggs': 400, 'beans': 200},
            },
        },
        # one level of nesting
        {
            'target_type': tclass2,
            'data': {
                'name': 'game',
                'xyz': {
                    'foo': 'within',
                    'bar': 32,
                    'baz': '',
                    'quux': [3, 33, 333],
                    'womble': 919,
                    'tags': {},
                },
            },
            'expected': {
                'name': 'game',
                'xyz': {
                    'foo': 'within',
                    'bar': 32,
                    'quux': [3, 33, 333],
                    'womble': 919,
                    'tags': {},
                },
            },
        },
        # three possible levels, but keep it minimal
        {
            'target_type': ResOne,
            'data': {
                'resource_type': 'test.res.one',
                'zim': 'zoom',
            },
            'expected': {
                'resource_type': 'test.res.one',
                'zim': 'zoom',
            },
        },
        # three levels of nesting
        {
            'target_type': ResOne,
            'data': {
                'resource_type': 'test.res.one',
                'zim': 'zoom',
                'zam': 'greetings',
                'jam': {
                    'name': 'game',
                    'xyz': {
                        'foo': 'is here',
                        'bar': 56,
                        'baz': 'babble',
                        'quux': [4, 0, 5],
                        'womble': 92,
                        'tags': {'bug': 9, 'feature': 4},
                    },
                },
            },
            'expected': {
                'resource_type': 'test.res.one',
                'zim': 'zoom',
                'zam': 'greetings',
                'jam': {
                    'name': 'game',
                    'xyz': {
                        'foo': 'is here',
                        'bar': 56,
                        'baz': 'babble',
                        'quux': [4, 0, 5],
                        'womble': 92,
                        'tags': {'bug': 9, 'feature': 4},
                    },
                },
            },
        },
        # nesting with embedding
        {
            'target_type': ResTwo,
            'data': {
                'resource_type': 'test.res.two',
                'aaa': 'apple',
                'bbb': [
                    {'foo': 'item1', 'bar': 'yes', 'baz': '0'},
                    {'foo': 'item2', 'bar': 'no', 'baz': '10'},
                ],
                'ccc': {
                    'cow': 'moo',
                    'dog': 'arf',
                },
                'artists': ['me', 'you'],
                'kind': 'very',
            },
            'expected': {
                'resource_type': 'test.res.two',
                'aaa': 'apple',
                'bbb': [
                    {
                        'foo': 'item1',
                        'bar': 'yes',
                        'baz': '0',
                        'womble': None,
                    },
                    {
                        'foo': 'item2',
                        'bar': 'no',
                        'baz': '10',
                        'womble': None,
                    },
                ],
                'ccc': {
                    'cow': 'moo',
                    'dog': 'arf',
                },
                'artists': ['me', 'you'],
                'kind': 'very',
            },
        },
        #  embedding is optional in a source
        {
            'target_type': ResTwo,
            'data': {
                'resource_type': 'test.res.two',
                'aaa': 'artichoke',
                'bbb': [
                    {'foo': 'item1', 'bar': 'yes', 'baz': '0'},
                ],
                'ccc': {
                    'cow': 'moo',
                    'dog': 'arf',
                },
                'ddd': {
                    'artists': ['city', 'country'],
                },
            },
            'expected': {
                'resource_type': 'test.res.two',
                'aaa': 'artichoke',
                'bbb': [
                    {
                        'foo': 'item1',
                        'bar': 'yes',
                        'baz': '0',
                        'womble': None,
                    },
                ],
                'ccc': {
                    'cow': 'moo',
                    'dog': 'arf',
                },
                'artists': ['city', 'country'],
                'kind': '',
            },
        },
    ],
)
def test_from_simplified(params):
    data = params.get('data')
    typ = params.get('target_type')
    obj = typ.from_simplified(data)
    # test round tripping because asserting equality on the
    # objects is not simple
    sdata = obj.to_simplified()
    assert params['expected'] == sdata


@pytest.mark.parametrize(
    "params",
    [
        # minimal single object
        {
            'data': {
                'resource_type': 'test.res.one',
                'zim': 'zoom',
            },
            'expected': [
                {
                    'resource_type': 'test.res.one',
                    'zim': 'zoom',
                }
            ],
        },
        # three levels of nesting
        {
            'data': {
                'resource_type': 'test.res.one',
                'zim': 'zoom',
                'zam': 'greetings',
                'jam': {
                    'name': 'game',
                    'xyz': {
                        'foo': 'is here',
                        'bar': 56,
                        'baz': 'babble',
                        'quux': [4, 0, 5],
                        'womble': 92,
                        'tags': {'bug': 9, 'feature': 4},
                    },
                },
            },
            'expected': [
                {
                    'resource_type': 'test.res.one',
                    'zim': 'zoom',
                    'zam': 'greetings',
                    'jam': {
                        'name': 'game',
                        'xyz': {
                            'foo': 'is here',
                            'bar': 56,
                            'baz': 'babble',
                            'quux': [4, 0, 5],
                            'womble': 92,
                            'tags': {'bug': 9, 'feature': 4},
                        },
                    },
                }
            ],
        },
        # nesting with embedding
        {
            'data': {
                'resource_type': 'test.res.two',
                'aaa': 'apple',
                'bbb': [
                    {'foo': 'item1', 'bar': 'yes', 'baz': '0'},
                    {'foo': 'item2', 'bar': 'no', 'baz': '10'},
                ],
                'ccc': {
                    'cow': 'moo',
                    'dog': 'arf',
                },
                'artists': ['me', 'you'],
                'kind': 'very',
            },
            'expected': [
                {
                    'resource_type': 'test.res.two',
                    'aaa': 'apple',
                    'bbb': [
                        {
                            'foo': 'item1',
                            'bar': 'yes',
                            'baz': '0',
                            'womble': None,
                        },
                        {
                            'foo': 'item2',
                            'bar': 'no',
                            'baz': '10',
                            'womble': None,
                        },
                    ],
                    'ccc': {
                        'cow': 'moo',
                        'dog': 'arf',
                    },
                    'artists': ['me', 'you'],
                    'kind': 'very',
                }
            ],
        },
        #  embedding is optional in a source
        {
            'data': {
                'resource_type': 'test.res.two',
                'aaa': 'artichoke',
                'bbb': [
                    {'foo': 'item1', 'bar': 'yes', 'baz': '0'},
                ],
                'ccc': {
                    'cow': 'moo',
                    'dog': 'arf',
                },
                'ddd': {
                    'artists': ['city', 'country'],
                },
            },
            'expected': [
                {
                    'resource_type': 'test.res.two',
                    'aaa': 'artichoke',
                    'bbb': [
                        {
                            'foo': 'item1',
                            'bar': 'yes',
                            'baz': '0',
                            'womble': None,
                        },
                    ],
                    'ccc': {
                        'cow': 'moo',
                        'dog': 'arf',
                    },
                    'artists': ['city', 'country'],
                    'kind': '',
                }
            ],
        },
        # two objects in a simple list
        {
            'data': [
                {
                    'resource_type': 'test.res.one',
                    'zim': 'zoom',
                },
                {
                    'resource_type': 'test.res.one',
                    'zim': 'zoinks',
                    'zam': 'zola',
                },
            ],
            'expected': [
                {
                    'resource_type': 'test.res.one',
                    'zim': 'zoom',
                },
                {
                    'resource_type': 'test.res.one',
                    'zim': 'zoinks',
                    'zam': 'zola',
                },
            ],
        },
        # two objects, different kinds
        {
            'data': [
                {
                    'resource_type': 'test.res.one',
                    'zim': 'zoom',
                },
                {
                    'resource_type': 'test.res.two',
                    'aaa': 'alpha',
                    'bbb': [],
                    'ccc': {
                        'delta': 'flyer',
                    },
                    'artists': ['country', 'western'],
                    'kind': '',
                },
            ],
            'expected': [
                {
                    'resource_type': 'test.res.one',
                    'zim': 'zoom',
                },
                {
                    'resource_type': 'test.res.two',
                    'aaa': 'alpha',
                    'bbb': [],
                    'ccc': {
                        'delta': 'flyer',
                    },
                    'artists': ['country', 'western'],
                    'kind': '',
                },
            ],
        },
        # two objects, "list type object"
        {
            'data': {
                'resources': [
                    {
                        'resource_type': 'test.res.one',
                        'zim': 'zippy',
                    },
                    {
                        'resource_type': 'test.res.two',
                        'aaa': 'alpha',
                        'bbb': [],
                        'ccc': {
                            'delta': 'flyer',
                        },
                        'artists': ['country', 'western'],
                        'kind': '',
                    },
                ]
            },
            'expected': [
                {
                    'resource_type': 'test.res.one',
                    'zim': 'zippy',
                },
                {
                    'resource_type': 'test.res.two',
                    'aaa': 'alpha',
                    'bbb': [],
                    'ccc': {
                        'delta': 'flyer',
                    },
                    'artists': ['country', 'western'],
                    'kind': '',
                },
            ],
        },
        # with enum
        {
            'data': {
                'resource_type': 'test.res.three',
                'one': {
                    'resource_type': 'test.res.one',
                    'zim': 'zalt',
                },
                'flavor': 'strawberry',
            },
            'expected': [
                {
                    'resource_type': 'test.res.three',
                    'one': {
                        'resource_type': 'test.res.one',
                        'zim': 'zalt',
                    },
                    'flavor': 'strawberry',
                },
            ],
        },
    ],
)
def test_load(params):
    data = params.get('data')
    loaded = rlib.load(data)
    # test round tripping because asserting equality on the
    # objects is not simple
    sdata = [obj.to_simplified() for obj in loaded]
    assert params['expected'] == sdata


@pytest.mark.parametrize(
    "params",
    [
        # missing resource_type, can not load
        {
            'data': {
                'zim': 'aaa',
                'zam': 'bbb',
            },
            'exc_type': rlib.MissingResourceTypeError,
            'error': '',
        },
        # bad resource_type, can not load
        {
            'data': {
                'resource_type': 'fred',
                'zim': 'aaa',
                'zim': 'aaa',
                'zam': 'bbb',
            },
            'exc_type': rlib.InvalidResourceTypeError,
            'error': 'fred',
        },
        # subtype mismatch - missing
        {
            'data': {
                'resource_type': 'test.res.three',
                'one': {},
            },
            'exc_type': rlib.MissingResourceTypeError,
            'error': '',
        },
        # subtype mismatch - wrong value
        {
            'data': {
                'resource_type': 'test.res.three',
                'one': {
                    'resource_type': 'test.foo.flub',
                    'zim': 'aaa',
                    'zam': 'bbb',
                },
            },
            'exc_type': rlib.InvalidResourceTypeError,
            'error': 'test.foo.flub',
        },
        # junk field
        {
            'data': {
                'resource_type': 'test.res.three',
                'one': {
                    'resource_type': 'test.res.one',
                    'zim': 'imok',
                    'zam': object(),
                },
            },
            'exc_type': rlib.InvalidFieldError,
            'error': 'zam',
        },
    ],
)
def test_load_error(params):
    data = params.get('data')
    with pytest.raises(params['exc_type'], match=params['error']):
        loaded = rlib.load(data)
