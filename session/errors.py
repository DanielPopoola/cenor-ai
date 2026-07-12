from common.errors import NotFoundError, ValidationError


class SessionNotFoundError(NotFoundError):
    pass


class SegmentNotFoundError(NotFoundError):
    pass


class CandidateProfileIncompleteError(ValidationError):
    """Session creation blocked — cv_structured doesn't meet the
    completeness bar yet. See TDD 'POST /sessions returns 403 if
    cv_structured is null'."""


class SessionNotInProgressError(ValidationError):
    """A turn was submitted against, or an end was requested for, a
    session that's already completed/abandoned."""
