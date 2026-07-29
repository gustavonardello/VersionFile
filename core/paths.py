import os
import sys
from pathlib import Path

APP_NAME = "VersionFile"


def base_path() -> Path:
    """
    Retorna o diretório base do app (arquivos somente-leitura que vêm no pacote).
    - Rodando via Python: raiz do projeto
    - Rodando via .exe (PyInstaller): diretório temporário de extração (_MEIPASS)
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


def data_path() -> Path:
    """
    Retorna o diretório onde ficam dados mutáveis (banco, configs editáveis).

    - .exe: %LOCALAPPDATA%\\VersionFile — propositalmente FORA da pasta do
      programa, para que instalação, atualização e desinstalação nunca
      encostem nos dados do usuário.
    - Python: raiz do projeto (comportamento de desenvolvimento inalterado)
    """
    if not getattr(sys, "frozen", False):
        return Path(__file__).parent.parent

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def legacy_data_path() -> Path | None:
    """
    Local onde os dados ficavam antes da mudança para %LOCALAPPDATA%: a própria
    pasta do .exe.

    Retorna None quando rodando via Python, caso em que o local dos dados nunca
    mudou e não há nada a migrar.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return None
