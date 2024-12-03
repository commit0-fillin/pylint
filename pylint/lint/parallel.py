from __future__ import annotations
import functools
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any
import dill
from pylint import reporters
from pylint.lint.utils import _augment_sys_path
from pylint.message import Message
from pylint.typing import FileItem
from pylint.utils import LinterStats, merge_stats
try:
    import multiprocessing
except ImportError:
    multiprocessing = None
try:
    from concurrent.futures import ProcessPoolExecutor
except ImportError:
    ProcessPoolExecutor = None
if TYPE_CHECKING:
    from pylint.lint import PyLinter
_worker_linter: PyLinter | None = None

def _worker_initialize(linter: bytes, extra_packages_paths: Sequence[str] | None=None) -> None:
    """Function called to initialize a worker for a Process within a concurrent Pool.

    :param linter: A linter-class (PyLinter) instance pickled with dill
    :param extra_packages_paths: Extra entries to be added to `sys.path`
    """
    global _worker_linter
    _worker_linter = dill.loads(linter)
    
    if extra_packages_paths:
        _augment_sys_path(extra_packages_paths)

def _merge_mapreduce_data(linter: PyLinter, all_mapreduce_data: defaultdict[int, list[defaultdict[str, list[Any]]]]) -> None:
    """Merges map/reduce data across workers, invoking relevant APIs on checkers."""
    for checker_id, mapreduce_data_list in all_mapreduce_data.items():
        checker = linter.get_checker_by_id(checker_id)
        if checker and hasattr(checker, 'reduce_map_data'):
            merged_data = defaultdict(list)
            for mapreduce_data in mapreduce_data_list:
                for key, value in mapreduce_data.items():
                    merged_data[key].extend(value)
            checker.reduce_map_data(merged_data)

def check_parallel(linter: PyLinter, jobs: int, files: Iterable[FileItem], extra_packages_paths: Sequence[str] | None=None) -> None:
    """Use the given linter to lint the files with given amount of workers (jobs).

    This splits the work filestream-by-filestream. If you need to do work across
    multiple files, as in the similarity-checker, then implement the map/reduce functionality.
    """
    if multiprocessing is None or ProcessPoolExecutor is None:
        raise ImportError("Multiprocessing is not available.")

    linter_pickle = dill.dumps(linter)
    initializer = functools.partial(_worker_initialize, linter_pickle, extra_packages_paths)

    with ProcessPoolExecutor(max_workers=jobs, initializer=initializer) as executor:
        all_mapreduce_data = defaultdict(list)
        all_stats = []

        for result in executor.map(lambda f: _worker_linter.check_single_file(*f), files):
            if result:
                stats, mapreduce_data = result
                all_stats.append(stats)
                for checker_id, data in mapreduce_data.items():
                    all_mapreduce_data[checker_id].append(data)

    _merge_mapreduce_data(linter, all_mapreduce_data)
    linter.stats = merge_stats(all_stats)
