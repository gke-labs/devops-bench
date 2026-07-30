# Copyright 2026 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A generic registry with optional entry-point discovery."""

from __future__ import annotations

import threading
from collections.abc import Callable, ItemsView, Iterator, KeysView, ValuesView
from importlib import metadata

from devops_bench.core.errors import AlreadyRegisteredError, InvalidKeyError, NotRegisteredError
from devops_bench.core.logging import get_logger

__all__ = ["Registry"]

_log = get_logger("core.registry")


class Registry[T]:
    """Name-to-object registry backing a single extension axis.

    Args:
        name: Registry name, used in error messages.
        entry_point_group: Entry-point group scanned lazily for plugins; when
            None, only explicit registrations are available.
        key_validator: Optional key policy for this axis. Called with a
            candidate key; returns None to accept it, or a human-readable
            reason to reject it. A rejected explicit :meth:`register` raises
            :class:`~devops_bench.core.errors.InvalidKeyError` — an in-tree
            programming error should fail loudly. A rejected *discovered*
            entry point is skipped with a warning instead, so one mispackaged
            third-party plugin never aborts a run. When None, any key is
            accepted.

    Example:
        >>> AGENTS: Registry[type] = Registry("agents")
        >>> @AGENTS.register("gemini")
        ... class GeminiCli: ...
        >>> AGENTS.get("gemini") is GeminiCli
        True
    """

    def __init__(
        self,
        name: str,
        *,
        entry_point_group: str | None = None,
        key_validator: Callable[[str], str | None] | None = None,
    ) -> None:
        self._name = name
        self._entry_point_group = entry_point_group
        self._key_validator = key_validator
        self._items: dict[str, T] = {}
        self._entry_points_loaded = False
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    def register(self, key: str) -> Callable[[T], T]:
        """Register an object under ``key``.

        Args:
            key: Name to register under.

        Returns:
            A decorator that registers and returns the object it decorates.

        Raises:
            InvalidKeyError: If ``key`` is rejected by this registry's key
                policy.
            AlreadyRegisteredError: If ``key`` is already registered.
        """

        def decorator(obj: T) -> T:
            reason = self._rejection_reason(key)
            if reason is not None:
                raise InvalidKeyError(self._name, key, reason)
            if key in self._items:
                raise AlreadyRegisteredError(self._name, key)
            self._items[key] = obj
            _log.debug("registered %r in %r registry", key, self._name)
            return obj

        return decorator

    def get(self, key: str) -> T:
        """Look up a registered object by name.

        A miss triggers a one-time entry-point scan when a group was configured.

        Args:
            key: Name to look up.

        Returns:
            The registered object.

        Raises:
            NotRegisteredError: If ``key`` is unknown.
        """
        if key not in self._items:
            self._ensure_entry_points_loaded()
        try:
            return self._items[key]
        except KeyError:
            raise NotRegisteredError(self._name, key, self.keys()) from None

    def __getitem__(self, key: str) -> T:
        return self.get(key)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str) and key in self._items:
            return True
        self._ensure_entry_points_loaded()
        return key in self._items

    def __iter__(self) -> Iterator[str]:
        self._ensure_entry_points_loaded()
        return iter(self._items)

    def __len__(self) -> int:
        self._ensure_entry_points_loaded()
        return len(self._items)

    def keys(self) -> KeysView[str]:
        self._ensure_entry_points_loaded()
        return self._items.keys()

    def items(self) -> ItemsView[str, T]:
        self._ensure_entry_points_loaded()
        return self._items.items()

    def values(self) -> ValuesView[T]:
        self._ensure_entry_points_loaded()
        return self._items.values()

    def _rejection_reason(self, key: str) -> str | None:
        """Return why ``key`` violates this registry's key policy, else None."""
        if self._key_validator is None:
            return None
        return self._key_validator(key)

    def _ensure_entry_points_loaded(self) -> None:
        if self._entry_points_loaded or self._entry_point_group is None:
            return
        with self._lock:
            if self._entry_points_loaded:
                return
            for entry_point in metadata.entry_points(group=self._entry_point_group):
                if entry_point.name in self._items:
                    continue
                # A key the policy rejects could never be looked up anyway, so
                # skip it loudly here rather than admitting a dead entry that
                # only shows up as noise in a later "available:" listing.
                reason = self._rejection_reason(entry_point.name)
                if reason is not None:
                    _log.warning(
                        "skipping entry point %r for %r registry: %s",
                        entry_point.name,
                        self._name,
                        reason,
                    )
                    continue
                try:
                    loaded = entry_point.load()
                except Exception:
                    _log.exception(
                        "failed to load entry point %r for %r registry",
                        entry_point.name,
                        self._name,
                    )
                    continue
                self._items[entry_point.name] = loaded
                _log.debug(
                    "loaded entry point %r into %r registry",
                    entry_point.name,
                    self._name,
                )
            # Mark loaded only after a full successful scan (held under the lock,
            # so concurrent readers never observe a half-populated registry). If
            # enumeration itself raises, the flag stays unset and the next lookup
            # retries discovery.
            self._entry_points_loaded = True

    def __repr__(self) -> str:
        return (
            f"Registry(name={self._name!r}, "
            f"entry_point_group={self._entry_point_group!r}, "
            f"size={len(self._items)})"
        )
