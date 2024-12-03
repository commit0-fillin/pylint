"""Python code format's checker.

By default, try to follow Guido's style guide :

https://www.python.org/doc/essays/styleguide/

Some parts of the process_token method is based from The Tab Nanny std module.
"""
from __future__ import annotations
import tokenize
from functools import reduce
from re import Match
from typing import TYPE_CHECKING, Literal
from astroid import nodes
from pylint.checkers import BaseRawFileChecker, BaseTokenChecker
from pylint.checkers.utils import only_required_for_messages
from pylint.constants import WarningScope
from pylint.interfaces import HIGH
from pylint.typing import MessageDefinitionTuple
from pylint.utils.pragma_parser import OPTION_PO, PragmaParserError, parse_pragma
if TYPE_CHECKING:
    from pylint.lint import PyLinter
_KEYWORD_TOKENS = {'assert', 'del', 'elif', 'except', 'for', 'if', 'in', 'not', 'raise', 'return', 'while', 'yield', 'with', '=', ':='}
_JUNK_TOKENS = {tokenize.COMMENT, tokenize.NL}
MSGS: dict[str, MessageDefinitionTuple] = {'C0301': ('Line too long (%s/%s)', 'line-too-long', 'Used when a line is longer than a given number of characters.'), 'C0302': ('Too many lines in module (%s/%s)', 'too-many-lines', 'Used when a module has too many lines, reducing its readability.'), 'C0303': ('Trailing whitespace', 'trailing-whitespace', 'Used when there is whitespace between the end of a line and the newline.'), 'C0304': ('Final newline missing', 'missing-final-newline', 'Used when the last line in a file is missing a newline.'), 'C0305': ('Trailing newlines', 'trailing-newlines', 'Used when there are trailing blank lines in a file.'), 'W0311': ('Bad indentation. Found %s %s, expected %s', 'bad-indentation', "Used when an unexpected number of indentation's tabulations or spaces has been found."), 'W0301': ('Unnecessary semicolon', 'unnecessary-semicolon', 'Used when a statement is ended by a semi-colon (";"), which isn\'t necessary (that\'s python, not C ;).'), 'C0321': ('More than one statement on a single line', 'multiple-statements', 'Used when more than on statement are found on the same line.', {'scope': WarningScope.NODE}), 'C0325': ('Unnecessary parens after %r keyword', 'superfluous-parens', 'Used when a single item in parentheses follows an if, for, or other keyword.'), 'C0327': ('Mixed line endings LF and CRLF', 'mixed-line-endings', 'Used when there are mixed (LF and CRLF) newline signs in a file.'), 'C0328': ("Unexpected line ending format. There is '%s' while it should be '%s'.", 'unexpected-line-ending-format', 'Used when there is different newline than expected.')}

class TokenWrapper:
    """A wrapper for readable access to token information."""

    def __init__(self, tokens: list[tokenize.TokenInfo]) -> None:
        self._tokens = tokens

