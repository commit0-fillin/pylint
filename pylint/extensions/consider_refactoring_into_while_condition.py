"""Looks for try/except statements with too much code in the try clause."""
from __future__ import annotations
from typing import TYPE_CHECKING
from astroid import nodes
from pylint import checkers
from pylint.checkers import utils
from pylint.interfaces import HIGH
if TYPE_CHECKING:
    from pylint.lint import PyLinter

class ConsiderRefactorIntoWhileConditionChecker(checkers.BaseChecker):
    """Checks for instances where while loops are implemented with a constant condition
    which.

    always evaluates to truthy and the first statement(s) is/are if statements which, when
    evaluated.

    to True, breaks out of the loop.

    The if statement(s) can be refactored into the while loop.
    """
    name = 'consider_refactoring_into_while'
    msgs = {'R3501': ("Consider using 'while %s' instead of 'while %s:' an 'if', and a 'break'", 'consider-refactoring-into-while-condition', 'Emitted when `while True:` loop is used and the first statement is a break condition. The ``if / break`` construct can be removed if the check is inverted and moved to the ``while`` statement.')}

    def _check_breaking_after_while_true(self, node: nodes.While) -> None:
        """Check that any loop with an ``if`` clause has a break statement."""
        if not isinstance(node.test, nodes.Const) or not node.test.value:
            return

        first_stmt = node.body[0] if node.body else None
        if not isinstance(first_stmt, nodes.If):
            return

        if_body = first_stmt.body
        if len(if_body) != 1 or not isinstance(if_body[0], nodes.Break):
            return

        condition = first_stmt.test
        self.add_message(
            "consider-refactoring-into-while-condition",
            node=node,
            args=(condition.as_string(), node.test.as_string()),
        )
