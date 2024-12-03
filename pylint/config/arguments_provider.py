"""Arguments provider class used to expose options."""
from __future__ import annotations
from collections.abc import Iterator
from typing import Any
import warnings
from pylint.config.arguments_manager import _ArgumentsManager
from pylint.typing import OptionDict, Options

class _ArgumentsProvider:
    """Base class for classes that provide arguments."""
    name: str
    'Name of the provider.'
    options: Options = ()
    'Options provided by this provider.'
    option_groups_descs: dict[str, str] = {}
    'Option groups of this provider and their descriptions.'

    def __init__(self, arguments_manager: _ArgumentsManager) -> None:
        self._arguments_manager = arguments_manager
        'The manager that will parse and register any options provided.'
        self._arguments_manager._register_options_provider(self)

    def _option_value(self, opt: str) -> Any:
        """Get the current value for the given option."""
        return getattr(self._arguments_manager.config, opt, None)

    def _options_by_section(self) -> Iterator[tuple[str, list[tuple[str, OptionDict, Any]]] | tuple[None, dict[str, list[tuple[str, OptionDict, Any]]]]]:
        """Return an iterator on options grouped by section.

        (section, [list of (optname, optdict, optvalue)])
        """
        sections: dict[str, list[tuple[str, OptionDict, Any]]] = {}
        for optname, optdict in self._arguments_manager._option_dicts.items():
            sections.setdefault(optdict.get('group', ''), []).append(
                (optname, optdict, self._option_value(optname))
            )
        
        if len(sections) == 1:
            # If there's only one section, return it directly
            return next(iter(sections.items()))
        
        # If there are multiple sections, return them as a dict
        return (None, sections)

    def _options_and_values(self, options: Options | None=None) -> Iterator[tuple[str, OptionDict, Any]]:
        """DEPRECATED."""
        warnings.warn("The _options_and_values method is deprecated.", DeprecationWarning, stacklevel=2)
        if options is None:
            options = self.options
        for section, option_list in options:
            for option in option_list:
                yield (option['name'], option, self._option_value(option['name']))
