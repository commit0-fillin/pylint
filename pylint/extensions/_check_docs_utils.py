"""Utility methods for docstring checking."""
from __future__ import annotations
import itertools
import re
from collections.abc import Iterable
import astroid
from astroid import nodes
from astroid.util import UninferableBase
from pylint.checkers import utils

def space_indentation(s: str) -> int:
    """The number of leading spaces in a string.

    :param str s: input string

    :rtype: int
    :return: number of leading spaces
    """
    return len(s) - len(s.lstrip())

def get_setters_property_name(node: nodes.FunctionDef) -> str | None:
    """Get the name of the property that the given node is a setter for.

    :param node: The node to get the property name for.
    :type node: str

    :rtype: str or None
    :returns: The name of the property that the node is a setter for,
        or None if one could not be found.
    """
    if not node.decorators:
        return None
    
    for decorator in node.decorators.nodes:
        if isinstance(decorator, nodes.Attribute) and decorator.attrname == "setter":
            return decorator.expr.name
    
    return None

def get_setters_property(node: nodes.FunctionDef) -> nodes.FunctionDef | None:
    """Get the property node for the given setter node.

    :param node: The node to get the property for.
    :type node: nodes.FunctionDef

    :rtype: nodes.FunctionDef or None
    :returns: The node relating to the property of the given setter node,
        or None if one could not be found.
    """
    property_name = get_setters_property_name(node)
    if property_name is None:
        return None
    
    class_node = node.parent.frame()
    if not isinstance(class_node, nodes.ClassDef):
        return None
    
    for member in class_node.body:
        if (isinstance(member, nodes.FunctionDef) and 
            member.name == property_name and 
            utils.decorated_with_property(member)):
            return member
    
    return None

def returns_something(return_node: nodes.Return) -> bool:
    """Check if a return node returns a value other than None.

    :param return_node: The return node to check.
    :type return_node: astroid.Return

    :rtype: bool
    :return: True if the return node returns a value other than None,
        False otherwise.
    """
    if return_node.value is None:
        return False
    
    try:
        value = next(return_node.value.infer())
        return not (value is None or isinstance(value, nodes.Const) and value.value is None)
    except astroid.InferenceError:
        return True  # If we can't infer the value, assume it returns something

def possible_exc_types(node: nodes.NodeNG) -> set[nodes.ClassDef]:
    """Gets all the possible raised exception types for the given raise node.

    .. note::

        Caught exception types are ignored.

    :param node: The raise node to find exception types for.

    :returns: A list of exception types possibly raised by :param:`node`.
    """
    exc_types = set()
    if isinstance(node, nodes.Raise):
        if node.exc is None:
            return exc_types
        
        for exc_type in node.exc.nodes_of_class(nodes.Name):
            try:
                inferred = next(exc_type.infer())
                if isinstance(inferred, nodes.ClassDef) and utils.inherit_from_std_ex(inferred):
                    exc_types.add(inferred)
            except astroid.InferenceError:
                continue
    
    return exc_types

def _annotations_list(args_node: nodes.Arguments) -> list[nodes.NodeNG]:
    """Get a merged list of annotations.

    The annotations can come from:

    * Real type annotations.
    * A type comment on the function.
    * A type common on the individual argument.

    :param args_node: The node to get the annotations for.
    :returns: The annotations.
    """
    annotations = []
    
    # Real type annotations
    if args_node.annotations:
        annotations.extend(args_node.annotations)
    
    # Type comment on the function
    if args_node.parent and isinstance(args_node.parent, nodes.FunctionDef):
        if args_node.parent.type_comment_args:
            annotations.extend(args_node.parent.type_comment_args)
    
    # Type comment on individual arguments
    for arg in args_node.args:
        if arg.type_comment:
            annotations.append(arg.type_comment)
    
    return annotations

class Docstring:
    re_for_parameters_see = re.compile('\n        For\\s+the\\s+(other)?\\s*parameters\\s*,\\s+see\n        ', re.X | re.S)
    supports_yields: bool = False
    'True if the docstring supports a "yield" section.\n\n    False if the docstring uses the returns section to document generators.\n    '

    def __init__(self, doc: nodes.Const | None) -> None:
        docstring: str = doc.value if doc else ''
        self.doc = docstring.expandtabs()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}:'''{self.doc}'''>"

    def matching_sections(self) -> int:
        """Returns the number of matching docstring sections."""
        return 0  # Base Docstring class doesn't implement any specific matching

