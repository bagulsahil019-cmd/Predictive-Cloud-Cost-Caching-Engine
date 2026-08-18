import time
import asyncio

class CacheLayer:
    def __init__(self):
        # In-memory dictionary to store cached items:
        # key -> {"data": val, "size_kb": size, "timestamp": ts, "ttl": ttl}
        self.store = {}
        
    def get(self, key: str) -> dict | None:
        """
        Attempts to retrieve a key from the cache.
        Returns the data dictionary if found and not expired, else None.
        Simulates <5ms latency (around 1-2ms).
        """
        if key not in self.store:
            return None
            
        item = self.store[key]
        now = time.time()
        
        # Check expiration
        if now - item["timestamp"] > item["ttl"]:
            del self.store[key]
            return None
            
        return item["data"]

    def set(self, key: str, value: str, size_kb: float, ttl: float = 300.0) -> None:
        """
        Stores an item in the cache with a size (KB) and TTL (seconds).
        """
        self.store[key] = {
            "data": value,
            "size_kb": size_kb,
            "timestamp": time.time(),
            "ttl": ttl
        }

    def delete(self, key: str) -> None:
        """Removes a key from the cache."""
        if key in self.store:
            del self.store[key]

    def clear(self) -> None:
        """Clears all cached items."""
        self.store.clear()

    def calculate_cache_cost(self, size_kb: float, p_storage_per_kb: float, p_write_op: float, w_writes: int = 1) -> float:
        """
        Calculates cache overhead cost:
        Cost_cache = [S * P_storage] + [W * P_write]
        """
        storage_cost = size_kb * p_storage_per_kb
        write_cost = w_writes * p_write_op
        return storage_cost + write_cost
