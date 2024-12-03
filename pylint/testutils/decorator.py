from __future__ import annotations
import functools
from collections.abc import Callable
from typing import Any
from pylint.testutils.checker_test_case import CheckerTestCase

def set_config(**kwargs: Any) -> Callable[[Callable[..., None]], Callable[..., None]]:
    """Decorator for setting an option on the linter.

    Passing the args and kwargs back to the test function itself
    allows this decorator to be used on parameterized test cases.
    """
    def _wrapper(fun: Callable[..., None]) -> Callable[..., None]:
        @functools.wraps(fun)
        def _forward(self: CheckerTestCase, *args: Any, **kw: Any) -> None:
            old_values = {}
            for key, value in kwargs.items():
                old_values[key] = getattr(self.linter.config, key)
                setattr(self.linter.config, key, value)
            try:
                fun(self, *args, **kw)
            finally:
                for key, value in old_values.items():
                    setattr(self.linter.config, key, value)
        return _forward
    return _wrapper
