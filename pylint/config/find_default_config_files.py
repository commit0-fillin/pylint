from __future__ import annotations
import configparser
import os
import sys
from collections.abc import Iterator
from pathlib import Path
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
RC_NAMES = (Path('pylintrc'), Path('pylintrc.toml'), Path('.pylintrc'), Path('.pylintrc.toml'))
PYPROJECT_NAME = Path('pyproject.toml')
CONFIG_NAMES = (*RC_NAMES, PYPROJECT_NAME, Path('setup.cfg'))

def _find_pyproject() -> Path:
    """Search for file pyproject.toml in the parent directories recursively.

    It resolves symlinks, so if there is any symlink up in the tree, it does not respect them
    """
    current_dir = Path.cwd().resolve()
    while current_dir != current_dir.parent:
        pyproject = current_dir / PYPROJECT_NAME
        if pyproject.is_file():
            return pyproject
        current_dir = current_dir.parent
    return Path()

def _yield_default_files() -> Iterator[Path]:
    """Iterate over the default config file names and see if they exist."""
    for config_name in CONFIG_NAMES:
        config_path = Path.cwd() / config_name
        if config_path.is_file():
            yield config_path

def _find_project_config() -> Iterator[Path]:
    """Traverse up the directory tree to find a config file.

    Stop if no '__init__' is found and thus we are no longer in a package.
    """
    current_dir = Path.cwd()
    while current_dir != current_dir.parent:
        if not (current_dir / '__init__.py').exists():
            break
        for config_name in CONFIG_NAMES:
            config_path = current_dir / config_name
            if config_path.is_file():
                yield config_path
        current_dir = current_dir.parent

def _find_config_in_home_or_environment() -> Iterator[Path]:
    """Find a config file in the specified environment var or the home directory."""
    env_config = os.environ.get('PYLINTRC')
    if env_config:
        env_config_path = Path(env_config)
        if env_config_path.is_file():
            yield env_config_path

    home = Path.home()
    for rc_name in RC_NAMES:
        home_config = home / rc_name
        if home_config.is_file():
            yield home_config

def find_default_config_files() -> Iterator[Path]:
    """Find all possible config files."""
    yield from _yield_default_files()
    yield from _find_project_config()
    yield from _find_config_in_home_or_environment()
    pyproject = _find_pyproject()
    if pyproject.is_file():
        yield pyproject
