"""Unicode and some other ASCII characters can be used to create programs that run
much different compared to what a human reader would expect from them.

PEP 672 lists some examples.
See: https://www.python.org/dev/peps/pep-0672/

The following checkers are intended to make users are aware of these issues.
"""
from __future__ import annotations
import codecs
import contextlib
import io
import re
from collections import OrderedDict
from collections.abc import Iterable
from functools import lru_cache
from tokenize import detect_encoding
from typing import NamedTuple, TypeVar
from astroid import nodes
import pylint.interfaces
import pylint.lint
from pylint import checkers
_StrLike = TypeVar('_StrLike', str, bytes)
BIDI_UNICODE = ['\u202a', '\u202b', '\u202c', '\u202d', '\u202e', '\u2066', '\u2067', '\u2068', '\u2069', '\u200f']

class _BadChar(NamedTuple):
    """Representation of an ASCII char considered bad."""
    name: str
    unescaped: str
    escaped: str
    code: str
    help_text: str

    def description(self) -> str:
        """Used for the detailed error message description."""
        return f"Found '{self.name}' character (escaped as '{self.escaped}')"

    def human_code(self) -> str:
        """Used to generate the human readable error message."""
        return f"bad-ascii-{self.name}"
BAD_CHARS = [_BadChar('backspace', '\x08', '\\b', 'E2510', 'Moves the cursor back, so the character after it will overwrite the character before.'), _BadChar('carriage-return', '\r', '\\r', 'E2511', 'Moves the cursor to the start of line, subsequent characters overwrite the start of the line.'), _BadChar('sub', '\x1a', '\\x1A', 'E2512', 'Ctrl+Z "End of text" on Windows. Some programs (such as type) ignore the rest of the file after it.'), _BadChar('esc', '\x1b', '\\x1B', 'E2513', 'Commonly initiates escape codes which allow arbitrary control of the terminal.'), _BadChar('nul', '\x00', '\\0', 'E2514', 'Mostly end of input for python.'), _BadChar('zero-width-space', '\u200b', '\\u200B', 'E2515', 'Invisible space character could hide real code execution.')]
BAD_ASCII_SEARCH_DICT = {char.unescaped: char for char in BAD_CHARS}

def _line_length(line: _StrLike, codec: str) -> int:
    """Get the length of a string like line as displayed in an editor."""
    if isinstance(line, bytes):
        return len(line.decode(codec))
    return len(line)

