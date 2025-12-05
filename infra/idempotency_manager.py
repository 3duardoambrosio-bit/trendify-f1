import hashlib
import json
import time
from typing import Any, Dict, Optional


class IdempotencyManager:
    def __init__(self) -> None:
        self._storage: Dict[str, Dict[str, Any]] = {}

    def generate_key(self, operation: str, payload: Dict[str, Any]) -> str:
        """Generate idempotency key from operation and payload"""
        payload_str = json.dumps(payload, sort_keys=True)
        unique_str = f"{operation}:{payload_str}"
        return hashlib.md5(unique_str.encode(), usedforsecurity=False).hexdigest()

    def store_result(self, key: str, result: Any, ttl_seconds: int = 3600) -> None:
        """Store operation result with TTL"""
        self._storage[key] = {
            "result": result,
            "expires_at": time.time() + ttl_seconds,
            "created_at": time.time(),
        }

    def get_result(self, key: str) -> Optional[Any]:
        """Get stored result if exists and not expired"""
        if key not in self._storage:
            return None

        stored = self._storage[key]
        if time.time() > stored["expires_at"]:
            del self._storage[key]
            return None

        return stored["result"]

    def is_processed(self, key: str) -> bool:
        """Check if operation was already processed"""
        return self.get_result(key) is not None


# Global instance
idempotency_manager = IdempotencyManager()
