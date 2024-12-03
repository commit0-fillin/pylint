from __future__ import annotations
import sys
from typing import TYPE_CHECKING
from astroid import nodes
from pylint.constants import _SCOPE_EXEMPT, MSG_TYPES, WarningScope
from pylint.exceptions import InvalidMessageError
from pylint.utils import normalize_text
if TYPE_CHECKING:
    from pylint.checkers import BaseChecker

class MessageDefinition:

    def __init__(self, checker: BaseChecker, msgid: str, msg: str, description: str, symbol: str, scope: str, minversion: tuple[int, int] | None=None, maxversion: tuple[int, int] | None=None, old_names: list[tuple[str, str]] | None=None, shared: bool=False, default_enabled: bool=True) -> None:
        self.checker_name = checker.name
        self.check_msgid(msgid)
        self.msgid = msgid
        self.symbol = symbol
        self.msg = msg
        self.description = description
        self.scope = scope
        self.minversion = minversion
        self.maxversion = maxversion
        self.shared = shared
        self.default_enabled = default_enabled
        self.old_names: list[tuple[str, str]] = []
        if old_names:
            for old_msgid, old_symbol in old_names:
                self.check_msgid(old_msgid)
                self.old_names.append((old_msgid, old_symbol))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, MessageDefinition) and self.msgid == other.msgid and (self.symbol == other.symbol)

    def __repr__(self) -> str:
        return f'MessageDefinition:{self.symbol} ({self.msgid})'

    def __str__(self) -> str:
        return f'{self!r}:\n{self.msg} {self.description}'

    def may_be_emitted(self, py_version: tuple[int, ...] | sys._version_info) -> bool:
        """May the message be emitted using the configured py_version?"""
        if self.minversion is not None and py_version < self.minversion:
            return False
        if self.maxversion is not None and py_version > self.maxversion:
            return False
        return True

    def format_help(self, checkerref: bool=False) -> str:
        """Return the help string for the given message id."""
        desc = self.description
        if checkerref:
            desc += f" This message belongs to the {self.checker_name} checker."
        message = f"{self.symbol} ({self.msgid}): {desc}"
        message = normalize_text(message, indent='  ', line_len=79)
        return message

    def check_message_definition(self, line: int | None, node: nodes.NodeNG | None) -> None:
        """Check MessageDefinition for possible errors."""
        if self.msgid[0] not in MSG_TYPES:
            raise InvalidMessageError(
                f"Bad message type {self.msgid[0]} in {self.symbol} message"
            )
        
        if line is None and self.scope == WarningScope.LINE:
            raise InvalidMessageError(
                f"Message {self.msgid} must provide line, got None"
            )
        if self.scope == WarningScope.NODE and node is None:
            raise InvalidMessageError(
                f"Message {self.msgid} must provide Node, got None"
            )
        
        if self.msgid[1:3].isdigit():
            if self.msgid[1] == '0':
                raise InvalidMessageError(
                    f"Invalid message id '{self.msgid}'. The first digit after the letter should not be 0."
                )
        else:
            raise InvalidMessageError(
                f"Invalid message id '{self.msgid}'. The second and third characters should be digits."
            )
        
        if not self.symbol[0].isalpha():
            raise InvalidMessageError(
                f"Invalid message symbol '{self.symbol}'. The first character should be alphabetic."
            )
        if self.msgid[0] not in _SCOPE_EXEMPT:
            if self.scope == WarningScope.LINE:
                if not self.symbol.endswith("-line"):
                    raise InvalidMessageError(
                        f"Message symbol '{self.symbol}' should end with '-line'"
                    )
            elif self.scope == WarningScope.NODE:
                if self.symbol.endswith("-line"):
                    raise InvalidMessageError(
                        f"Message symbol '{self.symbol}' should not end with '-line'"
                    )
