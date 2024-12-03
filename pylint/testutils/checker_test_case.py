from __future__ import annotations
import contextlib
from collections.abc import Generator, Iterator
from typing import Any
from astroid import nodes
from pylint.constants import IS_PYPY, PY39_PLUS
from pylint.testutils.global_test_linter import linter
from pylint.testutils.output_line import MessageTest
from pylint.testutils.unittest_linter import UnittestLinter
from pylint.utils import ASTWalker
from pylint.testutils.unittest_linter import UnittestLinter

class CheckerTestCase:
    """A base testcase class for unit testing individual checker classes."""
    CHECKER_CLASS: Any
    CONFIG: dict[str, Any] = {}

    @contextlib.contextmanager
    def assertNoMessages(self) -> Iterator[None]:
        """Assert that no messages are added by the given method."""
        initial_messages = list(self.linter._messages)
        yield
        new_messages = self.linter._messages[len(initial_messages):]
        if new_messages:
            raise AssertionError(f"Unexpected message(s) raised: {new_messages}")

    @contextlib.contextmanager
    def assertAddsMessages(self, *messages: MessageTest, ignore_position: bool=False) -> Generator[None, None, None]:
        """Assert that exactly the given method adds the given messages.

        The list of messages must exactly match *all* the messages added by the
        method. Additionally, we check to see whether the args in each message can
        actually be substituted into the message string.

        Using the keyword argument `ignore_position`, all checks for position
        arguments (line, col_offset, ...) will be skipped. This can be used to
        just test messages for the correct node.
        """
        initial_messages = list(self.linter._messages)
        yield
        new_messages = self.linter._messages[len(initial_messages):]
        
        if len(new_messages) != len(messages):
            raise AssertionError(f"Expected {len(messages)} message(s), got {len(new_messages)}")
        
        for expected, actual in zip(messages, new_messages):
            if expected.msg_id != actual.msg_id:
                raise AssertionError(f"Expected message id {expected.msg_id}, got {actual.msg_id}")
            
            if not ignore_position:
                if expected.line != actual.line:
                    raise AssertionError(f"Expected line {expected.line}, got {actual.line}")
                if expected.col_offset != actual.col_offset:
                    raise AssertionError(f"Expected column {expected.col_offset}, got {actual.col_offset}")
                if expected.end_line != actual.end_line:
                    raise AssertionError(f"Expected end line {expected.end_line}, got {actual.end_line}")
                if expected.end_col_offset != actual.end_col_offset:
                    raise AssertionError(f"Expected end column {expected.end_col_offset}, got {actual.end_col_offset}")
            
            if expected.args != actual.args:
                raise AssertionError(f"Expected args {expected.args}, got {actual.args}")

    def walk(self, node: nodes.NodeNG) -> None:
        """Recursive walk on the given node."""
        walker = ASTWalker(self.linter)
        walker.walk(node)
