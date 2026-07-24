#!/usr/bin/env python3
"""HippoData class for storing structured medical data with section support.

Copyright (C) 2025 Costin Stroie <costinstroie@eridu.eu.org>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from datetime import datetime
from typing import Any
import logging

logger = logging.getLogger('HippoData')


class HippoData(dict):
    """A specialised dict for structured medical data with dot-notation storage.

    ``store("section.key", value)`` normalises and stores a value in a nested
    dict (``self["section"]["key"]``).  ``get("section.key")`` retrieves it.

    Dot-notation is one level deep: ``"a.b.c"`` means section=``"a"``,
    sub-key=``"b.c"`` (stored as a literal key inside the section dict).

    Normalisation applied by ``store()`` and ``__init__``:
    - Single-element lists are unwrapped to their sole item.
    - ``datetime`` objects are converted to ISO-8601 strings.
    - Strings are stripped of leading/trailing whitespace.
    - ``None`` values are silently ignored (not stored).
    """

    def __init__(self, **kwargs):
        super().__init__()
        for k, v in kwargs.items():
            self.store(k, v)

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def set_error(self, message: str) -> None:
        """Set status to 'error' with the given message."""
        self["status"] = "error"
        self["message"] = message

    def set_success(self) -> None:
        """Set status to 'success' and remove any stale message key."""
        self["status"] = "success"
        self.pop("message", None)

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(value: Any) -> Any:
        """Apply standard normalisation rules to a value before storage."""
        if isinstance(value, list):
            value = value[0] if len(value) == 1 else (None if len(value) == 0 else value)
        if isinstance(value, datetime):
            value = value.isoformat()
        if isinstance(value, str):
            value = value.strip()
        return value

    def store(self, key: str, value: Any = None) -> None:
        """Normalise *value* and store it under *key*.

        *key* may use dot-notation (``"section.subkey"``) to store the value
        inside a nested dict.  An empty section or sub-key is silently ignored.
        If the section already holds a scalar, it is promoted to a dict with
        the scalar stored under the empty-string key ``""`` before the new
        sub-key is added (this preserves the original value rather than
        discarding it).
        """
        value = self._normalise(value)
        if value is None:
            return

        if '.' in key:
            section, sub_key = key.split('.', 1)
            if not section or not sub_key:
                logger.debug(f"store: skipping key with empty section or sub-key: {key!r}")
                return
            if section not in self:
                self[section] = {}
            if not isinstance(self[section], dict):
                # Promote existing scalar to dict so we don't lose it
                self[section] = {"": self[section]}
            self[section][sub_key] = value
        else:
            if not key:
                return
            self[key] = value

    def store_list(self, key: str, value: Any = None) -> None:
        """Like ``store()``, but always keeps the value as a list.

        ``None`` is treated the same as in ``store()`` — not stored.
        """
        if value is None:
            return
        if not isinstance(value, list):
            value = [value]

        if '.' in key:
            section, sub_key = key.split('.', 1)
            if not section or not sub_key:
                return
            if section not in self:
                self[section] = {}
            if not isinstance(self[section], dict):
                self[section] = {"": self[section]}
            self[section][sub_key] = value
        else:
            if not key:
                return
            self[key] = value

    # ------------------------------------------------------------------
    # Retrieval / mutation with dot-notation
    # ------------------------------------------------------------------

    def get_section_key(self, key: str) -> tuple:
        """Split ``"section.subkey"`` → ``(section, subkey)``.

        Returns ``(key, None)`` for keys without a dot.
        """
        if '.' in key:
            section, sub_key = key.split('.', 1)
            return (section.strip(), sub_key.strip())
        return (key.strip(), None)

    def get(self, key: str, default: Any = None) -> Any:
        """Return ``self[section][subkey]`` for dot-notation *key*, else *default*.

        The default is ``None`` (matching ``dict.get`` behaviour).
        """
        section, sub_key = self.get_section_key(key)
        if sub_key is None:
            return super().get(section, default)
        section_data = super().get(section)
        if isinstance(section_data, dict):
            return section_data.get(sub_key, default)
        return default

    def set(self, key: str, value: Any) -> None:
        """Set ``self[section][subkey]`` for dot-notation *key*.

        Applies the same normalisation as ``store()`` so callers get
        consistent behaviour regardless of which method they use.
        """
        value = self._normalise(value)
        section, sub_key = self.get_section_key(key)
        if sub_key is None:
            self[section] = value
            return
        if section not in self:
            self[section] = {}
        self[section][sub_key] = value
