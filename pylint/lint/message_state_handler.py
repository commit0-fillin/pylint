from __future__ import annotations
import tokenize
from collections import defaultdict
from typing import TYPE_CHECKING, Literal
from pylint import exceptions, interfaces
from pylint.constants import MSG_STATE_CONFIDENCE, MSG_STATE_SCOPE_CONFIG, MSG_STATE_SCOPE_MODULE, MSG_TYPES, MSG_TYPES_LONG
from pylint.interfaces import HIGH
from pylint.message import MessageDefinition
from pylint.typing import ManagedMessage
from pylint.utils.pragma_parser import OPTION_PO, InvalidPragmaError, UnRecognizedOptionError, parse_pragma
if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter

class _MessageStateHandler:
    """Class that handles message disabling & enabling and processing of inline
    pragma's.
    """

    def __init__(self, linter: PyLinter) -> None:
        self.linter = linter
        self._msgs_state: dict[str, bool] = {}
        self._options_methods = {'enable': self.enable, 'disable': self.disable, 'disable-next': self.disable_next}
        self._bw_options_methods = {'disable-msg': self._options_methods['disable'], 'enable-msg': self._options_methods['enable']}
        self._pragma_lineno: dict[str, int] = {}
        self._stashed_messages: defaultdict[tuple[str, str], list[tuple[str | None, str]]] = defaultdict(list)
        'Some messages in the options (for --enable and --disable) are encountered\n        too early to warn about them.\n\n        i.e. before all option providers have been fully parsed. Thus, this dict stores\n        option_value and msg_id needed to (later) emit the messages keyed on module names.\n        '

    def _set_one_msg_status(self, scope: str, msg: MessageDefinition, line: int | None, enable: bool) -> None:
        """Set the status of an individual message."""
        if scope == "module":
            self.file_state.set_msg_status(msg, line, enable)
        elif scope == "package":
            self._msgs_state[msg.msgid] = enable
        else:
            raise ValueError(f"Invalid scope: {scope}")

    def _get_messages_to_set(self, msgid: str, enable: bool, ignore_unknown: bool=False) -> list[MessageDefinition]:
        """Do some tests and find the actual messages of which the status should be set."""
        if msgid == 'all':
            return list(self.msgs_store.messages.values())
        # If the msgid is a category name, get all messages of that category
        if msgid.upper() in MSG_TYPES:
            return [m for m in self.msgs_store.messages.values() if m.msgid[0] == msgid.upper()]
        # If it's a message symbol or number, get that specific message
        try:
            return [self.msgs_store.get_message_definition(msgid)]
        except exceptions.UnknownMessageError:
            if ignore_unknown:
                return []
            raise

    def _set_msg_status(self, msgid: str, enable: bool, scope: str='package', line: int | None=None, ignore_unknown: bool=False) -> None:
        """Do some tests and then iterate over message definitions to set state."""
        if msgid == 'all':
            for _msgid in MSG_TYPES:
                self._set_msg_status(_msgid, enable, scope, line, ignore_unknown)
            return

        messages = self._get_messages_to_set(msgid, enable, ignore_unknown)
        for msg in messages:
            self._set_one_msg_status(scope, msg, line, enable)

    def _register_by_id_managed_msg(self, msgid_or_symbol: str, line: int | None, is_disabled: bool=True) -> None:
        """If the msgid is a numeric one, then register it to inform the user
        it could furnish instead a symbolic msgid.
        """
        try:
            msg = self.msgs_store.get_message_definition(msgid_or_symbol)
        except exceptions.UnknownMessageError:
            # Unknown msgid, don't register it
            return
        if msg.msgid != msgid_or_symbol:
            self._by_id_managed_msgs.append(
                ManagedMessage(msg.msgid, msg.symbol, line, is_disabled)
            )

    def disable(self, msgid: str, scope: str='package', line: int | None=None, ignore_unknown: bool=False) -> None:
        """Disable a message for a scope."""
        self._set_msg_status(msgid, enable=False, scope=scope, line=line, ignore_unknown=ignore_unknown)
        if line is None:
            self._register_by_id_managed_msg(msgid, line, is_disabled=True)

    def disable_next(self, msgid: str, _: str='package', line: int | None=None, ignore_unknown: bool=False) -> None:
        """Disable a message for the next line."""
        if line is None:
            raise ValueError("Line number is required for disable_next")
        self._set_msg_status(msgid, enable=False, scope='module', line=line+1, ignore_unknown=ignore_unknown)

    def enable(self, msgid: str, scope: str='package', line: int | None=None, ignore_unknown: bool=False) -> None:
        """Enable a message for a scope."""
        self._set_msg_status(msgid, enable=True, scope=scope, line=line, ignore_unknown=ignore_unknown)
        if line is None:
            self._register_by_id_managed_msg(msgid, line, is_disabled=False)

    def disable_noerror_messages(self) -> None:
        """Disable message categories other than `error` and `fatal`."""
        for msgcat in MSG_TYPES:
            if msgcat not in ('E', 'F'):
                self.disable(msgcat)

    def _get_message_state_scope(self, msgid: str, line: int | None=None, confidence: interfaces.Confidence | None=None) -> Literal[0, 1, 2] | None:
        """Returns the scope at which a message was enabled/disabled."""
        if self._msgs_state.get(msgid):
            return MSG_STATE_SCOPE_CONFIG
        if line in self.file_state._module_msgs_state.get(msgid, ()):
            return MSG_STATE_SCOPE_MODULE
        if confidence is not None:
            try:
                if confidence.name in self._msgs_state.get(msgid, ()):
                    return MSG_STATE_CONFIDENCE
            except AttributeError:
                pass
        return None

    def _is_one_message_enabled(self, msgid: str, line: int | None) -> bool:
        """Checks state of a single message for the current file.

        This function can't be cached as it depends on self.file_state which can
        change.
        """
        if line is None:
            return self._msgs_state.get(msgid, True)
        try:
            return self.file_state._module_msgs_state[msgid][line]
        except KeyError:
            return self._msgs_state.get(msgid, True)

    def is_message_enabled(self, msg_descr: str, line: int | None=None, confidence: interfaces.Confidence | None=None) -> bool:
        """Is this message enabled for the current file ?

        Optionally, is it enabled for this line and confidence level ?

        The current file is implicit and mandatory. As a result this function
        can't be cached right now as the line is the line of the currently
        analysed file (self.file_state), if it changes, then the result for
        the same msg_descr/line might need to change.

        :param msg_descr: Either the msgid or the symbol for a MessageDefinition
        :param line: The line of the currently analysed file
        :param confidence: The confidence of the message
        """
        try:
            msgid = self.msgs_store.get_message_definition(msg_descr).msgid
        except exceptions.UnknownMessageError:
            # The linter checks for messages that are not registered
            # due to version mismatch, just treat them as message IDs
            # for now.
            msgid = msg_descr
        if msgid not in self.msgs_store._messages_definitions:
            return True
        if self._get_message_state_scope(msgid, line, confidence) is None:
            return True
        return self._is_one_message_enabled(msgid, line)

    def process_tokens(self, tokens: list[tokenize.TokenInfo]) -> None:
        """Process tokens from the current module to search for module/block level
        options.

        See func_block_disable_msg.py test case for expected behaviour.
        """
        control_pragmas = {"disable", "disable-next", "enable"}
        for (tok_type, content, start, _, _) in tokens:
            if tok_type != tokenize.COMMENT:
                continue

            match = OPTION_PO.search(content)
            if match is None:
                continue

            try:
                for pragma_repr in parse_pragma(match.group(2)):
                    if pragma_repr.action in control_pragmas:
                        for msgid in pragma_repr.messages:
                            self._set_msg_status(
                                msgid,
                                pragma_repr.action == "enable",
                                "module",
                                start[0],
                            )
            except (InvalidPragmaError, UnRecognizedOptionError):
                self.add_message(
                    "bad-inline-option",
                    args=match.group(1).rstrip(),
                    line=start[0],
                )
