from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Optional
from uuid import uuid4


@contextmanager
def transacao(conn):
    """Permite operações compostas com rollback, inclusive dentro de outra transação."""
    nome = "operacao_" + uuid4().hex
    conn.execute(f"SAVEPOINT {nome}")
    try:
        yield
        conn.execute(f"RELEASE SAVEPOINT {nome}")
    except BaseException:
        conn.execute(f"ROLLBACK TO SAVEPOINT {nome}")
        conn.execute(f"RELEASE SAVEPOINT {nome}")
        raise


def _atomica(func):
    @wraps(func)
    def executar(conn, *args, **kwargs):
        with transacao(conn):
            return func(conn, *args, **kwargs)
    return executar


@dataclass
class Cliente:
    id: Optional[int]
    nome: str
    criado_em: str = ""


@dataclass
class Projeto:
    id: Optional[int]
    cliente_id: int
    nome: str
    tipo: str  # 'DID', 'Projeto' ou 'Regra'
    descricao: str = ""
    criado_em: str = ""


@dataclass
class Regra:
    id: Optional[int]
    projeto_id: int
    numero: str
    descricao: str = ""
    criado_em: str = ""
    porta_id: Optional[int] = None


@dataclass
class Porta:
    id: Optional[int]
    projeto_id: int
    numero: str
    criado_em: str = ""


TIPOS_VERSAO = ["Criação", "Correção", "Melhoria", "Refatoração"]


@dataclass
class Versao:
    id: Optional[int]
    regra_id: int
    numero: int
    conteudo: str = ""
    status: str = "Em desenvolvimento"
    notas: str = ""
    atual: bool = False
    tipo: str = "Criação"
    criado_em: str = ""


# --- CRUD: Clientes ---

def listar_clientes(conn) -> list[Cliente]:
    rows = conn.execute("SELECT * FROM clientes ORDER BY nome COLLATE NOCASE").fetchall()
    return [Cliente(**dict(r)) for r in rows]


@_atomica
def criar_cliente(conn, nome: str) -> Cliente:
    nome = nome.strip()
    if not nome:
        raise ValueError("Informe o nome do cliente.")
    cur = conn.execute(
        "INSERT INTO clientes (nome) VALUES (?)", (nome,)
    )
    row = conn.execute("SELECT * FROM clientes WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Cliente(**dict(row))


@_atomica
def deletar_cliente(conn, cliente_id: int):
    conn.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))


@_atomica
def renomear_cliente(conn, cliente_id: int, novo_nome: str):
    novo_nome = novo_nome.strip()
    if not novo_nome:
        raise ValueError("Informe o nome do cliente.")
    conn.execute("UPDATE clientes SET nome = ? WHERE id = ?", (novo_nome, cliente_id))


# --- CRUD: Projetos ---

def listar_projetos(conn, cliente_id: int) -> list[Projeto]:
    rows = conn.execute(
        "SELECT * FROM projetos WHERE cliente_id = ? ORDER BY nome COLLATE NOCASE", (cliente_id,)
    ).fetchall()
    return [Projeto(**dict(r)) for r in rows]


