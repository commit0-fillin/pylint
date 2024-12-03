from __future__ import annotations
from collections.abc import Sequence
from typing import Any, NamedTuple, TypeVar
from astroid import nodes
from pylint.interfaces import UNDEFINED, Confidence
from pylint.message.message import Message
_T = TypeVar('_T')

class MessageTest(NamedTuple):
    msg_id: str
    line: int | None = None
    node: nodes.NodeNG | None = None
    args: Any | None = None
    confidence: Confidence | None = UNDEFINED
    col_offset: int | None = None
    end_line: int | None = None
    end_col_offset: int | None = None
    "Used to test messages produced by pylint.\n\n    Class name cannot start with Test as pytest doesn't allow constructors in test classes.\n    "

class OutputLine(NamedTuple):
    symbol: str
    lineno: int
    column: int
    end_lineno: int | None
    end_column: int | None
    object: str
    msg: str
    confidence: str

    @classmethod
    def from_msg(cls, msg: Message, check_endline: bool=True) -> OutputLine:
        """Create an OutputLine from a Pylint Message."""
        end_line = cls._get_py38_none_value(msg.end_line, check_endline)
        end_column = cls._get_py38_none_value(msg.end_column, check_endline)
        return cls(
            symbol=msg.symbol,
            lineno=msg.line,
            column=msg.column,
            end_lineno=end_line,
            end_column=end_column,
            object=msg.obj,
            msg=msg.msg,
            confidence=msg.confidence.name
        )

    @staticmethod
    def _get_column(column: str | int) -> int:
        """Handle column numbers."""
        if isinstance(column, str):
            return int(column)
        return column

    @staticmethod
    def _get_py38_none_value(value: _T, check_endline: bool) -> _T | None:
        """Used to make end_line and end_column None as indicated by our version
        compared to `min_pyver_end_position`.
        """
        if check_endline:
            return value
        return None

    @classmethod
    def from_csv(cls, row: Sequence[str] | str, check_endline: bool=True) -> OutputLine:
        """Create an OutputLine from a comma separated list (the functional tests
        expected output .txt files).
        """
        if isinstance(row, str):
            row = row.split(',')
        
        symbol, lineno, column, *rest = row
        end_lineno = cls._get_py38_none_value(rest[0] if rest else None, check_endline)
        end_column = cls._get_py38_none_value(rest[1] if len(rest) > 1 else None, check_endline)
        object_ = rest[2] if len(rest) > 2 else ''
        msg = rest[3] if len(rest) > 3 else ''
        confidence = rest[4] if len(rest) > 4 else ''

        return cls(
            symbol=symbol,
            lineno=int(lineno),
            column=cls._get_column(column),
            end_lineno=cls._value_to_optional_int(end_lineno),
            end_column=cls._value_to_optional_int(end_column),
            object=object_,
            msg=msg,
            confidence=confidence
        )

    def to_csv(self) -> tuple[str, str, str, str, str, str, str, str]:
        """Convert an OutputLine to a tuple of string to be written by a
        csv-writer.
        """
        return (
            self.symbol,
            str(self.lineno),
            str(self.column),
            str(self.end_lineno) if self.end_lineno is not None else '',
            str(self.end_column) if self.end_column is not None else '',
            self.object,
            self.msg,
            self.confidence
        )

    @staticmethod
    def _value_to_optional_int(value: str | None) -> int | None:
        """Checks if a (stringified) value should be None or a Python integer."""
        if value is None or value == '':
            return None
        return int(value)
