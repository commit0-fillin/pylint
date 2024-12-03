from __future__ import annotations
from io import StringIO
from os import getcwd, sep
from typing import TYPE_CHECKING
from pylint.message import Message
from pylint.reporters import BaseReporter
if TYPE_CHECKING:
    from pylint.reporters.ureports.nodes import Section

class GenericTestReporter(BaseReporter):
    """Reporter storing plain text messages."""
    out: StringIO

    def __init__(self) -> None:
        self.path_strip_prefix: str = getcwd() + sep
        self.reset()

    def handle_message(self, msg: Message) -> None:
        """Append messages to the list of messages of the reporter."""
        if not hasattr(self, 'messages'):
            self.messages = []
        self.messages.append(msg)

    def finalize(self) -> str:
        """Format and print messages in the context of the path."""
        formatted_messages = []
        for msg in getattr(self, 'messages', []):
            path = msg.path or "<unknown>"
            path = path.replace(self.path_strip_prefix, "", 1)
            formatted_msg = f"{path}:{msg.line}: [{msg.symbol}, {msg.msg_id}] {msg.msg}"
            formatted_messages.append(formatted_msg)
        return "\n".join(formatted_messages)

    def display_reports(self, layout: Section) -> None:
        """Ignore layouts."""
        # This function intentionally does nothing as per the comment

class MinimalTestReporter(BaseReporter):
    pass

class FunctionalTestReporter(BaseReporter):

    def display_reports(self, layout: Section) -> None:
        """Ignore layouts and don't call self._display()."""
        # This function intentionally does nothing as per the comment
