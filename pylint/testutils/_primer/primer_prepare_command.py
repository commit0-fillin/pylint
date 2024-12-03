from __future__ import annotations
import sys
from git.cmd import Git
from git.repo import Repo
from pylint.testutils._primer.primer_command import PrimerCommand

class PrepareCommand(PrimerCommand):
    def __init__(self, repo_path: str):
        super().__init__()
        self.repo_path = repo_path
        self.repo = Repo(self.repo_path)
        self.git = self.repo.git

    def run(self) -> None:
        """Run the prepare command."""
        self.fetch_upstream()
        self.checkout_main()
        self.pull_upstream()
        self.update_submodules()

    def fetch_upstream(self) -> None:
        """Fetch the upstream repository."""
        self.git.fetch('upstream')

    def checkout_main(self) -> None:
        """Checkout the main branch."""
        self.git.checkout('main')

    def pull_upstream(self) -> None:
        """Pull changes from the upstream main branch."""
        self.git.pull('upstream', 'main')

    def update_submodules(self) -> None:
        """Update and initialize submodules."""
        self.git.submodule('update', '--init', '--recursive')
