from __future__ import annotations
from typing import NoReturn
from pylint.exceptions import DeletedMessageError, InvalidMessageError, MessageBecameExtensionError, UnknownMessageError
from pylint.message._deleted_message_ids import is_deleted_msgid, is_deleted_symbol, is_moved_msgid, is_moved_symbol

class MessageIdStore:
    """The MessageIdStore store MessageId and make sure that there is a 1-1 relation
    between msgid and symbol.
    """

    def __init__(self) -> None:
        self.__msgid_to_symbol: dict[str, str] = {}
        self.__symbol_to_msgid: dict[str, str] = {}
        self.__old_names: dict[str, list[str]] = {}
        self.__active_msgids: dict[str, list[str]] = {}

    def __len__(self) -> int:
        return len(self.__msgid_to_symbol)

    def __repr__(self) -> str:
        result = 'MessageIdStore: [\n'
        for msgid, symbol in self.__msgid_to_symbol.items():
            result += f'  - {msgid} ({symbol})\n'
        result += ']'
        return result

    def add_msgid_and_symbol(self, msgid: str, symbol: str) -> None:
        """Add valid message id.

        There is a little duplication with add_legacy_msgid_and_symbol to avoid a function call,
        this is called a lot at initialization.
        """
        if symbol in self.__symbol_to_msgid:
            self._raise_duplicate_symbol(msgid, symbol, self.__symbol_to_msgid[symbol])
        if msgid in self.__msgid_to_symbol:
            self._raise_duplicate_msgid(symbol, msgid, self.__msgid_to_symbol[msgid])
        self.__msgid_to_symbol[msgid] = symbol
        self.__symbol_to_msgid[symbol] = msgid

    def add_legacy_msgid_and_symbol(self, msgid: str, symbol: str, new_msgid: str) -> None:
        """Add valid legacy message id.

        There is a little duplication with add_msgid_and_symbol to avoid a function call,
        this is called a lot at initialization.
        """
        if symbol not in self.__symbol_to_msgid:
            self.__symbol_to_msgid[symbol] = new_msgid
        if new_msgid not in self.__old_names:
            self.__old_names[new_msgid] = []
        self.__old_names[new_msgid].append((msgid, symbol))

    @staticmethod
    def _raise_duplicate_symbol(msgid: str, symbol: str, other_symbol: str) -> NoReturn:
        """Raise an error when a symbol is duplicated."""
        raise InvalidMessageError(
            f"Message symbol '{symbol}' is already defined for '{other_symbol}'. "
            f"Can't be assigned to '{msgid}'."
        )

    @staticmethod
    def _raise_duplicate_msgid(symbol: str, msgid: str, other_msgid: str) -> NoReturn:
        """Raise an error when a msgid is duplicated."""
        raise InvalidMessageError(
            f"Message id '{msgid}' is already defined for '{other_msgid}'. "
            f"Can't be assigned to '{symbol}'."
        )

    def get_active_msgids(self, msgid_or_symbol: str) -> list[str]:
        """Return msgids but the input can be a symbol.

        self.__active_msgids is used to implement a primitive cache for this function.
        """
        if msgid_or_symbol in self.__active_msgids:
            return self.__active_msgids[msgid_or_symbol]

        result = []
        if msgid_or_symbol in self.__msgid_to_symbol:
            result.append(msgid_or_symbol)
        elif msgid_or_symbol in self.__symbol_to_msgid:
            result.append(self.__symbol_to_msgid[msgid_or_symbol])
        else:
            for new_msgid, old_names in self.__old_names.items():
                for old_msgid, old_symbol in old_names:
                    if msgid_or_symbol in (old_msgid, old_symbol):
                        result.append(new_msgid)
                        break
                if result:
                    break

        if not result:
            explanation = is_deleted_msgid(msgid_or_symbol) or is_deleted_symbol(msgid_or_symbol)
            if explanation:
                raise DeletedMessageError(f"{msgid_or_symbol} was removed. {explanation}")
            explanation = is_moved_msgid(msgid_or_symbol) or is_moved_symbol(msgid_or_symbol)
            if explanation:
                raise MessageBecameExtensionError(f"{msgid_or_symbol} was moved to an extension. {explanation}")
            raise UnknownMessageError(f"No such message id or symbol '{msgid_or_symbol}'.")

        self.__active_msgids[msgid_or_symbol] = result
        return result
