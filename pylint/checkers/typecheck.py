"""Try to find more bugs in the code using astroid inference capabilities."""
from __future__ import annotations
import heapq
import itertools
import operator
import re
import shlex
import sys
from collections.abc import Callable, Iterable
from functools import cached_property, singledispatch
from re import Pattern
from typing import TYPE_CHECKING, Any, Literal, Union
import astroid
import astroid.exceptions
import astroid.helpers
from astroid import arguments, bases, nodes, util
from astroid.nodes import _base_nodes
from astroid.typing import InferenceResult, SuccessfulInferenceResult
from pylint.checkers import BaseChecker, utils
from pylint.checkers.utils import decorated_with, decorated_with_property, has_known_bases, is_builtin_object, is_comprehension, is_hashable, is_inside_abstract_class, is_iterable, is_mapping, is_module_ignored, is_node_in_type_annotation_context, is_none, is_overload_stub, is_postponed_evaluation_enabled, is_super, node_ignores_exception, only_required_for_messages, safe_infer, supports_delitem, supports_getitem, supports_membership_test, supports_setitem
from pylint.constants import PY310_PLUS
from pylint.interfaces import HIGH, INFERENCE
from pylint.typing import MessageDefinitionTuple
if TYPE_CHECKING:
    from pylint.lint import PyLinter
CallableObjects = Union[bases.BoundMethod, bases.UnboundMethod, nodes.FunctionDef, nodes.Lambda, nodes.ClassDef]
STR_FORMAT = {'builtins.str.format'}
ASYNCIO_COROUTINE = 'asyncio.coroutines.coroutine'
BUILTIN_TUPLE = 'builtins.tuple'
TYPE_ANNOTATION_NODES_TYPES = (nodes.AnnAssign, nodes.Arguments, nodes.FunctionDef)
BUILTINS_IMPLICIT_RETURN_NONE = {'builtins.dict': {'clear', 'update'}, 'builtins.list': {'append', 'clear', 'extend', 'insert', 'remove', 'reverse', 'sort'}, 'builtins.set': {'add', 'clear', 'difference_update', 'discard', 'intersection_update', 'remove', 'symmetric_difference_update', 'update'}}

class VERSION_COMPATIBLE_OVERLOAD:
    pass
VERSION_COMPATIBLE_OVERLOAD_SENTINEL = VERSION_COMPATIBLE_OVERLOAD()

def _is_owner_ignored(owner: SuccessfulInferenceResult, attrname: str | None, ignored_classes: Iterable[str], ignored_modules: Iterable[str]) -> bool:
    """Check if the given owner should be ignored.

    This will verify if the owner's module is in *ignored_modules*
    or the owner's module fully qualified name is in *ignored_modules*
    or if the *ignored_modules* contains a pattern which catches
    the fully qualified name of the module.

    Also, similar checks are done for the owner itself, if its name
    matches any name from the *ignored_classes* or if its qualified
    name can be found in *ignored_classes*.
    """
    if isinstance(owner, nodes.Module):
        owner_name = owner.name
        return (
            any(owner_name == ignored_mod for ignored_mod in ignored_modules)
            or any(fnmatch.fnmatch(owner_name, ignored_pattern) for ignored_pattern in ignored_modules)
        )
    
    if isinstance(owner, nodes.ClassDef):
        owner_name = owner.name
        owner_qname = owner.qname()
        return (
            any(owner_name == ignored_class for ignored_class in ignored_classes)
            or any(owner_qname == ignored_class for ignored_class in ignored_classes)
            or any(fnmatch.fnmatch(owner_qname, ignored_pattern) for ignored_pattern in ignored_classes)
        )
    
    return False

def _similar_names(owner: SuccessfulInferenceResult, attrname: str | None, distance_threshold: int, max_choices: int) -> list[str]:
    """Given an owner and a name, try to find similar names.

    The similar names are searched given a distance metric and only
    a given number of choices will be returned.
    """
    if attrname is None:
        return []
    
    possible_names = []
    if isinstance(owner, (nodes.Module, nodes.ClassDef)):
        possible_names = [m for m in owner.getattr(attrname) if isinstance(m, nodes.FunctionDef)]
    
    if not possible_names:
        try:
            possible_names = owner.getattr(attrname)
        except astroid.NotFoundError:
            possible_names = []
    
    def compute_distance(name: str) -> int:
        return _levenshtein_distance(attrname, name)
    
    similar_names = [
        (name, compute_distance(name))
        for name in possible_names
        if compute_distance(name) <= distance_threshold
    ]
    similar_names.sort(key=lambda x: x[1])
    return [name for name, _ in similar_names[:max_choices]]

