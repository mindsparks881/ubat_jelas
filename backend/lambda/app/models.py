"""
Pydantic request/response schemas.
Per SDD Section 3 — no DB, these are pure request/response contracts.
"""
from typing import List, Optional
from pydantic import BaseModel


class UploadResponse(BaseModel):
    raw_text: str
    confidence_score: float  # aggregated 0-100
    passed_confidence_check: bool
    message: Optional[str] = None  # populated if failed check


class TranslateRequest(BaseModel):
    raw_text: str
    session_language: str  # "ms" | "en" | "ta" | "zh"


class TranslateResponse(BaseModel):
    translated_text: str
    medicine_name: Optional[str] = None
    frequency_code: Optional[str] = None  # OD | BD | TDS | QID | PRN | None
    meal_relation: Optional[str] = None  # AC | PC | None
    duration: Optional[str] = None
    term_uncertain: bool = False
    warning_text: str = ""


class ReminderRequest(BaseModel):
    frequency_code: Optional[str] = None
    meal_relation: Optional[str] = None
    manual_times: Optional[List[str]] = None  # "HH:MM" if no frequency detected
    session_language: str = "en"


class ReminderTime(BaseModel):
    time: str  # "HH:MM"
    label: str  # e.g. "Morning dose"


class ReminderResponse(BaseModel):
    proposed_times: List[ReminderTime]
    source: str  # "auto" | "manual" | "prn"
    note: Optional[str] = None
