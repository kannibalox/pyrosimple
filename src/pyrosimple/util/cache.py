"""Helper classes to deal with caching various data"""
import time

from collections import abc
from threading import RLock
from typing import Any, Dict, Hashable, Optional, Set, Tuple, Union


class ExpiringCache(abc.MutableMapping):
    """Caches items for a fixed time, with an optional exlusionary
    list of static keys."""

    def __init__(
        self,
        items: Optional[Dict] = None,
        expires: float = 5.0,
        static_keys: Optional[Set] = None,
    ):
        self.expires: float = expires
        # When 3.7 support is dropped, the type can be made more specific:
        # Dict[str, tuple[float, Any]]
        self.data: Dict[Hashable, tuple] = {}
        self.lock = RLock()
        self.static_keys = static_keys or set()
        if items:
            for key, val in items:
                if key in self.static_keys:
                    expire_at = 0.0
                else:
                    expire_at = self.expires + time.time()
                self.data[key] = (expire_at, val)

    def __delitem__(self, key: Hashable):
        with self.lock:
            del self.data[key]

    def __setitem__(self, key: Hashable, val: Any, expire: Optional[float] = None):
        with self.lock:
            if key in self.static_keys or expire == 0:
                expire_at = 0.0
            else:
                expire_at = (expire or self.expires) + time.time()
            self.data[key] = (expire_at, val)

    def __getitem__(
        self, key: Hashable, with_age: bool = False
    ) -> Union[Tuple[Any, float], Any]:
        with self.lock:
            expires_at, item = self.data[key]
            if expires_at == 0 or expires_at > time.time():
                if with_age:
                    return item, expires_at - time.time()
                return item
            del self[key]
            raise KeyError(key)

    def __contains__(self, key: Hashable) -> bool:
        """Return True if the dict has a key, else return False."""
        try:
            with self.lock:
                expires_at, item = self.data.get(key, (0, None))
                if item is not None and expires_at == 0 or expires_at < time.time():
                    return True
                del self[key]
        except KeyError:
            pass
        return False

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return self.data.__iter__()
