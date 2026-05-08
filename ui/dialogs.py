from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QTextEdit, QLabel, QVBoxLayout, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont


class DialogCliente(QDialog):
    def __init__(self, parent=None, nome_atual: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Cliente")
        self.setMinimumWidth(300)
        layout = QFormLayout(self)
        self.campo_nome = QLineEdit(nome_atual)
        layout.addRow("Nome:", self.campo_nome)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addRow(botoes)

    @property
    def nome(self) -> str:
        return self.campo_nome.text().strip()


class DialogProjeto(QDialog):
    def __init__(self, parent=None, nome_atual: str = "", tipo_atual: str = "DID"):
        super().__init__(parent)
        self.setWindowTitle("Projeto / DID")
        self.setMinimumWidth(300)
        layout = QFormLayout(self)
        self.campo_nome = QLineEdit(nome_atual)
        self.campo_tipo = QComboBox()
        self.campo_tipo.addItems(["DID", "Projeto"])
        self.campo_tipo.setCurrentText(tipo_atual)
        layout.addRow("Nome:", self.campo_nome)
        layout.addRow("Tipo:", self.campo_tipo)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addRow(botoes)

    @property
    def nome(self) -> str:
        return self.campo_nome.text().strip()

    @property
    def tipo(self) -> str:
        return self.campo_tipo.currentText()


class DialogRegra(QDialog):
    def __init__(self, parent=None, numero_atual: str = "", descricao_atual: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Regra")
        self.setMinimumWidth(320)
        layout = QFormLayout(self)
        self.campo_numero = QLineEdit(numero_atual)
        self.campo_numero.setPlaceholderText("ex: 800")
        self.campo_descricao = QLineEdit(descricao_atual)
        self.campo_descricao.setPlaceholderText("Descrição opcional")
        layout.addRow("Número:", self.campo_numero)
        layout.addRow("Descrição:", self.campo_descricao)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addRow(botoes)

    @property
    def numero(self) -> str:
        return self.campo_numero.text().strip()

    @property
    def descricao(self) -> str:
        return self.campo_descricao.text().strip()


TIPO_CORES = {
    "Criação":     ("#1A3A1A", "#73C991"),
    "Correção":    ("#1A2A3A", "#569CD6"),
    "Melhoria":    ("#3A2E00", "#E5C07B"),
    "Refatoração": ("#2E1A3A", "#C586C0"),
}


class DialogVersao(QDialog):
    def __init__(self, parent=None, tipo_sugerido: str = "Melhoria", numero_versao: int = None):
        super().__init__(parent)
        from database.models import TIPOS_VERSAO
        self.setWindowTitle("Nova Versão")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Cabeçalho com número da versão
        if numero_versao is not None:
            lbl_num = QLabel(f"Versão  {numero_versao}")
            lbl_num.setStyleSheet("font-size: 18px; font-weight: bold; color: #D4D4D4;")
            layout.addWidget(lbl_num)

        # Tipo detectado automaticamente
        lbl_tipo = QLabel("Tipo detectado automaticamente:")
        lbl_tipo.setStyleSheet("color: #858585; font-size: 11px;")
        layout.addWidget(lbl_tipo)

        self.combo_tipo = QComboBox()
        self.combo_tipo.addItems(TIPOS_VERSAO)
        self.combo_tipo.setCurrentText(tipo_sugerido)
        self.combo_tipo.currentTextChanged.connect(self._atualizar_badge)
        layout.addWidget(self.combo_tipo)

        self.label_badge = QLabel("")
        self.label_badge.setTextFormat(Qt.TextFormat.RichText)
        self.label_badge.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.label_badge)
        self._atualizar_badge(tipo_sugerido)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #3A3A3A;")
        layout.addWidget(sep)

        lbl_notas = QLabel("Notas (opcional):")
        lbl_notas.setStyleSheet("color: #858585; font-size: 11px;")
        layout.addWidget(lbl_notas)

        self.campo_notas = QTextEdit()
        self.campo_notas.setMaximumHeight(90)
        self.campo_notas.setPlaceholderText("Descreva o que foi alterado nesta versão...")
        layout.addWidget(self.campo_notas)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

        self.setStyleSheet("""
            QDialog { background-color: #1E1E1E; color: #D4D4D4; }
            QLabel  { color: #D4D4D4; font-family: Segoe UI; }
            QComboBox, QTextEdit {
                background-color: #3C3C3C; border: 1px solid #555;
                color: #D4D4D4; padding: 4px 8px; border-radius: 4px;
            }
            QPushButton {
                background-color: #0E639C; color: white;
                border: none; padding: 5px 16px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #1177BB; }
        """)

    def _atualizar_badge(self, tipo: str):
        bg, fg = TIPO_CORES.get(tipo, ("#333", "#D4D4D4"))
        self.label_badge.setText(
            f'<span style="background-color:{bg}; color:{fg}; '
            f'padding: 2px 10px; border-radius: 4px; font-size:12px;">'
            f'&nbsp;{tipo}&nbsp;</span>'
        )

    @property
    def tipo(self) -> str:
        return self.combo_tipo.currentText()

    @property
    def notas(self) -> str:
        return self.campo_notas.toPlainText().strip()
