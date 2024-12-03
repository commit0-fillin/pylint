"""Text formatting drivers for ureports."""
from __future__ import annotations
from typing import TYPE_CHECKING
from pylint.reporters.ureports.base_writer import BaseWriter
if TYPE_CHECKING:
    from pylint.reporters.ureports.nodes import EvaluationSection, Paragraph, Section, Table, Text, Title, VerbatimText
TITLE_UNDERLINES = ['', '=', '-', '`', '.', '~', '^']
BULLETS = ['*', '-']

class TextWriter(BaseWriter):
    """Format layouts as text
    (ReStructured inspiration but not totally handled yet).
    """

    def __init__(self) -> None:
        super().__init__()
        self.list_level = 0

    def visit_section(self, layout: Section) -> None:
        """Display a section as text."""
        self.section += 1
        self.writeln()
        if layout.title:
            self.visit_title(layout.title)
        self.format_children(layout)
        self.section -= 1

    def visit_evaluationsection(self, layout: EvaluationSection) -> None:
        """Display an evaluation section as a text."""
        self.section += 1
        self.writeln()
        self.format_children(layout)
        self.section -= 1

    def visit_paragraph(self, layout: Paragraph) -> None:
        """Enter a paragraph."""
        self.writeln()
        self.format_children(layout)
        self.writeln()

    def visit_table(self, layout: Table) -> None:
        """Display a table as text."""
        table_content = self.get_table_content(layout)
        cols_width = [max(len(cell) for cell in col) for col in zip(*table_content)]
        self.default_table(layout, table_content, cols_width)
        self.writeln()

    def default_table(self, layout: Table, table_content: list[list[str]], cols_width: list[int]) -> None:
        """Format a table."""
        cols_width = [max(w, 4) for w in cols_width]
        table_width = sum(cols_width) + len(cols_width) * 3 + 1
        if layout.title:
            self.writeln("=" * table_width)
            self.writeln(layout.title.center(table_width))
        self.writeln("=" * table_width)
        for row in table_content:
            self.write("| ")
            for width, cell in zip(cols_width, row):
                self.write(cell.ljust(width))
                self.write(" | ")
            self.writeln()
        self.writeln("=" * table_width)

    def visit_verbatimtext(self, layout: VerbatimText) -> None:
        """Display a verbatim layout as text."""
        self.writeln()
        for line in layout.data.splitlines():
            self.writeln("    " + line)
        self.writeln()

    def visit_text(self, layout: Text) -> None:
        """Add some text."""
        self.write(layout.data)