class SphinxDocstring(Docstring):
    re_type = '\n        [~!.]?               # Optional link style prefix\n        \\w(?:\\w|\\.[^\\.])*    # Valid python name\n        '
    re_simple_container_type = f'\n        {re_type}                     # a container type\n        [\\(\\[] [^\\n\\s]+ [\\)\\]]        # with the contents of the container\n    '
    re_multiple_simple_type = f'\n        (?:{re_simple_container_type}|{re_type})\n        (?:(?:\\s+(?:of|or)\\s+|\\s*,\\s*|\\s+\\|\\s+)(?:{re_simple_container_type}|{re_type}))*\n    '
    re_xref = f'\n        (?::\\w+:)?                    # optional tag\n        `{re_type}`                   # what to reference\n        '
    re_param_raw = f'\n        :                       # initial colon\n        (?:                     # Sphinx keywords\n        param|parameter|\n        arg|argument|\n        key|keyword\n        )\n        \\s+                     # whitespace\n\n        (?:                     # optional type declaration\n        ({re_type}|{re_simple_container_type})\n        \\s+\n        )?\n\n        ((\\\\\\*{{0,2}}\\w+)|(\\w+))  # Parameter name with potential asterisks\n        \\s*                       # whitespace\n        :                         # final colon\n        '
    re_param_in_docstring = re.compile(re_param_raw, re.X | re.S)
    re_type_raw = f'\n        :type                           # Sphinx keyword\n        \\s+                             # whitespace\n        ({re_multiple_simple_type})     # Parameter name\n        \\s*                             # whitespace\n        :                               # final colon\n        '
    re_type_in_docstring = re.compile(re_type_raw, re.X | re.S)
    re_property_type_raw = f'\n        :type:                      # Sphinx keyword\n        \\s+                         # whitespace\n        {re_multiple_simple_type}   # type declaration\n        '
    re_property_type_in_docstring = re.compile(re_property_type_raw, re.X | re.S)
    re_raise_raw = f'\n        :                               # initial colon\n        (?:                             # Sphinx keyword\n        raises?|\n        except|exception\n        )\n        \\s+                             # whitespace\n        ({re_multiple_simple_type})     # exception type\n        \\s*                             # whitespace\n        :                               # final colon\n        '
    re_raise_in_docstring = re.compile(re_raise_raw, re.X | re.S)
    re_rtype_in_docstring = re.compile(':rtype:')
    re_returns_in_docstring = re.compile(':returns?:')
    supports_yields = False

    def matching_sections(self) -> int:
        """Returns the number of matching docstring sections."""
        count = 0
        if self.re_param_in_docstring.search(self.doc):
            count += 1
        if self.re_raise_in_docstring.search(self.doc):
            count += 1
        if self.re_returns_in_docstring.search(self.doc):
            count += 1
        if self.supports_yields and self.re_yields_in_docstring.search(self.doc):
            count += 1
        return count

class EpytextDocstring(SphinxDocstring):
    """Epytext is similar to Sphinx.

    See the docs:
        http://epydoc.sourceforge.net/epytext.html
        http://epydoc.sourceforge.net/fields.html#fields

    It's used in PyCharm:
        https://www.jetbrains.com/help/pycharm/2016.1/creating-documentation-comments.html#d848203e314
        https://www.jetbrains.com/help/pycharm/2016.1/using-docstrings-to-specify-types.html
    """
    re_param_in_docstring = re.compile(SphinxDocstring.re_param_raw.replace(':', '@', 1), re.X | re.S)
    re_type_in_docstring = re.compile(SphinxDocstring.re_type_raw.replace(':', '@', 1), re.X | re.S)
    re_property_type_in_docstring = re.compile(SphinxDocstring.re_property_type_raw.replace(':', '@', 1), re.X | re.S)
    re_raise_in_docstring = re.compile(SphinxDocstring.re_raise_raw.replace(':', '@', 1), re.X | re.S)
    re_rtype_in_docstring = re.compile('\n        @                       # initial "at" symbol\n        (?:                     # Epytext keyword\n        rtype|returntype\n        )\n        :                       # final colon\n        ', re.X | re.S)
    re_returns_in_docstring = re.compile('@returns?:')

