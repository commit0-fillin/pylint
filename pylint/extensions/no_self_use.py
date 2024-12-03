from __future__ import annotations
from typing import TYPE_CHECKING
from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.checkers.utils import PYMETHODS, decorated_with_property, is_overload_stub, is_protocol_class, overrides_a_method
from pylint.interfaces import INFERENCE
if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter

class NoSelfUseChecker(BaseChecker):
    name = 'no_self_use'
    msgs = {'R6301': ('Method could be a function', 'no-self-use', "Used when a method doesn't use its bound instance, and so could be written as a function.", {'old_names': [('R0201', 'old-no-self-use')]})}

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._first_attrs: list[str | None] = []
        self._meth_could_be_func: bool | None = None

    def visit_name(self, node: nodes.Name) -> None:
        """Check if the name handle an access to a class member
        if so, register it.
        """
        if isinstance(node.parent, nodes.Attribute):
            if node.parent.expr is node:
                if node.name == 'self':
                    self._first_attrs.append(node.parent.attrname)
    visit_asyncfunctiondef = visit_functiondef

    def _check_first_arg_for_type(self, node: nodes.FunctionDef) -> None:
        """Check the name of first argument."""
        if node.args.args:
            first_arg = node.args.args[0]
            if first_arg.name != 'self' and first_arg.name != 'cls':
                self.add_message('no-self-argument', node=node)

    def leave_functiondef(self, node: nodes.FunctionDef) -> None:
        """On method node, check if this method couldn't be a function.

        ignore class, static and abstract methods, initializer,
        methods overridden from a parent class.
        """
        if not self._is_method_without_self_use(node):
            return

        if self._meth_could_be_func:
            self.add_message('no-self-use', node=node)

        # reset for the next method
        self._meth_could_be_func = None
        self._first_attrs = []

    def _is_method_without_self_use(self, node: nodes.FunctionDef) -> bool:
        if not node.is_method():
            return False
        if node.decorators:
            for decorator in node.decorators.nodes:
                if isinstance(decorator, nodes.Name):
                    if decorator.name in ('classmethod', 'staticmethod'):
                        return False
                if isinstance(decorator, nodes.Attribute):
                    if decorator.attrname in ('classmethod', 'staticmethod'):
                        return False
        if node.is_abstract():
            return False
        if node.name == '__init__':
            return False
        if overrides_a_method(node.parent.frame(), node.name):
            return False
        self._meth_could_be_func = True
        return True
    leave_asyncfunctiondef = leave_functiondef
