from __future__ import annotations
import sys
import warnings
from glob import glob
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING
from pylint import reporters
from pylint.config.config_file_parser import _ConfigurationFileParser
from pylint.config.exceptions import ArgumentPreprocessingError, _UnrecognizedOptionError
from pylint.utils import utils
if TYPE_CHECKING:
    from pylint.lint import PyLinter

def _config_initialization(linter: PyLinter, args_list: list[str], reporter: reporters.BaseReporter | reporters.MultiReporter | None=None, config_file: None | str | Path=None, verbose_mode: bool=False) -> list[str]:
    """Parse all available options, read config files and command line arguments and
    set options accordingly.
    """
    config_parser = _ConfigurationFileParser(verbose_mode, linter)
    
    # Parse configuration file if provided
    if config_file:
        config_file = Path(config_file)
        options, _ = config_parser.parse_config_file(config_file)
        linter.read_config_file(options)
    
    # Parse command line arguments
    args_list = linter.load_command_line_configuration(args_list)
    
    if reporter:
        linter.set_reporter(reporter)
    
    # Ensure all plugins are fully loaded
    linter.load_plugin_modules()
    
    return args_list

def _order_all_first(config_args: list[str], *, joined: bool) -> list[str]:
    """Reorder config_args such that --enable=all or --disable=all comes first.

    Raise if both are given.

    If joined is True, expect args in the form '--enable=all,for-any-all'.
    If joined is False, expect args in the form '--enable', 'all,for-any-all'.
    """
    enable_all = None
    disable_all = None
    other_args = []

    for i, arg in enumerate(config_args):
        if joined:
            if arg.startswith('--enable=all'):
                enable_all = arg
            elif arg.startswith('--disable=all'):
                disable_all = arg
            else:
                other_args.append(arg)
        else:
            if arg in ('--enable', '--disable'):
                next_arg = config_args[i + 1] if i + 1 < len(config_args) else ''
                if next_arg.startswith('all'):
                    if arg == '--enable':
                        enable_all = [arg, next_arg]
                    else:
                        disable_all = [arg, next_arg]
                    i += 1  # Skip the next argument
                else:
                    other_args.extend([arg, next_arg])
                    i += 1  # Skip the next argument
            else:
                other_args.append(arg)

    if enable_all and disable_all:
        raise ArgumentPreprocessingError("--enable=all and --disable=all are mutually exclusive")

    result = []
    if enable_all:
        result.extend([enable_all] if joined else enable_all)
    if disable_all:
        result.extend([disable_all] if joined else disable_all)
    result.extend(other_args)

    return result
