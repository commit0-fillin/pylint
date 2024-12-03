"""Some functions that may be useful for various checkers."""
from __future__ import annotations
import builtins
import fnmatch
import itertools
import numbers
import re
import string
from collections.abc import Iterable, Iterator
from functools import lru_cache, partial
from re import Match
from typing import TYPE_CHECKING, Any, Callable, TypeVar
import _string
import astroid.objects
from astroid import TooManyLevelsError, nodes, util
from astroid.context import InferenceContext
from astroid.exceptions import AstroidError
from astroid.nodes._base_nodes import ImportNode, Statement
from astroid.typing import InferenceResult, SuccessfulInferenceResult
from pylint.constants import TYPING_NEVER, TYPING_NORETURN
if TYPE_CHECKING:
    from functools import _lru_cache_wrapper
    from pylint.checkers import BaseChecker
_NodeT = TypeVar('_NodeT', bound=nodes.NodeNG)
_CheckerT = TypeVar('_CheckerT', bound='BaseChecker')
AstCallbackMethod = Callable[[_CheckerT, _NodeT], None]
COMP_NODE_TYPES = (nodes.ListComp, nodes.SetComp, nodes.DictComp, nodes.GeneratorExp)
EXCEPTIONS_MODULE = 'builtins'
ABC_MODULES = {'abc', '_py_abc'}
ABC_METHODS = {'abc.abstractproperty', 'abc.abstractmethod', 'abc.abstractclassmethod', 'abc.abstractstaticmethod'}
TYPING_PROTOCOLS = frozenset({'typing.Protocol', 'typing_extensions.Protocol', '.Protocol'})
COMMUTATIVE_OPERATORS = frozenset({'*', '+', '^', '&', '|'})
ITER_METHOD = '__iter__'
AITER_METHOD = '__aiter__'
NEXT_METHOD = '__next__'
GETITEM_METHOD = '__getitem__'
CLASS_GETITEM_METHOD = '__class_getitem__'
SETITEM_METHOD = '__setitem__'
DELITEM_METHOD = '__delitem__'
CONTAINS_METHOD = '__contains__'
KEYS_METHOD = 'keys'
_SPECIAL_METHODS_PARAMS = {None: ('__new__', '__init__', '__call__', '__init_subclass__'), 0: ('__del__', '__repr__', '__str__', '__bytes__', '__hash__', '__bool__', '__dir__', '__len__', '__length_hint__', '__iter__', '__reversed__', '__neg__', '__pos__', '__abs__', '__invert__', '__complex__', '__int__', '__float__', '__index__', '__trunc__', '__floor__', '__ceil__', '__enter__', '__aenter__', '__getnewargs_ex__', '__getnewargs__', '__getstate__', '__reduce__', '__copy__', '__unicode__', '__nonzero__', '__await__', '__aiter__', '__anext__', '__fspath__', '__subclasses__'), 1: ('__format__', '__lt__', '__le__', '__eq__', '__ne__', '__gt__', '__ge__', '__getattr__', '__getattribute__', '__delattr__', '__delete__', '__instancecheck__', '__subclasscheck__', '__getitem__', '__missing__', '__delitem__', '__contains__', '__add__', '__sub__', '__mul__', '__truediv__', '__floordiv__', '__rfloordiv__', '__mod__', '__divmod__', '__lshift__', '__rshift__', '__and__', '__xor__', '__or__', '__radd__', '__rsub__', '__rmul__', '__rtruediv__', '__rmod__', '__rdivmod__', '__rpow__', '__rlshift__', '__rrshift__', '__rand__', '__rxor__', '__ror__', '__iadd__', '__isub__', '__imul__', '__itruediv__', '__ifloordiv__', '__imod__', '__ilshift__', '__irshift__', '__iand__', '__ixor__', '__ior__', '__ipow__', '__setstate__', '__reduce_ex__', '__deepcopy__', '__cmp__', '__matmul__', '__rmatmul__', '__imatmul__', '__div__'), 2: ('__setattr__', '__get__', '__set__', '__setitem__', '__set_name__'), 3: ('__exit__', '__aexit__'), (0, 1): ('__round__',), (1, 2): ('__pow__',)}
SPECIAL_METHODS_PARAMS = {name: params for params, methods in _SPECIAL_METHODS_PARAMS.items() for name in methods}
PYMETHODS = set(SPECIAL_METHODS_PARAMS)
SUBSCRIPTABLE_CLASSES_PEP585 = frozenset(('builtins.tuple', 'builtins.list', 'builtins.dict', 'builtins.set', 'builtins.frozenset', 'builtins.type', 'collections.deque', 'collections.defaultdict', 'collections.OrderedDict', 'collections.Counter', 'collections.ChainMap', '_collections_abc.Awaitable', '_collections_abc.Coroutine', '_collections_abc.AsyncIterable', '_collections_abc.AsyncIterator', '_collections_abc.AsyncGenerator', '_collections_abc.Iterable', '_collections_abc.Iterator', '_collections_abc.Generator', '_collections_abc.Reversible', '_collections_abc.Container', '_collections_abc.Collection', '_collections_abc.Callable', '_collections_abc.Set', '_collections_abc.MutableSet', '_collections_abc.Mapping', '_collections_abc.MutableMapping', '_collections_abc.Sequence', '_collections_abc.MutableSequence', '_collections_abc.ByteString', '_collections_abc.MappingView', '_collections_abc.KeysView', '_collections_abc.ItemsView', '_collections_abc.ValuesView', 'contextlib.AbstractContextManager', 'contextlib.AbstractAsyncContextManager', 're.Pattern', 're.Match'))
SINGLETON_VALUES = {True, False, None}
TERMINATING_FUNCS_QNAMES = frozenset({'_sitebuiltins.Quitter', 'sys.exit', 'posix._exit', 'nt._exit'})

