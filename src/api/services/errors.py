class ServiceError(Exception):
    """Base service-level error."""


class VKAuthorizationError(ServiceError):
    """Raised when VK OAuth or access token is missing/invalid."""


class VKOperationError(ServiceError):
    """Raised for generic VK API operation failures."""


class VKIDAuthorizationError(ServiceError):
    """Raised when VK ID auth or token is missing/invalid."""


class VKIDOperationError(ServiceError):
    """Raised for generic VK ID operation failures."""
