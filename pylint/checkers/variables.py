"""Variables checkers for Python code."""
from __future__ import annotations
import collections
import copy
import itertools
import math
import os
import re
from collections import defaultdict
from collections.abc import Generator, Iterable, Iterator
from enum import Enum
from functools import cached_property
from typing import TYPE_CHECKING, Any, NamedTuple
import astroid
import astroid.exceptions
from astroid import bases, extract_node, nodes, util
from astroid.nodes import _base_nodes
from astroid.typing import InferenceResult
from pylint.checkers import BaseChecker, utils
from pylint.checkers.utils import in_type_checking_block, is_module_ignored, is_postponed_evaluation_enabled, is_sys_guard, overridden_method
from pylint.constants import PY39_PLUS, TYPING_NEVER, TYPING_NORETURN
from pylint.interfaces import CONTROL_FLOW, HIGH, INFERENCE, INFERENCE_FAILURE
from pylint.typing import MessageDefinitionTuple
if TYPE_CHECKING:
    from pylint.lint import PyLinter
SPECIAL_OBJ = re.compile('^_{2}[a-z]+_{2}$')
FUTURE = '__future__'
IGNORED_ARGUMENT_NAMES = re.compile('_.*|^ignored_|^unused_')
METACLASS_NAME_TRANSFORMS = {'_py_abc': 'abc'}
BUILTIN_RANGE = 'builtins.range'
TYPING_MODULE = 'typing'
TYPING_NAMES = frozenset({'Any', 'Callable', 'ClassVar', 'Generic', 'Optional', 'Tuple', 'Type', 'TypeVar', 'Union', 'AbstractSet', 'ByteString', 'Container', 'ContextManager', 'Hashable', 'ItemsView', 'Iterable', 'Iterator', 'KeysView', 'Mapping', 'MappingView', 'MutableMapping', 'MutableSequence', 'MutableSet', 'Sequence', 'Sized', 'ValuesView', 'Awaitable', 'AsyncIterator', 'AsyncIterable', 'Coroutine', 'Collection', 'AsyncGenerator', 'AsyncContextManager', 'Reversible', 'SupportsAbs', 'SupportsBytes', 'SupportsComplex', 'SupportsFloat', 'SupportsInt', 'SupportsRound', 'Counter', 'Deque', 'Dict', 'DefaultDict', 'List', 'Set', 'FrozenSet', 'NamedTuple', 'Generator', 'AnyStr', 'Text', 'Pattern', 'BinaryIO'})
DICT_TYPES = (astroid.objects.DictValues, astroid.objects.DictKeys, astroid.objects.DictItems, astroid.nodes.node_classes.Dict)
NODES_WITH_VALUE_ATTR = (nodes.Assign, nodes.AnnAssign, nodes.AugAssign, nodes.Expr, nodes.Return, nodes.Match, nodes.TypeAlias)

class VariableVisitConsumerAction(Enum):
    """Reported by _check_consumer() and its sub-methods to determine the
    subsequent action to take in _undefined_and_used_before_checker().

    Continue -> continue loop to next consumer
    Return -> return and thereby break the loop
    """
    CONTINUE = 0
    RETURN = 1

def _is_from_future_import(stmt: nodes.ImportFrom, name: str) -> bool | None:
    """Check if the name is a future import from another module."""
    if stmt.modname == FUTURE:
        for import_name, import_as_name in stmt.names:
            if import_name == name:
                return True
    return None

def _get_unpacking_extra_info(node: nodes.Assign, inferred: InferenceResult) -> str:
    """Return extra information to add to the message for unpacking-non-sequence
    and unbalanced-tuple/dict-unpacking errors.
    """
    more = ""
    if isinstance(inferred, astroid.Instance):
        actual_type = inferred.name
        if node.value.parent_of(inferred.ast_node):
            more = f" (inferred type is '{actual_type}')"
    elif isinstance(inferred, astroid.ClassDef):
        more = f" (type is '{inferred.name}')"
    return more

