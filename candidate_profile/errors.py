from common.errors import NotFoundError, ValidationError


class CandidateProfileNotFoundError(NotFoundError):
    pass


class CVExtractionError(ValidationError):
    pass


class CVStructuringError(ValidationError):
    pass


class GitHubFetchError(ValidationError):
    pass


class GitHubStructuringError(ValidationError):
    pass
