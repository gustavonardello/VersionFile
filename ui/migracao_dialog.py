"""
Fluxo de primeira execução após a mudança do local dos dados.

Cobre as três situações possíveis quando o app abre:
  1. Já existe banco no local definitivo  → segue direto
  2. Existe banco na pasta do .exe        → copia e avisa onde ficou
  3. Não achou banco em lugar nenhum      → pergunta ao usuário

O caso 3 existe porque o usuário pode ter baixado o .exe novo numa pasta
diferente da que usava antes; sem perguntar, o app criaria um banco vazio e
daria a impressão de que os dados sumiram.
"""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox,
)

from core.migration import (
    Estado, detectar_estado, banco_legado, banco_atual,
    eh_banco_versionfile, importar_de, NOME_BANCO,
)
from core.paths import data_path, legacy_data_path

ESTILO = """
    QDialog, QWidget { background-color: #1E1E1E; color: #D4D4D4; }
    QLabel { font-family: Segoe UI; font-size: 12px; }
    QPushButton {
        background-color: #0E639C;
        color: white;
        border: none;
        padding: 7px 14px;
        border-radius: 2px;
        font-family: Segoe UI;
    }
    QPushButton:hover   { background-color: #1177BB; }
    QPushButton:pressed { background-color: #0A4F82; }
    QPushButton#secundario { background-color: #3C3C3C; border: 1px solid #555; }
    QPushButton#secundario:hover { background-color: #4A4A4A; }
"""


class LocalizarDadosDialog(QDialog):
    """Pergunta ao usuário se ele já usava o app e, se sim, onde está o banco."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VersionFile — Localizar seus dados")
        self.setStyleSheet(ESTILO)
        self.setMinimumWidth(560)
        self.origem_escolhida: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        titulo = QLabel("Onde estão os seus dados?")
        titulo.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFFFFF;")
        layout.addWidget(titulo)

        explicacao = QLabel(
            "A partir desta versão, o VersionFile guarda o banco de dados numa "
            "pasta fixa do seu usuário, separada do programa. Assim, atualizar "
            "ou reinstalar o app nunca mais mexe nas suas regras.\n\n"
            f"Novo local:\n{data_path()}\n\n"
            "Não encontramos um banco existente. Se você já usava o VersionFile, "
            "localize o arquivo <b>versionfile.db</b> que fica na pasta onde você "
            "abria o programa antes — ele será <b>copiado</b> para o novo local, "
            "sem ser apagado nem alterado."
        )
        explicacao.setWordWrap(True)
        explicacao.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(explicacao)

        layout.addSpacing(4)

        botoes = QHBoxLayout()
        botoes.setSpacing(10)

        btn_localizar = QPushButton("Já usei antes — localizar meu banco...")
        btn_localizar.clicked.connect(self._localizar)
        botoes.addWidget(btn_localizar)

        btn_novo = QPushButton("É a primeira vez que uso")
        btn_novo.setObjectName("secundario")
        btn_novo.clicked.connect(self._comecar_do_zero)
        botoes.addWidget(btn_novo)

        botoes.addStretch()
        layout.addLayout(botoes)

    def _localizar(self):
        inicial = legacy_data_path() or Path.home()
        caminho, _ = QFileDialog.getOpenFileName(
            self,
            "Selecione o arquivo versionfile.db",
            str(inicial),
            f"Banco do VersionFile ({NOME_BANCO});;Todos os arquivos (*)",
        )
        if not caminho:
            return

        escolhido = Path(caminho)
        if not eh_banco_versionfile(escolhido):
            _aviso(
                self,
                "Arquivo inválido",
                "Esse arquivo não parece ser um banco do VersionFile.\n\n"
                "Procure por um arquivo chamado versionfile.db na pasta onde "
                "você abria o programa antes.",
            )
            return

        self.origem_escolhida = escolhido
        self.accept()

    def _comecar_do_zero(self):
        self.origem_escolhida = None
        self.accept()


def _aviso(parent, titulo: str, texto: str, icone=QMessageBox.Icon.Warning):
    caixa = QMessageBox(parent)
    caixa.setIcon(icone)
    caixa.setWindowTitle(titulo)
    caixa.setText(texto)
    caixa.setStyleSheet(ESTILO)
    caixa.exec()


def garantir_dados(parent=None) -> bool:
    """
    Resolve a localização dos dados antes do banco ser aberto.

    Retorna False quando o usuário fecha o diálogo sem escolher — nesse caso o
    app deve encerrar sem criar banco nenhum, para que a pergunta reapareça na
    próxima abertura em vez de o usuário ficar preso a um banco vazio.
    """
    estado = detectar_estado()

    if estado in (Estado.NAO_SE_APLICA, Estado.JA_NO_LUGAR):
        return True

    if estado is Estado.LEGADO_ENCONTRADO:
        origem = banco_legado()
        try:
            copiados = importar_de(origem)
        except OSError as erro:
            _aviso(
                parent,
                "Falha ao copiar seus dados",
                f"Não foi possível copiar seus dados para o novo local.\n\n"
                f"Origem: {origem}\nDestino: {data_path()}\n\nErro: {erro}\n\n"
                "Seus dados originais continuam intactos. Tente abrir o "
                "programa como administrador ou entre em contato com o suporte.",
                QMessageBox.Icon.Critical,
            )
            return False

        if copiados:
            _aviso(
                parent,
                "Dados movidos para um local seguro",
                "Seus dados foram copiados para uma pasta fixa do seu usuário, "
                "separada do programa. Atualizações do VersionFile não vão mais "
                "encostar neles.\n\n"
                f"Novo local:\n{data_path()}\n\n"
                f"Os arquivos originais continuam intactos em:\n{origem.parent}\n\n"
                "Confira se suas regras estão todas aí. Depois disso, pode "
                "apagar os arquivos antigos se quiser.",
                QMessageBox.Icon.Information,
            )
        return True

    # Estado.NADA_ENCONTRADO
    dlg = LocalizarDadosDialog(parent)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return False

    if dlg.origem_escolhida is None:
        data_path().mkdir(parents=True, exist_ok=True)
        return True

    try:
        importar_de(dlg.origem_escolhida)
    except OSError as erro:
        _aviso(
            parent,
            "Falha ao copiar seus dados",
            f"Não foi possível copiar o banco selecionado.\n\n"
            f"Origem: {dlg.origem_escolhida}\nDestino: {data_path()}\n\n"
            f"Erro: {erro}\n\nO arquivo original continua intacto.",
            QMessageBox.Icon.Critical,
        )
        return False

    _aviso(
        parent,
        "Dados importados",
        f"Seus dados foram copiados para:\n{data_path()}\n\n"
        f"O arquivo original continua intacto em:\n{dlg.origem_escolhida}",
        QMessageBox.Icon.Information,
    )
    return True
