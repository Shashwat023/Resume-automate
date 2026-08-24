"""
Structured resume parsing. One OpenRouter call turns free-text resume
content into a stable ResumeFacts shape (education/employment/skills/
certifications), so Tier 1 can answer academic/professional questions from
real resume content instead of the profile's handful of summary columns.

Paid for ONCE per resume, not once per application — the caller
(services/resume_service.py::get_facts) is responsible for caching the
result on Resume.parsed_facts and only calling this when that cache is
empty. This module itself is stateless and does no caching/DB I/O.
"""

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.engine.openrouter_client import OpenRouterError, chat_json

settings = get_settings()


class EmploymentEntry(BaseModel):
    employer: str
    title: str
    start_date: str = ""
    end_date: str = ""
    description: str = ""


class EducationEntry(BaseModel):
    institution: str
    degree: str = ""
    field_of_study: str = ""
    graduation_year: str = ""


class ResumeFacts(BaseModel):
    employment: list[EmploymentEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "employment": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "employer": {"type": "string"},
                    "title": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": [
                    "employer",
                    "title",
                    "start_date",
                    "end_date",
                    "description",
                ],
                "additionalProperties": False,
            },
        },
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "institution": {"type": "string"},
                    "degree": {"type": "string"},
                    "field_of_study": {"type": "string"},
                    "graduation_year": {"type": "string"},
                },
                "required": [
                    "institution",
                    "degree",
                    "field_of_study",
                    "graduation_year",
                ],
                "additionalProperties": False,
            },
        },
        "skills": {"type": "array", "items": {"type": "string"}},
        "certifications": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["employment", "education", "skills", "certifications"],
    "additionalProperties": False,
}


async def parse_resume_facts(extracted_text: str) -> ResumeFacts:
    """
    Kill switch handled by the caller (chat_json raises OpenRouterError
    without a key) — resume_service.get_facts treats that as "no facts
    available" and Tier 1 keeps working off the profile alone, same
    degrade-gracefully pattern as Tier 1's own kill switch.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "Extract structured facts from this resume text. List every "
                "employment entry and every education entry found, most "
                "recent first. Use empty string for any date/field not "
                "present in the text — never invent one. Skills and "
                "certifications should be short strings, one item per skill."
            ),
        },
        {"role": "user", "content": extracted_text},
    ]
    raw, _usage = await chat_json(
        messages,
        json_schema=_RESPONSE_SCHEMA,
        schema_name="resume_facts",
        model=settings.openrouter_model_tier1,
    )
    return ResumeFacts.model_validate(raw)
