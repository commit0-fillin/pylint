"""Pylint plugin for checking in Sphinx, Google, or Numpy style docstrings."""
from __future__ import annotations
import re
from typing import TYPE_CHECKING
import astroid
from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.checkers import utils as checker_utils
from pylint.extensions import _check_docs_utils as utils
from pylint.extensions._check_docs_utils import Docstring
from pylint.interfaces import HIGH
if TYPE_CHECKING:
    from pylint.lint import PyLinter

class DocstringParameterChecker(BaseChecker):
    """Checker for Sphinx, Google, or Numpy style docstrings.

    * Check that all function, method and constructor parameters are mentioned
      in the params and types part of the docstring.  Constructor parameters
      can be documented in either the class docstring or ``__init__`` docstring,
      but not both.
    * Check that there are no naming inconsistencies between the signature and
      the documentation, i.e. also report documented parameters that are missing
      in the signature. This is important to find cases where parameters are
      renamed only in the code, not in the documentation.
    * Check that all explicitly raised exceptions in a function are documented
      in the function docstring. Caught exceptions are ignored.

    Activate this checker by adding the line::

        load-plugins=pylint.extensions.docparams

    to the ``MAIN`` section of your ``.pylintrc``.
    """
    name = 'parameter_documentation'
    msgs = {'W9005': ('"%s" has constructor parameters documented in class and __init__', 'multiple-constructor-doc', 'Please remove parameter declarations in the class or constructor.'), 'W9006': ('"%s" not documented as being raised', 'missing-raises-doc', 'Please document exceptions for all raised exception types.'), 'W9008': ('Redundant returns documentation', 'redundant-returns-doc', 'Please remove the return/rtype documentation from this method.'), 'W9010': ('Redundant yields documentation', 'redundant-yields-doc', 'Please remove the yields documentation from this method.'), 'W9011': ('Missing return documentation', 'missing-return-doc', 'Please add documentation about what this method returns.', {'old_names': [('W9007', 'old-missing-returns-doc')]}), 'W9012': ('Missing return type documentation', 'missing-return-type-doc', 'Please document the type returned by this method.'), 'W9013': ('Missing yield documentation', 'missing-yield-doc', 'Please add documentation about what this generator yields.', {'old_names': [('W9009', 'old-missing-yields-doc')]}), 'W9014': ('Missing yield type documentation', 'missing-yield-type-doc', 'Please document the type yielded by this method.'), 'W9015': ('"%s" missing in parameter documentation', 'missing-param-doc', 'Please add parameter declarations for all parameters.', {'old_names': [('W9003', 'old-missing-param-doc')]}), 'W9016': ('"%s" missing in parameter type documentation', 'missing-type-doc', 'Please add parameter type declarations for all parameters.', {'old_names': [('W9004', 'old-missing-type-doc')]}), 'W9017': ('"%s" differing in parameter documentation', 'differing-param-doc', 'Please check parameter names in declarations.'), 'W9018': ('"%s" differing in parameter type documentation', 'differing-type-doc', 'Please check parameter names in type declarations.'), 'W9019': ('"%s" useless ignored parameter documentation', 'useless-param-doc', 'Please remove the ignored parameter documentation.'), 'W9020': ('"%s" useless ignored parameter type documentation', 'useless-type-doc', 'Please remove the ignored parameter type documentation.'), 'W9021': ('Missing any documentation in "%s"', 'missing-any-param-doc', 'Please add parameter and/or type documentation.')}
    options = (('accept-no-param-doc', {'default': True, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Whether to accept totally missing parameter documentation in the docstring of a function that has parameters.'}), ('accept-no-raise-doc', {'default': True, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Whether to accept totally missing raises documentation in the docstring of a function that raises an exception.'}), ('accept-no-return-doc', {'default': True, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Whether to accept totally missing return documentation in the docstring of a function that returns a statement.'}), ('accept-no-yields-doc', {'default': True, 'type': 'yn', 'metavar': '<y or n>', 'help': 'Whether to accept totally missing yields documentation in the docstring of a generator.'}), ('default-docstring-type', {'type': 'choice', 'default': 'default', 'metavar': '<docstring type>', 'choices': list(utils.DOCSTRING_TYPES), 'help': 'If the docstring type cannot be guessed the specified docstring type will be used.'}))
    constructor_names = {'__init__', '__new__'}
    not_needed_param_in_docstring = {'self', 'cls'}

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Called for function and method definitions (def).

        :param node: Node for a function or method definition in the AST
        :type node: :class:`astroid.scoped_nodes.Function`
        """
        if not node.doc:
            return  # No docstring, no need to check

        doc = utils.parse_docstring(node)
        self.check_arguments_in_docstring(doc, node.args, node)
        
        # Check return values
        if node.returns:
            return_nodes = node.nodes_of_class(nodes.Return)
            if return_nodes:
                self.check_return_doc(node, doc)
            else:
                self.add_message(
                    "redundant-returns-doc",
                    node=node,
                    confidence=HIGH,
                )
        elif any(isinstance(child, nodes.Return) for child in node.body if child.value is not None):
            self.check_return_doc(node, doc)

        # Check raised exceptions
        self.check_raises_doc(node, doc)
    visit_asyncfunctiondef = visit_functiondef
    visit_yieldfrom = visit_yield

    def _compare_missing_args(self, found_argument_names: set[str], message_id: str, not_needed_names: set[str], expected_argument_names: set[str], warning_node: nodes.NodeNG) -> None:
        """Compare the found argument names with the expected ones and
        generate a message if there are arguments missing.

        :param found_argument_names: argument names found in the docstring
        :param message_id: pylint message id
        :param not_needed_names: names that may be omitted
        :param expected_argument_names: Expected argument names
        :param warning_node: The node to be analyzed
        """
        missing_args = (expected_argument_names - found_argument_names) - not_needed_names
        if missing_args:
            self.add_message(
                message_id,
                args=(", ".join(sorted(missing_args)),),
                node=warning_node,
                confidence=HIGH,
            )

    def _compare_different_args(self, found_argument_names: set[str], message_id: str, not_needed_names: set[str], expected_argument_names: set[str], warning_node: nodes.NodeNG) -> None:
        """Compare the found argument names with the expected ones and
        generate a message if there are extra arguments found.

        :param found_argument_names: argument names found in the docstring
        :param message_id: pylint message id
        :param not_needed_names: names that may be omitted
        :param expected_argument_names: Expected argument names
        :param warning_node: The node to be analyzed
        """
        different_args = (found_argument_names - expected_argument_names) - not_needed_names
        if different_args:
            self.add_message(
                message_id,
                args=(", ".join(sorted(different_args)),),
                node=warning_node,
                confidence=HIGH,
            )

    def _compare_ignored_args(self, found_argument_names: set[str], message_id: str, ignored_argument_names: set[str], warning_node: nodes.NodeNG) -> None:
        """Compare the found argument names with the ignored ones and
        generate a message if there are ignored arguments found.

        :param found_argument_names: argument names found in the docstring
        :param message_id: pylint message id
        :param ignored_argument_names: Expected argument names
        :param warning_node: The node to be analyzed
        """
        ignored_args = found_argument_names & ignored_argument_names
        if ignored_args:
            self.add_message(
                message_id,
                args=(", ".join(sorted(ignored_args)),),
                node=warning_node,
                confidence=HIGH,
            )

    def check_arguments_in_docstring(self, doc: Docstring, arguments_node: astroid.Arguments, warning_node: astroid.NodeNG, accept_no_param_doc: bool | None=None) -> None:
        """Check that all parameters are consistent with the parameters mentioned
        in the parameter documentation (e.g. the Sphinx tags 'param' and 'type').

        * Undocumented parameters except 'self' are noticed.
        * Undocumented parameter types except for 'self' and the ``*<args>``
          and ``**<kwargs>`` parameters are noticed.
        * Parameters mentioned in the parameter documentation that don't or no
          longer exist in the function parameter list are noticed.
        * If the text "For the parameters, see" or "For the other parameters,
          see" (ignoring additional white-space) is mentioned in the docstring,
          missing parameter documentation is tolerated.
        * If there's no Sphinx style, Google style or NumPy style parameter
          documentation at all, i.e. ``:param`` is never mentioned etc., the
          checker assumes that the parameters are documented in another format
          and the absence is tolerated.

        :param doc: Docstring for the function, method or class.
        :type doc: :class:`Docstring`

        :param arguments_node: Arguments node for the function, method or
            class constructor.
        :type arguments_node: :class:`astroid.scoped_nodes.Arguments`

        :param warning_node: The node to assign the warnings to
        :type warning_node: :class:`astroid.scoped_nodes.Node`

        :param accept_no_param_doc: Whether to allow no parameters to be
            documented. If None then this value is read from the configuration.
        :type accept_no_param_doc: bool or None
        """
        if accept_no_param_doc is None:
            accept_no_param_doc = self.config.accept_no_param_doc

        expected_argument_names = set(arguments_node.arguments)
        expected_argument_names.update(arguments_node.kwonlyargs)

        if arguments_node.vararg:
            expected_argument_names.add(arguments_node.vararg)
        if arguments_node.kwarg:
            expected_argument_names.add(arguments_node.kwarg)

        found_argument_names = set(doc.params.keys())
        not_needed_names = self.not_needed_param_in_docstring

        if doc.params and not accept_no_param_doc:
            self._compare_missing_args(
                found_argument_names,
                'missing-param-doc',
                not_needed_names,
                expected_argument_names,
                warning_node,
            )

            self._compare_different_args(
                found_argument_names,
                'differing-param-doc',
                not_needed_names,
                expected_argument_names,
                warning_node,
            )

        if doc.params and not accept_no_param_doc:
            self._compare_ignored_args(
                found_argument_names,
                'useless-param-doc',
                not_needed_names,
                warning_node,
            )

    def _add_raise_message(self, missing_exceptions: set[str], node: nodes.FunctionDef) -> None:
        """Adds a message on :param:`node` for the missing exception type.

        :param missing_exceptions: A list of missing exception types.
        :param node: The node show the message on.
        """
        if missing_exceptions:
            self.add_message(
                'missing-raises-doc',
                args=(', '.join(sorted(missing_exceptions)),),
                node=node,
                confidence=HIGH,
            )
