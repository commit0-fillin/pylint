from __future__ import annotations
import collections
from collections import defaultdict
from collections.abc import Iterator
from typing import TYPE_CHECKING, Dict, Literal
from astroid import nodes
from pylint.constants import INCOMPATIBLE_WITH_USELESS_SUPPRESSION, MSG_STATE_SCOPE_MODULE, WarningScope
if TYPE_CHECKING:
    from pylint.message import MessageDefinition, MessageDefinitionStore
MessageStateDict = Dict[str, Dict[int, bool]]

class FileState:
    """Hold internal state specific to the currently analyzed file."""

    def __init__(self, modname: str, msg_store: MessageDefinitionStore, node: nodes.Module | None=None, *, is_base_filestate: bool=False) -> None:
        self.base_name = modname
        self._module_msgs_state: MessageStateDict = {}
        self._raw_module_msgs_state: MessageStateDict = {}
        self._ignored_msgs: defaultdict[tuple[str, int], set[int]] = collections.defaultdict(set)
        self._suppression_mapping: dict[tuple[str, int], int] = {}
        self._module = node
        if node:
            self._effective_max_line_number = node.tolineno
        else:
            self._effective_max_line_number = None
        self._msgs_store = msg_store
        self._is_base_filestate = is_base_filestate
        'If this FileState is the base state made during initialization of\n        PyLinter.\n        '

    def _set_state_on_block_lines(self, msgs_store: MessageDefinitionStore, node: nodes.NodeNG, msg: MessageDefinition, msg_state: dict[int, bool]) -> None:
        """Recursively walk (depth first) AST to collect block level options
        line numbers and set the state correctly.
        """
        first_child = node.first_child()
        if first_child:
            self._set_message_state_in_block(msg, msg_state, node, first_child.fromlineno)
        else:
            self._set_message_state_in_block(msg, msg_state, node, node.fromlineno)
        
        for child in node.get_children():
            self._set_state_on_block_lines(msgs_store, child, msg, msg_state)

    def _set_message_state_in_block(self, msg: MessageDefinition, lines: dict[int, bool], node: nodes.NodeNG, firstchildlineno: int) -> None:
        """Set the state of a message in a block of lines."""
        start = node.fromlineno
        end = node.tolineno
        for line in range(start, firstchildlineno):
            self._set_message_state_on_line(msg, line, lines.get(start, True), start)
        for line in range(firstchildlineno, end + 1):
            self._set_message_state_on_line(msg, line, lines.get(line, True), line)

    def _set_message_state_on_line(self, msg: MessageDefinition, line: int, state: bool, original_lineno: int) -> None:
        """Set the state of a message on a line."""
        if msg.msgid not in self._module_msgs_state:
            self._module_msgs_state[msg.msgid] = {}
        self._module_msgs_state[msg.msgid][line] = state
        
        if msg.msgid not in self._raw_module_msgs_state:
            self._raw_module_msgs_state[msg.msgid] = {}
        self._raw_module_msgs_state[msg.msgid][original_lineno] = state

    def set_msg_status(self, msg: MessageDefinition, line: int, status: bool, scope: str='package') -> None:
        """Set status (enabled/disable) for a given message at a given line."""
        assert line > 0
        
        if msg.msgid not in self._module_msgs_state:
            self._module_msgs_state[msg.msgid] = {}
        
        if scope == 'package':
            for current_line in range(line, self._effective_max_line_number + 1):
                self._module_msgs_state[msg.msgid][current_line] = status
        else:
            self._module_msgs_state[msg.msgid][line] = status

    def handle_ignored_message(self, state_scope: Literal[0, 1, 2] | None, msgid: str, line: int | None) -> None:
        """Report an ignored message.

        state_scope is either MSG_STATE_SCOPE_MODULE or MSG_STATE_SCOPE_CONFIG,
        depending on whether the message was disabled locally in the module,
        or globally.
        """
        if state_scope == MSG_STATE_SCOPE_MODULE:
            if line in self._suppression_mapping:
                self._suppression_mapping[(msgid, line)] = self._suppression_mapping.pop((msgid, line))
            else:
                self._suppression_mapping[(msgid, line)] = line
        elif line is None:
            self._ignored_msgs[(msgid, 0)].add(0)
        else:
            self._ignored_msgs[(msgid, line)].add(line)
