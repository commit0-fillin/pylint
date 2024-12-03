"""Functions that creates the basic options for the Run and PyLinter classes."""
from __future__ import annotations
import re
import sys
from typing import TYPE_CHECKING
from pylint import constants, interfaces
from pylint.config.callback_actions import _DisableAction, _DoNothingAction, _EnableAction, _ErrorsOnlyModeAction, _FullDocumentationAction, _GenerateConfigFileAction, _GenerateRCFileAction, _ListCheckGroupsAction, _ListConfidenceLevelsAction, _ListExtensionsAction, _ListMessagesAction, _ListMessagesEnabledAction, _LongHelpAction, _MessageHelpAction, _OutputFormatAction
from pylint.typing import Options
if TYPE_CHECKING:
    from pylint.lint import PyLinter, Run

def _make_linter_options(linter: PyLinter) -> Options:
    """Return the options used in a PyLinter class."""
    return [
        (
            "master",
            {
                "short": "m",
                "metavar": "<module>",
                "type": "string",
                "help": "Specify a configuration file.",
                "action": "callback",
                "callback": linter.cb_set_rcfile,
            },
        ),
        (
            "init-hook",
            {
                "metavar": "<code>",
                "type": "string",
                "help": "Python code to execute, usually for sys.path manipulation such as pygtk.require().",
                "action": "callback",
                "callback": linter.cb_add_hook,
            },
        ),
        (
            "errors-only",
            {
                "short": "E",
                "help": "In error mode, checkers without error messages are disabled and for others, only the error messages are displayed, and no reports are done by default.",
                "action": "callback",
                "callback": _ErrorsOnlyModeAction(linter),
            },
        ),
        (
            "full-documentation",
            {
                "help": "Display a full documentation of all available features and options.",
                "action": "callback",
                "callback": _FullDocumentationAction(linter),
            },
        ),
        (
            "generate-rcfile",
            {
                "help": "Generate a sample configuration file according to the current configuration.",
                "action": "callback",
                "callback": _GenerateRCFileAction(linter),
            },
        ),
        (
            "generate-toml-config",
            {
                "help": "Generate a sample configuration file according to the current configuration.",
                "action": "callback",
                "callback": _GenerateConfigFileAction(linter),
            },
        ),
        (
            "help-msg",
            {
                "metavar": "<msg-id>",
                "type": "string",
                "help": "Display a help message for the given message id and exit. The value may be a comma separated list of message ids.",
                "action": "callback",
                "callback": _MessageHelpAction(linter),
            },
        ),
        (
            "list-msgs",
            {
                "help": "Display a list of all available messages.",
                "action": "callback",
                "callback": _ListMessagesAction(linter),
            },
        ),
        (
            "list-msgs-enabled",
            {
                "help": "Display a list of enabled messages.",
                "action": "callback",
                "callback": _ListMessagesEnabledAction(linter),
            },
        ),
        (
            "list-groups",
            {
                "help": "List pylint's message groups.",
                "action": "callback",
                "callback": _ListCheckGroupsAction(linter),
            },
        ),
        (
            "list-conf-levels",
            {
                "help": "List confidence levels for all messages.",
                "action": "callback",
                "callback": _ListConfidenceLevelsAction(linter),
            },
        ),
        (
            "list-extensions",
            {
                "help": "List available extensions and exit.",
                "action": "callback",
                "callback": _ListExtensionsAction(linter),
            },
        ),
        (
            "long-help",
            {
                "help": "Display long help messages about all available features and options.",
                "action": "callback",
                "callback": _LongHelpAction(linter),
            },
        ),
        (
            "output-format",
            {
                "short": "f",
                "metavar": "<format>",
                "type": "string",
                "group": "Reports",
                "default": "text",
                "choices": linter.formatters.keys(),
                "action": "callback",
                "callback": _OutputFormatAction(linter),
                "help": "Set the output format. Available formats are text, parseable, colorized, json and msvs (visual studio).",
            },
        ),
    ]

