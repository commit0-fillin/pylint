"""Classes checker for Python code."""
from __future__ import annotations
from collections import defaultdict
from collections.abc import Callable, Sequence
from functools import cached_property
from itertools import chain, zip_longest
from re import Pattern
from typing import TYPE_CHECKING, Any, NamedTuple, Union
import astroid
from astroid import bases, nodes, util
from astroid.nodes import LocalsDictNodeNG
from astroid.typing import SuccessfulInferenceResult
from pylint.checkers import BaseChecker, utils
from pylint.checkers.utils import PYMETHODS, class_is_abstract, decorated_with, decorated_with_property, get_outer_class, has_known_bases, is_attr_private, is_attr_protected, is_builtin_object, is_comprehension, is_iterable, is_property_setter, is_property_setter_or_deleter, node_frame_class, only_required_for_messages, safe_infer, unimplemented_abstract_methods, uninferable_final_decorators
from pylint.interfaces import HIGH, INFERENCE
from pylint.typing import MessageDefinitionTuple
if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter
_AccessNodes = Union[nodes.Attribute, nodes.AssignAttr]
INVALID_BASE_CLASSES = {'bool', 'range', 'slice', 'memoryview'}
ALLOWED_PROPERTIES = {'bultins.property', 'functools.cached_property'}
BUILTIN_DECORATORS = {'builtins.property', 'builtins.classmethod'}
ASTROID_TYPE_COMPARATORS = {nodes.Const: lambda a, b: a.value == b.value, nodes.ClassDef: lambda a, b: a.qname == b.qname, nodes.Tuple: lambda a, b: a.elts == b.elts, nodes.List: lambda a, b: a.elts == b.elts, nodes.Dict: lambda a, b: a.items == b.items, nodes.Name: lambda a, b: set(a.infer()) == set(b.infer())}

class _CallSignature(NamedTuple):
    args: list[str | None]
    kws: dict[str | None, str | None]
    starred_args: list[str]
    starred_kws: list[str]

class _ParameterSignature(NamedTuple):
    args: list[str]
    kwonlyargs: list[str]
    varargs: str
    kwargs: str

def _definition_equivalent_to_call(definition: _ParameterSignature, call: _CallSignature) -> bool:
    """Check if a definition signature is equivalent to a call."""
    if len(definition.args) != len(call.args):
        return False
    
    if definition.varargs and not call.starred_args:
        return False
    
    if definition.kwargs and not call.starred_kws:
        return False
    
    for def_arg, call_arg in zip(definition.args, call.args):
        if def_arg != call_arg and call_arg is not None:
            return False
    
    for kwarg in definition.kwonlyargs:
        if kwarg not in call.kws:
            return False
    
    return True

def _is_trivial_super_delegation(function: nodes.FunctionDef) -> bool:
    """Check whether a function definition is a method consisting only of a
    call to the same function on the superclass.
    """
    if len(function.body) != 1:
        return False
    
    stmt = function.body[0]
    if not isinstance(stmt, nodes.Return):
        return False
    
    call = stmt.value
    if not isinstance(call, nodes.Call):
        return False
    
    func = call.func
    if not isinstance(func, nodes.Attribute):
        return False
    
    if not isinstance(func.expr, nodes.Call):
        return False
    
    if not isinstance(func.expr.func, nodes.Name) or func.expr.func.name != 'super':
        return False
    
    return func.attrname == function.name

class _DefaultMissing:
    """Sentinel value for missing arg default, use _DEFAULT_MISSING."""
_DEFAULT_MISSING = _DefaultMissing()

def _has_different_parameters_default_value(original: nodes.Arguments, overridden: nodes.Arguments) -> bool:
    """Check if original and overridden methods arguments have different default values.

    Return True if one of the overridden arguments has a default
    value different from the default value of the original argument
    If one of the method doesn't have argument (.args is None)
    return False
    """
    if original.args is None or overridden.args is None:
        return False

    for original_arg, overridden_arg in zip(original.args, overridden.args):
        original_default = original_arg.default if hasattr(original_arg, 'default') else None
        overridden_default = overridden_arg.default if hasattr(overridden_arg, 'default') else None

        if original_default != overridden_default:
            return True

    return False

