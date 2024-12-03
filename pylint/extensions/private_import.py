"""Check for imports on private external modules and names."""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING
from astroid import nodes
from pylint.checkers import BaseChecker, utils
from pylint.interfaces import HIGH
if TYPE_CHECKING:
    from pylint.lint.pylinter import PyLinter

class PrivateImportChecker(BaseChecker):
    name = 'import-private-name'
    msgs = {'C2701': ('Imported private %s (%s)', 'import-private-name', 'Used when a private module or object prefixed with _ is imported. PEP8 guidance on Naming Conventions states that public attributes with leading underscores should be considered private.')}

    def __init__(self, linter: PyLinter) -> None:
        BaseChecker.__init__(self, linter)
        self.all_used_type_annotations: dict[str, bool] = {}
        self.populated_annotations = False

    def _get_private_imports(self, names: list[str]) -> list[str]:
        """Returns the private names from input names by a simple string check."""
        return [name for name in names if self._name_is_private(name)]

    @staticmethod
    def _name_is_private(name: str) -> bool:
        """Returns true if the name exists, starts with `_`, and if len(name) > 4
        it is not a dunder, i.e. it does not begin and end with two underscores.
        """
        return bool(name) and name.startswith('_') and not (len(name) > 4 and name.startswith('__') and name.endswith('__'))

    def _get_type_annotation_names(self, node: nodes.Import | nodes.ImportFrom, names: list[str]) -> list[str]:
        """Removes from names any names that are used as type annotations with no other
        illegal usages.
        """
        if not self.populated_annotations:
            self._populate_type_annotations(node.root(), self.all_used_type_annotations)
            self.populated_annotations = True
        
        return [name for name in names if name not in self.all_used_type_annotations or not self.all_used_type_annotations[name]]

    def _populate_type_annotations(self, node: nodes.LocalsDictNodeNG, all_used_type_annotations: dict[str, bool]) -> None:
        """Adds to `all_used_type_annotations` all names ever used as a type annotation
        in the node's (nested) scopes and whether they are only used as annotation.
        """
        for child in node.get_children():
            if isinstance(child, nodes.FunctionDef):
                self._populate_type_annotations_function(child, all_used_type_annotations)
            elif isinstance(child, (nodes.ClassDef, nodes.Module)):
                self._populate_type_annotations(child, all_used_type_annotations)

    def _populate_type_annotations_function(self, node: nodes.FunctionDef, all_used_type_annotations: dict[str, bool]) -> None:
        """Adds all names used as type annotation in the arguments and return type of
        the function node into the dict `all_used_type_annotations`.
        """
        for arg in node.args.args + node.args.kwonlyargs:
            self._populate_type_annotations_annotation(arg.annotation, all_used_type_annotations)
        
        self._populate_type_annotations_annotation(node.args.varargannotation, all_used_type_annotations)
        self._populate_type_annotations_annotation(node.args.kwargannotation, all_used_type_annotations)
        self._populate_type_annotations_annotation(node.returns, all_used_type_annotations)

    def _populate_type_annotations_annotation(self, node: nodes.Attribute | nodes.Subscript | nodes.Name | None, all_used_type_annotations: dict[str, bool]) -> str | None:
        """Handles the possibility of an annotation either being a Name, i.e. just type,
        or a Subscript e.g. `Optional[type]` or an Attribute, e.g. `pylint.lint.linter`.
        """
        if isinstance(node, nodes.Name):
            all_used_type_annotations[node.name] = all_used_type_annotations.get(node.name, True)
            return node.name
        elif isinstance(node, nodes.Attribute):
            return self._populate_type_annotations_annotation(node.expr, all_used_type_annotations)
        elif isinstance(node, nodes.Subscript):
            self._populate_type_annotations_annotation(node.value, all_used_type_annotations)
            if isinstance(node.slice, nodes.Index):
                self._populate_type_annotations_annotation(node.slice.value, all_used_type_annotations)
        return None

    @staticmethod
    def _assignments_call_private_name(assignments: list[nodes.AnnAssign | nodes.Assign], private_name: str) -> bool:
        """Returns True if no assignments involve accessing `private_name`."""
        for assignment in assignments:
            if isinstance(assignment, nodes.AnnAssign):
                if isinstance(assignment.value, nodes.Name) and assignment.value.name == private_name:
                    return True
            elif isinstance(assignment, nodes.Assign):
                for target in assignment.targets:
                    if isinstance(target, nodes.Name) and target.name == private_name:
                        return True
        return False

    @staticmethod
    def same_root_dir(node: nodes.Import | nodes.ImportFrom, import_mod_name: str) -> bool:
        """Does the node's file's path contain the base name of `import_mod_name`?"""
        node_file = node.root().file
        if node_file:
            node_dir = os.path.dirname(node_file)
            import_base_name = import_mod_name.split('.')[0]
            return import_base_name in node_dir.split(os.path.sep)
        return False
