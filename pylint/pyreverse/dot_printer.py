"""Class to generate files in dot format and image formats supported by Graphviz."""
from __future__ import annotations
import os
import subprocess
import tempfile
from enum import Enum
from pathlib import Path
from astroid import nodes
from pylint.pyreverse.printer import EdgeType, Layout, NodeProperties, NodeType, Printer
from pylint.pyreverse.utils import get_annotation_label

class HTMLLabels(Enum):
    LINEBREAK_LEFT = '<br ALIGN="LEFT"/>'
ALLOWED_CHARSETS: frozenset[str] = frozenset(('utf-8', 'iso-8859-1', 'latin1'))
SHAPES: dict[NodeType, str] = {NodeType.PACKAGE: 'box', NodeType.CLASS: 'record'}
ARROWS: dict[EdgeType, dict[str, str]] = {EdgeType.INHERITS: {'arrowtail': 'none', 'arrowhead': 'empty'}, EdgeType.ASSOCIATION: {'fontcolor': 'green', 'arrowtail': 'none', 'arrowhead': 'diamond', 'style': 'solid'}, EdgeType.AGGREGATION: {'fontcolor': 'green', 'arrowtail': 'none', 'arrowhead': 'odiamond', 'style': 'solid'}, EdgeType.USES: {'arrowtail': 'none', 'arrowhead': 'open'}, EdgeType.TYPE_DEPENDENCY: {'arrowtail': 'none', 'arrowhead': 'open', 'style': 'dashed'}}

class DotPrinter(Printer):
    DEFAULT_COLOR = 'black'

    def __init__(self, title: str, layout: Layout | None=None, use_automatic_namespace: bool | None=None):
        layout = layout or Layout.BOTTOM_TO_TOP
        self.charset = 'utf-8'
        super().__init__(title, layout, use_automatic_namespace)

    def _open_graph(self) -> None:
        """Emit the header lines."""
        self.lines.append(f'digraph "{self.title}" {{')
        self.lines.append(f'    charset="{self.charset}";')
        if self.layout:
            self.lines.append(f'    rankdir={self.layout.value};')
        self._inc_indent()

    def emit_node(self, name: str, type_: NodeType, properties: NodeProperties | None=None) -> None:
        """Create a new node.

        Nodes can be classes, packages, participants etc.
        """
        node_str = f'{self._indent}"{name}" ['
        attrs = [f'shape="{SHAPES[type_]}"']
        if properties:
            if properties.label:
                attrs.append(f'label="{properties.label}"')
            if properties.color:
                attrs.append(f'color="{properties.color}"')
            if properties.fontcolor:
                attrs.append(f'fontcolor="{properties.fontcolor}"')
        node_str += ', '.join(attrs) + '];'
        self.lines.append(node_str)

    def emit_edge(self, from_node: str, to_node: str, type_: EdgeType, label: str | None=None) -> None:
        """Create an edge from one node to another to display relationships."""
        edge_str = f'{self._indent}"{from_node}" -> "{to_node}"'
        attrs = ARROWS[type_].copy()
        if label:
            attrs['label'] = f'"{label}"'
        attr_str = ', '.join(f'{k}={v}' for k, v in attrs.items())
        edge_str += f' [{attr_str}];'
        self.lines.append(edge_str)

    def _close_graph(self) -> None:
        """Emit the lines needed to properly close the graph."""
        self._dec_indent()
        self.lines.append('}')
