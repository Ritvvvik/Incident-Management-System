# incident_system/rca.py
# Handles RCA validation and MTTR calculation

from datetime import datetime
from shared.models import RCA

# Valid root cause categories
VALID_CATEGORIES = [
    "Infrastructure",
    "Code Bug",
    "Human Error",
    "Third Party",
    "Capacity",
    "Security",
    "Unknown"
]

class RCAValidationError(Exception):
    pass

def validate_rca(rca: RCA) -> bool:
    """
    Validates RCA object has all required fields filled.
    Raises RCAValidationError if anything is missing or invalid.
    This is what blocks the CLOSED state transition.
    """
    # check root cause category is valid
    if rca.root_cause_category not in VALID_CATEGORIES:
        raise RCAValidationError(
            f"Invalid root_cause_category: '{rca.root_cause_category}'. "
            f"Must be one of: {VALID_CATEGORIES}"
        )

    # check all text fields are filled (not empty strings)
    if not rca.problem_description.strip():
        raise RCAValidationError("problem_description cannot be empty")

    if not rca.fix_applied.strip():
        raise RCAValidationError("fix_applied cannot be empty")

    if not rca.prevention_steps.strip():
        raise RCAValidationError("prevention_steps cannot be empty")

    # check timestamps make sense
    if rca.incident_end <= rca.incident_start:
        raise RCAValidationError(
            "incident_end must be after incident_start"
        )

    return True


def calculate_mttr(incident_start: datetime, incident_end: datetime) -> float:
    """
    Calculate Mean Time To Repair in seconds.
    MTTR = time from first signal (start) to RCA submission (end)
    """
    mttr_seconds = (incident_end - incident_start).total_seconds()

    if mttr_seconds <= 0:
        raise RCAValidationError("MTTR cannot be zero or negative")

    return mttr_seconds


def mttr_summary(mttr_seconds: float) -> dict:
    """Returns MTTR in multiple units for the UI."""
    return {
        "mttr_seconds": round(mttr_seconds, 2),
        "mttr_minutes": round(mttr_seconds / 60, 2),
        "mttr_hours":   round(mttr_seconds / 3600, 2),
    }