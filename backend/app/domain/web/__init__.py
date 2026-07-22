"""Public web retrieval contracts and the single URL safety policy."""

from app.domain.web.contracts import (
    WebFetchDiagnostics,
    WebFetchFailure,
    WebFetchFailureCode,
    WebFetchOutcome,
    WebFetchResult,
    WebPageContent,
    WebPageMetadata,
    WebRecoveryAction,
)

__all__ = [
    "WebFetchDiagnostics",
    "WebFetchFailure",
    "WebFetchFailureCode",
    "WebFetchOutcome",
    "WebFetchResult",
    "WebPageContent",
    "WebPageMetadata",
    "WebRecoveryAction",
]
