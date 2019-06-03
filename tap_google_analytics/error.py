class TapGaApiError(Exception):
    """Base exception for API errors."""

class TapGaInvalidArgumentError(TapGaApiError):
    """Exception for errors on the report definition."""

class TapGaAuthenticationError(TapGaApiError):
    """Exception for UNAUTHENTICATED && PERMISSION_DENIED errors."""

class TapGaRateLimitError(TapGaApiError):
    """Exception for Rate Limit errors."""

class TapGaQuotaExceededError(TapGaApiError):
    """Exception for Quota Exceeded errors."""

class TapGaUnknownError(TapGaApiError):
    """Exception for 5XX and other unknown errors."""
