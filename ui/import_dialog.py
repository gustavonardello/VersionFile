from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QTreeWidget, QTreeWidgetItem, QLineEdit,
    QComboBox, QMessageBox, QProgressBar, QFrame, QCheckBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from core.importer import escanear_pasta, importar_para_banco, ItemCliente, _inferir_tipo

ICON_CLIENTE = "👤"
ICON_PROJETO = "📁"
ICON_REGRA   = "📄"


class _WorkerImport(QThread):
    concluido = pyqtSignal(dict)
    erro = pyqtSignal(str)

    def __init__(self, conn, clientes, notas):
        super().__init__()
        self.conn = conn
        self.clientes = clientes
        self.notas = notas

    def run(self):
        try:
            result = importar_para_banco(self.conn, self.clientes, self.notas)
            self.concluido.emit(result)
        except Exception as e:
            self.erro.emit(str(e))


class ImportDialog(QDialog):
    importacao_concluida = pyqtSignal()

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._clientes_escaneados: list[ItemCliente] = []
        self._pasta_raiz: Path | None = None

        self.setWindowTitle("Importar estrutura de pastas")
        self.resize(700, 550)
        self._build_ui()
        self._aplicar_estilo()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # --- Seleção de pasta ---
        row_pasta = QHBoxLayout()
        row_pasta.addWidget(QLabel("Pasta raiz:"))
        self.campo_pasta = QLineEdit()
        self.campo_pasta.setReadOnly(True)
        self.campo_pasta.setPlaceholderText("Selecione a pasta que contém as subpastas de clientes...")
        row_pasta.addWidget(self.campo_pasta)
        btn_browse = QPushButton("Procurar...")
        btn_browse.clicked.connect(self._selecionar_pasta)
        row_pasta.addWidget(btn_browse)
        layout.addLayout(row_pasta)

        # Instrução
        self.label_instrucao = QLabel(
            "Estrutura esperada:  pasta_raiz / Cliente / Projeto ou DID / arquivo.txt"
        )
        self.label_instrucao.setStyleSheet("color:#858585; font-size:11px;")
        layout.addWidget(self.label_instrucao)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#444;")
        layout.addWidget(sep)

        # --- Preview ---
        self.label_preview = QLabel("Preview de importação:")
        layout.addWidget(self.label_preview)

        self.tree_preview = QTreeWidget()
        self.tree_preview.setHeaderLabels(["Nome", "Tipo", "Arquivo"])
        self.tree_preview.setColumnWidth(0, 300)
        self.tree_preview.setColumnWidth(1, 80)
        layout.addWidget(self.tree_preview)

        self.label_stats = QLabel("")
        self.label_stats.setStyleSheet("color:#858585; font-size:11px;")
        layout.addWidget(self.label_stats)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color:#444;")
        layout.addWidget(sep2)

        # --- Opções de importação ---
        row_notas = QHBoxLayout()
        row_notas.addWidget(QLabel("Notas da versão:"))
        self.campo_notas = QLineEdit("Importação inicial")
        row_notas.addWidget(self.campo_notas)
        layout.addLayout(row_notas)

        row_tipo = QHBoxLayout()
        row_tipo.addWidget(QLabel("Tipo padrão para projetos sem 'DID' no nome:"))
        self.combo_tipo_default = QComboBox()
        self.combo_tipo_default.addItems(["Projeto", "DID"])
        row_tipo.addWidget(self.combo_tipo_default)
        row_tipo.addStretch()
        layout.addLayout(row_tipo)

        # --- Barra de progresso (oculta até importar) ---
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0)  # indeterminado
        layout.addWidget(self.progress)

        # --- Botões ---
        row_btn = QHBoxLayout()
        row_btn.addStretch()
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.clicked.connect(self.reject)
        row_btn.addWidget(self.btn_cancelar)
        self.btn_importar = QPushButton("Importar")
        self.btn_importar.setEnabled(False)
        self.btn_importar.clicked.connect(self._iniciar_importacao)
        row_btn.addWidget(self.btn_importar)
        layout.addLayout(row_btn)

    def _selecionar_pasta(self):
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar pasta raiz")
        if not pasta:
            return
        self._pasta_raiz = Path(pasta)
        self.campo_pasta.setText(str(self._pasta_raiz))
        self._escanear()

    def _escanear(self):
        self.tree_preview.clear()
        self.label_stats.setText("Escaneando...")

        try:
            self._clientes_escaneados = escanear_pasta(self._pasta_raiz)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao escanear pasta:\n{e}")
            return

        total_clientes = len(self._clientes_escaneados)
        total_projetos = sum(len(c.projetos) for c in self._clientes_escaneados)
        total_regras   = sum(len(p.regras) for c in self._clientes_escaneados for p in c.projetos)

        if total_regras == 0:
            self.label_stats.setText("Nenhum arquivo .txt/.lsp encontrado na estrutura selecionada.")
            self.btn_importar.setEnabled(False)
            return

        # Monta preview
        for item_c in self._clientes_escaneados:
            node_c = QTreeWidgetItem([f"{ICON_CLIENTE}  {item_c.nome}", "", ""])
            node_c.setForeground(0, QColor("#9CDCFE"))
            node_c.setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))

            for item_p in item_c.projetos:
                node_p = QTreeWidgetItem([f"{ICON_PROJETO}  {item_p.nome}", item_p.tipo, ""])
                node_p.setForeground(0, QColor("#DCDCAA"))
                node_p.setForeground(1, QColor("#858585"))

                for arq in item_p.regras:
                    node_r = QTreeWidgetItem([
                        f"{ICON_REGRA}  {arq.numero}",
                        "",
                        arq.caminho.name,
                    ])
                    node_r.setForeground(0, QColor("#D4D4D4"))
                    node_r.setForeground(2, QColor("#858585"))
                    node_p.addChild(node_r)

                node_c.addChild(node_p)
            self.tree_preview.addTopLevelItem(node_c)

        self.tree_preview.expandAll()

        self.label_stats.setText(
            f"Encontrado:  {total_clientes} cliente(s)   "
            f"{total_projetos} projeto(s)   "
            f"{total_regras} regra(s)"
        )
        self.btn_importar.setEnabled(True)

    def _iniciar_importacao(self):
        self.btn_importar.setEnabled(False)
        self.btn_cancelar.setEnabled(False)
        self.progress.setVisible(True)

        self._worker = _WorkerImport(
            self.conn,
            self._clientes_escaneados,
            self.campo_notas.text().strip() or "Importação inicial",
        )
        self._worker.concluido.connect(self._on_concluido)
        self._worker.erro.connect(self._on_erro)
        self._worker.start()

    def _on_concluido(self, resultado: dict):
        self.progress.setVisible(False)
        msg = (
            f"Importação concluída!\n\n"
            f"  Clientes criados:  {resultado['clientes']}\n"
            f"  Projetos criados:  {resultado['projetos']}\n"
            f"  Regras importadas: {resultado['regras']}\n"
            f"  Já existiam:       {resultado['pulados']}"
        )
        QMessageBox.information(self, "Concluído", msg)
        self.importacao_concluida.emit()
        self.accept()

    def _on_erro(self, mensagem: str):
        self.progress.setVisible(False)
        self.btn_importar.setEnabled(True)
        self.btn_cancelar.setEnabled(True)
        QMessageBox.critical(self, "Erro na importação", mensagem)

    def _aplicar_estilo(self):
        self.setStyleSheet("""
            QDialog, QWidget {
                background-color: #1E1E1E;
                color: #D4D4D4;
            }
            QTreeWidget {
                background-color: #252526;
                border: 1px solid #444;
                font-family: Consolas;
                font-size: 11px;
            }
            QTreeWidget::item:selected { background-color: #094771; }
            QTreeWidget::item:hover    { background-color: #2A2D2E; }
            QHeaderView::section {
                background-color: #2D2D2D;
                color: #858585;
                border: none;
                padding: 2px 4px;
                font-size: 11px;
            }
            QLineEdit, QComboBox {
                background-color: #3C3C3C;
                border: 1px solid #555;
                color: #D4D4D4;
                padding: 3px 6px;
                border-radius: 2px;
            }
            QPushButton {
                background-color: #0E639C;
                color: white;
                border: none;
                padding: 5px 14px;
                border-radius: 2px;
            }
            QPushButton:hover    { background-color: #1177BB; }
            QPushButton:disabled { background-color: #444; color: #666; }
            QProgressBar {
                background-color: #2D2D2D;
                border: 1px solid #444;
                border-radius: 2px;
                height: 6px;
            }
            QProgressBar::chunk { background-color: #0E639C; }
        """)
