"""Check source code is ascii only or has an encoding declaration (PEP 263)."""
from __future__ import annotations
import re
import tokenize
from typing import TYPE_CHECKING
from astroid import nodes
from pylint.checkers import BaseRawFileChecker, BaseTokenChecker
from pylint.typing import ManagedMessage
if TYPE_CHECKING:
    from pylint.lint import PyLinter

class ByIdManagedMessagesChecker(BaseRawFileChecker):
    """Checks for messages that are enabled or disabled by id instead of symbol."""
    name = 'miscellaneous'
    msgs = {'I0023': ('%s', 'use-symbolic-message-instead', 'Used when a message is enabled or disabled by id.', {'default_enabled': False})}
    options = ()

    def process_module(self, node: nodes.Module) -> None:
        """Inspect the source file to find messages activated or deactivated by id."""
        for comment in node.body:
            if isinstance(comment, nodes.Comment):
                match = re.search(r'pylint:\s*(disable|enable)=([A-Z]\d{4}(?:,\s*[A-Z]\d{4})*)', comment.value)
                if match:
                    action, message_ids = match.groups()
                    for message_id in message_ids.split(','):
                        message_id = message_id.strip()
                        self.add_message(
                            'use-symbolic-message-instead',
                            line=comment.lineno,
                            args=f"'{action}={message_id}' should use symbolic names",
                        )

class EncodingChecker(BaseTokenChecker, BaseRawFileChecker):
    """BaseChecker for encoding issues.

    Checks for:
    * warning notes in the code like FIXME, XXX
    * encoding issues.
    """
    name = 'miscellaneous'
    msgs = {'W0511': ('%s', 'fixme', 'Used when a warning note as FIXME or XXX is detected.')}
    options = (('notes', {'type': 'csv', 'metavar': '<comma separated values>', 'default': ('FIXME', 'XXX', 'TODO'), 'help': 'List of note tags to take in consideration, separated by a comma.'}), ('notes-rgx', {'type': 'string', 'metavar': '<regexp>', 'help': 'Regular expression of note tags to take in consideration.', 'default': ''}))

    def process_module(self, node: nodes.Module) -> None:
        """Inspect the source file to find encoding problem."""
        encoding = node.file_encoding
        if encoding is None:
            self.add_message(
                'no-encoding-declaration',
                line=1,
                args='No encoding declared in file',
            )
        elif encoding.lower() != 'utf-8':
            self.add_message(
                'non-utf8-encoding',
                line=1,
                args=f'File encoding is {encoding}, consider using UTF-8',
            )

    def process_tokens(self, tokens: list[tokenize.TokenInfo]) -> None:
        """Inspect the source to find fixme problems."""
        notes_regexp = '|'.join(map(re.escape, self.config.notes))
        if self.config.notes_rgx:
            notes_regexp = f'({notes_regexp}|{self.config.notes_rgx})'
        else:
            notes_regexp = f'({notes_regexp})'
        
        regexp = re.compile(notes_regexp, re.IGNORECASE)
        for token in tokens:
            if token.type == tokenize.COMMENT:
                comment = token.string.lstrip('#').strip()
                match = regexp.search(comment)
                if match:
                    note = match.group(1)
                    self.add_message(
                        'fixme',
                        args=comment,
                        line=token.start[0],
                        col_offset=token.start[1],
                    )
