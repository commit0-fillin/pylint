from __future__ import annotations
import csv
import operator
import platform
import sys
from collections import Counter
from io import StringIO
from pathlib import Path
from typing import Counter as CounterType
from typing import TextIO, Tuple
import pytest
from _pytest.config import Config
from pylint import checkers
from pylint.config.config_initialization import _config_initialization
from pylint.constants import IS_PYPY
from pylint.lint import PyLinter
from pylint.message.message import Message
from pylint.testutils.constants import _EXPECTED_RE, _OPERATORS, UPDATE_OPTION
from pylint.testutils.functional.test_file import FunctionalTestFile, NoFileError, parse_python_version
from pylint.testutils.output_line import OutputLine
from pylint.testutils.reporter_for_tests import FunctionalTestReporter
MessageCounter = CounterType[Tuple[int, str]]
PYLINTRC = Path(__file__).parent / 'testing_pylintrc'

class LintModuleTest:
    maxDiff = None

    def __init__(self, test_file: FunctionalTestFile, config: Config | None=None) -> None:
        _test_reporter = FunctionalTestReporter()
        self._linter = PyLinter()
        self._linter.config.persistent = 0
        checkers.initialize(self._linter)
        rc_file: Path | str = PYLINTRC
        try:
            rc_file = test_file.option_file
            self._linter.disable('suppressed-message')
            self._linter.disable('locally-disabled')
            self._linter.disable('useless-suppression')
        except NoFileError:
            pass
        self._test_file = test_file
        try:
            args = [test_file.source]
        except NoFileError:
            args = ['']
        if config and config.getoption('minimal_messages_config'):
            with self._open_source_file() as f:
                messages_to_enable = {msg[1] for msg in self.get_expected_messages(f)}
                messages_to_enable.add('astroid-error')
                messages_to_enable.add('fatal')
                messages_to_enable.add('syntax-error')
            args.extend(['--disable=all', f'--enable={','.join(messages_to_enable)}'])
        self._linter._arg_parser.add_argument('--min_pyver', type=parse_python_version, default=(2, 5))
        self._linter._arg_parser.add_argument('--max_pyver', type=parse_python_version, default=(4, 0))
        self._linter._arg_parser.add_argument('--min_pyver_end_position', type=parse_python_version, default=(3, 8))
        self._linter._arg_parser.add_argument('--requires', type=lambda s: [i.strip() for i in s.split(',')], default=[])
        self._linter._arg_parser.add_argument('--except_implementations', type=lambda s: [i.strip() for i in s.split(',')], default=[])
        self._linter._arg_parser.add_argument('--exclude_platforms', type=lambda s: [i.strip() for i in s.split(',')], default=[])
        self._linter._arg_parser.add_argument('--exclude_from_minimal_messages_config', default=False)
        _config_initialization(self._linter, args_list=args, config_file=rc_file, reporter=_test_reporter)
        self._check_end_position = sys.version_info >= self._linter.config.min_pyver_end_position
        if self._check_end_position and IS_PYPY:
            self._check_end_position = sys.version_info >= (3, 9)
        self._config = config

    def __str__(self) -> str:
        return f'{self._test_file.base} ({self.__class__.__module__}.{self.__class__.__name__})'

    @staticmethod
    def get_expected_messages(stream: TextIO) -> MessageCounter:
        """Parses a file and get expected messages.

        :param stream: File-like input stream.
        :type stream: enumerable
        :returns: A dict mapping line,msg-symbol tuples to the count on this line.
        :rtype: dict
        """
        message_counter: MessageCounter = Counter()
        for i, line in enumerate(stream, start=1):
            match = _EXPECTED_RE.search(line)
            if match:
                line_num = int(match.group('line') or i)
                msg_id = match.group('msg_id')
                message_counter[(line_num, msg_id)] += 1
        return message_counter

    @staticmethod
    def multiset_difference(expected_entries: MessageCounter, actual_entries: MessageCounter) -> tuple[MessageCounter, dict[tuple[int, str], int]]:
        """Takes two multisets and compares them.

        A multiset is a dict with the cardinality of the key as the value.
        """
        missing_entries = Counter()
        unexpected_entries = {}
        for key, count in expected_entries.items():
            if key not in actual_entries:
                missing_entries[key] = count
            elif actual_entries[key] < count:
                missing_entries[key] = count - actual_entries[key]
        for key, count in actual_entries.items():
            if key not in expected_entries:
                unexpected_entries[key] = count
            elif count > expected_entries[key]:
                unexpected_entries[key] = count - expected_entries[key]
        return missing_entries, unexpected_entries

    def _check_output_text(self, _: MessageCounter, expected_output: list[OutputLine], actual_output: list[OutputLine]) -> None:
        """This is a function because we want to be able to update the text in
        LintModuleOutputUpdate.
        """
        assert len(expected_output) == len(actual_output)
        for expected, actual in zip(expected_output, actual_output):
            assert expected == actual, f"Expected: {expected}\nGot: {actual}"
