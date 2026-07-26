class ProviderError(Exception):
    """Base class for expected, recoverable job-provider failures.

    job_service catches only this hierarchy when combining providers -- a
    ProviderError means "this provider is unavailable right now", not "this is
    a bug". Programming errors (KeyError, TypeError, etc.) are left to
    propagate so they are never mistaken for a provider outage.
    """


class ProviderFetchError(ProviderError):
    """Raised when a provider's API/feed could not be reached (network, HTTP status)."""


class ProviderResponseError(ProviderError):
    """Raised when a provider's response has an unexpected shape (bad payload/schema)."""
