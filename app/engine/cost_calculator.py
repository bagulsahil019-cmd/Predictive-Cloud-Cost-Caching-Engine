class CostCalculator:
    def __init__(self, p_read_op: float = 0.000001):
        # Default read operation cost is extremely small (e.g. $0.000001 per query)
        self.p_read_op = p_read_op

    def evaluate_routing_decision(
        self,
        key: str,
        n_predicted: float,
        size_kb: float,
        p_compute: float,
        p_egress_per_kb: float,
        p_storage_per_kb: float,
        p_write_op: float,
        is_in_cache: bool,
        predictive_active: bool = True
    ) -> dict:
        """
        Compares Cost_cache vs Cost_fetch to decide the routing action.
        
        If predictive_active is False, we use standard caching:
          - If in cache -> CACHE_HIT
          - If not in cache -> CACHE_ROUTED (always cache on miss)
        
        If predictive_active is True:
          - Compare total fetch cost vs total cache route cost.
          - Return one of:
            - "CACHE_HIT": Served from cache because it was already cached and cost-effective.
            - "CACHE_ROUTED": Cache miss, but caching is predicted to be cost-effective, so we fetch and write to cache.
            - "DIRECT_FETCH": Served from DB directly because it is NOT cost-effective to cache (either on miss or evicting on hit).
        """
        # DB Fetch Cost per request: compute + egress (based on payload size)
        p_fetch_single = p_compute + (size_kb * p_egress_per_kb)
        cost_fetch_total = n_predicted * p_fetch_single

        # Standard caching behavior (no predictive cost optimizations)
        if not predictive_active:
            if is_in_cache:
                cost_incurred = 0.0  # Already in cache
                return {
                    "decision": "CACHE_HIT",
                    "reason": "Standard Caching: Key found in cache.",
                    "cost_fetch_predicted": cost_fetch_total,
                    "cost_cache_predicted": 0.0,
                    "saving_predicted": cost_fetch_total,
                    "cost_incurred": cost_incurred
                }
            else:
                # Must fetch once from DB and write to cache
                cost_incurred = p_fetch_single + p_write_op + (size_kb * p_storage_per_kb)
                return {
                    "decision": "CACHE_ROUTED",
                    "reason": "Standard Caching: Cache miss, writing to cache.",
                    "cost_fetch_predicted": cost_fetch_total,
                    "cost_cache_predicted": p_fetch_single + (size_kb * p_storage_per_kb) + p_write_op,
                    "saving_predicted": cost_fetch_total - (p_fetch_single + (size_kb * p_storage_per_kb) + p_write_op),
                    "cost_incurred": cost_incurred
                }

        # Predictive active logic
        # Cost to serve via Cache route
        cache_storage_cost = size_kb * p_storage_per_kb
        cache_write_cost = p_write_op
        cache_read_total = n_predicted * self.p_read_op

        if is_in_cache:
            # If already in cache, cost of keeping it in cache and serving from it:
            # We don't pay the database fetch or the write cost (they were already spent).
            # We only pay storage cost and read cost.
            cost_cache_total = cache_storage_cost + cache_read_total
            
            if cost_cache_total < cost_fetch_total:
                return {
                    "decision": "CACHE_HIT",
                    "reason": f"Predictive Engine: Already cached. Cost to keep in cache (${cost_cache_total:.6f}) < DB fetch cost (${cost_fetch_total:.6f}) for {n_predicted:.1f} predicted requests.",
                    "cost_fetch_predicted": cost_fetch_total,
                    "cost_cache_predicted": cost_cache_total,
                    "saving_predicted": cost_fetch_total - cost_cache_total,
                    "cost_incurred": cache_read_total
                }
            else:
                # Even though it's cached, the storage cost is too high compared to fetch cost
                # So we bypass cache, fetch directly, and we should evict it to stop paying storage!
                return {
                    "decision": "DIRECT_FETCH",
                    "reason": f"Predictive Engine (Evict): Storage cost (${cache_storage_cost:.6f}) is too high relative to low request rate ({n_predicted:.1f} predicted requests). Bypassing cache.",
                    "cost_fetch_predicted": cost_fetch_total,
                    "cost_cache_predicted": cost_cache_total,
                    "saving_predicted": cost_fetch_total - cost_cache_total,
                    "cost_incurred": p_fetch_single
                }
        else:
            # If not in cache, cost to fetch once, write, store, and serve subsequent from cache
            cost_cache_total = p_fetch_single + cache_write_cost + cache_storage_cost + (n_predicted - 1) * self.p_read_op
            
            if cost_cache_total < cost_fetch_total:
                return {
                    "decision": "CACHE_ROUTED",
                    "reason": f"Predictive Engine: Cache miss. Caching is viable. Total cache route cost (${cost_cache_total:.6f}) < Direct DB fetches (${cost_fetch_total:.6f}) for {n_predicted:.1f} predicted requests.",
                    "cost_fetch_predicted": cost_fetch_total,
                    "cost_cache_predicted": cost_cache_total,
                    "saving_predicted": cost_fetch_total - cost_cache_total,
                    "cost_incurred": p_fetch_single + cache_write_cost + cache_storage_cost
                }
            else:
                return {
                    "decision": "DIRECT_FETCH",
                    "reason": f"Predictive Engine: Cache miss. Caching is not viable. Direct DB fetches (${cost_fetch_total:.6f}) <= Total cache route cost (${cost_cache_total:.6f}) for {n_predicted:.1f} predicted requests.",
                    "cost_fetch_predicted": cost_fetch_total,
                    "cost_cache_predicted": cost_cache_total,
                    "saving_predicted": cost_fetch_total - cost_cache_total,
                    "cost_incurred": p_fetch_single
                }
