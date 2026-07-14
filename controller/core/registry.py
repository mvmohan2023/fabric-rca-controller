"""Generic thread-safe registry used by FVP extension points."""

from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from typing import Dict, Generic, Iterable, List, Optional, TypeVar

from controller.core.exceptions import (
    DuplicateRegistrationError,
    RegistrationNotFoundError,
)


T = TypeVar("T")


class Registry(Generic[T]):
    """A small, thread-safe named-object registry."""

    def __init__(self, name: str):
        self.name = str(name or "").strip()
        if not self.name:
            raise ValueError("Registry name must be non-empty")

        self._items: "OrderedDict[str, T]" = OrderedDict()
        self._lock = RLock()

    @staticmethod
    def _normalize_key(key: str) -> str:
        normalized = str(key or "").strip()
        if not normalized:
            raise ValueError("Registry key must be non-empty")
        return normalized

    def register(
        self,
        key: str,
        value: T,
        *,
        replace: bool = False,
    ) -> T:
        normalized = self._normalize_key(key)

        with self._lock:
            if normalized in self._items and not replace:
                raise DuplicateRegistrationError(
                    f"'{normalized}' is already registered in "
                    f"the {self.name} registry"
                )

            self._items[normalized] = value

        return value

    def unregister(self, key: str) -> T:
        normalized = self._normalize_key(key)

        with self._lock:
            if normalized not in self._items:
                raise RegistrationNotFoundError(
                    f"'{normalized}' is not registered in "
                    f"the {self.name} registry"
                )

            return self._items.pop(normalized)

    def get(self, key: str, default: Optional[T] = None) -> Optional[T]:
        normalized = self._normalize_key(key)

        with self._lock:
            return self._items.get(normalized, default)

    def require(self, key: str) -> T:
        normalized = self._normalize_key(key)

        with self._lock:
            if normalized not in self._items:
                raise RegistrationNotFoundError(
                    f"'{normalized}' is not registered in "
                    f"the {self.name} registry"
                )

            return self._items[normalized]

    def exists(self, key: str) -> bool:
        normalized = self._normalize_key(key)

        with self._lock:
            return normalized in self._items

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._items.keys())

    def values(self) -> List[T]:
        with self._lock:
            return list(self._items.values())

    def items(self) -> List[tuple[str, T]]:
        with self._lock:
            return list(self._items.items())

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return self.exists(key)

    def __iter__(self) -> Iterable[str]:
        return iter(self.keys())

    def __repr__(self) -> str:
        return (
            f"Registry(name={self.name!r}, "
            f"size={len(self)}, keys={self.keys()!r})"
        )


scenario_registry: Registry[object] = Registry("scenario")
stress_action_registry: Registry[object] = Registry("stress_action")
validation_registry: Registry[object] = Registry("validation")
rca_registry: Registry[object] = Registry("rca")
report_registry: Registry[object] = Registry("report")
