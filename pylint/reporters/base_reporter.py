from __future__ import annotations
import os
import sys
from typing import TYPE_CHECKING, TextIO
from pylint.message import Message
from pylint.reporters.ureports.nodes import Text
from pylint.utils import LinterStats
if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter
    from pylint.reporters.ureports.nodes import Section

class BaseReporter:
    """Base class for reporters.

    symbols: show short symbolic names for messages.
    """
    extension = ''
    name = 'base'
    'Name of the reporter.'

    def __init__(self, output: TextIO | None=None) -> None:
        self.linter: PyLinter
        self.section = 0
        self.out: TextIO = output or sys.stdout
        self.messages: list[Message] = []
        self.path_strip_prefix = os.getcwd() + os.sep

    def handle_message(self, msg: Message) -> None:
        """Handle a new message triggered on the current file."""
        self.messages.append(msg)

    def writeln(self, string: str='') -> None:
        """Write a line in the output buffer."""
        print(string, file=self.out)

    def display_reports(self, layout: Section) -> None:
        """Display results encapsulated in the layout tree."""
        self._display(layout)

    def _display(self, layout: Section) -> None:
        """Display the layout."""
        for child in layout.children:
            if isinstance(child, Section):
                self._display(child)
            elif isinstance(child, (Text, VerbatimText)):
                self.writeln(child.data)
            elif isinstance(child, Table):
                self._display_table(child)

    def display_messages(self, layout: Section | None) -> None:
        """Hook for displaying the messages of the reporter.

        This will be called whenever the underlying messages
        needs to be displayed. For some reporters, it probably
        doesn't make sense to display messages as soon as they
        are available, so some mechanism of storing them could be used.
        This method can be implemented to display them after they've
        been aggregated.
        """
        for msg in self.messages:
            self.writeln(str(msg))

    def on_set_current_module(self, module: str, filepath: str | None) -> None:
        """Hook called when a module starts to be analysed."""
        self.writeln(f"Analyzing module {module} from file {filepath}")

    def on_close(self, stats: LinterStats, previous_stats: LinterStats | None) -> None:
        """Hook called when a module finished analyzing."""
        self.writeln("Analysis complete.")
        self.writeln(f"Total messages: {stats.total_errors + stats.total_warnings}")
        self.writeln(f"Errors: {stats.total_errors}")
        self.writeln(f"Warnings: {stats.total_warnings}")
