from __future__ import annotations
import argparse
import configparser
import shlex
from pathlib import Path
from typing import NamedTuple, TypedDict
from pylint.pyreverse.main import DEFAULT_COLOR_PALETTE

class PyreverseConfig(argparse.Namespace):
    """Holds the configuration options for Pyreverse.

    The default values correspond to the defaults of the options' parser.
    """

    def __init__(self, mode: str='PUB_ONLY', classes: list[str] | None=None, show_ancestors: int | None=None, all_ancestors: bool | None=None, show_associated: int | None=None, all_associated: bool | None=None, no_standalone: bool=False, show_builtin: bool=False, show_stdlib: bool=False, module_names: bool | None=None, only_classnames: bool=False, output_format: str='dot', colorized: bool=False, max_color_depth: int=2, color_palette: tuple[str, ...]=DEFAULT_COLOR_PALETTE, ignore_list: tuple[str, ...]=tuple(), project: str='', output_directory: str='') -> None:
        super().__init__()
        self.mode = mode
        if classes:
            self.classes = classes
        else:
            self.classes = []
        self.show_ancestors = show_ancestors
        self.all_ancestors = all_ancestors
        self.show_associated = show_associated
        self.all_associated = all_associated
        self.no_standalone = no_standalone
        self.show_builtin = show_builtin
        self.show_stdlib = show_stdlib
        self.module_names = module_names
        self.only_classnames = only_classnames
        self.output_format = output_format
        self.colorized = colorized
        self.max_color_depth = max_color_depth
        self.color_palette = color_palette
        self.ignore_list = ignore_list
        self.project = project
        self.output_directory = output_directory

class TestFileOptions(TypedDict):
    source_roots: list[str]
    output_formats: list[str]
    command_line_args: list[str]

class FunctionalPyreverseTestfile(NamedTuple):
    """Named tuple containing the test file and the expected output."""
    source: Path
    options: TestFileOptions

def get_functional_test_files(root_directory: Path) -> list[FunctionalPyreverseTestfile]:
    """Get all functional test files from the given directory."""
    test_files = []
    for source_file in root_directory.glob("**/*.py"):
        config_file = source_file.with_suffix(".rc")
        if config_file.exists():
            options = _parse_config_file(config_file)
            test_files.append(FunctionalPyreverseTestfile(source=source_file, options=options))
    return test_files

def _parse_config_file(config_file: Path) -> TestFileOptions:
    """Parse the configuration file for a test."""
    config = configparser.ConfigParser()
    config.read(config_file)
    
    options: TestFileOptions = {
        "source_roots": [],
        "output_formats": [],
        "command_line_args": []
    }
    
    if config.has_section("options"):
        if config.has_option("options", "source_roots"):
            options["source_roots"] = [s.strip() for s in config.get("options", "source_roots").split(",")]
        if config.has_option("options", "output_formats"):
            options["output_formats"] = [s.strip() for s in config.get("options", "output_formats").split(",")]
        if config.has_option("options", "command_line_args"):
            options["command_line_args"] = shlex.split(config.get("options", "command_line_args"))
    
    return options
