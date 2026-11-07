from pathlib import Path
import os

APP_VERSION = "0.4.0"
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "nexus.db"
FRONTEND_DIR = ROOT / "frontend"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("NEXUS_MODEL", "qwen2.5:3b")
USER_AGENT = "NexusAIResearchBot/1.0 (+local personal research; respects robots.txt)"
DATA_DIR.mkdir(exist_ok=True)
