"""All alphanumeric unicode character are allowed in Python but due
to similarities in how they look they can be confused.

See: https://peps.python.org/pep-0672/#confusing-features

The following checkers are intended to make users are aware of these issues.
"""
from __future__ import annotations
from astroid import nodes
from pylint import constants, interfaces, lint
from pylint.checkers import base_checker, utils
NON_ASCII_HELP = 'Used when the name contains at least one non-ASCII unicode character. See https://peps.python.org/pep-0672/#confusing-features for a background why this could be bad. \nIf your programming guideline defines that you are programming in English, then there should be no need for non ASCII characters in Python Names. If not you can simply disable this check.'

class NonAsciiNameChecker(base_checker.BaseChecker):
    """A strict name checker only allowing ASCII.

    Note: This check only checks Names, so it ignores the content of
          docstrings and comments!
    """
    msgs = {'C2401': ('%s name "%s" contains a non-ASCII character, consider renaming it.', 'non-ascii-name', NON_ASCII_HELP, {'old_names': [('C0144', 'old-non-ascii-name')]}), 'W2402': ('%s name "%s" contains a non-ASCII character.', 'non-ascii-file-name', "Under python 3.5, PEP 3131 allows non-ascii identifiers, but not non-ascii file names.Since Python 3.5, even though Python supports UTF-8 files, some editors or tools don't."), 'C2403': ('%s name "%s" contains a non-ASCII character, use an ASCII-only alias for import.', 'non-ascii-module-import', NON_ASCII_HELP)}
    name = 'NonASCII-Checker'

    def _check_name(self, node_type: str, name: str | None, node: nodes.NodeNG) -> None:
        """Check whether a name is using non-ASCII characters."""
        if name is None:
            return
        if not name.isascii():
            if isinstance(node, nodes.Module):
                self.add_message("non-ascii-file-name", node=node, args=(node_type, name))
            elif isinstance(node, (nodes.ImportFrom, nodes.Import)):
                self.add_message("non-ascii-module-import", node=node, args=(node_type, name))
            else:
                self.add_message("non-ascii-name", node=node, args=(node_type, name))
    visit_asyncfunctiondef = visit_functiondef

    @utils.only_required_for_messages('non-ascii-name')
    def visit_assignname(self, node: nodes.AssignName) -> None:
        """Check module level assigned names."""
        if isinstance(node.parent, nodes.Assign) and node.parent.parent.scope_type == "module":
            self._check_name("variable", node.name, node)

    @utils.only_required_for_messages('non-ascii-name')
    def visit_call(self, node: nodes.Call) -> None:
        """Check if the used keyword args are correct."""
        for keyword in node.keywords:
            self._check_name("keyword argument", keyword.arg, keyword)
