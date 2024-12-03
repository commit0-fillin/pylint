from __future__ import annotations
import astroid
from astroid import nodes
from pylint import checkers
from pylint.checkers import utils
from pylint.interfaces import HIGH, INFERENCE

class RecommendationChecker(checkers.BaseChecker):
    name = 'refactoring'
    msgs = {'C0200': ('Consider using enumerate instead of iterating with range and len', 'consider-using-enumerate', 'Emitted when code that iterates with range and len is encountered. Such code can be simplified by using the enumerate builtin.'), 'C0201': ('Consider iterating the dictionary directly instead of calling .keys()', 'consider-iterating-dictionary', 'Emitted when the keys of a dictionary are iterated through the ``.keys()`` method or when ``.keys()`` is used for a membership check. It is enough to iterate through the dictionary itself, ``for key in dictionary``. For membership checks, ``if key in dictionary`` is faster.'), 'C0206': ('Consider iterating with .items()', 'consider-using-dict-items', 'Emitted when iterating over the keys of a dictionary and accessing the value by index lookup. Both the key and value can be accessed by iterating using the .items() method of the dictionary instead.'), 'C0207': ('Use %s instead', 'use-maxsplit-arg', 'Emitted when accessing only the first or last element of str.split(). The first and last element can be accessed by using str.split(sep, maxsplit=1)[0] or str.rsplit(sep, maxsplit=1)[-1] instead.'), 'C0208': ('Use a sequence type when iterating over values', 'use-sequence-for-iteration', 'When iterating over values, sequence types (e.g., ``lists``, ``tuples``, ``ranges``) are more efficient than ``sets``.'), 'C0209': ('Formatting a regular string which could be an f-string', 'consider-using-f-string', 'Used when we detect a string that is being formatted with format() or % which could potentially be an f-string. The use of f-strings is preferred. Requires Python 3.6 and ``py-version >= 3.6``.')}

    def _check_use_maxsplit_arg(self, node: nodes.Call) -> None:
        """Add message when accessing first or last elements of a str.split() or
        str.rsplit().
        """
        if not isinstance(node.func, nodes.Attribute):
            return
        
        if node.func.attrname not in ('split', 'rsplit'):
            return
        
        if len(node.args) > 1 or node.keywords:
            return
        
        parent = node.parent
        if not isinstance(parent, nodes.Subscript):
            return
        
        slice_value = parent.slice
        if not isinstance(slice_value, nodes.Const):
            return
        
        index = slice_value.value
        if index not in (0, -1):
            return
        
        method = 'split' if node.func.attrname == 'split' else 'rsplit'
        suggestion = f"str.{method}(sep, maxsplit=1)[{index}]"
        self.add_message('use-maxsplit-arg', node=parent, args=(suggestion,))

    def _check_consider_using_enumerate(self, node: nodes.For) -> None:
        """Emit a convention whenever range and len are used for indexing."""
        if not isinstance(node.iter, nodes.Call):
            return
        
        if not isinstance(node.iter.func, nodes.Name) or node.iter.func.name != 'range':
            return
        
        if len(node.iter.args) != 1:
            return
        
        arg = node.iter.args[0]
        if not isinstance(arg, nodes.Call) or not isinstance(arg.func, nodes.Name) or arg.func.name != 'len':
            return
        
        if len(arg.args) != 1:
            return
        
        iterated = arg.args[0]
        if not isinstance(iterated, nodes.Name):
            return
        
        if not isinstance(node.target, nodes.Name):
            return
        
        self.add_message('consider-using-enumerate', node=node)

    def _check_consider_using_dict_items(self, node: nodes.For) -> None:
        """Add message when accessing dict values by index lookup."""
        if not isinstance(node.iter, nodes.Call):
            return
        
        if not isinstance(node.iter.func, nodes.Attribute) or node.iter.func.attrname != 'keys':
            return
        
        if not isinstance(node.target, nodes.Name):
            return
        
        for child in node.body:
            if not isinstance(child, nodes.Assign):
                continue
            
            if not isinstance(child.targets[0], nodes.Name):
                continue
            
            if not isinstance(child.value, nodes.Subscript):
                continue
            
            if not isinstance(child.value.value, nodes.Name) or child.value.value.name != node.iter.func.expr.name:
                continue
            
            if not isinstance(child.value.slice, nodes.Name) or child.value.slice.name != node.target.name:
                continue
            
            self.add_message('consider-using-dict-items', node=node)
            break

    def _check_consider_using_dict_items_comprehension(self, node: nodes.Comprehension) -> None:
        """Add message when accessing dict values by index lookup."""
        if not isinstance(node.iter, nodes.Call):
            return
        
        if not isinstance(node.iter.func, nodes.Attribute) or node.iter.func.attrname != 'keys':
            return
        
        if not isinstance(node.target, nodes.Name):
            return
        
        parent = node.parent
        if not isinstance(parent, (nodes.DictComp, nodes.ListComp, nodes.SetComp, nodes.GeneratorExp)):
            return
        
        if isinstance(parent.elt, nodes.Tuple):
            if len(parent.elt.elts) != 2:
                return
            
            key, value = parent.elt.elts
            if not isinstance(key, nodes.Name) or key.name != node.target.name:
                return
            
            if not isinstance(value, nodes.Subscript):
                return
            
            if not isinstance(value.value, nodes.Name) or value.value.name != node.iter.func.expr.name:
                return
            
            if not isinstance(value.slice, nodes.Name) or value.slice.name != node.target.name:
                return
            
            self.add_message('consider-using-dict-items', node=parent)

    def _check_use_sequence_for_iteration(self, node: nodes.For | nodes.Comprehension) -> None:
        """Check if code iterates over an in-place defined set.

        Sets using `*` are not considered in-place.
        """
        if not isinstance(node.iter, nodes.Set):
            return
        
        if any(isinstance(elt, nodes.Starred) for elt in node.iter.elts):
            return
        
        self.add_message('use-sequence-for-iteration', node=node)

    def _detect_replacable_format_call(self, node: nodes.Const) -> None:
        """Check whether a string is used in a call to format() or '%' and whether it
        can be replaced by an f-string.
        """
        if not isinstance(node.parent, (nodes.Call, nodes.BinOp)):
            return
        
        if isinstance(node.parent, nodes.Call):
            if not isinstance(node.parent.func, nodes.Attribute):
                return
            if node.parent.func.attrname != 'format':
                return
            if node is not node.parent.func.expr:
                return
        else:  # BinOp
            if node.parent.op != '%':
                return
            if node is not node.parent.left:
                return
        
        if not self.linter.is_message_enabled('consider-using-f-string'):
            return
        
        if utils.parse_format_string(node.value)[0]:
            # If there are any named fields, we can't convert to f-string
            return
        
        self.add_message('consider-using-f-string', node=node)
