"""Remediation planner module for Ghost Data Still Exists.

Constructs ordered execution plans adhering strictly to problem_statement.md § Allowed Operations:
1. Phase ordering: FINDING -> REMEDIATION -> VERIFICATION
2. Operation ordering within each phase
3. Deterministic tie-breaking: system_id ascending, resource_id ascending
4. Consecutive step numbering starting at 1
5. Evidence ID provenance:
   - COMPLETE: verification steps only, each with valid nonempty evidence_id proving compliant state
   - INCOMPLETE: findings cite evidence_id, proposed remediation and future verification have evidence_id=""
   - NOT_APPLICABLE: steps_json = []
"""

from dataclasses import dataclass
import json
from typing import Any, Dict, List, Optional, Tuple

try:
    from code.config import (
        DeletionStatus,
        Phase,
        Operation,
        State,
        PHASE_ORDER,
        OPERATION_ORDER,
        OPERATION_STATE_MAP,
    )
except (ImportError, ModuleNotFoundError):
    from config import (
        DeletionStatus,
        Phase,
        Operation,
        State,
        PHASE_ORDER,
        OPERATION_ORDER,
        OPERATION_STATE_MAP,
    )


@dataclass
class PlanStep:
    """A discrete step in an audit or remediation plan."""
    step_no: int
    phase: str
    system_id: str
    resource_id: str
    operation: str
    state: str
    evidence_id: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert step to dictionary adhering to the exact required output schema."""
        return {
            "step_no": self.step_no,
            "phase": self.phase,
            "system_id": self.system_id,
            "resource_id": self.resource_id,
            "operation": self.operation,
            "state": self.state,
            "evidence_id": self.evidence_id,
        }


def step_sort_key(step: Dict[str, Any]) -> Tuple[int, int, str, str]:
    """Deterministic sort key for plan steps:
    1. Phase order (FINDING -> REMEDIATION -> VERIFICATION)
    2. Operation order within the phase (from problem_statement.md table)
    3. system_id ascending
    4. resource_id ascending
    """
    phase = step.get("phase", "")
    op = step.get("operation", "")
    system_id = step.get("system_id", "")
    resource_id = step.get("resource_id", "")

    # Phase index
    try:
        phase_idx = PHASE_ORDER.index(phase)
    except ValueError:
        phase_idx = 99

    # Operation index within phase
    op_order = OPERATION_ORDER.get(phase, [])
    try:
        op_idx = op_order.index(op)
    except ValueError:
        op_idx = 99

    return (phase_idx, op_idx, system_id, resource_id)


class RemediationPlanner:
    """Builds and serializes compliant step plans for audit decisions."""

    def build_plan(
        self,
        status: DeletionStatus,
        findings: Optional[List[Dict[str, Any]]] = None,
        remediations: Optional[List[Dict[str, Any]]] = None,
        verifications: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Construct, sort, and consecutively number steps according to status contract."""
        # Contract 1: NOT_APPLICABLE produces an empty list []
        if status == DeletionStatus.NOT_APPLICABLE:
            return []

        raw_steps: List[Dict[str, Any]] = []

        if status == DeletionStatus.COMPLETE:
            # Contract 2: COMPLETE has VERIFICATION steps only, each with valid nonempty evidence_id
            if verifications:
                for v in verifications:
                    step_dict = dict(v)
                    step_dict["phase"] = Phase.VERIFICATION.value
                    # Ensure state matches operation contract if missing
                    if "state" not in step_dict or not step_dict["state"]:
                        step_dict["state"] = OPERATION_STATE_MAP.get(step_dict["operation"], State.ABSENT.value)
                    raw_steps.append(step_dict)

        elif status == DeletionStatus.INCOMPLETE:
            # Contract 3: INCOMPLETE has findings, proposed remediations, and future verifications
            if findings:
                for f in findings:
                    step_dict = dict(f)
                    step_dict["phase"] = Phase.FINDING.value
                    if "state" not in step_dict or not step_dict["state"]:
                        step_dict["state"] = OPERATION_STATE_MAP.get(step_dict["operation"], State.PRESENT.value)
                    raw_steps.append(step_dict)

            if remediations:
                for r in remediations:
                    step_dict = dict(r)
                    step_dict["phase"] = Phase.REMEDIATION.value
                    step_dict["evidence_id"] = ""  # Future work has empty evidence_id
                    if "state" not in step_dict or not step_dict["state"]:
                        step_dict["state"] = OPERATION_STATE_MAP.get(step_dict["operation"], State.ABSENT.value)
                    raw_steps.append(step_dict)

            if verifications:
                for v in verifications:
                    step_dict = dict(v)
                    step_dict["phase"] = Phase.VERIFICATION.value
                    step_dict["evidence_id"] = ""  # Future verification has empty evidence_id
                    if "state" not in step_dict or not step_dict["state"]:
                        step_dict["state"] = OPERATION_STATE_MAP.get(step_dict["operation"], State.ABSENT.value)
                    raw_steps.append(step_dict)

        # Sort according to exact phase, operation, and tie-breaking rules
        sorted_steps = sorted(raw_steps, key=step_sort_key)

        # Number steps consecutively starting at 1
        final_steps: List[Dict[str, Any]] = []
        for i, step in enumerate(sorted_steps, start=1):
            final_steps.append({
                "step_no": i,
                "phase": step["phase"],
                "system_id": step["system_id"],
                "resource_id": step["resource_id"],
                "operation": step["operation"],
                "state": step["state"],
                "evidence_id": step.get("evidence_id", ""),
            })

        return final_steps

    def serialize_steps(self, steps: List[Dict[str, Any]]) -> str:
        """Serialize plan steps into JSON array string (compact, deterministic)."""
        return json.dumps(steps, separators=(',', ':'))
