from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QTreeWidget, QTreeWidgetItem, QLineEdit,
    QComboBox, QMessageBox, QFrame, QCheckBox, QAbstractItemView,
    QProgressDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

import database.models as M

VERSAO_OPTS = ["Atual", "Mais recente", "Todas as versões"]


class ExportDialog(QDialog):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("Exportar múltiplas regras")
        self.resize(700, 520)
        self._build_ui()
        self._aplicar_estilo()
        self._carregar_arvore()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Opções de exportação
        row_opts = QHBoxLayout()
        row_opts.addWidget(QLabel("Exportar versão:"))
        self.combo_versao = QComboBox()
        self.combo_versao.addItems(VERSAO_OPTS)
        row_opts.addWidget(self.combo_versao)

        row_opts.addSpacing(20)
        row_opts.addWidget(QLabel("Extensão:"))
        self.combo_ext = QComboBox()
        self.combo_ext.addItems([".lsp", ".txt"])
        row_opts.addWidget(self.combo_ext)

        row_opts.addSpacing(20)
        self.check_subpastas = QCheckBox("Recriar estrutura de pastas")
        self.check_subpastas.setChecked(True)
        self.check_subpastas.setToolTip(
            "Cria subpastas Cliente/Projeto/Regra no destino.\n"
            "Desmarcado: todos os arquivos na mesma pasta."
        )
        row_opts.addWidget(self.check_subpastas)
        row_opts.addStretch()
        layout.addLayout(row_opts)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Árvore de seleção
        layout.addWidget(QLabel("Selecione as regras a exportar:"))

        row_sel = QHBoxLayout()
        btn_todos = QPushButton("Selecionar tudo")
        btn_todos.clicked.connect(self._selecionar_todos)
        btn_nenhum = QPushButton("Limpar seleção")
        btn_nenhum.clicked.connect(self._limpar_selecao)
        row_sel.addWidget(btn_todos)
        row_sel.addWidget(btn_nenhum)
        row_sel.addStretch()
        layout.addLayout(row_sel)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Regra", "Versões"])
        self.tree.setColumnWidth(0, 420)
        self.tree.itemChanged.connect(self._propagar_check)
        layout.addWidget(self.tree)

        self.label_sel = QLabel("0 regra(s) selecionada(s)")
        self.label_sel.setStyleSheet("color:#858585; font-size:11px;")
        layout.addWidget(self.label_sel)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep2)

        # Pasta de destino
        row_dest = QHBoxLayout()
        row_dest.addWidget(QLabel("Pasta de destino:"))
        self.campo_dest = QLineEdit()
        self.campo_dest.setReadOnly(True)
        self.campo_dest.setPlaceholderText("Selecione a pasta onde os arquivos serão salvos...")
        row_dest.addWidget(self.campo_dest)
        btn_browse = QPushButton("Procurar...")
        btn_browse.clicked.connect(self._selecionar_destino)
        row_dest.addWidget(btn_browse)
        layout.addLayout(row_dest)

        # Botões
        row_btn = QHBoxLayout()
        row_btn.addStretch()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.clicked.connect(self.reject)
        row_btn.addWidget(btn_cancelar)
        self.btn_exportar = QPushButton("Exportar")
        self.btn_exportar.clicked.connect(self._exportar)
        row_btn.addWidget(self.btn_exportar)
        layout.addLayout(row_btn)

    def _carregar_arvore(self):
        self.tree.blockSignals(True)
        self.tree.clear()

        for cliente in M.listar_clientes(self.conn):
            node_c = QTreeWidgetItem([cliente.nome, ""])
            node_c.setCheckState(0, Qt.CheckState.Unchecked)
            node_c.setForeground(0, QColor("#1080C0"))
            node_c.setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))
            node_c.setData(0, Qt.ItemDataRole.UserRole, {"tipo": "cliente", "id": cliente.id})

            for projeto in M.listar_projetos(self.conn, cliente.id):
                node_p = QTreeWidgetItem([f"[{projeto.tipo}] {projeto.nome}", ""])
                node_p.setCheckState(0, Qt.CheckState.Unchecked)
                node_p.setForeground(0, QColor("#6B6B00"))
                node_p.setData(0, Qt.ItemDataRole.UserRole, {"tipo": "projeto", "id": projeto.id})

                for regra in M.listar_regras(self.conn, projeto.id):
                    versoes = M.listar_versoes(self.conn, regra.id)
                    desc = f" — {regra.descricao}" if regra.descricao else ""
                    node_r = QTreeWidgetItem([
                        f"Regra {regra.numero}{desc}",
                        str(len(versoes)),
                    ])
                    node_r.setCheckState(0, Qt.CheckState.Unchecked)
                    node_r.setData(0, Qt.ItemDataRole.UserRole, {
                        "tipo": "regra", "id": regra.id,
                        "numero": regra.numero,
                        "cliente": cliente.nome,
                        "projeto": projeto.nome,
                    })
                    node_p.addChild(node_r)

                node_c.addChild(node_p)
            self.tree.addTopLevelItem(node_c)

        self.tree.expandAll()
        self.tree.blockSignals(False)

    def _propagar_check(self, item: QTreeWidgetItem, col: int):
        if col != 0:
            return
        self.tree.blockSignals(True)
        estado = item.checkState(0)
        # Para baixo: propaga aos filhos
        self._set_filhos(item, estado)
        # Para cima: atualiza pai
        pai = item.parent()
        while pai:
            self._atualizar_pai(pai)
            pai = pai.parent()
        self.tree.blockSignals(False)
        self._atualizar_contador()

    def _set_filhos(self, item, estado):
        for i in range(item.childCount()):
            filho = item.child(i)
            filho.setCheckState(0, estado)
            self._set_filhos(filho, estado)

    def _atualizar_pai(self, item):
        total = item.childCount()
        marcados = sum(
            1 for i in range(total)
            if item.child(i).checkState(0) == Qt.CheckState.Checked
        )
        if marcados == 0:
            item.setCheckState(0, Qt.CheckState.Unchecked)
        elif marcados == total:
            item.setCheckState(0, Qt.CheckState.Checked)
        else:
            item.setCheckState(0, Qt.CheckState.PartiallyChecked)

    def _atualizar_contador(self):
        count = len(self._regras_selecionadas())
        self.label_sel.setText(f"{count} regra(s) selecionada(s)")

    def _regras_selecionadas(self) -> list[dict]:
        resultado = []
        for i in range(self.tree.topLevelItemCount()):
            node_c = self.tree.topLevelItem(i)
            for j in range(node_c.childCount()):
                node_p = node_c.child(j)
                for k in range(node_p.childCount()):
                    node_r = node_p.child(k)
                    if node_r.checkState(0) == Qt.CheckState.Checked:
                        resultado.append(node_r.data(0, Qt.ItemDataRole.UserRole))
        return resultado

    def _selecionar_todos(self):
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item.setCheckState(0, Qt.CheckState.Checked)
            self._set_filhos(item, Qt.CheckState.Checked)
        self.tree.blockSignals(False)
        self._atualizar_contador()

    def _limpar_selecao(self):
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            self._set_filhos(item, Qt.CheckState.Unchecked)
        self.tree.blockSignals(False)
        self._atualizar_contador()

    def _selecionar_destino(self):
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar pasta de destino")
        if pasta:
            self.campo_dest.setText(pasta)

    def _exportar(self):
        regras = self._regras_selecionadas()
        if not regras:
            QMessageBox.warning(self, "Exportar", "Selecione ao menos uma regra.")
            return
        destino = self.campo_dest.text().strip()
        if not destino:
            QMessageBox.warning(self, "Exportar", "Selecione a pasta de destino.")
            return

        destino_path = Path(destino)
        opcao_versao = self.combo_versao.currentText()
        ext = self.combo_ext.currentText()
        subpastas = self.check_subpastas.isChecked()

        progress = QProgressDialog("Exportando...", "Cancelar", 0, len(regras), self)
        progress.setWindowTitle("Exportando regras")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        exportados = 0
        erros = []

        for i, dados in enumerate(regras):
            if progress.wasCanceled():
                break
            progress.setValue(i)

            versoes = M.listar_versoes(self.conn, dados["id"])
            if not versoes:
                continue

            if opcao_versao == "Atual":
                para_exportar = [v for v in versoes if v.atual] or [versoes[0]]
            elif opcao_versao == "Mais recente":
                para_exportar = [versoes[0]]
            else:  # Todas
                para_exportar = versoes

            for versao in para_exportar:
                try:
                    if subpastas:
                        pasta_dest = destino_path / dados["cliente"] / dados["projeto"]
                    else:
                        pasta_dest = destino_path
                    pasta_dest.mkdir(parents=True, exist_ok=True)

                    sufixo = f"_v{versao.numero}" if opcao_versao == "Todas as versões" else ""
                    nome_arquivo = f"{dados['numero']}{sufixo}{ext}"
                    (pasta_dest / nome_arquivo).write_text(versao.conteudo, encoding="utf-8")
                    exportados += 1
                except Exception as e:
                    erros.append(f"{dados['numero']}: {e}")

        progress.setValue(len(regras))

        msg = f"Exportação concluída!\n\n{exportados} arquivo(s) gerado(s)."
        if erros:
            msg += f"\n\n{len(erros)} erro(s):\n" + "\n".join(erros[:5])
        QMessageBox.information(self, "Concluído", msg)
        self.accept()

    def _aplicar_estilo(self):
        self.setStyleSheet("""
            QDialog, QWidget { background-color: #FAFAFA; color: #1E1E1E; }
            QTreeWidget {
                background-color: #FFFFFF;
                border: 1px solid #CCC;
                font-family: Segoe UI;
                font-size: 12px;
            }
            QTreeWidget::item:selected { background-color: #ADD6FF; color: #000; }
            QTreeWidget::item:hover    { background-color: #EEF5FF; }
            QHeaderView::section {
                background-color: #F3F3F3; color: #555;
                border: none; padding: 2px 4px; font-size: 11px;
            }
            QLineEdit, QComboBox {
                background-color: #FFF; border: 1px solid #CCC;
                color: #1E1E1E; padding: 3px 6px; border-radius: 2px;
            }
            QPushButton {
                background-color: #0E639C; color: white;
                border: none; padding: 5px 14px; border-radius: 2px;
            }
            QPushButton:hover    { background-color: #1177BB; }
            QPushButton:disabled { background-color: #AAA; color: #EEE; }
            QCheckBox { color: #1E1E1E; }
        """)