def _map_positions_to_result(line: _StrLike, search_dict: dict[_StrLike, _BadChar], new_line: _StrLike, byte_str_length: int=1) -> dict[int, _BadChar]:
    """Get all occurrences of search dict keys within line.

    Ignores Windows end of line and can handle bytes as well as string.
    Also takes care of encodings for which the length of an encoded code point does not
    default to 8 Bit.
    """
    result = {}
    for key, value in search_dict.items():
        start = 0
        while True:
            pos = line.find(key, start)
            if pos == -1:
                break
            result[pos // byte_str_length] = value
            start = pos + len(key)
    return result
UNICODE_BOMS = {'utf-8': codecs.BOM_UTF8, 'utf-16': codecs.BOM_UTF16, 'utf-32': codecs.BOM_UTF32, 'utf-16le': codecs.BOM_UTF16_LE, 'utf-16be': codecs.BOM_UTF16_BE, 'utf-32le': codecs.BOM_UTF32_LE, 'utf-32be': codecs.BOM_UTF32_BE}
BOM_SORTED_TO_CODEC = OrderedDict(((UNICODE_BOMS[codec], codec) for codec in ('utf-32le', 'utf-32be', 'utf-8', 'utf-16le', 'utf-16be')))
UTF_NAME_REGEX_COMPILED = re.compile('utf[ -]?(8|16|32)[ -]?(le|be|)?(sig)?', flags=re.IGNORECASE)

def _normalize_codec_name(codec: str) -> str:
    """Make sure the codec name is always given as defined in the BOM dict."""
    match = UTF_NAME_REGEX_COMPILED.match(codec)
    if match:
        base = match.group(1)
        endian = match.group(2)
        return f"utf-{base}{endian.lower()}".rstrip('-')
    return codec.lower()

def _remove_bom(encoded: bytes, encoding: str) -> bytes:
    """Remove the bom if given from a line."""
    bom = UNICODE_BOMS.get(encoding)
    if bom and encoded.startswith(bom):
        return encoded[len(bom):]
    return encoded

def _encode_without_bom(string: str, encoding: str) -> bytes:
    """Encode a string but remove the BOM."""
    encoded = string.encode(encoding)
    return _remove_bom(encoded, encoding)

def _byte_to_str_length(codec: str) -> int:
    """Return how many byte are usually(!) a character point."""
    if codec.startswith('utf-16'):
        return 2
    if codec.startswith('utf-32'):
        return 4
    return 1

@lru_cache(maxsize=1000)
def _cached_encode_search(string: str, encoding: str) -> bytes:
    """A cached version of encode used for search pattern."""
    return string.encode(encoding)

def _fix_utf16_32_line_stream(steam: Iterable[bytes], codec: str) -> Iterable[bytes]:
    """Handle line ending for UTF16 and UTF32 correctly.

    Currently, Python simply strips the required zeros after \\n after the
    line ending. Leading to lines that can't be decoded properly
    """
    byte_length = _byte_to_str_length(codec)
    if byte_length == 1:
        yield from steam
    else:
        for line in steam:
            yield line + b'\x00' * (byte_length - 1)

def extract_codec_from_bom(first_line: bytes) -> str:
    """Try to extract the codec (unicode only) by checking for the BOM.

    For details about BOM see https://unicode.org/faq/utf_bom.html#BOM

    Args:
        first_line: the first line of a file

    Returns:
        a codec name

    Raises:
        ValueError: if no codec was found
    """
    for bom, codec in BOM_SORTED_TO_CODEC.items():
        if first_line.startswith(bom):
            return codec
    raise ValueError("No BOM found")

class UnicodeChecker(checkers.BaseRawFileChecker):
    """Check characters that could be used to hide bad code to humans.

    This includes:

    - Bidirectional Unicode (see https://trojansource.codes/)

    - Bad ASCII characters (see PEP672)

        If a programmer requires to use such a character they should use the escaped
        version, that is also much easier to read and does not depend on the editor used.

    The Checker also includes a check that UTF-16 and UTF-32 are not used to encode
    Python files.

    At the time of writing Python supported only UTF-8. See
    https://stackoverflow.com/questions/69897842/ and https://bugs.python.org/issue1503789
    for background.
    """
    name = 'unicode_checker'
    msgs = {'E2501': ("UTF-16 and UTF-32 aren't backward compatible. Use UTF-8 instead", 'invalid-unicode-codec', 'For compatibility use UTF-8 instead of UTF-16/UTF-32. See also https://bugs.python.org/issue1503789 for a history of this issue. And https://softwareengineering.stackexchange.com/questions/102205/ for some possible problems when using UTF-16 for instance.'), 'E2502': ('Contains control characters that can permit obfuscated code executed differently than displayed', 'bidirectional-unicode', 'bidirectional unicode are typically not displayed characters required to display right-to-left (RTL) script (i.e. Chinese, Japanese, Arabic, Hebrew, ...) correctly. So can you trust this code? Are you sure it displayed correctly in all editors? If you did not write it or your language is not RTL, remove the special characters, as they could be used to trick you into executing code, that does something else than what it looks like.\nMore Information:\nhttps://en.wikipedia.org/wiki/Bidirectional_text\nhttps://trojansource.codes/'), 'C2503': ('PEP8 recommends UTF-8 as encoding for Python files', 'bad-file-encoding', 'PEP8 recommends UTF-8 default encoding for Python files. See https://peps.python.org/pep-0008/#source-file-encoding'), **{bad_char.code: (bad_char.description(), bad_char.human_code(), bad_char.help_text) for bad_char in BAD_CHARS}}

    @classmethod
    def _find_line_matches(cls, line: bytes, codec: str) -> dict[int, _BadChar]:
        """Find all matches of BAD_CHARS within line.

        Args:
            line: the input
            codec: that will be used to convert line/or search string into

        Return:
            A dictionary with the column offset and the BadASCIIChar
        """
        search_dict = {_cached_encode_search(char.unescaped, codec): char for char in BAD_CHARS}
        return _map_positions_to_result(line, search_dict, line, _byte_to_str_length(codec))

    @staticmethod
    def _determine_codec(stream: io.BytesIO) -> tuple[str, int]:
        """Determine the codec from the given stream.

        first tries https://www.python.org/dev/peps/pep-0263/
        and if this fails also checks for BOMs of UTF-16 and UTF-32
        to be future-proof.

        Args:
            stream: The byte stream to analyse

        Returns: A tuple consisting of:
                  - normalized codec name
                  - the line in which the codec was found

        Raises:
            SyntaxError: if failing to detect codec
        """
        try:
            encoding, lines = detect_encoding(stream.readline)
            return _normalize_codec_name(encoding), lines
        except SyntaxError:
            stream.seek(0)
            first_line = stream.read(4)
            try:
                codec = extract_codec_from_bom(first_line)
                return _normalize_codec_name(codec), 1
            except ValueError as e:
                raise SyntaxError("Failed to detect encoding") from e

    def _check_codec(self, codec: str, codec_definition_line: int) -> None:
        """Check validity of the codec."""
        if codec.startswith(('utf-16', 'utf-32')):
            self.add_message('invalid-unicode-codec', line=codec_definition_line)
        elif codec != 'utf-8':
            self.add_message('bad-file-encoding', line=codec_definition_line)

    def _check_invalid_chars(self, line: bytes, lineno: int, codec: str) -> None:
        """Look for chars considered bad."""
        for col, bad_char in self._find_line_matches(line, codec).items():
            self.add_message(bad_char.code, line=lineno, col_offset=col, args=(bad_char.unescaped, bad_char.escaped))

    def _check_bidi_chars(self, line: bytes, lineno: int, codec: str) -> None:
        """Look for Bidirectional Unicode, if we use unicode."""
        if codec.startswith('utf'):
            decoded_line = line.decode(codec)
            for col, char in enumerate(decoded_line):
                if char in BIDI_UNICODE:
                    self.add_message('bidirectional-unicode', line=lineno, col_offset=col)

    def process_module(self, node: nodes.Module) -> None:
        """Perform the actual check by checking module stream."""
        with node.stream() as stream:
            try:
                codec, codec_definition_line = self._determine_codec(stream)
            except SyntaxError:
                self.add_message('invalid-unicode-codec', line=1)
                return

            self._check_codec(codec, codec_definition_line)

            stream.seek(0)
            for lineno, line in enumerate(_fix_utf16_32_line_stream(stream, codec), start=1):
                self._check_invalid_chars(line, lineno, codec)
                self._check_bidi_chars(line, lineno, codec)
