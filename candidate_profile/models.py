import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db import Base


class CandidateProfileORM(Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), unique=True, nullable=False, index=True
    )

    cv_raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cv_attempted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cv_structured: Mapped[str | None] = mapped_column(Text, nullable=True)

    github_username: Mapped[str | None] = mapped_column(String, nullable=True)
    github_attempted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    github_structured: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
