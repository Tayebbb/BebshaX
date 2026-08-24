from fastapi.testclient import TestClient

from bebshax.llm.router import PoolRouter
from bebshax.main import create_app


def test_lifespan_wires_pool_router_with_default_adapters() -> None:
    app = create_app()
    with TestClient(app) as client:  # context manager triggers lifespan
        assert isinstance(app.state.llm_router, PoolRouter)
        assert set(app.state.llm_adapters) == {"openrouter", "freellmpool", "ollama"}
        assert client.get("/api/health").status_code == 200
