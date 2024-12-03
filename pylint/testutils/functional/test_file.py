from __future__ import annotations
import configparser
from collections.abc import Callable
from os.path import basename, exists, join
from typing import TypedDict

def parse_python_version(ver_str: str) -> tuple[int, ...]:
    """Convert python version to a tuple of integers for easy comparison."""
    return tuple(map(int, ver_str.split('.')))

class NoFileError(Exception):
    pass

class TestFileOptions(TypedDict):
    min_pyver: tuple[int, ...]
    max_pyver: tuple[int, ...]
    min_pyver_end_position: tuple[int, ...]
    requires: list[str]
    except_implementations: list[str]
    exclude_platforms: list[str]
    exclude_from_minimal_messages_config: bool
POSSIBLE_TEST_OPTIONS = {'min_pyver', 'max_pyver', 'min_pyver_end_position', 'requires', 'except_implementations', 'exclude_platforms', 'exclude_from_minimal_messages_config'}

class FunctionalTestFile:
    """A single functional test case file with options."""
    _CONVERTERS: dict[str, Callable[[str], tuple[int, ...] | list[str]]] = {'min_pyver': parse_python_version, 'max_pyver': parse_python_version, 'min_pyver_end_position': parse_python_version, 'requires': lambda s: [i.strip() for i in s.split(',')], 'except_implementations': lambda s: [i.strip() for i in s.split(',')], 'exclude_platforms': lambda s: [i.strip() for i in s.split(',')]}

    def __init__(self, directory: str, filename: str) -> None:
        self._directory = directory
        self.base = filename.replace('.py', '')
        self.options: TestFileOptions = {'min_pyver': (2, 5), 'max_pyver': (4, 0), 'min_pyver_end_position': (3, 8), 'requires': [], 'except_implementations': [], 'exclude_platforms': [], 'exclude_from_minimal_messages_config': False}
        self._parse_options()

    def __repr__(self) -> str:
        return f'FunctionalTest:{self.base}'
