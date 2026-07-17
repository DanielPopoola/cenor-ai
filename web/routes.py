from dataclasses import dataclass

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session as DBSession

from auth.domain import User
from auth.routes import get_current_user
from candidate_profile.repository import CandidateProfileRepository
from candidate_profile.schemas import CandidateProfileResponse
from candidate_profile.service import CandidateProfileService
from config import Settings
from job_posting.repository import JobPostingRepository
from job_posting.service import JobPostingService
from session.lens import derive_lens_type
from session.repository import SessionRepository
from session.service import SessionService
from web.templating import get_current_user_or_none, templates

router = APIRouter()


def _get_db(request: Request):
    yield from request.app.state.database.get_db_session()


def _get_settings(request: Request) -> Settings:
    return request.app.state.settings


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


@router.get("/sessions/{session_id}")
def session_interview_page(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(_get_db),
):
    session_repository = SessionRepository(db)
    job_posting_repository = JobPostingRepository(db)

    session_service = SessionService(
        settings=request.app.state.settings,
        repository=session_repository,
        candidate_profile_repository=CandidateProfileRepository(db),
        job_posting_repository=job_posting_repository,
        ai_service=request.app.state.ai_service,
    )
    session = session_service.get_session(user.id, session_id)

    if session.status != "in_progress":
        return RedirectResponse(url=f"/sessions/{session_id}/feedback", status_code=302)

    job = job_posting_repository.find_by_id(user.id, session.job_posting_id)
    segments = session_repository.list_segments_for_session(session_id)
    current_segment = next(s for s in segments if s.status == "in_progress")
    segment_order_index = current_segment.segment_order

    turns = session_repository.list_turns_for_segment(current_segment.id)
    last_interviewer_turn = next(
        (t for t in reversed(turns) if t.speaker == "interviewer"), None
    )
    question = last_interviewer_turn.content if last_interviewer_turn else ""

    return templates.TemplateResponse(
        request,
        "session/_shell.html",
        {
            "user": user,
            "session": session,
            "job": job,
            "segment": current_segment,
            "segment_order_index": segment_order_index,
            "question": question,
        },
    )


@dataclass(frozen=True)
class JobListItemView:
    job: object
    session_count: int


@router.get("/jobs")
def jobs_list_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(_get_db),
):
    job_posting_repository = JobPostingRepository(db)
    session_repository = SessionRepository(db)

    jobs = job_posting_repository.list_for_user(user.id)
    all_sessions = session_repository.list_sessions(user.id)

    items = []
    for job in jobs:
        count = sum(1 for s in all_sessions if s.job_posting_id == job.id)
        items.append(JobListItemView(job=job, session_count=count))

    return templates.TemplateResponse(
        request, "job_posting/list.html", {"user": user, "jobs": items}
    )


@router.get("/jobs/new")
def new_job_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(_get_db),
):
    profile = CandidateProfileRepository(db).find_by_user_id_or_none(user.id)
    if profile is None or profile.cv_status != "done":
        return RedirectResponse(url="/onboarding", status_code=302)

    return templates.TemplateResponse(request, "job_posting/new.html", {"user": user})


@router.post("/jobs/new")
def create_job_from_form(
    request: Request,
    title: str = Form(...),
    description_raw: str = Form(...),
    company: str | None = Form(default=None),
    url: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: DBSession = Depends(_get_db),
):
    job_posting_service = JobPostingService(JobPostingRepository(db))
    job = job_posting_service.create(
        user_id=user.id,
        title=title,
        description_raw=description_raw,
        company=company or None,
        url=url or None,
    )
    db.commit()

    response = Response(status_code=200)
    response.headers["HX-Redirect"] = f"/jobs/{job.id}"
    return response


@router.get("/jobs/{job_posting_id}")
def job_detail_page(
    job_posting_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(_get_db),
    settings: Settings = Depends(_get_settings),
):
    job_posting_repository = JobPostingRepository(db)
    session_repository = SessionRepository(db)

    job = job_posting_repository.find_by_id(user.id, job_posting_id)
    sessions = [
        s
        for s in session_repository.list_sessions(user.id)
        if s.job_posting_id == job.id
    ]

    session_views = []
    for s in sessions:
        segments = session_repository.list_segments_for_session(s.id)
        lens_type = derive_lens_type(segments) if segments else "conversational"
        session_views.append(
            SessionCardView(
                id=s.id,
                job_title=job.title,
                company=job.company,
                lens_type=lens_type,
                status=s.status,
                started_at_display=s.started_at.strftime("%b %-d"),
            )
        )

    return templates.TemplateResponse(
        request,
        "job_posting/detail.html",
        {
            "user": user,
            "job": job,
            "sessions": session_views,
            "length_options": settings.session_length_options,
            "default_length": settings.session_length_default,
        },
    )


@router.post("/jobs/{job_posting_id}/sessions")
async def start_session_for_job(
    job_posting_id: str,
    request: Request,
    duration_limit_minutes: int = Form(...),
    user: User = Depends(get_current_user),
    db: DBSession = Depends(_get_db),
    settings: Settings = Depends(_get_settings),
):
    session_service = SessionService(
        settings=settings,
        repository=SessionRepository(db),
        candidate_profile_repository=CandidateProfileRepository(db),
        job_posting_repository=JobPostingRepository(db),
        ai_service=request.app.state.ai_service,
    )
    session, _first_segment, _result = await session_service.create_session(
        user_id=user.id,
        job_posting_id=job_posting_id,
        duration_limit_minutes=duration_limit_minutes,
    )
    db.commit()

    response = Response(status_code=200)
    response.headers["HX-Redirect"] = f"/sessions/{session.id}"
    return response
