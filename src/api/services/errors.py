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


class AIEnhancementError(ServiceError):
    """Raised when AI enhancement is required but unavailable or failed."""


class VKAuthorizationError(ServiceError):
    """Raised when VK OAuth or access token is missing/invalid."""


class VKOperationError(ServiceError):
    """Raised for generic VK API operation failures."""
