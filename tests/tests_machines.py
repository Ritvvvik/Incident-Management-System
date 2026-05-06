# tests/test_state_machine.py
import pytest
from state_machine import transition, InvalidTransitionError, RCARequiredError

# ── Valid transitions ────────────────────────────────────────

def test_open_to_investigating():
    result = transition("OPEN", "INVESTIGATING", has_rca=False)
    assert result == "INVESTIGATING"

def test_investigating_to_resolved():
    result = transition("INVESTIGATING", "RESOLVED", has_rca=False)
    assert result == "RESOLVED"

def test_resolved_to_closed_with_rca():
    result = transition("RESOLVED", "CLOSED", has_rca=True)
    assert result == "CLOSED"

# ── Invalid transitions ──────────────────────────────────────

def test_cannot_skip_states():
    with pytest.raises(InvalidTransitionError):
        transition("OPEN", "RESOLVED", has_rca=False)

def test_cannot_go_backwards():
    with pytest.raises(InvalidTransitionError):
        transition("RESOLVED", "OPEN", has_rca=False)

def test_cannot_leave_closed():
    with pytest.raises(InvalidTransitionError):
        transition("CLOSED", "OPEN", has_rca=True)

# ── RCA validation ───────────────────────────────────────────

def test_cannot_close_without_rca():
    with pytest.raises(RCARequiredError):
        transition("RESOLVED", "CLOSED", has_rca=False)

def test_can_close_with_rca():
    result = transition("RESOLVED", "CLOSED", has_rca=True)
    assert result == "CLOSED"


# tests/test_rca.py
import pytest
from datetime import datetime, timedelta

def calculate_mttr(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds()

def validate_rca(rca: dict) -> bool:
    required_fields = [
        "root_cause_category",
        "problem_description",
        "fix_applied",
        "prevention_steps",
        "incident_start",
        "incident_end"
    ]
    for field in required_fields:
        if not rca.get(field):
            raise ValueError(f"RCA missing required field: {field}")
    if rca["incident_end"] <= rca["incident_start"]:
        raise ValueError("incident_end must be after incident_start")
    return True

# ── RCA validation tests ─────────────────────────────────────

def test_valid_rca():
    rca = {
        "root_cause_category": "Infrastructure",
        "problem_description": "Redis OOM",
        "fix_applied": "Restarted node",
        "prevention_steps": "Add memory alerts",
        "incident_start": datetime(2025, 1, 1, 10, 0),
        "incident_end":   datetime(2025, 1, 1, 10, 45),
    }
    assert validate_rca(rca) is True

def test_rca_missing_field():
    rca = {
        "root_cause_category": "Infrastructure",
        "problem_description": "Redis OOM",
        # missing fix_applied and prevention_steps
        "incident_start": datetime(2025, 1, 1, 10, 0),
        "incident_end":   datetime(2025, 1, 1, 10, 45),
    }
    with pytest.raises(ValueError, match="fix_applied"):
        validate_rca(rca)

def test_rca_end_before_start():
    rca = {
        "root_cause_category": "Infrastructure",
        "problem_description": "Redis OOM",
        "fix_applied": "Restarted",
        "prevention_steps": "Add alerts",
        "incident_start": datetime(2025, 1, 1, 11, 0),
        "incident_end":   datetime(2025, 1, 1, 10, 0),  # before start!
    }
    with pytest.raises(ValueError, match="incident_end must be after"):
        validate_rca(rca)

def test_mttr_calculation():
    start = datetime(2025, 1, 1, 10, 0)
    end   = datetime(2025, 1, 1, 10, 45)
    assert calculate_mttr(start, end) == 2700.0  # 45 minutes in seconds