@_atomica
def criar_projeto(conn, cliente_id: int, nome: str, tipo: str, descricao: str = "") -> Projeto:
    cur = conn.execute(
        "INSERT INTO projetos (cliente_id, nome, tipo, descricao) VALUES (?, ?, ?, ?)",
        (cliente_id, nome, tipo, descricao),
    )
    row = conn.execute("SELECT * FROM projetos WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Projeto(**dict(row))


@_atomica
def deletar_projeto(conn, projeto_id: int):
    conn.execute("DELETE FROM projetos WHERE id = ?", (projeto_id,))


@_atomica
def atualizar_projeto(conn, projeto_id: int, novo_nome: str, tipo: str, descricao: str = ""):
    anterior = conn.execute(
        "SELECT tipo FROM projetos WHERE id = ?", (projeto_id,)
    ).fetchone()
    conn.execute(
        "UPDATE projetos SET nome = ?, tipo = ?, descricao = ? WHERE id = ?",
        (novo_nome, tipo, descricao, projeto_id),
    )

    if anterior and anterior["tipo"] != "Webservice" and tipo == "Webservice":
        regras_diretas = conn.execute(
            "SELECT id, numero FROM regras WHERE projeto_id = ? AND porta_id IS NULL ORDER BY id",
            (projeto_id,),
        ).fetchall()
        for indice, regra in enumerate(regras_diretas):
            base = "Sem porta" if indice == 0 else f"Sem porta - {regra['numero']}"
            numero_porta = base
            sufixo = 2
            while conn.execute(
                "SELECT 1 FROM portas WHERE projeto_id = ? AND numero = ?",
                (projeto_id, numero_porta),
            ).fetchone():
                numero_porta = f"{base} ({sufixo})"
                sufixo += 1
            cur = conn.execute(
                "INSERT INTO portas (projeto_id, numero) VALUES (?, ?)",
                (projeto_id, numero_porta),
            )
            porta_id = cur.lastrowid
            conn.execute(
                "UPDATE regras SET porta_id = ? WHERE id = ?",
                (porta_id, regra["id"]),
            )
    elif anterior and anterior["tipo"] == "Webservice" and tipo != "Webservice":
        # Ao voltar para um tipo comum, as regras retornam diretamente ao
        # projeto antes da remoção das portas, preservando todo o conteúdo.
        conn.execute(
            "UPDATE regras SET porta_id = NULL WHERE projeto_id = ?",
            (projeto_id,),
        )
        conn.execute("DELETE FROM portas WHERE projeto_id = ?", (projeto_id,))


# --- CRUD: Portas de Webservice ---

def listar_portas(conn, projeto_id: int) -> list[Porta]:
    rows = conn.execute(
        "SELECT * FROM portas WHERE projeto_id = ? ORDER BY numero COLLATE NOCASE",
        (projeto_id,),
    ).fetchall()
    return [Porta(**dict(r)) for r in rows]


@_atomica
def criar_porta(conn, projeto_id: int, numero: str) -> Porta:
    numero = numero.strip()
    if not numero:
        raise ValueError("Informe a porta do Webservice.")
    projeto = conn.execute(
        "SELECT tipo FROM projetos WHERE id = ?", (projeto_id,)
    ).fetchone()
    if not projeto or projeto["tipo"] != "Webservice":
        raise ValueError("Portas só podem ser criadas em projetos do tipo Webservice.")
    cur = conn.execute(
        "INSERT INTO portas (projeto_id, numero) VALUES (?, ?)",
        (projeto_id, numero),
    )
    row = conn.execute("SELECT * FROM portas WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Porta(**dict(row))


@_atomica
def criar_porta_com_regra(conn, projeto_id: int, numero: str) -> tuple[Porta, Regra]:
    """Cria a porta e seu conteúdo versionado interno em uma única operação."""
    porta = criar_porta(conn, projeto_id, numero)
    regra = criar_regra(
        conn, projeto_id, f"porta-{porta.id}", porta_id=porta.id,
    )
    criar_versao(conn, regra.id)
    return porta, regra


@_atomica
def atualizar_porta(conn, porta_id: int, numero: str):
    numero = numero.strip()
    if not numero:
        raise ValueError("Informe a porta do Webservice.")
    conn.execute("UPDATE portas SET numero = ? WHERE id = ?", (numero, porta_id))


@_atomica
def deletar_porta(conn, porta_id: int):
    conn.execute("DELETE FROM portas WHERE id = ?", (porta_id,))


def regra_da_porta(conn, porta_id: int) -> Optional[Regra]:
    row = conn.execute(
        "SELECT * FROM regras WHERE porta_id = ? ORDER BY id LIMIT 1",
        (porta_id,),
    ).fetchone()
    return Regra(**dict(row)) if row else None


# --- CRUD: Regras ---

def listar_regras(conn, projeto_id: int) -> list[Regra]:
    rows = conn.execute(
        "SELECT * FROM regras WHERE projeto_id = ? ORDER BY numero COLLATE NOCASE", (projeto_id,)
    ).fetchall()
    return [Regra(**dict(r)) for r in rows]


def listar_regras_porta(conn, porta_id: int) -> list[Regra]:
    rows = conn.execute(
        "SELECT * FROM regras WHERE porta_id = ? ORDER BY numero COLLATE NOCASE",
        (porta_id,),
    ).fetchall()
    return [Regra(**dict(r)) for r in rows]


@_atomica
def criar_regra(
    conn, projeto_id: int, numero: str, descricao: str = "", porta_id: int | None = None,
) -> Regra:
    projeto = conn.execute(
        "SELECT tipo FROM projetos WHERE id = ?", (projeto_id,)
    ).fetchone()
    if not projeto:
        raise ValueError("Projeto não encontrado.")
    if projeto["tipo"] == "Webservice":
        porta = conn.execute(
            "SELECT 1 FROM portas WHERE id = ? AND projeto_id = ?",
            (porta_id, projeto_id),
        ).fetchone()
        if not porta:
            raise ValueError("Selecione uma porta do Webservice para criar a regra.")
    elif porta_id is not None:
        raise ValueError("A porta informada não pertence a um Webservice.")
    cur = conn.execute(
        "INSERT INTO regras (projeto_id, porta_id, numero, descricao) VALUES (?, ?, ?, ?)",
        (projeto_id, porta_id, numero, descricao),
    )
    row = conn.execute("SELECT * FROM regras WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Regra(**dict(row))


@_atomica
def deletar_regra(conn, regra_id: int):
    conn.execute("DELETE FROM regras WHERE id = ?", (regra_id,))


@_atomica
def atualizar_regra(conn, regra_id: int, numero: str, descricao: str):
    conn.execute(
        "UPDATE regras SET numero = ?, descricao = ? WHERE id = ?",
        (numero, descricao, regra_id),
    )


# --- CRUD: Versões ---

def listar_versoes(conn, regra_id: int) -> list[Versao]:
    rows = conn.execute(
        "SELECT * FROM versoes WHERE regra_id = ? ORDER BY numero DESC", (regra_id,)
    ).fetchall()
    return [Versao(**{**dict(r), "atual": bool(r["atual"])}) for r in rows]


@_atomica
def criar_versao(conn, regra_id: int, conteudo: str = "", notas: str = "", tipo: str = "Criação") -> Versao:
    ultimo = conn.execute(
        "SELECT COALESCE(MAX(numero), 0) FROM versoes WHERE regra_id = ?", (regra_id,)
    ).fetchone()[0]
    proximo = ultimo + 1

    conn.execute("UPDATE versoes SET atual = 0 WHERE regra_id = ?", (regra_id,))
    cur = conn.execute(
        """INSERT INTO versoes (regra_id, numero, conteudo, notas, atual, tipo)
           VALUES (?, ?, ?, ?, 1, ?)""",
        (regra_id, proximo, conteudo, notas, tipo),
    )
    row = conn.execute("SELECT * FROM versoes WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Versao(**{**dict(row), "atual": bool(row["atual"])})


@_atomica
def salvar_conteudo_versao(conn, versao_id: int, conteudo: str):
    conn.execute("UPDATE versoes SET conteudo = ? WHERE id = ?", (conteudo, versao_id))


@_atomica
def atualizar_versao(conn, versao_id: int, status: str, notas: str):
    conn.execute(
        "UPDATE versoes SET status = ?, notas = ? WHERE id = ?",
        (status, notas, versao_id),
    )


@_atomica
def atualizar_meta_versao(conn, versao_id: int, tipo: str, status: str, notas: str):
    conn.execute(
        "UPDATE versoes SET tipo = ?, status = ?, notas = ? WHERE id = ?",
        (tipo, status, notas, versao_id),
    )


@_atomica
def definir_versao_atual(conn, regra_id: int, versao_id: int):
    if not conn.execute(
        "SELECT 1 FROM versoes WHERE id = ? AND regra_id = ?", (versao_id, regra_id)
    ).fetchone():
        raise ValueError("A versão não pertence à regra selecionada.")
    conn.execute("UPDATE versoes SET atual = 0 WHERE regra_id = ?", (regra_id,))
    conn.execute("UPDATE versoes SET atual = 1 WHERE id = ?", (versao_id,))


@_atomica
def deletar_versao(conn, versao_id: int):
    versao = conn.execute("SELECT * FROM versoes WHERE id = ?", (versao_id,)).fetchone()
    if not versao:
        return
    restantes = conn.execute(
        "SELECT id FROM versoes WHERE regra_id = ? AND id != ? ORDER BY numero DESC",
        (versao["regra_id"], versao_id),
    ).fetchall()
    if not restantes:
        raise ValueError("Não é possível excluir a única versão da regra.")
    conn.execute("DELETE FROM versoes WHERE id = ?", (versao_id,))
    if versao["atual"]:
        definir_versao_atual(conn, versao["regra_id"], restantes[0]["id"])
