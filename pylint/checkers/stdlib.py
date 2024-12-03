"""Checkers for various standard library functions."""
from __future__ import annotations
import sys
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Dict, Set, Tuple
import astroid
from astroid import nodes, util
from astroid.typing import InferenceResult
from pylint import interfaces
from pylint.checkers import BaseChecker, DeprecatedMixin, utils
from pylint.interfaces import HIGH, INFERENCE
from pylint.typing import MessageDefinitionTuple
if TYPE_CHECKING:
    from pylint.lint import PyLinter
DeprecationDict = Dict[Tuple[int, int, int], Set[str]]
OPEN_FILES_MODE = ('open', 'file')
OPEN_FILES_FUNCS = (*OPEN_FILES_MODE, 'read_text', 'write_text')
UNITTEST_CASE = 'unittest.case'
THREADING_THREAD = 'threading.Thread'
COPY_COPY = 'copy.copy'
OS_ENVIRON = 'os._Environ'
ENV_GETTERS = ('os.getenv',)
SUBPROCESS_POPEN = 'subprocess.Popen'
SUBPROCESS_RUN = 'subprocess.run'
OPEN_MODULE = {'_io', 'pathlib'}
DEBUG_BREAKPOINTS = ('builtins.breakpoint', 'sys.breakpointhook', 'pdb.set_trace')
LRU_CACHE = {'functools.lru_cache', 'functools._lru_cache_wrapper.wrapper', 'functools.lru_cache.decorating_function'}
NON_INSTANCE_METHODS = {'builtins.staticmethod', 'builtins.classmethod'}
DEPRECATED_ARGUMENTS: dict[tuple[int, int, int], dict[str, tuple[tuple[int | None, str], ...]]] = {(0, 0, 0): {'int': ((None, 'x'),), 'bool': ((None, 'x'),), 'float': ((None, 'x'),)}, (3, 8, 0): {'asyncio.tasks.sleep': ((None, 'loop'),), 'asyncio.tasks.gather': ((None, 'loop'),), 'asyncio.tasks.shield': ((None, 'loop'),), 'asyncio.tasks.wait_for': ((None, 'loop'),), 'asyncio.tasks.wait': ((None, 'loop'),), 'asyncio.tasks.as_completed': ((None, 'loop'),), 'asyncio.subprocess.create_subprocess_exec': ((None, 'loop'),), 'asyncio.subprocess.create_subprocess_shell': ((4, 'loop'),), 'gettext.translation': ((5, 'codeset'),), 'gettext.install': ((2, 'codeset'),), 'functools.partialmethod': ((None, 'func'),), 'weakref.finalize': ((None, 'func'), (None, 'obj')), 'profile.Profile.runcall': ((None, 'func'),), 'cProfile.Profile.runcall': ((None, 'func'),), 'bdb.Bdb.runcall': ((None, 'func'),), 'trace.Trace.runfunc': ((None, 'func'),), 'curses.wrapper': ((None, 'func'),), 'unittest.case.TestCase.addCleanup': ((None, 'function'),), 'concurrent.futures.thread.ThreadPoolExecutor.submit': ((None, 'fn'),), 'concurrent.futures.process.ProcessPoolExecutor.submit': ((None, 'fn'),), 'contextlib._BaseExitStack.callback': ((None, 'callback'),), 'contextlib.AsyncExitStack.push_async_callback': ((None, 'callback'),), 'multiprocessing.managers.Server.create': ((None, 'c'), (None, 'typeid')), 'multiprocessing.managers.SharedMemoryServer.create': ((None, 'c'), (None, 'typeid'))}, (3, 9, 0): {'random.Random.shuffle': ((1, 'random'),)}, (3, 12, 0): {'argparse.BooleanOptionalAction': ((3, 'type'), (4, 'choices'), (7, 'metavar')), 'coroutine.throw': ((1, 'value'), (2, 'traceback')), 'email.utils.localtime': ((1, 'isdst'),), 'shutil.rmtree': ((2, 'onerror'),)}}
DEPRECATED_DECORATORS: DeprecationDict = {(3, 8, 0): {'asyncio.coroutine'}, (3, 3, 0): {'abc.abstractclassmethod', 'abc.abstractstaticmethod', 'abc.abstractproperty'}, (3, 4, 0): {'importlib.util.module_for_loader'}}
DEPRECATED_METHODS: dict[int, DeprecationDict] = {0: {(0, 0, 0): {'cgi.parse_qs', 'cgi.parse_qsl', 'ctypes.c_buffer', 'distutils.command.register.register.check_metadata', 'distutils.command.sdist.sdist.check_metadata', 'tkinter.Misc.tk_menuBar', 'tkinter.Menu.tk_bindForTraversal'}}, 2: {(2, 6, 0): {'commands.getstatus', 'os.popen2', 'os.popen3', 'os.popen4', 'macostools.touched'}, (2, 7, 0): {'unittest.case.TestCase.assertEquals', 'unittest.case.TestCase.assertNotEquals', 'unittest.case.TestCase.assertAlmostEquals', 'unittest.case.TestCase.assertNotAlmostEquals', 'unittest.case.TestCase.assert_', 'xml.etree.ElementTree.Element.getchildren', 'xml.etree.ElementTree.Element.getiterator', 'xml.etree.ElementTree.XMLParser.getiterator', 'xml.etree.ElementTree.XMLParser.doctype'}}, 3: {(3, 0, 0): {'inspect.getargspec', 'failUnlessEqual', 'assertEquals', 'failIfEqual', 'assertNotEquals', 'failUnlessAlmostEqual', 'assertAlmostEquals', 'failIfAlmostEqual', 'assertNotAlmostEquals', 'failUnless', 'assert_', 'failUnlessRaises', 'failIf', 'assertRaisesRegexp', 'assertRegexpMatches', 'assertNotRegexpMatches'}, (3, 1, 0): {'base64.encodestring', 'base64.decodestring', 'ntpath.splitunc', 'os.path.splitunc', 'os.stat_float_times', 'turtle.RawTurtle.settiltangle'}, (3, 2, 0): {'cgi.escape', 'configparser.RawConfigParser.readfp', 'xml.etree.ElementTree.Element.getchildren', 'xml.etree.ElementTree.Element.getiterator', 'xml.etree.ElementTree.XMLParser.getiterator', 'xml.etree.ElementTree.XMLParser.doctype'}, (3, 3, 0): {'inspect.getmoduleinfo', 'logging.warn', 'logging.Logger.warn', 'logging.LoggerAdapter.warn', 'nntplib._NNTPBase.xpath', 'platform.popen', 'sqlite3.OptimizedUnicode', 'time.clock'}, (3, 4, 0): {'importlib.find_loader', 'importlib.abc.Loader.load_module', 'importlib.abc.Loader.module_repr', 'importlib.abc.PathEntryFinder.find_loader', 'importlib.abc.PathEntryFinder.find_module', 'plistlib.readPlist', 'plistlib.writePlist', 'plistlib.readPlistFromBytes', 'plistlib.writePlistToBytes'}, (3, 4, 4): {'asyncio.tasks.async'}, (3, 5, 0): {'fractions.gcd', 'inspect.formatargspec', 'inspect.getcallargs', 'platform.linux_distribution', 'platform.dist'}, (3, 6, 0): {'importlib._bootstrap_external.FileLoader.load_module', '_ssl.RAND_pseudo_bytes'}, (3, 7, 0): {'sys.set_coroutine_wrapper', 'sys.get_coroutine_wrapper', 'aifc.openfp', 'threading.Thread.isAlive', 'asyncio.Task.current_task', 'asyncio.Task.all_task', 'locale.format', 'ssl.wrap_socket', 'ssl.match_hostname', 'sunau.openfp', 'wave.openfp'}, (3, 8, 0): {'gettext.lgettext', 'gettext.ldgettext', 'gettext.lngettext', 'gettext.ldngettext', 'gettext.bind_textdomain_codeset', 'gettext.NullTranslations.output_charset', 'gettext.NullTranslations.set_output_charset', 'threading.Thread.isAlive'}, (3, 9, 0): {'binascii.b2a_hqx', 'binascii.a2b_hqx', 'binascii.rlecode_hqx', 'binascii.rledecode_hqx', 'importlib.resources.contents', 'importlib.resources.is_resource', 'importlib.resources.open_binary', 'importlib.resources.open_text', 'importlib.resources.path', 'importlib.resources.read_binary', 'importlib.resources.read_text'}, (3, 10, 0): {'_sqlite3.enable_shared_cache', 'importlib.abc.Finder.find_module', 'pathlib.Path.link_to', 'zipimport.zipimporter.load_module', 'zipimport.zipimporter.find_module', 'zipimport.zipimporter.find_loader', 'threading.currentThread', 'threading.activeCount', 'threading.Condition.notifyAll', 'threading.Event.isSet', 'threading.Thread.setName', 'threading.Thread.getName', 'threading.Thread.isDaemon', 'threading.Thread.setDaemon', 'cgi.log'}, (3, 11, 0): {'locale.getdefaultlocale', 'locale.resetlocale', 're.template', 'unittest.findTestCases', 'unittest.makeSuite', 'unittest.getTestCaseNames', 'unittest.TestLoader.loadTestsFromModule', 'unittest.TestLoader.loadTestsFromTestCase', 'unittest.TestLoader.getTestCaseNames', 'unittest.TestProgram.usageExit'}, (3, 12, 0): {'builtins.bool.__invert__', 'datetime.datetime.utcfromtimestamp', 'datetime.datetime.utcnow', 'pkgutil.find_loader', 'pkgutil.get_loader', 'pty.master_open', 'pty.slave_open', 'xml.etree.ElementTree.Element.__bool__'}}}
DEPRECATED_CLASSES: dict[tuple[int, int, int], dict[str, set[str]]] = {(3, 2, 0): {'configparser': {'LegacyInterpolation', 'SafeConfigParser'}}, (3, 3, 0): {'importlib.abc': {'Finder'}, 'pkgutil': {'ImpImporter', 'ImpLoader'}, 'collections': {'Awaitable', 'Coroutine', 'AsyncIterable', 'AsyncIterator', 'AsyncGenerator', 'Hashable', 'Iterable', 'Iterator', 'Generator', 'Reversible', 'Sized', 'Container', 'Callable', 'Collection', 'Set', 'MutableSet', 'Mapping', 'MutableMapping', 'MappingView', 'KeysView', 'ItemsView', 'ValuesView', 'Sequence', 'MutableSequence', 'ByteString'}}, (3, 9, 0): {'smtpd': {'MailmanProxy'}}, (3, 11, 0): {'typing': {'Text'}, 'webbrowser': {'MacOSX'}}, (3, 12, 0): {'ast': {'Bytes', 'Ellipsis', 'NameConstant', 'Num', 'Str'}, 'asyncio': {'AbstractChildWatcher', 'MultiLoopChildWatcher', 'FastChildWatcher', 'SafeChildWatcher'}, 'collections.abc': {'ByteString'}, 'importlib.abc': {'ResourceReader', 'Traversable', 'TraversableResources'}, 'typing': {'ByteString', 'Hashable', 'Sized'}}}
DEPRECATED_ATTRIBUTES: DeprecationDict = {(3, 2, 0): {'configparser.ParsingError.filename'}, (3, 12, 0): {'calendar.January', 'calendar.February', 'sys.last_traceback', 'sys.last_type', 'sys.last_value'}}

