"""Various helper functions to create the docs of a linter object."""
from __future__ import annotations
import sys
from typing import TYPE_CHECKING, Any, TextIO
from pylint.constants import MAIN_CHECKER_NAME
from pylint.utils.utils import get_rst_section, get_rst_title, normalize_text
if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter

def _get_checkers_infos(linter: PyLinter) -> dict[str, dict[str, Any]]:
    """Get info from a checker and handle KeyError."""
    checkers_infos = {}
    for checker in linter.get_checkers():
        try:
            name = checker.name
            checkers_infos[name] = {
                'options': list(checker.options),
                'msgs': dict(checker.msgs),
                'reports': list(checker.reports),
            }
        except KeyError:
            # Ignore checkers without name, options, msgs or reports
            continue
    return checkers_infos

def _get_global_options_documentation(linter: PyLinter) -> str:
    """Get documentation for the main checker."""
    global_options = []
    for checker in linter.get_checkers():
        if checker.name == MAIN_CHECKER_NAME:
            for option in checker.options:
                option_name, option_dict, option_value = option
                global_options.append((option_name, option_dict, option_value))
    return get_rst_section("Global options", global_options)

def _get_checkers_documentation(linter: PyLinter, show_options: bool=True) -> str:
    """Get documentation for individual checkers."""
    result = []
    for checker in linter.get_checkers():
        if checker.name == MAIN_CHECKER_NAME:
            continue
        result.append(get_rst_title(checker.name.capitalize(), "-"))
        if checker.__doc__:
            result.append(normalize_text(checker.__doc__) + "\n")
        if show_options:
            options = [opt for opt in checker.options if opt[1].get('hide', False)]
            if options:
                result.append(get_rst_section("Options", options))
        messages = sorted(checker.msgs.items())
        if messages:
            result.append(get_rst_section("Messages", messages))
        reports = sorted(checker.reports)
        if reports:
            result.append(get_rst_section("Reports", reports))
    return "\n".join(result)

def print_full_documentation(linter: PyLinter, stream: TextIO=sys.stdout, show_options: bool=True) -> None:
    """Output a full documentation in ReST format."""
    print("Pylint global options and switches", file=stream)
    print("="*40, file=stream)
    print(file=stream)
    print(_get_global_options_documentation(linter), file=stream)
    print("Pylint checkers' options and switches", file=stream)
    print("="*40, file=stream)
    print(file=stream)
    print(_get_checkers_documentation(linter, show_options), file=stream)
