class CernoError(Exception):
    def __init__(self, message: str | None = None):
        self.message = message or self.__class__.__name__
        super().__init__(self.message)


class NotFoundError(CernoError):
    pass


class ValidationError(CernoError):
    pass


class ConflictError(CernoError):
    pass


class UnauthorizedError(CernoError):
    pass
