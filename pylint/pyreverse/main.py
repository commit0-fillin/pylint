"""Create UML diagrams for classes and modules in <packages>."""
from __future__ import annotations
import sys
from collections.abc import Sequence
from typing import NoReturn
from pylint import constants
from pylint.config.arguments_manager import _ArgumentsManager
from pylint.config.arguments_provider import _ArgumentsProvider
from pylint.lint import discover_package_path
from pylint.lint.utils import augmented_sys_path
from pylint.pyreverse import writer
from pylint.pyreverse.diadefslib import DiadefsHandler
from pylint.pyreverse.inspector import Linker, project_from_files
from pylint.pyreverse.utils import check_graphviz_availability, check_if_graphviz_supports_format, insert_default_options
from pylint.typing import Options
DIRECTLY_SUPPORTED_FORMATS = ('dot', 'puml', 'plantuml', 'mmd', 'html')
DEFAULT_COLOR_PALETTE = ('#77AADD', '#99DDFF', '#44BB99', '#BBCC33', '#AAAA00', '#EEDD88', '#EE8866', '#FFAABB', '#DDDDDD')
OPTIONS: Options = (('filter-mode', {'short': 'f', 'default': 'PUB_ONLY', 'dest': 'mode', 'type': 'string', 'action': 'store', 'metavar': '<mode>', 'help': "filter attributes and functions according to\n    <mode>. Correct modes are :\n                            'PUB_ONLY' filter all non public attributes\n                                [DEFAULT], equivalent to PRIVATE+SPECIAL_A\n                            'ALL' no filter\n                            'SPECIAL' filter Python special functions\n                                except constructor\n                            'OTHER' filter protected and private\n                                attributes"}), ('class', {'short': 'c', 'action': 'extend', 'metavar': '<class>', 'type': 'csv', 'dest': 'classes', 'default': None, 'help': 'create a class diagram with all classes related to <class>; this uses by default the options -ASmy'}), ('show-ancestors', {'short': 'a', 'action': 'store', 'metavar': '<ancestor>', 'type': 'int', 'default': None, 'help': 'show <ancestor> generations of ancestor classes not in <projects>'}), ('all-ancestors', {'short': 'A', 'default': None, 'action': 'store_true', 'help': 'show all ancestors off all classes in <projects>'}), ('show-associated', {'short': 's', 'action': 'store', 'metavar': '<association_level>', 'type': 'int', 'default': None, 'help': 'show <association_level> levels of associated classes not in <projects>'}), ('all-associated', {'short': 'S', 'default': None, 'action': 'store_true', 'help': 'show recursively all associated off all associated classes'}), ('show-builtin', {'short': 'b', 'action': 'store_true', 'default': False, 'help': 'include builtin objects in representation of classes'}), ('show-stdlib', {'short': 'L', 'action': 'store_true', 'default': False, 'help': 'include standard library objects in representation of classes'}), ('module-names', {'short': 'm', 'default': None, 'type': 'yn', 'metavar': '<y or n>', 'help': 'include module name in representation of classes'}), ('only-classnames', {'short': 'k', 'action': 'store_true', 'default': False, 'help': "don't show attributes and methods in the class boxes; this disables -f values"}), ('no-standalone', {'action': 'store_true', 'default': False, 'help': 'only show nodes with connections'}), ('output', {'short': 'o', 'dest': 'output_format', 'action': 'store', 'default': 'dot', 'metavar': '<format>', 'type': 'string', 'help': f"create a *.<format> output file if format is available. Available formats are: {', '.join(DIRECTLY_SUPPORTED_FORMATS)}. Any other format will be tried to create by means of the 'dot' command line tool, which requires a graphviz installation."}), ('colorized', {'dest': 'colorized', 'action': 'store_true', 'default': False, 'help': 'Use colored output. Classes/modules of the same package get the same color.'}), ('max-color-depth', {'dest': 'max_color_depth', 'action': 'store', 'default': 2, 'metavar': '<depth>', 'type': 'int', 'help': 'Use separate colors up to package depth of <depth>'}), ('color-palette', {'dest': 'color_palette', 'action': 'store', 'default': DEFAULT_COLOR_PALETTE, 'metavar': '<color1,color2,...>', 'type': 'csv', 'help': 'Comma separated list of colors to use'}), ('ignore', {'type': 'csv', 'metavar': '<file[,file...]>', 'dest': 'ignore_list', 'default': constants.DEFAULT_IGNORE_LIST, 'help': 'Files or directories to be skipped. They should be base names, not paths.'}), ('project', {'default': '', 'type': 'string', 'short': 'p', 'metavar': '<project name>', 'help': 'set the project name.'}), ('output-directory', {'default': '', 'type': 'path', 'short': 'd', 'action': 'store', 'metavar': '<output_directory>', 'help': 'set the output directory path.'}), ('source-roots', {'type': 'glob_paths_csv', 'metavar': '<path>[,<path>...]', 'default': (), 'help': 'Add paths to the list of the source roots. Supports globbing patterns. The source root is an absolute path or a path relative to the current working directory used to determine a package namespace for modules located under the source root.'}), ('verbose', {'action': 'store_true', 'default': False, 'help': 'Makes pyreverse more verbose/talkative. Mostly useful for debugging.'}))

class Run(_ArgumentsManager, _ArgumentsProvider):
    """Base class providing common behaviour for pyreverse commands."""
    options = OPTIONS
    name = 'pyreverse'

    def __init__(self, args: Sequence[str]) -> NoReturn:
        if '--version' in args:
            print('pyreverse is included in pylint:')
            print(constants.full_version)
            sys.exit(0)
        _ArgumentsManager.__init__(self, prog='pyreverse', description=__doc__)
        _ArgumentsProvider.__init__(self, self)
        insert_default_options()
        args = self._parse_command_line_configuration(args)
        if self.config.output_format not in DIRECTLY_SUPPORTED_FORMATS:
            check_graphviz_availability()
            print(f'Format {self.config.output_format} is not supported natively. Pyreverse will try to generate it using Graphviz...')
            check_if_graphviz_supports_format(self.config.output_format)
        sys.exit(self.run(args))

    def run(self, args: list[str]) -> int:
        """Checking arguments and run project."""
        if not args:
            print("No files or modules to analyze. Please provide at least one.")
            return 1

        try:
            project = project_from_files(
                args,
                project_name=self.config.project,
                black_list=self.config.ignore_list,
                verbose=self.config.verbose
            )
            linker = Linker(project)
            handler = DiadefsHandler(self.config)
            diadefs = handler.get_diadefs(project, linker)
            writer = DiagramWriter(self.config)
            writer.write(diadefs)
        except Exception as ex:
            print(f"An error occurred: {ex}", file=sys.stderr)
            if self.config.verbose:
                traceback.print_exc()
            return 1

        return 0
if __name__ == '__main__':
    Run(sys.argv[1:])
