from __future__ import annotations
import collections
import functools
import sys
from collections.abc import Sequence, ValuesView
from typing import TYPE_CHECKING
from pylint.exceptions import UnknownMessageError
from pylint.message.message_definition import MessageDefinition
from pylint.message.message_id_store import MessageIdStore
if TYPE_CHECKING:
    from pylint.checkers import BaseChecker

class MessageDefinitionStore:
    """The messages store knows information about every possible message definition but
    has no particular state during analysis.
    """

    def __init__(self, py_version: tuple[int, ...] | sys._version_info=sys.version_info) -> None:
        self.message_id_store: MessageIdStore = MessageIdStore()
        self._messages_definitions: dict[str, MessageDefinition] = {}
        self._msgs_by_category: dict[str, list[str]] = collections.defaultdict(list)
        self.py_version = py_version

    @property
    def messages(self) -> ValuesView[MessageDefinition]:
        """The list of all active messages."""
        return self._messages_definitions.values()

    def register_messages_from_checker(self, checker: BaseChecker) -> None:
        """Register all messages definitions from a checker."""
        for message in checker.messages:
            self.register_message(message)

    def register_message(self, message: MessageDefinition) -> None:
        """Register a MessageDefinition with consistency in mind."""
        self.message_id_store.add_msgid_and_symbol(message.msgid, message.symbol)
        self._messages_definitions[message.msgid] = message
        self._msgs_by_category[message.msgid[0]].append(message.msgid)
        for old_msgid, old_symbol in message.old_names:
            self.message_id_store.add_legacy_msgid_and_symbol(old_msgid, old_symbol, message.msgid)

    @functools.lru_cache(maxsize=None)
    def get_message_definitions(self, msgid_or_symbol: str) -> list[MessageDefinition]:
        """Returns the Message definition for either a numeric or symbolic id.

        The cache has no limit as its size will likely stay minimal. For each message we store
        about 1000 characters, so even if we would have 1000 messages the cache would only
        take up ~= 1 Mb.
        """
        try:
            msgids = self.message_id_store.get_active_msgids(msgid_or_symbol)
        except UnknownMessageError:
            return []
        return [self._messages_definitions[msgid] for msgid in msgids]

    def get_msg_display_string(self, msgid_or_symbol: str) -> str:
        """Generates a user-consumable representation of a message."""
        message_definitions = self.get_message_definitions(msgid_or_symbol)
        if not message_definitions:
            raise UnknownMessageError(f"No such message id or symbol '{msgid_or_symbol}'.")
        message = message_definitions[0]
        return f"{message.symbol} ({message.msgid})"

    def help_message(self, msgids_or_symbols: Sequence[str]) -> None:
        """Display help messages for the given message identifiers."""
        for msgid_or_symbol in msgids_or_symbols:
            try:
                for message in self.get_message_definitions(msgid_or_symbol):
                    print(message.format_help(checkerref=True))
                    print("")
            except UnknownMessageError:
                print(f"No help message available for '{msgid_or_symbol}'")

    def list_messages(self) -> None:
        """Output full messages list documentation in ReST format."""
        by_checker: dict[str, list[MessageDefinition]] = {}
        for message in self.messages:
            by_checker.setdefault(message.checker_name, []).append(message)

        for checker, messages in sorted(by_checker.items()):
            print(f"Messages for checker ``{checker}``:")
            for message in sorted(messages, key=lambda m: m.msgid):
                print(f":{message.msgid} ({message.symbol}): {message.msg}")
            print("")

    def find_emittable_messages(self) -> tuple[list[MessageDefinition], list[MessageDefinition]]:
        """Finds all emittable and non-emittable messages."""
        emittable = []
        non_emittable = []
        for message in self.messages:
            if message.may_be_emitted(self.py_version):
                emittable.append(message)
            else:
                non_emittable.append(message)
        return emittable, non_emittable
