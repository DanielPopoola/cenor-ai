import re
from typing import Iterator

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session as DBSession

from auth.domain import User
from auth.routes import get_current_user
from candidate_profile.repository import CandidateProfileRepository
from candidate_profile.schemas import CandidateProfileResponse
from candidate_profile.service import CandidateProfileService
from common.errors import ValidationError
from common.schemas import APIResponse
from config import Settings

router = APIRouter()

# GitHub usernames: alphanumeric + single hyphens, can't start/end with
# a hyphen, max 39 chars — GitHub's own username constraints. Rejecting
# obviously-malformed input here avoids a wasted outbound API call.
_GITHUB_USERNAME_PATTERN = re.compile(
    r"^[a-zA-Z\d](?:[a-zA-Z\d]|-(?=[a-zA-Z\d])){0,38}$"
)

_ALLOWED_CV_EXTENSIONS = {"pdf", "docx"}


def get_db(request: Request) -> Iterator[DBSession]:
    yield from request.app.state.database.get_db_session()


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_candidate_profile_service(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    db: DBSession = Depends(get_db),
) -> CandidateProfileService:
    repository = CandidateProfileRepository(db)
    ai_service = request.app.state.ai_service
    return CandidateProfileService(settings, repository, ai_service)


def _validate_cv_upload(
    filename: str | None, file_bytes: bytes, settings: Settings
) -> None:
    if not filename or "." not in filename:
        raise ValidationError("Uploaded file must have a name with an extension")
    extension = filename.lower().rsplit(".", 1)[-1]
    if extension not in _ALLOWED_CV_EXTENSIONS:
        raise ValidationError(
            f"Unsupported file type '.{extension}' — only .pdf and .docx are accepted"
        )
    if len(file_bytes) == 0:
        raise ValidationError("Uploaded file is empty")
    if len(file_bytes) > settings.cv_upload_max_bytes:
        max_mb = settings.cv_upload_max_bytes / (1024 * 1024)
        raise ValidationError(f"File exceeds the {max_mb:.0f}MB upload limit")


def _validate_github_username(username: str) -> None:
    if not _GITHUB_USERNAME_PATTERN.match(username):
        raise ValidationError(
            "Invalid GitHub username — usernames may only contain "
            "alphanumeric characters and single hyphens, and cannot "
            "start or end with a hyphen"
        )


@router.get("")
def get_profile(
    user: User = Depends(get_current_user),
    service: CandidateProfileService = Depends(get_candidate_profile_service),
) -> APIResponse[CandidateProfileResponse]:
    profile = service.get_or_create(user.id)
    return APIResponse.ok(CandidateProfileResponse.from_domain(profile))


@router.post("/cv")
async def upload_cv(
    db: DBSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user: User = Depends(get_current_user),
    service: CandidateProfileService = Depends(get_candidate_profile_service),
    file: UploadFile = File(...),
) -> APIResponse[CandidateProfileResponse]:
    file_bytes = await file.read()
    _validate_cv_upload(file.filename, file_bytes, settings)

    profile = await service.upload_cv(
        user.id, file_bytes, file.filename if file.filename else ""
    )
    db.commit()
    return APIResponse.ok(CandidateProfileResponse.from_domain(profile))


@router.post("/github")
async def connect_github(
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
    service: CandidateProfileService = Depends(get_candidate_profile_service),
    username: str = Form(...),
) -> APIResponse[CandidateProfileResponse]:
    username = username.strip()
    _validate_github_username(username)

    profile = await service.connect_github(user.id, username)
    db.commit()
    return APIResponse.ok(CandidateProfileResponse.from_domain(profile))
