"""Class to generate files in mermaidjs format."""
from __future__ import annotations
from pylint.pyreverse.printer import EdgeType, NodeProperties, NodeType, Printer
from pylint.pyreverse.utils import get_annotation_label

class MermaidJSPrinter(Printer):
    """Printer for MermaidJS diagrams."""
    DEFAULT_COLOR = 'black'
    NODES: dict[NodeType, str] = {NodeType.CLASS: 'class', NodeType.PACKAGE: 'class'}
    ARROWS: dict[EdgeType, str] = {EdgeType.INHERITS: '--|>', EdgeType.ASSOCIATION: '--*', EdgeType.AGGREGATION: '--o', EdgeType.USES: '-->', EdgeType.TYPE_DEPENDENCY: '..>'}

    def _open_graph(self) -> None:
        """Emit the header lines."""
        self.lines.append("classDiagram")
        if self.layout:
            self.lines.append(f"    direction {self.layout.value}")

    def emit_node(self, name: str, type_: NodeType, properties: NodeProperties | None=None) -> None:
        """Create a new node.

        Nodes can be classes, packages, participants etc.
        """
        node_str = f"    {self.NODES[type_]} {name}"
        if properties and properties.label:
            node_str += f' "{properties.label}"'
        self.lines.append(node_str)

        if properties and properties.attrs:
            for attr in properties.attrs:
                self.lines.append(f"    {name} : {attr}")

        if properties and properties.methods:
            for method in properties.methods:
                self.lines.append(f"    {name} : {method.name}()")

    def emit_edge(self, from_node: str, to_node: str, type_: EdgeType, label: str | None=None) -> None:
        """Create an edge from one node to another to display relationships."""
        edge_str = f"    {from_node} {self.ARROWS[type_]} {to_node}"
        if label:
            edge_str += f" : {label}"
        self.lines.append(edge_str)

    def _close_graph(self) -> None:
        """Emit the lines needed to properly close the graph."""
        # MermaidJS doesn't require any specific closing, so we'll just pass
        pass

class HTMLMermaidJSPrinter(MermaidJSPrinter):
    """Printer for MermaidJS diagrams wrapped in a html boilerplate."""
    HTML_OPEN_BOILERPLATE = '<html>\n  <body>\n    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>\n      <div class="mermaid">\n    '
    HTML_CLOSE_BOILERPLATE = '\n       </div>\n  </body>\n</html>\n'
    GRAPH_INDENT_LEVEL = 4
