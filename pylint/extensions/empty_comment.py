from __future__ import annotations
from typing import TYPE_CHECKING
from astroid import nodes
from pylint.checkers import BaseRawFileChecker
if TYPE_CHECKING:
    from pylint.lint import PyLinter

def is_line_commented(line: bytes) -> bool:
    """Checks if a `# symbol that is not part of a string was found in line."""
    for i, char in enumerate(line):
        if char == ord(b'#'):
            if not comment_part_of_string(line, i):
                return True
    return False

def comment_part_of_string(line: bytes, comment_idx: int) -> bool:
    """Checks if the symbol at comment_idx is part of a string."""
    in_single_quote = False
    in_double_quote = False
    escape_next = False

    for i, char in enumerate(line[:comment_idx]):
        if escape_next:
            escape_next = False
            continue

        if char == ord(b'\\'):
            escape_next = True
        elif char == ord(b"'") and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == ord(b'"') and not in_single_quote:
            in_double_quote = not in_double_quote

    return in_single_quote or in_double_quote

class CommentChecker(BaseRawFileChecker):
    name = 'empty-comment'
    msgs = {'R2044': ('Line with empty comment', 'empty-comment', 'Used when a # symbol appears on a line not followed by an actual comment')}
    options = ()
