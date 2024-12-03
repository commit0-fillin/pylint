"""Utility functions for configuration testing."""
from __future__ import annotations
import copy
import json
import logging
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import Mock
from pylint.lint import Run
ConfigurationValue = Any
PylintConfiguration = Dict[str, ConfigurationValue]

def get_expected_or_default(tested_configuration_file: str | Path, suffix: str, default: str) -> str:
    """Return the expected value from the file if it exists, or the given default."""
    expected_file = Path(tested_configuration_file).with_suffix(suffix)
    if expected_file.exists():
        with expected_file.open("r", encoding="utf-8") as f:
            return f.read().strip()
    return default
EXPECTED_CONF_APPEND_KEY = 'functional_append'
EXPECTED_CONF_REMOVE_KEY = 'functional_remove'

def get_expected_configuration(configuration_path: str, default_configuration: PylintConfiguration) -> PylintConfiguration:
    """Get the expected parsed configuration of a configuration functional test."""
    expected_configuration = copy.deepcopy(default_configuration)
    expected_file = Path(configuration_path).with_suffix('.expected.json')
    
    if expected_file.exists():
        with expected_file.open("r", encoding="utf-8") as f:
            expected_data = json.load(f)
            
        for key, value in expected_data.get(EXPECTED_CONF_APPEND_KEY, {}).items():
            if key in expected_configuration:
                expected_configuration[key].extend(value)
            else:
                expected_configuration[key] = value
        
        for key, value in expected_data.get(EXPECTED_CONF_REMOVE_KEY, {}).items():
            if key in expected_configuration:
                for item in value:
                    if item in expected_configuration[key]:
                        expected_configuration[key].remove(item)
    
    return expected_configuration

def get_related_files(tested_configuration_file: str | Path, suffix_filter: str) -> list[Path]:
    """Return all the file related to a test conf file ending with a suffix."""
    tested_configuration_file = Path(tested_configuration_file)
    return [
        file for file in tested_configuration_file.parent.glob(f"{tested_configuration_file.stem}*")
        if file.suffix.endswith(suffix_filter)
    ]

def get_expected_output(configuration_path: str | Path, user_specific_path: Path) -> tuple[int, str]:
    """Get the expected output of a functional test."""
    configuration_path = Path(configuration_path)
    expected_output_file = configuration_path.with_suffix('.expected.out')
    
    if expected_output_file.exists():
        with expected_output_file.open("r", encoding="utf-8") as f:
            expected_output = f.read().strip()
    else:
        expected_output = ""
    
    expected_return_code_file = configuration_path.with_suffix('.expected.rc')
    if expected_return_code_file.exists():
        with expected_return_code_file.open("r", encoding="utf-8") as f:
            expected_return_code = int(f.read().strip())
    else:
        expected_return_code = 0
    
    expected_output = expected_output.replace(
        str(user_specific_path), str(configuration_path.parent)
    )
    
    return expected_return_code, expected_output

def run_using_a_configuration_file(configuration_path: Path | str, file_to_lint: str=__file__) -> tuple[Mock, Mock, Run]:
    """Simulate a run with a configuration without really launching the checks."""
    configuration_path = Path(configuration_path)
    args = ["--rcfile", str(configuration_path), file_to_lint]
    
    with unittest.mock.patch("sys.stdout", new_callable=unittest.mock.StringIO) as stdout_mock:
        with unittest.mock.patch("sys.stderr", new_callable=unittest.mock.StringIO) as stderr_mock:
            with unittest.mock.patch("pylint.lint.pylinter.PyLinter.check"):
                run = Run(args, exit=False)
    
    return stdout_mock, stderr_mock, run
