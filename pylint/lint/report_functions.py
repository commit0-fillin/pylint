from __future__ import annotations
import collections
from collections import defaultdict
from typing import cast
from pylint import checkers, exceptions
from pylint.reporters.ureports.nodes import Section, Table
from pylint.typing import MessageTypesFullName
from pylint.utils import LinterStats

def report_total_messages_stats(sect: Section, stats: LinterStats, previous_stats: LinterStats | None) -> None:
    """Make total errors / warnings report."""
    lines = ['type', 'number', 'previous', 'difference']
    for msg_type in ('convention', 'refactor', 'warning', 'error'):
        msg_type_full = MessageTypesFullName[msg_type]
        count = stats.get_message_stats(msg_type_full)
        previous_count = previous_stats.get_message_stats(msg_type_full) if previous_stats else None
        diff_str = ''
        if previous_count is not None:
            diff = count - previous_count
            diff_str = f"{diff:+d}"
        lines += [msg_type_full, str(count), str(previous_count) if previous_count is not None else '', diff_str]
    sect.append(Table(cols=4, children=lines, rheaders=1))

def report_messages_stats(sect: Section, stats: LinterStats, _: LinterStats | None) -> None:
    """Make messages type report."""
    messages_stats = sorted(stats.messages_stats.items(), key=lambda x: x[1], reverse=True)
    lines = ['message id', 'occurrences']
    for msg_id, count in messages_stats:
        lines += [msg_id, str(count)]
    sect.append(Table(cols=2, children=lines, rheaders=1))

def report_messages_by_module_stats(sect: Section, stats: LinterStats, _: LinterStats | None) -> None:
    """Make errors / warnings by modules report."""
    module_stats = defaultdict(lambda: defaultdict(int))
    for msg_type_full, msg_id, module, _ in stats.messages:
        module_stats[module][msg_type_full] += 1

    lines = ['module', 'error', 'warning', 'refactor', 'convention']
    for module, type_stats in sorted(module_stats.items()):
        lines += [
            module,
            str(type_stats['error']),
            str(type_stats['warning']),
            str(type_stats['refactor']),
            str(type_stats['convention'])
        ]
    sect.append(Table(cols=5, children=lines, rheaders=1))
