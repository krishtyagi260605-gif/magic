import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    """Returns a test client for the FastAPI app."""
    with TestClient(app) as c:
        yield c