"""
utils/logger.py
Sistema de log de erros: grava em arquivo texto (reports/erros.log)
e, quando possível, também na tabela log_erros do banco.
"""
import os
import traceback
from datetime import datetime

from utils.paths import pasta_base
BASE_DIR = pasta_base()
LOG_DIR = os.path.join(BASE_DIR, "reports")
LOG_FILE = os.path.join(LOG_DIR, "erros.log")

os.makedirs(LOG_DIR, exist_ok=True)


def registrar_erro(erro: Exception, origem: str = "") -> None:
    """Registra um erro no arquivo de log e na tabela log_erros."""
    mensagem = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {origem} | {repr(erro)}\n"
    mensagem += traceback.format_exc() + "\n"

    # Grava sempre em arquivo (não depende do banco estar disponível)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(mensagem)

    # Tenta também gravar no banco (best-effort)
    try:
        from database import get_session
        from models import LogErro
        session = get_session()
        try:
            session.add(LogErro(mensagem=str(erro), origem=origem))
            session.commit()
        finally:
            session.close()
    except Exception:
        pass  # evita erro em cascata dentro do próprio logger


def registrar_alteracao(usuario: str, acao: str) -> None:
    """Registra uma ação do usuário no histórico de alterações (auditoria)."""
    try:
        from database import get_session
        from models import LogAlteracao
        session = get_session()
        try:
            session.add(LogAlteracao(usuario=usuario, acao=acao))
            session.commit()
        finally:
            session.close()
    except Exception as e:
        registrar_erro(e, origem="registrar_alteracao")
