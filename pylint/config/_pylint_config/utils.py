"""Utils for the 'pylint-config' command."""
from __future__ import annotations
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Literal, TypeVar
if sys.version_info >= (3, 10):
    from typing import ParamSpec
else:
    from typing_extensions import ParamSpec
_P = ParamSpec('_P')
_ReturnValueT = TypeVar('_ReturnValueT', bool, str)
SUPPORTED_FORMATS = {'t', 'toml', 'i', 'ini'}
YES_NO_ANSWERS = {'y', 'yes', 'n', 'no'}

class InvalidUserInput(Exception):
    """Raised whenever a user input is invalid."""

    def __init__(self, valid_input: str, input_value: str, *args: object) -> None:
        self.valid = valid_input
        self.input = input_value
        super().__init__(*args)

def should_retry_after_invalid_input(func: Callable[_P, _ReturnValueT]) -> Callable[_P, _ReturnValueT]:
    """Decorator that handles InvalidUserInput exceptions and retries."""
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _ReturnValueT:
        while True:
            try:
                return func(*args, **kwargs)
            except InvalidUserInput as e:
                print(f"Invalid input. {e.valid}. You entered: {e.input}")
                print("Please try again.")
    return wrapper

@should_retry_after_invalid_input
def get_and_validate_format() -> Literal['toml', 'ini']:
    """Make sure that the output format is either .toml or .ini."""
    user_input = input("Enter the output format (toml/ini): ").lower().strip()
    if user_input in {'t', 'toml'}:
        return 'toml'
    if user_input in {'i', 'ini'}:
        return 'ini'
    raise InvalidUserInput("Valid inputs are 'toml' or 'ini'", user_input)

@should_retry_after_invalid_input
def validate_yes_no(question: str, default: Literal['yes', 'no'] | None) -> bool:
    """Validate that a yes or no answer is correct."""
    if default is None:
        prompt = f"{question} (yes/no): "
    elif default == 'yes':
        prompt = f"{question} [Y/n]: "
    else:
        prompt = f"{question} [y/N]: "

    user_input = input(prompt).lower().strip()

    if user_input == '' and default is not None:
        return default == 'yes'
    if user_input in {'y', 'yes'}:
        return True
    if user_input in {'n', 'no'}:
        return False
    raise InvalidUserInput("Please answer 'yes' or 'no'", user_input)

def get_minimal_setting() -> bool:
    """Ask the user if they want to use the minimal setting."""
    return validate_yes_no("Do you want to use the minimal setting?", default='no')

def get_and_validate_output_file() -> tuple[bool, Path]:
    """Make sure that the output file is correct."""
    while True:
        file_path = input("Enter the output file path: ").strip()
        path = Path(file_path)

        if path.exists():
            overwrite = validate_yes_no(f"The file {file_path} already exists. Do you want to overwrite it?", default='no')
            if overwrite:
                return True, path
        else:
            try:
                # Check if we can create the file
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
                path.unlink()  # Remove the test file
                return False, path
            except OSError as e:
                print(f"Error: Unable to create file at {file_path}. {str(e)}")
                retry = validate_yes_no("Do you want to try a different path?", default='yes')
                if not retry:
                    raise InvalidUserInput("Please provide a valid file path", file_path)