class GoogleDocstring(Docstring):
    re_type = SphinxDocstring.re_type
    re_xref = SphinxDocstring.re_xref
    re_container_type = f'\n        (?:{re_type}|{re_xref})       # a container type\n        [\\(\\[] [^\\n]+ [\\)\\]]          # with the contents of the container\n    '
    re_multiple_type = f'\n        (?:{re_container_type}|{re_type}|{re_xref})\n        (?:(?:\\s+(?:of|or)\\s+|\\s*,\\s*|\\s+\\|\\s+)(?:{re_container_type}|{re_type}|{re_xref}))*\n    '
    _re_section_template = '\n        ^([ ]*)   {0} \\s*:   \\s*$     # Google parameter header\n        (  .* )                       # section\n        '
    re_param_section = re.compile(_re_section_template.format('(?:Args|Arguments|Parameters)'), re.X | re.S | re.M)
    re_keyword_param_section = re.compile(_re_section_template.format('Keyword\\s(?:Args|Arguments|Parameters)'), re.X | re.S | re.M)
    re_param_line = re.compile(f'\n        \\s*  ((?:\\\\?\\*{{0,2}})?[\\w\\\\]+) # identifier potentially with asterisks or escaped `\\`\n        \\s*  ( [(]\n            {re_multiple_type}\n            (?:,\\s+optional)?\n            [)] )? \\s* :                # optional type declaration\n        \\s*  (.*)                       # beginning of optional description\n    ', re.X | re.S | re.M)
    re_raise_section = re.compile(_re_section_template.format('Raises'), re.X | re.S | re.M)
    re_raise_line = re.compile(f'\n        \\s*  ({re_multiple_type}) \\s* :  # identifier\n        \\s*  (.*)                        # beginning of optional description\n    ', re.X | re.S | re.M)
    re_returns_section = re.compile(_re_section_template.format('Returns?'), re.X | re.S | re.M)
    re_returns_line = re.compile(f'\n        \\s* ({re_multiple_type}:)?        # identifier\n        \\s* (.*)                          # beginning of description\n    ', re.X | re.S | re.M)
    re_property_returns_line = re.compile(f'\n        ^{re_multiple_type}:           # identifier\n        \\s* (.*)                       # Summary line / description\n    ', re.X | re.S | re.M)
    re_yields_section = re.compile(_re_section_template.format('Yields?'), re.X | re.S | re.M)
    re_yields_line = re_returns_line
    supports_yields = True

    def matching_sections(self) -> int:
        """Returns the number of matching docstring sections."""
        count = 0
        if self.re_param_section.search(self.doc):
            count += 1
        if self.re_raise_section.search(self.doc):
            count += 1
        if self.re_returns_section.search(self.doc):
            count += 1
        if self.supports_yields and self.re_yields_section.search(self.doc):
            count += 1
        return count

class NumpyDocstring(GoogleDocstring):
    _re_section_template = '\n        ^([ ]*)   {0}   \\s*?$          # Numpy parameters header\n        \\s*     [-=]+   \\s*?$          # underline\n        (  .* )                        # section\n    '
    re_param_section = re.compile(_re_section_template.format('(?:Args|Arguments|Parameters)'), re.X | re.S | re.M)
    re_default_value = '(([\'"]\\w+\\s*[\'"])|(\\d+)|(True)|(False)|(None))'
    re_param_line = re.compile(f"\n        \\s*  (?P<param_name>\\*{{0,2}}\\w+)(\\s?(:|\\n)) # identifier with potential asterisks\n        \\s*\n        (?P<param_type>\n         (\n          ({GoogleDocstring.re_multiple_type})      # default type declaration\n          (,\\s+optional)?                           # optional 'optional' indication\n         )?\n         (\n          {{({re_default_value},?\\s*)+}}            # set of default values\n         )?\n         (?:$|\\n)\n        )?\n        (\n         \\s* (?P<param_desc>.*)                     # optional description\n        )?\n    ", re.X | re.S)
    re_raise_section = re.compile(_re_section_template.format('Raises'), re.X | re.S | re.M)
    re_raise_line = re.compile(f'\n        \\s* ({GoogleDocstring.re_type})$   # type declaration\n        \\s* (.*)                           # optional description\n    ', re.X | re.S | re.M)
    re_returns_section = re.compile(_re_section_template.format('Returns?'), re.X | re.S | re.M)
    re_returns_line = re.compile(f'\n        \\s* (?:\\w+\\s+:\\s+)? # optional name\n        ({GoogleDocstring.re_multiple_type})$   # type declaration\n        \\s* (.*)                                # optional description\n    ', re.X | re.S | re.M)
    re_yields_section = re.compile(_re_section_template.format('Yields?'), re.X | re.S | re.M)
    re_yields_line = re_returns_line
    supports_yields = True

    def match_param_docs(self) -> tuple[set[str], set[str]]:
        """Matches parameter documentation section to parameter documentation rules."""
        params_with_doc = set()
        params_with_type = set()

        for match in self.re_param_section.finditer(self.doc):
            section = match.group(2)
            for line in section.splitlines():
                match = self.re_param_line.match(line.strip())
                if match:
                    param_name = match.group('param_name')
                    param_type = match.group('param_type')
                    param_desc = match.group('param_desc')
                    
                    if param_desc:
                        params_with_doc.add(param_name)
                    if param_type:
                        params_with_type.add(param_name)

        return params_with_doc, params_with_type
DOCSTRING_TYPES = {'sphinx': SphinxDocstring, 'epytext': EpytextDocstring, 'google': GoogleDocstring, 'numpy': NumpyDocstring, 'default': Docstring}
'A map of the name of the docstring type to its class.\n\n:type: dict(str, type)\n'
