import sys
from pathlib import Path


def base_path() -> Path:
    """
    Retorna o diretório base do app.
    - Rodando via Python: raiz do projeto
    - Rodando via .exe (PyInstaller): diretório temporário de extração (_MEIPASS)
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


def data_path() -> Path:
    """
    Retorna o diretório onde ficam dados mutáveis (banco, themes.json editável).
    Ao contrário do base_path, este diretório persiste entre execuções.
    - .exe: pasta ao lado do executável
    - Python: raiz do projeto
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent
