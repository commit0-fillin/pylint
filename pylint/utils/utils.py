from __future__ import annotations
try:
    import isort.api
    import isort.settings
    HAS_ISORT_5 = True
except ImportError:
    import isort
    HAS_ISORT_5 = False
import argparse
import codecs
import os
import re
import sys
import textwrap
import tokenize
import warnings
from collections import deque
from collections.abc import Iterable, Sequence
from io import BufferedReader, BytesIO
from typing import TYPE_CHECKING, Any, List, Literal, Pattern, TextIO, Tuple, TypeVar, Union
from astroid import Module, modutils, nodes
from pylint.constants import PY_EXTS
from pylint.typing import OptionDict
if TYPE_CHECKING:
    from pylint.lint import PyLinter
DEFAULT_LINE_LENGTH = 79
GLOBAL_OPTION_BOOL = Literal['suggestion-mode', 'analyse-fallback-blocks', 'allow-global-unused-variables', 'prefer-stubs']
GLOBAL_OPTION_INT = Literal['max-line-length', 'docstring-min-length']
GLOBAL_OPTION_LIST = Literal['ignored-modules']
GLOBAL_OPTION_PATTERN = Literal['no-docstring-rgx', 'dummy-variables-rgx', 'ignored-argument-names', 'mixin-class-rgx']
GLOBAL_OPTION_PATTERN_LIST = Literal['exclude-too-few-public-methods', 'ignore-paths']
GLOBAL_OPTION_TUPLE_INT = Literal['py-version']
GLOBAL_OPTION_NAMES = Union[GLOBAL_OPTION_BOOL, GLOBAL_OPTION_INT, GLOBAL_OPTION_LIST, GLOBAL_OPTION_PATTERN, GLOBAL_OPTION_PATTERN_LIST, GLOBAL_OPTION_TUPLE_INT]
T_GlobalOptionReturnTypes = TypeVar('T_GlobalOptionReturnTypes', bool, int, List[str], Pattern[str], List[Pattern[str]], Tuple[int, ...])

def normalize_text(text: str, line_len: int=DEFAULT_LINE_LENGTH, indent: str='') -> str:
    """Wrap the text on the given line length."""
    lines = textwrap.wrap(text, width=line_len)
    return '\n'.join(indent + line for line in lines)
CMPS = ['=', '-', '+']

def diff_string(old: float, new: float) -> str:
    """Given an old and new value, return a string representing the difference."""
    diff = new - old
    if diff == 0:
        return '='
    return f"{CMPS[0] if diff > 0 else CMPS[1]}{abs(diff):+.2f}"

def get_module_and_frameid(node: nodes.NodeNG) -> tuple[str, str]:
    """Return the module name and the frame id in the module."""
    frame = node.frame()
    module = node.root()
    name = module.name
    if isinstance(module, nodes.Module):
        name = module.file
    return name, frame.qname()

def get_rst_title(title: str, character: str) -> str:
    """Permit to get a title formatted as ReStructuredText test (underlined with a
    chosen character).
    """
    return f"{title}\n{character * len(title)}\n"

def get_rst_section(section: str | None, options: list[tuple[str, OptionDict, Any]], doc: str | None=None) -> str:
    """Format an option's section using as a ReStructuredText formatted output."""
    result = []
    if section:
        result.append(get_rst_title(section, "'"))
    if doc:
        result.append(normalize_text(doc))
    result.append('\n')
    for optname, optdict, value in options:
        help_text = optdict.get('help')
        result.append(f":{optname}:")
        if help_text:
            result.append(normalize_text(help_text, indent='  '))
        if value:
            result.append(f"\n  Default: ``{_format_option_value(optdict, value)}``")
        result.append('\n')
    return '\n'.join(result)

