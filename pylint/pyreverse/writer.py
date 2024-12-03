"""Utilities for creating diagrams."""
from __future__ import annotations
import argparse
import itertools
import os
from collections import defaultdict
from collections.abc import Iterable
from astroid import modutils, nodes
from pylint.pyreverse.diagrams import ClassDiagram, ClassEntity, DiagramEntity, PackageDiagram, PackageEntity
from pylint.pyreverse.printer import EdgeType, NodeProperties, NodeType, Printer
from pylint.pyreverse.printer_factory import get_printer_for_filetype
from pylint.pyreverse.utils import is_exception

class DiagramWriter:
    """Base class for writing project diagrams."""

    def __init__(self, config: argparse.Namespace) -> None:
        self.config = config
        self.printer_class = get_printer_for_filetype(self.config.output_format)
        self.printer: Printer
        self.file_name = ''
        self.depth = self.config.max_color_depth
        self.available_colors = itertools.cycle(self.config.color_palette)
        self.used_colors: dict[str, str] = {}

    def write(self, diadefs: Iterable[ClassDiagram | PackageDiagram]) -> None:
        """Write files for <project> according to <diadefs>."""
        for diagram in diadefs:
            if isinstance(diagram, PackageDiagram):
                self.write_packages(diagram)
            elif isinstance(diagram, ClassDiagram):
                self.write_classes(diagram)

    def write_packages(self, diagram: PackageDiagram) -> None:
        """Write a package diagram."""
        self.set_printer(f"{diagram.title}.{self.config.output_format}", diagram.title)
        for obj in diagram.modules():
            self.printer.emit_node(obj.title, NodeType.PACKAGE, self.get_package_properties(obj))
        for relation in diagram.relationships.get('depends', []):
            self.printer.emit_edge(relation.from_object.title, relation.to_object.title, EdgeType.USES)
        self.save()

    def write_classes(self, diagram: ClassDiagram) -> None:
        """Write a class diagram."""
        self.set_printer(f"{diagram.title}.{self.config.output_format}", diagram.title)
        for obj in diagram.objects:
            self.printer.emit_node(obj.title, NodeType.CLASS, self.get_class_properties(obj))
        for relation in diagram.relationships.get('inherits', []):
            self.printer.emit_edge(relation.from_object.title, relation.to_object.title, EdgeType.INHERITS)
        for relation in diagram.relationships.get('association', []):
            self.printer.emit_edge(relation.from_object.title, relation.to_object.title, EdgeType.ASSOCIATION, relation.name)
        self.save()

    def set_printer(self, file_name: str, basename: str) -> None:
        """Set printer."""
        self.file_name = file_name
        self.printer = self.printer_class(basename, self.config.layout)

    def get_package_properties(self, obj: PackageEntity) -> NodeProperties:
        """Get label and shape for packages."""
        label = obj.title
        color = self.get_shape_color(obj)
        return NodeProperties(label=label, color=color)

    def get_class_properties(self, obj: ClassEntity) -> NodeProperties:
        """Get label and shape for classes."""
        label = f"{obj.title}|"
        label += r"\l".join(obj.attrs) + r"\l"
        if obj.methods:
            label += "|" + r"\l".join(method.name for method in obj.methods) + r"\l"
        color = self.get_shape_color(obj)
        return NodeProperties(label=label, color=color)

    def get_shape_color(self, obj: DiagramEntity) -> str:
        """Get shape color."""
        if self.depth == 0:
            return "black"
        base_name = obj.node.root().name.split('.')[0]
        if base_name not in self.used_colors:
            self.used_colors[base_name] = next(self.available_colors)
        return self.used_colors[base_name]

    def save(self) -> None:
        """Write to disk."""
        self.printer.generate(self.file_name)
