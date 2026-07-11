from fastapi import APIRouter

from auth.routes import router as auth_router
from candidate_profile.routes import router as candidate_profile_router


api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(
    candidate_profile_router, prefix="/profile", tags=["candidate_profile"]
)
