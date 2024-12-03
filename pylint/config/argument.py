"""Definition of an Argument class and transformers for various argument types.

An Argument instance represents a pylint option to be handled by an argparse.ArgumentParser
"""
from __future__ import annotations
import argparse
import os
import pathlib
import re
from collections.abc import Callable
from glob import glob
from typing import Any, Literal, Pattern, Sequence, Tuple, Union
from pylint import interfaces
from pylint import utils as pylint_utils
from pylint.config.callback_actions import _CallbackAction
from pylint.config.deprecation_actions import _NewNamesAction, _OldNamesAction
_ArgumentTypes = Union[str, int, float, bool, Pattern[str], Sequence[str], Sequence[Pattern[str]], Tuple[int, ...]]
'List of possible argument types.'

def _confidence_transformer(value: str) -> Sequence[str]:
    """Transforms a comma separated string of confidence values."""
    return [v.strip().upper() for v in value.split(',') if v.strip()]

def _csv_transformer(value: str) -> Sequence[str]:
    """Transforms a comma separated string."""
    return [v.strip() for v in value.split(',') if v.strip()]
YES_VALUES = {'y', 'yes', 'true'}
NO_VALUES = {'n', 'no', 'false'}

def _yn_transformer(value: str) -> bool:
    """Transforms a yes/no or stringified bool into a bool."""
    value = value.lower()
    if value in YES_VALUES:
        return True
    if value in NO_VALUES:
        return False
    raise ValueError(f"Invalid yes/no value: {value}")

def _non_empty_string_transformer(value: str) -> str:
    """Check that a string is not empty and remove quotes."""
    value = value.strip()
    if not value:
        raise ValueError("Empty string is not allowed")
    return pylint_utils._unquote(value)

def _path_transformer(value: str) -> str:
    """Expand user and variables in a path."""
    return os.path.expandvars(os.path.expanduser(value))

def _glob_paths_csv_transformer(value: str) -> Sequence[str]:
    """Transforms a comma separated list of paths while expanding user and
    variables and glob patterns.
    """
    paths = _csv_transformer(value)
    expanded_paths = []
    for path in paths:
        expanded_path = _path_transformer(path)
        expanded_paths.extend(glob(expanded_path, recursive=True))
    return expanded_paths

def _py_version_transformer(value: str) -> tuple[int, ...]:
    """Transforms a version string into a version tuple."""
    return tuple(int(part) for part in value.split('.'))

def _regex_transformer(value: str) -> Pattern[str]:
    """Return `re.compile(value)`."""
    return re.compile(value)

def _regexp_csv_transfomer(value: str) -> Sequence[Pattern[str]]:
    """Transforms a comma separated list of regular expressions."""
    return [_regex_transformer(v) for v in _csv_transformer(value)]

def _regexp_paths_csv_transfomer(value: str) -> Sequence[Pattern[str]]:
    """Transforms a comma separated list of regular expressions paths."""
    paths = _glob_paths_csv_transformer(value)
    return [re.compile(f"^{re.escape(path)}$") for path in paths]
_TYPE_TRANSFORMERS: dict[str, Callable[[str], _ArgumentTypes]] = {'choice': str, 'csv': _csv_transformer, 'float': float, 'int': int, 'confidence': _confidence_transformer, 'non_empty_string': _non_empty_string_transformer, 'path': _path_transformer, 'glob_paths_csv': _glob_paths_csv_transformer, 'py_version': _py_version_transformer, 'regexp': _regex_transformer, 'regexp_csv': _regexp_csv_transfomer, 'regexp_paths_csv': _regexp_paths_csv_transfomer, 'string': pylint_utils._unquote, 'yn': _yn_transformer}
'Type transformers for all argument types.\n\nA transformer should accept a string and return one of the supported\nArgument types. It will only be called when parsing 1) command-line,\n2) configuration files and 3) a string default value.\nNon-string default values are assumed to be of the correct type.\n'

class _Argument:
    """Class representing an argument to be parsed by an argparse.ArgumentsParser.

    This is based on the parameters passed to argparse.ArgumentsParser.add_message.
    See:
    https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument
    """

    def __init__(self, *, flags: list[str], arg_help: str, hide_help: bool, section: str | None) -> None:
        self.flags = flags
        'The name of the argument.'
        self.hide_help = hide_help
        'Whether to hide this argument in the help message.'
        self.help = arg_help.replace('%', '%%')
        'The description of the argument.'
        if hide_help:
            self.help = argparse.SUPPRESS
        self.section = section
        'The section to add this argument to.'

class _BaseStoreArgument(_Argument):
    """Base class for store arguments to be parsed by an argparse.ArgumentsParser.

    This is based on the parameters passed to argparse.ArgumentsParser.add_message.
    See:
    https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument
    """

    def __init__(self, *, flags: list[str], action: str, default: _ArgumentTypes, arg_help: str, hide_help: bool, section: str | None) -> None:
        super().__init__(flags=flags, arg_help=arg_help, hide_help=hide_help, section=section)
        self.action = action
        'The action to perform with the argument.'
        self.default = default
        'The default value of the argument.'

