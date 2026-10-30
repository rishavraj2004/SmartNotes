# app/services/pipeline.py
import logging
from app.database import SessionLocal
from app.crud import lecture as crud_lecture
from app.services import gemini_service, video_service

logger = logging.getLogger(__name__)


def run_lecture_pipeline(
    lecture_id: int,
    custom_filter_instructions: str | None = None,
    custom_notes_focus: str | None = None,
    format_style: str = "comprehensive",
) -> None:
    """
    Background worker that runs the full end-to-end pipeline:
    1. Transcribe Media (Video/Audio) -> Raw Transcript with timestamps
    2. Filter Transcript -> Clean, filler-free, organized transcript
    3. Generate Lecture Notes -> Summary, Key Concepts, Markdown Notes, Practice Questions
    """
    db = SessionLocal()
    try:
        lecture = crud_lecture.get_lecture(db, lecture_id)
        if not lecture:
            logger.error(f"Pipeline error: Lecture with ID {lecture_id} not found.")
            return

        if not lecture.file_path:
            crud_lecture.update_lecture_status(
                db, lecture, status="failed", error_message="No media file path associated with lecture."
            )
            return

        # ---------------- Stage 1: Transcription ----------------
        logger.info(f"[Lecture {lecture_id}] Preparing audio and starting transcription...")
        crud_lecture.update_lecture_status(db, lecture, status="transcribing")

        # Convert video to lightweight MP3 for fast, reliable Gemini transcription
        audio_file_path = video_service.extract_audio(lecture.file_path)
        raw_transcript = gemini_service.transcribe_media(audio_file_path)
        crud_lecture.upsert_transcript(
            db,
            lecture_id=lecture.id,
            raw_transcript=raw_transcript,
        )

        # ---------------- Stage 2: Filtering ----------------
        logger.info(f"[Lecture {lecture_id}] Starting Transcript Filtering...")
        crud_lecture.update_lecture_status(db, lecture, status="filtering")

        filtered_transcript = gemini_service.filter_transcript(
            raw_transcript=raw_transcript,
            custom_instructions=custom_filter_instructions,
        )
        crud_lecture.update_filtered_transcript(
            db,
            lecture_id=lecture.id,
            filtered_transcript=filtered_transcript,
        )

        # ---------------- Stage 3: Notes Generation ----------------
        logger.info(f"[Lecture {lecture_id}] Generating Lecture Notes...")
        crud_lecture.update_lecture_status(db, lecture, status="generating_notes")

        notes_data = gemini_service.generate_lecture_notes(
            filtered_transcript=filtered_transcript,
            lecture_title=lecture.title,
            format_style=format_style,
            custom_focus=custom_notes_focus,
        )

        crud_lecture.upsert_lecture_notes(
            db,
            lecture_id=lecture.id,
            title=f"Study Notes: {lecture.title}",
            summary=notes_data.get("summary", ""),
            structured_notes=notes_data.get("structured_notes", ""),
            key_concepts=notes_data.get("key_concepts", []),
            study_questions=notes_data.get("study_questions", []),
        )

        # ---------------- Completed ----------------
        crud_lecture.update_lecture_status(db, lecture, status="completed")
        logger.info(f"[Lecture {lecture_id}] Pipeline completed successfully!")

    except Exception as e:
        logger.exception(f"[Lecture {lecture_id}] Pipeline failed with error: {e}")
        try:
            lecture = crud_lecture.get_lecture(db, lecture_id)
            if lecture:
                crud_lecture.update_lecture_status(
                    db, lecture, status="failed", error_message=str(e)
                )
        except Exception as inner_e:
            logger.error(f"Failed to update error status on DB: {inner_e}")
    finally:
        db.close()