def _levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]
MSGS: dict[str, MessageDefinitionTuple] = {'E1101': ('%s %r has no %r member%s', 'no-member', 'Used when a variable is accessed for a nonexistent member.', {'old_names': [('E1103', 'maybe-no-member')]}), 'I1101': ('%s %r has no %r member%s, but source is unavailable. Consider adding this module to extension-pkg-allow-list if you want to perform analysis based on run-time introspection of living objects.', 'c-extension-no-member', 'Used when a variable is accessed for non-existent member of C extension. Due to unavailability of source static analysis is impossible, but it may be performed by introspecting living objects in run-time.'), 'E1102': ('%s is not callable', 'not-callable', 'Used when an object being called has been inferred to a non callable object.'), 'E1111': ('Assigning result of a function call, where the function has no return', 'assignment-from-no-return', "Used when an assignment is done on a function call but the inferred function doesn't return anything."), 'E1120': ('No value for argument %s in %s call', 'no-value-for-parameter', 'Used when a function call passes too few arguments.'), 'E1121': ('Too many positional arguments for %s call', 'too-many-function-args', 'Used when a function call passes too many positional arguments.'), 'E1123': ('Unexpected keyword argument %r in %s call', 'unexpected-keyword-arg', "Used when a function call passes a keyword argument that doesn't correspond to one of the function's parameter names."), 'E1124': ('Argument %r passed by position and keyword in %s call', 'redundant-keyword-arg', 'Used when a function call would result in assigning multiple values to a function parameter, one value from a positional argument and one from a keyword argument.'), 'E1125': ('Missing mandatory keyword argument %r in %s call', 'missing-kwoa', 'Used when a function call does not pass a mandatory keyword-only argument.'), 'E1126': ('Sequence index is not an int, slice, or instance with __index__', 'invalid-sequence-index', 'Used when a sequence type is indexed with an invalid type. Valid types are ints, slices, and objects with an __index__ method.'), 'E1127': ('Slice index is not an int, None, or instance with __index__', 'invalid-slice-index', 'Used when a slice index is not an integer, None, or an object with an __index__ method.'), 'E1128': ('Assigning result of a function call, where the function returns None', 'assignment-from-none', 'Used when an assignment is done on a function call but the inferred function returns nothing but None.', {'old_names': [('W1111', 'old-assignment-from-none')]}), 'E1129': ("Context manager '%s' doesn't implement __enter__ and __exit__.", 'not-context-manager', "Used when an instance in a with statement doesn't implement the context manager protocol(__enter__/__exit__)."), 'E1130': ('%s', 'invalid-unary-operand-type', 'Emitted when a unary operand is used on an object which does not support this type of operation.'), 'E1131': ('%s', 'unsupported-binary-operation', 'Emitted when a binary arithmetic operation between two operands is not supported.'), 'E1132': ('Got multiple values for keyword argument %r in function call', 'repeated-keyword', 'Emitted when a function call got multiple values for a keyword.'), 'E1135': ("Value '%s' doesn't support membership test", 'unsupported-membership-test', "Emitted when an instance in membership test expression doesn't implement membership protocol (__contains__/__iter__/__getitem__)."), 'E1136': ("Value '%s' is unsubscriptable", 'unsubscriptable-object', "Emitted when a subscripted value doesn't support subscription (i.e. doesn't define __getitem__ method or __class_getitem__ for a class)."), 'E1137': ('%r does not support item assignment', 'unsupported-assignment-operation', "Emitted when an object does not support item assignment (i.e. doesn't define __setitem__ method)."), 'E1138': ('%r does not support item deletion', 'unsupported-delete-operation', "Emitted when an object does not support item deletion (i.e. doesn't define __delitem__ method)."), 'E1139': ('Invalid metaclass %r used', 'invalid-metaclass', 'Emitted whenever we can detect that a class is using, as a metaclass, something which might be invalid for using as a metaclass.'), 'E1141': ('Unpacking a dictionary in iteration without calling .items()', 'dict-iter-missing-items', 'Emitted when trying to iterate through a dict without calling .items()'), 'E1142': ("'await' should be used within an async function", 'await-outside-async', 'Emitted when await is used outside an async function.'), 'E1143': ("'%s' is unhashable and can't be used as a %s in a %s", 'unhashable-member', "Emitted when a dict key or set member is not hashable (i.e. doesn't define __hash__ method).", {'old_names': [('E1140', 'unhashable-dict-key')]}), 'E1144': ('Slice step cannot be 0', 'invalid-slice-step', "Used when a slice step is 0 and the object doesn't implement a custom __getitem__ method."), 'W1113': ('Keyword argument before variable positional arguments list in the definition of %s function', 'keyword-arg-before-vararg', 'When defining a keyword argument before variable positional arguments, one can end up in having multiple values passed for the aforementioned parameter in case the method is called with keyword arguments.'), 'W1114': ('Positional arguments appear to be out of order', 'arguments-out-of-order', "Emitted  when the caller's argument names fully match the parameter names in the function signature but do not have the same order."), 'W1115': ('Non-string value assigned to __name__', 'non-str-assignment-to-dunder-name', 'Emitted when a non-string value is assigned to __name__'), 'W1116': ('Second argument of isinstance is not a type', 'isinstance-second-argument-not-valid-type', 'Emitted when the second argument of an isinstance call is not a type.'), 'W1117': ('%r will be included in %r since a positional-only parameter with this name already exists', 'kwarg-superseded-by-positional-arg', 'Emitted when a function is called with a keyword argument that has the same name as a positional-only parameter and the function contains a keyword variadic parameter dict.')}
SEQUENCE_TYPES = {'str', 'unicode', 'list', 'tuple', 'bytearray', 'xrange', 'range', 'bytes', 'memoryview'}

