from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QAction, QIcon
from ui.tree_panel import TreePanel
from ui.editor_panel import EditorPanel
from ui.export_dialog import ExportDialog
from ui.import_dialog import ImportDialog
from ui.theme_color_dialog import ThemeColorDialog
from core.paths import base_path
from core.version import __version__
from core.updater import (
    verificar_atualizacao, baixar_e_instalar, InfoAtualizacao, ErroAtualizacao,
)


class _WorkerAtualizacao(QThread):
    """Verifica atualização em background, sem travar a UI."""
    resultado = pyqtSignal(object)  # InfoAtualizacao ou None
    erro = pyqtSignal(str)

    def __init__(self, forcar: bool = False):
        super().__init__()
        self._forcar = forcar

    def run(self):
        try:
            info = verificar_atualizacao(
                forcar=self._forcar,
                propagar_erros=self._forcar,
            )
            self.resultado.emit(info)
        except ErroAtualizacao as e:
            self.erro.emit(str(e))


class _WorkerDownload(QThread):
    """Baixa e instala a atualização em background."""
    progresso = pyqtSignal(int, int)  # bytes_baixados, bytes_totais
    concluido = pyqtSignal()
    erro = pyqtSignal(str)

    def __init__(self, info: InfoAtualizacao):
        super().__init__()
        self._info = info

    def run(self):
        try:
            baixar_e_instalar(self._info, on_progress=self._reportar)
            self.concluido.emit()
        except ErroAtualizacao as e:
            self.erro.emit(str(e))
        except Exception as e:
            self.erro.emit(f"Erro inesperado: {e}")

    def _reportar(self, baixados: int, total: int):
        self.progresso.emit(baixados, total)


