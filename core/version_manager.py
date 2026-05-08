import difflib
from database.models import (
    listar_versoes, criar_versao, salvar_conteudo_versao,
    atualizar_versao, definir_versao_atual, deletar_versao,
)


def detectar_tipo(conteudo_novo: str, conteudo_anterior: str) -> str:
    """
    Analisa o diff entre dois conteúdos e sugere o tipo da versão:
      - Sem anterior ou anterior vazio  → Criação
      - Até 20% das linhas alteradas   → Correção
      - 20% a 60%                      → Melhoria
      - Acima de 60%                   → Refatoração
    """
    if not conteudo_anterior.strip():
        return "Criação"

    linhas_ant = conteudo_anterior.splitlines()
    linhas_nov = conteudo_novo.splitlines()
    total = max(len(linhas_ant), len(linhas_nov), 1)

    matcher = difflib.SequenceMatcher(None, linhas_ant, linhas_nov, autojunk=False)
    alteradas = sum(
        max(i2 - i1, j2 - j1)
        for op, i1, i2, j1, j2 in matcher.get_opcodes()
        if op != "equal"
    )
    pct = alteradas / total

    if pct <= 0.20:
        return "Correção"
    elif pct <= 0.60:
        return "Melhoria"
    else:
        return "Refatoração"


def sugerir_tipo_para_regra(conn, regra_id: int, conteudo_novo: str) -> str:
    """Retorna o tipo sugerido comparando com a versão mais recente da regra."""
    versoes = listar_versoes(conn, regra_id)
    if not versoes:
        return "Criação"
    return detectar_tipo(conteudo_novo, versoes[0].conteudo)


def nova_versao_de_arquivo(conn, regra_id: int, caminho: str, notas: str = "", tipo: str = "") -> object:
    """Cria uma nova versão importando o conteúdo de um arquivo .txt/.lsp."""
    with open(caminho, "r", encoding="utf-8", errors="replace") as f:
        conteudo = f.read()
    tipo_final = tipo or sugerir_tipo_para_regra(conn, regra_id, conteudo)
    return criar_versao(conn, regra_id, conteudo, notas, tipo_final)


def diff_versoes(conn, regra_id: int, num_a: int, num_b: int) -> list[str]:
    """Retorna unified diff entre versão num_a e num_b."""
    versoes = {v.numero: v for v in listar_versoes(conn, regra_id)}
    v_a = versoes.get(num_a)
    v_b = versoes.get(num_b)
    if not v_a or not v_b:
        return []

    linhas_a = v_a.conteudo.splitlines(keepends=True)
    linhas_b = v_b.conteudo.splitlines(keepends=True)

    return list(difflib.unified_diff(
        linhas_a, linhas_b,
        fromfile=f"v{num_a}",
        tofile=f"v{num_b}",
        lineterm="",
    ))