class FormatChecker(BaseTokenChecker, BaseRawFileChecker):
    """Formatting checker.

    Checks for :
    * unauthorized constructions
    * strict indentation
    * line length
    """
    name = 'format'
    msgs = MSGS
    options = (('max-line-length', {'default': 100, 'type': 'int', 'metavar': '<int>', 'help': 'Maximum number of characters on a single line.'}), ('ignore-long-lines', {'type': 'regexp', 'metavar': '<regexp>', 'default': '^\\s*(# )?<?https?://\\S+>?$', 'help': 'Regexp for a line that is allowed to be longer than the limit.'}), ('single-line-if-stmt', {'default': False, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Allow the body of an if to be on the same line as the test if there is no else.'}), ('single-line-class-stmt', {'default': False, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Allow the body of a class to be on the same line as the declaration if body contains single statement.'}), ('max-module-lines', {'default': 1000, 'type': 'int', 'metavar': '<int>', 'help': 'Maximum number of lines in a module.'}), ('indent-string', {'default': '    ', 'type': 'non_empty_string', 'metavar': '<string>', 'help': 'String used as indentation unit. This is usually "    " (4 spaces) or "\\t" (1 tab).'}), ('indent-after-paren', {'type': 'int', 'metavar': '<int>', 'default': 4, 'help': 'Number of spaces of indent required inside a hanging or continued line.'}), ('expected-line-ending-format', {'type': 'choice', 'metavar': '<empty or LF or CRLF>', 'default': '', 'choices': ['', 'LF', 'CRLF'], 'help': 'Expected format of line ending, e.g. empty (any line ending), LF or CRLF.'}))

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._lines: dict[int, str] = {}
        self._visited_lines: dict[int, Literal[1, 2]] = {}

    def new_line(self, tokens: TokenWrapper, line_end: int, line_start: int) -> None:
        """A new line has been encountered, process it if necessary."""
        if line_start > len(self._lines):
            return
        line = self._lines[line_start]
        line = line.rstrip('\n\r')
        self._lines[line_start] = line
        if line:
            self.check_lines(tokens, line_start, line + '\n', line_end)

    def _check_keyword_parentheses(self, tokens: list[tokenize.TokenInfo], start: int) -> None:
        """Check that there are not unnecessary parentheses after a keyword.

        Parens are unnecessary if there is exactly one balanced outer pair on a
        line and contains no commas (i.e. is not a tuple).

        Args:
        tokens: The entire list of Tokens.
        start: The position of the keyword in the token list.
        """
        if start >= len(tokens) - 2:
            return
        if tokens[start + 1].string != '(':
            return
        found_and_or = False
        depth = 0
        keyword_token = tokens[start]
        for i in range(start + 1, len(tokens)):
            token = tokens[i]
            if token.string == '(':
                depth += 1
            elif token.string == ')':
                depth -= 1
                if depth == 0:
                    # If the closing parenthesis is on a different line than the
                    # opening paren, we don't want to classify it as redundant.
                    if token.start[0] != keyword_token.start[0]:
                        return
                    # If there's anything except the closing paren after the
                    # keyword, the parentheses are not redundant.
                    if i != start + 3:
                        return
                    if found_and_or:
                        return
                    self.add_message(
                        'superfluous-parens',
                        line=keyword_token.start[0],
                        args=keyword_token.string,
                    )
                    return
            elif depth == 1:
                # If there's a comma or semicolon, the parentheses are not redundant.
                if token.string in ',:':
                    return
                # 'and' and 'or' are always in parentheses.
                if token.string in ('and', 'or'):
                    found_and_or = True
                    return
            elif depth == 0:
                # If there's anything except the closing paren after the
                # keyword, the parentheses are not redundant.
                return

    def process_tokens(self, tokens: list[tokenize.TokenInfo]) -> None:
        """Process tokens and search for:

        - too long lines (i.e. longer than <max_chars>)
        - optionally bad construct (if given, bad_construct must be a compiled
          regular expression).
        """
        indents = [0]
        check_equal = False
        line_num = 0
        line_start = 0
        prev_line_start = -1
        for idx, token in enumerate(tokens):
            token_type, token_string, start, _, _ = token
            if token_type == tokenize.NEWLINE:
                line_start = idx + 1
                self.new_line(TokenWrapper(tokens[prev_line_start:line_start]), start[0], prev_line_start)
                prev_line_start = line_start
                line_num += 1
            elif token_type == tokenize.INDENT:
                indents.append(indents[-1] + len(token_string))
                check_equal = True
                line_num += 1
            elif token_type == tokenize.DEDENT:
                if len(indents) > 1:
                    if check_equal and indents[-1] != indents[-2]:
                        self.add_message('bad-indentation', line=line_num,
                                         args=(token_string, indents[-1], indents[-2]))
                    indents.pop()
                check_equal = True
            elif token_type == tokenize.NL:
                line_num += 1
            elif token_string in ('return', 'yield', 'del', 'pass', 'break', 'continue'):
                self._check_keyword_parentheses(tokens, idx)
        self.new_line(TokenWrapper(tokens[prev_line_start:]), tokens[-1].start[0], prev_line_start)

    @only_required_for_messages('multiple-statements')
    def visit_default(self, node: nodes.NodeNG) -> None:
        """Check the node line number and check it if not yet done."""
        if isinstance(node, nodes.Module):
            return
        if node.root().file.endswith('__init__.py'):
            return
        if node.lineno not in self._visited_lines:
            self._visited_lines[node.lineno] = 1
            self._check_multi_statement_line(node, node.lineno)
        elif self._visited_lines[node.lineno] == 1:
            self._visited_lines[node.lineno] = 2

    def _check_multi_statement_line(self, node: nodes.NodeNG, line: int) -> None:
        """Check for lines containing multiple statements."""
        if isinstance(node.parent, (nodes.Lambda, nodes.ListComp, nodes.SetComp, nodes.DictComp, nodes.GeneratorExp)):
            return
        if isinstance(node, (nodes.With, nodes.TryExcept, nodes.TryFinally)):
            return
        if isinstance(node, nodes.Expr) and isinstance(node.value, nodes.Yield):
            return
        stmt = node.statement()
        if stmt.fromlineno == stmt.tolineno:
            return
        if line in self._ignored_lines:
            return
        self.add_message('multiple-statements', node=node)

    def check_trailing_whitespace_ending(self, line: str, i: int) -> None:
        """Check that there is no trailing white-space."""
        stripped_line = line.rstrip('\n\r')
        if stripped_line != stripped_line.rstrip():
            self.add_message('trailing-whitespace', line=i)

    def check_line_length(self, line: str, i: int, checker_off: bool) -> None:
        """Check that the line length is less than the authorized value."""
        max_chars = self.config.max_line_length
        ignore_long_line = self.config.ignore_long_lines
        line = line.rstrip()
        if len(line) > max_chars and not checker_off:
            if ignore_long_line.search(line):
                return
            self.add_message('line-too-long', line=i, args=(len(line), max_chars))

    @staticmethod
    def remove_pylint_option_from_lines(options_pattern_obj: Match[str]) -> str:
        """Remove the `# pylint ...` pattern from lines."""
        lines = options_pattern_obj.string.splitlines(True)
        pylint_pattern = re.compile(r'#.*pylint:')
        result = []
        for line in lines:
            if pylint_pattern.search(line):
                line = pylint_pattern.sub('', line)
                if line.strip() == '':
                    continue
            result.append(line)
        return ''.join(result)

    @staticmethod
    def is_line_length_check_activated(pylint_pattern_match_object: Match[str]) -> bool:
        """Return True if the line length check is activated."""
        try:
            for pragma in parse_pragma(pylint_pattern_match_object.group()):
                if 'disable' in pragma.action and 'line-too-long' in pragma.messages:
                    return False
                if 'enable' in pragma.action and 'line-too-long' in pragma.messages:
                    return True
        except PragmaParserError:
            # We can't parse the line, so we consider the check activated
            return True
        return True

    @staticmethod
    def specific_splitlines(lines: str) -> list[str]:
        """Split lines according to universal newlines except those in a specific
        sets.
        """
        idx = 0
        lines_list = []
        for match in re.finditer(r'\r\n|\r|\n', lines):
            end = match.start()
            lines_list.append(lines[idx:end])
            idx = match.end()
        if idx < len(lines):
            lines_list.append(lines[idx:])
        return lines_list

    def check_lines(self, tokens: TokenWrapper, line_start: int, lines: str, lineno: int) -> None:
        """Check given lines for potential messages.

        Check if lines have:
        - a final newline
        - no trailing white-space
        - less than a maximum number of characters
        """
        lines_list = self.specific_splitlines(lines)
        checker_off = False
        for i, line in enumerate(lines_list):
            line_num = i + lineno

            if line.endswith('\n'):
                self.check_trailing_whitespace_ending(line, line_num)

            pylint_pattern_match_object = OPTION_PO.search(line)
            if pylint_pattern_match_object:
                checker_off = not self.is_line_length_check_activated(pylint_pattern_match_object)
                line = self.remove_pylint_option_from_lines(pylint_pattern_match_object)

            self.check_line_length(line, line_num, checker_off)

        if lines and not lines.endswith('\n'):
            self.add_message('missing-final-newline', line=lineno + len(lines_list))
        elif len(lines_list) > 1 and not lines_list[-1]:
            self.add_message('trailing-newlines', line=lineno + len(lines_list) - 1)

    def check_indent_level(self, string: str, expected: int, line_num: int) -> None:
        """Return the indent level of the string."""
        indent = self.config.indent_string
        if indent == '\\t':  # \t is not interpreted in the configuration file
            indent = '\t'
        level = 0
        for char in string:
            if char == ' ':
                level += 1
            elif char == '\t':
                level += len(indent)
            else:
                break
        if level != expected:
            self.add_message('bad-indentation', args=(level, expected), line=line_num)
