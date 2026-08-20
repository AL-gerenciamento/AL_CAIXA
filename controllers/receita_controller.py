"""
controllers/receita_controller.py
Regras de negócio para lançamentos de receitas.
"""
from __future__ import annotations

from datetime import date

from database import get_session
from models import Receita
from utils.validators import validar_texto_obrigatorio, validar_valor_monetario, ValidationError
from utils.logger import registrar_erro, registrar_alteracao


class ReceitaController:
    """CRUD e consultas de receitas."""

    @staticmethod
    def criar(descricao: str, valor: float, data_lanc: date, categoria_id: int,
               observacoes: str = "", usuario: str = "sistema") -> Receita:
        session = get_session()
        try:
            descricao = validar_texto_obrigatorio(descricao, "Descrição", 200)
            if valor <= 0:
                raise ValidationError("O valor deve ser maior que zero.")
            if not categoria_id:
                raise ValidationError("Selecione uma categoria.")

            receita = Receita(
                descricao=descricao, valor=valor, data=data_lanc,
                categoria_id=categoria_id, observacoes=observacoes or "",
            )
            session.add(receita)
            session.commit()
            session.refresh(receita)
            registrar_alteracao(usuario, f"Receita criada: {descricao} (R$ {valor:.2f})")
            return receita
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "criar_receita")
            raise
        finally:
            session.close()

    @staticmethod
    def editar(receita_id: int, descricao: str, valor: float, data_lanc: date,
               categoria_id: int, observacoes: str = "", usuario: str = "sistema") -> None:
        session = get_session()
        try:
            receita = session.get(Receita, receita_id)
            if not receita:
                raise ValidationError("Receita não encontrada.")
            receita.descricao = validar_texto_obrigatorio(descricao, "Descrição", 200)
            if valor <= 0:
                raise ValidationError("O valor deve ser maior que zero.")
            receita.valor = valor
            receita.data = data_lanc
            receita.categoria_id = categoria_id
            receita.observacoes = observacoes or ""
            session.commit()
            registrar_alteracao(usuario, f"Receita editada: {descricao}")
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "editar_receita")
            raise
        finally:
            session.close()

    @staticmethod
    def excluir(receita_id: int, usuario: str = "sistema") -> None:
        session = get_session()
        try:
            receita = session.get(Receita, receita_id)
            if receita:
                session.delete(receita)
                session.commit()
                registrar_alteracao(usuario, f"Receita excluída: {receita.descricao}")
        except Exception as e:
            session.rollback()
            registrar_erro(e, "excluir_receita")
            raise
        finally:
            session.close()

    @staticmethod
    def listar(texto: str = "", categoria_id: int | None = None,
               data_inicio: date | None = None, data_fim: date | None = None) -> list[Receita]:
        """Lista receitas com filtros opcionais de texto, categoria e período."""
        session = get_session()
        try:
            query = session.query(Receita)
            if texto:
                query = query.filter(Receita.descricao.ilike(f"%{texto}%"))
            if categoria_id:
                query = query.filter_by(categoria_id=categoria_id)
            if data_inicio:
                query = query.filter(Receita.data >= data_inicio)
            if data_fim:
                query = query.filter(Receita.data <= data_fim)
            resultado = query.order_by(Receita.data.desc()).all()
            for r in resultado:
                _ = r.categoria.nome  # força carregamento antes de fechar a sessão
            session.expunge_all()
            return resultado
        finally:
            session.close()

    @staticmethod
    def total_periodo(data_inicio: date, data_fim: date) -> float:
        session = get_session()
        try:
            receitas = session.query(Receita).filter(
                Receita.data >= data_inicio, Receita.data <= data_fim
            ).all()
            return sum(r.valor for r in receitas)
        finally:
            session.close()
