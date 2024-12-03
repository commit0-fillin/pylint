"""Imports checkers for Python code."""
from __future__ import annotations
import collections
import copy
import os
import sys
from collections import defaultdict
from collections.abc import ItemsView, Sequence
from functools import cached_property
from typing import TYPE_CHECKING, Any, Dict, List, Union
import astroid
from astroid import nodes
from astroid.nodes._base_nodes import ImportNode
from pylint.checkers import BaseChecker, DeprecatedMixin
from pylint.checkers.utils import get_import_name, in_type_checking_block, is_from_fallback_block, is_module_ignored, is_sys_guard, node_ignores_exception
from pylint.constants import MAX_NUMBER_OF_IMPORT_SHOWN
from pylint.exceptions import EmptyReportError
from pylint.graph import DotBackend, get_cycles
from pylint.interfaces import HIGH
from pylint.reporters.ureports.nodes import Paragraph, Section, VerbatimText
from pylint.typing import MessageDefinitionTuple
from pylint.utils import IsortDriver
from pylint.utils.linterstats import LinterStats
if TYPE_CHECKING:
    from pylint.lint import PyLinter
_ImportTree = Dict[str, Union[List[Dict[str, Any]], List[str]]]
DEPRECATED_MODULES = {(0, 0, 0): {'tkinter.tix', 'fpectl'}, (3, 2, 0): {'optparse'}, (3, 3, 0): {'xml.etree.cElementTree'}, (3, 4, 0): {'imp'}, (3, 5, 0): {'formatter'}, (3, 6, 0): {'asynchat', 'asyncore', 'smtpd'}, (3, 7, 0): {'macpath'}, (3, 9, 0): {'lib2to3', 'parser', 'symbol', 'binhex'}, (3, 10, 0): {'distutils', 'typing.io', 'typing.re'}, (3, 11, 0): {'aifc', 'audioop', 'cgi', 'cgitb', 'chunk', 'crypt', 'imghdr', 'msilib', 'mailcap', 'nis', 'nntplib', 'ossaudiodev', 'pipes', 'sndhdr', 'spwd', 'sunau', 'sre_compile', 'sre_constants', 'sre_parse', 'telnetlib', 'uu', 'xdrlib'}}

def _get_first_import(node: ImportNode, context: nodes.LocalsDictNodeNG, name: str, base: str | None, level: int | None, alias: str | None) -> tuple[nodes.Import | nodes.ImportFrom | None, str | None]:
    """Return the node where [base.]<name> is imported or None if not found."""
    for import_node in context.body:
        if not isinstance(import_node, (nodes.Import, nodes.ImportFrom)):
            continue
        if import_node.names:
            for import_name, import_alias in import_node.names:
                if import_name == name and import_alias == alias:
                    if isinstance(import_node, nodes.ImportFrom):
                        if import_node.level == level and import_node.modname == base:
                            return import_node, import_name
                    else:
                        if base is None:
                            return import_node, import_name
    return None, None

def _make_tree_defs(mod_files_list: ItemsView[str, set[str]]) -> _ImportTree:
    """Get a list of 2-uple (module, list_of_files_which_import_this_module),
    it will return a dictionary to represent this as a tree.
    """
    tree: _ImportTree = {}
    for mod, files in mod_files_list:
        parts = mod.split('.')
        subtree = tree
        for part in parts[:-1]:
            if part not in subtree:
                subtree[part] = {}
            subtree = subtree[part]
        subtree[parts[-1]] = list(files)
    return tree

def _repr_tree_defs(data: _ImportTree, indent_str: str | None=None) -> str:
    """Return a string which represents imports as a tree."""
    lines = []
    if indent_str is None:
        indent_str = '  '
    
    def _repr_tree(tree: _ImportTree, indent: str = '') -> None:
        for name, values in tree.items():
            if isinstance(values, list):
                lines.append(f"{indent}{name}")
                for value in values:
                    lines.append(f"{indent}{indent_str}{value}")
            else:
                lines.append(f"{indent}{name}")
                _repr_tree(values, indent + indent_str)
    
    _repr_tree(data)
    return '\n'.join(lines)

def _dependencies_graph(filename: str, dep_info: dict[str, set[str]]) -> str:
    """Write dependencies as a dot (graphviz) file."""
    done = {}
    printer = DotBackend(filename, rankdir="LR")
    printer.emit('URL="." node[shape="box"]')
    for modname, dependencies in dep_info.items():
        done[modname] = 1
        printer.emit_node(modname)
        for dependency in dependencies:
            if dependency not in done:
                done[dependency] = 1
                printer.emit_node(dependency)
    for modname, dependencies in dep_info.items():
        for dependency in dependencies:
            printer.emit_edge(modname, dependency)
    return printer.generate(filename)

def _make_graph(filename: str, dep_info: dict[str, set[str]], sect: Section, gtype: str) -> None:
    """Generate a dependencies graph and add some information about it in the
    report's section.
    """
    outputfile = _dependencies_graph(filename, dep_info)
    sect.append(Paragraph(f"{gtype} dependencies graph has been written to {outputfile}"))
