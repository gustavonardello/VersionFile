"""Valida o ponto de entrada e o cadastro real em diálogos, sem dados reais ou rede.

Uso: py -3.11 scripts/validar_interface.py
Capturas: auditoria/capturas/. A execução usa Qt offscreen e um banco temporário.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if Path("C:/Windows/Fonts").is_dir():
    os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox
from core import paths


def executar():
    capturas = RAIZ / "auditoria" / "capturas"
    capturas.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as pasta, patch.object(paths, "data_path", return_value=Path(pasta)):
        # Importar depois do patch isola os caminhos calculados no import.
        import main
        import database.models as M
        from ui.dialogs import DialogCliente
        from ui.main_window import MainWindow
        from database.db import get_connection

        estado = {"etapa": 0, "erro": None}

        def iniciar():
            try:
                janela = next(w for w in QApplication.topLevelWidgets() if isinstance(w, MainWindow))
                M.criar_cliente(janela.conn, "Cliente exemplo")
                janela.tree_panel.carregar()
                timer = QTimer(janela)
                timer.setInterval(100)

                def preencher():
                    try:
                        modal = QApplication.activeModalWidget()
                        if isinstance(modal, DialogCliente):
                            if estado["etapa"] == 0:
                                modal.campo_nome.setText("Cliente exemplo")
                                modal.grab().save(str(capturas / "01-cadastro.png"))
                                estado["etapa"] = 1
                                modal.accept()
                            elif estado["etapa"] == 2:
                                assert modal.nome == "Cliente exemplo", "Nome não foi preservado"
                                modal.campo_nome.setText("Novo cliente")
                                estado["etapa"] = 3
                                modal.accept()
                        elif isinstance(modal, QMessageBox) and estado["etapa"] == 1:
                            assert "Já existe um cliente" in modal.text()
                            modal.grab().save(str(capturas / "02-duplicidade.png"))
                            estado["etapa"] = 2
                            modal.accept()
                    except BaseException as erro:
                        estado["erro"] = erro
                        timer.stop()
                        QApplication.exit(1)

                timer.timeout.connect(preencher)
                timer.start()
                janela.tree_panel._novo_cliente()
                timer.stop()
                if estado["erro"]:
                    raise estado["erro"]
                assert estado["etapa"] == 3
                assert [c.nome for c in M.listar_clientes(janela.conn)] == ["Cliente exemplo", "Novo cliente"]
                janela.grab().save(str(capturas / "03-cliente-cadastrado.png"))
                janela.close()
            except BaseException as erro:
                estado["erro"] = erro
                QApplication.exit(1)

        # main cria o QApplication; agendamento ocorre ao construir a janela.
        def agendar(_janela):
            QTimer.singleShot(150, iniciar)
            QTimer.singleShot(10000, lambda: QApplication.exit(2))

        with patch.object(MainWindow, "_iniciar_checagem_atualizacao", agendar):
            try:
                main.main()
            except SystemExit as saida:
                if estado["erro"]:
                    raise estado["erro"]
                if saida.code != 0:
                    raise RuntimeError(f"Validação encerrou com código {saida.code}")
        print("OK: main.main(), duplicidade, correção do nome e cadastro persistido.")
        print(f"Capturas: {capturas}")


if __name__ == "__main__":
    executar()
