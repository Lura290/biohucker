from fastapi.testclient import TestClient

from biohucker.web.app import create_app


def test_home_page_responds(db_url) -> None:
    client = TestClient(create_app(database_url=db_url))

    response = client.get("/")

    assert response.status_code == 200
    assert "biohucker" in response.text
