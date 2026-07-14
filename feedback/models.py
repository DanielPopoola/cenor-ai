import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db import Base


class FeedbackORM(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # unique=True enforces the 1:1-with-Session relationship, same
    # pattern as ObservationORM.session_id. FK points at sessions.id,
    # not observations.id — Feedback's stored invariant is "1:1 with
    # Session"; its dependency on Observation having already run is a
    # process ordering (TDD: "follows Observation"), not a storage
    # relationship, so there's no FK to the observations table itself.
    session_id: Mapped[str] = mapped_column(
        String, ForeignKey("sessions.id"), unique=True, nullable=False, index=True
    )
    trait_summary_raw: Mapped[str] = mapped_column(Text, nullable=False)
    focus_points_raw: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