class NoSuchArgumentError(Exception):
    pass

class InferredTypeError(Exception):
    pass

def get_all_elements(node: nodes.NodeNG) -> Iterable[nodes.NodeNG]:
    """Recursively returns all atoms in nested lists and tuples."""
    if isinstance(node, (nodes.List, nodes.Tuple)):
        for child in node.elts:
            yield from get_all_elements(child)
    else:
        yield node

def is_super(node: nodes.NodeNG) -> bool:
    """Return True if the node is referencing the "super" builtin function."""
    return (
        isinstance(node, nodes.Name)
        and node.name == 'super'
        and node.root().name == 'builtins'
    )

def is_error(node: nodes.FunctionDef) -> bool:
    """Return true if the given function node only raises an exception."""
    return (
        len(node.body) == 1
        and isinstance(node.body[0], nodes.Raise)
    )
builtins = builtins.__dict__.copy()
SPECIAL_BUILTINS = ('__builtins__',)

def is_builtin_object(node: nodes.NodeNG) -> bool:
    """Returns True if the given node is an object from the __builtin__ module."""
    return (
        isinstance(node, nodes.Name)
        and node.name in builtins
        and node.root().name == 'builtins'
    )

def is_builtin(name: str) -> bool:
    """Return true if <name> could be considered as a builtin defined by python."""
    pass

def is_defined_before(var_node: nodes.Name) -> bool:
    """Check if the given variable node is defined before.

    Verify that the variable node is defined by a parent node
    (e.g. if or with) earlier than `var_node`, or is defined by a
    (list, set, dict, or generator comprehension, lambda)
    or in a previous sibling node on the same line
    (statement_defining ; statement_using).
    """
    pass

def is_default_argument(node: nodes.NodeNG, scope: nodes.NodeNG | None=None) -> bool:
    """Return true if the given Name node is used in function or lambda
    default argument's value.
    """
    pass

def is_func_decorator(node: nodes.NodeNG) -> bool:
    """Return true if the name is used in function decorator."""
    pass

def is_ancestor_name(frame: nodes.ClassDef, node: nodes.NodeNG) -> bool:
    """Return whether `frame` is an astroid.Class node with `node` in the
    subtree of its bases attribute.
    """
    pass

def is_being_called(node: nodes.NodeNG) -> bool:
    """Return True if node is the function being called in a Call node."""
    pass

def assign_parent(node: nodes.NodeNG) -> nodes.NodeNG:
    """Return the higher parent which is not an AssignName, Tuple or List node."""
    pass

def overrides_a_method(class_node: nodes.ClassDef, name: str) -> bool:
    """Return True if <name> is a method overridden from an ancestor
    which is not the base object class.
    """
    pass

