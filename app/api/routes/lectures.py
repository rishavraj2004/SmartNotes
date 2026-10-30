# app/api/routes/lectures.py
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.crud import lecture as crud_lecture
from app.database import get_db
from app.models.user import User
from app.schemas.lecture import (
    FilterTranscriptRequest,
    GenerateNotesRequest,
    LectureDetailOut,
    LectureNoteOut,
    LectureOut,
    TranscriptOut,
    YouTubeIngestRequest,
)
from app.services import gemini_service, video_service
from app.services.pipeline import run_lecture_pipeline

router = APIRouter(prefix="/lectures", tags=["lectures"])


@router.post("/upload", response_model=LectureOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_lecture_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """
    Upload a lecture video or audio file (MP4, MKV, MP3, WAV, etc.).
    Automatically starts the transcription, filtering, and notes generation pipeline.
    """
    saved_path, auto_title = await video_service.save_uploaded_file(file)
    lecture_title = (title or auto_title).strip() or "Uploaded Lecture"

    lecture = crud_lecture.create_lecture(
        db=db,
        title=lecture_title,
        source_type="upload",
        file_path=saved_path,
    )

    # Launch background processing pipeline
    background_tasks.add_task(run_lecture_pipeline, lecture.id)
    return lecture


@router.post("/youtube", response_model=LectureOut, status_code=status.HTTP_202_ACCEPTED)
def ingest_youtube_lecture(
    request: YouTubeIngestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Ingest a lecture video directly from a YouTube URL.
    Downloads the audio/video and automatically kicks off transcription, filtering, and note generation.
    """
    file_path, auto_title = video_service.download_youtube_media(request.url)
    lecture_title = (request.title or auto_title).strip() or "YouTube Lecture"

    lecture = crud_lecture.create_lecture(
        db=db,
        title=lecture_title,
        source_type="youtube",
        source_url=request.url,
        file_path=file_path,
    )

    background_tasks.add_task(run_lecture_pipeline, lecture.id)
    return lecture


@router.get("/", response_model=list[LectureOut])
def list_lectures(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Retrieve list of all processed or pending lectures."""
    return crud_lecture.get_lectures(db, skip=skip, limit=limit)


@router.get("/{lecture_id}", response_model=LectureDetailOut)
def get_lecture_details(
    lecture_id: int,
    db: Session = Depends(get_db),
):
    """Get full details of a lecture including current status, transcript, and generated notes."""
    lecture = crud_lecture.get_lecture(db, lecture_id)
    if not lecture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lecture not found")
    return lecture


@router.get("/{lecture_id}/transcript", response_model=TranscriptOut)
def get_lecture_transcript(
    lecture_id: int,
    db: Session = Depends(get_db),
):
    """Get the raw and filtered transcripts for a lecture."""
    lecture = crud_lecture.get_lecture(db, lecture_id)
    if not lecture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lecture not found")
    if not lecture.transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transcript not yet available. Current status: {lecture.status}",
        )
    return lecture.transcript


@router.get("/{lecture_id}/notes", response_model=LectureNoteOut)
def get_lecture_notes(
    lecture_id: int,
    db: Session = Depends(get_db),
):
    """Get the generated study notes, executive summary, key concepts, and quiz flashcards."""
    lecture = crud_lecture.get_lecture(db, lecture_id)
    if not lecture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lecture not found")
    if not lecture.notes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notes not yet generated. Current status: {lecture.status}",
        )
    return lecture.notes


@router.get("/{lecture_id}/notes/markdown")
def download_notes_markdown(
    lecture_id: int,
    db: Session = Depends(get_db),
):
    """Download or view the structured notes as raw Markdown format."""
    lecture = crud_lecture.get_lecture(db, lecture_id)
    if not lecture or not lecture.notes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notes not found")

    markdown_content = f"# {lecture.notes.title}\n\n"
    markdown_content += f"## Executive Summary\n{lecture.notes.summary}\n\n"
    markdown_content += lecture.notes.structured_notes

    if lecture.notes.key_concepts:
        markdown_content += "\n\n## Key Concepts Glossary\n"
        for item in lecture.notes.key_concepts:
            concept = item.get("concept", "")
            explanation = item.get("explanation", "")
            markdown_content += f"- **{concept}**: {explanation}\n"

    if lecture.notes.study_questions:
        markdown_content += "\n\n## Practice & Review Questions\n"
        for idx, item in enumerate(lecture.notes.study_questions, 1):
            q = item.get("question", "")
            a = item.get("answer", "")
            markdown_content += f"### {idx}. {q}\n**Answer:** {a}\n\n"

    return Response(
        content=markdown_content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="lecture_{lecture_id}_notes.md"'
        },
    )


@router.post("/{lecture_id}/filter", response_model=TranscriptOut)
def re_filter_transcript(
    lecture_id: int,
    request: FilterTranscriptRequest,
    db: Session = Depends(get_db),
):
    """Re-filter the raw transcript using updated custom instructions."""
    lecture = crud_lecture.get_lecture(db, lecture_id)
    if not lecture or not lecture.transcript:
        raise HTTPException(status_code=404, detail="Lecture or raw transcript not found")

    cleaned = gemini_service.filter_transcript(
        raw_transcript=lecture.transcript.raw_transcript,
        custom_instructions=request.custom_instructions,
    )
    updated = crud_lecture.update_filtered_transcript(db, lecture.id, cleaned)
    return updated


@router.post("/{lecture_id}/generate-notes", response_model=LectureNoteOut)
def re_generate_notes(
    lecture_id: int,
    request: GenerateNotesRequest,
    db: Session = Depends(get_db),
):
    """Re-generate lecture notes from the filtered transcript with custom style/focus."""
    lecture = crud_lecture.get_lecture(db, lecture_id)
    if not lecture or not lecture.transcript:
        raise HTTPException(status_code=404, detail="Lecture or transcript not found")

    transcript_to_use = (
        lecture.transcript.filtered_transcript or lecture.transcript.raw_transcript
    )
    data = gemini_service.generate_lecture_notes(
        filtered_transcript=transcript_to_use,
        lecture_title=lecture.title,
        format_style=request.format_style,
        custom_focus=request.custom_focus,
    )

    notes = crud_lecture.upsert_lecture_notes(
        db=db,
        lecture_id=lecture.id,
        title=f"Study Notes: {lecture.title}",
        summary=data.get("summary", ""),
        structured_notes=data.get("structured_notes", ""),
        key_concepts=data.get("key_concepts", []),
        study_questions=data.get("study_questions", []),
    )
    return notes


@router.delete("/{lecture_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lecture(
    lecture_id: int,
    db: Session = Depends(get_db),
):
    """Delete a lecture, its transcript, notes, and local media file."""
    lecture = crud_lecture.get_lecture(db, lecture_id)
    if not lecture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lecture not found")

    if lecture.file_path:
        video_service.cleanup_file(lecture.file_path)

    crud_lecture.delete_lecture(db, lecture)
