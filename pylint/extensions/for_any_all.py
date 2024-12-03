"""Check for use of for loops that only check for a condition."""
from __future__ import annotations
from typing import TYPE_CHECKING
from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.checkers.utils import assigned_bool, only_required_for_messages, returns_bool
from pylint.interfaces import HIGH
if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter

class ConsiderUsingAnyOrAllChecker(BaseChecker):
    name = 'consider-using-any-or-all'
    msgs = {'C0501': ('`for` loop could be `%s`', 'consider-using-any-or-all', 'A for loop that checks for a condition and return a bool can be replaced with any or all.')}

    @staticmethod
    def _if_statement_returns_bool(if_children: list[nodes.NodeNG], node_after_loop: nodes.NodeNG) -> bool:
        """Detect for-loop, if-statement, return pattern:

        Ex:
            def any_uneven(items):
                for item in items:
                    if not item % 2 == 0:
                        return True
                return False
        """
        if len(if_children) != 1 or not isinstance(if_children[0], nodes.Return):
            return False
        
        if_return = if_children[0]
        if not isinstance(if_return.value, nodes.Const) or not isinstance(if_return.value.value, bool):
            return False
        
        if not isinstance(node_after_loop, nodes.Return):
            return False
        
        after_loop_return = node_after_loop
        if not isinstance(after_loop_return.value, nodes.Const) or not isinstance(after_loop_return.value.value, bool):
            return False
        
        return if_return.value.value != after_loop_return.value.value

    @staticmethod
    def _assigned_reassigned_returned(node: nodes.For, if_children: list[nodes.NodeNG], node_after_loop: nodes.NodeNG) -> bool:
        """Detect boolean-assign, for-loop, re-assign, return pattern:

        Ex:
            def check_lines(lines, max_chars):
                long_line = False
                for line in lines:
                    if len(line) > max_chars:
                        long_line = True
                    # no elif / else statement
                return long_line
        """
        if not isinstance(node.parent, nodes.FunctionDef):
            return False
        
        function_body = node.parent.body
        if len(function_body) < 3:
            return False
        
        first_assign = function_body[0]
        if not isinstance(first_assign, nodes.Assign) or not assigned_bool(first_assign):
            return False
        
        target_name = first_assign.targets[0].name
        
        if len(if_children) != 1 or not isinstance(if_children[0], nodes.Assign):
            return False
        
        reassign = if_children[0]
        if not isinstance(reassign.targets[0], nodes.AssignName) or reassign.targets[0].name != target_name:
            return False
        
        if not isinstance(reassign.value, nodes.Const) or not isinstance(reassign.value.value, bool):
            return False
        
        if not isinstance(node_after_loop, nodes.Return):
            return False
        
        return_node = node_after_loop
        if not isinstance(return_node.value, nodes.Name) or return_node.value.name != target_name:
            return False
        
        return True

    @staticmethod
    def _build_suggested_string(node: nodes.For, final_return_bool: bool) -> str:
        """When a nodes.For node can be rewritten as an any/all statement, return a
        suggestion for that statement.

        'final_return_bool' is the boolean literal returned after the for loop if all
        conditions fail.
        """
        func = "any" if not final_return_bool else "all"
        iter_name = node.iter.as_string()
        
        if isinstance(node.body[0], nodes.If):
            test = node.body[0].test.as_string()
            if func == "all":
                test = f"not ({test})"
        else:
            assign = node.body[0].body[0]
            test = assign.value.as_string()
            if func == "any":
                test = f"not ({test})"
        
        return f"{func}({test} for {node.target.as_string()} in {iter_name})"
