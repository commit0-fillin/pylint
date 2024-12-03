"""Checks for magic values instead of literals."""
from __future__ import annotations
from re import match as regex_match
from typing import TYPE_CHECKING
from astroid import nodes
from pylint.checkers import BaseChecker, utils
from pylint.interfaces import HIGH
if TYPE_CHECKING:
    from pylint.lint import PyLinter

class MagicValueChecker(BaseChecker):
    """Checks for constants in comparisons."""
    name = 'magic-value'
    msgs = {'R2004': ("Consider using a named constant or an enum instead of '%s'.", 'magic-value-comparison', 'Using named constants instead of magic values helps improve readability and maintainability of your code, try to avoid them in comparisons.')}
    options = (('valid-magic-values', {'default': (0, -1, 1, '', '__main__'), 'type': 'csv', 'metavar': '<argument names>', 'help': "List of valid magic values that `magic-value-compare` will not detect. Supports integers, floats, negative numbers, for empty string enter ``''``, for backslash values just use one backslash e.g \\n."}),)

    def __init__(self, linter: PyLinter) -> None:
        """Initialize checker instance."""
        super().__init__(linter=linter)
        self.valid_magic_vals: tuple[float | str, ...] = ()

    def _check_constants_comparison(self, node: nodes.Compare) -> None:
        """
        Magic values in any side of the comparison should be avoided,
        Detects comparisons that `comparison-of-constants` core checker cannot detect.
        """
        def is_magic_value(operand):
            return (
                isinstance(operand, nodes.Const)
                and operand.value not in self.valid_magic_vals
                and not isinstance(operand.value, bool)
                and operand.value is not None
            )

        for side in (node.left, *node.ops):
            if is_magic_value(side):
                self.add_message(
                    "magic-value-comparison",
                    node=node,
                    args=side.value,
                    confidence=HIGH,
                )
