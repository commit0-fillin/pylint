from __future__ import annotations
import sys
from typing import TYPE_CHECKING, Tuple, Type, cast
from astroid import nodes
from pylint.checkers import BaseChecker, utils
from pylint.checkers.utils import only_required_for_messages, safe_infer
from pylint.interfaces import INFERENCE
if TYPE_CHECKING:
    from pylint.lint import PyLinter
if sys.version_info >= (3, 10):
    from typing import TypeGuard
else:
    from typing_extensions import TypeGuard

class CodeStyleChecker(BaseChecker):
    """Checkers that can improve code consistency.

    As such they don't necessarily provide a performance benefit and
    are often times opinionated.

    Before adding another checker here, consider this:
    1. Does the checker provide a clear benefit,
       i.e. detect a common issue or improve performance
       => it should probably be part of the core checker classes
    2. Is it something that would improve code consistency,
       maybe because it's slightly better with regard to performance
       and therefore preferred => this is the right place
    3. Everything else should go into another extension
    """
    name = 'code_style'
    msgs = {'R6101': ('Consider using namedtuple or dataclass for dictionary values', 'consider-using-namedtuple-or-dataclass', 'Emitted when dictionary values can be replaced by namedtuples or dataclass instances.'), 'R6102': ('Consider using an in-place tuple instead of list', 'consider-using-tuple', 'Only for style consistency! Emitted where an in-place defined ``list`` can be replaced by a ``tuple``. Due to optimizations by CPython, there is no performance benefit from it.'), 'R6103': ("Use '%s' instead", 'consider-using-assignment-expr', 'Emitted when an if assignment is directly followed by an if statement and both can be combined by using an assignment expression ``:=``. Requires Python 3.8 and ``py-version >= 3.8``.'), 'R6104': ("Use '%s' to do an augmented assign directly", 'consider-using-augmented-assign', 'Emitted when an assignment is referring to the object that it is assigning to. This can be changed to be an augmented assign.\nDisabled by default!', {'default_enabled': False}), 'R6105': ("Prefer 'typing.NamedTuple' over 'collections.namedtuple'", 'prefer-typing-namedtuple', "'typing.NamedTuple' uses the well-known 'class' keyword with type-hints for readability (it's also faster as it avoids an internal exec call).\nDisabled by default!", {'default_enabled': False})}
    options = (('max-line-length-suggestions', {'type': 'int', 'default': 0, 'metavar': '<int>', 'help': 'Max line length for which to sill emit suggestions. Used to prevent optional suggestions which would get split by a code formatter (e.g., black). Will default to the setting for ``max-line-length``.'}),)

    def _check_dict_consider_namedtuple_dataclass(self, node: nodes.Dict) -> None:
        """Check if dictionary values can be replaced by Namedtuple or Dataclass."""
        if len(node.items) < 2:
            return

        all_keys_const = all(isinstance(key, nodes.Const) for key, _ in node.items)
        all_values_same_type = len(set(type(value) for _, value in node.items)) == 1

        if all_keys_const and all_values_same_type:
            self.add_message("consider-using-namedtuple-or-dataclass", node=node)

    def _check_consider_using_assignment_expr(self, node: nodes.If) -> None:
        """Check if an assignment expression (walrus operator) can be used.

        For example if an assignment is directly followed by an if statement:
        >>> x = 2
        >>> if x:
        >>>     ...

        Can be replaced by:
        >>> if (x := 2):
        >>>     ...

        Note: Assignment expressions were added in Python 3.8
        """
        if not self.linter.is_message_enabled("consider-using-assignment-expr"):
            return

        prev_sibling = node.previous_sibling()
        if not isinstance(prev_sibling, (nodes.Assign, nodes.AnnAssign)):
            return

        assign_names = list(prev_sibling.get_children())
        if len(assign_names) != 2:
            return

        name = assign_names[0]
        if not isinstance(name, nodes.AssignName):
            return

        if not self._check_prev_sibling_to_if_stmt(prev_sibling, name.name):
            return

        if self._check_ignore_assignment_expr_suggestion(node, name.name):
            return

        if isinstance(node.test, nodes.Compare):
            suggestion = f"if ({name.name} := {prev_sibling.value.as_string()}) {node.test.as_string()[len(name.name):]}"
        else:
            suggestion = f"if ({name.name} := {prev_sibling.value.as_string()})"

        self.add_message(
            "consider-using-assignment-expr",
            node=node,
            args=(suggestion,),
            confidence=INFERENCE,
        )

    @staticmethod
    def _check_prev_sibling_to_if_stmt(prev_sibling: nodes.NodeNG | None, name: str | None) -> TypeGuard[nodes.Assign | nodes.AnnAssign]:
        """Check if previous sibling is an assignment with the same name.

        Ignore statements which span multiple lines.
        """
        return (
            isinstance(prev_sibling, (nodes.Assign, nodes.AnnAssign))
            and prev_sibling.lineno == prev_sibling.end_lineno
            and isinstance(prev_sibling.targets[0], nodes.AssignName)
            and prev_sibling.targets[0].name == name
        )

    @staticmethod
    def _check_ignore_assignment_expr_suggestion(node: nodes.If, name: str | None) -> bool:
        """Return True if suggestion for assignment expr should be ignored.

        E.g., in cases where a match statement would be a better fit
        (multiple conditions).
        """
        if isinstance(node.test, nodes.Compare):
            return len(node.test.ops) > 1 or any(
                isinstance(op, (nodes.In, nodes.NotIn)) for op, _ in node.test.ops
            )
        if isinstance(node.test, nodes.BoolOp):
            return any(
                isinstance(operand, nodes.Name) and operand.name == name
                for operand in node.test.values
            )
        return False
