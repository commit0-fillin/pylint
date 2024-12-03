"""Check for signs of poor design."""
from __future__ import annotations
import re
from collections import defaultdict
from collections.abc import Iterator
from typing import TYPE_CHECKING
import astroid
from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.checkers.utils import is_enum, only_required_for_messages
from pylint.typing import MessageDefinitionTuple
if TYPE_CHECKING:
    from pylint.lint import PyLinter
MSGS: dict[str, MessageDefinitionTuple] = {'R0901': ('Too many ancestors (%s/%s)', 'too-many-ancestors', 'Used when class has too many parent classes, try to reduce this to get a simpler (and so easier to use) class.'), 'R0902': ('Too many instance attributes (%s/%s)', 'too-many-instance-attributes', 'Used when class has too many instance attributes, try to reduce this to get a simpler (and so easier to use) class.'), 'R0903': ('Too few public methods (%s/%s)', 'too-few-public-methods', "Used when class has too few public methods, so be sure it's really worth it."), 'R0904': ('Too many public methods (%s/%s)', 'too-many-public-methods', 'Used when class has too many public methods, try to reduce this to get a simpler (and so easier to use) class.'), 'R0911': ('Too many return statements (%s/%s)', 'too-many-return-statements', 'Used when a function or method has too many return statement, making it hard to follow.'), 'R0912': ('Too many branches (%s/%s)', 'too-many-branches', 'Used when a function or method has too many branches, making it hard to follow.'), 'R0913': ('Too many arguments (%s/%s)', 'too-many-arguments', 'Used when a function or method takes too many arguments.'), 'R0914': ('Too many local variables (%s/%s)', 'too-many-locals', 'Used when a function or method has too many local variables.'), 'R0915': ('Too many statements (%s/%s)', 'too-many-statements', 'Used when a function or method has too many statements. You should then split it in smaller functions / methods.'), 'R0916': ('Too many boolean expressions in if statement (%s/%s)', 'too-many-boolean-expressions', 'Used when an if statement contains too many boolean expressions.'), 'R0917': ('Too many positional arguments in a function call.', 'too-many-positional', 'Will be implemented in https://github.com/pylint-dev/pylint/issues/9099,msgid/symbol pair reserved for compatibility with ruff, see https://github.com/astral-sh/ruff/issues/8946.')}
SPECIAL_OBJ = re.compile('^_{2}[a-z]+_{2}$')
DATACLASSES_DECORATORS = frozenset({'dataclass', 'attrs'})
DATACLASS_IMPORT = 'dataclasses'
ATTRS_DECORATORS = frozenset({'define', 'frozen'})
ATTRS_IMPORT = 'attrs'
TYPING_NAMEDTUPLE = 'typing.NamedTuple'
TYPING_TYPEDDICT = 'typing.TypedDict'
TYPING_EXTENSIONS_TYPEDDICT = 'typing_extensions.TypedDict'
STDLIB_CLASSES_IGNORE_ANCESTOR = frozenset(('builtins.object', 'builtins.tuple', 'builtins.dict', 'builtins.list', 'builtins.set', 'bulitins.frozenset', 'collections.ChainMap', 'collections.Counter', 'collections.OrderedDict', 'collections.UserDict', 'collections.UserList', 'collections.UserString', 'collections.defaultdict', 'collections.deque', 'collections.namedtuple', '_collections_abc.Awaitable', '_collections_abc.Coroutine', '_collections_abc.AsyncIterable', '_collections_abc.AsyncIterator', '_collections_abc.AsyncGenerator', '_collections_abc.Hashable', '_collections_abc.Iterable', '_collections_abc.Iterator', '_collections_abc.Generator', '_collections_abc.Reversible', '_collections_abc.Sized', '_collections_abc.Container', '_collections_abc.Collection', '_collections_abc.Set', '_collections_abc.MutableSet', '_collections_abc.Mapping', '_collections_abc.MutableMapping', '_collections_abc.MappingView', '_collections_abc.KeysView', '_collections_abc.ItemsView', '_collections_abc.ValuesView', '_collections_abc.Sequence', '_collections_abc.MutableSequence', '_collections_abc.ByteString', 'typing.Tuple', 'typing.List', 'typing.Dict', 'typing.Set', 'typing.FrozenSet', 'typing.Deque', 'typing.DefaultDict', 'typing.OrderedDict', 'typing.Counter', 'typing.ChainMap', 'typing.Awaitable', 'typing.Coroutine', 'typing.AsyncIterable', 'typing.AsyncIterator', 'typing.AsyncGenerator', 'typing.Iterable', 'typing.Iterator', 'typing.Generator', 'typing.Reversible', 'typing.Container', 'typing.Collection', 'typing.AbstractSet', 'typing.MutableSet', 'typing.Mapping', 'typing.MutableMapping', 'typing.Sequence', 'typing.MutableSequence', 'typing.ByteString', 'typing.MappingView', 'typing.KeysView', 'typing.ItemsView', 'typing.ValuesView', 'typing.ContextManager', 'typing.AsyncContextManager', 'typing.Hashable', 'typing.Sized', TYPING_NAMEDTUPLE, TYPING_TYPEDDICT, TYPING_EXTENSIONS_TYPEDDICT))

