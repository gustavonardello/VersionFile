from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont

import database.models as M
from ui.errors import mostrar_erro

STATUS_CORES = {
    "Em desenvolvimento": "#569CD6",
    "Em teste":           "#DCDCAA",
    "Produção":           "#4EC9B0",
    "Depreciada":         "#808080",
}

TIPO_CORES = {
    "Criação":     "#73C991",
    "Correção":    "#569CD6",
    "Melhoria":    "#E5C07B",
    "Refatoração": "#C586C0",
}


class CartaoVersao(QFrame):
    """Card visual de uma versão."""
    selecionada = pyqtSignal(object)   # Versao
    excluir     = pyqtSignal(object)   # Versao

    def __init__(self, versao, total_versoes: int, parent=None):
        super().__init__(parent)
        self.versao = versao
        self._build(total_versoes)

    def _build(self, total_versoes: int):
        self.setObjectName("cartao")
        self.setFixedHeight(72)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # Número em destaque
        lbl_num = QLabel(str(self.versao.numero))
        lbl_num.setFixedWidth(32)
        lbl_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_num.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #D4D4D4; font-family: Consolas;"
        )
        layout.addWidget(lbl_num)

        # Separador vertical
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #3A3A3A;")
        layout.addWidget(sep)

        # Info central
        info = QVBoxLayout()
        info.setSpacing(3)

        # Linha 1: tipo + [atual]
        linha1 = QHBoxLayout()
        linha1.setSpacing(6)
        cor_tipo = TIPO_CORES.get(self.versao.tipo, "#D4D4D4")
        lbl_tipo = QLabel(self.versao.tipo)
        lbl_tipo.setStyleSheet(
            f"color: {cor_tipo}; font-weight: bold; font-size: 12px;"
        )
        linha1.addWidget(lbl_tipo)

        if self.versao.atual:
            lbl_atual = QLabel("atual")
            lbl_atual.setStyleSheet(
                "background: #0E639C; color: white; font-size: 10px;"
                "padding: 1px 6px; border-radius: 3px;"
            )
            linha1.addWidget(lbl_atual)
        linha1.addStretch()
        info.addLayout(linha1)

        # Linha 2: status + data
        linha2 = QHBoxLayout()
        linha2.setSpacing(8)
        cor_status = STATUS_CORES.get(self.versao.status, "#858585")
        lbl_status = QLabel(self.versao.status)
        lbl_status.setStyleSheet(f"color: {cor_status}; font-size: 11px;")
        linha2.addWidget(lbl_status)

        lbl_data = QLabel(self.versao.criado_em[:16])
        lbl_data.setStyleSheet("color: #585858; font-size: 11px;")
        linha2.addWidget(lbl_data)
        linha2.addStretch()
        info.addLayout(linha2)

        # Notas (se houver)
        if self.versao.notas:
            lbl_notas = QLabel(self.versao.notas[:60] + ("…" if len(self.versao.notas) > 60 else ""))
            lbl_notas.setStyleSheet("color: #585858; font-size: 10px; font-style: italic;")
            info.addWidget(lbl_notas)

        layout.addLayout(info)
        layout.addStretch()

        # Botões
        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)

        btn_carregar = QPushButton("Carregar")
        btn_carregar.setFixedWidth(80)
        btn_carregar.setStyleSheet(
            "QPushButton { background: #0E639C; color: white; border: none;"
            "padding: 3px 8px; border-radius: 3px; font-size: 11px; }"
            "QPushButton:hover { background: #1177BB; }"
        )
        btn_carregar.clicked.connect(lambda: self.selecionada.emit(self.versao))
        btn_col.addWidget(btn_carregar)

        if total_versoes > 1:
            btn_excluir = QPushButton("Excluir")
            btn_excluir.setFixedWidth(80)
            btn_excluir.setStyleSheet(
                "QPushButton { background: transparent; color: #F48771;"
                "border: 1px solid #5A2A2A; padding: 3px 8px; border-radius: 3px; font-size: 11px; }"
                "QPushButton:hover { background: #3A1A1A; }"
            )
            btn_excluir.clicked.connect(lambda: self.excluir.emit(self.versao))
            btn_col.addWidget(btn_excluir)

        layout.addLayout(btn_col)

        # Estilo do card
        bg = "#2A2A2A" if self.versao.atual else "#252526"
        border = "#0E639C" if self.versao.atual else "#3A3A3A"
        self.setStyleSheet(f"""
            QFrame#cartao {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
        """)


class VersionHistory(QDialog):
    versao_carregada = pyqtSignal(int)   # versao_id

    def __init__(self, conn, regra_id: int, regra_label: str = "", parent=None):
        super().__init__(parent)
        self.conn = conn
        self.regra_id = regra_id
        self.setWindowTitle(f"Histórico de versões — {regra_label}")
        self.resize(560, 480)
        self._build_ui()
        self._aplicar_estilo()
        self._carregar()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.label_total = QLabel("")
        self.label_total.setStyleSheet("color: #858585; font-size: 11px;")
        layout.addWidget(self.label_total)

        # Área de scroll com os cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.container = QWidget()
        self.cards_layout = QVBoxLayout(self.container)
        self.cards_layout.setSpacing(6)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.addStretch()

        scroll.setWidget(self.container)
        layout.addWidget(scroll)

        btn_fechar = QPushButton("Fechar")
        btn_fechar.clicked.connect(self.accept)
        btn_fechar.setFixedWidth(100)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn_fechar)
        layout.addLayout(row)

    def _carregar(self):
        # Remove cards antigos (exceto o stretch no final)
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        versoes = M.listar_versoes(self.conn, self.regra_id)
        total = len(versoes)
        self.label_total.setText(f"{total} versão(ões) registrada(s)")

        for versao in versoes:
            card = CartaoVersao(versao, total, self.container)
            card.selecionada.connect(self._on_carregar)
            card.excluir.connect(self._on_excluir)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

    def _on_carregar(self, versao):
        self.versao_carregada.emit(versao.id)
        self.accept()

    def _on_excluir(self, versao):
        resp = QMessageBox.question(
            self, "Excluir versão",
            f"Excluir versão {versao.numero} ({versao.tipo})?\nEsta ação não pode ser desfeita.",
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        try:
            M.deletar_versao(self.conn, versao.id)
        except Exception as erro:
            mostrar_erro(self, "Versão não excluída", erro)
            return

        self._carregar()

    def _aplicar_estilo(self):
        self.setStyleSheet("""
            QDialog, QWidget { background-color: #1E1E1E; color: #D4D4D4; }
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: #252526; width: 8px; }
            QScrollBar::handle:vertical { background: #555; border-radius: 4px; }
            QPushButton {
                background-color: #0E639C; color: white;
                border: none; padding: 5px 16px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #1177BB; }
            QLabel { font-family: Segoe UI; background: transparent; }
        """)
