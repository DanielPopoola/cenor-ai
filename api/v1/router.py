from fastapi import APIRouter

api_router = APIRouter()

# Populated once auth/routes.py exists (ticket 10):
# from auth.routes import router as auth_router
# api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
