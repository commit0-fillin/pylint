"""Visitor doing some post-processing on the astroid tree.

Try to resolve definitions (namespace) dictionary, relationship...
"""
from __future__ import annotations
import collections
import os
import traceback
from abc import ABC, abstractmethod
from typing import Callable, Optional
import astroid
from astroid import nodes
from pylint import constants
from pylint.pyreverse import utils
_WrapperFuncT = Callable[[Callable[[str], nodes.Module], str, bool], Optional[nodes.Module]]

class IdGeneratorMixIn:
    """Mixin adding the ability to generate integer uid."""

    def __init__(self, start_value: int=0) -> None:
        self.id_count = start_value

    def init_counter(self, start_value: int=0) -> None:
        """Init the id counter."""
        pass

    def generate_id(self) -> int:
        """Generate a new identifier."""
        pass

class Project:
    """A project handle a set of modules / packages."""

    def __init__(self, name: str=''):
        self.name = name
        self.uid: int | None = None
        self.path: str = ''
        self.modules: list[nodes.Module] = []
        self.locals: dict[str, nodes.Module] = {}
        self.__getitem__ = self.locals.__getitem__
        self.__iter__ = self.locals.__iter__
        self.values = self.locals.values
        self.keys = self.locals.keys
        self.items = self.locals.items

    def __repr__(self) -> str:
        return f'<Project {self.name!r} at {id(self)} ({len(self.modules)} modules)>'

class Linker(IdGeneratorMixIn, utils.LocalsVisitor):
    """Walk on the project tree and resolve relationships.

    According to options the following attributes may be
    added to visited nodes:

    * uid,
      a unique identifier for the node (on astroid.Project, astroid.Module,
      astroid.Class and astroid.locals_type). Only if the linker
      has been instantiated with tag=True parameter (False by default).

    * Function
      a mapping from locals names to their bounded value, which may be a
      constant like a string or an integer, or an astroid node
      (on astroid.Module, astroid.Class and astroid.Function).

    * instance_attrs_type
      as locals_type but for klass member attributes (only on astroid.Class)

    * associations_type
      as instance_attrs_type but for association relationships

    * aggregations_type
      as instance_attrs_type but for aggregations relationships
    """

    def __init__(self, project: Project, tag: bool=False) -> None:
        IdGeneratorMixIn.__init__(self)
        utils.LocalsVisitor.__init__(self)
        self.tag = tag
        self.project = project
        self.associations_handler = AggregationsHandler()
        self.associations_handler.set_next(OtherAssociationsHandler())

    def visit_project(self, node: Project) -> None:
        """Visit a pyreverse.utils.Project node.

        * optionally tag the node with a unique id
        """
        pass

    def visit_module(self, node: nodes.Module) -> None:
        """Visit an astroid.Module node.

        * set the locals_type mapping
        * set the depends mapping
        * optionally tag the node with a unique id
        """
        pass

    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """Visit an astroid.Class node.

        * set the locals_type and instance_attrs_type mappings
        * optionally tag the node with a unique id
        """
        pass

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Visit an astroid.Function node.

        * set the locals_type mapping
        * optionally tag the node with a unique id
        """
        pass

    def visit_assignname(self, node: nodes.AssignName) -> None:
        """Visit an astroid.AssignName node.

        handle locals_type
        """
        pass

    @staticmethod
    def handle_assignattr_type(node: nodes.AssignAttr, parent: nodes.ClassDef) -> None:
        """Handle an astroid.assignattr node.

        handle instance_attrs_type
        """
        pass

    def visit_import(self, node: nodes.Import) -> None:
        """Visit an astroid.Import node.

        resolve module dependencies
        """
        pass

    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        """Visit an astroid.ImportFrom node.

        resolve module dependencies
        """
        pass

    def compute_module(self, context_name: str, mod_path: str) -> bool:
        """Should the module be added to dependencies ?"""
        pass

    def _imported_module(self, node: nodes.Import | nodes.ImportFrom, mod_path: str, relative: bool) -> None:
        """Notify an imported module, used to analyze dependencies."""
        pass

class AssociationHandlerInterface(ABC):
    pass

class AbstractAssociationHandler(AssociationHandlerInterface):
    """
    Chain of Responsibility for handling types of association, useful
    to expand in the future if we want to add more distinct associations.

    Every link of the chain checks if it's a certain type of association.
    If no association is found it's set as a generic association in `associations_type`.

    The default chaining behavior is implemented inside the base handler
    class.
    """
    _next_handler: AssociationHandlerInterface

class AggregationsHandler(AbstractAssociationHandler):
    pass

class OtherAssociationsHandler(AbstractAssociationHandler):
    pass

def project_from_files(files: list[str], func_wrapper: _WrapperFuncT=_astroid_wrapper, project_name: str='no name', black_list: tuple[str, ...]=constants.DEFAULT_IGNORE_LIST, verbose: bool=False) -> Project:
    """Return a Project from a list of files or modules."""
    pass