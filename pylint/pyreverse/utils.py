"""Generic classes/functions for pyreverse core/extensions."""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, Any, Callable, Optional, Tuple, Union
import astroid
from astroid import nodes
from astroid.typing import InferenceResult
if TYPE_CHECKING:
    from pylint.pyreverse.diagrams import ClassDiagram, PackageDiagram
    _CallbackT = Callable[[nodes.NodeNG], Union[Tuple[ClassDiagram], Tuple[PackageDiagram, ClassDiagram], None]]
    _CallbackTupleT = Tuple[Optional[_CallbackT], Optional[_CallbackT]]
RCFILE = '.pyreverserc'

def get_default_options() -> list[str]:
    """Read config file and return list of options."""
    options = []
    if os.path.exists(RCFILE):
        with open(RCFILE, 'r') as config_file:
            for line in config_file:
                line = line.strip()
                if line and not line.startswith('#'):
                    options.append(line)
    return options

def insert_default_options() -> None:
    """Insert default options to sys.argv."""
    options = get_default_options()
    sys.argv[1:1] = options
SPECIAL = re.compile('^__([^\\W_]_*)+__$')
PRIVATE = re.compile('^__(_*[^\\W_])+_?$')
PROTECTED = re.compile('^_\\w*$')

def get_visibility(name: str) -> str:
    """Return the visibility from a name: public, protected, private or special."""
    if SPECIAL.match(name):
        return 'special'
    if PRIVATE.match(name):
        return 'private'
    if PROTECTED.match(name):
        return 'protected'
    return 'public'
_SPECIAL = 2
_PROTECTED = 4
_PRIVATE = 8
MODES = {'ALL': 0, 'PUB_ONLY': _SPECIAL + _PROTECTED + _PRIVATE, 'SPECIAL': _SPECIAL, 'OTHER': _PROTECTED + _PRIVATE}
VIS_MOD = {'special': _SPECIAL, 'protected': _PROTECTED, 'private': _PRIVATE, 'public': 0}

class FilterMixIn:
    """Filter nodes according to a mode and nodes' visibility."""

    def __init__(self, mode: str) -> None:
        """Init filter modes."""
        __mode = 0
        for nummod in mode.split('+'):
            try:
                __mode += MODES[nummod]
            except KeyError as ex:
                print(f'Unknown filter mode {ex}', file=sys.stderr)
        self.__mode = __mode

    def show_attr(self, node: nodes.NodeNG | str) -> bool:
        """Return true if the node should be treated."""
        name = node if isinstance(node, str) else node.name
        visibility = get_visibility(name)
        return not (self.__mode & VIS_MOD[visibility])

class LocalsVisitor:
    """Visit a project by traversing the locals dictionary.

    * visit_<class name> on entering a node, where class name is the class of
    the node in lower case

    * leave_<class name> on leaving a node, where class name is the class of
    the node in lower case
    """

    def __init__(self) -> None:
        self._cache: dict[type[nodes.NodeNG], _CallbackTupleT] = {}
        self._visited: set[nodes.NodeNG] = set()

    def get_callbacks(self, node: nodes.NodeNG) -> _CallbackTupleT:
        """Get callbacks from handler for the visited node."""
        klass = node.__class__
        if klass not in self._cache:
            visit = getattr(self, f'visit_{klass.__name__.lower()}', None)
            leave = getattr(self, f'leave_{klass.__name__.lower()}', None)
            self._cache[klass] = (visit, leave)
        return self._cache[klass]

    def visit(self, node: nodes.NodeNG) -> Any:
        """Launch the visit starting from the given node."""
        if node in self._visited:
            return

        self._visited.add(node)

        visit, leave = self.get_callbacks(node)
        if visit:
            visit(node)

        for child_node in node.get_children():
            self.visit(child_node)

        if leave:
            leave(node)

def get_annotation(node: nodes.AssignAttr | nodes.AssignName) -> nodes.Name | nodes.Subscript | None:
    """Return the annotation for `node`."""
    if isinstance(node, nodes.AssignAttr):
        return node.parent.annotation if isinstance(node.parent, nodes.AnnAssign) else None
    return node.parent.annotation if isinstance(node.parent, nodes.AnnAssign) else None

def infer_node(node: nodes.AssignAttr | nodes.AssignName) -> set[InferenceResult]:
    """Return a set containing the node annotation if it exists
    otherwise return a set of the inferred types using the NodeNG.infer method.
    """
    annotation = get_annotation(node)
    if annotation:
        try:
            return set(annotation.infer())
        except astroid.InferenceError:
            return set()
    
    try:
        return set(node.infer())
    except astroid.InferenceError:
        return set()

def check_graphviz_availability() -> None:
    """Check if the ``dot`` command is available on the machine.

    This is needed if image output is desired and ``dot`` is used to convert
    from *.dot or *.gv into the final output format.
    """
    if shutil.which('dot') is None:
        raise ImportError(
            "The 'dot' command from Graphviz is required to generate image output. "
            "Please make sure Graphviz is installed and 'dot' is available in your PATH."
        )

def check_if_graphviz_supports_format(output_format: str) -> None:
    """Check if the ``dot`` command supports the requested output format.

    This is needed if image output is desired and ``dot`` is used to convert
    from *.gv into the final output format.
    """
    check_graphviz_availability()
    try:
        subprocess.run(['dot', f'-T{output_format}', '-o', os.devnull], 
                       input='digraph { A -> B }', text=True, 
                       capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        raise ValueError(f"The 'dot' command does not support the '{output_format}' format. Error: {e.stderr}")
