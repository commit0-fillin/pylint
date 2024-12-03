"""A similarities / code duplication command line tool and pylint checker.

The algorithm is based on comparing the hash value of n successive lines of a file.
First the files are read and any line that doesn't fulfill requirement are removed
(comments, docstrings...)

Those stripped lines are stored in the LineSet class which gives access to them.
Then each index of the stripped lines collection is associated with the hash of n
successive entries of the stripped lines starting at the current index (n is the
minimum common lines option).

The common hashes between both linesets are then looked for. If there are matches, then
the match indices in both linesets are stored and associated with the corresponding
couples (start line number/end line number) in both files.

This association is then post-processed to handle the case of successive matches. For
example if the minimum common lines setting is set to four, then the hashes are
computed with four lines. If one of match indices couple (12, 34) is the
successor of another one (11, 33) then it means that there are in fact five lines which
are common.

Once post-processed the values of association table are the result looked for, i.e.
start and end lines numbers of common lines in both files.
"""
from __future__ import annotations
import argparse
import copy
import functools
import itertools
import operator
import re
import sys
import warnings
from collections import defaultdict
from collections.abc import Callable, Generator, Iterable, Sequence
from getopt import GetoptError, getopt
from io import BufferedIOBase, BufferedReader, BytesIO
from itertools import chain
from typing import TYPE_CHECKING, Dict, List, NamedTuple, NewType, NoReturn, TextIO, Tuple, Union
import astroid
from astroid import nodes
from pylint.checkers import BaseChecker, BaseRawFileChecker, table_lines_from_stats
from pylint.reporters.ureports.nodes import Section, Table
from pylint.typing import MessageDefinitionTuple, Options
from pylint.utils import LinterStats, decoding_stream
if TYPE_CHECKING:
    from pylint.lint import PyLinter
DEFAULT_MIN_SIMILARITY_LINE = 4
REGEX_FOR_LINES_WITH_CONTENT = re.compile('.*\\w+')
Index = NewType('Index', int)
LineNumber = NewType('LineNumber', int)

class LineSpecifs(NamedTuple):
    line_number: LineNumber
    text: str
HashToIndex_T = Dict['LinesChunk', List[Index]]
IndexToLines_T = Dict[Index, 'SuccessiveLinesLimits']
STREAM_TYPES = Union[TextIO, BufferedReader, BytesIO]

class CplSuccessiveLinesLimits:
    """Holds a SuccessiveLinesLimits object for each checked file and counts the number
    of common lines between both stripped lines collections extracted from both files.
    """
    __slots__ = ('first_file', 'second_file', 'effective_cmn_lines_nb')

    def __init__(self, first_file: SuccessiveLinesLimits, second_file: SuccessiveLinesLimits, effective_cmn_lines_nb: int) -> None:
        self.first_file = first_file
        self.second_file = second_file
        self.effective_cmn_lines_nb = effective_cmn_lines_nb
CplIndexToCplLines_T = Dict['LineSetStartCouple', CplSuccessiveLinesLimits]

class LinesChunk:
    """The LinesChunk object computes and stores the hash of some consecutive stripped
    lines of a lineset.
    """
    __slots__ = ('_fileid', '_index', '_hash')

    def __init__(self, fileid: str, num_line: int, *lines: Iterable[str]) -> None:
        self._fileid: str = fileid
        'The name of the file from which the LinesChunk object is generated.'
        self._index: Index = Index(num_line)
        'The index in the stripped lines that is the starting of consecutive\n        lines.\n        '
        self._hash: int = sum((hash(lin) for lin in lines))
        'The hash of some consecutive lines.'

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, LinesChunk):
            return NotImplemented
        return self._hash == o._hash

    def __hash__(self) -> int:
        return self._hash

    def __repr__(self) -> str:
        return f'<LinesChunk object for file {self._fileid} ({self._index}, {self._hash})>'

    def __str__(self) -> str:
        return f'LinesChunk object for file {self._fileid}, starting at line {self._index} \nHash is {self._hash}'

class SuccessiveLinesLimits:
    """A class to handle the numbering of begin and end of successive lines.

    :note: Only the end line number can be updated.
    """
    __slots__ = ('_start', '_end')

    def __init__(self, start: LineNumber, end: LineNumber) -> None:
        self._start: LineNumber = start
        self._end: LineNumber = end

    def __repr__(self) -> str:
        return f'<SuccessiveLinesLimits <{self._start};{self._end}>>'

