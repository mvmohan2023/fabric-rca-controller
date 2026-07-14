"""Public core framework API for Fabric Validation Platform."""

from controller.core.constants import (
    ExecutionStatus,
    RecoveryMode,
    ScenarioMaturity,
)
from controller.core.exceptions import (
    ArtifactError,
    ConfigurationError,
    DuplicateRegistrationError,
    FvpError,
    RcaError,
    RegistrationNotFoundError,
    RegistryError,
    ReportError,
    ScenarioError,
    ValidationError,
)
from controller.core.models import (
    ArtifactReference,
    CampaignResult,
    RcaFinding,
    RcaResult,
    ScenarioDefinition,
    StressResult,
    Target,
    ValidationResult,
)
from controller.core.registry import (
    Registry,
    rca_registry,
    report_registry,
    scenario_registry,
    stress_action_registry,
    validation_registry,
)

from controller.core.models import (
    ArtifactReference,
    CampaignResult,
    RcaFinding,
    RcaResult,
    ScenarioDefinition,
    StressActionContext,
    StressResult,
    Target,
    ValidationResult,
)

from controller.core.artifact_manager import ArtifactManager
from controller.core.execution_context import ExecutionContext
from controller.core.report_manager import ReportManager
__all__ = [
    "ArtifactError",
    "ArtifactReference",
    "CampaignResult",
    "ConfigurationError",
    "DuplicateRegistrationError",
    "ExecutionStatus",
    "FvpError",
    "RcaError",
    "RcaFinding",
    "RcaResult",
    "RecoveryMode",
    "RegistrationNotFoundError",
    "Registry",
    "RegistryError",
    "ReportError",
    "ScenarioDefinition",
    "ScenarioError",
    "ScenarioMaturity",
    "StressResult",
    "Target",
    "ValidationError",
    "ValidationResult",
    "rca_registry",
    "report_registry",
    "scenario_registry",
    "stress_action_registry",
    "validation_registry",
    "ArtifactManager",
    "ExecutionContext",
    "ReportManager",
    "StressActionContext",
]
