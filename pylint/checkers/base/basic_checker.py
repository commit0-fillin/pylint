"""Basic checker for Python code."""
from __future__ import annotations
import collections
import itertools
from collections.abc import Iterator
from typing import TYPE_CHECKING, Literal, cast
import astroid
from astroid import nodes, objects, util
from pylint import utils as lint_utils
from pylint.checkers import BaseChecker, utils
from pylint.interfaces import HIGH, INFERENCE, Confidence
from pylint.reporters.ureports import nodes as reporter_nodes
from pylint.utils import LinterStats
if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter

class _BasicChecker(BaseChecker):
    """Permits separating multiple checks with the same checker name into
    classes/file.
    """
    name = 'basic'
REVERSED_PROTOCOL_METHOD = '__reversed__'
SEQUENCE_PROTOCOL_METHODS = ('__getitem__', '__len__')
REVERSED_METHODS = (SEQUENCE_PROTOCOL_METHODS, (REVERSED_PROTOCOL_METHOD,))
DEFAULT_ARGUMENT_SYMBOLS = dict(zip(['.'.join(['builtins', x]) for x in ('set', 'dict', 'list')], ['set()', '{}', '[]']), **{x: f'{x}()' for x in ('collections.deque', 'collections.ChainMap', 'collections.Counter', 'collections.OrderedDict', 'collections.defaultdict', 'collections.UserDict', 'collections.UserList')})

def report_by_type_stats(sect: reporter_nodes.Section, stats: LinterStats, old_stats: LinterStats | None) -> None:
    """Make a report of.

    * percentage of different types documented
    * percentage of different types with a bad name
    """
    type_stats = sect.add_table(["type", "number", "old number", "documented", "badname"])
    for node_type in ("module", "class", "method", "function"):
        total = stats.get_node_count(node_type)
        old_total = old_stats.get_node_count(node_type) if old_stats else None
        documented = stats.get_documented_node_count(node_type)
        percent_documented = 100.0 * documented / total if total else 0
        badname = stats.get_bad_names_node_count(node_type)
        percent_badname = 100.0 * badname / total if total else 0
        type_stats.append_row([
            node_type,
            str(total),
            str(old_total) if old_total is not None else "NC",
            f"{percent_documented:.2f}% ({documented}/{total})",
            f"{percent_badname:.2f}% ({badname}/{total})",
        ])