class StdlibChecker(DeprecatedMixin, BaseChecker):
    name = 'stdlib'
    msgs: dict[str, MessageDefinitionTuple] = {**DeprecatedMixin.DEPRECATED_METHOD_MESSAGE, **DeprecatedMixin.DEPRECATED_ARGUMENT_MESSAGE, **DeprecatedMixin.DEPRECATED_CLASS_MESSAGE, **DeprecatedMixin.DEPRECATED_DECORATOR_MESSAGE, **DeprecatedMixin.DEPRECATED_ATTRIBUTE_MESSAGE, 'W1501': ('"%s" is not a valid mode for open.', 'bad-open-mode', 'Python supports: r, w, a[, x] modes with b, +, and U (only with r) options. See https://docs.python.org/3/library/functions.html#open'), 'W1502': ('Using datetime.time in a boolean context.', 'boolean-datetime', 'Using datetime.time in a boolean context can hide subtle bugs when the time they represent matches midnight UTC. This behaviour was fixed in Python 3.5. See https://bugs.python.org/issue13936 for reference.', {'maxversion': (3, 5)}), 'W1503': ('Redundant use of %s with constant value %r', 'redundant-unittest-assert', 'The first argument of assertTrue and assertFalse is a condition. If a constant is passed as parameter, that condition will be always true. In this case a warning should be emitted.'), 'W1506': ('threading.Thread needs the target function', 'bad-thread-instantiation', 'The warning is emitted when a threading.Thread class is instantiated without the target function being passed as a kwarg or as a second argument. By default, the first parameter is the group param, not the target param.'), 'W1507': ('Using copy.copy(os.environ). Use os.environ.copy() instead.', 'shallow-copy-environ', 'os.environ is not a dict object but proxy object, so shallow copy has still effects on original object. See https://bugs.python.org/issue15373 for reference.'), 'E1507': ('%s does not support %s type argument', 'invalid-envvar-value', 'Env manipulation functions support only string type arguments. See https://docs.python.org/3/library/os.html#os.getenv.'), 'E1519': ('singledispatch decorator should not be used with methods, use singledispatchmethod instead.', 'singledispatch-method', 'singledispatch should decorate functions and not class/instance methods. Use singledispatchmethod for those cases.'), 'E1520': ('singledispatchmethod decorator should not be used with functions, use singledispatch instead.', 'singledispatchmethod-function', 'singledispatchmethod should decorate class/instance methods and not functions. Use singledispatch for those cases.'), 'W1508': ('%s default type is %s. Expected str or None.', 'invalid-envvar-default', 'Env manipulation functions return None or str values. Supplying anything different as a default may cause bugs. See https://docs.python.org/3/library/os.html#os.getenv.'), 'W1509': ('Using preexec_fn keyword which may be unsafe in the presence of threads', 'subprocess-popen-preexec-fn', 'The preexec_fn parameter is not safe to use in the presence of threads in your application. The child process could deadlock before exec is called. If you must use it, keep it trivial! Minimize the number of libraries you call into. See https://docs.python.org/3/library/subprocess.html#popen-constructor'), 'W1510': ("'subprocess.run' used without explicitly defining the value for 'check'.", 'subprocess-run-check', "The ``check`` keyword  is set to False by default. It means the process launched by ``subprocess.run`` can exit with a non-zero exit code and fail silently. It's better to set it explicitly to make clear what the error-handling behavior is."), 'W1514': ('Using open without explicitly specifying an encoding', 'unspecified-encoding', 'It is better to specify an encoding when opening documents. Using the system default implicitly can create problems on other operating systems. See https://peps.python.org/pep-0597/'), 'W1515': ('Leaving functions creating breakpoints in production code is not recommended', 'forgotten-debug-statement', 'Calls to breakpoint(), sys.breakpointhook() and pdb.set_trace() should be removed from code that is not actively being debugged.'), 'W1518': ("'lru_cache(maxsize=None)' or 'cache' will keep all method args alive indefinitely, including 'self'", 'method-cache-max-size-none', "By decorating a method with lru_cache or cache the 'self' argument will be linked to the function and therefore never garbage collected. Unless your instance will never need to be garbage collected (singleton) it is recommended to refactor code to avoid this pattern or add a maxsize to the cache. The default value for maxsize is 128.", {'old_names': [('W1516', 'lru-cache-decorating-method'), ('W1517', 'cache-max-size-none')]})}

    def __init__(self, linter: PyLinter) -> None:
        BaseChecker.__init__(self, linter)
        self._deprecated_methods: set[str] = set()
        self._deprecated_arguments: dict[str, tuple[tuple[int | None, str], ...]] = {}
        self._deprecated_classes: dict[str, set[str]] = {}
        self._deprecated_decorators: set[str] = set()
        self._deprecated_attributes: set[str] = set()
        for since_vers, func_list in DEPRECATED_METHODS[sys.version_info[0]].items():
            if since_vers <= sys.version_info:
                self._deprecated_methods.update(func_list)
        for since_vers, args_list in DEPRECATED_ARGUMENTS.items():
            if since_vers <= sys.version_info:
                self._deprecated_arguments.update(args_list)
        for since_vers, class_list in DEPRECATED_CLASSES.items():
            if since_vers <= sys.version_info:
                self._deprecated_classes.update(class_list)
        for since_vers, decorator_list in DEPRECATED_DECORATORS.items():
            if since_vers <= sys.version_info:
                self._deprecated_decorators.update(decorator_list)
        for since_vers, attribute_list in DEPRECATED_ATTRIBUTES.items():
            if since_vers <= sys.version_info:
                self._deprecated_attributes.update(attribute_list)

    @utils.only_required_for_messages('bad-open-mode', 'redundant-unittest-assert', 'deprecated-method', 'deprecated-argument', 'bad-thread-instantiation', 'shallow-copy-environ', 'invalid-envvar-value', 'invalid-envvar-default', 'subprocess-popen-preexec-fn', 'subprocess-run-check', 'deprecated-class', 'unspecified-encoding', 'forgotten-debug-statement')
    def visit_call(self, node: nodes.Call) -> None:
        """Visit a Call node."""
        if isinstance(node.func, nodes.Name):
            name = node.func.name
            # Check for various issues
            if name in OPEN_FILES_MODE:
                self._check_open_call(node, name)
            elif name == 'thread':
                self._check_thread_instantiation(node)
            elif name == 'copy':
                self._check_shallow_copy_environ(node)
            elif name in ENV_GETTERS:
                self._check_env_function(node, name)
            elif name == 'subprocess.Popen':
                self._check_subprocess_popen(node)
            elif name == 'subprocess.run':
                self._check_subprocess_run(node)
        
        # Check for deprecated methods, arguments, and classes
        self._check_deprecated_method(node)
        self._check_deprecated_argument(node)
        self._check_deprecated_class(node)
        
        # Check for unspecified encoding in open() calls
        if isinstance(node.func, nodes.Attribute) and node.func.attrname in OPEN_FILES_FUNCS:
            self._check_open_encoding(node)
        
        # Check for forgotten debug statements
        if isinstance(node.func, (nodes.Name, nodes.Attribute)):
            self._check_forgotten_debug_statement(node)

    def _check_lru_cache_decorators(self, node: nodes.FunctionDef) -> None:
        """Check if instance methods are decorated with functools.lru_cache."""
        if not node.decorators:
            return

        for decorator in node.decorators.nodes:
            if isinstance(decorator, nodes.Call):
                decorator = decorator.func
            if not isinstance(decorator, (nodes.Name, nodes.Attribute)):
                continue

            if utils.is_typing_member(decorator, ('lru_cache', 'cache')):
                if utils.is_attribute_typed_annotation(node.parent, node.name):
                    continue
                if utils.decorated_with(node, ('staticmethod', 'classmethod')):
                    continue
                if utils.get_node_first_ancestor_of_type(node, nodes.ClassDef):
                    self.add_message(
                        'method-cache-max-size-none',
                        node=node,
                        args=(decorator.as_string(),),
                    )

    def _check_datetime(self, node: nodes.NodeNG) -> None:
        """Check that a datetime was inferred, if so, emit boolean-datetime warning."""
        try:
            inferred = next(node.infer())
        except astroid.InferenceError:
            return
        if isinstance(inferred, astroid.Instance) and inferred.qname() == 'datetime.time':
            self.add_message('boolean-datetime', node=node)

    def _check_open_call(self, node: nodes.Call, open_module: str, func_name: str) -> None:
        """Various checks for an open call."""
        if open_module not in OPEN_MODULE:
            return
        if node.keywords:
            mode = utils.get_argument_from_call(node, position=1, keyword='mode')
            if isinstance(mode, nodes.Const):
                mode_value = mode.value
                if mode_value not in ('r', 'rb', 'r+', 'rb+', 'w', 'wb', 'w+', 'wb+', 'a', 'ab', 'a+', 'ab+'):
                    self.add_message('bad-open-mode', node=node, args=mode_value)
        elif len(node.args) >= 2:
            mode = node.args[1]
            if isinstance(mode, nodes.Const):
                mode_value = mode.value
                if mode_value not in ('r', 'rb', 'r+', 'rb+', 'w', 'wb', 'w+', 'wb+', 'a', 'ab', 'a+', 'ab+'):
                    self.add_message('bad-open-mode', node=node, args=mode_value)