def _emit_no_member(node: nodes.Attribute | nodes.AssignAttr | nodes.DelAttr, owner: InferenceResult, owner_name: str | None, mixin_class_rgx: Pattern[str], ignored_mixins: bool=True, ignored_none: bool=True) -> bool:
    """Try to see if no-member should be emitted for the given owner.

    The following cases are ignored:

        * the owner is a function and it has decorators.
        * the owner is an instance and it has __getattr__, __getattribute__ implemented
        * the module is explicitly ignored from no-member checks
        * the owner is a class and the name can be found in its metaclass.
        * The access node is protected by an except handler, which handles
          AttributeError, Exception or bare except.
        * The node is guarded behind and `IF` or `IFExp` node
    """
    if isinstance(owner, astroid.FunctionDef) and owner.decorators:
        return False

    if isinstance(owner, astroid.Instance):
        if owner.has_dynamic_getattr():
            return False
        if not has_known_bases(owner):
            return False

    if isinstance(owner, nodes.Module):
        if owner.name in ignored_modules:
            return False

    if isinstance(owner, nodes.ClassDef):
        if owner.metaclass():
            try:
                owner.getattr(node.attrname)
                return False
            except astroid.NotFoundError:
                pass

    if node_ignores_exception(node, AttributeError):
        return False

    if is_node_inside_try_except(node):
        return False

    if is_node_in_guarded_import(node):
        return False

    if ignored_mixins and owner_name and mixin_class_rgx.match(owner_name):
        return False

    if ignored_none and isinstance(owner, nodes.Const) and owner.value is None:
        return False

    return True

def _has_parent_of_type(node: nodes.Call, node_type: nodes.Keyword | nodes.Starred, statement: _base_nodes.Statement) -> bool:
    """Check if the given node has a parent of the given type."""
    pass

