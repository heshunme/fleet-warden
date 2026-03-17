class ResourceNotFoundError(LookupError):
    pass


class InvalidTaskStateError(ValueError):
    pass


class InvalidInputError(ValueError):
    pass