class BasicChecker(_BasicChecker):
    """Basic checker.

    Checks for :
    * doc strings
    * number of arguments, local variables, branches, returns and statements in
    functions, methods
    * required module attributes
    * dangerous default values as arguments
    * redefinition of function / method / class
    * uses of the global statement
    """
    name = 'basic'
    msgs = {'W0101': ('Unreachable code', 'unreachable', 'Used when there is some code behind a "return" or "raise" statement, which will never be accessed.'), 'W0102': ('Dangerous default value %s as argument', 'dangerous-default-value', 'Used when a mutable value as list or dictionary is detected in a default value for an argument.'), 'W0104': ('Statement seems to have no effect', 'pointless-statement', "Used when a statement doesn't have (or at least seems to) any effect."), 'W0105': ('String statement has no effect', 'pointless-string-statement', "Used when a string is used as a statement (which of course has no effect). This is a particular case of W0104 with its own message so you can easily disable it if you're using those strings as documentation, instead of comments."), 'W0106': ('Expression "%s" is assigned to nothing', 'expression-not-assigned', 'Used when an expression that is not a function call is assigned to nothing. Probably something else was intended.'), 'W0108': ('Lambda may not be necessary', 'unnecessary-lambda', 'Used when the body of a lambda expression is a function call on the same argument list as the lambda itself; such lambda expressions are in all but a few cases replaceable with the function being called in the body of the lambda.'), 'W0109': ('Duplicate key %r in dictionary', 'duplicate-key', 'Used when a dictionary expression binds the same key multiple times.'), 'W0122': ('Use of exec', 'exec-used', "Raised when the 'exec' statement is used. It's dangerous to use this function for a user input, and it's also slower than actual code in general. This doesn't mean you should never use it, but you should consider alternatives first and restrict the functions available."), 'W0123': ('Use of eval', 'eval-used', 'Used when you use the "eval" function, to discourage its usage. Consider using `ast.literal_eval` for safely evaluating strings containing Python expressions from untrusted sources.'), 'W0150': ('%s statement in finally block may swallow exception', 'lost-exception', 'Used when a break or a return statement is found inside the finally clause of a try...finally block: the exceptions raised in the try clause will be silently swallowed instead of being re-raised.'), 'W0199': ("Assert called on a populated tuple. Did you mean 'assert x,y'?", 'assert-on-tuple', 'A call of assert on a tuple will always evaluate to true if the tuple is not empty, and will always evaluate to false if it is.'), 'W0124': ('Following "as" with another context manager looks like a tuple.', 'confusing-with-statement', "Emitted when a `with` statement component returns multiple values and uses name binding with `as` only for a part of those values, as in with ctx() as a, b. This can be misleading, since it's not clear if the context manager returns a tuple or if the node without a name binding is another context manager."), 'W0125': ('Using a conditional statement with a constant value', 'using-constant-test', 'Emitted when a conditional statement (If or ternary if) uses a constant value for its test. This might not be what the user intended to do.'), 'W0126': ('Using a conditional statement with potentially wrong function or method call due to missing parentheses', 'missing-parentheses-for-call-in-test', 'Emitted when a conditional statement (If or ternary if) seems to wrongly call a function due to missing parentheses'), 'W0127': ('Assigning the same variable %r to itself', 'self-assigning-variable', 'Emitted when we detect that a variable is assigned to itself'), 'W0128': ('Redeclared variable %r in assignment', 'redeclared-assigned-name', 'Emitted when we detect that a variable was redeclared in the same assignment.'), 'E0111': ('The first reversed() argument is not a sequence', 'bad-reversed-sequence', "Used when the first argument to reversed() builtin isn't a sequence (does not implement __reversed__, nor __getitem__ and __len__"), 'E0119': ('format function is not called on str', 'misplaced-format-function', 'Emitted when format function is not called on str object. e.g doing print("value: {}").format(123) instead of print("value: {}".format(123)). This might not be what the user intended to do.'), 'W0129': ('Assert statement has a string literal as its first argument. The assert will %s fail.', 'assert-on-string-literal', 'Used when an assert statement has a string literal as its first argument, which will cause the assert to always pass.'), 'W0130': ('Duplicate value %r in set', 'duplicate-value', 'This message is emitted when a set contains the same value two or more times.'), 'W0131': ('Named expression used without context', 'named-expr-without-context', 'Emitted if named expression is used to do a regular assignment outside a context like if, for, while, or a comprehension.'), 'W0133': ('Exception statement has no effect', 'pointless-exception-statement', 'Used when an exception is created without being assigned, raised or returned for subsequent use elsewhere.'), 'W0134': ("'return' shadowed by the 'finally' clause.", 'return-in-finally', "Emitted when a 'return' statement is found in a 'finally' block. This will overwrite the return value of a function and should be avoided.")}
    reports = (('RP0101', 'Statistics by type', report_by_type_stats),)

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._trys: list[nodes.Try]

    def open(self) -> None:
        """Initialize visit variables and statistics."""
        self._tryfinally = []
        self._init_variables()
        self._init_statistics()

    def _init_variables(self) -> None:
        self._return_nodes = []
        self._continue_nodes = []
        self._break_nodes = []
        self._raise_nodes = []

    def _init_statistics(self) -> None:
        self.stats = {
            'statement': 0,
            'function': 0,
            'class': 0,
            'method': 0,
            'module': 0,
        }

    @staticmethod
    def _name_holds_generator(test: nodes.Name) -> tuple[bool, nodes.Call | None]:
        """Return whether `test` tests a name certain to hold a generator, or optionally
        a call that should be then tested to see if *it* returns only generators.
        """
        if not isinstance(test, nodes.Name):
            return False, None
        
        inferred = safe_infer(test)
        if inferred is None:
            return False, None
        
        if isinstance(inferred, astroid.Generator):
            return True, None
        
        if isinstance(inferred, astroid.FunctionDef):
            if inferred.is_generator():
                return True, None
            if isinstance(test.parent, nodes.Call):
                return False, test.parent
        
        return False, None

    def visit_module(self, node: nodes.Module) -> None:
        """Check module name, docstring and required arguments."""
        self.stats['module'] += 1
        self._check_module_name(node)
        self._check_module_docstring(node)
        self._check_required_attributes(node)

    def _check_module_name(self, node: nodes.Module) -> None:
        if not node.name:
            return
        if not node.name.isidentifier():
            self.add_message('invalid-name', node=node, args=(node.name,))

    def _check_module_docstring(self, node: nodes.Module) -> None:
        if not node.doc:
            self.add_message('missing-module-docstring', node=node)

    def _check_required_attributes(self, node: nodes.Module) -> None:
        required_attributes = self.config.required_attributes
        for attr in required_attributes:
            if not hasattr(node, attr):
                self.add_message('missing-required-attribute', node=node, args=(attr,))

    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """Check class name, docstring and redefinition
        increment branch counter.
        """
        self.stats['class'] += 1
        self._check_class_name(node)
        self._check_class_docstring(node)
        self._check_class_redefinition(node)
        self.stats['statement'] += 1

    def _check_class_name(self, node: nodes.ClassDef) -> None:
        if not node.name.isidentifier():
            self.add_message('invalid-name', node=node, args=(node.name,))

    def _check_class_docstring(self, node: nodes.ClassDef) -> None:
        if not node.doc and not node.is_protocol():
            self.add_message('missing-class-docstring', node=node)

    def _check_class_redefinition(self, node: nodes.ClassDef) -> None:
        defined = node.parent.scope().lookup(node.name)
        if defined and defined[1][-1].lineno < node.lineno:
            self.add_message('redefined-outer-name', node=node, args=(node.name,))

    @utils.only_required_for_messages('pointless-statement', 'pointless-exception-statement', 'pointless-string-statement', 'expression-not-assigned', 'named-expr-without-context')
    def visit_expr(self, node: nodes.Expr) -> None:
        """Check for various kind of statements without effect."""
        pass

    @utils.only_required_for_messages('unnecessary-lambda')
    def visit_lambda(self, node: nodes.Lambda) -> None:
        """Check whether the lambda is suspicious."""
        pass

    @utils.only_required_for_messages('dangerous-default-value')
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check function name, docstring, arguments, redefinition,
        variable names, max locals.
        """
        pass
    visit_asyncfunctiondef = visit_functiondef

    def _check_dangerous_default(self, node: nodes.FunctionDef) -> None:
        """Check for dangerous default values as arguments."""
        pass

    @utils.only_required_for_messages('unreachable', 'lost-exception')
    def visit_return(self, node: nodes.Return) -> None:
        """Return node visitor.

        1 - check if the node has a right sibling (if so, that's some
        unreachable code)
        2 - check if the node is inside the 'finally' clause of a 'try...finally'
        block
        """
        pass

    @utils.only_required_for_messages('unreachable')
    def visit_continue(self, node: nodes.Continue) -> None:
        """Check is the node has a right sibling (if so, that's some unreachable
        code).
        """
        pass

    @utils.only_required_for_messages('unreachable', 'lost-exception')
    def visit_break(self, node: nodes.Break) -> None:
        """Break node visitor.

        1 - check if the node has a right sibling (if so, that's some
        unreachable code)
        2 - check if the node is inside the 'finally' clause of a 'try...finally'
        block
        """
        pass

    @utils.only_required_for_messages('unreachable')
    def visit_raise(self, node: nodes.Raise) -> None:
        """Check if the node has a right sibling (if so, that's some unreachable
        code).
        """
        pass

    @utils.only_required_for_messages('eval-used', 'exec-used', 'bad-reversed-sequence', 'misplaced-format-function', 'unreachable')
    def visit_call(self, node: nodes.Call) -> None:
        """Visit a Call node."""
        pass

    @utils.only_required_for_messages('assert-on-tuple', 'assert-on-string-literal')
    def visit_assert(self, node: nodes.Assert) -> None:
        """Check whether assert is used on a tuple or string literal."""
        pass

    @utils.only_required_for_messages('duplicate-key')
    def visit_dict(self, node: nodes.Dict) -> None:
        """Check duplicate key in dictionary."""
        pass

    @utils.only_required_for_messages('duplicate-value')
    def visit_set(self, node: nodes.Set) -> None:
        """Check duplicate value in set."""
        pass

    def visit_try(self, node: nodes.Try) -> None:
        """Update try block flag."""
        pass

    def leave_try(self, _: nodes.Try) -> None:
        """Update try block flag."""
        pass

    def _check_unreachable(self, node: nodes.Return | nodes.Continue | nodes.Break | nodes.Raise | nodes.Call, confidence: Confidence=HIGH) -> None:
        """Check unreachable code."""
        pass

    def _check_not_in_finally(self, node: nodes.Break | nodes.Return, node_name: str, breaker_classes: tuple[nodes.NodeNG, ...]=()) -> None:
        """Check that a node is not inside a 'finally' clause of a
        'try...finally' statement.

        If we find a parent which type is in breaker_classes before
        a 'try...finally' block we skip the whole check.
        """
        pass

    def _check_reversed(self, node: nodes.Call) -> None:
        """Check that the argument to `reversed` is a sequence."""
        pass