def _no_context_variadic(node: nodes.Call, variadic_name: str | None, variadic_type: nodes.Keyword | nodes.Starred, variadics: list[nodes.Keyword | nodes.Starred]) -> bool:
    """Verify if the given call node has variadic nodes without context.

    This is a workaround for handling cases of nested call functions
    which don't have the specific call context at hand.
    Variadic arguments (variable positional arguments and variable
    keyword arguments) are inferred, inherently wrong, by astroid
    as a Tuple, respectively a Dict with empty elements.
    This can lead pylint to believe that a function call receives
    too few arguments.
    """
    pass

def _infer_from_metaclass_constructor(cls: nodes.ClassDef, func: nodes.FunctionDef) -> InferenceResult | None:
    """Try to infer what the given *func* constructor is building.

    :param astroid.FunctionDef func:
        A metaclass constructor. Metaclass definitions can be
        functions, which should accept three arguments, the name of
        the class, the bases of the class and the attributes.
        The function could return anything, but usually it should
        be a proper metaclass.
    :param astroid.ClassDef cls:
        The class for which the *func* parameter should generate
        a metaclass.
    :returns:
        The class generated by the function or None,
        if we couldn't infer it.
    :rtype: astroid.ClassDef
    """
    pass

class TypeChecker(BaseChecker):
    """Try to find bugs in the code using type inference."""
    name = 'typecheck'
    msgs = MSGS
    options = (('ignore-on-opaque-inference', {'default': True, 'type': 'yn', 'metavar': '<y or n>', 'help': 'This flag controls whether pylint should warn about no-member and similar checks whenever an opaque object is returned when inferring. The inference can return multiple potential results while evaluating a Python object, but some branches might not be evaluated, which results in partial inference. In that case, it might be useful to still emit no-member and other checks for the rest of the inferred objects.'}), ('mixin-class-rgx', {'default': '.*[Mm]ixin', 'type': 'regexp', 'metavar': '<regexp>', 'help': 'Regex pattern to define which classes are considered mixins.'}), ('ignore-mixin-members', {'default': True, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Tells whether missing members accessed in mixin class should be ignored. A class is considered mixin if its name matches the mixin-class-rgx option.', 'kwargs': {'new_names': ['ignore-checks-for-mixin']}}), ('ignored-checks-for-mixins', {'default': ['no-member', 'not-async-context-manager', 'not-context-manager', 'attribute-defined-outside-init'], 'type': 'csv', 'metavar': '<list of messages names>', 'help': 'List of symbolic message names to ignore for Mixin members.'}), ('ignore-none', {'default': True, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Tells whether to warn about missing members when the owner of the attribute is inferred to be None.'}), ('ignored-classes', {'default': ('optparse.Values', 'thread._local', '_thread._local', 'argparse.Namespace'), 'type': 'csv', 'metavar': '<members names>', 'help': 'List of class names for which member attributes should not be checked (useful for classes with dynamically set attributes). This supports the use of qualified names.'}), ('generated-members', {'default': (), 'type': 'string', 'metavar': '<members names>', 'help': "List of members which are set dynamically and missed by pylint inference system, and so shouldn't trigger E1101 when accessed. Python regular expressions are accepted."}), ('contextmanager-decorators', {'default': ['contextlib.contextmanager'], 'type': 'csv', 'metavar': '<decorator names>', 'help': 'List of decorators that produce context managers, such as contextlib.contextmanager. Add to this list to register other decorators that produce valid context managers.'}), ('missing-member-hint-distance', {'default': 1, 'type': 'int', 'metavar': '<member hint edit distance>', 'help': 'The minimum edit distance a name should have in order to be considered a similar match for a missing member name.'}), ('missing-member-max-choices', {'default': 1, 'type': 'int', 'metavar': '<member hint max choices>', 'help': 'The total number of similar names that should be taken in consideration when showing a hint for a missing member.'}), ('missing-member-hint', {'default': True, 'type': 'yn', 'metavar': '<missing member hint>', 'help': 'Show a hint with possible names when a member name was not found. The aspect of finding the hint is based on edit distance.'}), ('signature-mutators', {'default': [], 'type': 'csv', 'metavar': '<decorator names>', 'help': 'List of decorators that change the signature of a decorated function.'}))
    visit_asyncfunctiondef = visit_functiondef

    @only_required_for_messages('no-member', 'c-extension-no-member')
    def visit_attribute(self, node: nodes.Attribute | nodes.AssignAttr | nodes.DelAttr) -> None:
        """Check that the accessed attribute exists.

        to avoid too much false positives for now, we'll consider the code as
        correct if a single of the inferred nodes has the accessed attribute.

        function/method, super call and metaclasses are ignored
        """
        pass

    @only_required_for_messages('assignment-from-no-return', 'assignment-from-none', 'non-str-assignment-to-dunder-name')
    def visit_assign(self, node: nodes.Assign) -> None:
        """Process assignments in the AST."""
        pass

    def _check_assignment_from_function_call(self, node: nodes.Assign) -> None:
        """When assigning to a function call, check that the function returns a valid
        value.
        """
        pass

    def _check_dundername_is_string(self, node: nodes.Assign) -> None:
        """Check a string is assigned to self.__name__."""
        pass

    def _check_uninferable_call(self, node: nodes.Call) -> None:
        """Check that the given uninferable Call node does not
        call an actual function.
        """
        pass

    def _check_argument_order(self, node: nodes.Call, call_site: arguments.CallSite, called: CallableObjects, called_param_names: list[str | None]) -> None:
        """Match the supplied argument names against the function parameters.

        Warn if some argument names are not in the same order as they are in
        the function signature.
        """
        pass

    def visit_call(self, node: nodes.Call) -> None:
        """Check that called functions/methods are inferred to callable objects,
        and that passed arguments match the parameters in the inferred function.
        """
        pass

    @staticmethod
    def _keyword_argument_is_in_all_decorator_returns(func: nodes.FunctionDef, keyword: str) -> bool:
        """Check if the keyword argument exists in all signatures of the
        return values of all decorators of the function.
        """
        pass

    def _check_not_callable(self, node: nodes.Call, inferred_call: nodes.NodeNG | None) -> None:
        """Checks to see if the not-callable message should be emitted.

        Only functions, generators and objects defining __call__ are "callable"
        We ignore instances of descriptors since astroid cannot properly handle them yet
        """
        pass

    @only_required_for_messages('invalid-unary-operand-type')
    def visit_unaryop(self, node: nodes.UnaryOp) -> None:
        """Detect TypeErrors for unary operands."""
        pass

    def _detect_unsupported_alternative_union_syntax(self, node: nodes.BinOp) -> None:
        """Detect if unsupported alternative Union syntax (PEP 604) was used."""
        pass

    def _includes_version_compatible_overload(self, attrs: list[nodes.NodeNG]) -> bool:
        """Check if a set of overloads of an operator includes one that
        can be relied upon for our configured Python version.

        If we are running under a Python 3.10+ runtime but configured for
        pre-3.10 compatibility then Astroid will have inferred the
        existence of __or__ / __ror__ on builtins.type, but these aren't
        available in the configured version of Python.
        """
        pass

    def _check_unsupported_alternative_union_syntax(self, node: nodes.BinOp) -> None:
        """Check if left or right node is of type `type`.

        If either is, and doesn't support an or operator via a metaclass,
        infer that this is a mistaken attempt to use alternative union
        syntax when not supported.
        """
        pass

    @only_required_for_messages('unsupported-binary-operation')
    def _visit_binop(self, node: nodes.BinOp) -> None:
        """Detect TypeErrors for binary arithmetic operands."""
        pass

    @only_required_for_messages('unsupported-binary-operation')
    def _visit_augassign(self, node: nodes.AugAssign) -> None:
        """Detect TypeErrors for augmented binary arithmetic operands."""
        pass

class IterableChecker(BaseChecker):
    """Checks for non-iterables used in an iterable context.

    Contexts include:
    - for-statement
    - starargs in function call
    - `yield from`-statement
    - list, dict and set comprehensions
    - generator expressions
    Also checks for non-mappings in function call kwargs.
    """
    name = 'typecheck'
    msgs = {'E1133': ('Non-iterable value %s is used in an iterating context', 'not-an-iterable', 'Used when a non-iterable value is used in place where iterable is expected'), 'E1134': ('Non-mapping value %s is used in a mapping context', 'not-a-mapping', 'Used when a non-mapping value is used in place where mapping is expected')}
