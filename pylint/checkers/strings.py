"""Checker for string formatting operations."""
from __future__ import annotations
import collections
import re
import sys
import tokenize
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Literal
import astroid
from astroid import bases, nodes, util
from astroid.typing import SuccessfulInferenceResult
from pylint.checkers import BaseChecker, BaseRawFileChecker, BaseTokenChecker, utils
from pylint.checkers.utils import only_required_for_messages
from pylint.interfaces import HIGH
from pylint.typing import MessageDefinitionTuple
if TYPE_CHECKING:
    from pylint.lint import PyLinter
_AST_NODE_STR_TYPES = ('__builtin__.unicode', '__builtin__.str', 'builtins.str')
_PREFIXES = {'r', 'u', 'R', 'U', 'f', 'F', 'fr', 'Fr', 'fR', 'FR', 'rf', 'rF', 'Rf', 'RF', 'b', 'B', 'br', 'Br', 'bR', 'BR', 'rb', 'rB', 'Rb', 'RB'}
_PAREN_IGNORE_TOKEN_TYPES = (tokenize.NEWLINE, tokenize.NL, tokenize.COMMENT)
SINGLE_QUOTED_REGEX = re.compile(f"({'|'.join(_PREFIXES)})?'''")
DOUBLE_QUOTED_REGEX = re.compile(f'({'|'.join(_PREFIXES)})?"""')
QUOTE_DELIMITER_REGEX = re.compile(f"""({'|'.join(_PREFIXES)})?("|')""", re.DOTALL)
MSGS: dict[str, MessageDefinitionTuple] = {'E1300': ('Unsupported format character %r (%#02x) at index %d', 'bad-format-character', 'Used when an unsupported format character is used in a format string.'), 'E1301': ('Format string ends in middle of conversion specifier', 'truncated-format-string', 'Used when a format string terminates before the end of a conversion specifier.'), 'E1302': ('Mixing named and unnamed conversion specifiers in format string', 'mixed-format-string', "Used when a format string contains both named (e.g. '%(foo)d') and unnamed (e.g. '%d') conversion specifiers.  This is also used when a named conversion specifier contains * for the minimum field width and/or precision."), 'E1303': ('Expected mapping for format string, not %s', 'format-needs-mapping', 'Used when a format string that uses named conversion specifiers is used with an argument that is not a mapping.'), 'W1300': ('Format string dictionary key should be a string, not %s', 'bad-format-string-key', 'Used when a format string that uses named conversion specifiers is used with a dictionary whose keys are not all strings.'), 'W1301': ('Unused key %r in format string dictionary', 'unused-format-string-key', 'Used when a format string that uses named conversion specifiers is used with a dictionary that contains keys not required by the format string.'), 'E1304': ('Missing key %r in format string dictionary', 'missing-format-string-key', "Used when a format string that uses named conversion specifiers is used with a dictionary that doesn't contain all the keys required by the format string."), 'E1305': ('Too many arguments for format string', 'too-many-format-args', 'Used when a format string that uses unnamed conversion specifiers is given too many arguments.'), 'E1306': ('Not enough arguments for format string', 'too-few-format-args', 'Used when a format string that uses unnamed conversion specifiers is given too few arguments'), 'E1307': ('Argument %r does not match format type %r', 'bad-string-format-type', 'Used when a type required by format string is not suitable for actual argument type'), 'E1310': ('Suspicious argument in %s.%s call', 'bad-str-strip-call', 'The argument to a str.{l,r,}strip call contains a duplicate character,'), 'W1302': ('Invalid format string', 'bad-format-string', 'Used when a PEP 3101 format string is invalid.'), 'W1303': ('Missing keyword argument %r for format string', 'missing-format-argument-key', "Used when a PEP 3101 format string that uses named fields doesn't receive one or more required keywords."), 'W1304': ('Unused format argument %r', 'unused-format-string-argument', 'Used when a PEP 3101 format string that uses named fields is used with an argument that is not required by the format string.'), 'W1305': ('Format string contains both automatic field numbering and manual field specification', 'format-combined-specification', "Used when a PEP 3101 format string contains both automatic field numbering (e.g. '{}') and manual field specification (e.g. '{0}')."), 'W1306': ('Missing format attribute %r in format specifier %r', 'missing-format-attribute', "Used when a PEP 3101 format string uses an attribute specifier ({0.length}), but the argument passed for formatting doesn't have that attribute."), 'W1307': ('Using invalid lookup key %r in format specifier %r', 'invalid-format-index', "Used when a PEP 3101 format string uses a lookup specifier ({a[1]}), but the argument passed for formatting doesn't contain or doesn't have that key as an attribute."), 'W1308': ('Duplicate string formatting argument %r, consider passing as named argument', 'duplicate-string-formatting-argument', 'Used when we detect that a string formatting is repeating an argument instead of using named string arguments'), 'W1309': ('Using an f-string that does not have any interpolated variables', 'f-string-without-interpolation', 'Used when we detect an f-string that does not use any interpolation variables, in which case it can be either a normal string or a bug in the code.'), 'W1310': ('Using formatting for a string that does not have any interpolated variables', 'format-string-without-interpolation', 'Used when we detect a string that does not have any interpolation variables, in which case it can be either a normal string without formatting or a bug in the code.')}
OTHER_NODES = (nodes.Const, nodes.List, nodes.Lambda, nodes.FunctionDef, nodes.ListComp, nodes.SetComp, nodes.GeneratorExp)

