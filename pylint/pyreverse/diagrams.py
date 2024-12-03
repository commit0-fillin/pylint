"""Diagram objects."""
from __future__ import annotations
from collections.abc import Iterable
from typing import Any
import astroid
from astroid import nodes, util
from pylint.checkers.utils import decorated_with_property, in_type_checking_block
from pylint.pyreverse.utils import FilterMixIn

class Figure:
    """Base class for counter handling."""

    def __init__(self) -> None:
        self.fig_id: str = ''

class Relationship(Figure):
    """A relationship from an object in the diagram to another."""

    def __init__(self, from_object: DiagramEntity, to_object: DiagramEntity, relation_type: str, name: str | None=None):
        super().__init__()
        self.from_object = from_object
        self.to_object = to_object
        self.type = relation_type
        self.name = name

class DiagramEntity(Figure):
    """A diagram object, i.e. a label associated to an astroid node."""
    default_shape = ''

    def __init__(self, title: str='No name', node: nodes.NodeNG | None=None) -> None:
        super().__init__()
        self.title = title
        self.node: nodes.NodeNG = node or nodes.NodeNG(lineno=None, col_offset=None, end_lineno=None, end_col_offset=None, parent=None)
        self.shape = self.default_shape

class PackageEntity(DiagramEntity):
    """A diagram object representing a package."""
    default_shape = 'package'

class ClassEntity(DiagramEntity):
    """A diagram object representing a class."""
    default_shape = 'class'

    def __init__(self, title: str, node: nodes.ClassDef) -> None:
        super().__init__(title=title, node=node)
        self.attrs: list[str] = []
        self.methods: list[nodes.FunctionDef] = []

class ClassDiagram(Figure, FilterMixIn):
    """Main class diagram handling."""
    TYPE = 'class'

    def __init__(self, title: str, mode: str) -> None:
        FilterMixIn.__init__(self, mode)
        Figure.__init__(self)
        self.title = title
        self.objects: list[Any] = []
        self.relationships: dict[str, list[Relationship]] = {}
        self._nodes: dict[nodes.NodeNG, DiagramEntity] = {}

    def add_relationship(self, from_object: DiagramEntity, to_object: DiagramEntity, relation_type: str, name: str | None=None) -> None:
        """Create a relationship."""
        relationship = Relationship(from_object, to_object, relation_type, name)
        self.relationships.setdefault(relation_type, []).append(relationship)

    def get_relationship(self, from_object: DiagramEntity, relation_type: str) -> Relationship | None:
        """Return a relationship or None."""
        for relationship in self.relationships.get(relation_type, []):
            if relationship.from_object == from_object:
                return relationship
        return None

    def get_attrs(self, node: nodes.ClassDef) -> list[str]:
        """Return visible attributes, possibly with class name."""
        attrs = []
        for attr in node.instance_attrs.items():
            if not self.show_attr(attr):
                continue
            name = attr[0]
            if in_type_checking_block(attr[1][0]):
                continue
            if not decorated_with_property(node, name):
                attrs.append(name)
        return attrs

    def get_methods(self, node: nodes.ClassDef) -> list[nodes.FunctionDef]:
        """Return visible methods."""
        methods = []
        for method in node.mymethods():
            if self.show_attr(method):
                methods.append(method)
        return methods

    def add_object(self, title: str, node: nodes.ClassDef) -> None:
        """Create a diagram object."""
        entity = ClassEntity(title, node)
        entity.attrs = self.get_attrs(node)
        entity.methods = self.get_methods(node)
        self.objects.append(entity)
        self._nodes[node] = entity

    def class_names(self, nodes_lst: Iterable[nodes.NodeNG]) -> list[str]:
        """Return class names if needed in diagram."""
        return [n.name for n in nodes_lst if isinstance(n, nodes.ClassDef) and self.has_node(n)]

    def has_node(self, node: nodes.NodeNG) -> bool:
        """Return true if the given node is included in the diagram."""
        return node in self._nodes

    def object_from_node(self, node: nodes.NodeNG) -> DiagramEntity:
        """Return the diagram object mapped to node."""
        return self._nodes[node]

    def classes(self) -> list[ClassEntity]:
        """Return all class nodes in the diagram."""
        return [o for o in self.objects if isinstance(o, ClassEntity)]

    def classe(self, name: str) -> ClassEntity:
        """Return a class by its name, raise KeyError if not found."""
        for klass in self.classes():
            if klass.node.name == name:
                return klass
        raise KeyError(f"No class named {name}")

    def extract_relationships(self) -> None:
        """Extract relationships between nodes in the diagram."""
        for obj in self.classes():
            node = obj.node
            for parent in node.bases:
                parent_name = parent.as_string()
                try:
                    parent_node = self.classe(parent_name)
                    self.add_relationship(obj, parent_node, "inherits")
                except KeyError:
                    continue

class PackageDiagram(ClassDiagram):
    """Package diagram handling."""
    TYPE = 'package'

    def modules(self) -> list[PackageEntity]:
        """Return all module nodes in the diagram."""
        return [o for o in self.objects if isinstance(o, PackageEntity)]

    def module(self, name: str) -> PackageEntity:
        """Return a module by its name, raise KeyError if not found."""
        for module in self.modules():
            if module.node.name == name:
                return module
        raise KeyError(f"No module named {name}")

    def add_object(self, title: str, node: nodes.Module) -> None:
        """Create a diagram object."""
        entity = PackageEntity(title, node)
        self.objects.append(entity)
        self._nodes[node] = entity

    def get_module(self, name: str, node: nodes.Module) -> PackageEntity:
        """Return a module by its name, looking also for relative imports;
        raise KeyError if not found.
        """
        try:
            return self.module(name)
        except KeyError:
            if name.startswith('.'):
                package = node.root().name
                return self.module(f"{package}{name}")
            raise

    def add_from_depend(self, node: nodes.ImportFrom, from_module: str) -> None:
        """Add dependencies created by from-imports."""
        try:
            imported_module = self.get_module(from_module, node)
        except KeyError:
            return
        
        if isinstance(node.parent, nodes.Module):
            for name, _ in node.names:
                self.add_relationship(self.object_from_node(node.parent),
                                      imported_module,
                                      "depends")

    def extract_relationships(self) -> None:
        """Extract relationships between nodes in the diagram."""
        for module in self.modules():
            node = module.node
            for dep in node.deps:
                if isinstance(dep, nodes.Import):
                    for name, _ in dep.names:
                        try:
                            imported_module = self.get_module(name, node)
                            self.add_relationship(module, imported_module, "depends")
                        except KeyError:
                            continue
                elif isinstance(dep, nodes.ImportFrom):
                    self.add_from_depend(dep, dep.modname)
