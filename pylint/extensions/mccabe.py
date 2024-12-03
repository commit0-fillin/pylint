"""Module to add McCabe checker class for pylint."""
from __future__ import annotations
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, TypeVar, Union
from astroid import nodes
from mccabe import PathGraph as Mccabe_PathGraph
from mccabe import PathGraphingAstVisitor as Mccabe_PathGraphingAstVisitor
from pylint import checkers
from pylint.checkers.utils import only_required_for_messages
from pylint.interfaces import HIGH
if TYPE_CHECKING:
    from pylint.lint import PyLinter
_StatementNodes = Union[nodes.Assert, nodes.Assign, nodes.AugAssign, nodes.Delete, nodes.Raise, nodes.Yield, nodes.Import, nodes.Call, nodes.Subscript, nodes.Pass, nodes.Continue, nodes.Break, nodes.Global, nodes.Return, nodes.Expr, nodes.Await]
_SubGraphNodes = Union[nodes.If, nodes.Try, nodes.For, nodes.While]
_AppendableNodeT = TypeVar('_AppendableNodeT', bound=Union[_StatementNodes, nodes.While, nodes.FunctionDef])

class PathGraph(Mccabe_PathGraph):

    def __init__(self, node: _SubGraphNodes | nodes.FunctionDef):
        super().__init__(name='', entity='', lineno=1)
        self.root = node

class PathGraphingAstVisitor(Mccabe_PathGraphingAstVisitor):

    def __init__(self) -> None:
        super().__init__()
        self._bottom_counter = 0
        self.graph: PathGraph | None = None
    visitAsyncFunctionDef = visitFunctionDef
    visitAssert = visitAssign = visitAugAssign = visitDelete = visitRaise = visitYield = visitImport = visitCall = visitSubscript = visitPass = visitContinue = visitBreak = visitGlobal = visitReturn = visitExpr = visitAwait = visitSimpleStatement
    visitAsyncWith = visitWith

    def _subgraph(self, node: _SubGraphNodes, name: str, extra_blocks: Sequence[nodes.ExceptHandler]=()) -> None:
        """Create the subgraphs representing any `if` and `for` statements."""
        if isinstance(node, nodes.If):
            test = self.graph.add_node(node.test)
            self.tail = test
            self._subgraph_parse(node.body, test, extra_blocks)
            if node.orelse:
                orelse = self.graph.add_node("else")
                test.connect(orelse)
                self._subgraph_parse(node.orelse, orelse, extra_blocks)
            else:
                test.connect_exit(self.graph)
        elif isinstance(node, nodes.For):
            for_node = self.graph.add_node(node)
            self.tail = for_node
            self._subgraph_parse(node.body, for_node, extra_blocks)
            for_node.connect_exit(self.graph)
            if node.orelse:
                orelse = self.graph.add_node("else")
                for_node.connect(orelse)
                self._subgraph_parse(node.orelse, orelse, extra_blocks)
        elif isinstance(node, nodes.While):
            while_node = self.graph.add_node(node)
            self.tail = while_node
            self._subgraph_parse(node.body, while_node, extra_blocks)
            while_node.connect_exit(self.graph)
            if node.orelse:
                orelse = self.graph.add_node("else")
                while_node.connect(orelse)
                self._subgraph_parse(node.orelse, orelse, extra_blocks)
        elif isinstance(node, nodes.Try):
            try_node = self.graph.add_node(node)
            self.tail = try_node
            self._subgraph_parse(node.body, try_node, extra_blocks)
            for handler in node.handlers:
                except_node = self.graph.add_node(handler)
                try_node.connect(except_node)
                self._subgraph_parse(handler.body, except_node, extra_blocks)
            if node.orelse:
                orelse = self.graph.add_node("else")
                try_node.connect(orelse)
                self._subgraph_parse(node.orelse, orelse, extra_blocks)
            if node.finalbody:
                finally_node = self.graph.add_node("finally")
                try_node.connect(finally_node)
                self._subgraph_parse(node.finalbody, finally_node, extra_blocks)

    def _subgraph_parse(self, node: _SubGraphNodes, pathnode: _SubGraphNodes, extra_blocks: Sequence[nodes.ExceptHandler]) -> None:
        """Parse the body and any `else` block of `if` and `for` statements."""
        if isinstance(node, (list, tuple)):
            for child in node:
                self.dispatch_node(child)
        elif isinstance(node, nodes.NodeNG):
            self.dispatch_node(node)
        
        if isinstance(pathnode, nodes.NodeNG):
            self.tail = pathnode
        elif pathnode:
            self.tail = self.graph.nodes[pathnode]
        
        for extra in extra_blocks:
            self.dispatch_node(extra)

class McCabeMethodChecker(checkers.BaseChecker):
    """Checks McCabe complexity cyclomatic threshold in methods and functions
    to validate a too complex code.
    """
    name = 'design'
    msgs = {'R1260': ('%s is too complex. The McCabe rating is %d', 'too-complex', 'Used when a method or function is too complex based on McCabe Complexity Cyclomatic')}
    options = (('max-complexity', {'default': 10, 'type': 'int', 'metavar': '<int>', 'help': 'McCabe complexity cyclomatic threshold'}),)

    @only_required_for_messages('too-complex')
    def visit_module(self, node: nodes.Module) -> None:
        """Visit an astroid.Module node to check too complex rating and
        add message if is greater than max_complexity stored from options.
        """
        visitor = PathGraphingAstVisitor()
        visitor.visit(node)
        
        for graph in visitor.graphs.values():
            complexity = graph.complexity()
            if complexity > self.linter.config.max_complexity:
                self.add_message(
                    'too-complex',
                    node=graph.root,
                    args=(graph.entity, complexity),
                )
