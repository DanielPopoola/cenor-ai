from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

from auth.models import UserORM
from job_posting.models import JobPostingORM
from observation.repository import ObservationRepository
from observation.domain import ObservationEntry
from session.models import SessionORM


def _mock_response(status_code: int, json_data: dict):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data)
    return resp


def _login(client) -> None:
    login_resp = client.get("/api/v1/auth/google", follow_redirects=False)
    state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]

    fake_profile = {"sub": "g-obs-1", "email": "obs-routes@example.com", "name": "Obs"}
    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = _mock_response(200, {"access_token": "tok"})
        mock_instance.get.return_value = _mock_response(200, fake_profile)
        client.get(
            f"/api/v1/auth/google/callback?code=fake-code&state={state}",
            follow_redirects=False,
        )


def _seed_session(db_session, user_email: str) -> tuple[str, str]:
    """Returns (user_id, session_id). Bypasses the full session-creation
    service flow (no AI service needed) — inserts rows directly, since
    this test only cares about the observations GET endpoint."""
    user = db_session.query(UserORM).filter_by(email=user_email).first()
    job = JobPostingORM(user_id=user.id, title="Eng", description_raw="desc")
    db_session.add(job)
    db_session.flush()

    session = SessionORM(user_id=user.id, job_posting_id=job.id, duration_limit_minutes=30)
    db_session.add(session)
    db_session.flush()
    db_session.commit()
    return user.id, session.id


def test_get_observations_without_login_returns_401(client):
    r = client.get("/api/v1/sessions/some-id/observations")
    assert r.status_code == 401


def test_get_observations_returns_404_when_not_ready_yet(client, db_session):
    _login(client)
    _, session_id = _seed_session(db_session, "obs-routes@example.com")

    r = client.get(f"/api/v1/sessions/{session_id}/observations")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "ObservationNotFoundError"


def test_get_observations_returns_404_for_session_belonging_to_another_user(client, db_session):
    _login(client)

    other_user = UserORM(email="other-obs@example.com", name="Other", google_sub="other-obs-sub")
    db_session.add(other_user)
    db_session.flush()
    other_job = JobPostingORM(user_id=other_user.id, title="Eng", description_raw="d")
    db_session.add(other_job)
    db_session.flush()
    other_session = SessionORM(user_id=other_user.id, job_posting_id=other_job.id, duration_limit_minutes=30)
    db_session.add(other_session)
    db_session.flush()
    db_session.commit()

    r = client.get(f"/api/v1/sessions/{other_session.id}/observations")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "SessionNotFoundError"


def test_get_observations_returns_entries_once_ready(client, db_session):
    _login(client)
    _, session_id = _seed_session(db_session, "obs-routes@example.com")

    repo = ObservationRepository(db_session)
    repo.create(
        session_id=session_id,
        entries=[
            ObservationEntry(
                id=1,
                category="clarifies_ambiguity",
                fact="The candidate asked about input size.",
                turn_ref=[2],
            )
        ],
    )
    db_session.commit()

    r = client.get(f"/api/v1/sessions/{session_id}/observations")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["session_id"] == session_id
    assert len(body["entries"]) == 1
    assert body["entries"][0]["category"] == "clarifies_ambiguity"
    assert body["entries"][0]["turn_ref"] == [2]


def test_get_observations_empty_entries_list_still_returns_200(client, db_session):
    """Zero observations is a valid, expected Observer outcome — the
    route must not error just because entries is empty; that's
    different from 'not ready yet' (which is 404)."""
    _login(client)
    _, session_id = _seed_session(db_session, "obs-routes@example.com")

    repo = ObservationRepository(db_session)
    repo.create(session_id=session_id, entries=[])
    db_session.commit()

    r = client.get(f"/api/v1/sessions/{session_id}/observations")
    assert r.status_code == 200
    assert r.json()["data"]["entries"] == []
