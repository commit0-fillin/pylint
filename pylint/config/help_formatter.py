from __future__ import annotations
import argparse
from pylint.config.callback_actions import _CallbackAction
from pylint.constants import DEFAULT_PYLINT_HOME

class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Formatter for the help message emitted by argparse."""

    def _get_help_string(self, action: argparse.Action) -> str | None:
        """Copied from argparse.ArgumentDefaultsHelpFormatter."""
        help_text = action.help
        if '%(default)' not in action.help:
            if action.default is not argparse.SUPPRESS:
                defaulting_nargs = [argparse.OPTIONAL, argparse.ZERO_OR_MORE]
                if action.option_strings or action.nargs in defaulting_nargs:
                    help_text += ' (default: %(default)s)'
        if isinstance(action, _CallbackAction):
            help_text += "\nCallback: " + action.callback.__name__
        return help_text
