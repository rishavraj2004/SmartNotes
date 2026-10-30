# tests/test_lectures.py
import io
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine, SessionLocal
from app.crud import lecture as crud_lecture

client = TestClient(app)


def setup_module():
    import app.models
    Base.metadata.create_all(bind=engine)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_lecture_and_lifecycle():
    # 1. Upload a simulated audio file
    fake_audio_content = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"simulated audio lecture data" * 10
    files = {"file": ("intro_to_ai.mp3", io.BytesIO(fake_audio_content), "audio/mpeg")}
    data = {"title": "Introduction to Artificial Intelligence"}

    response = client.post("/api/v1/lectures/upload", files=files, data=data)
    assert response.status_code == 202
    res_data = response.json()
    lecture_id = res_data["id"]
    assert res_data["title"] == "Introduction to Artificial Intelligence"
    assert res_data["source_type"] == "upload"

    # 2. Get lecture details
    get_res = client.get(f"/api/v1/lectures/{lecture_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == lecture_id

    # 3. Simulate pipeline completion in DB
    db = SessionLocal()
    try:
        raw_text = (
            "[00:00] Lecturer: Um, hello everyone. Can you hear me? Uh, today we will discuss neural networks.\n"
            "[00:30] Like, basically, an artificial neuron computes a weighted sum of inputs and passes it through an activation function."
        )
        filtered_text = (
            "## Introduction to Neural Networks [00:00]\n"
            "Today we will discuss neural networks.\n\n"
            "## Artificial Neurons [00:30]\n"
            "An artificial neuron computes a weighted sum of inputs and passes it through an activation function."
        )
        crud_lecture.upsert_transcript(
            db=db,
            lecture_id=lecture_id,
            raw_transcript=raw_text,
            filtered_transcript=filtered_text,
        )

        crud_lecture.upsert_lecture_notes(
            db=db,
            lecture_id=lecture_id,
            title="Study Notes: Introduction to Artificial Intelligence",
            summary="A comprehensive overview of neural networks, exploring artificial neurons and activation functions.",
            structured_notes=(
                "# Neural Networks Architecture\n\n"
                "## 1. Fundamentals\n"
                "- Weighted sums aggregate multiple inputs.\n"
                "- Activation functions introduce non-linearity (e.g. ReLU, Sigmoid).\n"
            ),
            key_concepts=[
                {"concept": "Artificial Neuron", "explanation": "Mathematical model of biological neurons."},
                {"concept": "Activation Function", "explanation": "Function that transforms neuron input into output."}
            ],
            study_questions=[
                {"question": "What is the purpose of an activation function?", "answer": "To introduce non-linearity into the network."}
            ],
        )
    finally:
        db.close()

    # 4. Verify Transcript endpoint
    transcript_res = client.get(f"/api/v1/lectures/{lecture_id}/transcript")
    assert transcript_res.status_code == 200
    t_data = transcript_res.json()
    assert "artificial neuron computes" in t_data["filtered_transcript"]
    assert "[00:00]" in t_data["raw_transcript"]

    # 5. Verify Notes endpoint
    notes_res = client.get(f"/api/v1/lectures/{lecture_id}/notes")
    assert notes_res.status_code == 200
    n_data = notes_res.json()
    assert len(n_data["key_concepts"]) == 2
    assert len(n_data["study_questions"]) == 1
    assert "Artificial Neuron" in n_data["key_concepts"][0]["concept"]

    # 6. Verify Markdown Download endpoint
    md_res = client.get(f"/api/v1/lectures/{lecture_id}/notes/markdown")
    assert md_res.status_code == 200
    assert md_res.headers["content-type"].startswith("text/markdown")
    assert "# Study Notes: Introduction to Artificial Intelligence" in md_res.text
    assert "## Key Concepts Glossary" in md_res.text
    assert "## Practice & Review Questions" in md_res.text

    # 7. Delete lecture
    del_res = client.delete(f"/api/v1/lectures/{lecture_id}")
    assert del_res.status_code == 204

    # 8. Confirm deleted
    assert client.get(f"/api/v1/lectures/{lecture_id}").status_code == 404
