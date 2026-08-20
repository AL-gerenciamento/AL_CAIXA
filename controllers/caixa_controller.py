"""
controllers/caixa_controller.py
Saídas de caixa (sempre vinculadas a usuário) e cálculo de saldo,
consolidando entradas (vendas) e saídas do dia/período. Itens 3 e 4.
"""
from __future__ import annotations

from datetime import date, datetime, time

from database import get_session
from models import CaixaSaida, Venda
from utils.validators import validar_texto_obrigatorio, ValidationError
from utils.logger import registrar_erro, registrar_alteracao


class CaixaController:

    @staticmethod
    def registrar_saida(usuario_id: int, valor: float, justificativa: str,
                         categoria: str = "", observacoes: str = "", usuario: str = "sistema") -> CaixaSaida:
        session = get_session()
        try:
            if not usuario_id:
                raise ValidationError("Toda saída de caixa deve ser vinculada a um usuário.")
            if valor <= 0:
                raise ValidationError("O valor deve ser maior que zero.")
            justificativa = validar_texto_obrigatorio(justificativa, "Justificativa", 300)

            saida = CaixaSaida(
                usuario_id=usuario_id, valor=round(valor, 2), justificativa=justificativa,
                categoria=(categoria or "").strip(), observacoes=(observacoes or "").strip(),
            )
            session.add(saida)
            session.commit()
            session.refresh(saida)
            registrar_alteracao(usuario, f"Saída de caixa registrada: R$ {valor:.2f} - {justificativa}")
            session.expunge(saida)
            return saida
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "registrar_saida_caixa")
            raise
        finally:
            session.close()

    @staticmethod
    def _intervalo_dia(dia):
        return datetime.combine(dia, time.min), datetime.combine(dia, time.max)

    @staticmethod
    def entradas_do_dia(dia=None) -> float:
        session = get_session()
        try:
            dia = dia or date.today()
            inicio, fim = CaixaController._intervalo_dia(dia)
            total = session.query(Venda).filter(
                Venda.data_hora >= inicio, Venda.data_hora <= fim,
                Venda.cancelada == False, Venda.aberta == False, Venda.deletado == False,  # noqa: E712
            ).all()
            return round(sum(v.valor_total for v in total), 2)
        finally:
            session.close()

    @staticmethod
    def saidas_do_dia(dia=None) -> float:
        session = get_session()
        try:
            dia = dia or date.today()
            inicio, fim = CaixaController._intervalo_dia(dia)
            saidas = session.query(CaixaSaida).filter(
                CaixaSaida.data_hora >= inicio, CaixaSaida.data_hora <= fim
            ).all()
            return round(sum(s.valor for s in saidas), 2)
        finally:
            session.close()

    @staticmethod
    def saldo_do_dia(dia=None) -> float:
        return round(CaixaController.entradas_do_dia(dia) - CaixaController.saidas_do_dia(dia), 2)

    @staticmethod
    def listar_saidas(dia=None, usuario_id: int | None = None) -> list[CaixaSaida]:
        session = get_session()
        try:
            query = session.query(CaixaSaida)
            if dia:
                inicio, fim = CaixaController._intervalo_dia(dia)
                query = query.filter(CaixaSaida.data_hora >= inicio, CaixaSaida.data_hora <= fim)
            if usuario_id:
                query = query.filter_by(usuario_id=usuario_id)
            saidas = query.order_by(CaixaSaida.data_hora.desc()).all()
            session.expunge_all()
            return saidas
        finally:
            session.close()
