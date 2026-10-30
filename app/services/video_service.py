# app/services/video_service.py
import os
import re
import uuid
from pathlib import Path
from typing import Tuple

import aiofiles
from fastapi import HTTPException, UploadFile, status
import yt_dlp

from app.config import settings

ALLOWED_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".mov",
    ".webm",
    ".avi",
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
}


def ensure_upload_dir() -> Path:
    upload_path = Path(settings.UPLOAD_DIR)
    upload_path.mkdir(parents=True, exist_ok=True)
    return upload_path


def sanitize_filename(filename: str) -> str:
    # Remove unsafe characters
    clean_name = re.sub(r"[^\w\-.]", "_", filename)
    return clean_name


async def save_uploaded_file(file: UploadFile) -> Tuple[str, str]:
    """
    Saves an uploaded video or audio file to disk.
    Returns (saved_file_path, original_filename_stem).
    """
    ext = Path(file.filename or "media.mp4").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Supported formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    upload_dir = ensure_upload_dir()
    unique_id = uuid.uuid4().hex[:12]
    base_name = sanitize_filename(Path(file.filename or "lecture").stem)
    filename = f"{base_name}_{unique_id}{ext}"
    dest_path = upload_dir / filename

    max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    bytes_written = 0

    async with aiofiles.open(dest_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):  # 1MB chunks
            bytes_written += len(chunk)
            if bytes_written > max_size_bytes:
                # Clean up partial file
                if dest_path.exists():
                    dest_path.unlink()
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds maximum upload size of {settings.MAX_UPLOAD_SIZE_MB}MB",
                )
            await buffer.write(chunk)

    return str(dest_path.resolve()), base_name.replace("_", " ")


def get_ffmpeg_path() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def extract_audio(input_media_path: str) -> str:
    """
    Extracts high-quality MP3 audio from a video or audio file.
    If already a clean MP3, returns it directly.
    For all videos (MP4, WebM, MKV, MOV), converts to lightweight MP3 for fast and reliable Gemini transcription.
    """
    import subprocess

    ext = Path(input_media_path).suffix.lower()
    if ext == ".mp3":
        return input_media_path

    output_path = str(Path(input_media_path).with_suffix(".mp3"))
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return output_path

    ffmpeg_exe = get_ffmpeg_path()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i",
        input_media_path,
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ab",
        "128k",
        "-ar",
        "44100",
        output_path,
    ]
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return output_path
    except Exception:
        # Fall back to original file if ffmpeg conversion encounters an issue
        return input_media_path


def download_youtube_media(url: str) -> Tuple[str, str]:
    """
    Downloads audio from a YouTube URL using yt-dlp and automatically extracts MP3 with bundled ffmpeg.
    Returns (file_path, video_title).
    """
    upload_dir = ensure_upload_dir()
    unique_id = uuid.uuid4().hex[:12]
    output_template = str(upload_dir / f"yt_%(id)s_{unique_id}.%(ext)s")
    ffmpeg_exe = get_ffmpeg_path()

    ydl_opts = {
        "format": "bestaudio/best",
        "ffmpeg_location": ffmpeg_exe,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise ValueError("Could not extract video metadata from URL")

            title = info.get("title", "YouTube Lecture")
            base_file = ydl.prepare_filename(info)
            # The postprocessor changes the extension to .mp3
            mp3_file = str(Path(base_file).with_suffix(".mp3"))
            if os.path.exists(mp3_file):
                return str(Path(mp3_file).resolve()), title

            # Check if any matching yt_ file was created
            matches = list(upload_dir.glob(f"yt_{info.get('id')}*.mp3"))
            if matches:
                return str(matches[0].resolve()), title

            return str(Path(base_file).resolve()), title
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to download YouTube video: {str(e)}",
        )


def cleanup_file(file_path: str | None) -> None:
    """Removes a file from disk if it exists."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
