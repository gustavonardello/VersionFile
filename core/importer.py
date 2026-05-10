from pathlib import Path
from dataclasses import dataclass, field


EXTENSOES_VALIDAS = {".txt", ".lsp", ".srule", ".rule"}


@dataclass
class ArquivoRegra:
    caminho: Path
    numero: str       # nome do arquivo sem extensão
    descricao: str = ""


@dataclass
class ItemProjeto:
    nome: str
    tipo: str         # 'DID' ou 'Projeto'
    regras: list[ArquivoRegra] = field(default_factory=list)


@dataclass
class ItemCliente:
    nome: str
    projetos: list[ItemProjeto] = field(default_factory=list)


def _inferir_tipo(nome: str) -> str:
    """Heurística simples: pastas com 'DID' no nome são DID, demais são Projeto."""
    return "DID" if "did" in nome.lower() else "Projeto"


def _ler_arquivo(caminho: Path) -> str:
    """Lê um arquivo tentando UTF-8 primeiro, depois latin-1 como fallback."""
    try:
        return caminho.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return caminho.read_text(encoding="latin-1")


def escanear_pasta(raiz: Path) -> list[ItemCliente]:
    """
    Escaneia estrutura de pastas de forma flexível:
      - 3 níveis: raiz / cliente / projeto / arquivo
      - 2 níveis: raiz / projeto / arquivo  (cliente = nome da pasta raiz)
      - 1 nível:  raiz / arquivo            (cliente e projeto = nome da pasta raiz)
    Retorna lista de ItemCliente com a hierarquia encontrada.
    """
    clientes: list[ItemCliente] = []

    # Tenta estrutura de 3 níveis (padrão)
    for pasta_cliente in sorted(raiz.iterdir()):
        if not pasta_cliente.is_dir():
            continue

        cliente = ItemCliente(nome=pasta_cliente.name)

        for pasta_proj in sorted(pasta_cliente.iterdir()):
            if not pasta_proj.is_dir():
                continue

            projeto = ItemProjeto(
                nome=pasta_proj.name,
                tipo=_inferir_tipo(pasta_proj.name),
            )

            for arquivo in sorted(pasta_proj.iterdir()):
                if arquivo.is_file() and arquivo.suffix.lower() in EXTENSOES_VALIDAS:
                    projeto.regras.append(ArquivoRegra(
                        caminho=arquivo,
                        numero=arquivo.stem,
                    ))

            if projeto.regras:
                cliente.projetos.append(projeto)

        if cliente.projetos:
            clientes.append(cliente)

    if clientes:
        return clientes

    # Fallback: estrutura de 2 níveis (raiz / projeto / arquivo)
    cliente_fallback = ItemCliente(nome=raiz.name)
    for pasta_proj in sorted(raiz.iterdir()):
        if not pasta_proj.is_dir():
            continue

        projeto = ItemProjeto(
            nome=pasta_proj.name,
            tipo=_inferir_tipo(pasta_proj.name),
        )

        for arquivo in sorted(pasta_proj.iterdir()):
            if arquivo.is_file() and arquivo.suffix.lower() in EXTENSOES_VALIDAS:
                projeto.regras.append(ArquivoRegra(
                    caminho=arquivo,
                    numero=arquivo.stem,
                ))

        if projeto.regras:
            cliente_fallback.projetos.append(projeto)

    if cliente_fallback.projetos:
        return [cliente_fallback]

    # Fallback: estrutura de 1 nível (raiz / arquivo)
    projeto_fallback = ItemProjeto(nome=raiz.name, tipo=_inferir_tipo(raiz.name))
    for arquivo in sorted(raiz.iterdir()):
        if arquivo.is_file() and arquivo.suffix.lower() in EXTENSOES_VALIDAS:
            projeto_fallback.regras.append(ArquivoRegra(
                caminho=arquivo,
                numero=arquivo.stem,
            ))

    if projeto_fallback.regras:
        return [ItemCliente(nome=raiz.name, projetos=[projeto_fallback])]

    return []


def importar_para_banco(conn, clientes: list[ItemCliente], notas: str = "Importação inicial") -> dict:
    """
    Insere toda a hierarquia no banco.
    Pula entradas que já existem (mesmo nome de cliente+projeto / mesmo número de regra).
    Retorna contagem: {'clientes': N, 'projetos': N, 'regras': N, 'pulados': N}
    """
    import database.models as M

    contagem = {"clientes": 0, "projetos": 0, "regras": 0, "pulados": 0}

    for item_c in clientes:
        row = conn.execute(
            "SELECT id FROM clientes WHERE nome = ?", (item_c.nome,)
        ).fetchone()
        if row:
            cliente_id = row["id"]
        else:
            c = M.criar_cliente(conn, item_c.nome)
            cliente_id = c.id
            contagem["clientes"] += 1

        for item_p in item_c.projetos:
            row = conn.execute(
                "SELECT id FROM projetos WHERE cliente_id = ? AND nome = ?",
                (cliente_id, item_p.nome),
            ).fetchone()
            if row:
                projeto_id = row["id"]
            else:
                p = M.criar_projeto(conn, cliente_id, item_p.nome, item_p.tipo)
                projeto_id = p.id
                contagem["projetos"] += 1

            for arq in item_p.regras:
                row = conn.execute(
                    "SELECT id FROM regras WHERE projeto_id = ? AND numero = ?",
                    (projeto_id, arq.numero),
                ).fetchone()
                if row:
                    contagem["pulados"] += 1
                    continue

                regra = M.criar_regra(conn, projeto_id, arq.numero, arq.descricao)
                conteudo = _ler_arquivo(arq.caminho)
                M.criar_versao(conn, regra.id, conteudo, notas)
                contagem["regras"] += 1

    return contagem
