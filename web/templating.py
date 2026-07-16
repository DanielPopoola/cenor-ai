from pathlib import Path
from typing import Iterator

from fastapi import Cookie, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session as DBSession

from auth.domain import User
from auth.errors import InvalidSessionCookieError, UserNotFoundError
from auth.repository import UserRepository
from auth.service import AuthService
from common.display.session import area_label, session_status_label
from config import Settings

_ROOT = Path(__file__).parent.parent

# One shared Jinja2Templates instance, searching web/templates/ (base
# layout, shared partials) plus every domain's own templates/ folder
# (EPICS.md ticket convention: "Each domain serving fragments gets its
# own templates/ subfolder... since rendering is a concern belonging to
# the domain producing the data"). A single instance means a domain
# fragment can `{% extends "base.html" %}` without needing its own
# Jinja2Templates instance or duplicated filter registration.
_TEMPLATE_DIRS = [
    _ROOT / "web" / "templates",
    _ROOT / "session" / "templates",
    _ROOT / "feedback" / "templates",
    _ROOT / "candidate_profile" / "templates",
    _ROOT / "job_posting" / "templates",
    _ROOT / "auth" / "templates",
]

templates = Jinja2Templates(directory=[str(d) for d in _TEMPLATE_DIRS])
templates.env.filters["area_label"] = area_label
templates.env.filters["session_status_label"] = session_status_label


def is_htmx(request: Request) -> bool:
    """
    Content-negotiation helper for the HX-Request header (EPICS.md's
    "HTMX / JSON routing convention"): every route.py branches on this
    once, for rendering only — the service call underneath is
    identical whichever branch is taken.
    """
    return request.headers.get("HX-Request") == "true"


def _get_db(request: Request) -> Iterator[DBSession]:
    yield from request.app.state.database.get_db_session()


def _get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_current_user_or_none(
    request: Request,
    cerno_session: str | None = Cookie(default=None),
    settings: Settings = Depends(_get_settings),
    db: DBSession = Depends(_get_db),
) -> User | None:
    if cerno_session is None:
        return None
    service = AuthService(
        settings, UserRepository(db), request.app.state.oauth_state_store
    )
    try:
        user_id = service.verify_cookie_value(cerno_session)
        return UserRepository(db).find_by_id(user_id)
    except (InvalidSessionCookieError, UserNotFoundError):
        return None
