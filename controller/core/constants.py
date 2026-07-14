"""Shared constants for the Fabric Validation Platform core framework."""

from enum import Enum


class ExecutionStatus(str, Enum):
    """Standard execution states used across FVP components."""

    PENDING = "pending"
    RUNNING = "running"
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    ERROR = "error"


class ScenarioMaturity(str, Enum):
    """Lifecycle states for scenario implementation maturity."""

    PLANNED = "planned"
    DESIGNED = "designed"
    IMPLEMENTED = "implemented"
    SMOKE_VALIDATED = "smoke_validated"
    RCA_VALIDATED = "rca_validated"
    PRODUCTION_READY = "production_ready"
    DEPRECATED = "deprecated"


class RecoveryMode(str, Enum):
    """Recovery behavior expected from a scenario."""

    AUTOMATIC = "automatic"
    EXPLICIT = "explicit"
    NONE = "none"


STATUS_PASS = ExecutionStatus.PASS.value
STATUS_FAIL = ExecutionStatus.FAIL.value
STATUS_ERROR = ExecutionStatus.ERROR.value
STATUS_RUNNING = ExecutionStatus.RUNNING.value
STATUS_PENDING = ExecutionStatus.PENDING.value
STATUS_BLOCKED = ExecutionStatus.BLOCKED.value
STATUS_SKIPPED = ExecutionStatus.SKIPPED.value
