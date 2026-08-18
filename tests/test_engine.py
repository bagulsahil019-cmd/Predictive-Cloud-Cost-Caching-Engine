import pytest
import time
from fastapi.testclient import TestClient

from app.origin_db import OriginDatabase
from app.cache_layer import CacheLayer
from app.engine.predictor import TrafficPredictor
from app.engine.cost_calculator import CostCalculator
from app.main import app

def test_origin_db_size():
    db = OriginDatabase()
    assert db.get_key_size("user_profile") == 10.0
    assert db.get_key_size("analytics_report") == 5000.0
    assert db.get_key_size("unknown_key") == 50.0

def test_cache_layer_get_set():
    cache = CacheLayer()
    assert cache.get("test_key") is None
    
    cache.set("test_key", "value_data", size_kb=10.0, ttl=5)
    assert cache.get("test_key") == "value_data"
    
    cache.delete("test_key")
    assert cache.get("test_key") is None

def test_cache_layer_ttl():
    cache = CacheLayer()
    cache.set("short_ttl_key", "data", size_kb=1.0, ttl=0.1)
    assert cache.get("short_ttl_key") == "data"
    time.sleep(0.2)
    assert cache.get("short_ttl_key") is None

def test_predictor_ema_fallback():
    predictor = TrafficPredictor(window_seconds=60.0)
    # Simulate a few requests spaced out to check EMA calculation
    key = "user_profile"
    predictor.record_request(key)
    
    # Immediately after 1 request, rate is low but should fallback gracefully
    pred = predictor.predict_frequency(key)
    assert pred >= 1.0

def test_cost_calculator_decisions():
    calculator = CostCalculator()
    
    # SCENARIO 1: Small payload, high frequency -> Should Cache (CACHE_ROUTED on miss, CACHE_HIT on hit)
    decision_miss = calculator.evaluate_routing_decision(
        key="user_profile",
        n_predicted=50.0,
        size_kb=10.0,
        p_compute=0.005,
        p_egress_per_kb=0.0001,
        p_storage_per_kb=0.0005,
        p_write_op=0.001,
        is_in_cache=False,
        predictive_active=True
    )
    assert decision_miss["decision"] == "CACHE_ROUTED"
    
    decision_hit = calculator.evaluate_routing_decision(
        key="user_profile",
        n_predicted=50.0,
        size_kb=10.0,
        p_compute=0.005,
        p_egress_per_kb=0.0001,
        p_storage_per_kb=0.0005,
        p_write_op=0.001,
        is_in_cache=True,
        predictive_active=True
    )
    assert decision_hit["decision"] == "CACHE_HIT"

    # SCENARIO 2: Large payload, low frequency -> Should NOT Cache (DIRECT_FETCH on miss, evicts on hit)
    decision_large_miss = calculator.evaluate_routing_decision(
        key="analytics_report",
        n_predicted=1.0,
        size_kb=5000.0,
        p_compute=0.005,
        p_egress_per_kb=0.0001,
        p_storage_per_kb=0.005,  # Very high storage cost ($25.0)
        p_write_op=0.001,
        is_in_cache=False,
        predictive_active=True
    )
    assert decision_large_miss["decision"] == "DIRECT_FETCH"

    decision_large_hit = calculator.evaluate_routing_decision(
        key="analytics_report",
        n_predicted=1.0,
        size_kb=5000.0,
        p_compute=0.005,
        p_egress_per_kb=0.0001,
        p_storage_per_kb=0.005,
        p_write_op=0.001,
        is_in_cache=True,
        predictive_active=True
    )
    assert decision_large_hit["decision"] == "DIRECT_FETCH"

def test_api_endpoints():
    client = TestClient(app)
    
    # Reset metrics
    res_reset = client.post("/reset")
    assert res_reset.status_code == 200
    
    # Query key
    res_query = client.get("/query?key=user_profile")
    assert res_query.status_code == 200
    data = res_query.json()
    assert data["key"] == "user_profile"
    assert "served_from" in data
    assert "decision" in data

    # Check metrics
    res_metrics = client.get("/metrics")
    assert res_metrics.status_code == 200
    metrics = res_metrics.json()
    assert metrics["total_requests"] == 1
    assert len(metrics["logs"]) == 1
    
    # Change settings
    res_settings_post = client.post("/settings", json={
        "p_compute": 0.010,
        "p_egress_per_kb": 0.0002,
        "p_storage_per_kb": 0.001,
        "p_write_op": 0.002,
        "predictive_active": False
    })
    assert res_settings_post.status_code == 200
    
    # Verify settings update
    res_settings_get = client.get("/settings")
    assert res_settings_get.status_code == 200
    settings = res_settings_get.json()
    assert settings["p_compute"] == 0.010
    assert settings["predictive_active"] is False
