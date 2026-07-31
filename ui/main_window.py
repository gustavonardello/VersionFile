import webbrowser

from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from ui.tree_panel import TreePanel
from ui.editor_panel import EditorPanel
from ui.export_dialog import ExportDialog
from core.paths import base_path
from core.updater import verificar_atualizacao, InfoAtualizacao


class _WorkerAtualizacao(QThread):
    """Verifica atualização em background, sem travar a UI."""
    resultado = pyqtSignal(object)  # InfoAtualizacao ou None

    def run(self):
        info = verificar_atualizacao()
        self.resultado.emit(info)


class MainWindow(QMainWindow):
    def __init__(self, conn):
        super().__init__()
        self.conn = conn
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

        self.tree_panel.regra_selecionada.connect(self.editor_panel.abrir_regra)
        self.tree_panel.regra_desmarcada.connect(self.editor_panel.desabilitar_acoes)

        self._iniciar_checagem_atualizacao()

    def _criar_menu(self):
        barra = self.menuBar()

        menu_arquivo = barra.addMenu("Arquivo")

        act_exportar = QAction("Exportar múltiplas regras...", self)
        act_exportar.setShortcut("Ctrl+E")
        act_exportar.triggered.connect(self._abrir_exportacao)
        menu_arquivo.addAction(act_exportar)

        menu_arquivo.addSeparator()

        act_sair = QAction("Sair", self)
        act_sair.setShortcut("Alt+F4")
        act_sair.triggered.connect(self.close)
        menu_arquivo.addAction(act_sair)

    def closeEvent(self, event):
        self.editor_panel.salvar_se_pendente()
        super().closeEvent(event)

    def _abrir_exportacao(self):
        dlg = ExportDialog(self.conn, parent=self)
        dlg.exec()

    # -- Atualização ----------------------------------------------------------

    def _iniciar_checagem_atualizacao(self):
        self._worker_update = _WorkerAtualizacao()
        self._worker_update.resultado.connect(self._tratar_resultado_atualizacao)
        self._worker_update.start()

    def _tratar_resultado_atualizacao(self, info: InfoAtualizacao | None):
        if info is None:
            return
        self._mostrar_dialogo_atualizacao(info)

    def _mostrar_dialogo_atualizacao(self, info: InfoAtualizacao):
        dlg = QDialog(self)
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

        btn_baixar = QPushButton("Baixar")
        btn_baixar.setDefault(True)
        btn_baixar.clicked.connect(lambda: self._abrir_release(info, dlg))
        btn_layout.addWidget(btn_baixar)

        layout.addLayout(btn_layout)
        dlg.setModal(False)
        dlg.show()

    def _abrir_release(self, info: InfoAtualizacao, dlg: QDialog):
        webbrowser.open(info.url_release)
        dlg.close()

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
