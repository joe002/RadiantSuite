"""
RadiantSuite Core - Shared infrastructure for 2026 agent-first tools

Provides:
- Determinism layer (strict reproducibility)
- Audit logging
- Human gate system
- Synapse command registration
"""
from .determinism import (
    DeterministicOperation,
    DeterministicConfig,
    round_float,
    round_vector,
    deterministic_uuid,
    deterministic_sort,
)
from .audit import (
    AuditLog,
    AuditEntry,
    AuditLevel,
    AuditCategory,
    audit_log,
)
from .gates import (
    HumanGate,
    GateDecision,
    GateLevel,
    GateProposal,
    GateBatch,
    human_gate,
    propose_change,
)

__all__ = [
    # Determinism
    'DeterministicOperation',
    'DeterministicConfig',
    'round_float',
    'round_vector',
    'deterministic_uuid',
    'deterministic_sort',
    # Audit
    'AuditLog',
    'AuditEntry',
    'AuditLevel',
    'AuditCategory',
    'audit_log',
    # Gates
    'HumanGate',
    'GateDecision',
    'GateLevel',
    'GateProposal',
    'GateBatch',
    'human_gate',
    'propose_change',
]
