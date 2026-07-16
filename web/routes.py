from dataclasses import dataclass

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as DBSession

from auth.domain import User
from auth.routes import get_current_user
from candidate_profile.repository import CandidateProfileRepository
from candidate_profile.schemas import CandidateProfileResponse
from candidate_profile.service import CandidateProfileService
from job_posting.repository import JobPostingRepository
from session.lens import derive_lens_type
from session.repository import SessionRepository
from fastapi.responses import RedirectResponse

from web.templating import get_current_user_or_none, templates

router = APIRouter()


def _get_db(request: Request):
    yield from request.app.state.database.get_db_session()


@router.get("/")
def landing_page(
    request: Request,
    user: User | None = Depends(get_current_user_or_none),
):
    if user is not None:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(request, "landing.html", {"user": None})


@router.get("/auth")
def auth_page(
    request: Request,
    user: User | None = Depends(get_current_user_or_none),
):
    if user is not None:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(request, "auth/page.html", {"user": None})


@router.get("/onboarding")
def onboarding_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(_get_db),
):
    ai_service = request.app.state.ai_service
    settings = request.app.state.settings
    service = CandidateProfileService(
        settings, CandidateProfileRepository(db), ai_service
    )
    profile = service.get_or_create(user.id)
    return templates.TemplateResponse(
        request,
        "candidate_profile/page.html",
        {"user": user, "profile": CandidateProfileResponse.from_domain(profile)},
    )


@dataclass(frozen=True)
class SessionCardView:
    id: str
    job_title: str
    company: str | None
    lens_type: str
    status: str
    started_at_display: str


@router.get("/dashboard")
def dashboard_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(_get_db),
):
    session_repository = SessionRepository(db)
    job_posting_repository = JobPostingRepository(db)

    sessions = session_repository.list_sessions(user.id)

    cards = []
    for session in sessions:
        job_posting = job_posting_repository.find_by_id(user.id, session.job_posting_id)
        segments = session_repository.list_segments_for_session(session.id)
        lens_type = derive_lens_type(segments) if segments else "conversational"
        cards.append(
            SessionCardView(
                id=session.id,
                job_title=job_posting.title,
                company=job_posting.company,
                lens_type=lens_type,
                status=session.status,
                started_at_display=session.started_at.strftime("%b %-d"),
            )
        )

    in_progress = next((c for c in cards if c.status == "in_progress"), None)

    return templates.TemplateResponse(
        request,
        "session/dashboard.html",
        {"user": user, "cards": cards, "in_progress": in_progress},
    )
