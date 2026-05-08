from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QMenu, QMessageBox, QLineEdit, QCheckBox, QLabel,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QAction, QColor
import database.models as M
from ui.dialogs import DialogCliente, DialogProjeto, DialogRegra

NODE_CLIENTE = "cliente"
NODE_PROJETO = "projeto"
NODE_REGRA   = "regra"


def _item(texto: str, tipo: str, id_: int, extra=None) -> QTreeWidgetItem:
    item = QTreeWidgetItem([texto])
    item.setData(0, Qt.ItemDataRole.UserRole, {"tipo": tipo, "id": id_, "extra": extra})
    return item


class TreePanel(QWidget):
    regra_selecionada = pyqtSignal(int)   # regra_id

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

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
        self.check_conteudo.setStyleSheet("color:#858585; font-size:11px; padding:0 4px;")
        layout.addWidget(self.check_conteudo)

        self.label_resultado = QLabel("")
        self.label_resultado.setStyleSheet("color:#858585; font-size:10px; padding:0 4px;")
        layout.addWidget(self.label_resultado)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemClicked.connect(self._on_click)
        layout.addWidget(self.tree)

        # Debounce: só filtra 300ms após parar de digitar
        self._timer_busca = QTimer()
        self._timer_busca.setSingleShot(True)
        self._timer_busca.setInterval(300)
        self._timer_busca.timeout.connect(self._aplicar_filtro)
        self.campo_busca.textChanged.connect(lambda _: self._timer_busca.start())
        self.check_conteudo.stateChanged.connect(lambda _: self._aplicar_filtro())

        self.carregar()

    def carregar(self):
        self.tree.clear()
        self.label_resultado.setText("")
        for cliente in M.listar_clientes(self.conn):
            item_c = _item(cliente.nome, NODE_CLIENTE, cliente.id)
            for projeto in M.listar_projetos(self.conn, cliente.id):
                label = f"[{projeto.tipo}] {projeto.nome}"
                item_p = _item(label, NODE_PROJETO, projeto.id, projeto.cliente_id)
                for regra in M.listar_regras(self.conn, projeto.id):
                    desc = f" — {regra.descricao}" if regra.descricao else ""
                    item_r = _item(f"Regra {regra.numero}{desc}", NODE_REGRA, regra.id, projeto.id)
                    item_p.addChild(item_r)
                item_c.addChild(item_p)
            self.tree.addTopLevelItem(item_c)
        self.tree.expandAll()

    def _aplicar_filtro(self):
        termo = self.campo_busca.text().strip().lower()
        buscar_conteudo = self.check_conteudo.isChecked()

        if not termo:
            self._mostrar_todos()
            self.label_resultado.setText("")
            return

        # Regras que batem com conteúdo (busca no banco)
        regras_conteudo: set[int] = set()
        if buscar_conteudo:
            rows = self.conn.execute(
                """SELECT DISTINCT r.id FROM regras r
                   JOIN versoes v ON v.regra_id = r.id
                   WHERE lower(v.conteudo) LIKE ?""",
                (f"%{termo}%",)
            ).fetchall()
            regras_conteudo = {r["id"] for r in rows}

        encontrados = 0
        for i in range(self.tree.topLevelItemCount()):
            item_c = self.tree.topLevelItem(i)
            tem_cliente = False

            for j in range(item_c.childCount()):
                item_p = item_c.child(j)
                tem_projeto = False

                for k in range(item_p.childCount()):
                    item_r = item_p.child(k)
                    d = self._dados(item_r)
                    texto = item_r.text(0).lower()

                    bate = (termo in texto) or (buscar_conteudo and d["id"] in regras_conteudo)
                    item_r.setHidden(not bate)
                    if bate:
                        tem_projeto = True
                        encontrados += 1

                item_p.setHidden(not tem_projeto)
                if tem_projeto:
                    item_p.setExpanded(True)
                    tem_cliente = True

            item_c.setHidden(not tem_cliente)
            if tem_cliente:
                item_c.setExpanded(True)

        label = f"{encontrados} regra(s) encontrada(s)"
        if buscar_conteudo:
            label += " (incl. conteúdo)"
        self.label_resultado.setText(label)

    def _mostrar_todos(self):
        for i in range(self.tree.topLevelItemCount()):
            item_c = self.tree.topLevelItem(i)
            item_c.setHidden(False)
            for j in range(item_c.childCount()):
                item_p = item_c.child(j)
                item_p.setHidden(False)
                for k in range(item_p.childCount()):
                    item_p.child(k).setHidden(False)

    def _dados(self, item: QTreeWidgetItem) -> dict:
        return item.data(0, Qt.ItemDataRole.UserRole) or {}

    def _on_click(self, item: QTreeWidgetItem, _col):
        d = self._dados(item)
        if d.get("tipo") == NODE_REGRA:
            self.regra_selecionada.emit(d["id"])

    def _context_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)

        if item is None:
            act_novo_cliente = menu.addAction("Novo cliente")
            act_novo_cliente.triggered.connect(self._novo_cliente)
        else:
            d = self._dados(item)
            tipo = d.get("tipo")

            if tipo == NODE_CLIENTE:
                menu.addAction("Novo projeto / DID").triggered.connect(
                    lambda: self._novo_projeto(d["id"])
                )
                menu.addAction("Renomear cliente").triggered.connect(
                    lambda: self._renomear_cliente(d["id"], item)
                )
                menu.addAction("Excluir cliente").triggered.connect(
                    lambda: self._excluir_cliente(d["id"])
                )

            elif tipo == NODE_PROJETO:
                menu.addAction("Nova regra").triggered.connect(
                    lambda: self._nova_regra(d["id"])
                )
                menu.addAction("Renomear projeto").triggered.connect(
                    lambda: self._renomear_projeto(d["id"], item)
                )
                menu.addAction("Excluir projeto").triggered.connect(
                    lambda: self._excluir_projeto(d["id"])
                )

            elif tipo == NODE_REGRA:
                menu.addAction("Excluir regra").triggered.connect(
                    lambda: self._excluir_regra(d["id"])
                )

            menu.addSeparator()
            menu.addAction("Novo cliente").triggered.connect(self._novo_cliente)

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    # --- Ações ---

    def _novo_cliente(self):
        dlg = DialogCliente(self)
        if dlg.exec() and dlg.nome:
            try:
                M.criar_cliente(self.conn, dlg.nome)
                self.carregar()
            except Exception as e:
                QMessageBox.warning(self, "Erro", str(e))

    def _renomear_cliente(self, cliente_id, _item):
        dlg = DialogCliente(self)
        if dlg.exec() and dlg.nome:
            M.renomear_cliente(self.conn, cliente_id, dlg.nome)
            self.carregar()

    def _excluir_cliente(self, cliente_id):
        if QMessageBox.question(self, "Confirmar", "Excluir cliente e todos os dados?") \
                == QMessageBox.StandardButton.Yes:
            M.deletar_cliente(self.conn, cliente_id)
            self.carregar()

    def _novo_projeto(self, cliente_id):
        dlg = DialogProjeto(self)
        if dlg.exec() and dlg.nome:
            try:
                M.criar_projeto(self.conn, cliente_id, dlg.nome, dlg.tipo)
                self.carregar()
            except Exception as e:
                QMessageBox.warning(self, "Erro", str(e))

    def _renomear_projeto(self, projeto_id, _item):
        dlg = DialogProjeto(self)
        if dlg.exec() and dlg.nome:
            M.renomear_projeto(self.conn, projeto_id, dlg.nome)
            self.carregar()

    def _excluir_projeto(self, projeto_id):
        if QMessageBox.question(self, "Confirmar", "Excluir projeto e todas as regras?") \
                == QMessageBox.StandardButton.Yes:
            M.deletar_projeto(self.conn, projeto_id)
            self.carregar()

    def _nova_regra(self, projeto_id):
        dlg = DialogRegra(self)
        if dlg.exec() and dlg.numero:
            try:
                regra = M.criar_regra(self.conn, projeto_id, dlg.numero, dlg.descricao)
                M.criar_versao(self.conn, regra.id)
                self.carregar()
            except Exception as e:
                QMessageBox.warning(self, "Erro", str(e))

    def _excluir_regra(self, regra_id):
        if QMessageBox.question(self, "Confirmar", "Excluir regra e todas as versões?") \
                == QMessageBox.StandardButton.Yes:
            M.deletar_regra(self.conn, regra_id)
            self.carregar()
