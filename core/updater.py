"""
Verificação de atualização contra o GitHub Releases.

Consulta a release mais recente do repositório e compara com a versão local.
Nunca lança exceção que derrube o app — qualquer erro retorna None.
"""

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path

from core.paths import data_path
from core.version import __version__


@dataclass
class InfoAtualizacao:
    versao: str
    url_release: str
    url_download: str
    tamanho_bytes: int
    notas: str


_CACHE_PATH = None  # inicializado sob demanda


def _cache_path() -> Path:
    global _CACHE_PATH
    if _CACHE_PATH is None:
        _CACHE_PATH = data_path() / "config" / "update_check.json"
    return _CACHE_PATH


def _parse_versao(tag: str) -> tuple[int, ...] | None:
    """Converte string 'x.y.z' em tupla de ints. Retorna None se inválido."""
    tag = tag.lstrip("vV")
    partes = tag.split(".")
    try:
        return tuple(int(p) for p in partes)
    except (ValueError, TypeError):
        return None


def _deve_verificar() -> bool:
    """Retorna True se já passaram mais de 20 horas desde a última checagem."""
    caminho = _cache_path()
    if not caminho.exists():
        return True
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        ultima = dados.get("ultima_checagem", 0)
        return (time.time() - ultima) > 20 * 3600
    except (json.JSONDecodeError, OSError, KeyError):
        return True


def _salvar_cache():
    """Grava o timestamp da checagem atual."""
    caminho = _cache_path()
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(
            json.dumps({"ultima_checagem": time.time()}),
            encoding="utf-8",
        )
    except OSError:
        pass  # não impede o funcionamento do app


def verificar_atualizacao(
    repo: str = "gustavonardello/VersionFile",
    forcar: bool = False,
) -> InfoAtualizacao | None:
    """
    Consulta a release mais recente do GitHub e retorna InfoAtualizacao se
    houver versão mais nova com um asset *Setup.exe, ou None caso contrário.

    Se `forcar` for True, ignora o cache de 20 h (útil para testes).
    Nunca lança exceção — qualquer falha retorna None silenciosamente.
    """
    try:
        if not forcar and not _deve_verificar():
            return None

        url = f"https://api.github.com/repos/{repo}/releases/latest"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "VersionFile-Updater",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            dados = json.loads(resp.read().decode("utf-8"))

        if not forcar:
            _salvar_cache()

        tag_remota = dados.get("tag_name", "")
        versao_remota = _parse_versao(tag_remota)
        versao_local = _parse_versao(__version__)

        if versao_remota is None or versao_local is None:
            return None

        if versao_remota <= versao_local:
            return None

        # Procura asset cujo nome termine em "Setup.exe"
        assets = dados.get("assets", [])
        asset_setup = None
        for asset in assets:
            nome = asset.get("name", "")
            if nome.endswith("Setup.exe"):
                asset_setup = asset
                break

        if asset_setup is None:
            return None

        return InfoAtualizacao(
            versao=tag_remota.lstrip("vV"),
            url_release=dados.get("html_url", ""),
            url_download=asset_setup.get("browser_download_url", ""),
            tamanho_bytes=asset_setup.get("size", 0),
            notas=dados.get("body", "") or "",
        )

    except Exception:
        return None