def _make_run_options(self: Run) -> Options:
    """Return the options used in a Run class."""
    return [
        (
            "version",
            {
                "short": "v",
                "help": "Display pylint version.",
                "action": "version",
                "version": constants.full_version,
            },
        ),
        (
            "ignore",
            {
                "metavar": "<file>[,<file>...]",
                "type": "csv",
                "short": "i",
                "group": "Messages control",
                "help": "Add files or directories to the blacklist. They should be base names, not paths.",
                "default": constants.DEFAULT_IGNORE_LIST,
            },
        ),
        (
            "ignore-patterns",
            {
                "metavar": "<pattern>[,<pattern>...]",
                "type": "csv",
                "group": "Messages control",
                "default": (),
                "help": "Add files or directories matching the regex patterns to the blacklist. The regex matches against base names, not paths.",
            },
        ),
        (
            "persistent",
            {
                "short": "p",
                "help": "Pickle collected data for later comparisons.",
                "type": "yn",
                "metavar": "<y or n>",
                "action": "callback",
                "callback": self._cb_set_persistent,
                "default": True,
            },
        ),
        (
            "load-plugins",
            {
                "metavar": "<modules>",
                "type": "csv",
                "help": "List of plugins (as comma separated values of python module names) to load, usually to register additional checkers.",
                "action": "callback",
                "callback": self._cb_load_plugins,
            },
        ),
        (
            "output",
            {
                "short": "o",
                "metavar": "<file>",
                "type": "string",
                "group": "Reports",
                "help": "Specify an output file.",
            },
        ),
        (
            "fail-under",
            {
                "metavar": "<score>",
                "type": "float",
                "help": "Specify a score threshold to be exceeded before program exits with error.",
                "default": 10.0,
            },
        ),
        (
            "fail-on",
            {
                "metavar": "<msg ids>",
                "type": "csv",
                "help": "Return non-zero exit code if any of these messages/categories are detected, even if score is above --fail-under value. Syntax same as enable.",
                "default": "",
            },
        ),
        (
            "confidence",
            {
                "metavar": "<levels>",
                "type": "multiple_choice",
                "choices": interfaces.CONFIDENCE_LEVELS,
                "group": "Messages control",
                "help": "Only show warnings with the listed confidence levels. Leave empty to show all. Valid levels: %s." % (", ".join(interfaces.CONFIDENCE_LEVELS),),
            },
        ),
        (
            "enable",
            {
                "metavar": "<msg ids>",
                "type": "csv",
                "short": "e",
                "group": "Messages control",
                "help": "Enable the message, report, category or checker with the given id(s). You can either give multiple identifier separated by comma (,) or put this option multiple time (only on the command line, not in the configuration file where it should appear only once). See also the '--disable' option for examples.",
                "action": "callback",
                "callback": _EnableAction(self),
            },
        ),
        (
            "disable",
            {
                "metavar": "<msg ids>",
                "type": "csv",
                "short": "d",
                "group": "Messages control",
                "help": "Disable the message, report, category or checker with the given id(s). You can either give multiple identifiers separated by comma (,) or put this option multiple times (only on the command line, not in the configuration file where it should appear only once). You can also use '--disable=all' to disable everything first and then re-enable specific checks. For example, if you want to run only the similarities checker, you can use '--disable=all --enable=similarities'. If you want to run only the classes checker, but have no Warning level messages displayed, use '--disable=all --enable=classes --disable=W'.",
                "action": "callback",
                "callback": _DisableAction(self),
            },
        ),
        (
            "msg-template",
            {
                "metavar": "<template>",
                "type": "string",
                "group": "Reports",
                "help": "Template used to display messages. This is a python new-style format string used to format the message information. See doc for all details.",
            },
        ),
        (
            "jobs",
            {
                "short": "j",
                "metavar": "<n-processes>",
                "type": "int",
                "help": "Use multiple processes to speed up Pylint. Specifying 0 will auto-detect the number of processors available to use.",
                "default": 1,
            },
        ),
        (
            "unsafe-load-any-extension",
            {
                "type": "yn",
                "metavar": "<y or n>",
                "default": False,
                "help": "Allow loading of arbitrary C extensions. Extensions are imported into the active Python interpreter and may run arbitrary code.",
            },
        ),
        (
            "limit-inference-results",
            {
                "metavar": "<number-of-results>",
                "type": "int",
                "default": 100,
                "help": "Control the amount of potential inferred values when inferring a single object. This can help the performance when dealing with large functions or complex, nested conditions.",
            },
        ),
        (
            "extension-pkg-allow-list",
            {
                "metavar": "<pkg[,pkg]>",
                "type": "csv",
                "default": [],
                "help": "A comma-separated list of package or module names from where C extensions may be loaded. Extensions are loading into the active Python interpreter and may run arbitrary code.",
            },
        ),
        (
            "suggestion-mode",
            {
                "type": "yn",
                "metavar": "<y or n>",
                "default": True,
                "help": "When enabled, pylint would attempt to guess common misconfiguration and emit user-friendly hints instead of false-positive error messages.",
            },
        ),
        (
            "exit-zero",
            {
                "help": "Always return a 0 (non-error) status code, even if lint errors are found. This is primarily useful in continuous integration scripts.",
                "action": "store_true",
                "default": False,
            },
        ),
        (
            "from-stdin",
            {
                "help": "Interpret the stdin as a python script, whose filename needs to be passed as the module_or_package argument.",
                "action": "store_true",
                "default": False,
            },
        ),
        (
            "recursive",
            {
                "short": "r",
                "help": "Discover python modules and packages in the file system subtree.",
                "action": "store_true",
                "default": False,
            },
        ),
    ]
