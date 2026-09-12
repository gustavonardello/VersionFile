import json
import sqlite3
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QMenu, QMessageBox, QLineEdit, QCheckBox, QLabel, QPushButton,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QAction, QColor, QPixmap
import database.models as M
from ui.dialogs import (
    DialogCliente, DialogProjeto, DialogRegra, DialogRegraRelatorio, DialogPorta,
)
from ui.errors import mostrar_erro
from core.paths import base_path, data_path
from core.text_utils import normalizar_busca

NODE_CLIENTE = "cliente"
NODE_PROJETO = "projeto"
NODE_PORTA   = "porta"
NODE_REGRA   = "regra"

_TREE_STATE_PATH = data_path() / "config" / "tree_state.json"


def _item(texto: str, tipo: str, id_: int, extra=None) -> QTreeWidgetItem:
    item = QTreeWidgetItem([texto])
    item.setData(0, Qt.ItemDataRole.UserRole, {"tipo": tipo, "id": id_, "extra": extra})
    return item


class TreePanel(QWidget):
    regra_selecionada = pyqtSignal(int)   # regra_id
    regra_desmarcada  = pyqtSignal()

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Logo
        logo_path = base_path() / "logo.png"
        if logo_path.exists():
            lbl_logo = QLabel()
            pixmap = QPixmap(str(logo_path))
            lbl_logo.setPixmap(pixmap.scaledToWidth(200, Qt.TransformationMode.SmoothTransformation))
            lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_logo.setContentsMargins(8, 8, 8, 4)
            layout.addWidget(lbl_logo)

        # Barra de busca
        self.campo_busca = QLineEdit()
        self.campo_busca.setPlaceholderText("Buscar regra...")
        self.campo_busca.setClearButtonEnabled(True)
        self.campo_busca.setStyleSheet(
            "background:#2D2D2D; border:1px solid #555; color:#D4D4D4;"
            "padding:4px 6px; border-radius:2px;"
        )
        layout.addWidget(self.campo_busca)

        self.check_conteudo = QCheckBox("Buscar no conteúdo")
        self.check_conteudo.setStyleSheet("""
            QCheckBox { color:#858585; font-size:11px; padding:0 4px; }
            QCheckBox::indicator {
                width: 13px;
                height: 13px;
                border: 1px solid #FFFFFF;
                border-radius: 2px;
                background-color: #252526;
            }
            QCheckBox::indicator:checked {
                background-color: #FFFFFF;
                border-color: #FFFFFF;
            }
        """)
        layout.addWidget(self.check_conteudo)

        # Ações visíveis da árvore. "+ Cliente" permanece sempre disponível;
        # as demais acompanham o nível atualmente selecionado.
        barra_acoes = QHBoxLayout()
        barra_acoes.setContentsMargins(4, 2, 4, 2)
        barra_acoes.setSpacing(4)

        self.btn_novo_cliente = QPushButton("+ Cliente")
        self.btn_novo_cliente.setToolTip("Adicionar cliente")
        self.btn_novo_cliente.clicked.connect(self._novo_cliente)
        barra_acoes.addWidget(self.btn_novo_cliente)

        self.btn_adicionar_contexto = QPushButton("")
        self.btn_adicionar_contexto.clicked.connect(self._adicionar_no_selecionado)
        self.btn_adicionar_contexto.setVisible(False)
        barra_acoes.addWidget(self.btn_adicionar_contexto)

        self.btn_editar_selecionado = QPushButton("Editar")
        self.btn_editar_selecionado.setToolTip("Editar item selecionado")
        self.btn_editar_selecionado.clicked.connect(self._editar_selecionado)
        self.btn_editar_selecionado.setVisible(False)
        barra_acoes.addWidget(self.btn_editar_selecionado)

        self.btn_excluir_selecionado = QPushButton("Excluir")
        self.btn_excluir_selecionado.setToolTip("Excluir item selecionado")
        self.btn_excluir_selecionado.clicked.connect(self._excluir_selecionado)
        self.btn_excluir_selecionado.setVisible(False)
        barra_acoes.addWidget(self.btn_excluir_selecionado)
        barra_acoes.addStretch()
        layout.addLayout(barra_acoes)

        for botao in (
            self.btn_novo_cliente,
            self.btn_adicionar_contexto,
            self.btn_editar_selecionado,
            self.btn_excluir_selecionado,
        ):
            botao.setFixedHeight(26)
            botao.setStyleSheet("""
                QPushButton {
                    background-color: #3C3C3C;
                    color: #D4D4D4;
                    border: 1px solid #555;
                    padding: 3px 8px;
                    border-radius: 3px;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #4A4A4A; border-color: #777; }
                QPushButton:pressed { background-color: #2A2A2A; }
            """)

        self.label_resultado = QLabel("")
        self.label_resultado.setStyleSheet("color:#858585; font-size:10px; padding:0 4px;")
        layout.addWidget(self.label_resultado)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemSelectionChanged.connect(self._on_selecao)
        self.tree.itemExpanded.connect(self._on_expandido)
        self.tree.itemCollapsed.connect(self._on_recolhido)
        layout.addWidget(self.tree)

        # Debounce: só filtra 300ms após parar de digitar
        self._timer_busca = QTimer()
        self._timer_busca.setSingleShot(True)
        self._timer_busca.setInterval(300)
        self._timer_busca.timeout.connect(self._aplicar_filtro)
        self.campo_busca.textChanged.connect(lambda _: self._timer_busca.start())
        self.check_conteudo.stateChanged.connect(lambda _: self._aplicar_filtro())

        self.carregar()

    def _estado_expandido(self) -> dict:
        """Salva quais clientes, projetos e portas estão expandidos."""
        estado = {"clientes": set(), "projetos": set(), "portas": set()}
        for i in range(self.tree.topLevelItemCount()):
            item_c = self.tree.topLevelItem(i)
            d = self._dados(item_c)
            if item_c.isExpanded():
                estado["clientes"].add(d["id"])
            for j in range(item_c.childCount()):
                item_p = item_c.child(j)
                dp = self._dados(item_p)
                if item_p.isExpanded():
                    estado["projetos"].add(dp["id"])
                for k in range(item_p.childCount()):
                    item_porta = item_p.child(k)
                    dados_porta = self._dados(item_porta)
                    if dados_porta.get("tipo") == NODE_PORTA and item_porta.isExpanded():
                        estado["portas"].add(dados_porta["id"])
        return estado

    def _restaurar_expandido(
        self, estado: dict, ids_novos_clientes: set,
        ids_novos_projetos: set, ids_novas_portas: set,
    ):
        """Restaura o estado expandido; novos itens ficam expandidos por padrão."""
        for i in range(self.tree.topLevelItemCount()):
            item_c = self.tree.topLevelItem(i)
            d = self._dados(item_c)
            cid = d["id"]
            # Expande se estava expandido antes ou é novo
            expandir_c = (cid in estado["clientes"]) or (cid in ids_novos_clientes)
            item_c.setExpanded(expandir_c)
            for j in range(item_c.childCount()):
                item_p = item_c.child(j)
                dp = self._dados(item_p)
                pid = dp["id"]
                expandir_p = (pid in estado["projetos"]) or (pid in ids_novos_projetos)
                item_p.setExpanded(expandir_p)
                for k in range(item_p.childCount()):
                    item_porta = item_p.child(k)
                    dados_porta = self._dados(item_porta)
                    if dados_porta.get("tipo") == NODE_PORTA:
                        porta_id = dados_porta["id"]
                        item_porta.setExpanded(
                            porta_id in estado.get("portas", set())
                            or porta_id in ids_novas_portas
                        )

    def carregar(
        self, ids_novos_clientes: set = None, ids_novos_projetos: set = None,
        ids_novas_portas: set = None,
    ):
        selecionado = self.tree.currentItem()
        dados = self._dados(selecionado) if selecionado else {}
        try:
            self._carregar_itens(ids_novos_clientes, ids_novos_projetos, ids_novas_portas)
        finally:
            self.tree.blockSignals(False)
        self._aplicar_filtro()
        if dados.get("tipo"):
            self._selecionar_item(dados["tipo"], dados["id"])
        if not self.tree.selectedItems():
            self.regra_desmarcada.emit()
        self._atualizar_barra_acoes()

    def _carregar_itens(
        self, ids_novos_clientes=None, ids_novos_projetos=None,
        ids_novas_portas=None,
    ):
        primeira_vez = self.tree.topLevelItemCount() == 0
        estado = self._carregar_estado_salvo() if primeira_vez else self._estado_expandido()

        self.tree.blockSignals(True)
        self.tree.clear()
        self.label_resultado.setText("")

        for cliente in M.listar_clientes(self.conn):
            item_c = _item(cliente.nome, NODE_CLIENTE, cliente.id)
            for projeto in M.listar_projetos(self.conn, cliente.id):
                label = f"[{projeto.tipo}] {projeto.nome}"
                item_p = _item(label, NODE_PROJETO, projeto.id, projeto.cliente_id)
                if projeto.tipo == "Webservice":
                    for porta in M.listar_portas(self.conn, projeto.id):
                        regra = M.regra_da_porta(self.conn, porta.id)
                        item_porta = _item(
                            f"Porta {porta.numero}", NODE_PORTA, porta.id,
                            {
                                "projeto_id": projeto.id,
                                "regra_id": regra.id if regra else None,
                            },
                        )
                        item_p.addChild(item_porta)
                else:
                    for regra in M.listar_regras(self.conn, projeto.id):
                        item_p.addChild(self._item_regra(regra, projeto))
                item_c.addChild(item_p)
            self.tree.addTopLevelItem(item_c)

        if primeira_vez and estado is None:
            # Sem estado salvo: expande tudo na primeira vez
            self.tree.expandAll()
        elif estado is not None:
            self._restaurar_expandido(
                estado,
                ids_novos_clientes or set(),
                ids_novos_projetos or set(),
                ids_novas_portas or set(),
            )

        self.tree.blockSignals(False)

    def _item_regra(self, regra, projeto) -> QTreeWidgetItem:
        desc = f" — {regra.descricao}" if regra.descricao else ""
        if projeto.tipo == "Relatório":
            label = f"{regra.numero}{desc}"
        else:
            label = f"Regra {regra.numero}{desc}"
        return _item(label, NODE_REGRA, regra.id, projeto.id)

    # --- Persistência do estado expandido ---

    def _salvar_estado(self):
        estado = self._estado_expandido()
        dados = {
            "clientes": list(estado["clientes"]),
            "projetos": list(estado["projetos"]),
            "portas": list(estado["portas"]),
        }
        try:
            _TREE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _TREE_STATE_PATH.write_text(
                json.dumps(dados, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def _carregar_estado_salvo(self) -> dict:
        try:
            if _TREE_STATE_PATH.exists():
                dados = json.loads(_TREE_STATE_PATH.read_text(encoding="utf-8"))
                return {
                    "clientes": set(dados.get("clientes", [])),
                    "projetos": set(dados.get("projetos", [])),
                    "portas": set(dados.get("portas", [])),
                }
        except Exception:
            pass
        return None

    def _on_expandido(self, _item):
        self._salvar_estado()

    def _on_recolhido(self, _item):
        self._salvar_estado()

    def _aplicar_filtro(self):
        termo = normalizar_busca(self.campo_busca.text().strip())
        buscar_conteudo = self.check_conteudo.isChecked()

        if not termo:
            self._mostrar_todos()
            self.label_resultado.setText("")
            return

        # Regras que batem com conteúdo (busca no banco)
        regras_conteudo: set[int] = set()
        if buscar_conteudo:
            rows = self.conn.execute("SELECT regra_id, conteudo FROM versoes").fetchall()
            regras_conteudo = {
                r["regra_id"] for r in rows if termo in normalizar_busca(r["conteudo"])
            }

        def filtrar(item: QTreeWidgetItem, ancestral_bate: bool = False) -> tuple[bool, int]:
            dados = self._dados(item)
            bate_texto = termo in normalizar_busca(item.text(0))
            bate_caminho = ancestral_bate or bate_texto

            if dados.get("tipo") in (NODE_REGRA, NODE_PORTA):
                regra_id = (
                    (dados.get("extra") or {}).get("regra_id")
                    if dados.get("tipo") == NODE_PORTA else dados["id"]
                )
                bate = bate_caminho or (
                    buscar_conteudo and regra_id in regras_conteudo
                )
                item.setHidden(not bate)
                return bate, int(bate)

            tem_filho = False
            encontrados_item = 0
            for indice in range(item.childCount()):
                filho_visivel, quantidade = filtrar(item.child(indice), bate_caminho)
                tem_filho = tem_filho or filho_visivel
                encontrados_item += quantidade

            visivel = bate_texto or tem_filho
            item.setHidden(not visivel)
            if visivel:
                item.setExpanded(True)
            return visivel, encontrados_item

        encontrados = 0
        for i in range(self.tree.topLevelItemCount()):
            _, quantidade = filtrar(self.tree.topLevelItem(i))
            encontrados += quantidade

        label = f"{encontrados} regra(s) encontrada(s)"
        if buscar_conteudo:
            label += " (incl. conteúdo)"
        self.label_resultado.setText(label)

    def _mostrar_todos(self):
        def mostrar(item: QTreeWidgetItem):
            item.setHidden(False)
            for indice in range(item.childCount()):
                mostrar(item.child(indice))

        for i in range(self.tree.topLevelItemCount()):
            mostrar(self.tree.topLevelItem(i))

    def _dados(self, item: QTreeWidgetItem) -> dict:
        return item.data(0, Qt.ItemDataRole.UserRole) or {}

    def _on_selecao(self):
        itens = self.tree.selectedItems()
        if not itens:
            self.regra_desmarcada.emit()
            self._atualizar_barra_acoes()
            return
        d = self._dados(itens[0])
        if d.get("tipo") == NODE_REGRA:
            self.regra_selecionada.emit(d["id"])
        elif d.get("tipo") == NODE_PORTA and (d.get("extra") or {}).get("regra_id"):
            self.regra_selecionada.emit(d["extra"]["regra_id"])
        else:
            self.regra_desmarcada.emit()
        self._atualizar_barra_acoes()

    def _atualizar_barra_acoes(self):
        item = self.tree.currentItem()
        dados = self._dados(item) if item else {}
        tipo = dados.get("tipo")

        mostrar_edicao = tipo in (NODE_CLIENTE, NODE_PROJETO, NODE_PORTA, NODE_REGRA)
        self.btn_editar_selecionado.setVisible(mostrar_edicao)
        self.btn_excluir_selecionado.setVisible(mostrar_edicao)

        textos = {
            NODE_CLIENTE: "+ Projeto",
        }
        if tipo == NODE_PROJETO:
            projeto = self.conn.execute(
                "SELECT tipo FROM projetos WHERE id = ?", (dados["id"],)
            ).fetchone()
            textos[NODE_PROJETO] = "+ Porta" if projeto and projeto["tipo"] == "Webservice" else "+ Regra"

        texto_adicionar = textos.get(tipo)
        self.btn_adicionar_contexto.setVisible(bool(texto_adicionar))
        if texto_adicionar:
            self.btn_adicionar_contexto.setText(texto_adicionar)

        nomes = {
            NODE_CLIENTE: "cliente",
            NODE_PROJETO: "projeto",
            NODE_PORTA: "porta",
            NODE_REGRA: "regra",
        }
        nome = nomes.get(tipo, "item")
        self.btn_editar_selecionado.setToolTip(f"Editar {nome} selecionado")
        self.btn_excluir_selecionado.setToolTip(f"Excluir {nome} selecionado")

    def _adicionar_no_selecionado(self):
        item = self.tree.currentItem()
        dados = self._dados(item) if item else {}
        tipo = dados.get("tipo")
        if tipo == NODE_CLIENTE:
            self._novo_projeto(dados["id"])
        elif tipo == NODE_PROJETO:
            projeto = self.conn.execute(
                "SELECT tipo FROM projetos WHERE id = ?", (dados["id"],)
            ).fetchone()
            if projeto and projeto["tipo"] == "Webservice":
                self._nova_porta(dados["id"])
            else:
                self._nova_regra(dados["id"])

    def _editar_selecionado(self):
        item = self.tree.currentItem()
        dados = self._dados(item) if item else {}
        tipo = dados.get("tipo")
        if tipo == NODE_CLIENTE:
            self._renomear_cliente(dados["id"], item)
        elif tipo == NODE_PROJETO:
            self._renomear_projeto(dados["id"], item)
        elif tipo == NODE_PORTA:
            self._editar_porta(dados["id"])
        elif tipo == NODE_REGRA:
            self._editar_regra(dados["id"])

    def _excluir_selecionado(self):
        item = self.tree.currentItem()
        dados = self._dados(item) if item else {}
        tipo = dados.get("tipo")
        if tipo == NODE_CLIENTE:
            self._excluir_cliente(dados["id"])
        elif tipo == NODE_PROJETO:
            self._excluir_projeto(dados["id"])
        elif tipo == NODE_PORTA:
            self._excluir_porta(dados["id"])
        elif tipo == NODE_REGRA:
            self._excluir_regra(dados["id"])

    def _on_click(self, item: QTreeWidgetItem, _col):
        d = self._dados(item)
        if d.get("tipo") == NODE_REGRA:
            self.regra_selecionada.emit(d["id"])

    def _context_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)

        if item is None:
            menu.addAction("Novo cliente").triggered.connect(self._novo_cliente)
            menu.addSeparator()
            menu.addAction("Expandir tudo").triggered.connect(self.tree.expandAll)
            menu.addAction("Recolher tudo").triggered.connect(self.tree.collapseAll)
        else:
            d = self._dados(item)
            tipo = d.get("tipo")

            if tipo == NODE_CLIENTE:
                menu.addAction("Novo projeto").triggered.connect(
                    lambda: self._novo_projeto(d["id"])
                )
                menu.addAction("Renomear cliente").triggered.connect(
                    lambda: self._renomear_cliente(d["id"], item)
                )
                menu.addAction("Excluir cliente").triggered.connect(
                    lambda: self._excluir_cliente(d["id"])
                )
                menu.addSeparator()
                menu.addAction("Novo cliente").triggered.connect(self._novo_cliente)
                menu.addSeparator()
                menu.addAction("Expandir tudo").triggered.connect(self.tree.expandAll)
                menu.addAction("Recolher tudo").triggered.connect(self.tree.collapseAll)

            elif tipo == NODE_PROJETO:
                projeto = self.conn.execute(
                    "SELECT tipo FROM projetos WHERE id = ?", (d["id"],)
                ).fetchone()
                if projeto and projeto["tipo"] == "Webservice":
                    menu.addAction("Nova porta").triggered.connect(
                        lambda: self._nova_porta(d["id"])
                    )
                else:
                    menu.addAction("Nova regra").triggered.connect(
                        lambda: self._nova_regra(d["id"])
                    )
                menu.addAction("Renomear projeto").triggered.connect(
                    lambda: self._renomear_projeto(d["id"], item)
                )
                menu.addAction("Excluir projeto").triggered.connect(
                    lambda: self._excluir_projeto(d["id"])
                )

            elif tipo == NODE_PORTA:
                menu.addAction("Editar porta").triggered.connect(
                    lambda: self._editar_porta(d["id"])
                )
                menu.addAction("Excluir porta").triggered.connect(
                    lambda: self._excluir_porta(d["id"])
                )

            elif tipo == NODE_REGRA:
                menu.addAction("Editar regra").triggered.connect(
                    lambda: self._editar_regra(d["id"])
                )
                menu.addAction("Excluir regra").triggered.connect(
                    lambda: self._excluir_regra(d["id"])
                )

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    # --- Ações ---

    def _novo_cliente(self):
        dlg = DialogCliente(self)
        while dlg.exec() and dlg.nome:
            try:
                c = M.criar_cliente(self.conn, dlg.nome)
            except sqlite3.IntegrityError as e:
                mensagem = (
                    f'Já existe um cliente com o nome "{dlg.nome}". Informe outro nome.'
                    if "clientes.nome" in str(e) else str(e)
                )
                QMessageBox.warning(self, "Cliente não cadastrado", mensagem)
                dlg.campo_nome.selectAll()
            except Exception as e:
                QMessageBox.warning(self, "Erro", str(e))
                return
            else:
                self.carregar(ids_novos_clientes={c.id})
                return

    def _renomear_cliente(self, cliente_id, _item):
        dlg = DialogCliente(self, nome_atual=_item.text(0))
        while dlg.exec() and dlg.nome:
            try:
                M.renomear_cliente(self.conn, cliente_id, dlg.nome)
            except sqlite3.IntegrityError as e:
                mensagem = (
                    f'Já existe um cliente com o nome "{dlg.nome}". Informe outro nome.'
                    if "clientes.nome" in str(e) else str(e)
                )
                QMessageBox.warning(self, "Cliente não renomeado", mensagem)
                dlg.campo_nome.selectAll()
            except Exception as e:
                QMessageBox.warning(self, "Erro", str(e))
                return
            else:
                self.carregar()
                return

    def _excluir_cliente(self, cliente_id):
        if QMessageBox.question(self, "Confirmar", "Excluir cliente e todos os dados?") \
                == QMessageBox.StandardButton.Yes:
            try:
                M.deletar_cliente(self.conn, cliente_id)
                self.carregar()
            except Exception as erro:
                mostrar_erro(self, "Cliente não excluído", erro)

    def _novo_projeto(self, cliente_id):
        dlg = DialogProjeto(self)
        if dlg.exec() and dlg.nome:
            try:
                p = M.criar_projeto(self.conn, cliente_id, dlg.nome, dlg.tipo, dlg.descricao)
                self.carregar(ids_novos_clientes={cliente_id}, ids_novos_projetos={p.id})
            except Exception as e:
                QMessageBox.warning(self, "Erro", str(e))

    def _renomear_projeto(self, projeto_id, _item):
        proj = self.conn.execute(
            "SELECT nome, tipo, descricao FROM projetos WHERE id = ?", (projeto_id,)
        ).fetchone()
        if not proj:
            return
        dlg = DialogProjeto(
            self,
            nome_atual=proj["nome"],
            tipo_atual=proj["tipo"],
            descricao_atual=proj["descricao"] or "",
        )
        dlg.setWindowTitle("Editar projeto")
        if dlg.exec() and dlg.nome:
            try:
                M.atualizar_projeto(self.conn, projeto_id, dlg.nome, dlg.tipo, dlg.descricao)
                self.carregar()
            except Exception as e:
                QMessageBox.warning(self, "Erro", str(e))

    def _excluir_projeto(self, projeto_id):
        if QMessageBox.question(self, "Confirmar", "Excluir projeto e todas as regras?") \
                == QMessageBox.StandardButton.Yes:
            try:
                M.deletar_projeto(self.conn, projeto_id)
                self.carregar()
            except Exception as erro:
                mostrar_erro(self, "Projeto não excluído", erro)

    def _nova_porta(self, projeto_id):
        dlg = DialogPorta(self)
        if dlg.exec() and dlg.numero:
            try:
                porta, _regra = M.criar_porta_com_regra(
                    self.conn, projeto_id, dlg.numero,
                )
                projeto = self.conn.execute(
                    "SELECT cliente_id FROM projetos WHERE id = ?", (projeto_id,)
                ).fetchone()
                self.carregar(
                    ids_novos_clientes={projeto["cliente_id"]} if projeto else set(),
                    ids_novos_projetos={projeto_id},
                    ids_novas_portas={porta.id},
                )
                self._selecionar_item(NODE_PORTA, porta.id)
            except Exception as erro:
                mostrar_erro(self, "Porta não criada", erro)

    def _editar_porta(self, porta_id):
        porta = self.conn.execute(
            "SELECT numero FROM portas WHERE id = ?", (porta_id,)
        ).fetchone()
        if not porta:
            return
        dlg = DialogPorta(self, numero_atual=porta["numero"])
        dlg.setWindowTitle("Editar porta")
        if dlg.exec() and dlg.numero:
            try:
                M.atualizar_porta(self.conn, porta_id, dlg.numero)
                self.carregar()
            except Exception as erro:
                mostrar_erro(self, "Porta não atualizada", erro)

    def _excluir_porta(self, porta_id):
        if QMessageBox.question(
            self, "Confirmar", "Excluir porta e todas as regras?"
        ) == QMessageBox.StandardButton.Yes:
            try:
                M.deletar_porta(self.conn, porta_id)
                self.carregar()
            except Exception as erro:
                mostrar_erro(self, "Porta não excluída", erro)

    def _nova_regra(self, projeto_id, porta_id=None):
        proj = self.conn.execute(
            "SELECT tipo, cliente_id FROM projetos WHERE id = ?", (projeto_id,)
        ).fetchone()
        if proj and proj["tipo"] == "Webservice" and porta_id is None:
            QMessageBox.information(
                self, "Nova regra", "Selecione ou crie uma porta antes de adicionar a regra.",
            )
            return
        if proj and proj["tipo"] == "Relatório":
            dlg = DialogRegraRelatorio(self)
        else:
            dlg = DialogRegra(self)
        if dlg.exec() and dlg.numero:
            try:
                with M.transacao(self.conn):
                    regra = M.criar_regra(
                        self.conn, projeto_id, dlg.numero, dlg.descricao, porta_id,
                    )
                    M.criar_versao(self.conn, regra.id)
                self.carregar(
                    ids_novos_clientes={proj["cliente_id"]} if proj else set(),
                    ids_novos_projetos={projeto_id},
                    ids_novas_portas={porta_id} if porta_id else set(),
                )
                self._selecionar_regra(regra.id)
            except Exception as e:
                QMessageBox.warning(self, "Erro", str(e))

    def _editar_regra(self, regra_id):
        regra = self.conn.execute(
            "SELECT numero, descricao, projeto_id FROM regras WHERE id = ?", (regra_id,)
        ).fetchone()
        if not regra:
            return
        proj_tipo = self.conn.execute(
            "SELECT tipo FROM projetos WHERE id = ?", (regra["projeto_id"],)
        ).fetchone()
        if proj_tipo and proj_tipo["tipo"] == "Relatório":
            dlg = DialogRegraRelatorio(self, numero_atual=regra["numero"], descricao_atual=regra["descricao"] or "")
        else:
            dlg = DialogRegra(self, numero_atual=regra["numero"], descricao_atual=regra["descricao"] or "")
        dlg.setWindowTitle("Editar Regra")
        if dlg.exec() and dlg.numero:
            try:
                M.atualizar_regra(self.conn, regra_id, dlg.numero, dlg.descricao)
                proj = self.conn.execute(
                    "SELECT cliente_id FROM projetos WHERE id = ?", (regra["projeto_id"],)
                ).fetchone()
                self.carregar(
                    ids_novos_clientes={proj["cliente_id"]} if proj else set(),
                    ids_novos_projetos={regra["projeto_id"]},
                )
            except Exception as e:
                QMessageBox.warning(self, "Erro", str(e))

    def _selecionar_regra(self, regra_id: int):
        """Seleciona o item da regra na árvore, disparando abertura no editor."""
        self._selecionar_item(NODE_REGRA, regra_id)

    def _selecionar_item(self, tipo: str, id_: int):
        def procurar(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            dados = self._dados(item)
            if dados.get("tipo") == tipo and dados.get("id") == id_:
                return item
            for indice in range(item.childCount()):
                encontrado = procurar(item.child(indice))
                if encontrado is not None:
                    return encontrado
            return None

        for indice in range(self.tree.topLevelItemCount()):
            encontrado = procurar(self.tree.topLevelItem(indice))
            if encontrado is not None:
                self.tree.setCurrentItem(encontrado)
                self.tree.scrollToItem(encontrado)
                return

    def _excluir_regra(self, regra_id):
        if QMessageBox.question(self, "Confirmar", "Excluir regra e todas as versões?") \
                == QMessageBox.StandardButton.Yes:
            try:
                M.deletar_regra(self.conn, regra_id)
                self.carregar()
            except Exception as erro:
                mostrar_erro(self, "Regra não excluída", erro)
