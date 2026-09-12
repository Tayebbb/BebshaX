from bebshax.llm.router import PoolRouter


async def test_lifespan_wires_remote_pool_router(api_test_app) -> None:
    app = api_test_app.app
    assert isinstance(app.state.llm_router, PoolRouter)
    assert {"freellmpool", "openrouter"}.issubset(app.state.llm_adapters)
    assert "ollama" not in app.state.llm_adapters
    assert app.state.llm_router is app.state.llm_service
    assert app.state.database_revision_validated is True
    assert app.state.core_ready is True
    assert not hasattr(app.state, "local_tier_up")
    assert api_test_app.get("/api/health").status_code == 200
    assert api_test_app.get("/api/health/ready").status_code == 200
