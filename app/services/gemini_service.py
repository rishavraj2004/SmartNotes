# app/services/gemini_service.py
import json
import logging
import os
import time
from typing import Any, Tuple

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)


class KeyConceptItem(BaseModel):
    concept: str = Field(description="Name or title of the key term or core concept")
    explanation: str = Field(description="Clear, in-depth explanation and significance")


class StudyQuestionItem(BaseModel):
    question: str = Field(description="Exam-style or active recall review question")
    answer: str = Field(description="Comprehensive answer with explanation")


class GeneratedNotesSchema(BaseModel):
    summary: str = Field(
        description="A 2-3 paragraph executive summary synthesizing the whole lecture"
    )
    key_concepts: list[KeyConceptItem] = Field(
        description="List of primary terms, concepts, and definitions taught in the lecture"
    )
    structured_notes: str = Field(
        description="Comprehensive, beautifully formatted Markdown notes with hierarchy, headers, bullet points, code/formula blocks, and critical takeaways"
    )
    study_questions: list[StudyQuestionItem] = Field(
        description="High-yield flashcard questions and answers for self-study and exam prep"
    )


def get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or settings.GEMINI_API_KEY
    if not key or not key.strip():
        from dotenv import dotenv_values
        env_dict = dotenv_values(".env")
        key = env_dict.get("GEMINI_API_KEY", "")
    return (key or "").strip()


def get_model() -> str:
    from dotenv import dotenv_values
    env_dict = dotenv_values(".env")
    model = env_dict.get("GEMINI_MODEL") or os.environ.get("GEMINI_MODEL") or settings.GEMINI_MODEL
    return (model or "gemini-flash-latest").strip()


from google.genai.errors import ClientError, ServerError


def execute_with_retry(fn, max_retries: int = 3, initial_delay: float = 2.0):
    """
    Executes a Gemini call with exponential backoff on 503 / 429 server errors.
    """
    delay = initial_delay
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except (ServerError, ClientError) as e:
            err_str = str(e)
            is_recoverable = (
                "503" in err_str
                or "429" in err_str
                or "RESOURCE_EXHAUSTED" in err_str
                or "UNAVAILABLE" in err_str
            )
            if is_recoverable and attempt < max_retries:
                logger.warning(
                    f"Gemini API rate limit or high demand ({err_str[:120]}...). Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})..."
                )
                time.sleep(delay)
                delay *= 2
            else:
                raise


def get_client() -> genai.Client:
    api_key = get_api_key()
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Please add your Gemini API key to the .env file "
            "or set the GEMINI_API_KEY environment variable. Get a free key at https://aistudio.google.com/"
        )
    return genai.Client(api_key=api_key)


def transcribe_media(file_path: str) -> str:
    """
    Uploads a media file (video/audio) to Gemini Files API, waits for processing,
    and prompts Gemini to produce a verbatim lecture transcript with timestamps.
    """
    client = get_client()
    logger.info(f"Uploading media file to Gemini: {file_path}")
    uploaded_file = client.files.upload(file=file_path)

    try:
        # Wait for file processing if needed
        max_wait = 180  # up to 3 minutes for large videos
        elapsed = 0
        while uploaded_file.state.name == "PROCESSING":
            if elapsed >= max_wait:
                raise TimeoutError("Media file processing timed out on Gemini API")
            time.sleep(3)
            elapsed += 3
            uploaded_file = client.files.get(name=uploaded_file.name)

        if uploaded_file.state.name == "FAILED":
            err_details = getattr(uploaded_file, "error", None) or "File processing error"
            raise RuntimeError(f"Gemini failed to process media file: {err_details}")

        model_name = get_model()
        logger.info(f"File active on Gemini. Generating transcript with {model_name}...")

        prompt = (
            "You are a professional lecture transcriber. Accurately transcribe all spoken dialogue "
            "from this audio/video recording.\n\n"
            "Transcription Instructions:\n"
            "1. Transcribe the speech completely and faithfully.\n"
            "2. Insert chronological timestamps in [MM:SS] format at regular intervals and topic transitions.\n"
            "3. Identify speaker shifts when audible (e.g. Instructor:, Student:).\n"
            "4. Carefully preserve all technical jargon, formulas, scientific nomenclature, and programming terminology.\n"
            "5. Output purely the transcript without introductory or meta commentary."
        )

        response = execute_with_retry(
            lambda: client.models.generate_content(
                model=model_name,
                contents=[uploaded_file, prompt],
            )
        )

        raw_transcript = response.text or ""
        return raw_transcript.strip()

    finally:
        # Always clean up the uploaded file on Gemini storage
        try:
            client.files.delete(name=uploaded_file.name)
            logger.info(f"Deleted remote Gemini file: {uploaded_file.name}")
        except Exception as e:
            logger.warning(f"Could not delete Gemini remote file: {e}")


