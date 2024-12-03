from __future__ import annotations
from typing import TYPE_CHECKING
from astroid import nodes
from pylint import checkers, interfaces
from pylint.checkers import utils
if TYPE_CHECKING:
    from pylint.lint import PyLinter
_LIST_MODIFIER_METHODS = {'append', 'remove'}
_SET_MODIFIER_METHODS = {'add', 'clear', 'discard', 'pop', 'remove'}

class ModifiedIterationChecker(checkers.BaseChecker):
    """Checks for modified iterators in for loops iterations.

    Currently supports `for` loops for Sets, Dictionaries and Lists.
    """
    name = 'modified_iteration'
    msgs = {'W4701': ("Iterated list '%s' is being modified inside for loop body, consider iterating through a copy of it instead.", 'modified-iterating-list', 'Emitted when items are added or removed to a list being iterated through. Doing so can result in unexpected behaviour, that is why it is preferred to use a copy of the list.'), 'E4702': ("Iterated dict '%s' is being modified inside for loop body, iterate through a copy of it instead.", 'modified-iterating-dict', 'Emitted when items are added or removed to a dict being iterated through. Doing so raises a RuntimeError.'), 'E4703': ("Iterated set '%s' is being modified inside for loop body, iterate through a copy of it instead.", 'modified-iterating-set', 'Emitted when items are added or removed to a set being iterated through. Doing so raises a RuntimeError.')}
    options = ()

    def _modified_iterating_check_on_node_and_children(self, body_node: nodes.NodeNG, iter_obj: nodes.NodeNG) -> None:
        """See if node or any of its children raises modified iterating messages."""
        if isinstance(body_node, nodes.Call):
            if isinstance(body_node.func, nodes.Attribute):
                if isinstance(body_node.func.expr, nodes.Name) and body_node.func.expr.name == iter_obj.name:
                    if body_node.func.attrname in _LIST_MODIFIER_METHODS:
                        self.add_message("modified-iterating-list", node=body_node, args=(iter_obj.name,))
                    elif body_node.func.attrname in _SET_MODIFIER_METHODS:
                        self.add_message("modified-iterating-set", node=body_node, args=(iter_obj.name,))
                    elif body_node.func.attrname in ("update", "pop", "clear"):
                        self.add_message("modified-iterating-dict", node=body_node, args=(iter_obj.name,))

        for child_node in body_node.get_children():
            self._modified_iterating_check_on_node_and_children(child_node, iter_obj)
