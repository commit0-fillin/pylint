"""Special methods checker and helper function's module."""
from __future__ import annotations
from collections.abc import Callable
import astroid
from astroid import bases, nodes, util
from astroid.context import InferenceContext
from astroid.typing import InferenceResult
from pylint.checkers import BaseChecker
from pylint.checkers.utils import PYMETHODS, SPECIAL_METHODS_PARAMS, decorated_with, is_function_body_ellipsis, only_required_for_messages, safe_infer
from pylint.lint.pylinter import PyLinter
NEXT_METHOD = '__next__'

def _safe_infer_call_result(node: nodes.FunctionDef, caller: nodes.FunctionDef, context: InferenceContext | None=None) -> InferenceResult | None:
    """Safely infer the return value of a function.

    Returns None if inference failed or if there is some ambiguity (more than
    one node has been inferred). Otherwise, returns inferred value.
    """
    try:
        inferred_results = list(node.infer_call_result(caller, context=context))
        if len(inferred_results) == 1:
            return inferred_results[0]
        if len(inferred_results) > 1:
            # Check if all inferred results are the same
            if all(result == inferred_results[0] for result in inferred_results[1:]):
                return inferred_results[0]
    except astroid.InferenceError:
        pass
    return None

class SpecialMethodsChecker(BaseChecker):
    """Checker which verifies that special methods
    are implemented correctly.
    """
    name = 'classes'
    msgs = {'E0301': ('__iter__ returns non-iterator', 'non-iterator-returned', f'Used when an __iter__ method returns something which is not an iterable (i.e. has no `{NEXT_METHOD}` method)', {'old_names': [('W0234', 'old-non-iterator-returned-1'), ('E0234', 'old-non-iterator-returned-2')]}), 'E0302': ('The special method %r expects %s param(s), %d %s given', 'unexpected-special-method-signature', 'Emitted when a special method was defined with an invalid number of parameters. If it has too few or too many, it might not work at all.', {'old_names': [('E0235', 'bad-context-manager')]}), 'E0303': ('__len__ does not return non-negative integer', 'invalid-length-returned', 'Used when a __len__ method returns something which is not a non-negative integer'), 'E0304': ('__bool__ does not return bool', 'invalid-bool-returned', 'Used when a __bool__ method returns something which is not a bool'), 'E0305': ('__index__ does not return int', 'invalid-index-returned', 'Used when an __index__ method returns something which is not an integer'), 'E0306': ('__repr__ does not return str', 'invalid-repr-returned', 'Used when a __repr__ method returns something which is not a string'), 'E0307': ('__str__ does not return str', 'invalid-str-returned', 'Used when a __str__ method returns something which is not a string'), 'E0308': ('__bytes__ does not return bytes', 'invalid-bytes-returned', 'Used when a __bytes__ method returns something which is not bytes'), 'E0309': ('__hash__ does not return int', 'invalid-hash-returned', 'Used when a __hash__ method returns something which is not an integer'), 'E0310': ('__length_hint__ does not return non-negative integer', 'invalid-length-hint-returned', 'Used when a __length_hint__ method returns something which is not a non-negative integer'), 'E0311': ('__format__ does not return str', 'invalid-format-returned', 'Used when a __format__ method returns something which is not a string'), 'E0312': ('__getnewargs__ does not return a tuple', 'invalid-getnewargs-returned', 'Used when a __getnewargs__ method returns something which is not a tuple'), 'E0313': ('__getnewargs_ex__ does not return a tuple containing (tuple, dict)', 'invalid-getnewargs-ex-returned', 'Used when a __getnewargs_ex__ method returns something which is not of the form tuple(tuple, dict)')}

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._protocol_map: dict[str, Callable[[nodes.FunctionDef, InferenceResult], None]] = {'__iter__': self._check_iter, '__len__': self._check_len, '__bool__': self._check_bool, '__index__': self._check_index, '__repr__': self._check_repr, '__str__': self._check_str, '__bytes__': self._check_bytes, '__hash__': self._check_hash, '__length_hint__': self._check_length_hint, '__format__': self._check_format, '__getnewargs__': self._check_getnewargs, '__getnewargs_ex__': self._check_getnewargs_ex}
    visit_asyncfunctiondef = visit_functiondef
