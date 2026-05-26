from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QTextEdit, QLabel, QVBoxLayout, QFrame, QHBoxLayout,
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
    _PLACEHOLDERS = {
        "DID":        "ex: 2425",
        "Projeto":    "ex: RH, Folha de Pagamento",
        "Regra":      "ex: Sistema, Módulo",
        "Webservice": "ex: API de Integração",
        "Relatório":  "ex: Balancete, Extrato",
    }

    def __init__(self, parent=None, nome_atual: str = "", tipo_atual: str = "DID", descricao_atual: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Novo projeto")
        self.setMinimumWidth(320)

        layout = QFormLayout(self)
        layout.setSpacing(10)

        self.campo_tipo = QComboBox()
        self.campo_tipo.addItems(["DID", "Projeto", "Regra", "Webservice", "Relatório"])
        self.campo_tipo.setCurrentText(tipo_atual)
        layout.addRow("Tipo:", self.campo_tipo)

        self.campo_nome = QLineEdit(nome_atual)
        self._label_nome_row = QLabel("Nome:")
        layout.addRow(self._label_nome_row, self.campo_nome)

        self.campo_descricao = QLineEdit(descricao_atual)
        self.campo_descricao.setPlaceholderText("Descrição opcional")
        self._label_descricao_row = QLabel("Descrição:")
        layout.addRow(self._label_descricao_row, self.campo_descricao)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addRow(botoes)

        self.campo_tipo.currentTextChanged.connect(self._atualizar_campos)
        self._atualizar_campos(tipo_atual)

        self.setStyleSheet("""
            QDialog { background-color: #1E1E1E; color: #D4D4D4; }
            QLabel  { color: #D4D4D4; font-family: Segoe UI; }
            QLineEdit, QComboBox {
                background-color: #3C3C3C; border: 1px solid #555;
                color: #D4D4D4; padding: 4px 8px; border-radius: 4px;
            }
            QPushButton {
                background-color: #0E639C; color: white;
                border: none; padding: 5px 16px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #1177BB; }
        """)

    def _atualizar_campos(self, tipo: str):
        self.campo_nome.setPlaceholderText(self._PLACEHOLDERS.get(tipo, ""))
        is_regra = (tipo == "Regra")
        self._label_descricao_row.setVisible(is_regra)
        self.campo_descricao.setVisible(is_regra)

    @property
    def nome(self) -> str:
        return self.campo_nome.text().strip()

    @property
    def tipo(self) -> str:
        return self.campo_tipo.currentText()

    @property
    def descricao(self) -> str:
        return self.campo_descricao.text().strip()


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


# Estrutura fixa de seções e sub-seções de um Relatório
ESTRUTURA_RELATORIO: dict[str, list[str]] = {
    "Titulo":            ["Antes de Imprimir", "Depois de Imprimir"],
    "Cabeçalho":         ["Antes de Imprimir", "Depois de Imprimir"],
    "Cabeçalho Colunas": ["Antes de Imprimir", "Depois de Imprimir"],
    "Subtitulo":         ["Antes de Imprimir", "Depois de Imprimir"],
    "Detalhe":           ["Antes de Imprimir", "Depois de Imprimir"],
    "Subtotal":          ["Antes de Imprimir", "Depois de Imprimir"],
    "Total Geral":       ["Antes de Imprimir", "Depois de Imprimir"],
    "Rodapé Titulo":     ["Antes de Imprimir", "Depois de Imprimir"],
    "Rodapé Cabeçalho":  ["Antes de Imprimir", "Depois de Imprimir"],
    "Adicional":         ["Antes de Imprimir", "Depois de Imprimir"],
    "Página de Fundo":   ["Antes de Imprimir", "Depois de Imprimir"],
    "Pré-Seleção":       ["Antes de Imprimir", "Depois de Imprimir"],
    "Seleção":           [],
    "Inicialização":     [],
    "Finalização":       [],
    "Funções Globais":   [],
    "Imprimir Página":   [],
    "Campo Descrição":   ["Na Impressão"],
    "Campo Cadastro":    ["Na Impressão"],
    "Campo Fórmula":     ["Na Impressão"],
    "Campo Totalizador": ["Na Impressão"],
    "Campo Sistema":     ["Na Impressão"],
}


class DialogRegraRelatorio(QDialog):
    def __init__(self, parent=None, numero_atual: str = "", descricao_atual: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Seção do Relatório")
        self.setMinimumWidth(360)

        layout = QFormLayout(self)
        layout.setSpacing(10)

        self.combo_secao = QComboBox()
        self.combo_secao.addItems(list(ESTRUTURA_RELATORIO.keys()))
        layout.addRow("Seção:", self.combo_secao)

        self._label_subsecao = QLabel("Evento:")
        self.combo_subsecao = QComboBox()
        layout.addRow(self._label_subsecao, self.combo_subsecao)

        self.campo_descricao = QLineEdit(descricao_atual)
        self.campo_descricao.setPlaceholderText("Descrição opcional")
        layout.addRow("Descrição:", self.campo_descricao)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addRow(botoes)

        self.combo_secao.currentTextChanged.connect(self._atualizar_subsecao)

        # Restaura seleção a partir do número salvo
        if numero_atual and " / " in numero_atual:
            secao, subsecao = numero_atual.split(" / ", 1)
            self.combo_secao.setCurrentText(secao)
            self._atualizar_subsecao(secao)
            self.combo_subsecao.setCurrentText(subsecao)
        elif numero_atual:
            self.combo_secao.setCurrentText(numero_atual)
            self._atualizar_subsecao(numero_atual)
        else:
            self._atualizar_subsecao(self.combo_secao.currentText())

        self.setStyleSheet("""
            QDialog { background-color: #1E1E1E; color: #D4D4D4; }
            QLabel  { color: #D4D4D4; font-family: Segoe UI; }
            QLineEdit, QComboBox {
                background-color: #3C3C3C; border: 1px solid #555;
                color: #D4D4D4; padding: 4px 8px; border-radius: 4px;
            }
            QPushButton {
                background-color: #0E639C; color: white;
                border: none; padding: 5px 16px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #1177BB; }
        """)

    def _atualizar_subsecao(self, secao: str):
        subsecoes = ESTRUTURA_RELATORIO.get(secao, [])
        self.combo_subsecao.clear()
        self.combo_subsecao.addItems(subsecoes)
        tem = bool(subsecoes)
        self._label_subsecao.setVisible(tem)
        self.combo_subsecao.setVisible(tem)

    @property
    def numero(self) -> str:
        secao = self.combo_secao.currentText()
        if ESTRUTURA_RELATORIO.get(secao):
            return f"{secao} / {self.combo_subsecao.currentText()}"
        return secao

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


_STATUS_CORES = {
    "Em desenvolvimento": "#569CD6",
    "Em teste":           "#DCDCAA",
    "Produção":           "#4EC9B0",
    "Depreciada":         "#808080",
}


class DialogEditarVersao(QDialog):
    def __init__(self, parent=None, versao=None):
        super().__init__(parent)
        from database.models import TIPOS_VERSAO
        self.setWindowTitle(f"Editar Versão {versao.numero}" if versao else "Editar Versão")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        if versao is not None:
            lbl_num = QLabel(f"Versão  {versao.numero}")
            lbl_num.setStyleSheet("font-size: 18px; font-weight: bold; color: #D4D4D4;")
            layout.addWidget(lbl_num)

        # Tipo
        lbl_tipo = QLabel("Tipo:")
        lbl_tipo.setStyleSheet("color: #858585; font-size: 11px;")
        layout.addWidget(lbl_tipo)

        self.combo_tipo = QComboBox()
        self.combo_tipo.addItems(TIPOS_VERSAO)
        if versao:
            self.combo_tipo.setCurrentText(versao.tipo)
        self.combo_tipo.currentTextChanged.connect(self._atualizar_badge)
        layout.addWidget(self.combo_tipo)

        self.label_badge = QLabel("")
        self.label_badge.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.label_badge)
        self._atualizar_badge(self.combo_tipo.currentText())

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("color: #3A3A3A;")
        layout.addWidget(sep1)

        # Status
        lbl_status = QLabel("Status:")
        lbl_status.setStyleSheet("color: #858585; font-size: 11px;")
        layout.addWidget(lbl_status)

        self.combo_status = QComboBox()
        self.combo_status.addItems(list(_STATUS_CORES.keys()))
        if versao:
            self.combo_status.setCurrentText(versao.status)
        layout.addWidget(self.combo_status)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #3A3A3A;")
        layout.addWidget(sep2)

        # Notas
        lbl_notas = QLabel("Notas (opcional):")
        lbl_notas.setStyleSheet("color: #858585; font-size: 11px;")
        layout.addWidget(lbl_notas)

        self.campo_notas = QTextEdit()
        self.campo_notas.setMaximumHeight(90)
        self.campo_notas.setPlaceholderText("Descreva o que foi alterado nesta versão...")
        if versao:
            self.campo_notas.setPlainText(versao.notas or "")
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
    def status(self) -> str:
        return self.combo_status.currentText()

    @property
    def notas(self) -> str:
        return self.campo_notas.toPlainText().strip()
