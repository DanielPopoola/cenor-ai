from datetime import datetime

from pydantic import BaseModel, Field


class CreateJobPostingRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description_raw: str = Field(min_length=1, max_length=20_000)
    company: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=2000)


class JobPostingResponse(BaseModel):
    id: str
    user_id: str
    title: str
    company: str | None
    url: str | None
    description_raw: str
    created_at: datetime
