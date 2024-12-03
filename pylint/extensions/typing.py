from __future__ import annotations
from typing import TYPE_CHECKING, NamedTuple
import astroid.bases
from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.checkers.utils import in_type_checking_block, is_node_in_type_annotation_context, is_postponed_evaluation_enabled, only_required_for_messages, safe_infer
from pylint.constants import TYPING_NORETURN
from pylint.interfaces import HIGH, INFERENCE
if TYPE_CHECKING:
    from pylint.lint import PyLinter

class TypingAlias(NamedTuple):
    name: str
    name_collision: bool
DEPRECATED_TYPING_ALIASES: dict[str, TypingAlias] = {'typing.Tuple': TypingAlias('tuple', False), 'typing.List': TypingAlias('list', False), 'typing.Dict': TypingAlias('dict', False), 'typing.Set': TypingAlias('set', False), 'typing.FrozenSet': TypingAlias('frozenset', False), 'typing.Type': TypingAlias('type', False), 'typing.Deque': TypingAlias('collections.deque', True), 'typing.DefaultDict': TypingAlias('collections.defaultdict', True), 'typing.OrderedDict': TypingAlias('collections.OrderedDict', True), 'typing.Counter': TypingAlias('collections.Counter', True), 'typing.ChainMap': TypingAlias('collections.ChainMap', True), 'typing.Awaitable': TypingAlias('collections.abc.Awaitable', True), 'typing.Coroutine': TypingAlias('collections.abc.Coroutine', True), 'typing.AsyncIterable': TypingAlias('collections.abc.AsyncIterable', True), 'typing.AsyncIterator': TypingAlias('collections.abc.AsyncIterator', True), 'typing.AsyncGenerator': TypingAlias('collections.abc.AsyncGenerator', True), 'typing.Iterable': TypingAlias('collections.abc.Iterable', True), 'typing.Iterator': TypingAlias('collections.abc.Iterator', True), 'typing.Generator': TypingAlias('collections.abc.Generator', True), 'typing.Reversible': TypingAlias('collections.abc.Reversible', True), 'typing.Container': TypingAlias('collections.abc.Container', True), 'typing.Collection': TypingAlias('collections.abc.Collection', True), 'typing.Callable': TypingAlias('collections.abc.Callable', True), 'typing.AbstractSet': TypingAlias('collections.abc.Set', False), 'typing.MutableSet': TypingAlias('collections.abc.MutableSet', True), 'typing.Mapping': TypingAlias('collections.abc.Mapping', True), 'typing.MutableMapping': TypingAlias('collections.abc.MutableMapping', True), 'typing.Sequence': TypingAlias('collections.abc.Sequence', True), 'typing.MutableSequence': TypingAlias('collections.abc.MutableSequence', True), 'typing.ByteString': TypingAlias('collections.abc.ByteString', True), 'typing.MappingView': TypingAlias('collections.abc.MappingView', True), 'typing.KeysView': TypingAlias('collections.abc.KeysView', True), 'typing.ItemsView': TypingAlias('collections.abc.ItemsView', True), 'typing.ValuesView': TypingAlias('collections.abc.ValuesView', True), 'typing.ContextManager': TypingAlias('contextlib.AbstractContextManager', False), 'typing.AsyncContextManager': TypingAlias('contextlib.AbstractAsyncContextManager', False), 'typing.Pattern': TypingAlias('re.Pattern', True), 'typing.Match': TypingAlias('re.Match', True), 'typing.Hashable': TypingAlias('collections.abc.Hashable', True), 'typing.Sized': TypingAlias('collections.abc.Sized', True)}
ALIAS_NAMES = frozenset((key.split('.')[1] for key in DEPRECATED_TYPING_ALIASES))
UNION_NAMES = ('Optional', 'Union')

class DeprecatedTypingAliasMsg(NamedTuple):
    node: nodes.Name | nodes.Attribute
    qname: str
    alias: str
    parent_subscript: bool = False

