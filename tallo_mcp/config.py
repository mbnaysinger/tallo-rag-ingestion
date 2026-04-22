import sys
from pathlib import Path

# Adiciona o diretório pai ao sys.path para importar config.py e pipeline/
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(dotenv_path=_REPO_ROOT / ".env")

from config import Settings, load_settings, REQUIRED_VARS  # noqa: E402


def load_mcp_settings() -> Settings:
    """Carrega Settings a partir do .env na raiz do repositório (diretório pai de mcp/).
    Levanta EnvironmentError listando variáveis ausentes se obrigatórias faltarem."""
    return load_settings()
