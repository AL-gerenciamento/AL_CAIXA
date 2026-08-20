"""
controllers/despesa_controller.py
Regras de negócio para lançamentos de despesas (com status pago/pendente).
"""
from __future__ import annotations

from datetime import date

from database import get_session
from models import Despesa
from utils.validators import validar_texto_obrigatorio, ValidationError
from utils.logger import registrar_erro, registrar_alteracao


class DespesaController:
    """CRUD e consultas de despesas."""

    @staticmethod
    def criar(descricao: str, valor: float, data_lanc: date, categoria_id: int,
               paga: bool = False, observacoes: str = "", usuario: str = "sistema") -> Despesa:
        session = get_session()
        try:
            descricao = validar_texto_obrigatorio(descricao, "Descrição", 200)
            if valor <= 0:
                raise ValidationError("O valor deve ser maior que zero.")
            if not categoria_id:
                raise ValidationError("Selecione uma categoria.")

            despesa = Despesa(
                descricao=descricao, valor=valor, data=data_lanc,
                categoria_id=categoria_id, paga=paga, observacoes=observacoes or "",
            )
            session.add(despesa)
            session.commit()
            session.refresh(despesa)
            registrar_alteracao(usuario, f"Despesa criada: {descricao} (R$ {valor:.2f})")
            return despesa
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "criar_despesa")
            raise
        finally:
            session.close()

    @staticmethod
    def editar(despesa_id: int, descricao: str, valor: float, data_lanc: date,
               categoria_id: int, paga: bool, observacoes: str = "",
               usuario: str = "sistema") -> None:
        session = get_session()
        try:
            despesa = session.get(Despesa, despesa_id)
            if not despesa:
                raise ValidationError("Despesa não encontrada.")
            despesa.descricao = validar_texto_obrigatorio(descricao, "Descrição", 200)
            if valor <= 0:
                raise ValidationError("O valor deve ser maior que zero.")
            despesa.valor = valor
            despesa.data = data_lanc
            despesa.categoria_id = categoria_id
            despesa.paga = paga
            despesa.observacoes = observacoes or ""
            session.commit()
            registrar_alteracao(usuario, f"Despesa editada: {descricao}")
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "editar_despesa")
            raise
        finally:
            session.close()

    @staticmethod
    def excluir(despesa_id: int, usuario: str = "sistema") -> None:
        session = get_session()
        try:
            despesa = session.get(Despesa, despesa_id)
            if despesa:
                session.delete(despesa)
                session.commit()
                registrar_alteracao(usuario, f"Despesa excluída: {despesa.descricao}")
        except Exception as e:
            session.rollback()
            registrar_erro(e, "excluir_despesa")
            raise
        finally:
            session.close()

    @staticmethod
    def listar(texto: str = "", categoria_id: int | None = None,
               data_inicio: date | None = None, data_fim: date | None = None,
               apenas_pendentes: bool = False) -> list[Despesa]:
        """Lista despesas com filtros opcionais."""
        session = get_session()
        try:
            query = session.query(Despesa)
            if texto:
                query = query.filter(Despesa.descricao.ilike(f"%{texto}%"))
            if categoria_id:
                query = query.filter_by(categoria_id=categoria_id)
            if data_inicio:
                query = query.filter(Despesa.data >= data_inicio)
            if data_fim:
                query = query.filter(Despesa.data <= data_fim)
            if apenas_pendentes:
                query = query.filter_by(paga=False)
            resultado = query.order_by(Despesa.data.desc()).all()
            for d in resultado:
                _ = d.categoria.nome
            session.expunge_all()
            return resultado
        finally:
            session.close()

    @staticmethod
    def total_periodo(data_inicio: date, data_fim: date) -> float:
        session = get_session()
        try:
            despesas = session.query(Despesa).filter(
                Despesa.data >= data_inicio, Despesa.data <= data_fim
            ).all()
            return sum(d.valor for d in despesas)
        finally:
            session.close()

    @staticmethod
    def alternar_status_pagamento(despesa_id: int, usuario: str = "sistema") -> None:
        session = get_session()
        try:
            despesa = session.get(Despesa, despesa_id)
            if despesa:
                despesa.paga = not despesa.paga
                session.commit()
                status = "paga" if despesa.paga else "pendente"
                registrar_alteracao(usuario, f"Despesa marcada como {status}: {despesa.descricao}")
        finally:
            session.close()
