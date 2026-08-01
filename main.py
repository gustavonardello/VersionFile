import os
import sys
import shutil
import traceback
from datetime import datetime
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from database.db import initialize_db, get_connection, DB_PATH
from ui.main_window import MainWindow
from ui.migracao_dialog import garantir_dados
from core.paths import base_path, data_path


def _instalar_excepthook():
    """Grava exceções não tratadas em crash.log dentro de data_path()."""
    def _hook(tipo, valor, tb):
        log = data_path() / "crash.log"
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.now().isoformat()} ---\n")
                traceback.print_exception(tipo, valor, tb, file=f)
        except OSError:
            pass
        sys.__excepthook__(tipo, valor, tb)

    sys.excepthook = _hook


def _bootstrap():
    """Garante que os arquivos de configuração existam na pasta de dados."""
    dest = data_path() / "config"
    dest.mkdir(parents=True, exist_ok=True)
    themes_dest = dest / "themes.json"
    if not themes_dest.exists():
        themes_src = base_path() / "config" / "themes.json"
        if themes_src.exists():
            shutil.copy2(themes_src, themes_dest)


def _boot_log(msg: str):
    """Grava uma linha no boot.log com flush imediato."""
    try:
        log = data_path() / "boot.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} {msg}\n")
            f.flush()
    except OSError:
        pass


def main():
    _instalar_excepthook()

    _boot_log(f"main() iniciou, PID={os.getpid()}")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    icone = base_path() / "icone.ico"
    if icone.exists():
        app.setWindowIcon(QIcon(str(icone)))

    # Precisa vir antes de qualquer acesso ao banco: resolve de onde os dados
    # devem ser lidos quando o local mudou entre versões do app.
    from core.migration import detectar_estado
    estado = detectar_estado()
    _boot_log(f"detectar_estado() = {estado}, PID={os.getpid()}")

    if not garantir_dados():
        _boot_log(f"garantir_dados() retornou False — saindo, PID={os.getpid()}")
        sys.exit(0)

    _bootstrap()
    db_is_new = not DB_PATH.exists()
    initialize_db()
    if db_is_new:
        print(f"Banco de dados criado em: {DB_PATH}")
    else:
        print(f"Banco de dados existente preservado: {DB_PATH}")
    conn = get_connection()

    window = MainWindow(conn)
    window.show()

    _boot_log(f"event loop iniciando, PID={os.getpid()}")
    ret = app.exec()
    _boot_log(f"event loop encerrou (ret={ret}), PID={os.getpid()}")
    sys.exit(ret)


if __name__ == "__main__":
    main()
