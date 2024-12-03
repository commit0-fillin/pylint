"""Checker for spelling errors in comments and docstrings."""
from __future__ import annotations
import re
import tokenize
from re import Pattern
from typing import TYPE_CHECKING, Any, Literal
from astroid import nodes
from pylint.checkers import BaseTokenChecker
from pylint.checkers.utils import only_required_for_messages
if TYPE_CHECKING:
    from pylint.lint import PyLinter
try:
    import enchant
    from enchant.tokenize import Chunker, EmailFilter, Filter, URLFilter, WikiWordFilter, get_tokenizer
    PYENCHANT_AVAILABLE = True
except ImportError:
    enchant = None
    PYENCHANT_AVAILABLE = False

    class EmailFilter:
        ...

    class URLFilter:
        ...

    class WikiWordFilter:
        ...

    class Filter:
        pass

    class Chunker:
        pass
enchant_dicts = _get_enchant_dicts()

class WordsWithDigitsFilter(Filter):
    """Skips words with digits."""

class WordsWithUnderscores(Filter):
    """Skips words with underscores.

    They are probably function parameter names.
    """

class RegExFilter(Filter):
    """Parent class for filters using regular expressions.

    This filter skips any words the match the expression
    assigned to the class attribute ``_pattern``.
    """
    _pattern: Pattern[str]

class CamelCasedWord(RegExFilter):
    """Filter skipping over camelCasedWords.
    This filter skips any words matching the following regular expression:

           ^([a-z]\\w+[A-Z]+\\w+)

    That is, any words that are camelCasedWords.
    """
    _pattern = re.compile('^([a-z]+(\\d|[A-Z])(?:\\w+)?)')

class SphinxDirectives(RegExFilter):
    """Filter skipping over Sphinx Directives.
    This filter skips any words matching the following regular expression:

           ^(:([a-z]+)){1,2}:`([^`]+)(`)?

    That is, for example, :class:`BaseQuery`
    """
    _pattern = re.compile('^(:([a-z]+)){1,2}:`([^`]+)(`)?')

class ForwardSlashChunker(Chunker):
    """This chunker allows splitting words like 'before/after' into 'before' and
    'after'.
    """
    _text: str
CODE_FLANKED_IN_BACKTICK_REGEX = re.compile('(\\s|^)(`{1,2})([^`]+)(\\2)([^`]|$)')

def _strip_code_flanked_in_backticks(line: str) -> str:
    """Alter line so code flanked in back-ticks is ignored.

    Pyenchant automatically strips back-ticks when parsing tokens,
    so this cannot be done at the individual filter level.
    """
    return CODE_FLANKED_IN_BACKTICK_REGEX.sub(r'\1\5', line)

class SpellingChecker(BaseTokenChecker):
    """Check spelling in comments and docstrings."""
    name = 'spelling'
    msgs = {'C0401': ("Wrong spelling of a word '%s' in a comment:\n%s\n%s\nDid you mean: '%s'?", 'wrong-spelling-in-comment', 'Used when a word in comment is not spelled correctly.'), 'C0402': ("Wrong spelling of a word '%s' in a docstring:\n%s\n%s\nDid you mean: '%s'?", 'wrong-spelling-in-docstring', 'Used when a word in docstring is not spelled correctly.'), 'C0403': ('Invalid characters %r in a docstring', 'invalid-characters-in-docstring', 'Used when a word in docstring cannot be checked by enchant.')}
    options = (('spelling-dict', {'default': '', 'type': 'choice', 'metavar': '<dict name>', 'choices': _get_enchant_dict_choices(enchant_dicts), 'help': _get_enchant_dict_help(enchant_dicts, PYENCHANT_AVAILABLE)}), ('spelling-ignore-words', {'default': '', 'type': 'string', 'metavar': '<comma separated words>', 'help': 'List of comma separated words that should not be checked.'}), ('spelling-private-dict-file', {'default': '', 'type': 'path', 'metavar': '<path to file>', 'help': 'A path to a file that contains the private dictionary; one word per line.'}), ('spelling-store-unknown-words', {'default': 'n', 'type': 'yn', 'metavar': '<y or n>', 'help': 'Tells whether to store unknown words to the private dictionary (see the --spelling-private-dict-file option) instead of raising a message.'}), ('max-spelling-suggestions', {'default': 4, 'type': 'int', 'metavar': 'N', 'help': 'Limits count of emitted suggestions for spelling mistakes.'}), ('spelling-ignore-comment-directives', {'default': 'fmt: on,fmt: off,noqa:,noqa,nosec,isort:skip,mypy:', 'type': 'string', 'metavar': '<comma separated words>', 'help': 'List of comma separated words that should be considered directives if they appear at the beginning of a comment and should not be checked.'}))
    visit_asyncfunctiondef = visit_functiondef

    def _check_docstring(self, node: nodes.FunctionDef | nodes.AsyncFunctionDef | nodes.ClassDef | nodes.Module) -> None:
        """Check if the node has any spelling errors."""
        if not node.doc:
            return
        
        # Get the line number and column offset of the string node
        lineno = node.lineno
        col_offset = node.col_offset
        
        # If it's a function or class, adjust the line and column numbers
        if isinstance(node, (nodes.FunctionDef, nodes.AsyncFunctionDef, nodes.ClassDef)):
            lineno += 1
            col_offset = 0
        
        # Check for spelling errors in the docstring
        for line in node.doc.splitlines():
            stripped_line = _strip_code_flanked_in_backticks(line)
            for word, pos in self.tokenize_str(stripped_line):
                if not self.check(word):
                    suggestions = self.spelling_dict.suggest(word)[:self.max_spelling_suggestions]
                    self.add_message(
                        'wrong-spelling-in-docstring',
                        args=(word, line, ' ' * pos + '^', ' or '.join(suggestions)),
                        node=node,
                        line=lineno,
                        col=col_offset + pos,
                    )
            lineno += 1
