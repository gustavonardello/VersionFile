from dataclasses import dataclass, field
from typing import Optional


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
    tipo: str  # 'DID' ou 'Projeto'
    criado_em: str = ""


@dataclass
class Regra:
    id: Optional[int]
    projeto_id: int
    numero: str
    descricao: str = ""
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
    rows = conn.execute("SELECT * FROM clientes ORDER BY nome").fetchall()
    return [Cliente(**dict(r)) for r in rows]


def criar_cliente(conn, nome: str) -> Cliente:
    cur = conn.execute(
        "INSERT INTO clientes (nome) VALUES (?) RETURNING *", (nome,)
    )
    row = cur.fetchone()
    conn.commit()
    return Cliente(**dict(row))


def deletar_cliente(conn, cliente_id: int):
    conn.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))
    conn.commit()


def renomear_cliente(conn, cliente_id: int, novo_nome: str):
    conn.execute("UPDATE clientes SET nome = ? WHERE id = ?", (novo_nome, cliente_id))
    conn.commit()


# --- CRUD: Projetos ---

def listar_projetos(conn, cliente_id: int) -> list[Projeto]:
    rows = conn.execute(
        "SELECT * FROM projetos WHERE cliente_id = ? ORDER BY nome", (cliente_id,)
    ).fetchall()
    return [Projeto(**dict(r)) for r in rows]


def criar_projeto(conn, cliente_id: int, nome: str, tipo: str) -> Projeto:
    cur = conn.execute(
        "INSERT INTO projetos (cliente_id, nome, tipo) VALUES (?, ?, ?) RETURNING *",
        (cliente_id, nome, tipo),
    )
    row = cur.fetchone()
    conn.commit()
    return Projeto(**dict(row))


def deletar_projeto(conn, projeto_id: int):
    conn.execute("DELETE FROM projetos WHERE id = ?", (projeto_id,))
    conn.commit()


def renomear_projeto(conn, projeto_id: int, novo_nome: str):
    conn.execute("UPDATE projetos SET nome = ? WHERE id = ?", (novo_nome, projeto_id))
    conn.commit()


# --- CRUD: Regras ---

def listar_regras(conn, projeto_id: int) -> list[Regra]:
    rows = conn.execute(
        "SELECT * FROM regras WHERE projeto_id = ? ORDER BY numero", (projeto_id,)
    ).fetchall()
    return [Regra(**dict(r)) for r in rows]


def criar_regra(conn, projeto_id: int, numero: str, descricao: str = "") -> Regra:
    cur = conn.execute(
        "INSERT INTO regras (projeto_id, numero, descricao) VALUES (?, ?, ?) RETURNING *",
        (projeto_id, numero, descricao),
    )
    row = cur.fetchone()
    conn.commit()
    return Regra(**dict(row))


def deletar_regra(conn, regra_id: int):
    conn.execute("DELETE FROM regras WHERE id = ?", (regra_id,))
    conn.commit()


# --- CRUD: Versões ---

def listar_versoes(conn, regra_id: int) -> list[Versao]:
    rows = conn.execute(
        "SELECT * FROM versoes WHERE regra_id = ? ORDER BY numero DESC", (regra_id,)
    ).fetchall()
    return [Versao(**{**dict(r), "atual": bool(r["atual"])}) for r in rows]


def criar_versao(conn, regra_id: int, conteudo: str = "", notas: str = "", tipo: str = "Criação") -> Versao:
    ultimo = conn.execute(
        "SELECT COALESCE(MAX(numero), 0) FROM versoes WHERE regra_id = ?", (regra_id,)
    ).fetchone()[0]
    proximo = ultimo + 1

    conn.execute("UPDATE versoes SET atual = 0 WHERE regra_id = ?", (regra_id,))
    cur = conn.execute(
        """INSERT INTO versoes (regra_id, numero, conteudo, notas, atual, tipo)
           VALUES (?, ?, ?, ?, 1, ?) RETURNING *""",
        (regra_id, proximo, conteudo, notas, tipo),
    )
    row = cur.fetchone()
    conn.commit()
    return Versao(**{**dict(row), "atual": bool(row["atual"])})


def salvar_conteudo_versao(conn, versao_id: int, conteudo: str):
    conn.execute("UPDATE versoes SET conteudo = ? WHERE id = ?", (conteudo, versao_id))
    conn.commit()


def atualizar_versao(conn, versao_id: int, status: str, notas: str):
    conn.execute(
        "UPDATE versoes SET status = ?, notas = ? WHERE id = ?",
        (status, notas, versao_id),
    )
    conn.commit()


def definir_versao_atual(conn, regra_id: int, versao_id: int):
    conn.execute("UPDATE versoes SET atual = 0 WHERE regra_id = ?", (regra_id,))
    conn.execute("UPDATE versoes SET atual = 1 WHERE id = ?", (versao_id,))
    conn.commit()


def deletar_versao(conn, versao_id: int):
    conn.execute("DELETE FROM versoes WHERE id = ?", (versao_id,))
    conn.commit()
