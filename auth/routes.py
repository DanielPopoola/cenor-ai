from typing import Iterator

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as DBSession

from auth.domain import User
from auth.errors import InvalidSessionCookieError
from auth.repository import UserRepository
from auth.service import AuthService
from candidate_profile.repository import CandidateProfileRepository
from config import Settings
from common.schemas import APIResponse

router = APIRouter()


def get_db(request: Request) -> Iterator[DBSession]:
    yield from request.app.state.database.get_db_session()


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_auth_service(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    db: DBSession = Depends(get_db),
) -> AuthService:
    repository = UserRepository(db)
    return AuthService(settings, repository, request.app.state.oauth_state_store)


def get_current_user(
    cerno_session: str | None = Cookie(default=None),
    service: AuthService = Depends(get_auth_service),
    db: DBSession = Depends(get_db),
) -> User:
    if cerno_session is None:
        raise InvalidSessionCookieError("No session cookie present")

    user_id = service.verify_cookie_value(cerno_session)
    repository = UserRepository(db)
    return repository.find_by_id(user_id)


@router.get("/google")
def google_login(service: AuthService = Depends(get_auth_service)) -> RedirectResponse:
    url = service.build_google_authorize_url()
    return RedirectResponse(url=url, status_code=302)


@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    db: DBSession = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings_dep),
) -> RedirectResponse:
    user = await service.handle_google_callback(code=code, state=state)
    db.commit()
    cookie_value = service.issue_cookie_value(user.id)

    profile = CandidateProfileRepository(db).find_by_user_id_or_none(user.id)
    destination = (
        "/dashboard"
        if profile is not None and profile.cv_status == "done"
        else "/onboarding"
    )

    redirect = RedirectResponse(url=destination, status_code=302)
    redirect.set_cookie(
        key=settings.cookie_name,
        value=cookie_value,
        max_age=settings.cookie_max_age_seconds,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )
    return redirect


@router.post("/logout")
def logout(
    response: Response, settings: Settings = Depends(get_settings_dep)
) -> APIResponse[dict]:
    response.delete_cookie(key=settings.cookie_name)
    return APIResponse.ok({"logged_out": True})


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> APIResponse[User]:
    return APIResponse.ok(user)
