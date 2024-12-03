"""Plain text reporters:.

:text: the default one grouping messages by module
:colorized: an ANSI colorized text reporter
"""
from __future__ import annotations
import os
import re
import sys
import warnings
from dataclasses import asdict, fields
from typing import TYPE_CHECKING, Dict, NamedTuple, TextIO
from pylint.message import Message
from pylint.reporters import BaseReporter
from pylint.reporters.ureports.text_writer import TextWriter
if TYPE_CHECKING:
    from pylint.lint import PyLinter
    from pylint.reporters.ureports.nodes import Section

class MessageStyle(NamedTuple):
    """Styling of a message."""
    color: str | None
    'The color name (see `ANSI_COLORS` for available values)\n    or the color number when 256 colors are available.\n    '
    style: tuple[str, ...] = ()
    'Tuple of style strings (see `ANSI_COLORS` for available values).'

    def __get_ansi_code(self) -> str:
        """Return ANSI escape code corresponding to color and style.

        :raise KeyError: if a nonexistent color or style identifier is given

        :return: the built escape code
        """
        code = []
        if self.color:
            if isinstance(self.color, str):
                code.append(ANSI_COLORS[self.color])
            else:
                code.append(f'38;5;{self.color}')
        for style in self.style:
            code.append(ANSI_STYLES[style])
        return ANSI_PREFIX + ';'.join(code) + ANSI_END
ColorMappingDict = Dict[str, MessageStyle]
TITLE_UNDERLINES = ['', '=', '-', '.']
ANSI_PREFIX = '\x1b['
ANSI_END = 'm'
ANSI_RESET = '\x1b[0m'
ANSI_STYLES = {'reset': '0', 'bold': '1', 'italic': '3', 'underline': '4', 'blink': '5', 'inverse': '7', 'strike': '9'}
ANSI_COLORS = {'reset': '0', 'black': '30', 'red': '31', 'green': '32', 'yellow': '33', 'blue': '34', 'magenta': '35', 'cyan': '36', 'white': '37'}
MESSAGE_FIELDS = {i.name for i in fields(Message)}
'All fields of the Message class.'

def colorize_ansi(msg: str, msg_style: MessageStyle) -> str:
    """Colorize message by wrapping it with ANSI escape codes."""
    if not msg_style.color and not msg_style.style:
        return msg
    escape_code = msg_style.__get_ansi_code()
    return f"{escape_code}{msg}{ANSI_RESET}"

class TextReporter(BaseReporter):
    """Reports messages and layouts in plain text."""
    name = 'text'
    extension = 'txt'
    line_format = '{path}:{line}:{column}: {msg_id}: {msg} ({symbol})'

    def __init__(self, output: TextIO | None=None) -> None:
        super().__init__(output)
        self._modules: set[str] = set()
        self._template = self.line_format
        self._fixed_template = self.line_format
        'The output format template with any unrecognized arguments removed.'

    def on_set_current_module(self, module: str, filepath: str | None) -> None:
        """Set the format template to be used and check for unrecognized arguments."""
        self._modules.add(module)
        self._template = self.line_format
        # Remove any unrecognized arguments from the template
        recognized_args = MESSAGE_FIELDS | {'path', 'module', 'obj', 'column'}
        self._fixed_template = re.sub(
            r'\{([^}]+)\}',
            lambda m: m.group(0) if m.group(1) in recognized_args else '',
            self._template
        )

    def write_message(self, msg: Message) -> None:
        """Convenience method to write a formatted message with class default
        template.
        """
        self.writeln(self._fixed_template.format(**{**asdict(msg), 'path': msg.abspath, 'module': msg.module, 'obj': msg.obj, 'column': msg.column or 0}))

    def handle_message(self, msg: Message) -> None:
        """Manage message of different type and in the context of path."""
        if msg.module not in self._modules:
            if msg.module and msg.module != 'global':
                self.writeln(f'************* Module {msg.module}')
                self._modules.add(msg.module)
            else:
                self.writeln('************* ')
        self.write_message(msg)

    def _display(self, layout: Section) -> None:
        """Launch layouts display."""
        writer = TextWriter()
        writer.format_children(layout)
        self.writeln(writer.stream.getvalue())

class NoHeaderReporter(TextReporter):
    """Reports messages and layouts in plain text without a module header."""
    name = 'no-header'

    def handle_message(self, msg: Message) -> None:
        """Write message(s) without module header."""
        self.write_message(msg)

class ParseableTextReporter(TextReporter):
    """A reporter very similar to TextReporter, but display messages in a form
    recognized by most text editors :

    <filename>:<linenum>:<msg>
    """
    name = 'parseable'
    line_format = '{path}:{line}: [{msg_id}({symbol}), {obj}] {msg}'

    def __init__(self, output: TextIO | None=None) -> None:
        warnings.warn(f'{self.name} output format is deprecated. This is equivalent to --msg-template={self.line_format}', DeprecationWarning, stacklevel=2)
        super().__init__(output)

class VSTextReporter(ParseableTextReporter):
    """Visual studio text reporter."""
    name = 'msvs'
    line_format = '{path}({line}): [{msg_id}({symbol}){obj}] {msg}'

class ColorizedTextReporter(TextReporter):
    """Simple TextReporter that colorizes text output."""
    name = 'colorized'
    COLOR_MAPPING: ColorMappingDict = {'I': MessageStyle('green'), 'C': MessageStyle(None, ('bold',)), 'R': MessageStyle('magenta', ('bold', 'italic')), 'W': MessageStyle('magenta'), 'E': MessageStyle('red', ('bold',)), 'F': MessageStyle('red', ('bold', 'underline')), 'S': MessageStyle('yellow', ('inverse',))}

    def __init__(self, output: TextIO | None=None, color_mapping: ColorMappingDict | None=None) -> None:
        super().__init__(output)
        self.color_mapping = color_mapping or ColorizedTextReporter.COLOR_MAPPING
        ansi_terms = ['xterm-16color', 'xterm-256color']
        if os.environ.get('TERM') not in ansi_terms:
            if sys.platform == 'win32':
                import colorama
                self.out = colorama.AnsiToWin32(self.out)

    def _get_decoration(self, msg_id: str) -> MessageStyle:
        """Returns the message style as defined in self.color_mapping."""
        return self.color_mapping.get(msg_id[0], MessageStyle(None))

    def handle_message(self, msg: Message) -> None:
        """Manage message of different types, and colorize output
        using ANSI escape codes.
        """
        if msg.module not in self._modules:
            if msg.module and msg.module != 'global':
                self.writeln(colorize_ansi(f'************* Module {msg.module}', MessageStyle('green', ('bold',))))
                self._modules.add(msg.module)
            else:
                self.writeln(colorize_ansi('************* ', MessageStyle('green', ('bold',))))
        self.write_message(colorize_ansi(self._fixed_template.format(**{**asdict(msg), 'path': msg.abspath, 'module': msg.module, 'obj': msg.obj, 'column': msg.column or 0}), self._get_decoration(msg.C)))

class GithubReporter(TextReporter):
    """Report messages in GitHub's special format to annotate code in its user
    interface.
    """
    name = 'github'
    line_format = '::{category} file={path},line={line},endline={end_line},col={column},title={msg_id}::{msg}'
    category_map = {'F': 'error', 'E': 'error', 'W': 'warning', 'C': 'notice', 'R': 'notice', 'I': 'notice'}
