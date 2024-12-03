from __future__ import annotations
import argparse
import collections
import contextlib
import functools
import os
import sys
import tokenize
import traceback
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Sequence
from io import TextIOWrapper
from pathlib import Path
from re import Pattern
from types import ModuleType
from typing import Any, Protocol
import astroid
from astroid import nodes
from pylint import checkers, exceptions, interfaces, reporters
from pylint.checkers.base_checker import BaseChecker
from pylint.config.arguments_manager import _ArgumentsManager
from pylint.constants import MAIN_CHECKER_NAME, MSG_TYPES, MSG_TYPES_STATUS, WarningScope
from pylint.interfaces import HIGH
from pylint.lint.base_options import _make_linter_options
from pylint.lint.caching import load_results, save_results
from pylint.lint.expand_modules import _is_ignored_file, discover_package_path, expand_modules
from pylint.lint.message_state_handler import _MessageStateHandler
from pylint.lint.parallel import check_parallel
from pylint.lint.report_functions import report_messages_by_module_stats, report_messages_stats, report_total_messages_stats
from pylint.lint.utils import _is_relative_to, augmented_sys_path, get_fatal_error_message, prepare_crash_report
from pylint.message import Message, MessageDefinition, MessageDefinitionStore
from pylint.reporters.base_reporter import BaseReporter
from pylint.reporters.text import TextReporter
from pylint.reporters.ureports import nodes as report_nodes
from pylint.typing import DirectoryNamespaceDict, FileItem, ManagedMessage, MessageDefinitionTuple, MessageLocationTuple, ModuleDescriptionDict, Options
from pylint.utils import ASTWalker, FileState, LinterStats, utils
MANAGER = astroid.MANAGER

class GetAstProtocol(Protocol):

    def __call__(self, filepath: str, modname: str, data: str | None=None) -> nodes.Module:
        ...
MSGS: dict[str, MessageDefinitionTuple] = {'F0001': ('%s', 'fatal', 'Used when an error occurred preventing the analysis of a               module (unable to find it for instance).', {'scope': WarningScope.LINE}), 'F0002': ('%s: %s', 'astroid-error', 'Used when an unexpected error occurred while building the Astroid  representation. This is usually accompanied by a traceback. Please report such errors !', {'scope': WarningScope.LINE}), 'F0010': ('error while code parsing: %s', 'parse-error', 'Used when an exception occurred while building the Astroid representation which could be handled by astroid.', {'scope': WarningScope.LINE}), 'F0011': ('error while parsing the configuration: %s', 'config-parse-error', 'Used when an exception occurred while parsing a pylint configuration file.', {'scope': WarningScope.LINE}), 'I0001': ('Unable to run raw checkers on built-in module %s', 'raw-checker-failed', 'Used to inform that a built-in module has not been checked using the raw checkers.', {'scope': WarningScope.LINE, 'default_enabled': False}), 'I0010': ('Unable to consider inline option %r', 'bad-inline-option', "Used when an inline option is either badly formatted or can't be used inside modules.", {'scope': WarningScope.LINE, 'default_enabled': False}), 'I0011': ('Locally disabling %s (%s)', 'locally-disabled', 'Used when an inline option disables a message or a messages category.', {'scope': WarningScope.LINE, 'default_enabled': False}), 'I0013': ('Ignoring entire file', 'file-ignored', 'Used to inform that the file will not be checked', {'scope': WarningScope.LINE, 'default_enabled': False}), 'I0020': ('Suppressed %s (from line %d)', 'suppressed-message', 'A message was triggered on a line, but suppressed explicitly by a disable= comment in the file. This message is not generated for messages that are ignored due to configuration settings.', {'scope': WarningScope.LINE, 'default_enabled': False}), 'I0021': ('Useless suppression of %s', 'useless-suppression', 'Reported when a message is explicitly disabled for a line or a block of code, but never triggered.', {'scope': WarningScope.LINE, 'default_enabled': False}), 'I0022': ('Pragma "%s" is deprecated, use "%s" instead', 'deprecated-pragma', 'Some inline pylint options have been renamed or reworked, only the most recent form should be used. NOTE:skip-all is only available with pylint >= 0.26', {'old_names': [('I0014', 'deprecated-disable-all')], 'scope': WarningScope.LINE, 'default_enabled': False}), 'E0001': ('%s', 'syntax-error', 'Used when a syntax error is raised for a module.', {'scope': WarningScope.LINE}), 'E0011': ('Unrecognized file option %r', 'unrecognized-inline-option', 'Used when an unknown inline option is encountered.', {'scope': WarningScope.LINE}), 'W0012': ("Unknown option value for '%s', expected a valid pylint message and got '%s'", 'unknown-option-value', 'Used when an unknown value is encountered for an option.', {'scope': WarningScope.LINE, 'old_names': [('E0012', 'bad-option-value')]}), 'R0022': ("Useless option value for '%s', %s", 'useless-option-value', 'Used when a value for an option that is now deleted from pylint is encountered.', {'scope': WarningScope.LINE, 'old_names': [('E0012', 'bad-option-value')]}), 'E0013': ("Plugin '%s' is impossible to load, is it installed ? ('%s')", 'bad-plugin-value', "Used when a bad value is used in 'load-plugins'.", {'scope': WarningScope.LINE}), 'E0014': ("Out-of-place setting encountered in top level configuration-section '%s' : '%s'", 'bad-configuration-section', "Used when we detect a setting in the top level of a toml configuration that shouldn't be there.", {'scope': WarningScope.LINE}), 'E0015': ('Unrecognized option found: %s', 'unrecognized-option', 'Used when we detect an option that we do not recognize.', {'scope': WarningScope.LINE})}

