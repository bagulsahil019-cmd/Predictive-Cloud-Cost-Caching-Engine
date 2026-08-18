import asyncio
import random
import time

class OriginDatabase:
    def __init__(self):
        # Default mock size in KB for typical keys
        self.key_sizes_kb = {
            "user_profile": 10.0,
            "image_metadata": 5.0,
            "search_products": 150.0,
            "recommendations_feed": 800.0,
            "analytics_report": 5000.0
        }
        self.default_size_kb = 50.0

    def get_key_size(self, key: str) -> float:
        """Returns the size of the key's result in KB."""
        return self.key_sizes_kb.get(key, self.default_size_kb)

    async def fetch(self, key: str) -> dict:
        """
        Simulates fetching data from the database with 150ms-300ms latency.
        Returns a dict containing the result and the latency.
        """
        start_time = time.time()
        # Latency simulation
        latency = random.uniform(0.150, 0.300)
        await asyncio.sleep(latency)
        
        # Simulated payload data
        size = self.get_key_size(key)
        payload = f"mock_data_for_{key}_of_size_{size}KB"
        
        elapsed = time.time() - start_time
        return {
            "key": key,
            "data": payload,
            "size_kb": size,
            "db_latency_seconds": elapsed
        }

    def calculate_fetch_cost(self, n_predicted: float, p_compute: float, p_egress_per_kb: float, key: str) -> float:
        """
        Calculates the cost of fetching from the database directly over the predicted horizon.
        Cost_fetch = N_predicted * (P_compute + P_egress)
        P_egress is computed dynamically based on the payload size (size_kb * p_egress_per_kb).
        """
        size_kb = self.get_key_size(key)
        p_egress = size_kb * p_egress_per_kb
        cost_per_fetch = p_compute + p_egress
        return n_predicted * cost_per_fetch