class LineSetStartCouple(NamedTuple):
    """Indices in both linesets that mark the beginning of successive lines."""
    fst_lineset_index: Index
    snd_lineset_index: Index

    def __repr__(self) -> str:
        return f'<LineSetStartCouple <{self.fst_lineset_index};{self.snd_lineset_index}>>'

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LineSetStartCouple):
            return NotImplemented
        return self.fst_lineset_index == other.fst_lineset_index and self.snd_lineset_index == other.snd_lineset_index

    def __hash__(self) -> int:
        return hash(self.fst_lineset_index) + hash(self.snd_lineset_index)
LinesChunkLimits_T = Tuple['LineSet', LineNumber, LineNumber]

def hash_lineset(lineset: LineSet, min_common_lines: int=DEFAULT_MIN_SIMILARITY_LINE) -> tuple[HashToIndex_T, IndexToLines_T]:
    """Return two dicts.

    The first associates the hash of successive stripped lines of a lineset
    to the indices of the starting lines.
    The second dict, associates the index of the starting line in the lineset's stripped lines to the
    couple [start, end] lines number in the corresponding file.

    :param lineset: lineset object (i.e the lines in a file)
    :param min_common_lines: number of successive lines that are used to compute the hash
    :return: a dict linking hashes to corresponding start index and a dict that links this
             index to the start and end lines in the file
    """
    hash_to_index = defaultdict(list)
    index_to_lines = {}
    
    for idx in range(len(lineset._stripped_lines) - min_common_lines + 1):
        lines = [line.text for line in lineset._stripped_lines[idx:idx + min_common_lines]]
        chunk = LinesChunk(lineset.name, idx, *lines)
        hash_to_index[chunk].append(Index(idx))
        
        start_line = lineset._stripped_lines[idx].line_number
        end_line = lineset._stripped_lines[idx + min_common_lines - 1].line_number
        index_to_lines[Index(idx)] = SuccessiveLinesLimits(LineNumber(start_line), LineNumber(end_line))
    
    return hash_to_index, index_to_lines

def remove_successive(all_couples: CplIndexToCplLines_T) -> None:
    """Removes all successive entries in the dictionary in argument.

    :param all_couples: collection that has to be cleaned up from successive entries.
                        The keys are couples of indices that mark the beginning of common entries
                        in both linesets. The values have two parts. The first one is the couple
                        of starting and ending line numbers of common successive lines in the first file.
                        The second part is the same for the second file.

    For example consider the following dict:

    >>> all_couples
    {(11, 34): ([5, 9], [27, 31]),
     (23, 79): ([15, 19], [45, 49]),
     (12, 35): ([6, 10], [28, 32])}

    There are two successive keys (11, 34) and (12, 35).
    It means there are two consecutive similar chunks of lines in both files.
    Thus remove last entry and update the last line numbers in the first entry

    >>> remove_successive(all_couples)
    >>> all_couples
    {(11, 34): ([5, 10], [27, 32]),
     (23, 79): ([15, 19], [45, 49])}
    """
    keys = sorted(all_couples.keys())
    for i in range(len(keys) - 1):
        current_key, next_key = keys[i], keys[i + 1]
        if (current_key[0] + 1 == next_key[0] and
            current_key[1] + 1 == next_key[1]):
            current_value = all_couples[current_key]
            next_value = all_couples[next_key]
            current_value.first_file._end = next_value.first_file._end
            current_value.second_file._end = next_value.second_file._end
            current_value.effective_cmn_lines_nb += next_value.effective_cmn_lines_nb
            del all_couples[next_key]

