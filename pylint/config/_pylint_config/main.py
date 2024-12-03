"""Everything related to the 'pylint-config' command."""
from __future__ import annotations
from typing import TYPE_CHECKING
from pylint.config._pylint_config.generate_command import handle_generate_command
from pylint.config._pylint_config.help_message import get_help
if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter

def _handle_pylint_config_commands(linter: PyLinter) -> int:
    """Handle whichever command is passed to 'pylint-config'."""
    command = linter.config.pylint_config_command

    if command == "generate":
        return handle_generate_command(linter)
    elif command == "help":
        print(get_help(linter._arg_parser))
        return 0
    else:
        print(f"Unknown command: {command}")
        print(get_help(linter._arg_parser))
        return 1
