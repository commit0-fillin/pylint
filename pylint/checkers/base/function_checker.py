"""Function checker for Python code."""
from __future__ import annotations
from itertools import chain
from astroid import nodes
from pylint.checkers import utils
from pylint.checkers.base.basic_checker import _BasicChecker

class FunctionChecker(_BasicChecker):
    """Check if a function definition handles possible side effects."""
    msgs = {'W0135': ('The context used in function %r will not be exited.', 'contextmanager-generator-missing-cleanup', 'Used when a contextmanager is used inside a generator function and the cleanup is not handled.')}

    def _check_contextmanager_generator_missing_cleanup(self, node: nodes.FunctionDef) -> None:
        """Check a FunctionDef to find if it is a generator
        that uses a contextmanager internally.

        If it is, check if the contextmanager is properly cleaned up. Otherwise, add message.

        :param node: FunctionDef node to check
        :type node: nodes.FunctionDef
        """
        if not node.is_generator():
            return

        yield_nodes = list(node.nodes_of_class(nodes.Yield))
        if not yield_nodes:
            return

        if self._node_fails_contextmanager_cleanup(node, yield_nodes):
            self.add_message(
                'contextmanager-generator-missing-cleanup',
                node=node,
                args=(node.name,)
            )

    @staticmethod
    def _node_fails_contextmanager_cleanup(node: nodes.FunctionDef, yield_nodes: list[nodes.Yield]) -> bool:
        """Check if a node fails contextmanager cleanup.

        Current checks for a contextmanager:
            - only if the context manager yields a non-constant value
            - only if the context manager lacks a finally, or does not catch GeneratorExit
            - only if some statement follows the yield, some manually cleanup happens

        :param node: Node to check
        :type node: nodes.FunctionDef
        :return: True if fails, False otherwise
        :param yield_nodes: List of Yield nodes in the function body
        :type yield_nodes: list[nodes.Yield]
        :rtype: bool
        """
        if not yield_nodes:
            return False

        first_yield = yield_nodes[0]
        if isinstance(first_yield.value, nodes.Const):
            return False

        try_finally = next(node.nodes_of_class(nodes.TryFinally), None)
        if try_finally:
            # Check if GeneratorExit is caught in the try block
            for handler in try_finally.handlers:
                if handler.type and handler.type.name == 'GeneratorExit':
                    return False
            
            # Check if there's any cleanup in the finally block
            if try_finally.finalbody:
                return False

        # Check if there are any statements after the yield
        yield_index = node.body.index(first_yield)
        if yield_index < len(node.body) - 1:
            return True

        return False
