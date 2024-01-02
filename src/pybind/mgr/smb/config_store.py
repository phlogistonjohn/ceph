from typing import Tuple, Collection, Iterator, Dict


class MemConfigResource:
    def __init__(self, store: 'MemConfigStore', ns: str, name: str) -> None:
        self._store = store
        self._ns = ns
        self._name = name

    def read(self) -> str:
        return self._store._data[(self._ns, self._name)]

    def write(self, content: str) -> None:
        self._store._data[(self._ns, self._name)] = content

    @property
    def uri(self) -> str:
        return f'fake-resource:{self._ns}/{self._name}'


class MemConfigStore:
    def __init__(self) -> None:
        self._data: Dict[Tuple[str, str], str] = {}

    def __getitem__(self, key: Tuple[str, str]) -> MemConfigResource:
        return MemConfigResource(self, key[0], key[1])

    def namespaces(self) -> Collection[str]:
        return {k[0] for k in self._data.keys()}

    def contents(self, ns: str) -> Collection[str]:
        return {k[1] for k in self._data.keys() if k[0] == ns}

    def __iter__(self) -> Iterator[Tuple[str, str]]:
        return iter(self._data.keys())