def filter_noncode_lines(ls_1: LineSet, stindex_1: Index, ls_2: LineSet, stindex_2: Index, common_lines_nb: int) -> int:
    """Return the effective number of common lines between lineset1
    and lineset2 filtered from non code lines.

    That is to say the number of common successive stripped
    lines except those that do not contain code (for example
    a line with only an ending parenthesis)

    :param ls_1: first lineset
    :param stindex_1: first lineset starting index
    :param ls_2: second lineset
    :param stindex_2: second lineset starting index
    :param common_lines_nb: number of common successive stripped lines before being filtered from non code lines
    :return: the number of common successive stripped lines that contain code
    """
    effective_common_lines = 0
    for i in range(common_lines_nb):
        line1 = ls_1[stindex_1 + i].text.strip()
        line2 = ls_2[stindex_2 + i].text.strip()
        if line1 and line2 and REGEX_FOR_LINES_WITH_CONTENT.match(line1) and REGEX_FOR_LINES_WITH_CONTENT.match(line2):
            effective_common_lines += 1
    return effective_common_lines

class Commonality(NamedTuple):
    cmn_lines_nb: int
    fst_lset: LineSet
    fst_file_start: LineNumber
    fst_file_end: LineNumber
    snd_lset: LineSet
    snd_file_start: LineNumber
    snd_file_end: LineNumber

class Similar:
    """Finds copy-pasted lines of code in a project."""

    def __init__(self, min_lines: int=DEFAULT_MIN_SIMILARITY_LINE, ignore_comments: bool=False, ignore_docstrings: bool=False, ignore_imports: bool=False, ignore_signatures: bool=False) -> None:
        if isinstance(self, BaseChecker):
            self.namespace = self.linter.config
        else:
            self.namespace = argparse.Namespace()
        self.namespace.min_similarity_lines = min_lines
        self.namespace.ignore_comments = ignore_comments
        self.namespace.ignore_docstrings = ignore_docstrings
        self.namespace.ignore_imports = ignore_imports
        self.namespace.ignore_signatures = ignore_signatures
        self.linesets: list[LineSet] = []

    def append_stream(self, streamid: str, stream: STREAM_TYPES, encoding: str | None=None) -> None:
        """Append a file to search for similarities."""
        if isinstance(stream, TextIO):
            data = stream.read()
        else:
            data = stream.read().decode(encoding or 'utf-8')
        
        lines = data.splitlines()
        self.linesets.append(LineSet(streamid, lines,
                                     self.namespace.ignore_comments,
                                     self.namespace.ignore_docstrings,
                                     self.namespace.ignore_imports,
                                     self.namespace.ignore_signatures))

    def run(self) -> None:
        """Start looking for similarities and display results on stdout."""
        similarities = self._compute_sims()
        self._display_sims(similarities)

    def _compute_sims(self) -> list[tuple[int, set[LinesChunkLimits_T]]]:
        """Compute similarities in appended files."""
        pass

    def _display_sims(self, similarities: list[tuple[int, set[LinesChunkLimits_T]]]) -> None:
        """Display computed similarities on stdout."""
        pass

    def _get_similarity_report(self, similarities: list[tuple[int, set[LinesChunkLimits_T]]]) -> str:
        """Create a report from similarities."""
        pass

    def _find_common(self, lineset1: LineSet, lineset2: LineSet) -> Generator[Commonality, None, None]:
        """Find similarities in the two given linesets.

        This the core of the algorithm. The idea is to compute the hashes of a
        minimal number of successive lines of each lineset and then compare the
        hashes. Every match of such comparison is stored in a dict that links the
        couple of starting indices in both linesets to the couple of corresponding
        starting and ending lines in both files.

        Last regroups all successive couples in a bigger one. It allows to take into
        account common chunk of lines that have more than the minimal number of
        successive lines required.
        """
        pass

    def _iter_sims(self) -> Generator[Commonality, None, None]:
        """Iterate on similarities among all files, by making a Cartesian
        product.
        """
        pass

    def get_map_data(self) -> list[LineSet]:
        """Returns the data we can use for a map/reduce process.

        In this case we are returning this instance's Linesets, that is all file
        information that will later be used for vectorisation.
        """
        pass

    def combine_mapreduce_data(self, linesets_collection: list[list[LineSet]]) -> None:
        """Reduces and recombines data into a format that we can report on.

        The partner function of get_map_data()
        """
        pass

