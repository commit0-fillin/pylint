from __future__ import annotations
import json
from pathlib import Path, PurePosixPath
from pylint.reporters.json_reporter import OldJsonExport
from pylint.testutils._primer.primer_command import PackageData, PackageMessages, PrimerCommand
MAX_GITHUB_COMMENT_LENGTH = 65536

class CompareCommand(PrimerCommand):

    def _truncate_comment(self, comment: str) -> str:
        """GitHub allows only a set number of characters in a comment."""
        if len(comment) <= MAX_GITHUB_COMMENT_LENGTH:
            return comment
        truncated = comment[:MAX_GITHUB_COMMENT_LENGTH - 3] + "..."
        return truncated
