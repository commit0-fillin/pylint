"""Utils for arguments/options parsing and handling."""
from __future__ import annotations
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any
from pylint import extensions, utils
from pylint.config.argument import _CallableArgument, _ExtendArgument, _StoreArgument, _StoreNewNamesArgument, _StoreOldNamesArgument, _StoreTrueArgument
from pylint.config.callback_actions import _CallbackAction
from pylint.config.exceptions import ArgumentPreprocessingError
if TYPE_CHECKING:
    from pylint.lint.run import Run

def _convert_option_to_argument(opt: str, optdict: dict[str, Any]) -> _StoreArgument | _StoreTrueArgument | _CallableArgument | _StoreOldNamesArgument | _StoreNewNamesArgument | _ExtendArgument:
    """Convert an optdict to an Argument class instance."""
    action = optdict.get('action', 'store')
    default = optdict.get('default')
    metavar = optdict.get('metavar')
    hide_help = optdict.get('hide_help', False)
    section = optdict.get('group')
    
    if action == 'callback':
        return _CallableArgument(
            flags=[opt],
            action=optdict['callback'],
            arg_help=optdict.get('help', ''),
            kwargs=optdict,
            hide_help=hide_help,
            section=section,
            metavar=metavar
        )
    elif action == 'store_true':
        return _StoreTrueArgument(
            flags=[opt],
            action=action,
            default=default,
            arg_help=optdict.get('help', ''),
            hide_help=hide_help,
            section=section
        )
    elif action == 'extend':
        return _ExtendArgument(
            flags=[opt],
            action=action,
            default=default,
            arg_type=optdict.get('type', 'string'),
            metavar=metavar,
            arg_help=optdict.get('help', ''),
            hide_help=hide_help,
            section=section,
            choices=optdict.get('choices'),
            dest=optdict.get('dest')
        )
    elif 'old_names' in optdict:
        return _StoreOldNamesArgument(
            flags=[opt],
            default=default,
            arg_type=optdict.get('type', 'string'),
            choices=optdict.get('choices'),
            arg_help=optdict.get('help', ''),
            metavar=metavar,
            hide_help=hide_help,
            kwargs=optdict,
            section=section
        )
    elif 'new_names' in optdict:
        return _StoreNewNamesArgument(
            flags=[opt],
            default=default,
            arg_type=optdict.get('type', 'string'),
            choices=optdict.get('choices'),
            arg_help=optdict.get('help', ''),
            metavar=metavar,
            hide_help=hide_help,
            kwargs=optdict,
            section=section
        )
    else:
        return _StoreArgument(
            flags=[opt],
            action=action,
            default=default,
            arg_type=optdict.get('type', 'string'),
            choices=optdict.get('choices'),
            arg_help=optdict.get('help', ''),
            metavar=metavar,
            hide_help=hide_help,
            section=section
        )

def _parse_rich_type_value(value: Any) -> str:
    """Parse rich (toml) types into strings."""
    if isinstance(value, (list, tuple)):
        return ','.join(str(item) for item in value)
    elif isinstance(value, bool):
        return str(value).lower()
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, str):
        return value
    else:
        raise ValueError(f"Unsupported type for value: {type(value)}")

def _init_hook(run: Run, value: str | None) -> None:
    """Execute arbitrary code from the init_hook.

    This can be used to set the 'sys.path' for example.
    """
    if value:
        exec(value)

def _set_rcfile(run: Run, value: str | None) -> None:
    """Set the rcfile."""
    if value:
        run._rcfile = value

def _set_output(run: Run, value: str | None) -> None:
    """Set the output."""
    if value:
        run._output = value

def _add_plugins(run: Run, value: str | None) -> None:
    """Add plugins to the list of loadable plugins."""
    if value:
        run._plugins.extend(value.split(','))

def _enable_all_extensions(run: Run, value: str | None) -> None:
    """Enable all extensions."""
    from pylint import extensions
    run._plugins.extend(extensions.__all__)
PREPROCESSABLE_OPTIONS: dict[str, tuple[bool, Callable[[Run, str | None], None], int]] = {'--init-hook': (True, _init_hook, 8), '--rcfile': (True, _set_rcfile, 4), '--output': (True, _set_output, 0), '--load-plugins': (True, _add_plugins, 5), '--verbose': (False, _set_verbose_mode, 4), '-v': (False, _set_verbose_mode, 2), '--enable-all-extensions': (False, _enable_all_extensions, 9)}

def _preprocess_options(run: Run, args: Sequence[str]) -> list[str]:
    """Pre-process options before full config parsing has started."""
    remaining_args = list(args)
    i = 0
    while i < len(remaining_args):
        arg = remaining_args[i]
        if arg.startswith('--'):
            option = arg.split('=')[0]
            if option in PREPROCESSABLE_OPTIONS:
                preprocessable, action, takearg = PREPROCESSABLE_OPTIONS[option]
                if takearg:
                    if '=' in arg:
                        opt, value = arg.split('=', 1)
                    else:
                        value = remaining_args[i + 1] if i + 1 < len(remaining_args) else None
                        if value and not value.startswith('-'):
                            del remaining_args[i + 1]
                        else:
                            value = None
                else:
                    value = None

                if preprocessable:
                    action(run, value)
                    del remaining_args[i]
                    continue
        i += 1
    return remaining_args
