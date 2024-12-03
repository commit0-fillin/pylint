"""Checker for use of Python logging."""
from __future__ import annotations
import string
from typing import TYPE_CHECKING, Literal
import astroid
from astroid import bases, nodes
from astroid.typing import InferenceResult
from pylint import checkers
from pylint.checkers import utils
from pylint.checkers.utils import infer_all
from pylint.typing import MessageDefinitionTuple
if TYPE_CHECKING:
    from pylint.lint import PyLinter
MSGS: dict[str, MessageDefinitionTuple] = {'W1201': ('Use %s formatting in logging functions', 'logging-not-lazy', 'Used when a logging statement has a call form of "logging.<logging method>(format_string % (format_args...))". Use another type of string formatting instead. You can use % formatting but leave interpolation to the logging function by passing the parameters as arguments. If logging-fstring-interpolation is disabled then you can use fstring formatting. If logging-format-interpolation is disabled then you can use str.format.'), 'W1202': ('Use %s formatting in logging functions', 'logging-format-interpolation', 'Used when a logging statement has a call form of "logging.<logging method>(format_string.format(format_args...))". Use another type of string formatting instead. You can use % formatting but leave interpolation to the logging function by passing the parameters as arguments. If logging-fstring-interpolation is disabled then you can use fstring formatting. If logging-not-lazy is disabled then you can use % formatting as normal.'), 'W1203': ('Use %s formatting in logging functions', 'logging-fstring-interpolation', 'Used when a logging statement has a call form of "logging.<logging method>(f"...")".Use another type of string formatting instead. You can use % formatting but leave interpolation to the logging function by passing the parameters as arguments. If logging-format-interpolation is disabled then you can use str.format. If logging-not-lazy is disabled then you can use % formatting as normal.'), 'E1200': ('Unsupported logging format character %r (%#02x) at index %d', 'logging-unsupported-format', 'Used when an unsupported format character is used in a logging statement format string.'), 'E1201': ('Logging format string ends in middle of conversion specifier', 'logging-format-truncated', 'Used when a logging statement format string terminates before the end of a conversion specifier.'), 'E1205': ('Too many arguments for logging format string', 'logging-too-many-args', 'Used when a logging format string is given too many arguments.'), 'E1206': ('Not enough arguments for logging format string', 'logging-too-few-args', 'Used when a logging format string is given too few arguments.')}
CHECKED_CONVENIENCE_FUNCTIONS = {'critical', 'debug', 'error', 'exception', 'fatal', 'info', 'warn', 'warning'}
MOST_COMMON_FORMATTING = frozenset(['%s', '%d', '%f', '%r'])

def is_method_call(func: bases.BoundMethod, types: tuple[str, ...]=(), methods: tuple[str, ...]=()) -> bool:
    """Determines if a BoundMethod node represents a method call.

    Args:
      func: The BoundMethod AST node to check.
      types: Optional sequence of caller type names to restrict check.
      methods: Optional sequence of method names to restrict check.

    Returns:
      true if the node represents a method call for the given type and
      method names, False otherwise.
    """
    if isinstance(func, bases.BoundMethod):
        if types and func.bound.name not in types:
            return False
        if methods and func.name not in methods:
            return False
        return True
    return False

