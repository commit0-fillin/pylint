from __future__ import annotations
import tokenize
from tokenize import TokenInfo
from typing import TYPE_CHECKING
from astroid import nodes
from pylint.checkers import BaseTokenChecker
from pylint.checkers.utils import only_required_for_messages
from pylint.interfaces import HIGH
if TYPE_CHECKING:
    from pylint.lint import PyLinter

class ElseifUsedChecker(BaseTokenChecker):
    """Checks for use of "else if" when an "elif" could be used."""
    name = 'else_if_used'
    msgs = {'R5501': ('Consider using "elif" instead of "else" then "if" to remove one indentation level', 'else-if-used', 'Used when an else statement is immediately followed by an if statement and does not contain statements that would be unrelated to it.')}

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._init()

    def process_tokens(self, tokens: list[TokenInfo]) -> None:
        """Process tokens and look for 'if' or 'elif'."""
        for index, token in enumerate(tokens):
            if token.exact_type == tokenize.NAME and token.string in ('if', 'elif'):
                self._check_elif(tokens, index)

    def _check_elif(self, tokens: list[TokenInfo], if_index: int) -> None:
        """Check for 'else' followed by 'if' when 'elif' could be used."""
        # Look for 'else' token
        for token in tokens[if_index + 1:]:
            if token.exact_type == tokenize.NAME and token.string == 'else':
                # Found 'else', now look for 'if'
                for next_token in tokens[tokens.index(token) + 1:]:
                    if next_token.exact_type == tokenize.NAME:
                        if next_token.string == 'if':
                            # Found 'else if', report the issue
                            self.add_message(
                                'else-if-used',
                                line=next_token.start[0]
                            )
                        break
                break

    @only_required_for_messages('else-if-used')
    def visit_if(self, node: nodes.If) -> None:
        """Current if node must directly follow an 'else'."""
        parent = node.parent
        if isinstance(parent, nodes.Expr):
            parent = parent.parent
        if not isinstance(parent, nodes.If):
            return
        if not parent.orelse:
            return
        if len(parent.orelse) != 1:
            return
        if node != parent.orelse[0]:
            return
        self.add_message('else-if-used', node=node)