def only_required_for_messages(*messages: str) -> Callable[[AstCallbackMethod[_CheckerT, _NodeT]], AstCallbackMethod[_CheckerT, _NodeT]]:
    """Decorator to store messages that are handled by a checker method as an
    attribute of the function object.

    This information is used by ``ASTWalker`` to decide whether to call the decorated
    method or not. If none of the messages is enabled, the method will be skipped.
    Therefore, the list of messages must be well maintained at all times!
    This decorator only has an effect on ``visit_*`` and ``leave_*`` methods
    of a class inheriting from ``BaseChecker``.
    """
    pass

class IncompleteFormatString(Exception):
    """A format string ended in the middle of a format specifier."""

class UnsupportedFormatCharacter(Exception):
    """A format character in a format string is not one of the supported
    format characters.
    """

    def __init__(self, index: int) -> None:
        super().__init__(index)
        self.index = index

def parse_format_string(format_string: str) -> tuple[set[str], int, dict[str, str], list[str]]:
    """Parses a format string, returning a tuple (keys, num_args).

    Where 'keys' is the set of mapping keys in the format string, and 'num_args' is the number
    of arguments required by the format string. Raises IncompleteFormatString or
    UnsupportedFormatCharacter if a parse error occurs.
    """
    pass

def collect_string_fields(format_string: str) -> Iterable[str | None]:
    """Given a format string, return an iterator
    of all the valid format fields.

    It handles nested fields as well.
    """
    pass

def parse_format_method_string(format_string: str) -> tuple[list[tuple[str, list[tuple[bool, str]]]], int, int]:
    """Parses a PEP 3101 format string, returning a tuple of
    (keyword_arguments, implicit_pos_args_cnt, explicit_pos_args).

    keyword_arguments is the set of mapping keys in the format string, implicit_pos_args_cnt
    is the number of arguments required by the format string and
    explicit_pos_args is the number of arguments passed with the position.
    """
    pass

def is_attr_protected(attrname: str) -> bool:
    """Return True if attribute name is protected (start with _ and some other
    details), False otherwise.
    """
    pass

def node_frame_class(node: nodes.NodeNG) -> nodes.ClassDef | None:
    """Return the class that is wrapping the given node.

    The function returns a class for a method node (or a staticmethod or a
    classmethod), otherwise it returns `None`.
    """
    pass

def get_outer_class(class_node: astroid.ClassDef) -> astroid.ClassDef | None:
    """Return the class that is the outer class of given (nested) class_node."""
    pass

def is_attr_private(attrname: str) -> Match[str] | None:
    """Check that attribute name is private (at least two leading underscores,
    at most one trailing underscore).
    """
    pass

def get_argument_from_call(call_node: nodes.Call, position: int | None=None, keyword: str | None=None) -> nodes.Name:
    """Returns the specified argument from a function call.

    :param nodes.Call call_node: Node representing a function call to check.
    :param int position: position of the argument.
    :param str keyword: the keyword of the argument.

    :returns: The node representing the argument, None if the argument is not found.
    :rtype: nodes.Name
    :raises ValueError: if both position and keyword are None.
    :raises NoSuchArgumentError: if no argument at the provided position or with
    the provided keyword.
    """
    pass

def infer_kwarg_from_call(call_node: nodes.Call, keyword: str) -> nodes.Name | None:
    """Returns the specified argument from a function's kwargs.

    :param nodes.Call call_node: Node representing a function call to check.
    :param str keyword: Name of the argument to be extracted.

    :returns: The node representing the argument, None if the argument is not found.
    :rtype: nodes.Name
    """
    pass

def inherit_from_std_ex(node: nodes.NodeNG | astroid.Instance) -> bool:
    """Return whether the given class node is subclass of
    exceptions.Exception.
    """
    pass

def error_of_type(handler: nodes.ExceptHandler, error_type: str | type[Exception] | tuple[str | type[Exception], ...]) -> bool:
    """Check if the given exception handler catches
    the given error_type.

    The *handler* parameter is a node, representing an ExceptHandler node.
    The *error_type* can be an exception, such as AttributeError,
    the name of an exception, or it can be a tuple of errors.
    The function will return True if the handler catches any of the
    given errors.
    """
    pass

def decorated_with_property(node: nodes.FunctionDef) -> bool:
    """Detect if the given function node is decorated with a property."""
    pass

def is_property_setter(node: nodes.NodeNG) -> bool:
    """Check if the given node is a property setter."""
    pass

def is_property_deleter(node: nodes.NodeNG) -> bool:
    """Check if the given node is a property deleter."""
    pass

