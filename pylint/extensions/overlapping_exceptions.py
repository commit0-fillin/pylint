"""Looks for overlapping exceptions."""
from __future__ import annotations
from typing import TYPE_CHECKING, Any
import astroid
from astroid import nodes, util
from pylint import checkers
from pylint.checkers import utils
from pylint.checkers.exceptions import _annotated_unpack_infer
if TYPE_CHECKING:
    from pylint.lint import PyLinter

class OverlappingExceptionsChecker(checkers.BaseChecker):
    """Checks for two or more exceptions in the same exception handler
    clause that are identical or parts of the same inheritance hierarchy.

    (i.e. overlapping).
    """
    name = 'overlap-except'
    msgs = {'W0714': ('Overlapping exceptions (%s)', 'overlapping-except', 'Used when exceptions in handler overlap or are identical')}
    options = ()

    @utils.only_required_for_messages('overlapping-except')
    def visit_try(self, node: nodes.Try) -> None:
        """Check for overlapping exceptions in except clauses."""
        exceptions = []
        for handler in node.handlers:
            if handler.type is None:
                # This is a bare except clause, which catches all exceptions
                # We can stop checking here as it will catch everything
                return
            
            if isinstance(handler.type, nodes.Tuple):
                current_exceptions = handler.type.elts
            else:
                current_exceptions = [handler.type]
            
            for exception in current_exceptions:
                exc_name = exception.as_string()
                for previous_exc in exceptions:
                    if utils.inherit_from_std_ex(exception, previous_exc):
                        self.add_message(
                            'overlapping-except',
                            node=handler,
                            args=f"{exc_name} is an ancestor class of {previous_exc.as_string()}"
                        )
                    elif utils.inherit_from_std_ex(previous_exc, exception):
                        self.add_message(
                            'overlapping-except',
                            node=handler,
                            args=f"{previous_exc.as_string()} is an ancestor class of {exc_name}"
                        )
                exceptions.extend(current_exceptions)
