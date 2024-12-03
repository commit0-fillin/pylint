"""Arguments manager class used to handle command-line arguments and options."""
from __future__ import annotations
import argparse
import re
import sys
import textwrap
import warnings
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, TextIO
import tomlkit
from pylint import utils
from pylint.config.argument import _Argument, _CallableArgument, _ExtendArgument, _StoreArgument, _StoreNewNamesArgument, _StoreOldNamesArgument, _StoreTrueArgument
from pylint.config.exceptions import UnrecognizedArgumentAction, _UnrecognizedOptionError
from pylint.config.help_formatter import _HelpFormatter
from pylint.config.utils import _convert_option_to_argument, _parse_rich_type_value
from pylint.constants import MAIN_CHECKER_NAME
from pylint.typing import DirectoryNamespaceDict, OptionDict
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
if TYPE_CHECKING:
    from pylint.config.arguments_provider import _ArgumentsProvider

class _ArgumentsManager:
    """Arguments manager class used to handle command-line arguments and options."""

    def __init__(self, prog: str, usage: str | None=None, description: str | None=None) -> None:
        self._config = argparse.Namespace()
        'Namespace for all options.'
        self._base_config = self._config
        'Fall back Namespace object created during initialization.\n\n        This is necessary for the per-directory configuration support. Whenever we\n        fail to match a file with a directory we fall back to the Namespace object\n        created during initialization.\n        '
        self._arg_parser = argparse.ArgumentParser(prog=prog, usage=usage or '%(prog)s [options]', description=description, formatter_class=_HelpFormatter, conflict_handler='resolve')
        'The command line argument parser.'
        self._argument_groups_dict: dict[str, argparse._ArgumentGroup] = {}
        'Dictionary of all the argument groups.'
        self._option_dicts: dict[str, OptionDict] = {}
        'All option dictionaries that have been registered.'
        self._directory_namespaces: DirectoryNamespaceDict = {}
        'Mapping of directories and their respective namespace objects.'

    @property
    def config(self) -> argparse.Namespace:
        """Namespace for all options."""
        return self._config

    def _register_options_provider(self, provider: _ArgumentsProvider) -> None:
        """Register an options provider and load its defaults."""
        for section, options in provider.options:
            for option in options:
                argument = _convert_option_to_argument(option)
                self._add_arguments_to_parser(section, provider.name, argument)
                self._option_dicts[option['name']] = option
        self._load_default_argument_values()

    def _add_arguments_to_parser(self, section: str, section_desc: str | None, argument: _Argument) -> None:
        """Add an argument to the correct argument section/group."""
        if section not in self._argument_groups_dict:
            self._argument_groups_dict[section] = self._arg_parser.add_argument_group(
                title=section.capitalize(), description=section_desc
            )
        section_group = self._argument_groups_dict[section]
        self._add_parser_option(section_group, argument)

    @staticmethod
    def _add_parser_option(section_group: argparse._ArgumentGroup, argument: _Argument) -> None:
        """Add an argument."""
        try:
            if isinstance(argument, _CallableArgument):
                section_group.add_argument(*argument.args, **argument.kwargs, action=argument)
            else:
                section_group.add_argument(*argument.args, **argument.kwargs)
        except argparse.ArgumentError as exc:
            raise UnrecognizedArgumentAction(str(exc)) from exc

    def _load_default_argument_values(self) -> None:
        """Loads the default values of all registered options."""
        for option_dict in self._option_dicts.values():
            if 'default' in option_dict:
                default = option_dict['default']
                if callable(default):
                    default = default()
                self.set_option(option_dict['name'], default)

    def _parse_configuration_file(self, arguments: list[str]) -> None:
        """Parse the arguments found in a configuration file into the namespace."""
        config_parser = argparse.ArgumentParser(
            prog=self._arg_parser.prog,
            usage=self._arg_parser.usage,
            description=self._arg_parser.description,
            formatter_class=self._arg_parser.formatter_class,
            conflict_handler=self._arg_parser.conflict_handler,
            add_help=False,
        )
        for group in self._arg_parser._action_groups:
            config_parser._action_groups.append(group)

        try:
            parsed_args = config_parser.parse_args(arguments)
        except _UnrecognizedOptionError as exc:
            warnings.warn(f"Unrecognized option in the configuration file: {exc}")
        else:
            for key, value in vars(parsed_args).items():
                if value is not None:
                    self.set_option(key, value)

    def _parse_command_line_configuration(self, arguments: Sequence[str] | None=None) -> list[str]:
        """Parse the arguments found on the command line into the namespace."""
        if arguments is None:
            arguments = sys.argv[1:]
        try:
            args = self._arg_parser.parse_args(arguments)
        except SystemExit:
            self._arg_parser.print_usage()
            sys.exit(2)

        for key, value in vars(args).items():
            if value is not None:
                self.set_option(key, value)

        return self._arg_parser.parse_known_args(arguments)[1]

    def _generate_config(self, stream: TextIO | None=None, skipsections: tuple[str, ...]=()) -> None:
        """Write a configuration file according to the current configuration
        into the given stream or stdout.
        """
        if stream is None:
            stream = sys.stdout

        config = tomlkit.document()
        for section, options in self._option_dicts.items():
            if section in skipsections:
                continue
            if section not in config:
                config[section] = tomlkit.table()
            for option_name, option_dict in options.items():
                value = getattr(self._config, option_name)
                if value != option_dict.get("default"):
                    config[section][option_name] = value

        tomlkit.dump(config, stream)

    def help(self) -> str:
        """Return the usage string based on the available options."""
        return self._arg_parser.format_help()

    def _generate_config_file(self, *, minimal: bool=False) -> str:
        """Write a configuration file according to the current configuration into
        stdout.
        """
        stream = utils.CustomStringIO()
        skipsections = () if not minimal else (MAIN_CHECKER_NAME,)
        self._generate_config(stream=stream, skipsections=skipsections)
        return stream.getvalue()

    def set_option(self, optname: str, value: Any) -> None:
        """Set an option on the namespace object."""
        if optname not in self._option_dicts:
            raise ValueError(f"Unknown option '{optname}'")
        
        option_dict = self._option_dicts[optname]
        if "type" in option_dict:
            try:
                value = _parse_rich_type_value(option_dict["type"], value)
            except ValueError as exc:
                raise ValueError(f"Invalid value for option '{optname}': {exc}") from exc
        
        setattr(self._config, optname, value)
