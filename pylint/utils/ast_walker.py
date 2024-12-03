from __future__ import annotations
import sys
import traceback
from collections import defaultdict
from collections.abc import Sequence
from typing import TYPE_CHECKING, Callable
from astroid import nodes
if TYPE_CHECKING:
    from pylint.checkers.base_checker import BaseChecker
    from pylint.lint import PyLinter
AstCallback = Callable[[nodes.NodeNG], None]

class ASTWalker:

    def __init__(self, linter: PyLinter) -> None:
        self.nbstatements = 0
        self.visit_events: defaultdict[str, list[AstCallback]] = defaultdict(list)
        self.leave_events: defaultdict[str, list[AstCallback]] = defaultdict(list)
        self.linter = linter
        self.exception_msg = False

    def add_checker(self, checker: BaseChecker) -> None:
        """Walk to the checker's dir and collect visit and leave methods."""
        for member in dir(checker):
            if member.startswith('visit_'):
                self.visit_events[member[6:]].append(getattr(checker, member))
            elif member.startswith('leave_'):
                self.leave_events[member[6:]].append(getattr(checker, member))

    def walk(self, astroid: nodes.NodeNG) -> None:
        """Call visit events of astroid checkers for the given node, recurse on
        its children, then leave events.
        """
        try:
            callbacks = self.visit_events[astroid.__class__.__name__]
            for cb in callbacks:
                cb(astroid)
            
            for child in astroid.get_children():
                self.walk(child)
            
            callbacks = self.leave_events[astroid.__class__.__name__]
            for cb in callbacks:
                cb(astroid)
        except Exception:
            exc_info = sys.exc_info()
            if self.exception_msg:
                self.linter.add_message('E0013', line=astroid.lineno, args=exc_info[1])
            else:
                traceback.print_exc()