def _has_different_keyword_only_parameters(original: list[nodes.AssignName], overridden: list[nodes.AssignName]) -> list[str]:
    """Determine if the two methods have different keyword only parameters."""
    original_params = {param.name for param in original}
    overridden_params = {param.name for param in overridden}

    return list(original_params.symmetric_difference(overridden_params))

def _different_parameters(original: nodes.FunctionDef, overridden: nodes.FunctionDef, dummy_parameter_regex: Pattern[str]) -> list[str]:
    """Determine if the two methods have different parameters.

    They are considered to have different parameters if:

       * they have different positional parameters, including different names

       * one of the methods is having variadics, while the other is not

       * they have different keyword only parameters.
    """
    different = []
    original_parameters = original.args
    overridden_parameters = overridden.args

    # Check positional parameters
    for orig_param, overr_param in zip_longest(original_parameters.args or [], overridden_parameters.args or []):
        if orig_param is None:
            if not dummy_parameter_regex.match(overr_param.name):
                different.append(overr_param.name)
        elif overr_param is None:
            if not dummy_parameter_regex.match(orig_param.name):
                different.append(orig_param.name)
        elif orig_param.name != overr_param.name:
            different.append(orig_param.name)

    # Check variadics
    if bool(original_parameters.vararg) != bool(overridden_parameters.vararg):
        different.append('*args')

    if bool(original_parameters.kwarg) != bool(overridden_parameters.kwarg):
        different.append('**kwargs')

    # Check keyword-only parameters
    different.extend(_has_different_keyword_only_parameters(
        original_parameters.kwonlyargs, overridden_parameters.kwonlyargs
    ))

    return different

def _called_in_methods(func: LocalsDictNodeNG, klass: nodes.ClassDef, methods: Sequence[str]) -> bool:
    """Check if the func was called in any of the given methods,
    belonging to the *klass*.

    Returns True if so, False otherwise.
    """
    if not isinstance(func, nodes.FunctionDef):
        return False

    for method in methods:
        if method not in klass.locals:
            continue
        meth_node = klass.locals[method][0]
        for call in meth_node.nodes_of_class(nodes.Call):
            try:
                if call.func.expr.name == 'self' and call.func.attrname == func.name:
                    return True
            except AttributeError:
                continue
    return False

def _is_attribute_property(name: str, klass: nodes.ClassDef) -> bool:
    """Check if the given attribute *name* is a property in the given *klass*.

    It will look for `property` calls or for functions
    with the given name, decorated by `property` or `property`
    subclasses.
    Returns ``True`` if the name is a property in the given klass,
    ``False`` otherwise.
    """
    try:
        attributes = klass.getattr(name)
    except astroid.NotFoundError:
        return False

    for attr in attributes:
        if isinstance(attr, nodes.FunctionDef):
            if decorated_with_property(attr):
                return True
        elif isinstance(attr, nodes.Assign):
            if isinstance(attr.value, nodes.Call):
                func = safe_infer(attr.value.func)
                if (isinstance(func, nodes.ClassDef) and 
                    func.is_subtype_of('builtins.property')):
                    return True

    return False