def filter_transcript(raw_transcript: str, custom_instructions: str | None = None) -> str:
    """
    Cleans and filters a raw lecture transcript:
    - Eliminates filler words, stutters, false starts
    - Removes mic checks, banter, and off-topic classroom chatter
    - Polishes grammar and clarifies domain terminology
    - Segments the transcript into logical lecture chapters with timestamp anchors
    """
    client = get_client()

    base_prompt = (
        "You are an expert academic editor specializing in university lecture transcripts.\n"
        "Your task is to filter, clean, and organize the following raw lecture transcript into "
        "a clean, professional, readable lecture transcript.\n\n"
        "Editing Rules:\n"
        "1. ELIMINATE VERBAL FILLERS: Remove filler sounds and words (um, uh, like, you know, basically, so yeah, right?, okay?), repetitive stammers, and false starts.\n"
        "2. REMOVE OFF-TOPIC INTERRUPTIONS: Strip out mic checks, audio troubleshooting, casual banter, announcements about lost items, or unrelated administrative tangents.\n"
        "3. GRAMMATICAL SMOOTHING: Turn fragmented spoken phrases into clean, articulate sentences while strictly preserving the speaker's original intent and meaning.\n"
        "4. PRESERVE INTELLECTUAL DEPTH: Retain all course explanations, proofs, analogies, examples, academic Q&A, and technical details.\n"
        "5. DOMAIN ACCURACY: Fix phonetic misinterpretations of technical vocabulary, code names, or equations.\n"
        "6. STRUCTURE & TIMESTAMPS: Organize the text into coherent sections with Markdown headings (## Section Title) and retain the timestamp reference [MM:SS] at the start of each section.\n"
    )

    if custom_instructions:
        base_prompt += f"\nAdditional User Instructions:\n{custom_instructions}\n"

    base_prompt += f"\n\n--- RAW TRANSCRIPT ---\n{raw_transcript}\n--- END RAW TRANSCRIPT ---"

    response = execute_with_retry(
        lambda: client.models.generate_content(
            model=get_model(),
            contents=base_prompt,
        )
    )

    return (response.text or "").strip()


def generate_lecture_notes(
    filtered_transcript: str,
    lecture_title: str,
    format_style: str = "comprehensive",
    custom_focus: str | None = None,
) -> dict[str, Any]:
    """
    Generates structured study notes from a filtered transcript:
    - Executive summary
    - Key concepts & glossary
    - Structured Markdown notes (with headings, code/formula blocks, takeaways)
    - Self-study questions & flashcards
    """
    client = get_client()

    prompt = (
        f"You are a master university professor and educational note-taking specialist.\n"
        f"Analyze the following filtered lecture transcript for the lecture '{lecture_title}' and generate "
        f"high-yield, structured study notes.\n\n"
        f"Note Formatting Style: {format_style}\n"
    )

    if custom_focus:
        prompt += f"Special Focus: {custom_focus}\n\n"

    prompt += (
        "Generate a structured JSON output matching the required schema with:\n"
        "1. 'summary': A coherent 2-3 paragraph executive summary synthesizing the central themes.\n"
        "2. 'key_concepts': An array of key concepts ({concept, explanation}) for every major term or theorem introduced.\n"
        "3. 'structured_notes': Beautifully formatted, deep Markdown notes organized with clear `# Title`, `## Headings`, `### Subheadings`, bullet points, code or mathematical blocks (if applicable), practical examples, and 'Key Takeaways' callout blocks.\n"
        "4. 'study_questions': An array of 5-10 high-yield questions ({question, answer}) designed for active recall, flashcards, or exam prep.\n\n"
        f"--- FILTERED TRANSCRIPT ---\n{filtered_transcript}\n--- END TRANSCRIPT ---"
    )

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=GeneratedNotesSchema,
        temperature=0.3,
    )

    response = execute_with_retry(
        lambda: client.models.generate_content(
            model=get_model(),
            contents=prompt,
            config=config,
        )
    )

    result_text = response.text or "{}"
    data = json.loads(result_text)
    return data
