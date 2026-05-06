# models.py — shared data models for both services
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

class Signal(BaseModel):
    signal_id: str = str(uuid.uuid4())
    component_id: str               # e.g. "CACHE_CLUSTER_01"
    component_type: str             # e.g. "CACHE", "RDBMS", "API"
    error_type: str                 # e.g. "CONNECTION_TIMEOUT"
    payload: dict                   # raw error details
    timestamp: datetime

class WorkItem(BaseModel):
    id: str = str(uuid.uuid4())
    component_id: str
    component_type: str
    priority: str                   # P0, P1, P2
    state: str = "OPEN"
    start_time: datetime
    end_time: Optional[datetime] = None
    mttr_seconds: Optional[float] = None
    signal_ids: list[str] = []

class RCA(BaseModel):
    work_item_id: str
    root_cause_category: str        # e.g. "Infrastructure", "Code", "Human Error"
    problem_description: str
    fix_applied: str
    prevention_steps: str
    incident_start: datetime
    incident_end: datetime

class StateTransitionRequest(BaseModel):
    new_state: str

class HealthResponse(BaseModel):
    status: str = "ok"
    uptime_seconds: float