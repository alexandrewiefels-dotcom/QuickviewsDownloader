# ============================================================================
# FILE: core/exceptions.py – Shared exception hierarchy
# ============================================================================
"""
Standardised exception hierarchy for the OrbitShow application.

All modules should raise these exceptions instead of generic Exception or
bare raise statements.  This allows callers to catch specific error types
and provide appropriate user feedback.
"""


class OrbitShowError(Exception):
    """Base exception for all application errors."""
    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


# ── TLE / Orbital Data ──────────────────────────────────────────────────────

class TLEError(OrbitShowError):
    """Base for TLE-related errors."""


class TLENotFoundError(TLEError):
    """No TLE data available for a given NORAD ID."""


class TLEFetchError(TLEError):
    """Failed to fetch TLE data from remote source."""


class TLECacheError(TLEError):
    """Local TLE cache is corrupted or inaccessible."""


class TLERateLimitError(TLEError):
    """Remote API rate limit exceeded."""


# ── Geometry / Detection ────────────────────────────────────────────────────

class GeometryError(OrbitShowError):
    """Base for geometry-related errors."""


class InvalidGeometryError(GeometryError):
    """Geometry is invalid or cannot be processed."""


class AntimeridianError(GeometryError):
    """Geometry crosses the antimeridian and cannot be split."""


class PassDetectionError(OrbitShowError):
    """Error during satellite pass detection."""


# ── AOI / Upload ────────────────────────────────────────────────────────────

class AOIError(OrbitShowError):
    """Base for AOI-related errors."""


class AOIUploadError(AOIError):
    """Failed to upload AOI to remote service."""


class AOIOutOfRangeError(AOIError):
    """AOI is outside the coverage area of the remote archive."""


class AOIInvalidFormatError(AOIError):
    """Uploaded file format is not supported."""


class AOITooLargeError(AOIError):
    """Uploaded file exceeds maximum size."""


# ── API / Network ───────────────────────────────────────────────────────────

class APIError(OrbitShowError):
    """Base for external API errors."""


class APIHTTPError(APIError):
    """HTTP error from external API."""


class APIAuthenticationError(APIError):
    """Authentication failed for external API."""


class APIRateLimitError(APIError):
    """Rate limit exceeded for external API."""


# ── Tasking ─────────────────────────────────────────────────────────────────

class TaskingError(OrbitShowError):
    """Error during tasking optimisation."""


class TaskingCoverageError(TaskingError):
    """Insufficient coverage for tasking request."""


# ── Configuration ───────────────────────────────────────────────────────────

class ConfigurationError(OrbitShowError):
    """Missing or invalid configuration."""


class SecretNotFoundError(ConfigurationError):
    """Required secret (API key, password) not found."""


# ── Navigation / Tracking ───────────────────────────────────────────────────

class TrackingError(OrbitShowError):
    """Error during navigation tracking."""


class TrackingStorageError(TrackingError):
    """Failed to read/write tracking data."""


# ── SASClouds ───────────────────────────────────────────────────────────────

class SASCloudsError(OrbitShowError):
    """Base for SASClouds integration errors."""


class SASCloudsAuthError(SASCloudsError):
    """Authentication failed for SASClouds API."""


class SASCloudsSearchError(SASCloudsError):
    """Search failed on SASClouds API."""


class SASCloudsDownloadError(SASCloudsError):
    """Failed to download data from SASClouds."""


# ── Weather ──────────────────────────────────────────────────────────────────

class WeatherError(OrbitShowError):
    """Error during weather data retrieval or processing."""


# ── Export ──────────────────────────────────────────────────────────────────

class ExportError(OrbitShowError):
    """Error during data export."""


class PDFExportError(ExportError):
    """Failed to generate PDF."""


class KMLExportError(ExportError):
    """Failed to generate KML."""


class CSVExportError(ExportError):
    """Failed to generate CSV."""
