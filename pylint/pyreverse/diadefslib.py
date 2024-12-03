"""Handle diagram generation options for class diagram or default diagrams."""
from __future__ import annotations
import argparse
from collections.abc import Generator
from typing import Any
import astroid
from astroid import nodes
from astroid.modutils import is_stdlib_module
from pylint.pyreverse.diagrams import ClassDiagram, PackageDiagram
from pylint.pyreverse.inspector import Linker, Project
from pylint.pyreverse.utils import LocalsVisitor

class DiaDefGenerator:
    """Handle diagram generation options."""

    def __init__(self, linker: Linker, handler: DiadefsHandler) -> None:
        """Common Diagram Handler initialization."""
        self.config = handler.config
        self.module_names: bool = False
        self._set_default_options()
        self.linker = linker
        self.classdiagram: ClassDiagram

    def get_title(self, node: nodes.ClassDef) -> str:
        """Get title for objects."""
        return node.name if self.module_names else node.qname()

    def _set_option(self, option: bool | None) -> bool:
        """Activate some options if not explicitly deactivated."""
        return option if option is not None else self.config.all_ancestors

    def _set_default_options(self) -> None:
        """Set different default options with _default dictionary."""
        self.show_ancestors = self._set_option(self.config.show_ancestors)
        self.all_ancestors = self._set_option(self.config.all_ancestors)
        self.show_associated = self._set_option(self.config.show_associated)
        self.show_builtin = self._set_option(self.config.show_builtin)
        self.module_names = False

    def _get_levels(self) -> tuple[int, int]:
        """Help function for search levels."""
        return (self.config.max_inference_depth, self.config.max_inference_depth)

    def show_node(self, node: nodes.ClassDef) -> bool:
        """Determine if node should be shown based on config."""
        if isinstance(node, nodes.ClassDef):
            if self.show_builtin or not node.root().name.startswith('builtins'):
                return self.classdiagram.show_attr(node)
        return False

    def add_class(self, node: nodes.ClassDef) -> None:
        """Visit one class and add it to diagram."""
        pass

    def get_ancestors(self, node: nodes.ClassDef, level: int) -> Generator[nodes.ClassDef, None, None]:
        """Return ancestor nodes of a class node."""
        pass

    def get_associated(self, klass_node: nodes.ClassDef, level: int) -> Generator[nodes.ClassDef, None, None]:
        """Return associated nodes of a class node."""
        pass

    def extract_classes(self, klass_node: nodes.ClassDef, anc_level: int, association_level: int) -> None:
        """Extract recursively classes related to klass_node."""
        pass

class DefaultDiadefGenerator(LocalsVisitor, DiaDefGenerator):
    """Generate minimum diagram definition for the project :

    * a package diagram including project's modules
    * a class diagram including project's classes
    """

    def __init__(self, linker: Linker, handler: DiadefsHandler) -> None:
        DiaDefGenerator.__init__(self, linker, handler)
        LocalsVisitor.__init__(self)

    def visit_project(self, node: Project) -> None:
        """Visit a pyreverse.utils.Project node.

        create a diagram definition for packages
        """
        pass

    def leave_project(self, _: Project) -> Any:
        """Leave the pyreverse.utils.Project node.

        return the generated diagram definition
        """
        pass

    def visit_module(self, node: nodes.Module) -> None:
        """Visit an astroid.Module node.

        add this class to the package diagram definition
        """
        pass

    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """Visit an astroid.Class node.

        add this class to the class diagram definition
        """
        pass

    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        """Visit astroid.ImportFrom  and catch modules for package diagram."""
        pass

class ClassDiadefGenerator(DiaDefGenerator):
    """Generate a class diagram definition including all classes related to a
    given class.
    """

    def class_diagram(self, project: Project, klass: nodes.ClassDef) -> ClassDiagram:
        """Return a class diagram definition for the class and related classes."""
        pass

class DiadefsHandler:
    """Get diagram definitions from user (i.e. xml files) or generate them."""

    def __init__(self, config: argparse.Namespace) -> None:
        self.config = config

    def get_diadefs(self, project: Project, linker: Linker) -> list[ClassDiagram]:
        """Get the diagram's configuration data.

        :param project:The pyreverse project
        :type project: pyreverse.utils.Project
        :param linker: The linker
        :type linker: pyreverse.inspector.Linker(IdGeneratorMixIn, LocalsVisitor)

        :returns: The list of diagram definitions
        :rtype: list(:class:`pylint.pyreverse.diagrams.ClassDiagram`)
        """
        pass