def get_access_path(key: str | Literal[0], parts: list[tuple[bool, str]]) -> str:
    """Given a list of format specifiers, returns
    the final access path (e.g. a.b.c[0][1]).
    """
    path = str(key)
    for is_attribute, part in parts:
        if is_attribute:
            path += f".{part}"
        else:
            path += f"[{part}]"
    return path

class StringFormatChecker(BaseChecker):
    """Checks string formatting operations to ensure that the format string
    is valid and the arguments match the format string.
    """
    name = 'string'
    msgs = MSGS

    def _check_new_format(self, node: nodes.Call, func: bases.BoundMethod) -> None:
        """Check the new string formatting."""
        if isinstance(node.func, nodes.Attribute):
            format_string = next(func.infer()).value
        else:
            format_string = func.format_string

        try:
            fields, num_args, manual_pos_args = parse_format_method_string(format_string)
        except IncompleteFormatString:
            self.add_message('bad-format-string', node=node)
            return

        named_fields = [field[0] for field in fields if isinstance(field[0], str)]
        if num_args and manual_pos_args:
            self.add_message('format-combined-specification', node=node)

        args = node.args
        kwargs = []
        for keyword in node.keywords or []:
            if keyword.arg is None:
                args.extend(keyword.value.elts)
            else:
                kwargs.append(keyword)

        if not num_args and not named_fields:
            if args or kwargs:
                self.add_message('too-many-format-args', node=node)
            return

        check_args = num_args - manual_pos_args
        if len(args) > check_args:
            self.add_message('too-many-format-args', node=node)
        elif len(args) < check_args:
            self.add_message('too-few-format-args', node=node)

        for field, arg in zip(fields, args):
            if isinstance(field[0], int):
                self._check_new_format_specifiers(node, [field], {field[0]: arg})

        for keyword in kwargs:
            if keyword.arg in named_fields:
                self._check_new_format_specifiers(node, [f for f in fields if f[0] == keyword.arg], {keyword.arg: keyword.value})
            else:
                self.add_message('unused-format-string-argument', node=node, args=(keyword.arg,))

        for field in fields:
            if isinstance(field[0], str) and field[0] not in [kw.arg for kw in kwargs]:
                self.add_message('missing-format-argument-key', node=node, args=(field[0],))

    def _check_new_format_specifiers(self, node: nodes.Call, fields: list[tuple[str, list[tuple[bool, str]]]], named: dict[str, SuccessfulInferenceResult]) -> None:
        """Check attribute and index access in the format
        string ("{0.a}" and "{0[a]}").
        """
        for key, specifiers in fields:
            if not specifiers:
                continue

            if key in named:
                value = named[key]
                for is_attribute, specifier in specifiers:
                    if is_attribute:
                        if not hasattr(value, specifier):
                            self.add_message('missing-format-attribute', node=node, args=(specifier, get_access_path(key, specifiers)))
                        else:
                            value = getattr(value, specifier)
                    else:
                        if not hasattr(value, '__getitem__'):
                            self.add_message('invalid-format-index', node=node, args=(specifier, get_access_path(key, specifiers)))
                        else:
                            try:
                                value = value[specifier]
                            except (KeyError, IndexError):
                                self.add_message('invalid-format-index', node=node, args=(specifier, get_access_path(key, specifiers)))

