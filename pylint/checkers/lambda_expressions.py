from __future__ import annotations
from itertools import zip_longest
from typing import TYPE_CHECKING
from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.interfaces import HIGH
if TYPE_CHECKING:
    from pylint.lint import PyLinter

class LambdaExpressionChecker(BaseChecker):
    """Check for unnecessary usage of lambda expressions."""
    name = 'lambda-expressions'
    msgs = {'C3001': ('Lambda expression assigned to a variable. Define a function using the "def" keyword instead.', 'unnecessary-lambda-assignment', 'Used when a lambda expression is assigned to variable rather than defining a standard function with the "def" keyword.'), 'C3002': ('Lambda expression called directly. Execute the expression inline instead.', 'unnecessary-direct-lambda-call', 'Used when a lambda expression is directly called rather than executing its contents inline.')}
    options = ()

    def visit_assign(self, node: nodes.Assign) -> None:
        """Check if lambda expression is assigned to a variable."""
        for target in node.targets:
            if isinstance(node.value, nodes.Lambda):
                self.add_message(
                    'unnecessary-lambda-assignment',
                    node=target,
                    confidence=HIGH
                )

    def visit_call(self, node: nodes.Call) -> None:
        """Check if lambda expression is called directly."""
        if isinstance(node.func, nodes.Lambda):
            self.add_message(
                'unnecessary-direct-lambda-call',
                node=node,
                confidence=HIGH
            )