def stripped_lines(lines: Iterable[str], ignore_comments: bool, ignore_docstrings: bool, ignore_imports: bool, ignore_signatures: bool, line_enabled_callback: Callable[[str, int], bool] | None=None) -> list[LineSpecifs]:
    """Return tuples of line/line number/line type with leading/trailing white-space and
    any ignored code features removed.

    :param lines: a collection of lines
    :param ignore_comments: if true, any comment in the lines collection is removed from the result
    :param ignore_docstrings: if true, any line that is a docstring is removed from the result
    :param ignore_imports: if true, any line that is an import is removed from the result
    :param ignore_signatures: if true, any line that is part of a function signature is removed from the result
    :param line_enabled_callback: If called with "R0801" and a line number, a return value of False will disregard
           the line
    :return: the collection of line/line number/line type tuples
    """
    pass

@functools.total_ordering
class LineSet:
    """Holds and indexes all the lines of a single source file.

    Allows for correspondence between real lines of the source file and stripped ones, which
    are the real ones from which undesired patterns have been removed.
    """

    def __init__(self, name: str, lines: list[str], ignore_comments: bool=False, ignore_docstrings: bool=False, ignore_imports: bool=False, ignore_signatures: bool=False, line_enabled_callback: Callable[[str, int], bool] | None=None) -> None:
        self.name = name
        self._real_lines = lines
        self._stripped_lines = stripped_lines(lines, ignore_comments, ignore_docstrings, ignore_imports, ignore_signatures, line_enabled_callback=line_enabled_callback)

    def __str__(self) -> str:
        return f'<Lineset for {self.name}>'

    def __len__(self) -> int:
        return len(self._real_lines)

    def __getitem__(self, index: int) -> LineSpecifs:
        return self._stripped_lines[index]

    def __lt__(self, other: LineSet) -> bool:
        return self.name < other.name

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LineSet):
            return False
        return self.__dict__ == other.__dict__
MSGS: dict[str, MessageDefinitionTuple] = {'R0801': ('Similar lines in %s files\n%s', 'duplicate-code', 'Indicates that a set of similar lines has been detected among multiple file. This usually means that the code should be refactored to avoid this duplication.')}

def report_similarities(sect: Section, stats: LinterStats, old_stats: LinterStats | None) -> None:
    """Make a layout with some stats about duplication."""
    pass

class SimilarChecker(BaseRawFileChecker, Similar):
    """Checks for similarities and duplicated code.

    This computation may be memory / CPU intensive, so you
    should disable it if you experience some problems.
    """
    name = 'similarities'
    msgs = MSGS
    options: Options = (('min-similarity-lines', {'default': DEFAULT_MIN_SIMILARITY_LINE, 'type': 'int', 'metavar': '<int>', 'help': 'Minimum lines number of a similarity.'}), ('ignore-comments', {'default': True, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Comments are removed from the similarity computation'}), ('ignore-docstrings', {'default': True, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Docstrings are removed from the similarity computation'}), ('ignore-imports', {'default': True, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Imports are removed from the similarity computation'}), ('ignore-signatures', {'default': True, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Signatures are removed from the similarity computation'}))
    reports = (('RP0801', 'Duplication', report_similarities),)

    def __init__(self, linter: PyLinter) -> None:
        BaseRawFileChecker.__init__(self, linter)
        Similar.__init__(self, min_lines=self.linter.config.min_similarity_lines, ignore_comments=self.linter.config.ignore_comments, ignore_docstrings=self.linter.config.ignore_docstrings, ignore_imports=self.linter.config.ignore_imports, ignore_signatures=self.linter.config.ignore_signatures)

    def open(self) -> None:
        """Init the checkers: reset linesets and statistics information."""
        pass

    def process_module(self, node: nodes.Module) -> None:
        """Process a module.

        the module's content is accessible via the stream object

        stream must implement the readlines method
        """
        pass

    def close(self) -> None:
        """Compute and display similarities on closing (i.e. end of parsing)."""
        pass

    def get_map_data(self) -> list[LineSet]:
        """Passthru override."""
        pass

    def reduce_map_data(self, linter: PyLinter, data: list[list[LineSet]]) -> None:
        """Reduces and recombines data into a format that we can report on.

        The partner function of get_map_data()

        Calls self.close() to actually calculate and report duplicate code.
        """
        pass

def usage(status: int=0) -> NoReturn:
    """Display command line usage information."""
    pass

def Run(argv: Sequence[str] | None=None) -> NoReturn:
    """Standalone command line access point."""
    pass
if __name__ == '__main__':
    Run()