MSGS: dict[str, MessageDefinitionTuple] = {'F0202': ('Unable to check methods signature (%s / %s)', 'method-check-failed', "Used when Pylint has been unable to check methods signature compatibility for an unexpected reason. Please report this kind if you don't make sense of it."), 'E0202': ('An attribute defined in %s line %s hides this method', 'method-hidden', 'Used when a class defines a method which is hidden by an instance attribute from an ancestor class or set by some client code.'), 'E0203': ('Access to member %r before its definition line %s', 'access-member-before-definition', "Used when an instance member is accessed before it's actually assigned."), 'W0201': ('Attribute %r defined outside __init__', 'attribute-defined-outside-init', 'Used when an instance attribute is defined outside the __init__ method.'), 'W0212': ('Access to a protected member %s of a client class', 'protected-access', "Used when a protected member (i.e. class member with a name beginning with an underscore) is access outside the class or a descendant of the class where it's defined."), 'W0213': ('Flag member %(overlap)s shares bit positions with %(sources)s', 'implicit-flag-alias', 'Used when multiple integer values declared within an enum.IntFlag class share a common bit position.'), 'E0211': ('Method %r has no argument', 'no-method-argument', 'Used when a method which should have the bound instance as first argument has no argument defined.'), 'E0213': ('Method %r should have "self" as first argument', 'no-self-argument', 'Used when a method has an attribute different the "self" as first argument. This is considered as an error since this is a so common convention that you shouldn\'t break it!'), 'C0202': ('Class method %s should have %s as first argument', 'bad-classmethod-argument', 'Used when a class method has a first argument named differently than the value specified in valid-classmethod-first-arg option (default to "cls"), recommended to easily differentiate them from regular instance methods.'), 'C0203': ('Metaclass method %s should have %s as first argument', 'bad-mcs-method-argument', 'Used when a metaclass method has a first argument named differently than the value specified in valid-classmethod-first-arg option (default to "cls"), recommended to easily differentiate them from regular instance methods.'), 'C0204': ('Metaclass class method %s should have %s as first argument', 'bad-mcs-classmethod-argument', 'Used when a metaclass class method has a first argument named differently than the value specified in valid-metaclass-classmethod-first-arg option (default to "mcs"), recommended to easily differentiate them from regular instance methods.'), 'W0211': ('Static method with %r as first argument', 'bad-staticmethod-argument', 'Used when a static method has "self" or a value specified in valid-classmethod-first-arg option or valid-metaclass-classmethod-first-arg option as first argument.'), 'W0221': ('%s %s %r method', 'arguments-differ', 'Used when a method has a different number of arguments than in the implemented interface or in an overridden method. Extra arguments with default values are ignored.'), 'W0222': ('Signature differs from %s %r method', 'signature-differs', 'Used when a method signature is different than in the implemented interface or in an overridden method.'), 'W0223': ('Method %r is abstract in class %r but is not overridden in child class %r', 'abstract-method', 'Used when an abstract method (i.e. raise NotImplementedError) is not overridden in concrete class.'), 'W0231': ('__init__ method from base class %r is not called', 'super-init-not-called', 'Used when an ancestor class method has an __init__ method which is not called by a derived class.'), 'W0233': ('__init__ method from a non direct base class %r is called', 'non-parent-init-called', 'Used when an __init__ method is called on a class which is not in the direct ancestors for the analysed class.'), 'W0246': ('Useless parent or super() delegation in method %r', 'useless-parent-delegation', 'Used whenever we can detect that an overridden method is useless, relying on parent or super() delegation to do the same thing as another method from the MRO.', {'old_names': [('W0235', 'useless-super-delegation')]}), 'W0236': ('Method %r was expected to be %r, found it instead as %r', 'invalid-overridden-method', 'Used when we detect that a method was overridden in a way that does not match its base class which could result in potential bugs at runtime.'), 'W0237': ('%s %s %r method', 'arguments-renamed', 'Used when a method parameter has a different name than in the implemented interface or in an overridden method.'), 'W0238': ('Unused private member `%s.%s`', 'unused-private-member', 'Emitted when a private member of a class is defined but not used.'), 'W0239': ('Method %r overrides a method decorated with typing.final which is defined in class %r', 'overridden-final-method', 'Used when a method decorated with typing.final has been overridden.'), 'W0240': ('Class %r is a subclass of a class decorated with typing.final: %r', 'subclassed-final-class', 'Used when a class decorated with typing.final has been subclassed.'), 'W0244': ('Redefined slots %r in subclass', 'redefined-slots-in-subclass', 'Used when a slot is re-defined in a subclass.'), 'W0245': ('Super call without brackets', 'super-without-brackets', 'Used when a call to super does not have brackets and thus is not an actual call and does not work as expected.'), 'E0236': ('Invalid object %r in __slots__, must contain only non empty strings', 'invalid-slots-object', 'Used when an invalid (non-string) object occurs in __slots__.'), 'E0237': ('Assigning to attribute %r not defined in class slots', 'assigning-non-slot', 'Used when assigning to an attribute not defined in the class slots.'), 'E0238': ('Invalid __slots__ object', 'invalid-slots', 'Used when an invalid __slots__ is found in class. Only a string, an iterable or a sequence is permitted.'), 'E0239': ('Inheriting %r, which is not a class.', 'inherit-non-class', 'Used when a class inherits from something which is not a class.'), 'E0240': ('Inconsistent method resolution order for class %r', 'inconsistent-mro', 'Used when a class has an inconsistent method resolution order.'), 'E0241': ('Duplicate bases for class %r', 'duplicate-bases', 'Duplicate use of base classes in derived classes raise TypeErrors.'), 'E0242': ('Value %r in slots conflicts with class variable', 'class-variable-slots-conflict', 'Used when a value in __slots__ conflicts with a class variable, property or method.'), 'E0243': ("Invalid assignment to '__class__'. Should be a class definition but got a '%s'", 'invalid-class-object', 'Used when an invalid object is assigned to a __class__ property. Only a class is permitted.'), 'E0244': ('Extending inherited Enum class "%s"', 'invalid-enum-extension', 'Used when a class tries to extend an inherited Enum class. Doing so will raise a TypeError at runtime.'), 'R0202': ('Consider using a decorator instead of calling classmethod', 'no-classmethod-decorator', 'Used when a class method is defined without using the decorator syntax.'), 'R0203': ('Consider using a decorator instead of calling staticmethod', 'no-staticmethod-decorator', 'Used when a static method is defined without using the decorator syntax.'), 'C0205': ('Class __slots__ should be a non-string iterable', 'single-string-used-for-slots', 'Used when a class __slots__ is a simple string, rather than an iterable.'), 'R0205': ('Class %r inherits from object, can be safely removed from bases in python3', 'useless-object-inheritance', 'Used when a class inherit from object, which under python3 is implicit, hence can be safely removed from bases.'), 'R0206': ('Cannot have defined parameters for properties', 'property-with-parameters', 'Used when we detect that a property also has parameters, which are useless, given that properties cannot be called with additional arguments.')}

