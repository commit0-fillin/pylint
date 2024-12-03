"""Checker for features used that are not supported by all python versions
indicated by the py-version setting.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.checkers.utils import only_required_for_messages, safe_infer, uninferable_final_decorators
if TYPE_CHECKING:
    from pylint.lint import PyLinter

class UnsupportedVersionChecker(BaseChecker):
    """Checker for features that are not supported by all python versions
    indicated by the py-version setting.
    """
    name = 'unsupported_version'
    msgs = {'W2601': ('F-strings are not supported by all versions included in the py-version setting', 'using-f-string-in-unsupported-version', 'Used when the py-version set by the user is lower than 3.6 and pylint encounters an f-string.'), 'W2602': ('typing.final is not supported by all versions included in the py-version setting', 'using-final-decorator-in-unsupported-version', 'Used when the py-version set by the user is lower than 3.8 and pylint encounters a ``typing.final`` decorator.')}

    def open(self) -> None:
        """Initialize visit variables and statistics."""
        self.py_version = self.linter.config.py_version

    @only_required_for_messages('using-f-string-in-unsupported-version')
    def visit_joinedstr(self, node: nodes.JoinedStr) -> None:
        """Check f-strings."""
        if self.py_version < (3, 6):
            self.add_message('using-f-string-in-unsupported-version', node=node)

    @only_required_for_messages('using-final-decorator-in-unsupported-version')
    def visit_decorators(self, node: nodes.Decorators) -> None:
        """Check decorators."""
        for decorator in node.nodes:
            if self._check_typing_final(decorator):
                self.add_message('using-final-decorator-in-unsupported-version', node=decorator)

    def _check_typing_final(self, node: nodes.NodeNG) -> bool:
        """Check if the node is a `typing.final` decorator and the
        py-version is lower than 3.8.
        """
        if self.py_version >= (3, 8):
            return False

        if isinstance(node, nodes.Name) and node.name == 'final':
            return node.root().name in ('typing', 'typing_extensions')
        if isinstance(node, nodes.Attribute) and node.attrname == 'final':
            expr = node.expr
            return (
                isinstance(expr, nodes.Name)
                and expr.name in ('typing', 'typing_extensions')
            )
        return False
