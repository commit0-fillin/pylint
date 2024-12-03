from __future__ import annotations
import tokenize
from typing import TYPE_CHECKING, Any, Literal, cast
from pylint.checkers import BaseTokenChecker
from pylint.reporters.ureports.nodes import Paragraph, Section, Table, Text
from pylint.utils import LinterStats, diff_string
if TYPE_CHECKING:
    from pylint.lint import PyLinter

def report_raw_stats(sect: Section, stats: LinterStats, old_stats: LinterStats | None) -> None:
    """Calculate percentage of code / doc / comment / empty."""
    total_lines = stats.total_lines
    if total_lines == 0:
        sect.append(Paragraph([Text("No lines in file")]))
        return

    code_lines = stats.code_lines
    docstring_lines = stats.doc_lines
    comment_lines = stats.comment_lines
    empty_lines = stats.empty_lines

    def percentage(part: int) -> float:
        return float(part) / total_lines * 100

    table = Table(cols=4, rheaders=1, cheaders=1)
    table.append(Text("type"), Text("number"), Text("%), Text("previous"))
    table.append(Text("code"), Text(str(code_lines)), 
                 Text(f"{percentage(code_lines):.2f}"), 
                 diff_string(code_lines, old_stats.code_lines if old_stats else None))
    table.append(Text("docstring"), Text(str(docstring_lines)), 
                 Text(f"{percentage(docstring_lines):.2f}"), 
                 diff_string(docstring_lines, old_stats.doc_lines if old_stats else None))
    table.append(Text("comment"), Text(str(comment_lines)), 
                 Text(f"{percentage(comment_lines):.2f}"), 
                 diff_string(comment_lines, old_stats.comment_lines if old_stats else None))
    table.append(Text("empty"), Text(str(empty_lines)), 
                 Text(f"{percentage(empty_lines):.2f}"), 
                 diff_string(empty_lines, old_stats.empty_lines if old_stats else None))
    sect.append(table)

class RawMetricsChecker(BaseTokenChecker):
    """Checker that provides raw metrics instead of checking anything.

    Provides:
    * total number of lines
    * total number of code lines
    * total number of docstring lines
    * total number of comments lines
    * total number of empty lines
    """
    name = 'metrics'
    options = ()
    msgs: Any = {}
    reports = (('RP0701', 'Raw metrics', report_raw_stats),)

    def open(self) -> None:
        """Init statistics."""
        self.stats = LinterStats()
        self.stats.reset_code_count()

    def process_tokens(self, tokens: list[tokenize.TokenInfo]) -> None:
        """Update stats."""
        for token in tokens:
            self.stats.total_lines = max(self.stats.total_lines, token.end[0])
            if token.type == tokenize.NEWLINE:
                self.stats.code_lines += 1
            elif token.type == tokenize.COMMENT:
                self.stats.comment_lines += 1
                self.stats.code_lines += 1
            elif token.type == tokenize.STRING:
                if token.start[0] == token.end[0]:
                    self.stats.code_lines += 1
                else:
                    self.stats.doc_lines += token.end[0] - token.start[0] + 1
            elif token.type == tokenize.NL:
                if self._is_empty_line(token.line):
                    self.stats.empty_lines += 1
                else:
                    self.stats.code_lines += 1

    def _is_empty_line(self, line: str) -> bool:
        return len(line.strip()) == 0
JUNK = (tokenize.NL, tokenize.INDENT, tokenize.NEWLINE, tokenize.ENDMARKER)

def get_type(tokens: list[tokenize.TokenInfo], start_index: int) -> tuple[int, int, Literal['code', 'docstring', 'comment', 'empty']]:
    """Return the line type : docstring, comment, code, empty."""
    tok = tokens[start_index]
    start, end = tok.start[0], tok.end[0]
    
    if tok.type == tokenize.STRING and start_index == 0:
        return start, end, 'docstring'
    elif tok.type == tokenize.COMMENT:
        return start, end, 'comment'
    elif tok.type in JUNK:
        if tok.line.strip() == '':
            return start, end, 'empty'
        return start, end, 'code'
    else:
        return start, end, 'code'
