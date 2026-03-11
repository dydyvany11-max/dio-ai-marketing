class ServiceError(Exception):
    """Base service-level error."""


class AlreadyAuthorizedError(ServiceError):
    """Raised when the user is already authorized."""


class AuthorizationRequiredError(ServiceError):
    """Raised when an endpoint requires an authorized Telegram user."""


class InvalidTelegramPostUrlError(ServiceError):
    """Raised when Telegram post URL is invalid."""


class TelegramPostNotFoundError(ServiceError):
    """Raised when Telegram post is not found."""


class TelegramOperationError(ServiceError):
    """Raised for generic Telegram API operation failures."""