def _detect_global_scope(node: nodes.Name, frame: nodes.LocalsDictNodeNG, defframe: nodes.LocalsDictNodeNG) -> bool:
    """Detect that the given frames share a global scope.

    Two frames share a global scope when neither
    of them are hidden under a function scope, as well
    as any parent scope of them, until the root scope.
    In this case, depending from something defined later on
    will only work if guarded by a nested function definition.

    Example:
        class A:
            # B has the same global scope as `C`, leading to a NameError.
            # Return True to indicate a shared scope.
            class B(C): ...
        class C: ...

    Whereas this does not lead to a NameError:
        class A:
            def guard():
                # Return False to indicate no scope sharing.
                class B(C): ...
        class C: ...
    """
    def_scope = defframe.scope()
    node_scope = frame.scope()
    if def_scope.parent == node_scope.parent:
        # If the scopes share the same parent, they are not in global scope
        return False
    
    while frame and not isinstance(frame, nodes.Module):
        if isinstance(frame, nodes.FunctionDef):
            return False
        frame = frame.parent.frame()
    while defframe and not isinstance(defframe, nodes.Module):
        if isinstance(defframe, nodes.FunctionDef):
            return False
        defframe = defframe.parent.frame()
    return True

def _fix_dot_imports(not_consumed: dict[str, list[nodes.NodeNG]]) -> list[tuple[str, _base_nodes.ImportNode]]:
    """Try to fix imports with multiple dots, by returning a dictionary
    with the import names expanded.

    The function unflattens root imports,
    like 'xml' (when we have both 'xml.etree' and 'xml.sax'), to 'xml.etree'
    and 'xml.sax' respectively.
    """
    pass

def _find_frame_imports(name: str, frame: nodes.LocalsDictNodeNG) -> bool:
    """Detect imports in the frame, with the required *name*.

    Such imports can be considered assignments if they are not globals.
    Returns True if an import for the given name was found.
    """
    pass

def _assigned_locally(name_node: nodes.Name) -> bool:
    """Checks if name_node has corresponding assign statement in same scope."""
    pass
MSGS: dict[str, MessageDefinitionTuple] = {'E0601': ('Using variable %r before assignment', 'used-before-assignment', 'Emitted when a local variable is accessed before its assignment took place. Assignments in try blocks are assumed not to have occurred when evaluating associated except/finally blocks. Assignments in except blocks are assumed not to have occurred when evaluating statements outside the block, except when the associated try block contains a return statement.'), 'E0602': ('Undefined variable %r', 'undefined-variable', 'Used when an undefined variable is accessed.'), 'E0603': ('Undefined variable name %r in __all__', 'undefined-all-variable', 'Used when an undefined variable name is referenced in __all__.'), 'E0604': ('Invalid object %r in __all__, must contain only strings', 'invalid-all-object', 'Used when an invalid (non-string) object occurs in __all__.'), 'E0605': ('Invalid format for __all__, must be tuple or list', 'invalid-all-format', 'Used when __all__ has an invalid format.'), 'E0606': ('Possibly using variable %r before assignment', 'possibly-used-before-assignment', 'Emitted when a local variable is accessed before its assignment took place in both branches of an if/else switch.'), 'E0611': ('No name %r in module %r', 'no-name-in-module', 'Used when a name cannot be found in a module.'), 'W0601': ('Global variable %r undefined at the module level', 'global-variable-undefined', 'Used when a variable is defined through the "global" statement but the variable is not defined in the module scope.'), 'W0602': ('Using global for %r but no assignment is done', 'global-variable-not-assigned', "When a variable defined in the global scope is modified in an inner scope, the 'global' keyword is required in the inner scope only if there is an assignment operation done in the inner scope."), 'W0603': ('Using the global statement', 'global-statement', 'Used when you use the "global" statement to update a global variable. Pylint discourages its usage. That doesn\'t mean you cannot use it!'), 'W0604': ('Using the global statement at the module level', 'global-at-module-level', 'Used when you use the "global" statement at the module level since it has no effect.'), 'W0611': ('Unused %s', 'unused-import', 'Used when an imported module or variable is not used.'), 'W0612': ('Unused variable %r', 'unused-variable', 'Used when a variable is defined but not used.'), 'W0613': ('Unused argument %r', 'unused-argument', 'Used when a function or method argument is not used.'), 'W0614': ('Unused import(s) %s from wildcard import of %s', 'unused-wildcard-import', "Used when an imported module or variable is not used from a `'from X import *'` style import."), 'W0621': ('Redefining name %r from outer scope (line %s)', 'redefined-outer-name', "Used when a variable's name hides a name defined in an outer scope or except handler."), 'W0622': ('Redefining built-in %r', 'redefined-builtin', 'Used when a variable or function override a built-in.'), 'W0631': ('Using possibly undefined loop variable %r', 'undefined-loop-variable', 'Used when a loop variable (i.e. defined by a for loop or a list comprehension or a generator expression) is used outside the loop.'), 'W0632': ('Possible unbalanced tuple unpacking with sequence %s: left side has %d label%s, right side has %d value%s', 'unbalanced-tuple-unpacking', 'Used when there is an unbalanced tuple unpacking in assignment', {'old_names': [('E0632', 'old-unbalanced-tuple-unpacking')]}), 'E0633': ('Attempting to unpack a non-sequence%s', 'unpacking-non-sequence', 'Used when something which is not a sequence is used in an unpack assignment', {'old_names': [('W0633', 'old-unpacking-non-sequence')]}), 'W0640': ('Cell variable %s defined in loop', 'cell-var-from-loop', 'A variable used in a closure is defined in a loop. This will result in all closures using the same value for the closed-over variable.'), 'W0641': ('Possibly unused variable %r', 'possibly-unused-variable', 'Used when a variable is defined but might not be used. The possibility comes from the fact that locals() might be used, which could consume or not the said variable'), 'W0642': ('Invalid assignment to %s in method', 'self-cls-assignment', 'Invalid assignment to self or cls in instance or class method respectively.'), 'E0643': ('Invalid index for iterable length', 'potential-index-error', 'Emitted when an index used on an iterable goes beyond the length of that iterable.'), 'W0644': ('Possible unbalanced dict unpacking with %s: left side has %d label%s, right side has %d value%s', 'unbalanced-dict-unpacking', 'Used when there is an unbalanced dict unpacking in assignment or for loop')}

