"""Checks for various exception related errors."""
from __future__ import annotations
import builtins
import inspect
from collections.abc import Generator
from typing import TYPE_CHECKING, Any
import astroid
from astroid import nodes, objects, util
from astroid.context import InferenceContext
from astroid.typing import InferenceResult, SuccessfulInferenceResult
from pylint import checkers
from pylint.checkers import utils
from pylint.interfaces import HIGH, INFERENCE
from pylint.typing import MessageDefinitionTuple
if TYPE_CHECKING:
    from pylint.lint import PyLinter

def _annotated_unpack_infer(stmt: nodes.NodeNG, context: InferenceContext | None=None) -> Generator[tuple[nodes.NodeNG, SuccessfulInferenceResult], None, None]:
    """Recursively generate nodes inferred by the given statement.

    If the inferred value is a list or a tuple, recurse on the elements.
    Returns an iterator which yields tuples in the format
    ('original node', 'inferred node').
    """
    if isinstance(stmt, (nodes.List, nodes.Tuple)):
        for elt in stmt.elts:
            yield from _annotated_unpack_infer(elt, context)
    else:
        inferred = safe_infer(stmt, context)
        if inferred:
            yield stmt, inferred

def _is_raising(body: list[nodes.NodeNG]) -> bool:
    """Return whether the given statement node raises an exception."""
    return any(isinstance(node, nodes.Raise) for node in body)
MSGS: dict[str, MessageDefinitionTuple] = {'E0701': ('Bad except clauses order (%s)', 'bad-except-order', "Used when except clauses are not in the correct order (from the more specific to the more generic). If you don't fix the order, some exceptions may not be caught by the most specific handler."), 'E0702': ('Raising %s while only classes or instances are allowed', 'raising-bad-type', 'Used when something which is neither a class nor an instance is raised (i.e. a `TypeError` will be raised).'), 'E0704': ('The raise statement is not inside an except clause', 'misplaced-bare-raise', 'Used when a bare raise is not used inside an except clause. This generates an error, since there are no active exceptions to be reraised. An exception to this rule is represented by a bare raise inside a finally clause, which might work, as long as an exception is raised inside the try block, but it is nevertheless a code smell that must not be relied upon.'), 'E0705': ('Exception cause set to something which is not an exception, nor None', 'bad-exception-cause', 'Used when using the syntax "raise ... from ...", where the exception cause is not an exception, nor None.', {'old_names': [('E0703', 'bad-exception-context')]}), 'E0710': ("Raising a new style class which doesn't inherit from BaseException", 'raising-non-exception', "Used when a new style class which doesn't inherit from BaseException is raised."), 'E0711': ('NotImplemented raised - should raise NotImplementedError', 'notimplemented-raised', 'Used when NotImplemented is raised instead of NotImplementedError'), 'E0712': ("Catching an exception which doesn't inherit from Exception: %s", 'catching-non-exception', "Used when a class which doesn't inherit from Exception is used as an exception in an except clause."), 'W0702': ('No exception type(s) specified', 'bare-except', 'A bare ``except:`` clause will catch ``SystemExit`` and ``KeyboardInterrupt`` exceptions, making it harder to interrupt a program with ``Control-C``, and can disguise other problems. If you want to catch all exceptions that signal program errors, use ``except Exception:`` (bare except is equivalent to ``except BaseException:``).'), 'W0718': ('Catching too general exception %s', 'broad-exception-caught', 'If you use a naked ``except Exception:`` clause, you might end up catching exceptions other than the ones you expect to catch. This can hide bugs or make it harder to debug programs when unrelated errors are hidden.', {'old_names': [('W0703', 'broad-except')]}), 'W0705': ('Catching previously caught exception type %s', 'duplicate-except', 'Used when an except catches a type that was already caught by a previous handler.'), 'W0706': ('The except handler raises immediately', 'try-except-raise', 'Used when an except handler uses raise as its first or only operator. This is useless because it raises back the exception immediately. Remove the raise operator or the entire try-except-raise block!'), 'W0707': ("Consider explicitly re-raising using %s'%s from %s'", 'raise-missing-from', "Python's exception chaining shows the traceback of the current exception, but also of the original exception. When you raise a new exception after another exception was caught it's likely that the second exception is a friendly re-wrapping of the first exception. In such cases `raise from` provides a better link between the two tracebacks in the final error."), 'W0711': ('Exception to catch is the result of a binary "%s" operation', 'binary-op-exception', 'Used when the exception to catch is of the form "except A or B:".  If intending to catch multiple, rewrite as "except (A, B):"'), 'W0715': ('Exception arguments suggest string formatting might be intended', 'raising-format-tuple', 'Used when passing multiple arguments to an exception constructor, the first of them a string literal containing what appears to be placeholders intended for formatting'), 'W0716': ('Invalid exception operation. %s', 'wrong-exception-operation', 'Used when an operation is done against an exception, but the operation is not valid for the exception in question. Usually emitted when having binary operations between exceptions in except handlers.'), 'W0719': ('Raising too general exception: %s', 'broad-exception-raised', 'Raising exceptions that are too generic force you to catch exceptions generically too. It will force you to use a naked ``except Exception:`` clause. You might then end up catching exceptions other than the ones you expect to catch. This can hide bugs or make it harder to debug programs when unrelated errors are hidden.')}

class BaseVisitor:
    """Base class for visitors defined in this module."""

    def __init__(self, checker: ExceptionsChecker, node: nodes.Raise) -> None:
        self._checker = checker
        self._node = node

    def visit_default(self, _: nodes.NodeNG) -> None:
        """Default implementation for all the nodes."""
        # This method is intentionally left empty as it's a default implementation
        # for nodes that don't require specific handling.

class ExceptionRaiseRefVisitor(BaseVisitor):
    """Visit references (anything that is not an AST leaf)."""

class ExceptionRaiseLeafVisitor(BaseVisitor):
    """Visitor for handling leaf kinds of a raise value."""
    visit_exceptioninstance = visit_instance

class ExceptionsChecker(checkers.BaseChecker):
    """Exception related checks."""
    name = 'exceptions'
    msgs = MSGS
    options = (('overgeneral-exceptions', {'default': ('builtins.BaseException', 'builtins.Exception'), 'type': 'csv', 'metavar': '<comma-separated class names>', 'help': 'Exceptions that will emit a warning when caught.'}),)

    def _check_bad_exception_cause(self, node: nodes.Raise) -> None:
        """Verify that the exception cause is properly set.

        An exception cause can be only `None` or an exception.
        """
        if node.cause:
            cause = safe_infer(node.cause)
            if cause:
                if isinstance(cause, astroid.Const) and cause.value is not None:
                    self.add_message('bad-exception-cause', node=node)
                elif (not isinstance(cause, astroid.Instance) or
                      not inherit_from_std_ex(cause)):
                    self.add_message('bad-exception-cause', node=node)

    @utils.only_required_for_messages('bare-except', 'broad-exception-caught', 'try-except-raise', 'binary-op-exception', 'bad-except-order', 'catching-non-exception', 'duplicate-except')
    def visit_trystar(self, node: nodes.TryStar) -> None:
        """Check for empty except*."""
        self._check_except_handlers(node)

    def visit_try(self, node: nodes.Try) -> None:
        """Check for empty except."""
        self._check_except_handlers(node)