def register_plugins(linter: PyLinter, directory: str) -> None:
    """Load all module and package in the given directory, looking for a
    'register' function in each one, used to register pylint checkers.
    """
    imported_modules = []
    for filename in os.listdir(directory):
        name, ext = os.path.splitext(filename)
        if ext in PY_EXTS and name != '__init__':
            module = modutils.load_module_from_file(os.path.join(directory, filename))
            imported_modules.append(module)
    for module in imported_modules:
        if hasattr(module, 'register'):
            module.register(linter)

def _splitstrip(string: str, sep: str=',') -> list[str]:
    """Return a list of stripped string by splitting the string given as
    argument on `sep` (',' by default), empty strings are discarded.

    >>> _splitstrip('a, b, c   ,  4,,')
    ['a', 'b', 'c', '4']
    >>> _splitstrip('a')
    ['a']
    >>> _splitstrip('a,\\nb,\\nc,')
    ['a', 'b', 'c']

    :type string: str or unicode
    :param string: a csv line

    :type sep: str or unicode
    :param sep: field separator, default to the comma (',')

    :rtype: str or unicode
    :return: the unquoted string (or the input string if it wasn't quoted)
    """
    return [s.strip() for s in string.split(sep) if s.strip()]

def _unquote(string: str) -> str:
    """Remove optional quotes (simple or double) from the string.

    :param string: an optionally quoted string
    :return: the unquoted string (or the input string if it wasn't quoted)
    """
    if string.startswith('"') and string.endswith('"'):
        return string[1:-1]
    if string.startswith("'") and string.endswith("'"):
        return string[1:-1]
    return string

def _check_regexp_csv(value: list[str] | tuple[str] | str) -> Iterable[str]:
    """Split a comma-separated list of regexps, taking care to avoid splitting
    a regex employing a comma as quantifier, as in `\\d{1,2}`.
    """
    if isinstance(value, (list, tuple)):
        return value
    if isinstance(value, str):
        pattern = re.compile(r',\s*(?=(?:[^{]*{[^}]*})*[^}]*$)')
        return [s.strip() for s in pattern.split(value)]
    return []

def _comment(string: str) -> str:
    """Return string as a comment."""
    return f"# {string}"

def _format_option_value(optdict: OptionDict, value: Any) -> str:
    """Return the user input's value from a 'compiled' value.

    TODO: Refactor the code to not use this deprecated function
    """
    if isinstance(value, (list, tuple)):
        value = ','.join(value)
    elif isinstance(value, dict):
        value = ','.join(f'{k}:{v}' for k, v in value.items())
    elif hasattr(value, 'match'):  # Regexp
        value = value.pattern
    elif isinstance(value, (bool, int, float)):
        value = str(value).lower()
    return str(value)

def format_section(stream: TextIO, section: str, options: list[tuple[str, OptionDict, Any]], doc: str | None=None) -> None:
    """Format an option's section using the INI format."""
    if doc:
        print(_comment(normalize_text(doc)), file=stream)
    print(f"[{section}]", file=stream)
    for optname, optdict, value in options:
        help_text = optdict.get('help')
        if help_text:
            help_text = normalize_text(help_text, indent='# ')
            print(file=stream)
            print(help_text, file=stream)
        if value:
            value = _format_option_value(optdict, value)
            print(f"{optname}={value}", file=stream)

def _ini_format(stream: TextIO, options: list[tuple[str, OptionDict, Any]]) -> None:
    """Format options using the INI format."""
    for optname, optdict, value in options:
        value = _format_option_value(optdict, value)
        help_text = optdict.get('help')
        if help_text:
            help_text = normalize_text(help_text, indent='# ')
            print(file=stream)
            print(help_text, file=stream)
        print(f"{optname} = {value}", file=stream)

class IsortDriver:
    """A wrapper around isort API that changed between versions 4 and 5."""

    def __init__(self, config: argparse.Namespace) -> None:
        if HAS_ISORT_5:
            self.isort5_config = isort.settings.Config(extra_standard_library=config.known_standard_library, known_third_party=config.known_third_party)
        else:
            self.isort4_obj = isort.SortImports(file_contents='', known_standard_library=config.known_standard_library, known_third_party=config.known_third_party)