class TypingChecker(BaseChecker):
    """Find issue specifically related to type annotations."""
    name = 'typing'
    msgs = {'W6001': ("'%s' is deprecated, use '%s' instead", 'deprecated-typing-alias', 'Emitted when a deprecated typing alias is used.'), 'R6002': ("'%s' will be deprecated with PY39, consider using '%s' instead%s", 'consider-using-alias', "Only emitted if 'runtime-typing=no' and a deprecated typing alias is used in a type annotation context in Python 3.7 or 3.8."), 'R6003': ("Consider using alternative Union syntax instead of '%s'%s", 'consider-alternative-union-syntax', "Emitted when 'typing.Union' or 'typing.Optional' is used instead of the alternative Union syntax 'int | None'."), 'E6004': ("'NoReturn' inside compound types is broken in 3.7.0 / 3.7.1", 'broken-noreturn', "``typing.NoReturn`` inside compound types is broken in Python 3.7.0 and 3.7.1. If not dependent on runtime introspection, use string annotation instead. E.g. ``Callable[..., 'NoReturn']``. https://bugs.python.org/issue34921"), 'E6005': ("'collections.abc.Callable' inside Optional and Union is broken in 3.9.0 / 3.9.1 (use 'typing.Callable' instead)", 'broken-collections-callable', '``collections.abc.Callable`` inside Optional and Union is broken in Python 3.9.0 and 3.9.1. Use ``typing.Callable`` for these cases instead. https://bugs.python.org/issue42965'), 'R6006': ('Type `%s` is used more than once in union type annotation. Remove redundant typehints.', 'redundant-typehint-argument', 'Duplicated type arguments will be skipped by `mypy` tool, therefore should be removed to avoid confusion.')}
    options = (('runtime-typing', {'default': True, 'type': 'yn', 'metavar': '<y or n>', 'help': "Set to ``no`` if the app / library does **NOT** need to support runtime introspection of type annotations. If you use type annotations **exclusively** for type checking of an application, you're probably fine. For libraries, evaluate if some users want to access the type hints at runtime first, e.g., through ``typing.get_type_hints``. Applies to Python versions 3.7 - 3.9"}),)
    _should_check_typing_alias: bool
    'The use of type aliases (PEP 585) requires Python 3.9\n    or Python 3.7+ with postponed evaluation.\n    '
    _should_check_alternative_union_syntax: bool
    'The use of alternative union syntax (PEP 604) requires Python 3.10\n    or Python 3.7+ with postponed evaluation.\n    '

    def __init__(self, linter: PyLinter) -> None:
        """Initialize checker instance."""
        super().__init__(linter=linter)
        self._found_broken_callable_location: bool = False
        self._alias_name_collisions: set[str] = set()
        self._deprecated_typing_alias_msgs: list[DeprecatedTypingAliasMsg] = []
        self._consider_using_alias_msgs: list[DeprecatedTypingAliasMsg] = []

    def _msg_postponed_eval_hint(self, node: nodes.NodeNG) -> str:
        """Message hint if postponed evaluation isn't enabled."""
        return "" if is_postponed_evaluation_enabled(node) else " (Requires Python 3.7+ with postponed evaluation)"

    def _check_for_alternative_union_syntax(self, node: nodes.Name | nodes.Attribute, name: str) -> None:
        """Check if alternative union syntax could be used.

        Requires
        - Python 3.10
        - OR: Python 3.7+ with postponed evaluation in
              a type annotation context
        """
        if not self._should_check_alternative_union_syntax:
            return

        if name not in UNION_NAMES:
            return

        if not is_node_in_type_annotation_context(node):
            return

        hint = self._msg_postponed_eval_hint(node)
        self.add_message("consider-alternative-union-syntax", node=node, args=(name, hint))

    def _check_for_typing_alias(self, node: nodes.Name | nodes.Attribute) -> None:
        """Check if typing alias is deprecated or could be replaced.

        Requires
        - Python 3.9
        - OR: Python 3.7+ with postponed evaluation in
              a type annotation context

        For Python 3.7+: Only emit message if change doesn't create
            any name collisions, only ever used in a type annotation
            context, and can safely be replaced.
        """
        if not self._should_check_typing_alias:
            return

        if isinstance(node, nodes.Name):
            name = node.name
        else:
            name = node.attrname

        if name not in ALIAS_NAMES:
            return

        inferred = safe_infer(node)
        if not inferred:
            return

        qname = inferred.qname()
        if qname not in DEPRECATED_TYPING_ALIASES:
            return

        alias = DEPRECATED_TYPING_ALIASES[qname]
        if alias.name_collision:
            self._alias_name_collisions.add(alias.name)

        parent_subscript = isinstance(node.parent, nodes.Subscript)
        msg = DeprecatedTypingAliasMsg(node, qname, alias.name, parent_subscript)

        if self.linter.is_message_enabled("deprecated-typing-alias"):
            self.add_message(
                "deprecated-typing-alias",
                node=node,
                args=(qname, alias.name),
                confidence=INFERENCE,
            )
        elif self.linter.is_message_enabled("consider-using-alias"):
            self._consider_using_alias_msgs.append(msg)

    @only_required_for_messages('consider-using-alias', 'deprecated-typing-alias')
    def leave_module(self, node: nodes.Module) -> None:
        """After parsing of module is complete, add messages for
        'consider-using-alias' check.

        Make sure results are safe to recommend / collision free.
        """
        pass

    def _check_broken_noreturn(self, node: nodes.Name | nodes.Attribute) -> None:
        """Check for 'NoReturn' inside compound types."""
        if not isinstance(node.parent, (nodes.Subscript, nodes.BinOp)):
            return

        inferred = safe_infer(node)
        if not inferred or inferred.qname() not in TYPING_NORETURN:
            return

        self.add_message("broken-noreturn", node=node)

    def _check_broken_callable(self, node: nodes.Name | nodes.Attribute) -> None:
        """Check for 'collections.abc.Callable' inside Optional and Union."""
        if self._found_broken_callable_location:
            return

        if not self._broken_callable_location(node):
            return

        inferred = safe_infer(node)
        if not inferred or inferred.qname() != "collections.abc.Callable":
            return

        self.add_message("broken-collections-callable", node=node)
        self._found_broken_callable_location = True

    def _broken_callable_location(self, node: nodes.Name | nodes.Attribute) -> bool:
        """Check if node would be a broken location for collections.abc.Callable."""
        parent = node.parent
        if isinstance(parent, nodes.Subscript):
            parent = parent.parent

        if not isinstance(parent, nodes.Call):
            return False

        inferred = safe_infer(parent.func)
        if not inferred:
            return False

        return inferred.qname() in ("typing.Optional", "typing.Union")
