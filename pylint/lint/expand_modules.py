from __future__ import annotations
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from re import Pattern
from astroid import modutils
from pylint.typing import ErrorDescriptionDict, ModuleDescriptionDict

def discover_package_path(modulepath: str, source_roots: Sequence[str]) -> str:
    """Discover package path from one its modules and source roots."""
    for source_root in source_roots:
        root_path = Path(source_root).resolve()
        module_path = Path(modulepath).resolve()
        try:
            relative_path = module_path.relative_to(root_path)
            package_path = str(root_path / relative_path.parts[0])
            return package_path
        except ValueError:
            continue
    return os.path.dirname(modulepath)

def _is_in_ignore_list_re(element: str, ignore_list_re: list[Pattern[str]]) -> bool:
    """Determines if the element is matched in a regex ignore-list."""
    return any(pattern.search(element) for pattern in ignore_list_re)

def expand_modules(files_or_modules: Sequence[str], source_roots: Sequence[str], ignore_list: list[str], ignore_list_re: list[Pattern[str]], ignore_list_paths_re: list[Pattern[str]]) -> tuple[dict[str, ModuleDescriptionDict], list[ErrorDescriptionDict]]:
    """Take a list of files/modules/packages and return the list of tuple
    (file, module name) which have to be actually checked.
    """
    result: dict[str, ModuleDescriptionDict] = {}
    errors: list[ErrorDescriptionDict] = []

    for name in files_or_modules:
        if name in ignore_list or _is_in_ignore_list_re(name, ignore_list_re):
            continue

        try:
            modpath = modutils.file_from_modpath(name.split("."))
        except ImportError:
            modpath = modutils.file_from_modpath(name.split("."), path=sys.path[:])
        except SyntaxError:
            errors.append({"key": name, "mod": name, "ex": sys.exc_info()[1]})
            continue

        if modpath is None:
            errors.append({"key": name, "mod": name, "ex": f"Module {name} not found"})
            continue

        if _is_in_ignore_list_re(modpath, ignore_list_paths_re):
            continue

        package_path = discover_package_path(modpath, source_roots)
        if os.path.basename(modpath) == "__init__.py":
            for root, _, files in os.walk(os.path.dirname(modpath)):
                for file in files:
                    if file.endswith(".py"):
                        filepath = os.path.join(root, file)
                        if not _is_in_ignore_list_re(filepath, ignore_list_paths_re):
                            result[filepath] = {"path": filepath, "name": modutils.modpath_from_file(filepath), "package": package_path}
        else:
            result[modpath] = {"path": modpath, "name": name, "package": package_path}

    return result, errors
