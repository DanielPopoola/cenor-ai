from common.errors import NotFoundError


class ObservationNotFoundError(NotFoundError):
    """No Observation exists yet for this session — either the session
    hasn't ended, or the background Observer task hasn't completed
    yet. Route layer maps this to 404, same as Feedback's polling
    contract (TDD: 'client polls until ready')."""
