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
    if not raiz.is_dir():
        raise NotADirectoryError(f"Pasta não encontrada: {raiz}")

    clientes: dict[str, ItemCliente] = {}

    def arquivos_em(pasta: Path) -> list[ArquivoRegra]:
        return [
            ArquivoRegra(caminho=arquivo, numero=arquivo.stem)
            for arquivo in sorted(pasta.iterdir())
            if arquivo.is_file() and arquivo.suffix.lower() in EXTENSOES_VALIDAS
        ]

    def adicionar(cliente_nome: str, projeto_nome: str, arquivos: list[ArquivoRegra]):
        if not arquivos:
            return
        cliente = clientes.setdefault(cliente_nome, ItemCliente(cliente_nome))
        projeto = next((p for p in cliente.projetos if p.nome == projeto_nome), None)
        if projeto is None:
            projeto = ItemProjeto(projeto_nome, _inferir_tipo(projeto_nome))
            cliente.projetos.append(projeto)
        existentes = {a.caminho for a in projeto.regras}
        projeto.regras.extend(a for a in arquivos if a.caminho not in existentes)

    # Arquivos soltos pertencem ao cliente/projeto com o nome da raiz.
    adicionar(raiz.name, raiz.name, arquivos_em(raiz))

    for primeiro in sorted(p for p in raiz.iterdir() if p.is_dir()):
        # raiz/projeto/arquivo
        adicionar(raiz.name, primeiro.name, arquivos_em(primeiro))

        # raiz/cliente/projeto/arquivo; coexistem com os níveis acima.
        for segundo in sorted(p for p in primeiro.iterdir() if p.is_dir()):
            adicionar(primeiro.name, segundo.name, arquivos_em(segundo))

    for cliente in clientes.values():
        cliente.projetos.sort(key=lambda p: p.nome.casefold())
    return sorted(clientes.values(), key=lambda c: c.nome.casefold())


def importar_para_banco(conn, clientes: list[ItemCliente], notas: str = "Importação inicial") -> dict:
    import database.models as M
    with M.transacao(conn):
        return _importar_para_banco(conn, clientes, notas)


def _importar_para_banco(conn, clientes: list[ItemCliente], notas: str) -> dict:
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

                conteudo = _ler_arquivo(arq.caminho)
                regra = M.criar_regra(conn, projeto_id, arq.numero, arq.descricao)
                M.criar_versao(conn, regra.id, conteudo, notas)
                contagem["regras"] += 1

    return contagem
