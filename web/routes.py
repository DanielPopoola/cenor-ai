from fastapi import APIRouter, Depends, Request

from auth.domain import User
from web.templating import get_current_user_or_none, templates

router = APIRouter()


@router.get("/auth")
def auth_page(
    request: Request,
    user: User | None = Depends(get_current_user_or_none),
):
    return templates.TemplateResponse(request, "auth/page.html", {"user": user})
