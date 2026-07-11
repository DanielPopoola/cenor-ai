from datetime import datetime

from pydantic import BaseModel


class User(BaseModel):
    id: str
    email: str
    name: str | None
    google_sub: str
    created_at: datetime
