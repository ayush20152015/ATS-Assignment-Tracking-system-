"""Central configuration for gradebot. Everything is overridable by environment variable."""
import os


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


# --- Sarvam (speech + language models) -------------------------------------
SARVAM_API_KEY = _env("SARVAM_API_KEY")
SARVAM_BASE_URL = _env("SARVAM_BASE_URL", "https://api.sarvam.ai")

# Speech-to-text model (saaras:v3 or saaras:v4)
STT_MODEL = _env("GRADEBOT_STT_MODEL", "saaras:v3")
# Image understanding model -> used to read and grade the handwritten sheets
VISION_MODEL = _env("GRADEBOT_VISION_MODEL", "gemma4")
# Text model -> structures the rubric and can re-write feedback in Hindi
TEXT_MODEL = _env("GRADEBOT_TEXT_MODEL", "gemma4")

# The synchronous speech-to-text REST endpoint accepts at most 30s per request.
STT_MAX_SECONDS = 30

# --- Google Classroom (only needed for --live) ------------------------------
CLASSROOM_CLIENT_SECRET = _env("GRADEBOT_CLASSROOM_CLIENT_SECRET", "client_secret.json")
CLASSROOM_TOKEN_FILE = _env("GRADEBOT_CLASSROOM_TOKEN", "token.json")
CLASSROOM_SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students",
    "https://www.googleapis.com/auth/classroom.coursework.students.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
