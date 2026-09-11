"""
Verificação de atualização contra o GitHub Releases.

Consulta a release mais recente do repositório e compara com a versão local.
Nunca lança exceção que derrube o app — qualquer erro retorna None.
"""

import json
import hashlib
import re
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from core.paths import data_path
from core.version import __version__


@dataclass
class InfoAtualizacao:
    versao: str
    url_release: str
    url_download: str
    url_sha256: str
    tamanho_bytes: int
    notas: str


class ErroAtualizacao(Exception):
    """Erro durante consulta, download ou instalação de atualização."""


_CACHE_PATH = None  # inicializado sob demanda
_INTERVALO_CACHE_SEGUNDOS = 60 * 60


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
    """Retorna True se já passou uma hora desde a última checagem sem update."""
    caminho = _cache_path()
    if not caminho.exists():
        return True
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        ultima = dados.get("ultima_checagem", 0)
        return (time.time() - ultima) > _INTERVALO_CACHE_SEGUNDOS
    except (json.JSONDecodeError, OSError, KeyError, TypeError, AttributeError):
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


def _limpar_cache():
    """Não deixa uma atualização disponível ser ocultada na próxima abertura."""
    try:
        _cache_path().unlink(missing_ok=True)
    except OSError:
        pass


def verificar_atualizacao(
    repo: str = "gustavonardello/VersionFile",
    forcar: bool = False,
    propagar_erros: bool = False,
) -> InfoAtualizacao | None:
    """
    Consulta a release mais recente do GitHub e retorna InfoAtualizacao se
    houver versão mais nova com um asset *Setup.exe, ou None caso contrário.

    Se `forcar` for True, ignora o cache de uma hora. Quando `propagar_erros`
    é True, falhas de consulta são convertidas em ErroAtualizacao para que uma
    verificação manual possa informar o usuário.
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

        tag_remota = dados.get("tag_name", "")
        versao_remota = _parse_versao(tag_remota)
        versao_local = _parse_versao(__version__)

        if versao_remota is None or versao_local is None:
            _salvar_cache()
            return None

        if versao_remota <= versao_local:
            _salvar_cache()
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
            _salvar_cache()
            return None
        nome_checksum = asset_setup.get("name", "") + ".sha256"
        asset_checksum = next((a for a in assets if a.get("name") == nome_checksum), None)
        if asset_checksum is None:
            _salvar_cache()
            return None

        info = InfoAtualizacao(
            versao=tag_remota.lstrip("vV"),
            url_release=dados.get("html_url", ""),
            url_download=asset_setup.get("browser_download_url", ""),
            url_sha256=asset_checksum.get("browser_download_url", ""),
            tamanho_bytes=asset_setup.get("size", 0),
            notas=dados.get("body", "") or "",
        )
        _limpar_cache()
        return info

    except Exception as e:
        if propagar_erros:
            raise ErroAtualizacao(f"Não foi possível consultar as atualizações: {e}") from e
        return None


def baixar_e_instalar(
    update_info: InfoAtualizacao,
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    """
    Baixa o instalador da atualização e o executa em modo silencioso.

    O instalador é disparado como processo destacado (DETACHED_PROCESS)
    para que sobreviva ao fechamento do app atual. A função NÃO chama
    sys.exit — quem chamou deve fechar o app no momento apropriado
    (salvando edições pendentes via salvar_se_pendente()).

    Levanta ErroAtualizacao se qualquer etapa falhar.
    """
    url = update_info.url_download
    tamanho_esperado = update_info.tamanho_bytes

    if not url or not update_info.url_sha256:
        raise ErroAtualizacao("A release não contém instalador e checksum válidos.")
    for endereco in (url, update_info.url_sha256):
        parsed = urlparse(endereco)
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            raise ErroAtualizacao("A atualização aponta para uma origem não confiável.")

    try:
        req_hash = urllib.request.Request(
            update_info.url_sha256, headers={"User-Agent": "VersionFile-Updater"}
        )
        with urllib.request.urlopen(req_hash, timeout=10) as resposta:
            texto_hash = resposta.read(4096).decode("ascii", errors="strict")
        correspondencia = re.search(r"(?i)\b([0-9a-f]{64})\b", texto_hash)
        if not correspondencia:
            raise ValueError("checksum SHA-256 inválido")
        hash_esperado = correspondencia.group(1).lower()
    except Exception as e:
        raise ErroAtualizacao(f"Falha ao obter checksum da atualização: {e}") from e

    # -- Download em streaming para pasta temporária ----------------------
    nome_arquivo = f"VersionFile-{update_info.versao}-Setup.exe"
    pasta_temporaria = Path(tempfile.mkdtemp(prefix="versionfile-update-"))
    destino = pasta_temporaria / nome_arquivo

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "VersionFile-Updater"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
    except Exception as e:
        try:
            pasta_temporaria.rmdir()
        except OSError:
            pass
        raise ErroAtualizacao(f"Falha ao conectar para download: {e}") from e

    try:
        baixados = 0
        hash_real = hashlib.sha256()
        chunk_size = 64 * 1024  # 64 KB

        with open(destino, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                hash_real.update(chunk)
                baixados += len(chunk)
                if on_progress:
                    on_progress(baixados, tamanho_esperado)
    except Exception as e:
        # Remove arquivo parcial se o download falhou
        try:
            destino.unlink(missing_ok=True)
            pasta_temporaria.rmdir()
        except OSError:
            pass
        raise ErroAtualizacao(f"Falha durante o download: {e}") from e
    finally:
        resp.close()

    # -- Verificação de integridade (tamanho) -----------------------------
    tamanho_real = destino.stat().st_size
    if tamanho_esperado > 0 and tamanho_real != tamanho_esperado:
        try:
            destino.unlink(missing_ok=True)
            pasta_temporaria.rmdir()
        except OSError:
            pass
        raise ErroAtualizacao(
            f"Tamanho do arquivo não confere: esperado {tamanho_esperado} "
            f"bytes, recebido {tamanho_real} bytes. Download corrompido."
        )
    if hash_real.hexdigest() != hash_esperado:
        try:
            destino.unlink(missing_ok=True)
            pasta_temporaria.rmdir()
        except OSError:
            pass
        raise ErroAtualizacao("O checksum SHA-256 do instalador não confere.")

    # -- Dispara o instalador como processo destacado ---------------------
    try:
        # CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS: o instalador
        # sobrevive ao fechamento do VersionFile.exe atual.
        flags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
        )
        subprocess.Popen(
            [str(destino), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
            close_fds=True,
            creationflags=flags,
        )
    except Exception as e:
        try:
            destino.unlink(missing_ok=True)
            pasta_temporaria.rmdir()
        except OSError:
            pass
        raise ErroAtualizacao(f"Falha ao iniciar o instalador: {e}") from e