class PyLinter(_ArgumentsManager, _MessageStateHandler, reporters.ReportsHandlerMixIn, checkers.BaseChecker):
    """Lint Python modules using external checkers.

    This is the main checker controlling the other ones and the reports
    generation. It is itself both a raw checker and an astroid checker in order
    to:
    * handle message activation / deactivation at the module level
    * handle some basic but necessary stats' data (number of classes, methods...)

    IDE plugin developers: you may have to call
    `astroid.MANAGER.clear_cache()` across runs if you want
    to ensure the latest code version is actually checked.

    This class needs to support pickling for parallel linting to work. The exception
    is reporter member; see check_parallel function for more details.
    """
    name = MAIN_CHECKER_NAME
    msgs = MSGS
    crash_file_path: str = 'pylint-crash-%Y-%m-%d-%H-%M-%S.txt'
    option_groups_descs = {'Messages control': 'Options controlling analysis messages', 'Reports': 'Options related to output formatting and reporting'}

    def __init__(self, options: Options=(), reporter: reporters.BaseReporter | reporters.MultiReporter | None=None, option_groups: tuple[tuple[str, str], ...]=(), pylintrc: str | None=None) -> None:
        _ArgumentsManager.__init__(self, prog='pylint')
        _MessageStateHandler.__init__(self, self)
        self.reporter: reporters.BaseReporter | reporters.MultiReporter
        if reporter:
            self.set_reporter(reporter)
        else:
            self.set_reporter(TextReporter())
        self._reporters: dict[str, type[reporters.BaseReporter]] = {}
        'Dictionary of possible but non-initialized reporters.'
        self._checkers: defaultdict[str, list[checkers.BaseChecker]] = collections.defaultdict(list)
        'Dictionary of registered and initialized checkers.'
        self._dynamic_plugins: dict[str, ModuleType | ModuleNotFoundError | bool] = {}
        'Set of loaded plugin names.'
        self.stats = LinterStats()
        self.options: Options = options + _make_linter_options(self)
        for opt_group in option_groups:
            self.option_groups_descs[opt_group[0]] = opt_group[1]
        self._option_groups: tuple[tuple[str, str], ...] = (*option_groups, ('Messages control', 'Options controlling analysis messages'), ('Reports', 'Options related to output formatting and reporting'))
        self.fail_on_symbols: list[str] = []
        'List of message symbols on which pylint should fail, set by --fail-on.'
        self._error_mode = False
        reporters.ReportsHandlerMixIn.__init__(self)
        checkers.BaseChecker.__init__(self, self)
        self.reports = (('RP0001', 'Messages by category', report_total_messages_stats), ('RP0002', '% errors / warnings by module', report_messages_by_module_stats), ('RP0003', 'Messages', report_messages_stats))
        self.msgs_store = MessageDefinitionStore(self.config.py_version)
        self.msg_status = 0
        self._by_id_managed_msgs: list[ManagedMessage] = []
        self.file_state = FileState('', self.msgs_store, is_base_filestate=True)
        self.current_name: str = ''
        self.current_file: str | None = None
        self._ignore_file = False
        self._ignore_paths: list[Pattern[str]] = []
        self.register_checker(self)

    def load_plugin_modules(self, modnames: Iterable[str], force: bool=False) -> None:
        """Check a list of pylint plugins modules, load and register them.

        If a module cannot be loaded, never try to load it again and instead
        store the error message for later use in ``load_plugin_configuration``
        below.

        If `force` is True (useful when multiprocessing), then the plugin is
        reloaded regardless if an entry exists in self._dynamic_plugins.
        """
        for modname in modnames:
            if modname in self._dynamic_plugins and not force:
                continue
            try:
                module = utils.load_module_from_modpath(modname.split('.'))
                self._dynamic_plugins[modname] = module
                self.register_plugin(module)
            except Exception as e:
                self._dynamic_plugins[modname] = e

    def load_plugin_configuration(self) -> None:
        """Call the configuration hook for plugins.

        This walks through the list of plugins, grabs the "load_configuration"
        hook, if exposed, and calls it to allow plugins to configure specific
        settings.

        The result of attempting to load the plugin of the given name
        is stored in the dynamic plugins dictionary in ``load_plugin_modules`` above.

        ..note::
            This function previously always tried to load modules again, which
            led to some confusion and silent failure conditions as described
            in GitHub issue #7264. Making it use the stored result is more efficient, and
            means that we avoid the ``init-hook`` problems from before.
        """
        for plugin_name, plugin in self._dynamic_plugins.items():
            if isinstance(plugin, ModuleType):
                if hasattr(plugin, 'load_configuration'):
                    plugin.load_configuration(self)
            elif isinstance(plugin, Exception):
                print(f"Failed to load plugin {plugin_name}: {str(plugin)}", file=sys.stderr)

    def _load_reporters(self, reporter_names: str) -> None:
        """Load the reporters if they are available on _reporters."""
        for reporter_name in reporter_names.split(','):
            reporter_name = reporter_name.strip()
            if reporter_name in self._reporters:
                self.set_reporter(self._reporters[reporter_name]())
            else:
                raise exceptions.InvalidReporterError(reporter_name)

    def set_reporter(self, reporter: reporters.BaseReporter | reporters.MultiReporter) -> None:
        """Set the reporter used to display messages and reports."""
        self.reporter = reporter
        self.reporter.linter = self

    def register_reporter(self, reporter_class: type[reporters.BaseReporter]) -> None:
        """Registers a reporter class on the _reporters attribute."""
        self._reporters[reporter_class.name] = reporter_class

    def register_checker(self, checker: checkers.BaseChecker) -> None:
        """This method auto registers the checker."""
        self._checkers[checker.name].append(checker)
        for message in checker.messages:
            self.msgs_store.register_message(message)
        checker.load_defaults()

    def enable_fail_on_messages(self) -> None:
        """Enable 'fail on' msgs.

        Convert values in config.fail_on (which might be msg category, msg id,
        or symbol) to specific msgs, then enable and flag them for later.
        """
        pass

    def disable_reporters(self) -> None:
        """Disable all reporters."""
        pass

    def _parse_error_mode(self) -> None:
        """Parse the current state of the error mode.

        Error mode: enable only errors; no reports, no persistent.
        """
        pass

    def get_checkers(self) -> list[BaseChecker]:
        """Return all available checkers as an ordered list."""
        pass

    def get_checker_names(self) -> list[str]:
        """Get all the checker names that this linter knows about."""
        pass

    def prepare_checkers(self) -> list[BaseChecker]:
        """Return checkers needed for activated messages and reports."""
        pass

    @staticmethod
    def should_analyze_file(modname: str, path: str, is_argument: bool=False) -> bool:
        """Returns whether a module should be checked.

        This implementation returns True for all python source files (.py and .pyi),
        indicating that all files should be linted.

        Subclasses may override this method to indicate that modules satisfying
        certain conditions should not be linted.

        :param str modname: The name of the module to be checked.
        :param str path: The full path to the source code of the module.
        :param bool is_argument: Whether the file is an argument to pylint or not.
                                 Files which respect this property are always
                                 checked, since the user requested it explicitly.
        :returns: True if the module should be checked.
        """
        pass

    def initialize(self) -> None:
        """Initialize linter for linting.

        This method is called before any linting is done.
        """
        pass

    def _discover_files(self, files_or_modules: Sequence[str]) -> Iterator[str]:
        """Discover python modules and packages in sub-directory.

        Returns iterator of paths to discovered modules and packages.
        """
        pass

    def check(self, files_or_modules: Sequence[str]) -> None:
        """Main checking entry: check a list of files or modules from their name.

        files_or_modules is either a string or list of strings presenting modules to check.
        """
        pass

    def _get_asts(self, fileitems: Iterator[FileItem], data: str | None) -> dict[FileItem, nodes.Module | None]:
        """Get the AST for all given FileItems."""
        pass

    def check_single_file_item(self, file: FileItem) -> None:
        """Check single file item.

        The arguments are the same that are documented in _check_files

        initialize() should be called before calling this method
        """
        pass

    def _lint_files(self, ast_mapping: dict[FileItem, nodes.Module | None], check_astroid_module: Callable[[nodes.Module], bool | None]) -> None:
        """Lint all AST modules from a mapping.."""
        pass

    def _lint_file(self, file: FileItem, module: nodes.Module, check_astroid_module: Callable[[nodes.Module], bool | None]) -> None:
        """Lint a file using the passed utility function check_astroid_module).

        :param FileItem file: data about the file
        :param nodes.Module module: the ast module to lint
        :param Callable check_astroid_module: callable checking an AST taking the following
               arguments
        - ast: AST of the module
        :raises AstroidError: for any failures stemming from astroid
        """
        pass

    def _check_file(self, get_ast: GetAstProtocol, check_astroid_module: Callable[[nodes.Module], bool | None], file: FileItem) -> None:
        """Check a file using the passed utility functions (get_ast and
        check_astroid_module).

        :param callable get_ast: callable returning AST from defined file taking the
                                 following arguments
        - filepath: path to the file to check
        - name: Python module name
        :param callable check_astroid_module: callable checking an AST taking the following
               arguments
        - ast: AST of the module
        :param FileItem file: data about the file
        :raises AstroidError: for any failures stemming from astroid
        """
        pass

    def _get_file_descr_from_stdin(self, filepath: str) -> Iterator[FileItem]:
        """Return file description (tuple of module name, file path, base name) from
        given file path.

        This method is used for creating suitable file description for _check_files when the
        source is standard input.
        """
        pass

    def _iterate_file_descrs(self, files_or_modules: Sequence[str]) -> Iterator[FileItem]:
        """Return generator yielding file descriptions (tuples of module name, file
        path, base name).

        The returned generator yield one item for each Python module that should be linted.
        """
        pass

    def _expand_files(self, files_or_modules: Sequence[str]) -> dict[str, ModuleDescriptionDict]:
        """Get modules and errors from a list of modules and handle errors."""
        pass

    def set_current_module(self, modname: str, filepath: str | None=None) -> None:
        """Set the name of the currently analyzed module and
        init statistics for it.
        """
        pass

    @contextlib.contextmanager
    def _astroid_module_checker(self) -> Iterator[Callable[[nodes.Module], bool | None]]:
        """Context manager for checking ASTs.

        The value in the context is callable accepting AST as its only argument.
        """
        pass

    def get_ast(self, filepath: str, modname: str, data: str | None=None) -> nodes.Module | None:
        """Return an ast(roid) representation of a module or a string.

        :param filepath: path to checked file.
        :param str modname: The name of the module to be checked.
        :param str data: optional contents of the checked file.
        :returns: the AST
        :rtype: astroid.nodes.Module
        :raises AstroidBuildingError: Whenever we encounter an unexpected exception
        """
        pass

    def check_astroid_module(self, ast_node: nodes.Module, walker: ASTWalker, rawcheckers: list[checkers.BaseRawFileChecker], tokencheckers: list[checkers.BaseTokenChecker]) -> bool | None:
        """Check a module from its astroid representation.

        For return value see _check_astroid_module
        """
        pass

    def _check_astroid_module(self, node: nodes.Module, walker: ASTWalker, rawcheckers: list[checkers.BaseRawFileChecker], tokencheckers: list[checkers.BaseTokenChecker]) -> bool | None:
        """Check given AST node with given walker and checkers.

        :param astroid.nodes.Module node: AST node of the module to check
        :param pylint.utils.ast_walker.ASTWalker walker: AST walker
        :param list rawcheckers: List of token checkers to use
        :param list tokencheckers: List of raw checkers to use

        :returns: True if the module was checked, False if ignored,
            None if the module contents could not be parsed
        """
        pass

    def open(self) -> None:
        """Initialize counters."""
        pass

    def generate_reports(self, verbose: bool=False) -> int | None:
        """Close the whole package /module, it's time to make reports !

        if persistent run, pickle results for later comparison
        """
        pass

    def _report_evaluation(self, verbose: bool=False) -> int | None:
        """Make the global evaluation report."""
        pass

    def _add_one_message(self, message_definition: MessageDefinition, line: int | None, node: nodes.NodeNG | None, args: Any | None, confidence: interfaces.Confidence | None, col_offset: int | None, end_lineno: int | None, end_col_offset: int | None) -> None:
        """After various checks have passed a single Message is
        passed to the reporter and added to stats.
        """
        pass

    def add_message(self, msgid: str, line: int | None=None, node: nodes.NodeNG | None=None, args: Any | None=None, confidence: interfaces.Confidence | None=None, col_offset: int | None=None, end_lineno: int | None=None, end_col_offset: int | None=None) -> None:
        """Adds a message given by ID or name.

        If provided, the message string is expanded using args.

        AST checkers must provide the node argument (but may optionally
        provide line if the line number is different), raw and token checkers
        must provide the line argument.
        """
        pass

    def add_ignored_message(self, msgid: str, line: int, node: nodes.NodeNG | None=None, confidence: interfaces.Confidence | None=interfaces.UNDEFINED) -> None:
        """Prepares a message to be added to the ignored message storage.

        Some checks return early in special cases and never reach add_message(),
        even though they would normally issue a message.
        This creates false positives for useless-suppression.
        This function avoids this by adding those message to the ignored msgs attribute
        """
        pass
