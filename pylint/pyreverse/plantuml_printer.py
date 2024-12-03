"""Class to generate files in dot format and image formats supported by Graphviz."""
from __future__ import annotations
from pylint.pyreverse.printer import EdgeType, Layout, NodeProperties, NodeType, Printer
from pylint.pyreverse.utils import get_annotation_label

class PlantUmlPrinter(Printer):
    """Printer for PlantUML diagrams."""
    DEFAULT_COLOR = 'black'
    NODES: dict[NodeType, str] = {NodeType.CLASS: 'class', NodeType.PACKAGE: 'package'}
    ARROWS: dict[EdgeType, str] = {EdgeType.INHERITS: '--|>', EdgeType.ASSOCIATION: '--*', EdgeType.AGGREGATION: '--o', EdgeType.USES: '-->', EdgeType.TYPE_DEPENDENCY: '..>'}

    def _open_graph(self) -> None:
        """Emit the header lines."""
        self.lines.append("@startuml")
        self.lines.append(f"title {self.title}")
        if self.layout:
            self.lines.append(f"left to right direction")

    def emit_node(self, name: str, type_: NodeType, properties: NodeProperties | None=None) -> None:
        """Create a new node.

        Nodes can be classes, packages, participants etc.
        """
        node_type = self.NODES.get(type_, "class")
        node_str = f"{node_type} {name}"
        
        if properties:
            if properties.attrs or properties.methods:
                node_str += " {\n"
                if properties.attrs:
                    for attr in properties.attrs:
                        node_str += f"    {attr}\n"
                if properties.methods:
                    for method in properties.methods:
                        node_str += f"    {method.name}()\n"
                node_str += "}"
            
            if properties.color:
                node_str += f" #{''.join(c for c in properties.color if c.isalnum())}"
        
        self.lines.append(node_str)

    def emit_edge(self, from_node: str, to_node: str, type_: EdgeType, label: str | None=None) -> None:
        """Create an edge from one node to another to display relationships."""
        arrow = self.ARROWS.get(type_, "--")
        edge_str = f"{from_node} {arrow} {to_node}"
        
        if label:
            edge_str += f" : {label}"
        
        self.lines.append(edge_str)

    def _close_graph(self) -> None:
        """Emit the lines needed to properly close the graph."""
        self.lines.append("@enduml")
