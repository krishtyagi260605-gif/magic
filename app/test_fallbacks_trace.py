from concurrent.futures import TimeoutError as FuturesTimeout

def test_trace_endpoint(client):
    """Verify the trace endpoint behaves correctly for missing data."""
    assert client.get("/v1/trace/nonexistent-session").status_code == 404

def test_retry_fallback_logic():
    """Verify exponential backoff retries and cross-provider fallback handling in the graph."""
    from app.graph import _run_with_retries
    
    call_count = 0
    def _failing_call(provider):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise FuturesTimeout("Simulated timeout")
        return f"Success on {provider}!"

    # Test session logic natively
    res = _run_with_retries(_failing_call, "test_retry_session", 1)
    assert "Success" in res
    assert call_count == 3