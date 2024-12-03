from __future__ import annotations
import os
import sys
import warnings
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar
from pylint import config
from pylint.checkers.utils import clear_lru_caches
from pylint.config._pylint_config import _handle_pylint_config_commands, _register_generate_config_options
from pylint.config.config_initialization import _config_initialization
from pylint.config.exceptions import ArgumentPreprocessingError
from pylint.config.utils import _preprocess_options
from pylint.constants import full_version
from pylint.lint.base_options import _make_run_options
from pylint.lint.pylinter import MANAGER, PyLinter
from pylint.reporters.base_reporter import BaseReporter
try:
    import multiprocessing
    from multiprocessing import synchronize
except ImportError:
    multiprocessing = None
try:
    from concurrent.futures import ProcessPoolExecutor
except ImportError:
    ProcessPoolExecutor = None

def _query_cpu() -> int | None:
    """Try to determine number of CPUs allotted in a docker container.

    This is based on discussion and copied from suggestions in
    https://bugs.python.org/issue36054.
    """
    try:
        with open('/sys/fs/cgroup/cpu/cpu.cfs_quota_us') as quota_file:
            quota = int(quota_file.read())
        with open('/sys/fs/cgroup/cpu/cpu.cfs_period_us') as period_file:
            period = int(period_file.read())
        if quota > 0 and period > 0:
            return max(1, quota // period)
    except (FileNotFoundError, ValueError, ZeroDivisionError):
        pass
    return None

def _cpu_count() -> int:
    """Use sched_affinity if available for virtualized or containerized
    environments.
    """
    try:
        import psutil
        return len(psutil.Process().cpu_affinity())
    except (ImportError, AttributeError):
        pass

    try:
        import os
        return len(os.sched_getaffinity(0))
    except AttributeError:
        pass

    docker_cpu = _query_cpu()
    if docker_cpu is not None:
        return docker_cpu

    try:
        import multiprocessing
        return multiprocessing.cpu_count()
    except (ImportError, NotImplementedError):
        return 1

class Run:
    """Helper class to use as main for pylint with 'run(*sys.argv[1:])'."""
    LinterClass = PyLinter
    option_groups = (('Commands', 'Options which are actually commands. Options in this group are mutually exclusive.'),)
    _is_pylint_config: ClassVar[bool] = False
    "Boolean whether or not this is a 'pylint-config' run.\n\n    Used by _PylintConfigRun to make the 'pylint-config' command work.\n    "

    def __init__(self, args: Sequence[str], reporter: BaseReporter | None=None, exit: bool=True) -> None:
        if '--version' in args:
            print(full_version)
            sys.exit(0)
        self._rcfile: str | None = None
        self._output: str | None = None
        self._plugins: list[str] = []
        self.verbose: bool = False
        try:
            args = _preprocess_options(self, args)
        except ArgumentPreprocessingError as ex:
            print(ex, file=sys.stderr)
            sys.exit(32)
        if self._rcfile is None:
            default_file = next(config.find_default_config_files(), None)
            if default_file:
                self._rcfile = str(default_file)
        self.linter = linter = self.LinterClass(_make_run_options(self), option_groups=self.option_groups, pylintrc=self._rcfile)
        linter.load_default_plugins()
        linter.load_plugin_modules(self._plugins)
        if self._is_pylint_config:
            _register_generate_config_options(linter._arg_parser)
        args = _config_initialization(linter, args, reporter, config_file=self._rcfile, verbose_mode=self.verbose)
        if self._is_pylint_config:
            warnings.warn("NOTE: The 'pylint-config' command is experimental and usage can change", UserWarning, stacklevel=2)
            code = _handle_pylint_config_commands(linter)
            if exit:
                sys.exit(code)
            return
        if not args or len(linter.config.disable) == len(linter.msgs_store._messages_definitions):
            print('No files to lint: exiting.')
            sys.exit(32)
        if linter.config.jobs < 0:
            print(f'Jobs number ({linter.config.jobs}) should be greater than or equal to 0', file=sys.stderr)
            sys.exit(32)
        if linter.config.jobs > 1 or linter.config.jobs == 0:
            if ProcessPoolExecutor is None:
                print('concurrent.futures module is missing, fallback to single process', file=sys.stderr)
                linter.set_option('jobs', 1)
            elif linter.config.jobs == 0:
                linter.config.jobs = _cpu_count()
        if self._output:
            try:
                with open(self._output, 'w', encoding='utf-8') as output:
                    linter.reporter.out = output
                    linter.check(args)
                    score_value = linter.generate_reports(verbose=self.verbose)
            except OSError as ex:
                print(ex, file=sys.stderr)
                sys.exit(32)
        else:
            linter.check(args)
            score_value = linter.generate_reports(verbose=self.verbose)
        if linter.config.clear_cache_post_run:
            clear_lru_caches()
            MANAGER.clear_cache()
        if exit:
            if linter.config.exit_zero:
                sys.exit(0)
            elif linter.any_fail_on_issues():
                sys.exit(self.linter.msg_status or 1)
            elif score_value is not None:
                if score_value >= linter.config.fail_under:
                    sys.exit(0)
                else:
                    sys.exit(self.linter.msg_status or 1)
            else:
                sys.exit(self.linter.msg_status)

class _PylintConfigRun(Run):
    """A private wrapper for the 'pylint-config' command."""
    _is_pylint_config: ClassVar[bool] = True
    "Boolean whether or not this is a 'pylint-config' run.\n\n    Used by _PylintConfigRun to make the 'pylint-config' command work.\n    "
