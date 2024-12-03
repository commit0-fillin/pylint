from __future__ import annotations
import re
from re import Pattern
from pylint import constants
from pylint.typing import OptionDict, Options

class NamingStyle:
    """Class to register all accepted forms of a single naming style.

    It may seem counter-intuitive that single naming style has multiple "accepted"
    forms of regular expressions, but we need to special-case stuff like dunder
    names in method names.
    """
    ANY: Pattern[str] = re.compile('.*')
    CLASS_NAME_RGX: Pattern[str] = ANY
    MOD_NAME_RGX: Pattern[str] = ANY
    CONST_NAME_RGX: Pattern[str] = ANY
    COMP_VAR_RGX: Pattern[str] = ANY
    DEFAULT_NAME_RGX: Pattern[str] = ANY
    CLASS_ATTRIBUTE_RGX: Pattern[str] = ANY

    @classmethod
    def get_regex(cls, name_type: str) -> Pattern[str]:
        """Get the regex pattern for a specific name type."""
        return getattr(cls, f"{name_type.upper()}_NAME_RGX", cls.DEFAULT_NAME_RGX)

    @classmethod
    def validate_name(cls, name: str, name_type: str) -> bool:
        """Validate if a name matches the style for a specific name type."""
        return bool(cls.get_regex(name_type).match(name))

class SnakeCaseStyle(NamingStyle):
    """Regex rules for snake_case naming style."""
    CLASS_NAME_RGX = re.compile('[^\\W\\dA-Z][^\\WA-Z]*$')
    MOD_NAME_RGX = re.compile('[^\\W\\dA-Z][^\\WA-Z]*$')
    CONST_NAME_RGX = re.compile('([^\\W\\dA-Z][^\\WA-Z]*|__.*__)$')
    COMP_VAR_RGX = CLASS_NAME_RGX
    DEFAULT_NAME_RGX = re.compile('([^\\W\\dA-Z][^\\WA-Z]*|_[^\\WA-Z]*|__[^\\WA-Z\\d_][^\\WA-Z]+__)$')
    CLASS_ATTRIBUTE_RGX = re.compile('([^\\W\\dA-Z][^\\WA-Z]*|__.*__)$')

class CamelCaseStyle(NamingStyle):
    """Regex rules for camelCase naming style."""
    CLASS_NAME_RGX = re.compile('[^\\W\\dA-Z][^\\W_]*$')
    MOD_NAME_RGX = re.compile('[^\\W\\dA-Z][^\\W_]*$')
    CONST_NAME_RGX = re.compile('([^\\W\\dA-Z][^\\W_]*|__.*__)$')
    COMP_VAR_RGX = MOD_NAME_RGX
    DEFAULT_NAME_RGX = re.compile('([^\\W\\dA-Z][^\\W_]*|__[^\\W\\dA-Z_]\\w+__)$')
    CLASS_ATTRIBUTE_RGX = re.compile('([^\\W\\dA-Z][^\\W_]*|__.*__)$')

class PascalCaseStyle(NamingStyle):
    """Regex rules for PascalCase naming style."""
    CLASS_NAME_RGX = re.compile('[^\\W\\da-z][^\\W_]*$')
    MOD_NAME_RGX = CLASS_NAME_RGX
    CONST_NAME_RGX = re.compile('([^\\W\\da-z][^\\W_]*|__.*__)$')
    COMP_VAR_RGX = CLASS_NAME_RGX
    DEFAULT_NAME_RGX = re.compile('([^\\W\\da-z][^\\W_]*|__[^\\W\\dA-Z_]\\w+__)$')
    CLASS_ATTRIBUTE_RGX = re.compile('[^\\W\\da-z][^\\W_]*$')

class UpperCaseStyle(NamingStyle):
    """Regex rules for UPPER_CASE naming style."""
    CLASS_NAME_RGX = re.compile('[^\\W\\da-z][^\\Wa-z]*$')
    MOD_NAME_RGX = CLASS_NAME_RGX
    CONST_NAME_RGX = re.compile('([^\\W\\da-z][^\\Wa-z]*|__.*__)$')
    COMP_VAR_RGX = CLASS_NAME_RGX
    DEFAULT_NAME_RGX = re.compile('([^\\W\\da-z][^\\Wa-z]*|__[^\\W\\dA-Z_]\\w+__)$')
    CLASS_ATTRIBUTE_RGX = re.compile('[^\\W\\da-z][^\\Wa-z]*$')

class AnyStyle(NamingStyle):
    """Style that accepts any name."""
    pass
NAMING_STYLES = {'snake_case': SnakeCaseStyle, 'camelCase': CamelCaseStyle, 'PascalCase': PascalCaseStyle, 'UPPER_CASE': UpperCaseStyle, 'any': AnyStyle}
KNOWN_NAME_TYPES_WITH_STYLE = {'module', 'const', 'class', 'function', 'method', 'attr', 'argument', 'variable', 'class_attribute', 'class_const', 'inlinevar'}
DEFAULT_NAMING_STYLES = {'module': 'snake_case', 'const': 'UPPER_CASE', 'class': 'PascalCase', 'function': 'snake_case', 'method': 'snake_case', 'attr': 'snake_case', 'argument': 'snake_case', 'variable': 'snake_case', 'class_attribute': 'any', 'class_const': 'UPPER_CASE', 'inlinevar': 'any'}
KNOWN_NAME_TYPES = {*KNOWN_NAME_TYPES_WITH_STYLE, 'typevar', 'typealias'}
