from __future__ import annotations
from typing import Literal, TypedDict, cast
from pylint.typing import MessageTypesFullName

class BadNames(TypedDict):
    """TypedDict to store counts of node types with bad names."""
    argument: int
    attr: int
    klass: int
    class_attribute: int
    class_const: int
    const: int
    inlinevar: int
    function: int
    method: int
    module: int
    variable: int
    typevar: int
    typealias: int

class CodeTypeCount(TypedDict):
    """TypedDict to store counts of lines of code types."""
    code: int
    comment: int
    docstring: int
    empty: int
    total: int

class DuplicatedLines(TypedDict):
    """TypedDict to store counts of lines of duplicated code."""
    nb_duplicated_lines: int
    percent_duplicated_lines: float

class NodeCount(TypedDict):
    """TypedDict to store counts of different types of nodes."""
    function: int
    klass: int
    method: int
    module: int

class UndocumentedNodes(TypedDict):
    """TypedDict to store counts of undocumented node types."""
    function: int
    klass: int
    method: int
    module: int

class ModuleStats(TypedDict):
    """TypedDict to store counts of types of messages and statements."""
    convention: int
    error: int
    fatal: int
    info: int
    refactor: int
    statement: int
    warning: int

class LinterStats:
    """Class used to linter stats."""

    def __init__(self, bad_names: BadNames | None=None, by_module: dict[str, ModuleStats] | None=None, by_msg: dict[str, int] | None=None, code_type_count: CodeTypeCount | None=None, dependencies: dict[str, set[str]] | None=None, duplicated_lines: DuplicatedLines | None=None, node_count: NodeCount | None=None, undocumented: UndocumentedNodes | None=None) -> None:
        self.bad_names = bad_names or BadNames(argument=0, attr=0, klass=0, class_attribute=0, class_const=0, const=0, inlinevar=0, function=0, method=0, module=0, variable=0, typevar=0, typealias=0)
        self.by_module: dict[str, ModuleStats] = by_module or {}
        self.by_msg: dict[str, int] = by_msg or {}
        self.code_type_count = code_type_count or CodeTypeCount(code=0, comment=0, docstring=0, empty=0, total=0)
        self.dependencies: dict[str, set[str]] = dependencies or {}
        self.duplicated_lines = duplicated_lines or DuplicatedLines(nb_duplicated_lines=0, percent_duplicated_lines=0.0)
        self.node_count = node_count or NodeCount(function=0, klass=0, method=0, module=0)
        self.undocumented = undocumented or UndocumentedNodes(function=0, klass=0, method=0, module=0)
        self.convention = 0
        self.error = 0
        self.fatal = 0
        self.info = 0
        self.refactor = 0
        self.statement = 0
        self.warning = 0
        self.global_note = 0
        self.nb_duplicated_lines = 0
        self.percent_duplicated_lines = 0.0

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f'{self.bad_names}\n        {sorted(self.by_module.items())}\n        {sorted(self.by_msg.items())}\n        {self.code_type_count}\n        {sorted(self.dependencies.items())}\n        {self.duplicated_lines}\n        {self.undocumented}\n        {self.convention}\n        {self.error}\n        {self.fatal}\n        {self.info}\n        {self.refactor}\n        {self.statement}\n        {self.warning}\n        {self.global_note}\n        {self.nb_duplicated_lines}\n        {self.percent_duplicated_lines}'

    def init_single_module(self, module_name: str) -> None:
        """Use through PyLinter.set_current_module so PyLinter.current_name is
        consistent.
        """
        if module_name not in self.by_module:
            self.by_module[module_name] = ModuleStats(
                convention=0, error=0, fatal=0, info=0, refactor=0, statement=0, warning=0
            )

    def get_bad_names(self, node_name: Literal['argument', 'attr', 'class', 'class_attribute', 'class_const', 'const', 'inlinevar', 'function', 'method', 'module', 'variable', 'typevar', 'typealias']) -> int:
        """Get a bad names node count."""
        return self.bad_names.get(node_name, 0)

    def increase_bad_name(self, node_name: str, increase: int) -> None:
        """Increase a bad names node count."""
        if node_name in self.bad_names:
            self.bad_names[node_name] += increase

    def reset_bad_names(self) -> None:
        """Resets the bad_names attribute."""
        self.bad_names = BadNames(argument=0, attr=0, klass=0, class_attribute=0, class_const=0, const=0, inlinevar=0, function=0, method=0, module=0, variable=0, typevar=0, typealias=0)

    def get_code_count(self, type_name: Literal['code', 'comment', 'docstring', 'empty', 'total']) -> int:
        """Get a code type count."""
        return self.code_type_count.get(type_name, 0)

    def reset_code_count(self) -> None:
        """Resets the code_type_count attribute."""
        self.code_type_count = CodeTypeCount(code=0, comment=0, docstring=0, empty=0, total=0)

    def reset_duplicated_lines(self) -> None:
        """Resets the duplicated_lines attribute."""
        self.duplicated_lines = DuplicatedLines(nb_duplicated_lines=0, percent_duplicated_lines=0.0)
        self.nb_duplicated_lines = 0
        self.percent_duplicated_lines = 0.0

    def get_node_count(self, node_name: Literal['function', 'class', 'method', 'module']) -> int:
        """Get a node count while handling some extra conditions."""
        if node_name == 'class':
            return self.node_count['klass']
        return self.node_count.get(node_name, 0)

    def reset_node_count(self) -> None:
        """Resets the node count attribute."""
        self.node_count = NodeCount(function=0, klass=0, method=0, module=0)

    def get_undocumented(self, node_name: Literal['function', 'class', 'method', 'module']) -> float:
        """Get a undocumented node count."""
        if node_name == 'class':
            return self.undocumented['klass']
        return self.undocumented.get(node_name, 0)

    def reset_undocumented(self) -> None:
        """Resets the undocumented attribute."""
        self.undocumented = UndocumentedNodes(function=0, klass=0, method=0, module=0)

    def get_global_message_count(self, type_name: str) -> int:
        """Get a global message count."""
        return getattr(self, type_name, 0)

    def get_module_message_count(self, modname: str, type_name: MessageTypesFullName) -> int:
        """Get a module message count."""
        return self.by_module.get(modname, {}).get(type_name, 0)

    def increase_single_message_count(self, type_name: str, increase: int) -> None:
        """Increase the message type count of an individual message type."""
        setattr(self, type_name, getattr(self, type_name, 0) + increase)

    def increase_single_module_message_count(self, modname: str, type_name: MessageTypesFullName, increase: int) -> None:
        """Increase the message type count of an individual message type of a
        module.
        """
        if modname not in self.by_module:
            self.by_module[modname] = ModuleStats(convention=0, error=0, fatal=0, info=0, refactor=0, statement=0, warning=0)
        self.by_module[modname][type_name] += increase

    def reset_message_count(self) -> None:
        """Resets the message type count of the stats object."""
        self.convention = 0
        self.error = 0
        self.fatal = 0
        self.info = 0
        self.refactor = 0
        self.warning = 0
        self.by_module.clear()

