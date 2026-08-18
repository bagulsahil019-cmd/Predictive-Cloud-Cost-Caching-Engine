import time
import os
import random
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.origin_db import OriginDatabase
from app.cache_layer import CacheLayer
from app.engine.predictor import TrafficPredictor
from app.engine.cost_calculator import CostCalculator

app = FastAPI(title="Predictive Cloud-Cost Caching Engine")

# Instantiate Core Layers
db = OriginDatabase()
cache = CacheLayer()
predictor = TrafficPredictor(window_seconds=60.0, bin_seconds=10.0)
calculator = CostCalculator()

# Simulation settings (mutable in-memory)
class Settings(BaseModel):
    p_compute: float = 0.005          # Cost of database compute per query ($)
    p_egress_per_kb: float = 0.0001    # Cost of network egress per KB ($)
    p_storage_per_kb: float = 0.0005   # Cost of caching 1 KB for 60 seconds ($)
    p_write_op: float = 0.001          # Cost of writing to cache per operation ($)
    predictive_active: bool = True     # Toggle predictive routing vs standard caching

settings = Settings()

# Cumulative metrics (running totals)
class MetricsTracker:
    def __init__(self):
        self.reset()
        
    def reset(self):
        self.total_requests = 0
        self.latency_saved_seconds = 0.0
        self.total_latency_seconds = 0.0
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Cumulative cost trackers for comparison
        self.cost_direct_fetch_only = 0.0
        self.cost_standard_caching = 0.0
        self.cost_predictive_caching = 0.0
        
        # In-memory history for metrics chart (time-series)
        # Each entry: {timestamp: float, direct: float, standard: float, predictive: float}
        self.chart_history = []
        # Telemetry logs
        self.logs = []

metrics = MetricsTracker()

# Mount frontend static directory if exists, otherwise we'll serve files manually
# We'll create the folder app/frontend
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
async def get_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

@app.get("/styles.css")
async def get_css():
    return FileResponse(os.path.join(frontend_dir, "styles.css"))

@app.get("/app.js")
async def get_js():
    return FileResponse(os.path.join(frontend_dir, "app.js"))