class MainWindow(QMainWindow):
    def __init__(self, conn, checar_atualizacao: bool = True):
        super().__init__()
        self.conn = conn
        self._fechando = False
        self._checagem_manual = False
        self._worker_update = None
        self._worker_download = None
        self._dlg_atualizacao = None
        self.setWindowTitle("VersionFile — Gerenciador de Regras LSP")
        self.resize(1200, 750)

        icone = base_path() / "icone.ico"
        if icone.exists():
            self.setWindowIcon(QIcon(str(icone)))

        self._aplicar_estilo()
        self._criar_menu()

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tree_panel = TreePanel(conn)
        self.tree_panel.setMinimumWidth(220)
        self.tree_panel.setMaximumWidth(360)
        splitter.addWidget(self.tree_panel)

        self.editor_panel = EditorPanel(conn)
        splitter.addWidget(self.editor_panel)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 940])

        self.setCentralWidget(splitter)

        self._label_versao = QLabel(f"Versão {__version__}", self)
        self._label_versao.setObjectName("label_versao")
        self._label_versao.setStyleSheet("color: #9D9D9D; padding: 0 6px;")
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().addPermanentWidget(self._label_versao)

        self.tree_panel.regra_selecionada.connect(self.editor_panel.abrir_regra)
        self.tree_panel.regra_desmarcada.connect(self.editor_panel.desabilitar_acoes)

        if checar_atualizacao:
            self._iniciar_checagem_atualizacao()

    def _criar_menu(self):
        barra = self.menuBar()

        menu_arquivo = barra.addMenu("Arquivo")

        act_exportar = QAction("Exportar múltiplas regras...", self)
        act_exportar.setShortcut("Ctrl+E")
        act_exportar.triggered.connect(self._abrir_exportacao)
        menu_arquivo.addAction(act_exportar)

        act_importar = QAction("Importar estrutura de pastas...", self)
        act_importar.setShortcut("Ctrl+I")
        act_importar.triggered.connect(self._abrir_importacao)
        menu_arquivo.addAction(act_importar)

        menu_config = barra.addMenu("Configurações")
        act_cores = QAction("Personalizar cores do editor...", self)
        act_cores.triggered.connect(self._personalizar_cores)
        menu_config.addAction(act_cores)

        menu_ajuda = barra.addMenu("Ajuda")
        act_atualizar = QAction("Verificar atualizações...", self)
        act_atualizar.triggered.connect(
            lambda: self._iniciar_checagem_atualizacao(forcar=True)
        )
        menu_ajuda.addAction(act_atualizar)

        menu_arquivo.addSeparator()

        act_sair = QAction("Sair", self)
        act_sair.setShortcut("Alt+F4")
        act_sair.triggered.connect(self.close)
        menu_arquivo.addAction(act_sair)

    def closeEvent(self, event):
        if not self.editor_panel.salvar_se_pendente():
            event.ignore()
            return
        self._fechando = True
        if any(
            worker is not None and worker.isRunning()
            for worker in (getattr(self, "_worker_update", None), getattr(self, "_worker_download", None))
        ):
            event.ignore()
            QTimer.singleShot(100, self.close)
            return
        super().closeEvent(event)

    def _abrir_exportacao(self):
        dlg = ExportDialog(self.conn, parent=self)
        dlg.exec()

    def _abrir_importacao(self):
        dlg = ImportDialog(self.conn, parent=self)
        dlg.importacao_concluida.connect(self.tree_panel.carregar)
        dlg.exec()

    def _personalizar_cores(self):
        dlg = ThemeColorDialog(self)
        if dlg.exec():
            self.editor_panel.recarregar_tema()

    # -- Atualização ----------------------------------------------------------

    def _iniciar_checagem_atualizacao(self, forcar: bool = False):
        if self._worker_update is not None and self._worker_update.isRunning():
            if forcar:
                QMessageBox.information(
                    self,
                    "Verificação em andamento",
                    "A consulta de atualizações já está em andamento.",
                )
            return
        self._checagem_manual = forcar
        self._worker_update = _WorkerAtualizacao(forcar=forcar)
        self._worker_update.resultado.connect(self._tratar_resultado_atualizacao)
        self._worker_update.erro.connect(self._tratar_erro_atualizacao)
        self._worker_update.start()

    def _tratar_resultado_atualizacao(self, info: InfoAtualizacao | None):
        manual = self._checagem_manual
        self._checagem_manual = False
        if self._fechando:
            return
        if info is None:
            if manual:
                QMessageBox.information(
                    self,
                    "VersionFile atualizado",
                    "Você já está usando a versão mais recente.",
                )
            return
        self._mostrar_dialogo_atualizacao(info)

    def _tratar_erro_atualizacao(self, mensagem: str):
        manual = self._checagem_manual
        self._checagem_manual = False
        if manual and not self._fechando:
            QMessageBox.warning(self, "Falha na verificação", mensagem)

    def _mostrar_dialogo_atualizacao(self, info: InfoAtualizacao):
        if self._dlg_atualizacao is not None:
            self._dlg_atualizacao.close()
        dlg = QDialog(self)
        self._dlg_atualizacao = dlg
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dlg.destroyed.connect(lambda: setattr(self, "_dlg_atualizacao", None))
        dlg.setWindowTitle("Atualização disponível")
        dlg.setFixedSize(420, 200)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)

        lbl = QLabel(
            f"<b>Nova versão {info.versao} disponível!</b><br><br>"
            f"Tamanho: {info.tamanho_bytes / (1024 * 1024):.1f} MB"
        )
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_depois = QPushButton("Mais tarde")
        btn_depois.clicked.connect(dlg.close)
        btn_layout.addWidget(btn_depois)

        btn_baixar = QPushButton("Instalar agora")
        btn_baixar.setDefault(True)
        btn_baixar.clicked.connect(lambda: self._iniciar_download(info, dlg))
        btn_layout.addWidget(btn_baixar)

        layout.addLayout(btn_layout)
        dlg.setModal(False)
        dlg.show()

    def _iniciar_download(self, info: InfoAtualizacao, dlg_aviso: QDialog):
        dlg_aviso.close()

        # Diálogo de progresso do download
        self._dlg_progresso = QDialog(self)
        self._dlg_progresso.setWindowTitle("Atualizando...")
        self._dlg_progresso.setFixedSize(400, 120)
        self._dlg_progresso.setModal(True)

        layout = QVBoxLayout(self._dlg_progresso)
        self._lbl_progresso = QLabel("Baixando atualização...")
        layout.addWidget(self._lbl_progresso)

        self._barra_progresso = QProgressBar()
        self._barra_progresso.setRange(0, info.tamanho_bytes or 0)
        self._barra_progresso.setValue(0)
        layout.addWidget(self._barra_progresso)

        self._dlg_progresso.show()

        # Worker de download em background
        self._worker_download = _WorkerDownload(info)
        self._worker_download.progresso.connect(self._atualizar_progresso)
        self._worker_download.concluido.connect(self._download_concluido)
        self._worker_download.erro.connect(self._download_erro)
        self._worker_download.start()

    def _atualizar_progresso(self, baixados: int, total: int):
        self._barra_progresso.setValue(baixados)
        mb_baixados = baixados / (1024 * 1024)
        mb_total = total / (1024 * 1024)
        self._lbl_progresso.setText(
            f"Baixando atualização... {mb_baixados:.1f} / {mb_total:.1f} MB"
        )

    def _download_concluido(self):
        self._dlg_progresso.close()
        # Instalador já foi disparado como processo destacado.
        # Fecha o app normalmente (salva edições pendentes via closeEvent).
        self.close()

    def _download_erro(self, mensagem: str):
        self._dlg_progresso.close()
        QMessageBox.warning(
            self,
            "Erro na atualização",
            f"Não foi possível atualizar:\n\n{mensagem}\n\n"
            f"Você pode baixar manualmente em:\n"
            f"github.com/gustavonardello/VersionFile/releases",
        )

    # -- Estilo -------------------------------------------------------------

    def _aplicar_estilo(self):
        self.menuBar().setStyleSheet(
            "QMenuBar { background:#252526; color:#D4D4D4; }"
            "QMenuBar::item:selected { background:#094771; }"
            "QMenu { background:#252526; color:#D4D4D4; border:1px solid #444; }"
            "QMenu::item:selected { background:#094771; }"
        )
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1E1E1E;
                color: #D4D4D4;
            }
            QTreeWidget {
                background-color: #252526;
                border: none;
                font-family: Segoe UI;
                font-size: 12px;
            }
            QTreeWidget::item:selected { background-color: #094771; }
            QTreeWidget::item:hover    { background-color: #2A2D2E; }
            QComboBox, QLineEdit, QTextEdit {
                background-color: #3C3C3C;
                border: 1px solid #555;
                color: #D4D4D4;
                padding: 2px 4px;
                border-radius: 2px;
            }
            QPushButton {
                background-color: #0E639C;
                color: white;
                border: none;
                padding: 4px 10px;
                border-radius: 2px;
            }
            QPushButton:hover   { background-color: #1177BB; }
            QPushButton:pressed { background-color: #0A4F82; }
            QLabel { font-family: Segoe UI; }
            QSplitter::handle { background-color: #444; }
            QScrollBar:vertical { background: #252526; width: 10px; }
            QScrollBar::handle:vertical { background: #555; border-radius: 4px; }
        """)
