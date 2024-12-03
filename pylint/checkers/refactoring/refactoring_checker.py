from __future__ import annotations
import collections
import copy
import itertools
import tokenize
from collections.abc import Iterator
from functools import cached_property, reduce
from re import Pattern
from typing import TYPE_CHECKING, Any, NamedTuple, Union, cast
import astroid
from astroid import bases, nodes
from astroid.util import UninferableBase
from pylint import checkers
from pylint.checkers import utils
from pylint.checkers.base.basic_error_checker import _loop_exits_early
from pylint.checkers.utils import node_frame_class
from pylint.interfaces import HIGH, INFERENCE, Confidence
if TYPE_CHECKING:
    from pylint.lint import PyLinter
NodesWithNestedBlocks = Union[nodes.Try, nodes.While, nodes.For, nodes.If]
KNOWN_INFINITE_ITERATORS = {'itertools.count', 'itertools.cycle'}
BUILTIN_EXIT_FUNCS = frozenset(('quit', 'exit'))
CALLS_THAT_COULD_BE_REPLACED_BY_WITH = frozenset(('threading.lock.acquire', 'threading._RLock.acquire', 'threading.Semaphore.acquire', 'multiprocessing.managers.BaseManager.start', 'multiprocessing.managers.SyncManager.start'))
CALLS_RETURNING_CONTEXT_MANAGERS = frozenset(('_io.open', 'pathlib.Path.open', 'codecs.open', 'urllib.request.urlopen', 'tempfile.NamedTemporaryFile', 'tempfile.SpooledTemporaryFile', 'tempfile.TemporaryDirectory', 'tempfile.TemporaryFile', 'zipfile.ZipFile', 'zipfile.PyZipFile', 'zipfile.ZipFile.open', 'zipfile.PyZipFile.open', 'tarfile.TarFile', 'tarfile.TarFile.open', 'multiprocessing.context.BaseContext.Pool', 'subprocess.Popen'))

def _except_statement_is_always_returning(node: nodes.Try, returning_node_class: nodes.NodeNG) -> bool:
    """Detect if all except statements return."""
    for handler in node.handlers:
        if not isinstance(handler.body[-1], returning_node_class):
            return False
    return bool(node.handlers)

def _is_trailing_comma(tokens: list[tokenize.TokenInfo], index: int) -> bool:
    """Check if the given token is a trailing comma.

    :param tokens: Sequence of modules tokens
    :type tokens: list[tokenize.TokenInfo]
    :param int index: Index of token under check in tokens
    :returns: True if the token is a comma which trails an expression
    :rtype: bool
    """
    token = tokens[index]
    if token.exact_type != tokenize.COMMA:
        return False
    
    # Skip whitespace and comments
    next_token_index = index + 1
    while next_token_index < len(tokens) and tokens[next_token_index].type in (tokenize.NL, tokenize.COMMENT):
        next_token_index += 1
    
    if next_token_index >= len(tokens):
        return True
    
    next_token = tokens[next_token_index]
    return next_token.exact_type in (tokenize.RPAR, tokenize.RBRACE, tokenize.RBRACKET)

def _is_part_of_with_items(node: nodes.Call) -> bool:
    """Checks if one of the node's parents is a ``nodes.With`` node and that the node
    itself is located somewhere under its ``items``.
    """
    parent = node.parent
    while parent:
        if isinstance(parent, nodes.With):
            for item in parent.items:
                if node.parent_of(item.context_expr) or node is item.context_expr:
                    return True
        parent = parent.parent
    return False

def _will_be_released_automatically(node: nodes.Call) -> bool:
    """Checks if a call that could be used in a ``with`` statement is used in an
    alternative construct which would ensure that its __exit__ method is called.
    """
    parent = node.parent
    while parent:
        if isinstance(parent, (nodes.FunctionDef, nodes.ClassDef)):
            break
        if isinstance(parent, nodes.Try):
            for handler in parent.handlers:
                if isinstance(handler.type, nodes.Name) and handler.type.name == 'Exception':
                    return True
            if parent.finalbody:
                return True
        parent = parent.parent
    return False

def _is_part_of_assignment_target(node: nodes.NodeNG) -> bool:
    """Check whether use of a variable is happening as part of the left-hand
    side of an assignment.

    This requires recursive checking, because destructuring assignment can have
    arbitrarily nested tuples and lists to unpack.
    """
    pass

