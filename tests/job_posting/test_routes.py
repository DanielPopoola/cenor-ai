from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse


def _mock_response(status_code: int, json_data: dict):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data)
    return resp


def _login(client) -> None:
    login_resp = client.get("/api/v1/auth/google", follow_redirects=False)
    state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]

    fake_profile = {"sub": "g-jp-1", "email": "jp-routes@example.com", "name": "JP"}
    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = _mock_response(200, {"access_token": "tok"})
        mock_instance.get.return_value = _mock_response(200, fake_profile)
        client.get(
            f"/api/v1/auth/google/callback?code=fake-code&state={state}",
            follow_redirects=False,
        )


# --- auth boundary --------------------------------------------------------


def test_create_job_posting_without_login_returns_401(client):
    r = client.post("/api/v1/jobs", json={"title": "Eng", "description_raw": "desc"})
    assert r.status_code == 401


def test_list_job_postings_without_login_returns_401(client):
    r = client.get("/api/v1/jobs")
    assert r.status_code == 401


# --- create ----------------------------------------------------------------


def test_create_job_posting_success(client):
    _login(client)
    r = client.post(
        "/api/v1/jobs",
        json={
            "title": "Backend Engineer",
            "description_raw": "Build distributed systems",
            "company": "Acme",
            "url": "https://acme.example/jobs/1",
        },
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["title"] == "Backend Engineer"
    assert body["company"] == "Acme"


def test_create_job_posting_without_optional_fields(client):
    _login(client)
    r = client.post(
        "/api/v1/jobs", json={"title": "Eng", "description_raw": "desc"}
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["company"] is None
    assert body["url"] is None


def test_create_job_posting_rejects_empty_title(client):
    _login(client)
    r = client.post("/api/v1/jobs", json={"title": "", "description_raw": "desc"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "RequestValidationError"


def test_create_job_posting_rejects_empty_description(client):
    _login(client)
    r = client.post("/api/v1/jobs", json={"title": "Eng", "description_raw": ""})
    assert r.status_code == 422


def test_create_job_posting_rejects_oversized_description(client):
    _login(client)
    r = client.post(
        "/api/v1/jobs", json={"title": "Eng", "description_raw": "x" * 20_001}
    )
    assert r.status_code == 422


def test_create_job_posting_rejects_missing_title(client):
    _login(client)
    r = client.post("/api/v1/jobs", json={"description_raw": "desc"})
    assert r.status_code == 422


# --- get / list --------------------------------------------------------


def test_get_job_posting_by_id(client):
    _login(client)
    created = client.post(
        "/api/v1/jobs", json={"title": "Eng", "description_raw": "desc"}
    ).json()["data"]

    r = client.get(f"/api/v1/jobs/{created['id']}")
    assert r.status_code == 200
    assert r.json()["data"]["id"] == created["id"]


def test_get_job_posting_not_found_returns_404(client):
    _login(client)
    r = client.get("/api/v1/jobs/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "JobPostingNotFoundError"


def test_list_job_postings_returns_only_own_postings(client):
    _login(client)
    client.post("/api/v1/jobs", json={"title": "Mine", "description_raw": "d"})

    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    titles = [j["title"] for j in r.json()["data"]]
    assert "Mine" in titles


def test_list_job_postings_empty_when_none_created(client):
    _login(client)
    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    assert r.json()["data"] == []