def is_property_setter_or_deleter(node: nodes.NodeNG) -> bool:
    """Check if the given node is either a property setter or a deleter."""
    pass

def decorated_with(func: nodes.ClassDef | nodes.FunctionDef | astroid.BoundMethod | astroid.UnboundMethod, qnames: Iterable[str]) -> bool:
    """Determine if the `func` node has a decorator with the qualified name `qname`."""
    pass

def uninferable_final_decorators(node: nodes.Decorators) -> list[nodes.Attribute | nodes.Name | None]:
    """Return a list of uninferable `typing.final` decorators in `node`.

    This function is used to determine if the `typing.final` decorator is used
    with an unsupported Python version; the decorator cannot be inferred when
    using a Python version lower than 3.8.
    """
    pass

@lru_cache(maxsize=1024)
def unimplemented_abstract_methods(node: nodes.ClassDef, is_abstract_cb: nodes.FunctionDef | None=None) -> dict[str, nodes.FunctionDef]:
    """Get the unimplemented abstract methods for the given *node*.

    A method can be considered abstract if the callback *is_abstract_cb*
    returns a ``True`` value. The check defaults to verifying that
    a method is decorated with abstract methods.
    It will return a dictionary of abstract method
    names and their inferred objects.
    """
    pass

def find_try_except_wrapper_node(node: nodes.NodeNG) -> nodes.ExceptHandler | nodes.Try | None:
    """Return the ExceptHandler or the Try node in which the node is."""
    pass

def find_except_wrapper_node_in_scope(node: nodes.NodeNG) -> nodes.ExceptHandler | None:
    """Return the ExceptHandler in which the node is, without going out of scope."""
    pass

def is_from_fallback_block(node: nodes.NodeNG) -> bool:
    """Check if the given node is from a fallback import block."""
    pass

def get_exception_handlers(node: nodes.NodeNG, exception: type[Exception] | str=Exception) -> list[nodes.ExceptHandler] | None:
    """Return the collections of handlers handling the exception in arguments.

    Args:
        node (nodes.NodeNG): A node that is potentially wrapped in a try except.
        exception (builtin.Exception or str): exception or name of the exception.

    Returns:
        list: the collection of handlers that are handling the exception or None.
    """
    pass

def get_contextlib_with_statements(node: nodes.NodeNG) -> Iterator[nodes.With]:
    """Get all contextlib.with statements in the ancestors of the given node."""
    pass

def _suppresses_exception(call: nodes.Call, exception: type[Exception] | str=Exception) -> bool:
    """Check if the given node suppresses the given exception."""
    pass

def get_contextlib_suppressors(node: nodes.NodeNG, exception: type[Exception] | str=Exception) -> Iterator[nodes.With]:
    """Return the contextlib suppressors handling the exception.

    Args:
        node (nodes.NodeNG): A node that is potentially wrapped in a contextlib.suppress.
        exception (builtin.Exception): exception or name of the exception.

    Yields:
        nodes.With: A with node that is suppressing the exception.
    """
    pass

def is_node_inside_try_except(node: nodes.Raise) -> bool:
    """Check if the node is directly under a Try/Except statement
    (but not under an ExceptHandler!).

    Args:
        node (nodes.Raise): the node raising the exception.

    Returns:
        bool: True if the node is inside a try/except statement, False otherwise.
    """
    pass

def node_ignores_exception(node: nodes.NodeNG, exception: type[Exception] | str=Exception) -> bool:
    """Check if the node is in a Try which handles the given exception.

    If the exception is not given, the function is going to look for bare
    excepts.
    """
    pass

@lru_cache(maxsize=1024)
def class_is_abstract(node: nodes.ClassDef) -> bool:
    """Return true if the given class node should be considered as an abstract
    class.
    """
    pass

@lru_cache(maxsize=1024)
def safe_infer(node: nodes.NodeNG, context: InferenceContext | None=None, *, compare_constants: bool=False, compare_constructors: bool=False) -> InferenceResult | None:
    """Return the inferred value for the given node.

    Return None if inference failed or if there is some ambiguity (more than
    one node has been inferred of different types).

    If compare_constants is True and if multiple constants are inferred,
    unequal inferred values are also considered ambiguous and return None.

    If compare_constructors is True and if multiple classes are inferred,
    constructors with different signatures are held ambiguous and return None.
    """
    pass

