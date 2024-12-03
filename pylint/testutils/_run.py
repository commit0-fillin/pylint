"""Classes and functions used to mimic normal pylint runs.

This module is considered private and can change at any time.
"""
from __future__ import annotations
from collections.abc import Sequence
from pylint.lint import Run as LintRun
from pylint.reporters.base_reporter import BaseReporter
from pylint.testutils.lint_module_test import PYLINTRC, Path

def _add_rcfile_default_pylintrc(args: list[str]) -> list[str]:
    """Add a default pylintrc with the rcfile option in a list of pylint args."""
    if not any(arg.startswith('--rcfile=') for arg in args):
        args.append(f'--rcfile={PYLINTRC}')
    return args

class _Run(LintRun):
    """Like Run, but we're using an explicitly set empty pylintrc.

    We don't want to use the project's pylintrc during tests, because
    it means that a change in our config could break tests.
    But we want to see if the changes to the default break tests.
    """

    def __init__(self, args: Sequence[str], reporter: BaseReporter | None=None, exit: bool=True) -> None:
        args = _add_rcfile_default_pylintrc(list(args))
        super().__init__(args, reporter, exit)
