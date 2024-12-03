"""This module exists for compatibility reasons.

It's updated via tbump, do not modify.
"""
from __future__ import annotations
__version__ = '3.2.6'

def get_numversion_from_version(v: str) -> tuple[int, int, int]:
    """Kept for compatibility reason.

    See https://github.com/pylint-dev/pylint/issues/4399
    https://github.com/pylint-dev/pylint/issues/4420,
    """
    parts = v.split('.')
    return tuple(int(part) for part in parts[:3])
numversion = get_numversion_from_version(__version__)