def has_known_bases(klass: nodes.ClassDef, context: InferenceContext | None=None) -> bool:
    """Return true if all base classes of a class could be inferred."""
    pass

def node_type(node: nodes.NodeNG) -> SuccessfulInferenceResult | None:
    """Return the inferred type for `node`.

    If there is more than one possible type, or if inferred type is Uninferable or None,
    return None
    """
    pass

def is_registered_in_singledispatch_function(node: nodes.FunctionDef) -> bool:
    """Check if the given function node is a singledispatch function."""
    pass

def is_registered_in_singledispatchmethod_function(node: nodes.FunctionDef) -> bool:
    """Check if the given function node is a singledispatchmethod function."""
    pass

def get_node_last_lineno(node: nodes.NodeNG) -> int:
    """Get the last lineno of the given node.

    For a simple statement this will just be node.lineno,
    but for a node that has child statements (e.g. a method) this will be the lineno of the last
    child statement recursively.
    """
    pass

def is_postponed_evaluation_enabled(node: nodes.NodeNG) -> bool:
    """Check if the postponed evaluation of annotations is enabled."""
    pass

def is_node_in_type_annotation_context(node: nodes.NodeNG) -> bool:
    """Check if node is in type annotation context.

    Check for 'AnnAssign', function 'Arguments',
    or part of function return type annotation.
    """
    pass

def is_subclass_of(child: nodes.ClassDef, parent: nodes.ClassDef) -> bool:
    """Check if first node is a subclass of second node.

    :param child: Node to check for subclass.
    :param parent: Node to check for superclass.
    :returns: True if child is derived from parent. False otherwise.
    """
    pass

@lru_cache(maxsize=1024)
def is_overload_stub(node: nodes.NodeNG) -> bool:
    """Check if a node is a function stub decorated with typing.overload.

    :param node: Node to check.
    :returns: True if node is an overload function stub. False otherwise.
    """
    pass

def is_protocol_class(cls: nodes.NodeNG) -> bool:
    """Check if the given node represents a protocol class.

    :param cls: The node to check
    :returns: True if the node is or inherits from typing.Protocol directly, false otherwise.
    """
    pass

def is_call_of_name(node: nodes.NodeNG, name: str) -> bool:
    """Checks if node is a function call with the given name."""
    pass

def is_test_condition(node: nodes.NodeNG, parent: nodes.NodeNG | None=None) -> bool:
    """Returns true if the given node is being tested for truthiness."""
    pass

def is_classdef_type(node: nodes.ClassDef) -> bool:
    """Test if ClassDef node is Type."""
    pass

def is_attribute_typed_annotation(node: nodes.ClassDef | astroid.Instance, attr_name: str) -> bool:
    """Test if attribute is typed annotation in current node
    or any base nodes.
    """
    pass

def is_assign_name_annotated_with(node: nodes.AssignName, typing_name: str) -> bool:
    """Test if AssignName node has `typing_name` annotation.

    Especially useful to check for `typing._SpecialForm` instances
    like: `Union`, `Optional`, `Literal`, `ClassVar`, `Final`.
    """
    pass

def get_iterating_dictionary_name(node: nodes.For | nodes.Comprehension) -> str | None:
    """Get the name of the dictionary which keys are being iterated over on
    a ``nodes.For`` or ``nodes.Comprehension`` node.

    If the iterating object is not either the keys method of a dictionary
    or a dictionary itself, this returns None.
    """
    pass

def get_subscript_const_value(node: nodes.Subscript) -> nodes.Const:
    """Returns the value 'subscript.slice' of a Subscript node.

    :param node: Subscript Node to extract value from
    :returns: Const Node containing subscript value
    :raises InferredTypeError: if the subscript node cannot be inferred as a Const
    """
    pass

def get_import_name(importnode: ImportNode, modname: str | None) -> str | None:
    """Get a prepared module name from the given import node.

    In the case of relative imports, this will return the
    absolute qualified module name, which might be useful
    for debugging. Otherwise, the initial module name
    is returned unchanged.

    :param importnode: node representing import statement.
    :param modname: module name from import statement.
    :returns: absolute qualified module name of the module
        used in import.
    """
    pass

def is_sys_guard(node: nodes.If) -> bool:
    """Return True if IF stmt is a sys.version_info guard.

    >>> import sys
    >>> if sys.version_info > (3, 8):
    >>>     from typing import Literal
    >>> else:
    >>>     from typing_extensions import Literal
    """
    pass

