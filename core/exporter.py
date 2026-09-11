"""Nomes portáveis e gravação de exportações sem sobrescrever arquivos."""
import re
from pathlib import Path


def sanitizar_nome(texto: str) -> str:
    nome = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", texto).strip().rstrip(". ")
    if not nome:
        nome = "sem_nome"
    reservado = nome.split(".")[0].upper()
    if reservado in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} or re.fullmatch(
        r"(?:COM|LPT)[1-9¹²³]", reservado
    ):
        nome = "_" + nome
    return nome


def exportar_arquivo(raiz: Path, pastas: list[str], nome: str, conteudo: str) -> Path:
    raiz = raiz.resolve()
    pasta = raiz.joinpath(*(sanitizar_nome(p) for p in pastas)).resolve()
    if not pasta.is_relative_to(raiz):
        raise ValueError("A pasta de exportação está fora do destino selecionado.")
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / sanitizar_nome(nome)
    indice = 1
    while True:
        candidato = arquivo if indice == 1 else arquivo.with_name(
            f"{arquivo.stem} ({indice}){arquivo.suffix}"
        )
        try:
            with candidato.open("x", encoding="utf-8") as saida:
                saida.write(conteudo)
            return candidato
        except FileExistsError:
            indice += 1
