import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db import Base


class SessionORM(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True
    )
    job_posting_id: Mapped[str] = mapped_column(
        String, ForeignKey("job_postings.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="in_progress")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_limit_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    strictness_mode: Mapped[str] = mapped_column(
        String, nullable=False, default="standard"
    )


class SegmentORM(Base):
    __tablename__ = "segments"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String, ForeignKey("sessions.id"), nullable=False, index=True
    )
    segment_order: Mapped[int] = mapped_column(Integer, nullable=False)
    area: Mapped[str] = mapped_column(String, nullable=False)
    editor_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    duration_limit_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    # JSON TEXT — serialize/deserialize is a repository concern, same
    # pattern as candidate_profile's cv_structured/github_structured.
    checklist: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TurnORM(Base):
    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Turn belongs to Segment, not Session directly — Section 2a.
    segment_id: Mapped[str] = mapped_column(
        String, ForeignKey("segments.id"), nullable=False, index=True
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    code_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