class ScopeConsumer(NamedTuple):
    """Store nodes and their consumption states."""
    to_consume: dict[str, list[nodes.NodeNG]]
    consumed: dict[str, list[nodes.NodeNG]]
    consumed_uncertain: defaultdict[str, list[nodes.NodeNG]]
    scope_type: str

class NamesConsumer:
    """A simple class to handle consumed, to consume and scope type info of node locals."""

    def __init__(self, node: nodes.NodeNG, scope_type: str) -> None:
        self._atomic = ScopeConsumer(copy.copy(node.locals), {}, collections.defaultdict(list), scope_type)
        self.node = node
        self.names_under_always_false_test: set[str] = set()
        self.names_defined_under_one_branch_only: set[str] = set()

    def __repr__(self) -> str:
        _to_consumes = [f'{k}->{v}' for k, v in self._atomic.to_consume.items()]
        _consumed = [f'{k}->{v}' for k, v in self._atomic.consumed.items()]
        _consumed_uncertain = [f'{k}->{v}' for k, v in self._atomic.consumed_uncertain.items()]
        to_consumes = ', '.join(_to_consumes)
        consumed = ', '.join(_consumed)
        consumed_uncertain = ', '.join(_consumed_uncertain)
        return f'\nto_consume : {to_consumes}\nconsumed : {consumed}\nconsumed_uncertain: {consumed_uncertain}\nscope_type : {self._atomic.scope_type}\n'

    def __iter__(self) -> Iterator[Any]:
        return iter(self._atomic)

    @property
    def consumed_uncertain(self) -> defaultdict[str, list[nodes.NodeNG]]:
        """Retrieves nodes filtered out by get_next_to_consume() that may not
        have executed.

        These include nodes such as statements in except blocks, or statements
        in try blocks (when evaluating their corresponding except and finally
        blocks). Checkers that want to treat the statements as executed
        (e.g. for unused-variable) may need to add them back.
        """
        pass

    def mark_as_consumed(self, name: str, consumed_nodes: list[nodes.NodeNG]) -> None:
        """Mark the given nodes as consumed for the name.

        If all of the nodes for the name were consumed, delete the name from
        the to_consume dictionary
        """
        pass

    def get_next_to_consume(self, node: nodes.Name) -> list[nodes.NodeNG] | None:
        """Return a list of the nodes that define `node` from this scope.

        If it is uncertain whether a node will be consumed, such as for statements in
        except blocks, add it to self.consumed_uncertain instead of returning it.
        Return None to indicate a special case that needs to be handled by the caller.
        """
        pass

    def _inferred_to_define_name_raise_or_return(self, name: str, node: nodes.NodeNG) -> bool:
        """Return True if there is a path under this `if_node`
        that is inferred to define `name`, raise, or return.
        """
        pass

    def _uncertain_nodes_if_tests(self, found_nodes: list[nodes.NodeNG], node: nodes.NodeNG) -> list[nodes.NodeNG]:
        """Identify nodes of uncertain execution because they are defined under if
        tests.

        Don't identify a node if there is a path that is inferred to
        define the name, raise, or return (e.g. any executed if/elif/else branch).
        """
        pass

    @staticmethod
    def _node_guarded_by_same_test(node: nodes.NodeNG, other_if: nodes.If) -> bool:
        """Identify if `node` is guarded by an equivalent test as `other_if`.

        Two tests are equivalent if their string representations are identical
        or if their inferred values consist only of constants and those constants
        are identical, and the if test guarding `node` is not a Name.
        """
        pass

    @staticmethod
    def _uncertain_nodes_in_except_blocks(found_nodes: list[nodes.NodeNG], node: nodes.NodeNG, node_statement: _base_nodes.Statement) -> list[nodes.NodeNG]:
        """Return any nodes in ``found_nodes`` that should be treated as uncertain
        because they are in an except block.
        """
        pass

    @staticmethod
    def _defines_name_raises_or_returns_recursive(name: str, node: nodes.NodeNG) -> bool:
        """Return True if some child of `node` defines the name `name`,
        raises, or returns.
        """
        pass

    @staticmethod
    def _check_loop_finishes_via_except(node: nodes.NodeNG, other_node_try_except: nodes.Try) -> bool:
        """Check for a specific control flow scenario.

        Described in https://github.com/pylint-dev/pylint/issues/5683.

        A scenario where the only non-break exit from a loop consists of the very
        except handler we are examining, such that code in the `else` branch of
        the loop can depend on it being assigned.

        Example:
        for _ in range(3):
            try:
                do_something()
            except:
                name = 1  <-- only non-break exit from loop
            else:
                break
        else:
            print(name)
        """
        pass

    @staticmethod
    def _recursive_search_for_continue_before_break(stmt: _base_nodes.Statement, break_stmt: nodes.Break) -> bool:
        """Return True if any Continue node can be found in descendants of `stmt`
        before encountering `break_stmt`, ignoring any nested loops.
        """
        pass

    @staticmethod
    def _uncertain_nodes_in_try_blocks_when_evaluating_except_blocks(found_nodes: list[nodes.NodeNG], node_statement: _base_nodes.Statement) -> list[nodes.NodeNG]:
        """Return any nodes in ``found_nodes`` that should be treated as uncertain.

        Nodes are uncertain when they are in a try block and the ``node_statement``
        being evaluated is in one of its except handlers.
        """
        pass

