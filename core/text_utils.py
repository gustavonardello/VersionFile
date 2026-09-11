"""Normalização de texto usada nas buscas da interface."""
import unicodedata


def normalizar_busca(texto: str) -> str:
    decomposicao = unicodedata.normalize("NFKD", texto or "")
    sem_acentos = "".join(c for c in decomposicao if not unicodedata.combining(c))
    return sem_acentos.casefold()
