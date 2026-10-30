# app/schemas/lecture.py
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


# ---------------- Transcript Schemas ----------------
class TranscriptBase(BaseModel):
    raw_transcript: str
    filtered_transcript: str | None = None
    language: str = "en"
    duration_seconds: float | None = None


class TranscriptCreate(TranscriptBase):
    lecture_id: int


class TranscriptOut(TranscriptBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lecture_id: int
    created_at: datetime


# ---------------- Lecture Notes Schemas ----------------
class KeyConcept(BaseModel):
    concept: str = Field(description="Name or title of the key concept")
    explanation: str = Field(description="Concise, clear explanation")


class StudyQuestion(BaseModel):
    question: str = Field(description="Self-study or exam review question")
    answer: str = Field(description="Clear, comprehensive answer")


class LectureNoteBase(BaseModel):
    title: str
    summary: str
    key_concepts: list[dict[str, Any]] | list[KeyConcept] | None = None
    structured_notes: str
    study_questions: list[dict[str, Any]] | list[StudyQuestion] | None = None


class LectureNoteCreate(LectureNoteBase):
    lecture_id: int


class LectureNoteOut(LectureNoteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lecture_id: int
    created_at: datetime


# ---------------- Lecture Schemas ----------------
class LectureBase(BaseModel):
    title: str
    source_type: str = "upload"  # "upload" or "youtube"
    source_url: str | None = None


class LectureCreate(BaseModel):
    title: str = Field(default="Untitled Lecture", max_length=255)


class YouTubeIngestRequest(BaseModel):
    url: str = Field(..., description="YouTube video URL")
    title: str | None = Field(default=None, description="Optional custom title for lecture")


class FilterTranscriptRequest(BaseModel):
    custom_instructions: str | None = Field(
        default=None,
        description="Optional custom filtering rules (e.g. 'focus on statistics topics' or 'remove intro jokes')",
    )


class GenerateNotesRequest(BaseModel):
    custom_focus: str | None = Field(
        default=None,
        description="Optional focus for note generation (e.g. 'emphasis on math formulas' or 'include bullet points')",
    )
    format_style: str = Field(
        default="comprehensive",
        description="'comprehensive', 'quick_review', or 'exam_cram'",
    )


class LectureOut(LectureBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class LectureDetailOut(LectureOut):
    transcript: TranscriptOut | None = None
    notes: LectureNoteOut | None = None