class VariablesChecker(BaseChecker):
    """BaseChecker for variables.

    Checks for
    * unused variables / imports
    * undefined variables
    * redefinition of variable from builtins or from an outer scope or except handler
    * use of variable before assignment
    * __all__ consistency
    * self/cls assignment
    """
    name = 'variables'
    msgs = MSGS
    options = (('init-import', {'default': False, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Tells whether we should check for unused import in __init__ files.'}), ('dummy-variables-rgx', {'default': '_+$|(_[a-zA-Z0-9_]*[a-zA-Z0-9]+?$)|dummy|^ignored_|^unused_', 'type': 'regexp', 'metavar': '<regexp>', 'help': 'A regular expression matching the name of dummy variables (i.e. expected to not be used).'}), ('additional-builtins', {'default': (), 'type': 'csv', 'metavar': '<comma separated list>', 'help': 'List of additional names supposed to be defined in builtins. Remember that you should avoid defining new builtins when possible.'}), ('callbacks', {'default': ('cb_', '_cb'), 'type': 'csv', 'metavar': '<callbacks>', 'help': 'List of strings which can identify a callback function by name. A callback name must start or end with one of those strings.'}), ('redefining-builtins-modules', {'default': ('six.moves', 'past.builtins', 'future.builtins', 'builtins', 'io'), 'type': 'csv', 'metavar': '<comma separated list>', 'help': 'List of qualified module names which can have objects that can redefine builtins.'}), ('ignored-argument-names', {'default': IGNORED_ARGUMENT_NAMES, 'type': 'regexp', 'metavar': '<regexp>', 'help': 'Argument names that match this expression will be ignored.'}), ('allow-global-unused-variables', {'default': True, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Tells whether unused global variables should be treated as a violation.'}), ('allowed-redefined-builtins', {'default': (), 'type': 'csv', 'metavar': '<comma separated list>', 'help': 'List of names allowed to shadow builtins'}))

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._to_consume: list[NamesConsumer] = []
        self._type_annotation_names: list[str] = []
        self._except_handler_names_queue: list[tuple[nodes.ExceptHandler, nodes.AssignName]] = []
        'This is a queue, last in first out.'
        self._evaluated_type_checking_scopes: dict[str, list[nodes.LocalsDictNodeNG]] = {}
        self._postponed_evaluation_enabled = False

    def visit_module(self, node: nodes.Module) -> None:
        """Visit module : update consumption analysis variable
        checks globals doesn't overrides builtins.
        """
        pass

    @utils.only_required_for_messages('unused-import', 'unused-wildcard-import', 'redefined-builtin', 'undefined-all-variable', 'invalid-all-object', 'invalid-all-format', 'unused-variable', 'undefined-variable')
    def leave_module(self, node: nodes.Module) -> None:
        """Leave module: check globals."""
        pass

    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """Visit class: update consumption analysis variable."""
        pass

    def leave_classdef(self, node: nodes.ClassDef) -> None:
        """Leave class: update consumption analysis variable."""
        pass

    def visit_lambda(self, node: nodes.Lambda) -> None:
        """Visit lambda: update consumption analysis variable."""
        pass

    def leave_lambda(self, _: nodes.Lambda) -> None:
        """Leave lambda: update consumption analysis variable."""
        pass

    def visit_generatorexp(self, node: nodes.GeneratorExp) -> None:
        """Visit genexpr: update consumption analysis variable."""
        pass

    def leave_generatorexp(self, _: nodes.GeneratorExp) -> None:
        """Leave genexpr: update consumption analysis variable."""
        pass

    def visit_dictcomp(self, node: nodes.DictComp) -> None:
        """Visit dictcomp: update consumption analysis variable."""
        pass

    def leave_dictcomp(self, _: nodes.DictComp) -> None:
        """Leave dictcomp: update consumption analysis variable."""
        pass

    def visit_setcomp(self, node: nodes.SetComp) -> None:
        """Visit setcomp: update consumption analysis variable."""
        pass

    def leave_setcomp(self, _: nodes.SetComp) -> None:
        """Leave setcomp: update consumption analysis variable."""
        pass

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Visit function: update consumption analysis variable and check locals."""
        pass

    def leave_functiondef(self, node: nodes.FunctionDef) -> None:
        """Leave function: check function's locals are consumed."""
        pass
    visit_asyncfunctiondef = visit_functiondef
    leave_asyncfunctiondef = leave_functiondef

    @utils.only_required_for_messages('global-variable-undefined', 'global-variable-not-assigned', 'global-statement', 'global-at-module-level', 'redefined-builtin')
    def visit_global(self, node: nodes.Global) -> None:
        """Check names imported exists in the global scope."""
        pass

    def visit_name(self, node: nodes.Name | nodes.AssignName | nodes.DelName) -> None:
        """Don't add the 'utils.only_required_for_messages' decorator here!

        It's important that all 'Name' nodes are visited, otherwise the
        'NamesConsumers' won't be correct.
        """
        pass

    def _should_node_be_skipped(self, node: nodes.Name, consumer: NamesConsumer, is_start_index: bool) -> bool:
        """Tests a consumer and node for various conditions in which the node shouldn't
        be checked for the undefined-variable and used-before-assignment checks.
        """
        pass

    def _check_consumer(self, node: nodes.Name, stmt: nodes.NodeNG, frame: nodes.LocalsDictNodeNG, current_consumer: NamesConsumer, base_scope_type: str) -> tuple[VariableVisitConsumerAction, list[nodes.NodeNG] | None]:
        """Checks a consumer for conditions that should trigger messages."""
        pass

    def _report_unfound_name_definition(self, node: nodes.NodeNG, current_consumer: NamesConsumer) -> None:
        """Reports used-before-assignment when all name definition nodes
        get filtered out by NamesConsumer.
        """
        pass

    def _filter_type_checking_import_from_consumption(self, node: nodes.NodeNG, nodes_to_consume: list[nodes.NodeNG]) -> list[nodes.NodeNG]:
        """Do not consume type-checking import node as used-before-assignment
        may invoke in different scopes.
        """
        pass

    @utils.only_required_for_messages('no-name-in-module')
    def visit_import(self, node: nodes.Import) -> None:
        """Check modules attribute accesses."""
        pass

    @utils.only_required_for_messages('no-name-in-module')
    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        """Check modules attribute accesses."""
        pass

    @utils.only_required_for_messages('unbalanced-tuple-unpacking', 'unpacking-non-sequence', 'self-cls-assignment', 'unbalanced_dict_unpacking')
    def visit_assign(self, node: nodes.Assign) -> None:
        """Check unbalanced tuple unpacking for assignments and unpacking
        non-sequences as well as in case self/cls get assigned.
        """
        pass

    def visit_listcomp(self, node: nodes.ListComp) -> None:
        """Visit listcomp: update consumption analysis variable."""
        pass

    def leave_listcomp(self, _: nodes.ListComp) -> None:
        """Leave listcomp: update consumption analysis variable."""
        pass

    @staticmethod
    def _in_lambda_or_comprehension_body(node: nodes.NodeNG, frame: nodes.NodeNG) -> bool:
        """Return True if node within a lambda/comprehension body (or similar) and thus
        should not have access to class attributes in frame.
        """
        pass

    @staticmethod
    def _maybe_used_and_assigned_at_once(defstmt: _base_nodes.Statement) -> bool:
        """Check if `defstmt` has the potential to use and assign a name in the
        same statement.
        """
        pass

    @staticmethod
    def _is_only_type_assignment(node: nodes.Name, defstmt: _base_nodes.Statement) -> bool:
        """Check if variable only gets assigned a type and never a value."""
        pass

    @staticmethod
    def _is_first_level_self_reference(node: nodes.Name, defstmt: nodes.ClassDef, found_nodes: list[nodes.NodeNG]) -> tuple[VariableVisitConsumerAction, list[nodes.NodeNG] | None]:
        """Check if a first level method's annotation or default values
        refers to its own class, and return a consumer action.
        """
        pass

    @staticmethod
    def _is_never_evaluated(defnode: nodes.NamedExpr, defnode_parent: nodes.IfExp) -> bool:
        """Check if a NamedExpr is inside a side of if ... else that never
        gets evaluated.
        """
        pass

    def _ignore_class_scope(self, node: nodes.NodeNG) -> bool:
        """Return True if the node is in a local class scope, as an assignment.

        Detect if we are in a local class scope, as an assignment.
        For example, the following is fair game.

        class A:
           b = 1
           c = lambda b=b: b * b

        class B:
           tp = 1
           def func(self, arg: tp):
               ...
        class C:
           tp = 2
           def func(self, arg=tp):
               ...
        class C:
           class Tp:
               pass
           class D(Tp):
               ...
        """
        pass

    def _check_late_binding_closure(self, node: nodes.Name) -> None:
        """Check whether node is a cell var that is assigned within a containing loop.

        Special cases where we don't care about the error:
        1. When the node's function is immediately called, e.g. (lambda: i)()
        2. When the node's function is returned from within the loop, e.g. return lambda: i
        """
        pass

    @staticmethod
    def _comprehension_between_frame_and_node(node: nodes.Name) -> bool:
        """Return True if a ComprehensionScope intervenes between `node` and its
        frame.
        """
        pass

    def _store_type_annotation_node(self, type_annotation: nodes.NodeNG) -> None:
        """Given a type annotation, store all the name nodes it refers to."""
        pass

    def _check_self_cls_assign(self, node: nodes.Assign) -> None:
        """Check that self/cls don't get assigned."""
        pass

    def _check_unpacking(self, inferred: InferenceResult, node: nodes.Assign, targets: list[nodes.NodeNG]) -> None:
        """Check for unbalanced tuple unpacking
        and unpacking non sequences.
        """
        pass

    @staticmethod
    def _nodes_to_unpack(node: nodes.NodeNG) -> list[nodes.NodeNG] | None:
        """Return the list of values of the `Assign` node."""
        pass

    def _check_module_attrs(self, node: _base_nodes.ImportNode, module: nodes.Module, module_names: list[str]) -> nodes.Module | None:
        """Check that module_names (list of string) are accessible through the
        given module, if the latest access name corresponds to a module, return it.
        """
        pass

    def _check_metaclasses(self, node: nodes.Module | nodes.FunctionDef) -> None:
        """Update consumption analysis for metaclasses."""
        pass

    def _check_potential_index_error(self, node: nodes.Subscript, inferred_slice: nodes.NodeNG | None) -> None:
        """Check for the potential-index-error message."""
        pass

    @utils.only_required_for_messages('unused-import', 'unused-variable')
    def visit_const(self, node: nodes.Const) -> None:
        """Take note of names that appear inside string literal type annotations
        unless the string is a parameter to `typing.Literal` or `typing.Annotation`.
        """
        pass
