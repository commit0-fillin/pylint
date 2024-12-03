from __future__ import annotations
import os
from collections.abc import Iterator
from pathlib import Path
from pylint.testutils.functional.test_file import FunctionalTestFile
REASONABLY_DISPLAYABLE_VERTICALLY = 49
"'Wet finger' number of files that are reasonable to display by an IDE.\n\n'Wet finger' as in 'in my settings there are precisely this many'.\n"
IGNORED_PARENT_DIRS = {'deprecated_relative_import', 'ext', 'regression', 'regression_02'}
'Direct parent directories that should be ignored.'
IGNORED_PARENT_PARENT_DIRS = {'docparams', 'deprecated_relative_import', 'ext'}
'Parents of direct parent directories that should be ignored.'

def get_functional_test_files_from_directory(input_dir: Path | str, max_file_per_directory: int=REASONABLY_DISPLAYABLE_VERTICALLY) -> list[FunctionalTestFile]:
    """Get all functional tests in the input_dir."""
    input_dir = Path(input_dir)
    _check_functional_tests_structure(input_dir, max_file_per_directory)
    
    functional_tests = []
    for root, _, files in os.walk(input_dir):
        root_path = Path(root)
        if root_path.name.startswith('_') or root_path.name in IGNORED_PARENT_DIRS or root_path.parent.name in IGNORED_PARENT_PARENT_DIRS:
            continue
        
        python_files = [f for f in files if f.endswith('.py') and not f.startswith('_')]
        for file in python_files:
            functional_tests.append(FunctionalTestFile(str(root_path), file))
    
    return functional_tests

def _check_functional_tests_structure(directory: Path, max_file_per_directory: int) -> None:
    """Check if test directories follow correct file/folder structure.

    Ignore underscored directories or files.
    """
    for root, dirs, files in os.walk(directory):
        root_path = Path(root)
        if root_path.name.startswith('_'):
            continue
        
        python_files = [f for f in files if f.endswith('.py') and not f.startswith('_')]
        if len(python_files) > max_file_per_directory:
            raise ValueError(f"Directory {root} contains {len(python_files)} Python files, "
                             f"which exceeds the maximum of {max_file_per_directory}.")
        
        for file in python_files:
            file_path = root_path / file
            try:
                FunctionalTestFile(str(root_path), file)
            except NoFileError:
                raise ValueError(f"File {file_path} is not a valid functional test file.")
        
        # Remove directories starting with underscore from further processing
        dirs[:] = [d for d in dirs if not d.startswith('_')]
