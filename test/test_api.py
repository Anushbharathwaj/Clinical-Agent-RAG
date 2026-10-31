from fastapi.testclient import TestClient
from types import SimpleNamespace
from unittest.mock import patch

# Import your FastAPI app instance from your main file (change 'main' to your actual file name)
from app.main import app, settings 

client = TestClient(app)

def test_transcribe_endpoint_returns_openai_transcription():
    received_filename = []

    mock_client = SimpleNamespace(
        audio=SimpleNamespace(
            transcriptions=SimpleNamespace(
                create=lambda **kwargs: (
                    received_filename.append(kwargs["file"].name)
                    or SimpleNamespace(text="recognized words")
                )
            )
        )
    )

    with patch("app.main.OpenAI", return_value=mock_client), patch("app.main.auth"):
        response = client.post(
            "/api/transcribe",
            files={"file": ("voice.mp4", b"x" * 256, "audio/mp4")},
        )

    assert response.status_code == 200
    assert response.json() == {"text": "recognized words"}
    assert received_filename == ["voice.mp4"]


def test_speech_endpoint_returns_openai_audio():
    mock_client = SimpleNamespace(
        audio=SimpleNamespace(
            speech=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(content=b"speech audio")
            )
        )
    )

    with patch("app.main.OpenAI", return_value=mock_client), patch("app.main.auth"):
        response = client.post("/api/speech", json={"text": "Hello"})

    assert response.status_code == 200
    assert response.content == b"speech audio"
    assert response.headers["content-type"] == "audio/mpeg"


def test_transcribe_rejects_tiny_audio_before_openai_call():
    with patch("app.main.OpenAI") as openai, patch("app.main.auth"):
        response = client.post(
            "/api/transcribe",
            files={"file": ("voice.webm", b"x" * 110, "audio/webm")},
        )

    assert response.status_code == 400
    assert "No usable audio" in response.json()["detail"]
    openai.assert_not_called()


def test_chat_endpoint():
    # 1. Define headers (optional auth token and conversation ID)
    headers = {
        "Authorization": f"Bearer {settings.api_token}" if settings.api_token else "",
        "X-Conversation-ID": "test-thread-123"
    }

    # 2. Define the JSON request body matching ChatRequest
    payload = {
        "message": "Hello, can you explain what a skin patch is?",
        "history": [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello! How can I help you today?"}
        ],
        "image_data": None  # Set to a valid base64 data url if you want to test vision
    }

    print("Sending POST request to /api/chat...")

    # 3. Send the POST request to your FastAPI route
    response = client.post("/api/chat", json=payload, headers=headers)

    print(f"\nResponse Status Code: {response.status_code}")
    print("Response JSON Body:")
    print(response.json())

if __name__ == "__main__":
    test_chat_endpoint()