from __future__ import annotations
from typing import TYPE_CHECKING
from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.checkers.utils import only_required_for_messages
if TYPE_CHECKING:
    from pylint.lint import PyLinter

class SetMembershipChecker(BaseChecker):
    name = 'set_membership'
    msgs = {'R6201': ('Consider using set for membership test', 'use-set-for-membership', 'Membership tests are more efficient when performed on a lookup optimized datatype like ``sets``.')}

    def __init__(self, linter: PyLinter) -> None:
        """Initialize checker instance."""
        super().__init__(linter=linter)

    def _check_in_comparison(self, comparator: nodes.NodeNG) -> None:
        """Checks for membership comparisons with in-place container objects."""
        if not isinstance(comparator, nodes.Compare):
            return

        if comparator.ops[0][0] not in ('in', 'not in'):
            return

        right = comparator.ops[0][1]
        if isinstance(right, (nodes.List, nodes.Tuple)):
            self.add_message('use-set-for-membership', node=comparator)
