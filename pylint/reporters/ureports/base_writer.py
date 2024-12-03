"""Universal report objects and some formatting drivers.

A way to create simple reports using python objects, primarily designed to be
formatted as text and html.
"""
from __future__ import annotations
import sys
from collections.abc import Iterator
from io import StringIO
from typing import TYPE_CHECKING, TextIO
if TYPE_CHECKING:
    from pylint.reporters.ureports.nodes import BaseLayout, EvaluationSection, Paragraph, Section, Table

class BaseWriter:
    """Base class for ureport writers."""

    def format(self, layout: BaseLayout, stream: TextIO=sys.stdout, encoding: str | None=None) -> None:
        """Format and write the given layout into the stream object.

        unicode policy: unicode strings may be found in the layout;
        try to call 'stream.write' with it, but give it back encoded using
        the given encoding if it fails
        """
        self.encoding = encoding
        self.out = StringIO()
        self.begin_format()
        layout.accept(self)
        self.end_format()
        string = self.out.getvalue()
        if encoding is not None:
            string = string.encode(encoding)
        stream.write(string)

    def format_children(self, layout: EvaluationSection | Paragraph | Section) -> None:
        """Recurse on the layout children and call their accept method
        (see the Visitor pattern).
        """
        for child in layout.children:
            child.accept(self)

    def writeln(self, string: str='') -> None:
        """Write a line in the output buffer."""
        self.write(string + '\n')

    def write(self, string: str) -> None:
        """Write a string in the output buffer."""
        self.out.write(string)

    def begin_format(self) -> None:
        """Begin to format a layout."""
        self.section = 0

    def end_format(self) -> None:
        """Finished formatting a layout."""
        # This method can be left empty as it's meant to be overridden in subclasses if needed
        pass

    def get_table_content(self, table: Table) -> list[list[str]]:
        """Trick to get table content without actually writing it.

        return an aligned list of lists containing table cells values as string
        """
        result = []
        for row in table.children:
            if not row.children:
                continue
            result.append(list(self.compute_content(child) for child in row.children))
        return result

    def compute_content(self, layout: BaseLayout) -> Iterator[str]:
        """Trick to compute the formatting of children layout before actually
        writing it.

        return an iterator on strings (one for each child element)
        """
        old_out = self.out
        old_section = self.section
        self.out = StringIO()
        self.section = 0
        layout.accept(self)
        self.section = old_section
        content = self.out.getvalue()
        self.out = old_out
        return (line.strip() for line in content.splitlines())
