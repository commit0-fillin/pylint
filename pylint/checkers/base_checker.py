from __future__ import annotations
import abc
import functools
from collections.abc import Iterable, Sequence
from inspect import cleandoc
from tokenize import TokenInfo
from typing import TYPE_CHECKING, Any
from astroid import nodes
from pylint.config.arguments_provider import _ArgumentsProvider
from pylint.constants import _MSG_ORDER, MAIN_CHECKER_NAME, WarningScope
from pylint.exceptions import InvalidMessageError
from pylint.interfaces import Confidence
from pylint.message.message_definition import MessageDefinition
from pylint.typing import ExtraMessageOptions, MessageDefinitionTuple, OptionDict, Options, ReportsCallable
from pylint.utils import get_rst_section, get_rst_title
if TYPE_CHECKING:
    from pylint.lint import PyLinter

@functools.total_ordering
class BaseChecker(_ArgumentsProvider):
    name: str = ''
    options: Options = ()
    msgs: dict[str, MessageDefinitionTuple] = {}
    reports: tuple[tuple[str, str, ReportsCallable], ...] = ()
    enabled: bool = True

    def __init__(self, linter: PyLinter) -> None:
        """Checker instances should have the linter as argument."""
        if self.name is not None:
            self.name = self.name.lower()
        self.linter = linter
        _ArgumentsProvider.__init__(self, linter)

    def __gt__(self, other: Any) -> bool:
        """Permits sorting checkers for stable doc and tests.

        The main checker is always the first one, then builtin checkers in alphabetical
        order, then extension checkers in alphabetical order.
        """
        if not isinstance(other, BaseChecker):
            return False
        if self.name == MAIN_CHECKER_NAME:
            return False
        if other.name == MAIN_CHECKER_NAME:
            return True
        self_is_builtin = type(self).__module__.startswith('pylint.checkers')
        if self_is_builtin ^ type(other).__module__.startswith('pylint.checkers'):
            return not self_is_builtin
        return self.name > other.name

    def __eq__(self, other: object) -> bool:
        """Permit to assert Checkers are equal."""
        if not isinstance(other, BaseChecker):
            return False
        return f'{self.name}{self.msgs}' == f'{other.name}{other.msgs}'

    def __hash__(self) -> int:
        """Make Checker hashable."""
        return hash(f'{self.name}{self.msgs}')

    def __repr__(self) -> str:
        status = 'Checker' if self.enabled else 'Disabled checker'
        msgs = "', '".join(self.msgs.keys())
        return f"{status} '{self.name}' (responsible for '{msgs}')"

    def __str__(self) -> str:
        """This might be incomplete because multiple classes inheriting BaseChecker
        can have the same name.

        See: MessageHandlerMixIn.get_full_documentation()
        """
        return self.get_full_documentation(msgs=self.msgs, options=self._options_and_values(), reports=self.reports)

    def check_consistency(self) -> None:
        """Check the consistency of msgid.

        msg ids for a checker should be a string of len 4, where the two first
        characters are the checker id and the two last the msg id in this
        checker.

        :raises InvalidMessageError: If the checker id in the messages are not
        always the same.
        """
        checker_id = None
        for msgid, _ in self.msgs.items():
            if checker_id is None:
                checker_id = msgid[:2]
            elif msgid[:2] != checker_id:
                raise InvalidMessageError(
                    f"Inconsistent checker id in messages: {msgid[:2]} != {checker_id}"
                )

    def open(self) -> None:
        """Called before visiting project (i.e. set of modules)."""
        # This method is intentionally left empty as it's meant to be
        # overridden by subclasses if needed.

    def close(self) -> None:
        """Called after visiting project (i.e set of modules)."""
        # This method is intentionally left empty as it's meant to be
        # overridden by subclasses if needed.

class BaseTokenChecker(BaseChecker):
    """Base class for checkers that want to have access to the token stream."""

    @abc.abstractmethod
    def process_tokens(self, tokens: list[TokenInfo]) -> None:
        """Should be overridden by subclasses."""
        raise NotImplementedError("This method must be overridden in derived classes.")

class BaseRawFileChecker(BaseChecker):
    """Base class for checkers which need to parse the raw file."""

    @abc.abstractmethod
    def process_module(self, node: nodes.Module) -> None:
        """Process a module.

        The module's content is accessible via ``astroid.stream``
        """
        raise NotImplementedError("This method must be overridden in derived classes.")
