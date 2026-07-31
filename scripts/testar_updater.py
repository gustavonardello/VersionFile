"""
Teste manual do core/updater.py contra o repositório real no GitHub.

Roda dois cenários:
  1. Simula versão local "1.0.0" → deve encontrar atualização (se existir release > 1.0.0)
  2. Simula versão local "9.9.9" → não deve encontrar nada

Uso:
  python scripts/testar_updater.py
"""

import sys
import os

# Adiciona a raiz do projeto ao path para imports funcionarem
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import core.updater as updater
import core.version as version


def testar(versao_simulada: str):
    """Executa verificar_atualizacao com uma versão local forjada."""
    original = version.__version__
    version.__version__ = versao_simulada
    # O updater importa __version__ no topo, então precisamos trocar lá também
    updater.__version__ = versao_simulada

    print(f"\n{'='*60}")
    print(f"  Versão local simulada: {versao_simulada}")
    print(f"{'='*60}")

    resultado = updater.verificar_atualizacao(forcar=True)

    if resultado is None:
        print("  Resultado: None (sem atualização disponível ou sem asset Setup.exe)")
    else:
        print(f"  Versao remota:  {resultado.versao}")
        print(f"  URL release:   {resultado.url_release}")
        print(f"  URL download:  {resultado.url_download}")
        print(f"  Tamanho:       {resultado.tamanho_bytes / (1024*1024):.1f} MB")
        print(f"  Notas:         {resultado.notas[:120]}...")

    # Restaura
    version.__version__ = original
    updater.__version__ = original

    return resultado


if __name__ == "__main__":
    print("Testando core/updater.py contra GitHub Releases real")
    print(f"Repositório: gustavonardello/VersionFile")

    # Cenário 1: versão antiga → deve encontrar update (se houver release com Setup.exe)
    r1 = testar("1.0.0")

    # Cenário 2: versão futura → nunca deve encontrar update
    r2 = testar("9.9.9")

    print(f"\n{'='*60}")
    print("  RESUMO")
    print(f"{'='*60}")

    ok1 = True  # r1 pode ser None se não há asset Setup.exe na release — isso é ok
    ok2 = r2 is None

    if r1 is not None:
        print(f"  1.0.0 -> encontrou v{r1.versao} OK")
    else:
        print(f"  1.0.0 -> None (sem asset Setup.exe na release, comportamento esperado)")

    if ok2:
        print(f"  9.9.9 -> None OK (correto, nao ha versao maior)")
    else:
        print(f"  9.9.9 -> FALHA! Retornou algo quando nao deveria: {r2}")

    sys.exit(0 if ok2 else 1)
