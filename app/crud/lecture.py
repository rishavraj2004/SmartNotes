# app/crud/lecture.py
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.lecture import Lecture, LectureNote, Transcript


def create_lecture(
    db: Session,
    title: str,
    source_type: str,
    source_url: str | None = None,
    file_path: str | None = None,
    user_id: int | None = None,
) -> Lecture:
    lecture = Lecture(
        title=title,
        source_type=source_type,
        source_url=source_url,
        file_path=file_path,
        user_id=user_id,
        status="pending",
    )
    db.add(lecture)
    db.commit()
    db.refresh(lecture)
    return lecture


def get_lecture(db: Session, lecture_id: int) -> Lecture | None:
    stmt = (
        select(Lecture)
        .where(Lecture.id == lecture_id)
        .options(selectinload(Lecture.transcript), selectinload(Lecture.notes))
    )
    return db.scalars(stmt).first()


def get_lectures(
    db: Session, skip: int = 0, limit: int = 100, user_id: int | None = None
) -> list[Lecture]:
    stmt = select(Lecture).order_by(Lecture.created_at.desc()).offset(skip).limit(limit)
    if user_id is not None:
        stmt = stmt.where(Lecture.user_id == user_id)
    return list(db.scalars(stmt).all())


def update_lecture_status(
    db: Session,
    lecture: Lecture,
    status: str,
    error_message: str | None = None,
) -> Lecture:
    lecture.status = status
    if error_message is not None:
        lecture.error_message = error_message
    db.commit()
    db.refresh(lecture)
    return lecture


def upsert_transcript(
    db: Session,
    lecture_id: int,
    raw_transcript: str,
    filtered_transcript: str | None = None,
    language: str = "en",
    duration_seconds: float | None = None,
) -> Transcript:
    transcript = db.scalars(
        select(Transcript).where(Transcript.lecture_id == lecture_id)
    ).first()

    if transcript:
        transcript.raw_transcript = raw_transcript
        if filtered_transcript is not None:
            transcript.filtered_transcript = filtered_transcript
        transcript.language = language
        transcript.duration_seconds = duration_seconds
    else:
        transcript = Transcript(
            lecture_id=lecture_id,
            raw_transcript=raw_transcript,
            filtered_transcript=filtered_transcript,
            language=language,
            duration_seconds=duration_seconds,
        )
        db.add(transcript)

    db.commit()
    db.refresh(transcript)
    return transcript


def update_filtered_transcript(
    db: Session,
    lecture_id: int,
    filtered_transcript: str,
) -> Transcript | None:
    transcript = db.scalars(
        select(Transcript).where(Transcript.lecture_id == lecture_id)
    ).first()
    if not transcript:
        return None
    transcript.filtered_transcript = filtered_transcript
    db.commit()
    db.refresh(transcript)
    return transcript


def upsert_lecture_notes(
    db: Session,
    lecture_id: int,
    title: str,
    summary: str,
    structured_notes: str,
    key_concepts: list[dict[str, Any]] | None = None,
    study_questions: list[dict[str, Any]] | None = None,
) -> LectureNote:
    note = db.scalars(
        select(LectureNote).where(LectureNote.lecture_id == lecture_id)
    ).first()

    if note:
        note.title = title
        note.summary = summary
        note.structured_notes = structured_notes
        note.key_concepts = key_concepts
        note.study_questions = study_questions
    else:
        note = LectureNote(
            lecture_id=lecture_id,
            title=title,
            summary=summary,
            structured_notes=structured_notes,
            key_concepts=key_concepts,
            study_questions=study_questions,
        )
        db.add(note)

    db.commit()
    db.refresh(note)
    return note


def delete_lecture(db: Session, lecture: Lecture) -> None:
    db.delete(lecture)
    db.commit()