MSGS: dict[str, MessageDefinitionTuple] = {'E0401': ('Unable to import %s', 'import-error', 'Used when pylint has been unable to import a module.', {'old_names': [('F0401', 'old-import-error')]}), 'E0402': ('Attempted relative import beyond top-level package', 'relative-beyond-top-level', 'Used when a relative import tries to access too many levels in the current package.'), 'R0401': ('Cyclic import (%s)', 'cyclic-import', 'Used when a cyclic import between two or more modules is detected.'), 'R0402': ("Use 'from %s import %s' instead", 'consider-using-from-import', 'Emitted when a submodule of a package is imported and aliased with the same name, e.g., instead of ``import concurrent.futures as futures`` use ``from concurrent import futures``.'), 'W0401': ('Wildcard import %s', 'wildcard-import', 'Used when `from module import *` is detected.'), 'W0404': ('Reimport %r (imported line %s)', 'reimported', 'Used when a module is imported more than once.'), 'W0406': ('Module import itself', 'import-self', 'Used when a module is importing itself.'), 'W0407': ('Prefer importing %r instead of %r', 'preferred-module', 'Used when a module imported has a preferred replacement module.'), 'W0410': ('__future__ import is not the first non docstring statement', 'misplaced-future', 'Python 2.5 and greater require __future__ import to be the first non docstring statement in the module.'), 'C0410': ('Multiple imports on one line (%s)', 'multiple-imports', 'Used when import statement importing multiple modules is detected.'), 'C0411': ('%s should be placed before %s', 'wrong-import-order', 'Used when PEP8 import order is not respected (standard imports first, then third-party libraries, then local imports).'), 'C0412': ('Imports from package %s are not grouped', 'ungrouped-imports', 'Used when imports are not grouped by packages.'), 'C0413': ('Import "%s" should be placed at the top of the module', 'wrong-import-position', 'Used when code and imports are mixed.'), 'C0414': ('Import alias does not rename original package', 'useless-import-alias', 'Used when an import alias is same as original package, e.g., using import numpy as numpy instead of import numpy as np.'), 'C0415': ('Import outside toplevel (%s)', 'import-outside-toplevel', 'Used when an import statement is used anywhere other than the module toplevel. Move this import to the top of the file.'), 'W0416': ('Shadowed %r (imported line %s)', 'shadowed-import', 'Used when a module is aliased with a name that shadows another import.')}
DEFAULT_STANDARD_LIBRARY = ()
DEFAULT_KNOWN_THIRD_PARTY = ('enchant',)
DEFAULT_PREFERRED_MODULES = ()

