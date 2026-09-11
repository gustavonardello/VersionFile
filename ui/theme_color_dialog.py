from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QColorDialog, QFrame,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt

from core.highlighter import load_theme, salvar_cores_tema

ELEMENTOS = [
    ("background",        "Fundo"),
    ("foreground",        "Texto padrão"),
    ("keyword",           "Palavra-chave"),
    ("function",          "Função"),
    ("type",              "Tipo"),
    ("number",            "Número"),
    ("string",            "String"),
    ("comment",           "Comentário"),
    ("operator",          "Operador"),
    ("identifier",        "Identificador"),
    ("constant",          "Constante"),
    ("caret_line",        "Linha do cursor"),
    ("selection",         "Seleção"),
    ("margin_background", "Margem (fundo)"),
    ("margin_foreground", "Margem (texto)"),
]


def _contraste(hex_color: str) -> str:
    """Retorna preto ou branco dependendo da luminância do fundo."""
    c = QColor(hex_color)
    lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return "#000000" if lum > 128 else "#FFFFFF"


class ThemeColorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Personalizar cores do editor")
        self.resize(420, 520)
        self._cores: dict = {}
        self._botoes: dict[str, QPushButton] = {}
        self._carregar_cores()
        self._build_ui()
        self._aplicar_estilo()

    def _carregar_cores(self):
        tema = load_theme()
        self._cores = dict(tema)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        lbl = QLabel("Clique em uma cor para alterá-la:")
        lbl.setStyleSheet("color:#858585; font-size:11px;")
        layout.addWidget(lbl)

        grid = QGridLayout()
        grid.setSpacing(6)

        for row, (chave, label) in enumerate(ELEMENTOS):
            lbl_nome = QLabel(label)
            lbl_nome.setFixedWidth(160)
            grid.addWidget(lbl_nome, row, 0)

            btn = QPushButton()
            btn.setFixedSize(140, 26)
            btn.setProperty("chave", chave)
            btn.clicked.connect(lambda _, k=chave: self._escolher_cor(k))
            self._botoes[chave] = btn
            self._atualizar_botao(chave)
            grid.addWidget(btn, row, 1)

        layout.addLayout(grid)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#444;")
        layout.addWidget(sep)

        row_btn = QHBoxLayout()
        row_btn.addStretch()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setObjectName("btnSecundario")
        btn_cancelar.clicked.connect(self.reject)
        row_btn.addWidget(btn_cancelar)
        btn_salvar = QPushButton("Salvar")
        btn_salvar.clicked.connect(self._salvar)
        row_btn.addWidget(btn_salvar)
        layout.addLayout(row_btn)

    def _atualizar_botao(self, chave: str):
        cor = self._cores.get(chave, "#888888")
        btn = self._botoes[chave]
        texto_cor = _contraste(cor)
        btn.setText(cor.upper())
        btn.setStyleSheet(
            f"background-color: {cor}; color: {texto_cor}; "
            f"border: 1px solid #555; border-radius: 2px; font-family: Consolas; font-size: 11px;"
        )

    def _escolher_cor(self, chave: str):
        cor_atual = QColor(self._cores.get(chave, "#888888"))
        cor = QColorDialog.getColor(cor_atual, self, f"Escolher cor — {chave}")
        if cor.isValid():
            self._cores[chave] = cor.name()
            self._atualizar_botao(chave)

    def _salvar(self):
        try:
            salvar_cores_tema(self._cores)
        except (OSError, ValueError) as erro:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Cores não salvas", str(erro))
            return
        self.accept()

    def _aplicar_estilo(self):
        self.setStyleSheet("""
            QDialog, QWidget { background-color: #1E1E1E; color: #D4D4D4; }
            QLabel { font-size: 12px; }
            QPushButton {
                background-color: #0E639C; color: white;
                border: none; padding: 5px 14px; border-radius: 2px;
            }
            QPushButton:hover { background-color: #1177BB; }
            QPushButton#btnSecundario {
                background-color: #3C3C3C; color: #D4D4D4;
                border: 1px solid #555;
            }
            QPushButton#btnSecundario:hover { background-color: #4A4A4A; }
        """)