class ConsiderUsingWithStack(NamedTuple):
    """Stack for objects that may potentially trigger a R1732 message
    if they are not used in a ``with`` block later on.
    """
    module_scope: dict[str, nodes.NodeNG] = {}
    class_scope: dict[str, nodes.NodeNG] = {}
    function_scope: dict[str, nodes.NodeNG] = {}

    def __iter__(self) -> Iterator[dict[str, nodes.NodeNG]]:
        yield from (self.function_scope, self.class_scope, self.module_scope)

    def get_stack_for_frame(self, frame: nodes.FunctionDef | nodes.ClassDef | nodes.Module) -> dict[str, nodes.NodeNG]:
        """Get the stack corresponding to the scope of the given frame."""
        pass

    def clear_all(self) -> None:
        """Convenience method to clear all stacks."""
        pass

class RefactoringChecker(checkers.BaseTokenChecker):
    """Looks for code which can be refactored.

    This checker also mixes the astroid and the token approaches
    in order to create knowledge about whether an "else if" node
    is a true "else if" node, or an "elif" node.
    """
    name = 'refactoring'
    msgs = {'R1701': ('Consider merging these isinstance calls to isinstance(%s, (%s))', 'consider-merging-isinstance', 'Used when multiple consecutive isinstance calls can be merged into one.'), 'R1706': ('Consider using ternary (%s)', 'consider-using-ternary', 'Used when one of known pre-python 2.5 ternary syntax is used.'), 'R1709': ('Boolean expression may be simplified to %s', 'simplify-boolean-expression', 'Emitted when redundant pre-python 2.5 ternary syntax is used.'), 'R1726': ('Boolean condition "%s" may be simplified to "%s"', 'simplifiable-condition', 'Emitted when a boolean condition is able to be simplified.'), 'R1727': ("Boolean condition '%s' will always evaluate to '%s'", 'condition-evals-to-constant', 'Emitted when a boolean condition can be simplified to a constant value.'), 'R1702': ('Too many nested blocks (%s/%s)', 'too-many-nested-blocks', 'Used when a function or a method has too many nested blocks. This makes the code less understandable and maintainable.', {'old_names': [('R0101', 'old-too-many-nested-blocks')]}), 'R1703': ('The if statement can be replaced with %s', 'simplifiable-if-statement', "Used when an if statement can be replaced with 'bool(test)'.", {'old_names': [('R0102', 'old-simplifiable-if-statement')]}), 'R1704': ('Redefining argument with the local name %r', 'redefined-argument-from-local', 'Used when a local name is redefining an argument, which might suggest a potential error. This is taken in account only for a handful of name binding operations, such as for iteration, with statement assignment and exception handler assignment.'), 'R1705': ('Unnecessary "%s" after "return", %s', 'no-else-return', 'Used in order to highlight an unnecessary block of code following an if containing a return statement. As such, it will warn when it encounters an else following a chain of ifs, all of them containing a return statement.'), 'R1707': ('Disallow trailing comma tuple', 'trailing-comma-tuple', 'In Python, a tuple is actually created by the comma symbol, not by the parentheses. Unfortunately, one can actually create a tuple by misplacing a trailing comma, which can lead to potential weird bugs in your code. You should always use parentheses explicitly for creating a tuple.'), 'R1708': ('Do not raise StopIteration in generator, use return statement instead', 'stop-iteration-return', 'According to PEP479, the raise of StopIteration to end the loop of a generator may lead to hard to find bugs. This PEP specify that raise StopIteration has to be replaced by a simple return statement'), 'R1710': ('Either all return statements in a function should return an expression, or none of them should.', 'inconsistent-return-statements', 'According to PEP8, if any return statement returns an expression, any return statements where no value is returned should explicitly state this as return None, and an explicit return statement should be present at the end of the function (if reachable)'), 'R1711': ('Useless return at end of function or method', 'useless-return', 'Emitted when a single "return" or "return None" statement is found at the end of function or method definition. This statement can safely be removed because Python will implicitly return None'), 'R1712': ('Consider using tuple unpacking for swapping variables', 'consider-swap-variables', 'You do not have to use a temporary variable in order to swap variables. Using "tuple unpacking" to directly swap variables makes the intention more clear.'), 'R1713': ('Consider using str.join(sequence) for concatenating strings from an iterable', 'consider-using-join', 'Using str.join(sequence) is faster, uses less memory and increases readability compared to for-loop iteration.'), 'R1714': ("Consider merging these comparisons with 'in' by using '%s %sin (%s)'. Use a set instead if elements are hashable.", 'consider-using-in', 'To check if a variable is equal to one of many values, combine the values into a set or tuple and check if the variable is contained "in" it instead of checking for equality against each of the values. This is faster and less verbose.'), 'R1715': ('Consider using dict.get for getting values from a dict if a key is present or a default if not', 'consider-using-get', 'Using the builtin dict.get for getting a value from a dictionary if a key is present or a default if not, is simpler and considered more idiomatic, although sometimes a bit slower'), 'R1716': ('Simplify chained comparison between the operands', 'chained-comparison', 'This message is emitted when pylint encounters boolean operation like "a < b and b < c", suggesting instead to refactor it to "a < b < c"'), 'R1717': ('Consider using a dictionary comprehension', 'consider-using-dict-comprehension', "Emitted when we detect the creation of a dictionary using the dict() callable and a transient list. Although there is nothing syntactically wrong with this code, it is hard to read and can be simplified to a dict comprehension. Also it is faster since you don't need to create another transient list"), 'R1718': ('Consider using a set comprehension', 'consider-using-set-comprehension', "Although there is nothing syntactically wrong with this code, it is hard to read and can be simplified to a set comprehension. Also it is faster since you don't need to create another transient list"), 'R1719': ('The if expression can be replaced with %s', 'simplifiable-if-expression', "Used when an if expression can be replaced with 'bool(test)' or simply 'test' if the boolean cast is implicit."), 'R1720': ('Unnecessary "%s" after "raise", %s', 'no-else-raise', 'Used in order to highlight an unnecessary block of code following an if containing a raise statement. As such, it will warn when it encounters an else following a chain of ifs, all of them containing a raise statement.'), 'R1721': ('Unnecessary use of a comprehension, use %s instead.', 'unnecessary-comprehension', 'Instead of using an identity comprehension, consider using the list, dict or set constructor. It is faster and simpler.'), 'R1722': ("Consider using 'sys.exit' instead", 'consider-using-sys-exit', "Contrary to 'exit()' or 'quit()', 'sys.exit' does not rely on the site module being available (as the 'sys' module is always available)."), 'R1723': ('Unnecessary "%s" after "break", %s', 'no-else-break', 'Used in order to highlight an unnecessary block of code following an if containing a break statement. As such, it will warn when it encounters an else following a chain of ifs, all of them containing a break statement.'), 'R1724': ('Unnecessary "%s" after "continue", %s', 'no-else-continue', 'Used in order to highlight an unnecessary block of code following an if containing a continue statement. As such, it will warn when it encounters an else following a chain of ifs, all of them containing a continue statement.'), 'R1725': ('Consider using Python 3 style super() without arguments', 'super-with-arguments', 'Emitted when calling the super() builtin with the current class and instance. On Python 3 these arguments are the default and they can be omitted.'), 'R1728': ("Consider using a generator instead '%s(%s)'", 'consider-using-generator', 'If your container can be large using a generator will bring better performance.'), 'R1729': ("Use a generator instead '%s(%s)'", 'use-a-generator', "Comprehension inside of 'any', 'all', 'max', 'min' or 'sum' is unnecessary. A generator would be sufficient and faster."), 'R1730': ("Consider using '%s' instead of unnecessary if block", 'consider-using-min-builtin', 'Using the min builtin instead of a conditional improves readability and conciseness.'), 'R1731': ("Consider using '%s' instead of unnecessary if block", 'consider-using-max-builtin', 'Using the max builtin instead of a conditional improves readability and conciseness.'), 'R1732': ("Consider using 'with' for resource-allocating operations", 'consider-using-with', "Emitted if a resource-allocating assignment or call may be replaced by a 'with' block. By using 'with' the release of the allocated resources is ensured even in the case of an exception."), 'R1733': ("Unnecessary dictionary index lookup, use '%s' instead", 'unnecessary-dict-index-lookup', 'Emitted when iterating over the dictionary items (key-item pairs) and accessing the value by index lookup. The value can be accessed directly instead.'), 'R1734': ('Consider using [] instead of list()', 'use-list-literal', 'Emitted when using list() to create an empty list instead of the literal []. The literal is faster as it avoids an additional function call.'), 'R1735': ("Consider using '%s' instead of a call to 'dict'.", 'use-dict-literal', "Emitted when using dict() to create a dictionary instead of a literal '{ ... }'. The literal is faster as it avoids an additional function call."), 'R1736': ("Unnecessary list index lookup, use '%s' instead", 'unnecessary-list-index-lookup', 'Emitted when iterating over an enumeration and accessing the value by index lookup. The value can be accessed directly instead.'), 'R1737': ("Use 'yield from' directly instead of yielding each element one by one", 'use-yield-from', 'Yielding directly from the iterator is faster and arguably cleaner code than yielding each element one by one in the loop.')}
    options = (('max-nested-blocks', {'default': 5, 'type': 'int', 'metavar': '<int>', 'help': 'Maximum number of nested blocks for function / method body'}), ('never-returning-functions', {'default': ('sys.exit', 'argparse.parse_error'), 'type': 'csv', 'metavar': '<members names>', 'help': 'Complete name of functions that never returns. When checking for inconsistent-return-statements if a never returning function is called then it will be considered as an explicit return statement and no message will be printed.'}), ('suggest-join-with-non-empty-separator', {'default': True, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Let \'consider-using-join\' be raised when the separator to join on would be non-empty (resulting in expected fixes of the type: ``"- " + "\n- ".join(items)``)'}))

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._return_nodes: dict[str, list[nodes.Return]] = {}
        self._consider_using_with_stack = ConsiderUsingWithStack()
        self._init()
        self._never_returning_functions: set[str] = set()
        self._suggest_join_with_non_empty_separator: bool = False

    def _is_actual_elif(self, node: nodes.If | nodes.Try) -> bool:
        """Check if the given node is an actual elif.

        This is a problem we're having with the builtin ast module,
        which splits `elif` branches into a separate if statement.
        Unfortunately we need to know the exact type in certain
        cases.
        """
        pass

    def _check_simplifiable_if(self, node: nodes.If) -> None:
        """Check if the given if node can be simplified.

        The if statement can be reduced to a boolean expression
        in some cases. For instance, if there are two branches
        and both of them return a boolean value that depends on
        the result of the statement's test, then this can be reduced
        to `bool(test)` without losing any functionality.
        """
        pass
    visit_while = visit_try

    def _check_consider_using_min_max_builtin(self, node: nodes.If) -> None:
        """Check if the given if node can be refactored as a min/max python builtin."""
        pass

    def _check_stop_iteration_inside_generator(self, node: nodes.Raise) -> None:
        """Check if an exception of type StopIteration is raised inside a generator."""
        pass

    @staticmethod
    def _check_exception_inherit_from_stopiteration(exc: nodes.ClassDef | bases.Instance) -> bool:
        """Return True if the exception node in argument inherit from StopIteration."""
        pass

    def _check_raising_stopiteration_in_generator_next_call(self, node: nodes.Call) -> None:
        """Check if a StopIteration exception is raised by the call to next function.

        If the next value has a default value, then do not add message.

        :param node: Check to see if this Call node is a next function
        :type node: :class:`nodes.Call`
        """
        pass

    def _check_nested_blocks(self, node: NodesWithNestedBlocks) -> None:
        """Update and check the number of nested blocks."""
        pass

    @staticmethod
    def _duplicated_isinstance_types(node: nodes.BoolOp) -> dict[str, set[str]]:
        """Get the duplicated types from the underlying isinstance calls.

        :param nodes.BoolOp node: Node which should contain a bunch of isinstance calls.
        :returns: Dictionary of the comparison objects from the isinstance calls,
                  to duplicate values from consecutive calls.
        :rtype: dict
        """
        pass

    def _check_consider_merging_isinstance(self, node: nodes.BoolOp) -> None:
        """Check isinstance calls which can be merged together."""
        pass

    def _check_chained_comparison(self, node: nodes.BoolOp) -> None:
        """Check if there is any chained comparison in the expression.

        Add a refactoring message if a boolOp contains comparison like a < b and b < c,
        which can be chained as a < b < c.

        Care is taken to avoid simplifying a < b < c and b < d.
        """
        pass

    @staticmethod
    def _apply_boolean_simplification_rules(operator: str, values: list[nodes.NodeNG]) -> list[nodes.NodeNG]:
        """Removes irrelevant values or returns short-circuiting values.

        This function applies the following two rules:
        1) an OR expression with True in it will always be true, and the
           reverse for AND

        2) False values in OR expressions are only relevant if all values are
           false, and the reverse for AND
        """
        pass

    def _simplify_boolean_operation(self, bool_op: nodes.BoolOp) -> nodes.BoolOp:
        """Attempts to simplify a boolean operation.

        Recursively applies simplification on the operator terms,
        and keeps track of whether reductions have been made.
        """
        pass

    def _check_simplifiable_condition(self, node: nodes.BoolOp) -> None:
        """Check if a boolean condition can be simplified.

        Variables will not be simplified, even if the value can be inferred,
        and expressions like '3 + 4' will remain expanded.
        """
        pass

    def _check_use_list_literal(self, node: nodes.Call) -> None:
        """Check if empty list is created by using the literal []."""
        pass

    def _check_use_dict_literal(self, node: nodes.Call) -> None:
        """Check if dict is created by using the literal {}."""
        pass

    @staticmethod
    def _dict_literal_suggestion(node: nodes.Call) -> str:
        """Return a suggestion of reasonable length."""
        pass

    def _name_to_concatenate(self, node: nodes.NodeNG) -> str | None:
        """Try to extract the name used in a concatenation loop."""
        pass

    def _check_consider_using_join(self, aug_assign: nodes.AugAssign) -> None:
        """We start with the augmented assignment and work our way upwards.

        Names of variables for nodes if match successful:
        result = ''  # assign
        for number in ['1', '2', '3']  # for_loop
            result += number  # aug_assign
        """
        pass

    @staticmethod
    def _is_and_or_ternary(node: nodes.NodeNG | None) -> bool:
        """Returns true if node is 'condition and true_value or false_value' form.

        All of: condition, true_value and false_value should not be a complex boolean expression
        """
        pass

    def _check_consistent_returns(self, node: nodes.FunctionDef) -> None:
        """Check that all return statements inside a function are consistent.

        Return statements are consistent if:
            - all returns are explicit and if there is no implicit return;
            - all returns are empty and if there is, possibly, an implicit return.

        Args:
            node (nodes.FunctionDef): the function holding the return statements.
        """
        pass

    def _is_if_node_return_ended(self, node: nodes.If) -> bool:
        """Check if the If node ends with an explicit return statement.

        Args:
            node (nodes.If): If node to be checked.

        Returns:
            bool: True if the node ends with an explicit statement, False otherwise.
        """
        pass

    def _is_raise_node_return_ended(self, node: nodes.Raise) -> bool:
        """Check if the Raise node ends with an explicit return statement.

        Args:
            node (nodes.Raise): Raise node to be checked.

        Returns:
            bool: True if the node ends with an explicit statement, False otherwise.
        """
        pass

    def _is_node_return_ended(self, node: nodes.NodeNG) -> bool:
        """Check if the node ends with an explicit return statement.

        Args:
            node (nodes.NodeNG): node to be checked.

        Returns:
            bool: True if the node ends with an explicit statement, False otherwise.
        """
        pass

    @staticmethod
    def _has_return_in_siblings(node: nodes.NodeNG) -> bool:
        """Returns True if there is at least one return in the node's siblings."""
        pass

    def _is_function_def_never_returning(self, node: nodes.FunctionDef | astroid.BoundMethod) -> bool:
        """Return True if the function never returns, False otherwise.

        Args:
            node (nodes.FunctionDef or astroid.BoundMethod): function definition node to be analyzed.

        Returns:
            bool: True if the function never returns, False otherwise.
        """
        pass

    def _check_return_at_the_end(self, node: nodes.FunctionDef) -> None:
        """Check for presence of a *single* return statement at the end of a
        function.

        "return" or "return None" are useless because None is the
        default return type if they are missing.

        NOTE: produces a message only if there is a single return statement
        in the function body. Otherwise _check_consistent_returns() is called!
        Per its implementation and PEP8 we can have a "return None" at the end
        of the function body if there are other return statements before that!
        """
        pass

    def _check_unnecessary_dict_index_lookup(self, node: nodes.For | nodes.Comprehension) -> None:
        """Add message when accessing dict values by index lookup."""
        pass

    def _enumerate_with_start(self, node: nodes.For | nodes.Comprehension) -> tuple[bool, Confidence]:
        """Check presence of `start` kwarg or second argument to enumerate.

        For example:

        `enumerate([1,2,3], start=1)`
        `enumerate([1,2,3], 1)`

        If `start` is assigned to `0`, the default value, this is equivalent to
        not calling `enumerate` with start.
        """
        pass