class StringConstantChecker(BaseTokenChecker, BaseRawFileChecker):
    """Check string literals."""
    name = 'string'
    msgs = {'W1401': ("Anomalous backslash in string: '%s'. String constant might be missing an r prefix.", 'anomalous-backslash-in-string', 'Used when a backslash is in a literal string but not as an escape.'), 'W1402': ("Anomalous Unicode escape in byte string: '%s'. String constant might be missing an r or u prefix.", 'anomalous-unicode-escape-in-string', 'Used when an escape like \\u is encountered in a byte string where it has no effect.'), 'W1404': ('Implicit string concatenation found in %s', 'implicit-str-concat', 'String literals are implicitly concatenated in a literal iterable definition : maybe a comma is missing ?', {'old_names': [('W1403', 'implicit-str-concat-in-sequence')]}), 'W1405': ('Quote delimiter %s is inconsistent with the rest of the file', 'inconsistent-quotes', 'Quote delimiters are not used consistently throughout a module (with allowances made for avoiding unnecessary escaping).'), 'W1406': ('The u prefix for strings is no longer necessary in Python >=3.0', 'redundant-u-string-prefix', 'Used when we detect a string with a u prefix. These prefixes were necessary in Python 2 to indicate a string was Unicode, but since Python 3.0 strings are Unicode by default.')}
    options = (('check-str-concat-over-line-jumps', {'default': False, 'type': 'yn', 'metavar': '<y or n>', 'help': 'This flag controls whether the implicit-str-concat should generate a warning on implicit string concatenation in sequences defined over several lines.'}), ('check-quote-consistency', {'default': False, 'type': 'yn', 'metavar': '<y or n>', 'help': 'This flag controls whether inconsistent-quotes generates a warning when the character used as a quote delimiter is used inconsistently within a module.'}))
    ESCAPE_CHARACTERS = 'abfnrtvx\n\r\t\\\'"01234567'
    UNICODE_ESCAPE_CHARACTERS = 'uUN'

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self.string_tokens: dict[tuple[int, int], tuple[str, tokenize.TokenInfo | None]] = {}
        'Token position -> (token value, next token).'
        self._parenthesized_string_tokens: dict[tuple[int, int], bool] = {}

    def check_for_consistent_string_delimiters(self, tokens: Iterable[tokenize.TokenInfo]) -> None:
        """Adds a message for each string using inconsistent quote delimiters.

        Quote delimiters are used inconsistently if " and ' are mixed in a module's
        shortstrings without having done so to avoid escaping an internal quote
        character.

        Args:
          tokens: The tokens to be checked against for consistent usage.
        """
        string_tokens = [t for t in tokens if t.type == tokenize.STRING]
        if not string_tokens:
            return

        preferred_delimiter = _get_quote_delimiter(string_tokens[0].string)
        for token in string_tokens:
            delimiter = _get_quote_delimiter(token.string)
            if delimiter != preferred_delimiter and _is_quote_delimiter_chosen_freely(token.string):
                self.add_message('inconsistent-quotes', line=token.start[0], args=(delimiter,))

    def process_non_raw_string_token(self, prefix: str, string_body: str, start_row: int, string_start_col: int) -> None:
        """Check for bad escapes in a non-raw string.

        prefix: lowercase string of string prefix markers ('ur').
        string_body: the un-parsed body of the string, not including the quote
        marks.
        start_row: line number in the source.
        string_start_col: col number of the string start in the source.
        """
        for match in re.finditer(r'[^\\]\\(?P<char>[^\\])', string_body):
            char = match.group('char')
            if char not in self.ESCAPE_CHARACTERS:
                col_offset = string_start_col + match.start() + 1
                self.add_message('anomalous-backslash-in-string', line=start_row, col_offset=col_offset, args=(char,))

        if 'u' in prefix:
            for match in re.finditer(r'[^\\]\\(?P<char>[^uUN\\])', string_body):
                char = match.group('char')
                if char not in self.UNICODE_ESCAPE_CHARACTERS:
                    col_offset = string_start_col + match.start() + 1
                    self.add_message('anomalous-unicode-escape-in-string', line=start_row, col_offset=col_offset, args=(char,))

    def _detect_u_string_prefix(self, node: nodes.Const) -> None:
        """Check whether strings include a 'u' prefix like u'String'."""
        if isinstance(node.value, str) and node.raw_string:
            prefix = node.raw_string.split("'")[0].lower()
            if 'u' in prefix:
                self.add_message('redundant-u-string-prefix', node=node)

