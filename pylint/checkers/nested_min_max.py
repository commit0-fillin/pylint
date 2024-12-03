"""Check for use of nested min/max functions."""
from __future__ import annotations
import copy
from typing import TYPE_CHECKING
from astroid import nodes, objects
from astroid.const import Context
from pylint.checkers import BaseChecker
from pylint.checkers.utils import only_required_for_messages, safe_infer
from pylint.constants import PY39_PLUS
from pylint.interfaces import INFERENCE
if TYPE_CHECKING:
    from pylint.lint import PyLinter
DICT_TYPES = (objects.DictValues, objects.DictKeys, objects.DictItems, nodes.node_classes.Dict)

class NestedMinMaxChecker(BaseChecker):
    """Multiple nested min/max calls on the same line will raise multiple messages.

    This behaviour is intended as it would slow down the checker to check
    for nested call with minimal benefits.
    """
    FUNC_NAMES = ('builtins.min', 'builtins.max')
    name = 'nested_min_max'
    msgs = {'W3301': ("Do not use nested call of '%s'; it's possible to do '%s' instead", 'nested-min-max', 'Nested calls ``min(1, min(2, 3))`` can be rewritten as ``min(1, 2, 3)``.')}

    def _is_splattable_expression(self, arg: nodes.NodeNG) -> bool:
        """Returns true if expression under min/max could be converted to splat
        expression.
        """
        if isinstance(arg, (nodes.List, nodes.Tuple, nodes.Set)):
            return True
        if isinstance(arg, nodes.Call):
            inferred = safe_infer(arg.func)
            if isinstance(inferred, nodes.ClassDef):
                return inferred.qname() in SUBSCRIPTABLE_CLASSES_PEP585
        return False
