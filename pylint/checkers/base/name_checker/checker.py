"""Basic checker for Python code."""
from __future__ import annotations
import argparse
import collections
import itertools
import re
import sys
from collections.abc import Iterable
from enum import Enum, auto
from re import Pattern
from typing import TYPE_CHECKING, Tuple
import astroid
from astroid import nodes
from pylint import constants, interfaces
from pylint.checkers import utils
from pylint.checkers.base.basic_checker import _BasicChecker
from pylint.checkers.base.name_checker.naming_style import KNOWN_NAME_TYPES, KNOWN_NAME_TYPES_WITH_STYLE, NAMING_STYLES, _create_naming_options
from pylint.checkers.utils import is_property_deleter, is_property_setter
from pylint.typing import Options
if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter
_BadNamesTuple = Tuple[nodes.NodeNG, str, str, interfaces.Confidence]
DEFAULT_PATTERNS = {'typevar': re.compile('^_{0,2}(?!T[A-Z])(?:[A-Z]+|(?:[A-Z]+[a-z]+)+T?(?<!Type))(?:_co(?:ntra)?)?$'), 'typealias': re.compile('^_{0,2}(?!T[A-Z]|Type)[A-Z]+[a-z0-9]+(?:[A-Z][a-z0-9]+)*$')}
BUILTIN_PROPERTY = 'builtins.property'
TYPE_VAR_QNAME = frozenset(('typing.TypeVar', 'typing_extensions.TypeVar'))

class TypeVarVariance(Enum):
    invariant = auto()
    covariant = auto()
    contravariant = auto()
    double_variant = auto()
    inferred = auto()

def _get_properties(config: argparse.Namespace) -> tuple[set[str], set[str]]:
    """Returns a tuple of property classes and names.

    Property classes are fully qualified, such as 'abc.abstractproperty' and
    property names are the actual names, such as 'abstract_property'.
    """
    property_classes = set(config.property_classes)
    property_names = {prop.rsplit('.', 1)[-1] for prop in property_classes}
    return property_classes, property_names

def _redefines_import(node: nodes.AssignName) -> bool:
    """Detect that the given node (AssignName) is inside an
    exception handler and redefines an import from the tryexcept body.

    Returns True if the node redefines an import, False otherwise.
    """
    current = node
    while current and not isinstance(current.parent, nodes.ExceptHandler):
        current = current.parent
    if not current:
        return False
    
    try_block = current.parent.parent
    if not isinstance(try_block, nodes.TryExcept):
        return False
    
    imports = [
        import_node.names[0][0]
        for import_node in try_block.body
        if isinstance(import_node, (nodes.Import, nodes.ImportFrom))
    ]
    return node.name in imports

def _determine_function_name_type(node: nodes.FunctionDef, config: argparse.Namespace) -> str:
    """Determine the name type whose regex the function's name should match.

    :param node: A function node.
    :param config: Configuration from which to pull additional property classes.

    :returns: One of ('function', 'method', 'attr')
    """
    if not node.is_method():
        return 'function'
    
    if node.decorators:
        property_classes, property_names = _get_properties(config)
        for decorator in node.decorators.nodes:
            if isinstance(decorator, nodes.Name):
                if decorator.name in property_names:
                    return 'attr'
            elif isinstance(decorator, nodes.Call):
                if isinstance(decorator.func, nodes.Name):
                    if decorator.func.name in property_names:
                        return 'attr'
    return 'method'
EXEMPT_NAME_CATEGORIES = {'exempt', 'ignore'}

