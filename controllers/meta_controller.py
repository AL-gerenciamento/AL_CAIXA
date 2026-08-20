"""
controllers/meta_controller.py
Regras de negócio para metas financeiras.
"""
from __future__ import annotations

from datetime import date

from database import get_session
from models import Meta
from utils.validators import validar_texto_obrigatorio, ValidationError
from utils.logger import registrar_erro, registrar_alteracao


class MetaController:
    """CRUD de metas financeiras e cálculo de progresso."""

    @staticmethod
    def criar(titulo: str, valor_alvo: float, prazo: date, usuario: str = "sistema") -> Meta:
        session = get_session()
        try:
            titulo = validar_texto_obrigatorio(titulo, "Título", 150)
            if valor_alvo <= 0:
                raise ValidationError("O valor alvo deve ser maior que zero.")
            meta = Meta(titulo=titulo, valor_alvo=valor_alvo, prazo=prazo)
            session.add(meta)
            session.commit()
            session.refresh(meta)
            registrar_alteracao(usuario, f"Meta criada: {titulo}")
            return meta
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "criar_meta")
            raise
        finally:
            session.close()

    @staticmethod
    def listar() -> list[Meta]:
        session = get_session()
        try:
            metas = session.query(Meta).order_by(Meta.prazo).all()
            session.expunge_all()
            return metas
        finally:
            session.close()

    @staticmethod
    def atualizar_progresso(meta_id: int, valor_atual: float, usuario: str = "sistema") -> None:
        session = get_session()
        try:
            meta = session.get(Meta, meta_id)
            if not meta:
                raise ValidationError("Meta não encontrada.")
            meta.valor_atual = max(0.0, valor_atual)
            meta.concluida = meta.valor_atual >= meta.valor_alvo
            session.commit()
            registrar_alteracao(usuario, f"Progresso da meta '{meta.titulo}' atualizado")
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "atualizar_progresso_meta")
            raise
        finally:
            session.close()

    @staticmethod
    def excluir(meta_id: int, usuario: str = "sistema") -> None:
        session = get_session()
        try:
            meta = session.get(Meta, meta_id)
            if meta:
                session.delete(meta)
                session.commit()
                registrar_alteracao(usuario, f"Meta excluída: {meta.titulo}")
        finally:
            session.close()
