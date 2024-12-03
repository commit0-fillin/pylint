"""Graph manipulation utilities.

(dot generation adapted from pypy/translator/tool/make_dot.py)
"""
from __future__ import annotations
import codecs
import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from typing import Any

def target_info_from_filename(filename: str) -> tuple[str, str, str]:
    """Transforms /some/path/foo.png into ('/some/path', 'foo.png', 'png')."""
    directory, full_filename = os.path.split(filename)
    name, extension = os.path.splitext(full_filename)
    return directory, full_filename, extension[1:]  # Remove the dot from extension

class DotBackend:
    """Dot File back-end."""

    def __init__(self, graphname: str, rankdir: str | None=None, size: Any=None, ratio: Any=None, charset: str='utf-8', renderer: str='dot', additional_param: dict[str, Any] | None=None) -> None:
        if additional_param is None:
            additional_param = {}
        self.graphname = graphname
        self.renderer = renderer
        self.lines: list[str] = []
        self._source: str | None = None
        self.emit(f'digraph {normalize_node_id(graphname)} {{')
        if rankdir:
            self.emit(f'rankdir={rankdir}')
        if ratio:
            self.emit(f'ratio={ratio}')
        if size:
            self.emit(f'size="{size}"')
        if charset:
            assert charset.lower() in {'utf-8', 'iso-8859-1', 'latin1'}, f'unsupported charset {charset}'
            self.emit(f'charset="{charset}"')
        for param in additional_param.items():
            self.emit('='.join(param))

    def get_source(self) -> str:
        """Returns self._source."""
        if self._source is None:
            self._source = '\n'.join(self.lines)
        return self._source
    source = property(get_source)

    def generate(self, outputfile: str | None=None, mapfile: str | None=None) -> str:
        """Generates a graph file.

        :param str outputfile: filename and path [defaults to graphname.png]
        :param str mapfile: filename and path

        :rtype: str
        :return: a path to the generated file
        :raises RuntimeError: if the executable for rendering was not found
        """
        if outputfile is None:
            outputfile = f"{self.graphname}.png"
        self.emit("}")
        if shutil.which(self.renderer) is None:
            raise RuntimeError(f"The '{self.renderer}' executable was not found")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".dot", delete=False) as dotfile:
            dotfile.write(self.source)
            dotfile.flush()
            cmd = [self.renderer, "-Tpng", dotfile.name, "-o", outputfile]
            if mapfile:
                cmd += ["-Tcmapx", "-o", mapfile]
            subprocess.run(cmd, check=True, capture_output=True)
        return outputfile

    def emit(self, line: str) -> None:
        """Adds <line> to final output."""
        self.lines.append(line)

    def emit_edge(self, name1: str, name2: str, **props: Any) -> None:
        """Emit an edge from <name1> to <name2>.

        For edge properties: see https://www.graphviz.org/doc/info/attrs.html
        """
        edge = f'{normalize_node_id(name1)} -> {normalize_node_id(name2)}'
        if props:
            edge += ' [' + ','.join(f'{key}="{value}"' for key, value in props.items()) + ']'
        self.emit(edge + ';')

    def emit_node(self, name: str, **props: Any) -> None:
        """Emit a node with given properties.

        For node properties: see https://www.graphviz.org/doc/info/attrs.html
        """
        node = normalize_node_id(name)
        if props:
            node += ' [' + ','.join(f'{key}="{value}"' for key, value in props.items()) + ']'
        self.emit(node + ';')

def normalize_node_id(nid: str) -> str:
    """Returns a suitable DOT node id for `nid`."""
    return '"%s"' % nid.replace('"', '\\"')

def get_cycles(graph_dict: dict[str, set[str]], vertices: list[str] | None=None) -> Sequence[list[str]]:
    """Return a list of detected cycles based on an ordered graph (i.e. keys are
    vertices and values are lists of destination vertices representing edges).
    """
    if vertices is None:
        vertices = list(graph_dict.keys())
    result: list[list[str]] = []
    visited: set[str] = set()
    for vertice in vertices:
        if vertice not in visited:
            _get_cycles(graph_dict, [vertice], visited, result, vertice)
    return result

def _get_cycles(graph_dict: dict[str, set[str]], path: list[str], visited: set[str], result: list[list[str]], vertice: str) -> None:
    """Recursive function doing the real work for get_cycles."""
    visited.add(vertice)
    for neighbor in graph_dict.get(vertice, []):
        if neighbor not in path:
            _get_cycles(graph_dict, path + [neighbor], visited, result, neighbor)
        else:
            result.append(path[path.index(neighbor):])
