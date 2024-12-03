"""Configuration file parser class."""
from __future__ import annotations
import configparser
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Tuple
from pylint.config.utils import _parse_rich_type_value
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
if TYPE_CHECKING:
    from pylint.lint import PyLinter
PylintConfigFileData = Tuple[Dict[str, str], List[str]]

class _RawConfParser:
    """Class to parse various formats of configuration files."""

    @staticmethod
    def parse_ini_file(file_path: Path) -> PylintConfigFileData:
        """Parse and handle errors of an ini configuration file.

        Raises ``configparser.Error``.
        """
        parser = configparser.ConfigParser()
        parser.read(file_path)
        
        options = {}
        for section in parser.sections():
            for option, value in parser.items(section):
                options[f"{section}.{option}"] = value
        
        if not options:
            # If no sections were found, try parsing without sections
            for option, value in parser.items('DEFAULT'):
                options[option] = value
        
        return options, []

    @staticmethod
    def _ini_file_with_sections(file_path: Path) -> bool:
        """Return whether the file uses sections."""
        with file_path.open() as file:
            return any(line.strip().startswith('[') and line.strip().endswith(']') for line in file)

    @staticmethod
    def parse_toml_file(file_path: Path) -> PylintConfigFileData:
        """Parse and handle errors of a toml configuration file.

        Raises ``tomllib.TOMLDecodeError``.
        """
        with file_path.open("rb") as file:
            toml_dict = tomllib.load(file)
        
        options = {}
        for section, values in toml_dict.items():
            if isinstance(values, dict):
                for key, value in values.items():
                    options[f"{section}.{key}"] = _parse_rich_type_value(value)
            else:
                options[section] = _parse_rich_type_value(values)
        
        return options, []

    @staticmethod
    def parse_config_file(file_path: Path | None, verbose: bool) -> PylintConfigFileData:
        """Parse a config file and return str-str pairs.

        Raises ``tomllib.TOMLDecodeError``, ``configparser.Error``.
        """
        if file_path is None:
            return {}, []
        
        if verbose:
            print(f"Using config file {file_path}")
        
        if file_path.suffix.lower() in ('.toml', '.lock'):
            return _RawConfParser.parse_toml_file(file_path)
        else:
            return _RawConfParser.parse_ini_file(file_path)

class _ConfigurationFileParser:
    """Class to parse various formats of configuration files."""

    def __init__(self, verbose: bool, linter: PyLinter) -> None:
        self.verbose_mode = verbose
        self.linter = linter

    def parse_config_file(self, file_path: Path | None) -> PylintConfigFileData:
        """Parse a config file and return str-str pairs."""
        try:
            return _RawConfParser.parse_config_file(file_path, self.verbose_mode)
        except (tomllib.TOMLDecodeError, configparser.Error) as exc:
            self.linter.add_message('config-parse-error', args=(file_path, exc))
            return {}, []