class LoggingChecker(checkers.BaseChecker):
    """Checks use of the logging module."""
    name = 'logging'
    msgs = MSGS
    options = (('logging-modules', {'default': ('logging',), 'type': 'csv', 'metavar': '<comma separated list>', 'help': 'Logging modules to check that the string format arguments are in logging function parameter format.'}), ('logging-format-style', {'default': 'old', 'type': 'choice', 'metavar': '<old (%) or new ({)>', 'choices': ['old', 'new'], 'help': 'The type of string formatting that logging methods do. `old` means using % formatting, `new` is for `{}` formatting.'}))

    def visit_module(self, _: nodes.Module) -> None:
        """Clears any state left in this checker from last module checked."""
        self._logging_names = set()
        self._from_imports = {}
        self._std_logging_names = set()

    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        """Checks to see if a module uses a non-Python logging module."""
        if node.modname in self.linter.config.logging_modules:
            self._logging_names.update(
                [import_name.name for import_name in node.names]
            )
        self._from_imports[node.modname] = [n[0] for n in node.names]

    def visit_import(self, node: nodes.Import) -> None:
        """Checks to see if this module uses Python's built-in logging."""
        for name, _ in node.names:
            if name in self.linter.config.logging_modules:
                self._logging_names.add(name)
            else:
                self._std_logging_names.add(name)

    def visit_call(self, node: nodes.Call) -> None:
        """Checks calls to logging methods."""
        if isinstance(node.func, nodes.Attribute):
            self._check_log_method(node, node.func.attrname)
        elif isinstance(node.func, nodes.Name):
            self._check_log_method(node, node.func.name)

    def _check_log_method(self, node: nodes.Call, name: str) -> None:
        """Checks calls to logging.log(level, format, *format_args)."""
        if name in CHECKED_CONVENIENCE_FUNCTIONS:
            self._check_call_func(node)
            if len(node.args) >= 2:
                self._check_format_string(node, 1)
        elif name == 'log':
            self._check_call_func(node)
            if len(node.args) >= 3:
                self._check_format_string(node, 2)

    def _helper_string(self, node: nodes.Call) -> str:
        """Create a string that lists the valid types of formatting for this node."""
        valid_formats = []
        if not self.linter.is_message_enabled("logging-fstring-interpolation"):
            valid_formats.append("fstring")
        if not self.linter.is_message_enabled("logging-format-interpolation"):
            valid_formats.append("str.format()")
        if not self.linter.is_message_enabled("logging-not-lazy"):
            valid_formats.append("% formatting")
        
        if len(valid_formats) > 1:
            return f"Use {', '.join(valid_formats[:-1])} or {valid_formats[-1]}"
        elif len(valid_formats) == 1:
            return f"Use {valid_formats[0]}"
        else:
            return "Avoid string formatting in logging functions"

    @staticmethod
    def _is_operand_literal_str(operand: InferenceResult | None) -> bool:
        """Return True if the operand in argument is a literal string."""
        if isinstance(operand, nodes.Const):
            return isinstance(operand.value, str)
        return False

    @staticmethod
    def _is_node_explicit_str_concatenation(node: nodes.NodeNG) -> bool:
        """Return True if the node represents an explicitly concatenated string."""
        if isinstance(node, nodes.BinOp) and node.op == "+":
            left_operand = safe_infer(node.left)
            right_operand = safe_infer(node.right)
            return (LoggingChecker._is_operand_literal_str(left_operand) and
                    LoggingChecker._is_operand_literal_str(right_operand))
        return False

    def _check_call_func(self, node: nodes.Call) -> None:
        """Checks that function call is not format_string.format()."""
        if isinstance(node.func, nodes.Attribute):
            if node.func.attrname == "format":
                if self._is_operand_literal_str(safe_infer(node.func.expr)):
                    self.add_message(
                        "logging-format-interpolation",
                        node=node,
                        args=(self._helper_string(node),),
                    )
            elif (node.func.attrname in CHECKED_CONVENIENCE_FUNCTIONS or
                  node.func.attrname == "log"):
                if (len(node.args) >= 1 and
                    isinstance(node.args[0], nodes.JoinedStr)):
                    self.add_message(
                        "logging-fstring-interpolation",
                        node=node,
                        args=(self._helper_string(node),),
                    )

    def _check_format_string(self, node: nodes.Call, format_arg: Literal[0, 1]) -> None:
        """Checks that format string tokens match the supplied arguments.

        Args:
          node: AST node to be checked.
          format_arg: Index of the format string in the node arguments.
        """
        if len(node.args) <= format_arg:
            return
        format_string = node.args[format_arg]
        if isinstance(format_string, nodes.Const):
            if not isinstance(format_string.value, str):
                return
            try:
                required_keys, required_num_args, _, _ = parse_format_string(format_string.value)
            except UnsupportedFormatCharacter as exc:
                char = format_string.value[exc.index]
                self.add_message(
                    "logging-unsupported-format",
                    node=node,
                    args=(char, ord(char), exc.index),
                )
                return
            except IncompleteFormatString:
                self.add_message("logging-format-truncated", node=node)
                return
            if required_keys:
                # Keyword parameters are used for formatting
                keywords = [keyword.arg for keyword in node.keywords]
                if set(required_keys) <= set(keywords):
                    return
            supplied_args = len(node.args) - format_arg - 1
            if not required_keys and required_num_args == supplied_args:
                return
            if required_num_args != supplied_args:
                if supplied_args > required_num_args:
                    self.add_message("logging-too-many-args", node=node)
                else:
                    self.add_message("logging-too-few-args", node=node)
        elif isinstance(format_string, nodes.JoinedStr):
            self.add_message(
                "logging-fstring-interpolation",
                node=node,
                args=(self._helper_string(node),),
            )
        elif isinstance(format_string, nodes.BinOp):
            if self._is_node_explicit_str_concatenation(format_string):
                self.add_message(
                    "logging-not-lazy",
                    node=node,
                    args=(self._helper_string(node),),
                )

def is_complex_format_str(node: nodes.NodeNG) -> bool:
    """Return whether the node represents a string with complex formatting specs."""
    if isinstance(node, nodes.Const) and isinstance(node.value, str):
        try:
            format_specs = list(string.Formatter().parse(node.value))
            return any(spec[1] for spec in format_specs if spec[1] is not None)
        except ValueError:
            # Invalid format string
            return False
    return False

def _count_supplied_tokens(args: list[nodes.NodeNG]) -> int:
    """Counts the number of tokens in an args list.

    The Python log functions allow for special keyword arguments: func,
    exc_info and extra. To handle these cases correctly, we only count
    arguments that aren't keywords.

    Args:
      args: AST nodes that are arguments for a log format string.

    Returns:
      Number of AST nodes that aren't keywords.
    """
    return sum(1 for arg in args if not isinstance(arg, nodes.Keyword))

def str_formatting_in_f_string(node: nodes.JoinedStr) -> bool:
    """Determine whether the node represents an f-string with string formatting.

    For example: `f'Hello %s'`
    """
    for value in node.values:
        if isinstance(value, nodes.Const) and '%' in value.value:
            return True
    return False
