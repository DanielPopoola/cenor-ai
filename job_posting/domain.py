from datetime import datetime

from pydantic import BaseModel


class JobPosting(BaseModel):
    id: str
    user_id: str
    title: str
    company: str | None = None  # confirmed on New Session form; see EPICS
    url: str | None = None
    description_raw: str
    created_at: datetime