def merge_stats(stats: list[LinterStats]) -> LinterStats:
    """Used to merge multiple stats objects into a new one when pylint is run in
    parallel mode.
    """
    merged = LinterStats()
    for stat in stats:
        for attr, value in stat.bad_names.items():
            merged.bad_names[attr] += value
        for module, module_stats in stat.by_module.items():
            if module not in merged.by_module:
                merged.by_module[module] = ModuleStats(**module_stats)
            else:
                for msg_type, count in module_stats.items():
                    merged.by_module[module][msg_type] += count
        for msg, count in stat.by_msg.items():
            merged.by_msg[msg] = merged.by_msg.get(msg, 0) + count
        for code_type, count in stat.code_type_count.items():
            merged.code_type_count[code_type] += count
        for module, deps in stat.dependencies.items():
            if module not in merged.dependencies:
                merged.dependencies[module] = set(deps)
            else:
                merged.dependencies[module].update(deps)
        merged.duplicated_lines['nb_duplicated_lines'] += stat.duplicated_lines['nb_duplicated_lines']
        merged.duplicated_lines['percent_duplicated_lines'] += stat.duplicated_lines['percent_duplicated_lines']
        for node_type, count in stat.node_count.items():
            merged.node_count[node_type] += count
        for node_type, count in stat.undocumented.items():
            merged.undocumented[node_type] += count
        merged.convention += stat.convention
        merged.error += stat.error
        merged.fatal += stat.fatal
        merged.info += stat.info
        merged.refactor += stat.refactor
        merged.statement += stat.statement
        merged.warning += stat.warning
        merged.global_note += stat.global_note
        merged.nb_duplicated_lines += stat.nb_duplicated_lines
        merged.percent_duplicated_lines += stat.percent_duplicated_lines
    
    # Calculate average for percent_duplicated_lines
    if stats:
        merged.percent_duplicated_lines /= len(stats)
        merged.duplicated_lines['percent_duplicated_lines'] /= len(stats)
    
    return merged
