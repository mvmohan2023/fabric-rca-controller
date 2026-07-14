"""Exception hierarchy for Fabric Validation Platform core services."""


class FvpError(Exception):
    """Base exception for all FVP-specific failures."""


class ConfigurationError(FvpError):
    """Raised when configuration or required inputs are invalid."""


class RegistryError(FvpError):
    """Base exception for registry-related failures."""


class DuplicateRegistrationError(RegistryError):
    """Raised when a registry key is already registered."""


class RegistrationNotFoundError(RegistryError):
    """Raised when a requested registry key does not exist."""


class ScenarioError(FvpError):
    """Raised when scenario resolution or execution fails."""


class ValidationError(FvpError):
    """Raised when validation cannot be completed."""


class ArtifactError(FvpError):
    """Raised when artifact creation, reading, or archival fails."""


class RcaError(FvpError):
    """Raised when RCA processing cannot be completed."""


class ReportError(FvpError):
    """Raised when report generation fails."""
