"""
Migração dos dados do local antigo (pasta do .exe) para o novo
(%LOCALAPPDATA%\\VersionFile).

Regra que vale para todo este módulo: **nada é movido, sobrescrito ou apagado.**
Arquivos são sempre copiados e a origem permanece intacta, de modo que uma
migração malsucedida nunca custe dados ao usuário.
"""

import shutil
import sqlite3
from enum import Enum, auto
from pathlib import Path

from core.paths import data_path, legacy_data_path

NOME_BANCO = "versionfile.db"
ARQUIVOS_CONFIG = ("themes.json", "ui_prefs.json", "tree_state.json")

# Tabelas que um banco do VersionFile obrigatoriamente possui. Usadas para
# validar o arquivo que o usuário aponta manualmente.
TABELAS_ESPERADAS = {"clientes", "projetos", "regras", "versoes"}


class Estado(Enum):
    NAO_SE_APLICA = auto()      # rodando via Python: o local nunca mudou
    JA_NO_LUGAR = auto()        # já existe banco no local novo
    LEGADO_ENCONTRADO = auto()  # existe banco na pasta do .exe
    NADA_ENCONTRADO = auto()    # usuário novo, ou .exe rodando de outra pasta


def banco_atual() -> Path:
    """Caminho do banco no local definitivo."""
    return data_path() / NOME_BANCO


def banco_legado() -> Path | None:
    """Caminho do banco no local antigo, ou None se não se aplica."""
    legado = legacy_data_path()
    return None if legado is None else legado / NOME_BANCO


def detectar_estado() -> Estado:
    """Descobre o que precisa acontecer antes de abrir o banco."""
    if legacy_data_path() is None:
        return Estado.NAO_SE_APLICA

    if banco_atual().exists():
        return Estado.JA_NO_LUGAR

    legado = banco_legado()
    if legado is not None and legado.exists():
        return Estado.LEGADO_ENCONTRADO

    return Estado.NADA_ENCONTRADO


def eh_banco_versionfile(caminho: Path) -> bool:
    """
    Verifica se o arquivo apontado é mesmo um banco do VersionFile, abrindo-o
    em modo somente-leitura para não alterar nada.
    """
    if not caminho.is_file():
        return False

    try:
        uri = f"{caminho.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    except (sqlite3.Error, ValueError, OSError):
        return False

    try:
        nomes = {
            linha[0]
            for linha in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    except sqlite3.Error:
        return False
    finally:
        conn.close()

    return TABELAS_ESPERADAS.issubset(nomes)


def importar_de(origem_banco: Path) -> list[str]:
    """
    Copia o banco indicado — e os configs que estiverem ao lado dele — para o
    local definitivo. Retorna a lista de arquivos copiados.

    Nunca sobrescreve arquivo já existente no destino e nunca altera a origem.
    """
    destino_dir = data_path()
    (destino_dir / "config").mkdir(parents=True, exist_ok=True)

    copiados: list[str] = []

    destino_banco = destino_dir / NOME_BANCO
    if not destino_banco.exists():
        shutil.copy2(origem_banco, destino_banco)
        copiados.append(NOME_BANCO)

    origem_config = origem_banco.parent / "config"
    for nome in ARQUIVOS_CONFIG:
        origem_arq = origem_config / nome
        destino_arq = destino_dir / "config" / nome
        if origem_arq.exists() and not destino_arq.exists():
            shutil.copy2(origem_arq, destino_arq)
            copiados.append(f"config/{nome}")

    return copiados