def is_reassigned_after_current(node: nodes.NodeNG, varname: str) -> bool:
    """Check if the given variable name is reassigned in the same scope after the
    current node.
    """
    pass

def is_deleted_after_current(node: nodes.NodeNG, varname: str) -> bool:
    """Check if the given variable name is deleted in the same scope after the current
    node.
    """
    pass

def is_function_body_ellipsis(node: nodes.FunctionDef) -> bool:
    """Checks whether a function body only consists of a single Ellipsis."""
    pass

def returns_bool(node: nodes.NodeNG) -> bool:
    """Returns true if a node is a nodes.Return that returns a constant boolean."""
    pass

def assigned_bool(node: nodes.NodeNG) -> bool:
    """Returns true if a node is a nodes.Assign that returns a constant boolean."""
    pass

def get_node_first_ancestor_of_type(node: nodes.NodeNG, ancestor_type: type[_NodeT] | tuple[type[_NodeT], ...]) -> _NodeT | None:
    """Return the first parent node that is any of the provided types (or None)."""
    pass

def get_node_first_ancestor_of_type_and_its_child(node: nodes.NodeNG, ancestor_type: type[_NodeT] | tuple[type[_NodeT], ...]) -> tuple[None, None] | tuple[_NodeT, nodes.NodeNG]:
    """Modified version of get_node_first_ancestor_of_type to also return the
    descendant visited directly before reaching the sought ancestor.

    Useful for extracting whether a statement is guarded by a try, except, or finally
    when searching for a Try ancestor.
    """
    pass

def in_type_checking_block(node: nodes.NodeNG) -> bool:
    """Check if a node is guarded by a TYPE_CHECKING guard."""
    pass

def is_typing_member(node: nodes.NodeNG, names_to_check: tuple[str, ...]) -> bool:
    """Check if `node` is a member of the `typing` module and has one of the names from
    `names_to_check`.
    """
    pass

@lru_cache
def in_for_else_branch(parent: nodes.NodeNG, stmt: Statement) -> bool:
    """Returns True if stmt is inside the else branch for a parent For stmt."""
    pass

def find_assigned_names_recursive(target: nodes.AssignName | nodes.BaseContainer) -> Iterator[str]:
    """Yield the names of assignment targets, accounting for nested ones."""
    pass

def has_starred_node_recursive(node: nodes.For | nodes.Comprehension | nodes.Set) -> Iterator[bool]:
    """Yield ``True`` if a Starred node is found recursively."""
    pass

def is_hashable(node: nodes.NodeNG) -> bool:
    """Return whether any inferred value of `node` is hashable.

    When finding ambiguity, return True.
    """
    pass

def _is_target_name_in_binop_side(target: nodes.AssignName | nodes.AssignAttr, side: nodes.NodeNG | None) -> bool:
    """Determine whether the target name-like node is referenced in the side node."""
    pass

def is_augmented_assign(node: nodes.Assign) -> tuple[bool, str]:
    """Determine if the node is assigning itself (with modifications) to itself.

    For example: x = 1 + x
    """
    pass

def _qualified_name_parts(qualified_module_name: str) -> list[str]:
    """Split the names of the given module into subparts.

    For example,
        _qualified_name_parts('pylint.checkers.ImportsChecker')
    returns
        ['pylint', 'pylint.checkers', 'pylint.checkers.ImportsChecker']
    """
    pass

def is_terminating_func(node: nodes.Call) -> bool:
    """Detect call to exit(), quit(), os._exit(), sys.exit(), or
    functions annotated with `typing.NoReturn` or `typing.Never`.
    """
    pass

def get_inverse_comparator(op: str) -> str:
    """Returns the inverse comparator given a comparator.

    E.g. when given "==", returns "!="

    :param str op: the comparator to look up.

    :returns: The inverse of the comparator in string format
    :raises KeyError: if input is not recognized as a comparator
    """
    pass

@lru_cache(maxsize=1000)
def overridden_method(klass: nodes.LocalsDictNodeNG, name: str | None) -> nodes.FunctionDef | None:
    """Get overridden method if any."""
    pass

def clear_lru_caches() -> None:
    """Clear caches holding references to AST nodes."""
    pass

def is_enum_member(node: nodes.AssignName) -> bool:
    """Return `True` if `node` is an Enum member (is an item of the
    `__members__` container).
    """
    pass