class NameChecker(_BasicChecker):
    msgs = {'C0103': ('%s name "%s" doesn\'t conform to %s', 'invalid-name', "Used when the name doesn't conform to naming rules associated to its type (constant, variable, class...)."), 'C0104': ('Disallowed name "%s"', 'disallowed-name', 'Used when the name matches bad-names or bad-names-rgxs- (unauthorized names).', {'old_names': [('C0102', 'blacklisted-name')]}), 'C0105': ('Type variable name does not reflect variance%s', 'typevar-name-incorrect-variance', "Emitted when a TypeVar name doesn't reflect its type variance. According to PEP8, it is recommended to add suffixes '_co' and '_contra' to the variables used to declare covariant or contravariant behaviour respectively. Invariant (default) variables do not require a suffix. The message is also emitted when invariant variables do have a suffix."), 'C0131': ('TypeVar cannot be both covariant and contravariant', 'typevar-double-variance', 'Emitted when both the "covariant" and "contravariant" keyword arguments are set to "True" in a TypeVar.'), 'C0132': ('TypeVar name "%s" does not match assigned variable name "%s"', 'typevar-name-mismatch', 'Emitted when a TypeVar is assigned to a variable that does not match its name argument.')}
    _options: Options = (('good-names', {'default': ('i', 'j', 'k', 'ex', 'Run', '_'), 'type': 'csv', 'metavar': '<names>', 'help': 'Good variable names which should always be accepted, separated by a comma.'}), ('good-names-rgxs', {'default': '', 'type': 'regexp_csv', 'metavar': '<names>', 'help': 'Good variable names regexes, separated by a comma. If names match any regex, they will always be accepted'}), ('bad-names', {'default': ('foo', 'bar', 'baz', 'toto', 'tutu', 'tata'), 'type': 'csv', 'metavar': '<names>', 'help': 'Bad variable names which should always be refused, separated by a comma.'}), ('bad-names-rgxs', {'default': '', 'type': 'regexp_csv', 'metavar': '<names>', 'help': 'Bad variable names regexes, separated by a comma. If names match any regex, they will always be refused'}), ('name-group', {'default': (), 'type': 'csv', 'metavar': '<name1:name2>', 'help': "Colon-delimited sets of names that determine each other's naming style when the name regexes allow several styles."}), ('include-naming-hint', {'default': False, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Include a hint for the correct naming format with invalid-name.'}), ('property-classes', {'default': ('abc.abstractproperty',), 'type': 'csv', 'metavar': '<decorator names>', 'help': 'List of decorators that produce properties, such as abc.abstractproperty. Add to this list to register other decorators that produce valid properties. These decorators are taken in consideration only for invalid-name.'}))
    options: Options = _options + _create_naming_options()

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._name_group: dict[str, str] = {}
        self._bad_names: dict[str, dict[str, list[_BadNamesTuple]]] = {}
        self._name_regexps: dict[str, re.Pattern[str]] = {}
        self._name_hints: dict[str, str] = {}
        self._good_names_rgxs_compiled: list[re.Pattern[str]] = []
        self._bad_names_rgxs_compiled: list[re.Pattern[str]] = []
    visit_asyncfunctiondef = visit_functiondef

    @utils.only_required_for_messages('disallowed-name', 'invalid-name', 'typevar-name-incorrect-variance', 'typevar-double-variance', 'typevar-name-mismatch')
    def visit_assignname(self, node: nodes.AssignName) -> None:
        """Check module level assigned names."""
        frame = node.frame()
        assign_type = node.assign_type()

        if isinstance(assign_type, nodes.AugAssign):
            return

        if isinstance(frame, nodes.Module):
            if isinstance(assign_type, nodes.Comprehension):
                self._check_name('inlinevar', node.name, node)
            else:
                if _redefines_import(node):
                    self._check_name('import', node.name, node)
                else:
                    self._check_name('const', node.name, node)
        elif isinstance(frame, nodes.ClassDef):
            if isinstance(assign_type, nodes.Comprehension):
                self._check_name('inlinevar', node.name, node)
            elif isinstance(assign_type, nodes.AssignAttr):
                self._check_name('attr', node.name, node)
            elif isinstance(assign_type, nodes.Assign) and not isinstance(
                utils.safe_infer(assign_type.value), nodes.ClassDef
            ):
                if not node.lineno == frame.lineno:
                    self._check_name('attr', node.name, node)
        elif isinstance(frame, nodes.FunctionDef):
            if isinstance(assign_type, nodes.Comprehension):
                self._check_name('inlinevar', node.name, node)
            else:
                self._check_name('variable', node.name, node)

    def _recursive_check_names(self, args: list[nodes.AssignName]) -> None:
        """Check names in a possibly recursive list <arg>."""
        for arg in args:
            if isinstance(arg, nodes.AssignName):
                self._check_name('argument', arg.name, arg)
            elif isinstance(arg, (nodes.Tuple, nodes.List)):
                self._recursive_check_names(arg.elts)

    def _check_name(self, node_type: str, name: str, node: nodes.NodeNG, confidence: interfaces.Confidence=interfaces.HIGH, disallowed_check_only: bool=False) -> None:
        """Check for a name using the type's regexp."""
        if name in self.config.good_names:
            return
        if name in self.config.bad_names:
            self.add_message('disallowed-name', node=node, args=(name,), confidence=confidence)
            return
        
        if disallowed_check_only:
            return
        
        regexp = self._name_regexps.get(node_type)
        if regexp and not regexp.match(name):
            self.add_message('invalid-name', node=node, args=(node_type, name, regexp.pattern), confidence=confidence)

    @staticmethod
    def _assigns_typevar(node: nodes.NodeNG | None) -> bool:
        """Check if a node is assigning a TypeVar."""
        if not isinstance(node, nodes.Assign):
            return False
        if not isinstance(node.value, nodes.Call):
            return False
        
        inferred = utils.safe_infer(node.value.func)
        if not inferred:
            return False
        
        return (
            isinstance(inferred, nodes.ClassDef)
            and inferred.qname() in constants.TYPE_VAR_QNAME
        )

    @staticmethod
    def _assigns_typealias(node: nodes.NodeNG | None) -> bool:
        """Check if a node is assigning a TypeAlias."""
        if not isinstance(node, nodes.AnnAssign):
            return False
        
        annotation = node.annotation
        if isinstance(annotation, nodes.Subscript):
            annotation = annotation.value
        
        if not isinstance(annotation, nodes.Name):
            return False
        
        return annotation.name == "TypeAlias"

    def _check_typevar(self, name: str, node: nodes.AssignName) -> None:
        """Check for TypeVar lint violations."""
        if not isinstance(node.parent, nodes.Assign):
            return

        call = node.parent.value
        if not isinstance(call, nodes.Call):
            return

        if len(call.args) < 1 or not isinstance(call.args[0], nodes.Const):
            return

        typevar_name = call.args[0].value
        if name != typevar_name:
            self.add_message(
                'typevar-name-mismatch',
                node=node,
                args=(typevar_name, name),
                confidence=interfaces.HIGH,
            )

        if len(call.args) == 1 and not call.keywords:
            return  # Everything is okay

        if len(call.args) > 1 or (call.keywords and 'bound' in call.keywords):
            expected_name = name if name.endswith('_co') or name.endswith('_contra') else f'{name}_co'
            if name != expected_name:
                self.add_message(
                    'typevar-name-incorrect-variance',
                    node=node,
                    args=(' ' + expected_name[len(name):],),
                    confidence=interfaces.HIGH,
                )

        covariant = False
        contravariant = False
        for keyword in call.keywords:
            if keyword.arg == 'covariant' and keyword.value.value:
                covariant = True
            elif keyword.arg == 'contravariant' and keyword.value.value:
                contravariant = True

        if covariant and contravariant:
            self.add_message(
                'typevar-double-variance',
                node=node,
                confidence=interfaces.HIGH,
            )
        elif covariant:
            expected_suffix = '_co'
            if not name.endswith(expected_suffix):
                self.add_message(
                    'typevar-name-incorrect-variance',
                    node=node,
                    args=(expected_suffix,),
                    confidence=interfaces.HIGH,
                )
        elif contravariant:
            expected_suffix = '_contra'
            if not name.endswith(expected_suffix):
                self.add_message(
                    'typevar-name-incorrect-variance',
                    node=node,
                    args=(expected_suffix,),
                    confidence=interfaces.HIGH,
                )
