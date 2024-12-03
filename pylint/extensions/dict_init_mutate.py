"""Check for use of dictionary mutation after initialization."""
from __future__ import annotations
from typing import TYPE_CHECKING
from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.checkers.utils import only_required_for_messages
from pylint.interfaces import HIGH
if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter

class DictInitMutateChecker(BaseChecker):
    name = 'dict-init-mutate'
    msgs = {'C3401': ('Declare all known key/values when initializing the dictionary.', 'dict-init-mutate', 'Dictionaries can be initialized with a single statement using dictionary literal syntax.')}

    @only_required_for_messages('dict-init-mutate')
    def visit_assign(self, node: nodes.Assign) -> None:
        """
        Detect dictionary mutation immediately after initialization.

        At this time, detecting nested mutation is not supported.
        """
        if isinstance(node.value, nodes.Dict):
            # Check if the next sibling is a mutation of the same dictionary
            next_sibling = node.next_sibling()
            if isinstance(next_sibling, nodes.Assign):
                target = next_sibling.targets[0]
                if isinstance(target, nodes.Subscript) and isinstance(target.value, nodes.Name):
                    if target.value.name == node.targets[0].name:
                        self.add_message('dict-init-mutate', node=next_sibling)