def _is_exempt_from_public_methods(node: astroid.ClassDef) -> bool:
    """Check if a class is exempt from too-few-public-methods."""
    return (
        is_enum(node)
        or node.name in STDLIB_CLASSES_IGNORE_ANCESTOR
        or any(
            node.is_subtype_of(f"{DATACLASS_IMPORT}.{decorator}")
            for decorator in DATACLASSES_DECORATORS
        )
        or any(
            node.is_subtype_of(f"{ATTRS_IMPORT}.{decorator}")
            for decorator in ATTRS_DECORATORS
        )
        or node.is_subtype_of(TYPING_NAMEDTUPLE)
        or node.is_subtype_of(TYPING_TYPEDDICT)
        or node.is_subtype_of(TYPING_EXTENSIONS_TYPEDDICT)
    )

def _count_boolean_expressions(bool_op: nodes.BoolOp) -> int:
    """Counts the number of boolean expressions in BoolOp `bool_op` (recursive).

    example: a and (b or c or (d and e)) ==> 5 boolean expressions
    """
    return sum(
        _count_boolean_expressions(node) if isinstance(node, nodes.BoolOp) else 1
        for node in bool_op.values
    )

def _get_parents_iter(node: nodes.ClassDef, ignored_parents: frozenset[str]) -> Iterator[nodes.ClassDef]:
    """Get parents of ``node``, excluding ancestors of ``ignored_parents``.

    If we have the following inheritance diagram:

             F
            /
        D  E
         \\/
          B  C
           \\/
            A      # class A(B, C): ...

    And ``ignored_parents`` is ``{"E"}``, then this function will return
    ``{A, B, C, D}`` -- both ``E`` and its ancestors are excluded.
    """
    for parent in node.ancestors():
        if parent.qname() in ignored_parents:
            continue
        yield parent

