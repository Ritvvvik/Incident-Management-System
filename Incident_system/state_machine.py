# state_machine.py

VALID_TRANSITIONS = {
    "OPEN":          {"INVESTIGATING"},
    "INVESTIGATING": {"RESOLVED"},
    "RESOLVED":      {"CLOSED"},
    "CLOSED":        set()
}

class InvalidTransitionError(Exception):
    pass

class RCARequiredError(Exception):
    pass

def transition(current_state: str, new_state: str, has_rca: bool) -> str:
    # TODO 1: check if new_state is valid for current_state
    # hint: use VALID_TRANSITIONS[current_state]
    if new_state not in VALID_TRANSITIONS[current_state]:
        raise InvalidTransitionError(
            f"Cannot move from {current_state} to {new_state}"
        )

    # TODO 2: block CLOSED if RCA is missing
    # hint: check new_state == "CLOSED" and has_rca == False
    if new_state == "CLOSED" and not has_rca:
        raise RCARequiredError("RCA must be submitted before closing the incident")

    # TODO 3: return the new state
    return new_state