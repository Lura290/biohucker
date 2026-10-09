from fastapi.testclient import TestClient

from biohucker.web.app import create_app


def test_home_page_responds() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "biohucker" in response.text