class ScopeAccessMap:
    """Store the accessed variables per scope."""

    def __init__(self) -> None:
        self._scopes: defaultdict[nodes.ClassDef, defaultdict[str, list[_AccessNodes]]] = defaultdict(_scope_default)

    def set_accessed(self, node: _AccessNodes) -> None:
        """Set the given node as accessed."""
        if isinstance(node, (nodes.Attribute, nodes.AssignAttr)):
            frame = node.frame()
            if isinstance(frame, nodes.ClassDef):
                self._scopes[frame][node.attrname].append(node)

    def accessed(self, scope: nodes.ClassDef) -> dict[str, list[_AccessNodes]]:
        """Get the accessed variables for the given scope."""
        return self._scopes[scope]

class ClassChecker(BaseChecker):
    """Checker for class nodes.

    Checks for :
    * methods without self as first argument
    * overridden methods signature
    * access only to existent members via self
    * attributes not defined in the __init__ method
    * unreachable code
    """
    name = 'classes'
    msgs = MSGS
    options = (('defining-attr-methods', {'default': ('__init__', '__new__', 'setUp', 'asyncSetUp', '__post_init__'), 'type': 'csv', 'metavar': '<method names>', 'help': 'List of method names used to declare (i.e. assign) instance attributes.'}), ('valid-classmethod-first-arg', {'default': ('cls',), 'type': 'csv', 'metavar': '<argument names>', 'help': 'List of valid names for the first argument in a class method.'}), ('valid-metaclass-classmethod-first-arg', {'default': ('mcs',), 'type': 'csv', 'metavar': '<argument names>', 'help': 'List of valid names for the first argument in a metaclass class method.'}), ('exclude-protected', {'default': ('_asdict', '_fields', '_replace', '_source', '_make', 'os._exit'), 'type': 'csv', 'metavar': '<protected access exclusions>', 'help': 'List of member names, which should be excluded from the protected access warning.'}), ('check-protected-access-in-special-methods', {'default': False, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Warn about protected attribute access inside special methods'}))

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._accessed = ScopeAccessMap()
        self._first_attrs: list[str | None] = []

    @only_required_for_messages('abstract-method', 'invalid-slots', 'single-string-used-for-slots', 'invalid-slots-object', 'class-variable-slots-conflict', 'inherit-non-class', 'useless-object-inheritance', 'inconsistent-mro', 'duplicate-bases', 'redefined-slots-in-subclass', 'invalid-enum-extension', 'subclassed-final-class', 'implicit-flag-alias')
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """Init visit variable _accessed."""
        self._check_bases_classes(node)
        self._check_slots(node)
        self._check_proper_bases(node)
        self._check_consistent_mro(node)
        self._check_typing_final(node)
        self._check_duplicate_bases(node)
        self._check_redefined_slots(node)
        self._check_enum_extension(node)

    def _check_consistent_mro(self, node: nodes.ClassDef) -> None:
        """Detect that a class has a consistent mro or duplicate bases."""
        pass

    def _check_proper_bases(self, node: nodes.ClassDef) -> None:
        """Detect that a class inherits something which is not
        a class or a type.
        """
        pass

    def _check_typing_final(self, node: nodes.ClassDef) -> None:
        """Detect that a class does not subclass a class decorated with
        `typing.final`.
        """
        pass

    @only_required_for_messages('unused-private-member', 'attribute-defined-outside-init', 'access-member-before-definition')
    def leave_classdef(self, node: nodes.ClassDef) -> None:
        """Checker for Class nodes.

        check that instance attributes are defined in __init__ and check
        access to existent members
        """
        pass

    def _check_unused_private_variables(self, node: nodes.ClassDef) -> None:
        """Check if private variables are never used within a class."""
        pass

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check method arguments, overriding."""
        pass
    visit_asyncfunctiondef = visit_functiondef

    def _check_useless_super_delegation(self, function: nodes.FunctionDef) -> None:
        """Check if the given function node is an useless method override.

        We consider it *useless* if it uses the super() builtin, but having
        nothing additional whatsoever than not implementing the method at all.
        If the method uses super() to delegate an operation to the rest of the MRO,
        and if the method called is the same as the current one, the arguments
        passed to super() are the same as the parameters that were passed to
        this method, then the method could be removed altogether, by letting
        other implementation to take precedence.
        """
        pass

    def _check_redefined_slots(self, node: nodes.ClassDef, slots_node: nodes.NodeNG, slots_list: list[nodes.NodeNG]) -> None:
        """Check if `node` redefines a slot which is defined in an ancestor class."""
        pass

    def leave_functiondef(self, node: nodes.FunctionDef) -> None:
        """On method node, check if this method couldn't be a function.

        ignore class, static and abstract methods, initializer,
        methods overridden from a parent class.
        """
        pass
    leave_asyncfunctiondef = leave_functiondef

    def visit_attribute(self, node: nodes.Attribute) -> None:
        """Check if the getattr is an access to a class member
        if so, register it.

        Also check for access to protected
        class member from outside its class (but ignore __special__
        methods)
        """
        pass

    def _check_super_without_brackets(self, node: nodes.Attribute) -> None:
        """Check if there is a function call on a super call without brackets."""
        pass

    def _check_in_slots(self, node: nodes.AssignAttr) -> None:
        """Check that the given AssignAttr node
        is defined in the class slots.
        """
        pass

    def _check_classmethod_declaration(self, node: nodes.Assign) -> None:
        """Checks for uses of classmethod() or staticmethod().

        When a @classmethod or @staticmethod decorator should be used instead.
        A message will be emitted only if the assignment is at a class scope
        and only if the classmethod's argument belongs to the class where it
        is defined.
        `node` is an assign node.
        """
        pass

    def _check_protected_attribute_access(self, node: nodes.Attribute | nodes.AssignAttr) -> None:
        """Given an attribute access node (set or get), check if attribute
        access is legitimate.

        Call _check_first_attr with node before calling
        this method. Valid cases are:
        * self._attr in a method or cls._attr in a classmethod. Checked by
        _check_first_attr.
        * Klass._attr inside "Klass" class.
        * Klass2._attr inside "Klass" class when Klass2 is a base class of
            Klass.
        """
        pass

    @staticmethod
    def _is_called_inside_special_method(node: nodes.NodeNG) -> bool:
        """Returns true if the node is located inside a special (aka dunder) method."""
        pass

    @staticmethod
    def _is_classmethod(func: LocalsDictNodeNG) -> bool:
        """Check if the given *func* node is a class method."""
        pass

    @staticmethod
    def _is_inferred_instance(expr: nodes.NodeNG, klass: nodes.ClassDef) -> bool:
        """Check if the inferred value of the given *expr* is an instance of
        *klass*.
        """
        pass

    @staticmethod
    def _is_class_or_instance_attribute(name: str, klass: nodes.ClassDef) -> bool:
        """Check if the given attribute *name* is a class or instance member of the
        given *klass*.

        Returns ``True`` if the name is a property in the given klass,
        ``False`` otherwise.
        """
        pass

    def _check_accessed_members(self, node: nodes.ClassDef, accessed: dict[str, list[_AccessNodes]]) -> None:
        """Check that accessed members are defined."""
        pass

    def _check_first_arg_for_type(self, node: nodes.FunctionDef, metaclass: bool) -> None:
        """Check the name of first argument, expect:.

        * 'self' for a regular method
        * 'cls' for a class method or a metaclass regular method (actually
          valid-classmethod-first-arg value)
        * 'mcs' for a metaclass class method (actually
          valid-metaclass-classmethod-first-arg)
        * not one of the above for a static method
        """
        pass

    def _check_bases_classes(self, node: nodes.ClassDef) -> None:
        """Check that the given class node implements abstract methods from
        base classes.
        """
        pass

    def _check_init(self, node: nodes.FunctionDef, klass_node: nodes.ClassDef) -> None:
        """Check that the __init__ method call super or ancestors'__init__
        method (unless it is used for type hinting with `typing.overload`).
        """
        pass

    def _check_signature(self, method1: nodes.FunctionDef, refmethod: nodes.FunctionDef, cls: nodes.ClassDef) -> None:
        """Check that the signature of the two given methods match."""
        pass

    def _uses_mandatory_method_param(self, node: nodes.Attribute | nodes.Assign | nodes.AssignAttr) -> bool:
        """Check that attribute lookup name use first attribute variable name.

        Name is `self` for method, `cls` for classmethod and `mcs` for metaclass.
        """
        pass

    def _is_mandatory_method_param(self, node: nodes.NodeNG) -> bool:
        """Check if nodes.Name corresponds to first attribute variable name.

        Name is `self` for method, `cls` for classmethod and `mcs` for metaclass.
        Static methods return False.
        """
        pass

def _ancestors_to_call(klass_node: nodes.ClassDef, method_name: str='__init__') -> dict[nodes.ClassDef, bases.UnboundMethod]:
    """Return a dictionary where keys are the list of base classes providing
    the queried method, and so that should/may be called from the method node.
    """
    pass