class ImportsChecker(DeprecatedMixin, BaseChecker):
    """BaseChecker for import statements.

    Checks for
    * external modules dependencies
    * relative / wildcard imports
    * cyclic imports
    * uses of deprecated modules
    * uses of modules instead of preferred modules
    """
    name = 'imports'
    msgs = {**DeprecatedMixin.DEPRECATED_MODULE_MESSAGE, **MSGS}
    default_deprecated_modules = ()
    options = (('deprecated-modules', {'default': default_deprecated_modules, 'type': 'csv', 'metavar': '<modules>', 'help': 'Deprecated modules which should not be used, separated by a comma.'}), ('preferred-modules', {'default': DEFAULT_PREFERRED_MODULES, 'type': 'csv', 'metavar': '<module:preferred-module>', 'help': 'Couples of modules and preferred modules, separated by a comma.'}), ('import-graph', {'default': '', 'type': 'path', 'metavar': '<file.gv>', 'help': 'Output a graph (.gv or any supported image format) of all (i.e. internal and external) dependencies to the given file (report RP0402 must not be disabled).'}), ('ext-import-graph', {'default': '', 'type': 'path', 'metavar': '<file.gv>', 'help': 'Output a graph (.gv or any supported image format) of external dependencies to the given file (report RP0402 must not be disabled).'}), ('int-import-graph', {'default': '', 'type': 'path', 'metavar': '<file.gv>', 'help': 'Output a graph (.gv or any supported image format) of internal dependencies to the given file (report RP0402 must not be disabled).'}), ('known-standard-library', {'default': DEFAULT_STANDARD_LIBRARY, 'type': 'csv', 'metavar': '<modules>', 'help': 'Force import order to recognize a module as part of the standard compatibility libraries.'}), ('known-third-party', {'default': DEFAULT_KNOWN_THIRD_PARTY, 'type': 'csv', 'metavar': '<modules>', 'help': 'Force import order to recognize a module as part of a third party library.'}), ('allow-any-import-level', {'default': (), 'type': 'csv', 'metavar': '<modules>', 'help': 'List of modules that can be imported at any level, not just the top level one.'}), ('allow-wildcard-with-all', {'default': False, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Allow wildcard imports from modules that define __all__.'}), ('allow-reexport-from-package', {'default': False, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Allow explicit reexports by alias from a package __init__.'}))

    def __init__(self, linter: PyLinter) -> None:
        BaseChecker.__init__(self, linter)
        self.import_graph: defaultdict[str, set[str]] = defaultdict(set)
        self._imports_stack: list[tuple[ImportNode, str]] = []
        self._first_non_import_node = None
        self._module_pkg: dict[Any, Any] = {}
        self._allow_any_import_level: set[Any] = set()
        self.reports = (('RP0401', 'External dependencies', self._report_external_dependencies), ('RP0402', 'Modules dependencies graph', self._report_dependencies_graph))
        self._excluded_edges: defaultdict[str, set[str]] = defaultdict(set)

    def open(self) -> None:
        """Called before visiting project (i.e set of modules)."""
        self._allow_any_import_level = set(self.linter.config.allow_any_import_level)

    def close(self) -> None:
        """Called before visiting project (i.e set of modules)."""
        if self.linter.is_message_enabled("cyclic-import"):
            importers = {}
            for importee, importers_set in self.import_graph.items():
                if importee not in importers:
                    importers[importee] = set()
                for importer in importers_set:
                    importers[importee].add(importer)
            cycles = get_cycles(importers)
            for cycle in cycles:
                self.add_message("cyclic-import", args=" -> ".join(cycle))

    def deprecated_modules(self) -> set[str]:
        """Callback returning the deprecated modules."""
        return set(self.config.deprecated_modules)

    def visit_module(self, node: nodes.Module) -> None:
        """Store if current module is a package, i.e. an __init__ file."""
        self._module_pkg[node.name] = node.package

    def visit_import(self, node: nodes.Import) -> None:
        """Triggered when an import statement is seen."""
        self._check_reimport(node)
        self._check_import_as_rename(node)
        self._check_toplevel(node)
        self._check_deprecated_module(node)
        for name, alias in node.names:
            self._check_preferred_module(node, name)
            imported_module = self._get_imported_module(node, name)
            if isinstance(imported_module, nodes.Module):
                self._record_import(node, imported_module)
                self._add_imported_module(node, imported_module.name)

    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        """Triggered when a from statement is seen."""
        self._check_misplaced_future(node)
        self._check_deprecated_module(node)
        self._check_preferred_module(node, node.modname)
        self._check_wildcard_imports(node)
        self._check_toplevel(node)
        self._check_reimport(node, node.modname)
        for name, _ in node.names:
            self._check_reimport(node, f"{node.modname}.{name}", name)
        if not node.level:
            importedmodnode = self._get_imported_module(node, node.modname)
            if isinstance(importedmodnode, nodes.Module):
                self._check_import_as_rename(node)
                self._record_import(node, importedmodnode)
                self._add_imported_module(node, importedmodnode.name)
    visit_try = visit_assignattr = visit_assign = visit_ifexp = visit_comprehension = visit_expr = visit_if = compute_first_non_import_node
    visit_classdef = visit_for = visit_while = visit_functiondef

    def _check_position(self, node: ImportNode) -> None:
        """Check `node` import or importfrom node position is correct.

        Send a message  if `node` comes before another instruction
        """
        pass

    def _record_import(self, node: ImportNode, importedmodnode: nodes.Module | None) -> None:
        """Record the package `node` imports from."""
        pass

    def _check_imports_order(self, _module_node: nodes.Module) -> tuple[list[tuple[ImportNode, str]], list[tuple[ImportNode, str]], list[tuple[ImportNode, str]]]:
        """Checks imports of module `node` are grouped by category.

        Imports must follow this order: standard, 3rd party, local
        """
        pass

    def _add_imported_module(self, node: ImportNode, importedmodname: str) -> None:
        """Notify an imported module, used to analyze dependencies."""
        pass

    def _check_preferred_module(self, node: ImportNode, mod_path: str) -> None:
        """Check if the module has a preferred replacement."""
        pass

    def _check_reimport(self, node: ImportNode, basename: str | None=None, level: int | None=None) -> None:
        """Check if a module with the same name is already imported or aliased."""
        pass

    def _report_external_dependencies(self, sect: Section, _: LinterStats, _dummy: LinterStats | None) -> None:
        """Return a verbatim layout for displaying dependencies."""
        pass

    def _report_dependencies_graph(self, sect: Section, _: LinterStats, _dummy: LinterStats | None) -> None:
        """Write dependencies as a dot (graphviz) file."""
        pass

    def _filter_dependencies_graph(self, internal: bool) -> defaultdict[str, set[str]]:
        """Build the internal or the external dependency graph."""
        pass

    @cached_property
    def _external_dependencies_info(self) -> defaultdict[str, set[str]]:
        """Return cached external dependencies information or build and
        cache them.
        """
        pass

    @cached_property
    def _internal_dependencies_info(self) -> defaultdict[str, set[str]]:
        """Return cached internal dependencies information or build and
        cache them.
        """
        pass

    def _check_toplevel(self, node: ImportNode) -> None:
        """Check whether the import is made outside the module toplevel."""
        pass