class _StoreArgument(_BaseStoreArgument):
    """Class representing a store argument to be parsed by an argparse.ArgumentsParser.

    This is based on the parameters passed to argparse.ArgumentsParser.add_message.
    See:
    https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument
    """

    def __init__(self, *, flags: list[str], action: str, default: _ArgumentTypes, arg_type: str, choices: list[str] | None, arg_help: str, metavar: str, hide_help: bool, section: str | None) -> None:
        super().__init__(flags=flags, action=action, default=default, arg_help=arg_help, hide_help=hide_help, section=section)
        self.type = _TYPE_TRANSFORMERS[arg_type]
        'A transformer function that returns a transformed type of the argument.'
        self.choices = choices
        'A list of possible choices for the argument.\n\n        None if there are no restrictions.\n        '
        self.metavar = metavar
        'The metavar of the argument.\n\n        See:\n        https://docs.python.org/3/library/argparse.html#metavar\n        '

class _StoreTrueArgument(_BaseStoreArgument):
    """Class representing a 'store_true' argument to be parsed by an
    argparse.ArgumentsParser.

    This is based on the parameters passed to argparse.ArgumentsParser.add_message.
    See:
    https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument
    """

    def __init__(self, *, flags: list[str], action: Literal['store_true'], default: _ArgumentTypes, arg_help: str, hide_help: bool, section: str | None) -> None:
        super().__init__(flags=flags, action=action, default=default, arg_help=arg_help, hide_help=hide_help, section=section)

class _DeprecationArgument(_Argument):
    """Store arguments while also handling deprecation warnings for old and new names.

    This is based on the parameters passed to argparse.ArgumentsParser.add_message.
    See:
    https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument
    """

    def __init__(self, *, flags: list[str], action: type[argparse.Action], default: _ArgumentTypes, arg_type: str, choices: list[str] | None, arg_help: str, metavar: str, hide_help: bool, section: str | None) -> None:
        super().__init__(flags=flags, arg_help=arg_help, hide_help=hide_help, section=section)
        self.action = action
        'The action to perform with the argument.'
        self.default = default
        'The default value of the argument.'
        self.type = _TYPE_TRANSFORMERS[arg_type]
        'A transformer function that returns a transformed type of the argument.'
        self.choices = choices
        'A list of possible choices for the argument.\n\n        None if there are no restrictions.\n        '
        self.metavar = metavar
        'The metavar of the argument.\n\n        See:\n        https://docs.python.org/3/library/argparse.html#metavar\n        '

class _ExtendArgument(_DeprecationArgument):
    """Class for extend arguments to be parsed by an argparse.ArgumentsParser.

    This is based on the parameters passed to argparse.ArgumentsParser.add_message.
    See:
    https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument
    """

    def __init__(self, *, flags: list[str], action: Literal['extend'], default: _ArgumentTypes, arg_type: str, metavar: str, arg_help: str, hide_help: bool, section: str | None, choices: list[str] | None, dest: str | None) -> None:
        action_class = argparse._ExtendAction
        self.dest = dest
        'The destination of the argument.'
        super().__init__(flags=flags, action=action_class, default=default, arg_type=arg_type, choices=choices, arg_help=arg_help, metavar=metavar, hide_help=hide_help, section=section)

class _StoreOldNamesArgument(_DeprecationArgument):
    """Store arguments while also handling old names.

    This is based on the parameters passed to argparse.ArgumentsParser.add_message.
    See:
    https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument
    """

    def __init__(self, *, flags: list[str], default: _ArgumentTypes, arg_type: str, choices: list[str] | None, arg_help: str, metavar: str, hide_help: bool, kwargs: dict[str, Any], section: str | None) -> None:
        super().__init__(flags=flags, action=_OldNamesAction, default=default, arg_type=arg_type, choices=choices, arg_help=arg_help, metavar=metavar, hide_help=hide_help, section=section)
        self.kwargs = kwargs
        'Any additional arguments passed to the action.'

class _StoreNewNamesArgument(_DeprecationArgument):
    """Store arguments while also emitting deprecation warnings.

    This is based on the parameters passed to argparse.ArgumentsParser.add_message.
    See:
    https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument
    """

    def __init__(self, *, flags: list[str], default: _ArgumentTypes, arg_type: str, choices: list[str] | None, arg_help: str, metavar: str, hide_help: bool, kwargs: dict[str, Any], section: str | None) -> None:
        super().__init__(flags=flags, action=_NewNamesAction, default=default, arg_type=arg_type, choices=choices, arg_help=arg_help, metavar=metavar, hide_help=hide_help, section=section)
        self.kwargs = kwargs
        'Any additional arguments passed to the action.'

class _CallableArgument(_Argument):
    """Class representing an callable argument to be parsed by an
    argparse.ArgumentsParser.

    This is based on the parameters passed to argparse.ArgumentsParser.add_message.
    See:
    https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument
    """

    def __init__(self, *, flags: list[str], action: type[_CallbackAction], arg_help: str, kwargs: dict[str, Any], hide_help: bool, section: str | None, metavar: str) -> None:
        super().__init__(flags=flags, arg_help=arg_help, hide_help=hide_help, section=section)
        self.action = action
        'The action to perform with the argument.'
        self.kwargs = kwargs
        'Any additional arguments passed to the action.'
        self.metavar = metavar
        'The metavar of the argument.\n\n        See:\n        https://docs.python.org/3/library/argparse.html#metavar\n        '