@app.get("/query")
async def handle_query(key: str = Query(..., description="Query key to look up")):
    """
    Main middleware interception endpoint.
    Routes the query dynamically, simulates costs/latencies, and records telemetry.
    """
    metrics.total_requests += 1
    
    # 1. Update Traffic Telemetry
    predictor.record_request(key)
    
    # 2. Get Key details (size)
    size_kb = db.get_key_size(key)
    
    # 3. Check cache state
    is_in_cache = cache.get(key) is not None
    
    # 4. Get Predicted Frequency
    n_predicted = predictor.predict_frequency(key)
    
    # 5. Evaluate Economic Decisions for ALL 3 modes to track cumulative comparison
    
    # A. Direct Fetch mode (always bypass cache)
    db_fetch_single_cost = settings.p_compute + (size_kb * settings.p_egress_per_kb)
    metrics.cost_direct_fetch_only += db_fetch_single_cost
    
    # B. Standard Caching mode (always cache on miss, hit on cache)
    # We maintain a separate logical cache state for the Standard Caching tracker
    # For simplification, we check the actual cache state but compute the cost of standard cache behaviour:
    # If key is already in cache, cost = p_read_op. If miss, cost = db_fetch_single_cost + write + storage
    standard_decision = calculator.evaluate_routing_decision(
        key=key,
        n_predicted=n_predicted,
        size_kb=size_kb,
        p_compute=settings.p_compute,
        p_egress_per_kb=settings.p_egress_per_kb,
        p_storage_per_kb=settings.p_storage_per_kb,
        p_write_op=settings.p_write_op,
        is_in_cache=is_in_cache,
        predictive_active=False
    )
    metrics.cost_standard_caching += standard_decision["cost_incurred"]
    
    # C. Predictive Caching mode (decides economics dynamically)
    predictive_decision = calculator.evaluate_routing_decision(
        key=key,
        n_predicted=n_predicted,
        size_kb=size_kb,
        p_compute=settings.p_compute,
        p_egress_per_kb=settings.p_egress_per_kb,
        p_storage_per_kb=settings.p_storage_per_kb,
        p_write_op=settings.p_write_op,
        is_in_cache=is_in_cache,
        predictive_active=True
    )
    
    # Track metrics according to the currently active setting (Predictive or Standard Caching)
    active_decision = predictive_decision if settings.predictive_active else standard_decision
    
    # Update running predictive cost
    metrics.cost_predictive_caching += predictive_decision["cost_incurred"]
    
    # 6. Execute Routing Action for the actual active route
    start_latency = time.time()
    
    routing_action = active_decision["decision"]
    latency_seconds = 0.0
    served_from = ""
    
    if routing_action == "CACHE_HIT":
        # Served in <1ms from memory
        latency_seconds = random.uniform(0.0005, 0.002)
        await asyncio.sleep(latency_seconds)
        data = cache.get(key)
        served_from = "Cache"
        metrics.cache_hits += 1
    elif routing_action == "CACHE_ROUTED":
        # Cache miss, fetch from DB
        db_res = await db.fetch(key)
        # Write to cache
        cache.set(key, db_res["data"], size_kb, ttl=300.0)
        latency_seconds = db_res["db_latency_seconds"]
        served_from = "Database (Cached)"
        metrics.cache_misses += 1
    else:  # DIRECT_FETCH
        # Fetch from DB directly (and evict if currently in cache)
        if is_in_cache:
            cache.delete(key)
        db_res = await db.fetch(key)
        latency_seconds = db_res["db_latency_seconds"]
        served_from = "Database (Direct)"
        metrics.cache_misses += 1
        
    actual_latency = time.time() - start_latency
    metrics.total_latency_seconds += actual_latency
    
    # Latency saved compares actual latency against standard DB fetch latency (~225ms average)
    db_avg_latency = 0.225
    latency_saved = max(0.0, db_avg_latency - actual_latency)
    metrics.latency_saved_seconds += latency_saved
    
    # 7. Append to Telemetry Log
    log_entry = {
        "timestamp": time.time(),
        "key": key,
        "size_kb": size_kb,
        "n_predicted": round(n_predicted, 2),
        "is_in_cache": is_in_cache,
        "routing_action": routing_action,
        "served_from": served_from,
        "latency_ms": round(actual_latency * 1000, 1),
        "reason": active_decision["reason"],
        "cost_incurred": active_decision["cost_incurred"]
    }
    
    metrics.logs.append(log_entry)
    if len(metrics.logs) > 50:
        metrics.logs.pop(0)
        
    # Append to chart history (every few requests or throttled in frontend)
    # We record current state
    metrics.chart_history.append({
        "timestamp": time.time(),
        "direct": round(metrics.cost_direct_fetch_only, 4),
        "standard": round(metrics.cost_standard_caching, 4),
        "predictive": round(metrics.cost_predictive_caching, 4)
    })
    if len(metrics.chart_history) > 100:
        metrics.chart_history.pop(0)
        
    return {
        "key": key,
        "served_from": served_from,
        "latency_ms": round(actual_latency * 1000, 1),
        "decision": routing_action,
        "reason": active_decision["reason"]
    }

@app.get("/metrics")
async def get_metrics():
    """Returns aggregated stats, comparison costs, and historical telemetry."""
    avg_latency = (metrics.total_latency_seconds / metrics.total_requests * 1000) if metrics.total_requests > 0 else 0.0
    hit_ratio = (metrics.cache_hits / metrics.total_requests) if metrics.total_requests > 0 else 0.0
    
    return {
        "total_requests": metrics.total_requests,
        "cache_hit_ratio": round(hit_ratio, 3),
        "avg_latency_ms": round(avg_latency, 1),
        "latency_saved_seconds": round(metrics.latency_saved_seconds, 2),
        "cost_direct": round(metrics.cost_direct_fetch_only, 4),
        "cost_standard": round(metrics.cost_standard_caching, 4),
        "cost_predictive": round(metrics.cost_predictive_caching, 4),
        "savings_vs_direct_pct": round(
            ((metrics.cost_direct_fetch_only - metrics.cost_predictive_caching) / max(0.0001, metrics.cost_direct_fetch_only)) * 100, 1
        ),
        "savings_vs_standard_pct": round(
            ((metrics.cost_standard_caching - metrics.cost_predictive_caching) / max(0.0001, metrics.cost_standard_caching)) * 100, 1
        ),
        "chart_history": metrics.chart_history,
        "logs": list(reversed(metrics.logs))
    }

@app.post("/settings")
async def update_settings(new_settings: Settings):
    """Updates simulation pricing and toggles."""
    global settings
    settings = new_settings
    return {"status": "success", "settings": settings}

@app.get("/settings")
async def get_settings():
    """Retrieves current simulation configurations."""
    return settings

@app.post("/reset")
async def reset_metrics():
    """Resets all simulation telemetry and caches."""
    metrics.reset()
    cache.clear()
    predictor.request_history.clear()
    predictor.ema_rates.clear()
    predictor.last_request_time.clear()
    predictor.X_train.clear()
    predictor.y_train.clear()
    predictor.is_trained = False
    return {"status": "success", "message": "Simulation metrics and cache cleared."}
