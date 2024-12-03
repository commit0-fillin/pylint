from __future__ import annotations
from typing import Any, Literal
from astroid import nodes
from pylint.interfaces import UNDEFINED, Confidence
from pylint.lint import PyLinter
from pylint.testutils.output_line import MessageTest

class UnittestLinter(PyLinter):
    """A fake linter class to capture checker messages."""

    def __init__(self) -> None:
        self._messages: list[MessageTest] = []
        super().__init__()

    def add_message(self, msgid: str, line: int | None=None, node: nodes.NodeNG | None=None, args: Any=None, confidence: Confidence | None=None, col_offset: int | None=None, end_lineno: int | None=None, end_col_offset: int | None=None) -> None:
        """Add a MessageTest to the _messages attribute of the linter class."""
        message = MessageTest(
            msg_id=msgid,
            line=line,
            node=node,
            args=args,
            confidence=confidence,
            col_offset=col_offset,
            end_line=end_lineno,
            end_col_offset=end_col_offset
        )
        self._messages.append(message)