def str_eval(token: str) -> str:
    """Mostly replicate `ast.literal_eval(token)` manually to avoid any performance hit.

    This supports f-strings, contrary to `ast.literal_eval`.
    We have to support all string literal notations:
    https://docs.python.org/3/reference/lexical_analysis.html#string-and-bytes-literals
    """
    prefix = ''
    quote = ''
    for i, char in enumerate(token):
        if char in "'\"":
            quote = char
            token = token[i:]
            break
        prefix += char.lower()

    if 'f' in prefix:
        return token  # Don't evaluate f-strings

    if quote * 3 == token[:3]:
        end = token.rindex(quote * 3)
        token = token[3:end]
    else:
        end = token.rindex(quote)
        token = token[1:end]

    if 'r' in prefix:
        return token  # Don't evaluate raw strings

    try:
        return token.encode('ascii').decode('unicode-escape')
    except UnicodeDecodeError:
        return token

def _is_long_string(string_token: str) -> bool:
    """Is this string token a "longstring" (is it triple-quoted)?

    Long strings are triple-quoted as defined in
    https://docs.python.org/3/reference/lexical_analysis.html#string-and-bytes-literals

    This function only checks characters up through the open quotes.  Because it's meant
    to be applied only to tokens that represent string literals, it doesn't bother to
    check for close-quotes (demonstrating that the literal is a well-formed string).

    Args:
        string_token: The string token to be parsed.

    Returns:
        A boolean representing whether this token matches a longstring
        regex.
    """
    return bool(SINGLE_QUOTED_REGEX.match(string_token) or DOUBLE_QUOTED_REGEX.match(string_token))

def _get_quote_delimiter(string_token: str) -> str:
    """Returns the quote character used to delimit this token string.

    This function checks whether the token is a well-formed string.

    Args:
        string_token: The token to be parsed.

    Returns:
        A string containing solely the first quote delimiter character in the
        given string.

    Raises:
      ValueError: No quote delimiter characters are present.
    """
    match = QUOTE_DELIMITER_REGEX.match(string_token)
    if not match:
        raise ValueError("String token is not a well-formed string.")
    return match.group(2)

def _is_quote_delimiter_chosen_freely(string_token: str) -> bool:
    """Was there a non-awkward option for the quote delimiter?

    Args:
        string_token: The quoted string whose delimiters are to be checked.

    Returns:
        Whether there was a choice in this token's quote character that would
        not have involved backslash-escaping an interior quote character.  Long
        strings are excepted from this analysis under the assumption that their
        quote characters are set by policy.
    """
    if _is_long_string(string_token):
        return False

    delimiter = _get_quote_delimiter(string_token)
    other_delimiter = '"' if delimiter == "'" else "'"

    string_body = string_token[1:-1]  # Remove the quotes
    return other_delimiter not in string_body or (
        other_delimiter in string_body and delimiter in string_body
    )
