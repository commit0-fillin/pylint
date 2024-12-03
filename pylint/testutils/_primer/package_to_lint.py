from __future__ import annotations
import logging
from pathlib import Path
from typing import Literal
from git import GitCommandError
from git.cmd import Git
from git.repo import Repo
PRIMER_DIRECTORY_PATH = Path('tests') / '.pylint_primer_tests'

class DirtyPrimerDirectoryException(Exception):
    """We can't pull if there's local changes."""

    def __init__(self, path: Path | str):
        super().__init__(f"\n\n/!\\ Can't pull /!\\\n\nIn order for the prepare command to be able to pull please cleanup your local repo:\ncd {path}\ngit diff\n")

class PackageToLint:
    """Represents data about a package to be tested during primer tests."""
    url: str
    'URL of the repository to clone.'
    branch: str
    'Branch of the repository to clone.'
    directories: list[str]
    'Directories within the repository to run pylint over.'
    commit: str | None
    'Commit hash to pin the repository on.'
    pylint_additional_args: list[str]
    'Arguments to give to pylint.'
    pylintrc_relpath: str | None
    "Path relative to project's main directory to the pylintrc if it exists."
    minimum_python: str | None
    'Minimum python version supported by the package.'

    def __init__(self, url: str, branch: str, directories: list[str], commit: str | None=None, pylint_additional_args: list[str] | None=None, pylintrc_relpath: str | None=None, minimum_python: str | None=None) -> None:
        self.url = url
        self.branch = branch
        self.directories = directories
        self.commit = commit
        self.pylint_additional_args = pylint_additional_args or []
        self.pylintrc_relpath = pylintrc_relpath
        self.minimum_python = minimum_python

    @property
    def clone_directory(self) -> Path:
        """Directory to clone repository into."""
        repo_name = self.url.split('/')[-1].replace('.git', '')
        return PRIMER_DIRECTORY_PATH / repo_name

    @property
    def paths_to_lint(self) -> list[str]:
        """The paths we need to lint."""
        return [str(self.clone_directory / directory) for directory in self.directories]

    def lazy_clone(self) -> str:
        """Concatenates the target directory and clones the file.

        Not expected to be tested as the primer won't work if it doesn't.
        It's tested in the continuous integration primers, only the coverage
        is not calculated on everything. If lazy clone breaks for local use
        we'll probably notice because we'll have a fatal when launching the
        primer locally.
        """
        if not self.clone_directory.exists():
            logging.info("Cloning %s", self.url)
            Repo.clone_from(self.url, self.clone_directory, branch=self.branch)
        else:
            logging.info("Repository already cloned, pulling latest changes")
            repo = Repo(self.clone_directory)
            try:
                repo.git.pull()
            except GitCommandError:
                raise DirtyPrimerDirectoryException(self.clone_directory)

        if self.commit:
            repo = Repo(self.clone_directory)
            repo.git.checkout(self.commit)

        return str(self.clone_directory)
