"""Apresentação uniforme de falhas recuperáveis da interface."""
from PyQt6.QtWidgets import QMessageBox


def mostrar_erro(parent, titulo: str, erro: BaseException):
    mensagem = str(erro).strip() or erro.__class__.__name__
    QMessageBox.warning(parent, titulo, mensagem)
