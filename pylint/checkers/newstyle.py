"""Check for new / old style related problems."""
from __future__ import annotations
from typing import TYPE_CHECKING
import astroid
from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.checkers.utils import has_known_bases, node_frame_class, only_required_for_messages
from pylint.typing import MessageDefinitionTuple
if TYPE_CHECKING:
    from pylint.lint import PyLinter
MSGS: dict[str, MessageDefinitionTuple] = {'E1003': ('Bad first argument %r given to super()', 'bad-super-call', 'Used when another argument than the current class is given as first argument of the super builtin.')}

class NewStyleConflictChecker(BaseChecker):
    """Checks for usage of new style capabilities on old style classes and
    other new/old styles conflicts problems.

    * use of property, __slots__, super
    * "super" usage
    """
    name = 'newstyle'
    msgs = MSGS
    options = ()

    @only_required_for_messages('bad-super-call')
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check use of super."""
        if node.is_method():
            for stmt in node.body:
                if isinstance(stmt, nodes.Call):
                    if is_super(stmt.func):
                        self._check_super_call(stmt, node)

    def _check_super_call(self, super_call: nodes.Call, method: nodes.FunctionDef) -> None:
        """Check if the super call is valid."""
        if len(super_call.args) not in (0, 1, 2):
            return  # Not a valid super() call, but that's not what we're checking

        if len(super_call.args) == 0:
            # Python 3 form of super(), always correct
            return

        arg = super_call.args[0]
        if isinstance(arg, nodes.Name) and arg.name != method.parent.name:
            self.add_message(
                "bad-super-call",
                node=super_call,
                args=(arg.name,)
            )
    visit_asyncfunctiondef = visit_functiondef
