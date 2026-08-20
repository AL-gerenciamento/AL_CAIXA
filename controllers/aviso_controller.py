"""
controllers/aviso_controller.py
CRUD de avisos exibidos na tela de login.
"""
from __future__ import annotations
from datetime import date

from database import get_session
from models import Aviso
from utils.validators import validar_texto_obrigatorio, ValidationError
from utils.logger import registrar_erro, registrar_alteracao


class AvisoController:

    @staticmethod
    def listar_ativos() -> list[Aviso]:
        session = get_session()
        try:
            hoje = date.today()
            avisos = session.query(Aviso).filter_by(ativo=True, deletado=False).all()
            avisos = [a for a in avisos if not a.expira_em or a.expira_em >= hoje]
            session.expunge_all()
            return avisos
        finally:
            session.close()

    @staticmethod
    def listar_todos() -> list[Aviso]:
        session = get_session()
        try:
            avisos = session.query(Aviso).filter_by(deletado=False).order_by(Aviso.criado_em.desc()).all()
            session.expunge_all()
            return avisos
        finally:
            session.close()

    @staticmethod
    def criar(titulo: str, mensagem: str, expira_em: date | None, usuario: str = "sistema") -> Aviso:
        session = get_session()
        try:
            titulo = validar_texto_obrigatorio(titulo, "Título", 150)
            mensagem = validar_texto_obrigatorio(mensagem, "Mensagem", 1000)
            aviso = Aviso(titulo=titulo, mensagem=mensagem, expira_em=expira_em)
            session.add(aviso)
            session.commit()
            session.refresh(aviso)
            registrar_alteracao(usuario, f"Aviso criado: {titulo}")
            return aviso
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "criar_aviso")
            raise
        finally:
            session.close()

    @staticmethod
    def alternar_ativo(aviso_id: int, usuario: str = "sistema") -> None:
        session = get_session()
        try:
            aviso = session.get(Aviso, aviso_id)
            if aviso:
                aviso.ativo = not aviso.ativo
                session.commit()
                registrar_alteracao(usuario, f"Aviso {'ativado' if aviso.ativo else 'desativado'}: {aviso.titulo}")
        finally:
            session.close()

    @staticmethod
    def excluir(aviso_id: int, usuario: str = "sistema") -> None:
        session = get_session()
        try:
            aviso = session.get(Aviso, aviso_id)
            if aviso:
                aviso.deletado = True
                session.commit()
                registrar_alteracao(usuario, f"Aviso excluído: {aviso.titulo}")
        finally:
            session.close()