class MisdesignChecker(BaseChecker):
    """Checker of potential misdesigns.

    Checks for sign of poor/misdesign:
    * number of methods, attributes, local variables...
    * size, complexity of functions, methods
    """
    name = 'design'
    msgs = MSGS
    options = (('max-args', {'default': 5, 'type': 'int', 'metavar': '<int>', 'help': 'Maximum number of arguments for function / method.'}), ('max-locals', {'default': 15, 'type': 'int', 'metavar': '<int>', 'help': 'Maximum number of locals for function / method body.'}), ('max-returns', {'default': 6, 'type': 'int', 'metavar': '<int>', 'help': 'Maximum number of return / yield for function / method body.'}), ('max-branches', {'default': 12, 'type': 'int', 'metavar': '<int>', 'help': 'Maximum number of branch for function / method body.'}), ('max-statements', {'default': 50, 'type': 'int', 'metavar': '<int>', 'help': 'Maximum number of statements in function / method body.'}), ('max-parents', {'default': 7, 'type': 'int', 'metavar': '<num>', 'help': 'Maximum number of parents for a class (see R0901).'}), ('ignored-parents', {'default': (), 'type': 'csv', 'metavar': '<comma separated list of class names>', 'help': 'List of qualified class names to ignore when counting class parents (see R0901)'}), ('max-attributes', {'default': 7, 'type': 'int', 'metavar': '<num>', 'help': 'Maximum number of attributes for a class (see R0902).'}), ('min-public-methods', {'default': 2, 'type': 'int', 'metavar': '<num>', 'help': 'Minimum number of public methods for a class (see R0903).'}), ('max-public-methods', {'default': 20, 'type': 'int', 'metavar': '<num>', 'help': 'Maximum number of public methods for a class (see R0904).'}), ('max-bool-expr', {'default': 5, 'type': 'int', 'metavar': '<num>', 'help': 'Maximum number of boolean expressions in an if statement (see R0916).'}), ('exclude-too-few-public-methods', {'default': [], 'type': 'regexp_csv', 'metavar': '<pattern>[,<pattern>...]', 'help': 'List of regular expressions of class ancestor names to ignore when counting public methods (see R0903)'}))

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._returns: list[int]
        self._branches: defaultdict[nodes.LocalsDictNodeNG, int]
        self._stmts: list[int]

    def open(self) -> None:
        """Initialize visit variables."""
        self._returns = []
        self._branches = defaultdict(int)
        self._stmts = []

    @only_required_for_messages('too-many-ancestors', 'too-many-instance-attributes', 'too-few-public-methods', 'too-many-public-methods')
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """Check size of inheritance hierarchy and number of instance attributes."""
        ignored_parents = frozenset(self.linter.config.ignored_parents)
        # Do not check ignored classes
        if node.qname() in ignored_parents:
            return

        # Count the number of ancestors
        try:
            ancestors = list(_get_parents_iter(node, ignored_parents))
        except astroid.MroError:
            # This class has an invalid MRO, this should be reported by another checker.
            return
        
        # Only check ancestors if the class has a non-trivial inheritance hierarchy
        if len(ancestors) > 1:
            self.add_message(
                'too-many-ancestors',
                node=node,
                args=(len(ancestors), self.linter.config.max_parents),
                confidence=HIGH,
            )

        # Count the number of instance attributes
        instance_attrs = list(node.instance_attrs.keys())
        if len(instance_attrs) > self.linter.config.max_attributes:
            self.add_message(
                'too-many-instance-attributes',
                node=node,
                args=(len(instance_attrs), self.linter.config.max_attributes),
                confidence=HIGH,
            )

    @only_required_for_messages('too-few-public-methods', 'too-many-public-methods')
    def leave_classdef(self, node: nodes.ClassDef) -> None:
        """Check number of public methods."""
        if _is_exempt_from_public_methods(node):
            return

        if not any(
            isinstance(ancestor, astroid.scoped_nodes.ClassDef)
            and ancestor.name in self.linter.config.exclude_too_few_public_methods
            for ancestor in node.ancestors()
        ):
            public_methods = [
                method
                for method in node.mymethods()
                if not method.name.startswith("_") and method.type == "method"
            ]
            if len(public_methods) == 0 and len(node.instance_attrs) == 0:
                self.add_message('too-few-public-methods', node=node, confidence=HIGH)
            elif len(public_methods) > self.linter.config.max_public_methods:
                self.add_message(
                    'too-many-public-methods',
                    node=node,
                    args=(len(public_methods), self.linter.config.max_public_methods),
                    confidence=HIGH,
                )

    @only_required_for_messages('too-many-return-statements', 'too-many-branches', 'too-many-arguments', 'too-many-locals', 'too-many-statements', 'keyword-arg-before-vararg')
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check function name, docstring, arguments, redefinition,
        variable names, max locals.
        """
        # Check the number of arguments
        args = node.args.args
        if args is not None:
            ignored_argument_names = self.linter.config.ignored_argument_names
            args = [arg for arg in args if not ignored_argument_names.match(arg.name)]
            if len(args) > self.linter.config.max_args:
                self.add_message(
                    'too-many-arguments',
                    node=node,
                    args=(len(args), self.linter.config.max_args),
                    confidence=HIGH,
                )

        # Check if there's a keyword argument before a variable argument
        if node.args.kwarg and node.args.vararg:
            if node.args.kwarg.lineno < node.args.vararg.lineno:
                self.add_message('keyword-arg-before-vararg', node=node, confidence=HIGH)

        # init function specific checks
        if node.name == '__init__':
            self._check_init_function(node)
        else:
            self._check_function(node)
    visit_asyncfunctiondef = visit_functiondef

    @only_required_for_messages('too-many-return-statements', 'too-many-branches', 'too-many-arguments', 'too-many-locals', 'too-many-statements')
    def leave_functiondef(self, node: nodes.FunctionDef) -> None:
        """Most of the work is done here on close:
        checks for max returns, branch, return in __init__.
        """
        returns = self._returns.pop()
        if returns > self.linter.config.max_returns:
            self.add_message(
                'too-many-return-statements',
                node=node,
                args=(returns, self.linter.config.max_returns),
                confidence=HIGH,
            )
        branches = self._branches[node]
        if branches > self.linter.config.max_branches:
            self.add_message(
                'too-many-branches',
                node=node,
                args=(branches, self.linter.config.max_branches),
                confidence=HIGH,
            )
        # check number of local variables
        locals_count = len(node.locals)
        if locals_count > self.linter.config.max_locals:
            self.add_message(
                'too-many-locals',
                node=node,
                args=(locals_count, self.linter.config.max_locals),
                confidence=HIGH,
            )
        statements = self._stmts.pop()
        if statements > self.linter.config.max_statements:
            self.add_message(
                'too-many-statements',
                node=node,
                args=(statements, self.linter.config.max_statements),
                confidence=HIGH,
            )
    leave_asyncfunctiondef = leave_functiondef

    def visit_return(self, _: nodes.Return) -> None:
        """Count number of returns."""
        if not self._returns:
            self._returns.append(1)
        else:
            self._returns[-1] += 1

    def visit_default(self, node: nodes.NodeNG) -> None:
        """Default visit method -> increments the statements counter if
        necessary.
        """
        if isinstance(node, nodes.Statement):
            if not self._stmts:
                self._stmts.append(1)
            else:
                self._stmts[-1] += 1

    def visit_try(self, node: nodes.Try) -> None:
        """Increments the branches counter."""
        self._inc_branch(node)
        # try considered as one branch
        self._inc_branch(node, 1)
        # one branch for each except
        self._inc_branch(node, len(node.handlers))
        # finally
        if node.finalbody:
            self._inc_branch(node, 1)

    @only_required_for_messages('too-many-boolean-expressions', 'too-many-branches')
    def visit_if(self, node: nodes.If) -> None:
        """Increments the branches counter and checks boolean expressions."""
        self._inc_branch(node)
        self._inc_branch(node, 2)
        # if there is an elif: go through all elif
        if node.orelse and len(node.orelse) == 1 and isinstance(node.orelse[0], nodes.If):
            self._inc_branch(node, len(list(node.orelse[0].nodes_of_class(nodes.If))) + 1)
        self._check_boolean_expressions(node)

    def _check_boolean_expressions(self, node: nodes.If) -> None:
        """Go through "if" node `node` and count its boolean expressions
        if the 'if' node test is a BoolOp node.
        """
        condition = node.test
        if isinstance(condition, nodes.BoolOp):
            nb_bool_expr = _count_boolean_expressions(condition)
            if nb_bool_expr > self.linter.config.max_bool_expr:
                self.add_message(
                    'too-many-boolean-expressions',
                    node=condition,
                    args=(nb_bool_expr, self.linter.config.max_bool_expr),
                    confidence=HIGH,
                )

    def visit_while(self, node: nodes.While) -> None:
        """Increments the branches counter."""
        self._inc_branch(node)
        self._inc_branch(node, 2)
    visit_for = visit_while

    def _inc_branch(self, node: nodes.NodeNG, branchesnum: int=1) -> None:
        """Increments the branches counter."""
        parent = node.parent
        while parent and not isinstance(parent, (nodes.FunctionDef, nodes.AsyncFunctionDef)):
            parent = parent.parent
        if parent:
            self._branches[parent] += branchesnum
