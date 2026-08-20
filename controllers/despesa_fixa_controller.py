"""
controllers/despesa_fixa_controller.py
Regras de negócio para despesas fixas/recorrentes (diária, semanal, mensal
ou boleto) e geração automática dos lançamentos correspondentes na tabela
Despesa.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from database import get_session
from models import DespesaFixa, Despesa
from utils.validators import validar_texto_obrigatorio, ValidationError
from utils.logger import registrar_erro, registrar_alteracao

TIPOS_RECORRENCIA = ("diaria", "semanal", "mensal", "boleto")

NOMES_DIA_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

# Limite de segurança: quantos lançamentos gerar de uma vez por regra,
# para evitar um loop gigante caso o sistema fique muito tempo sem abrir
LIMITE_GERACAO_POR_REGRA = 90


class DespesaFixaController:
    """CRUD de despesas fixas e geração automática dos lançamentos."""

    # --- CRUD ---

    @staticmethod
    def criar(descricao: str, valor: float, categoria_id: int, tipo_recorrencia: str,
              dia_semana: int | None = None, dia_mes: int | None = None,
              data_inicio: date | None = None, data_fim: date | None = None,
              observacoes: str = "", usuario: str = "sistema") -> DespesaFixa:
        session = get_session()
        try:
            descricao = validar_texto_obrigatorio(descricao, "Descrição", 200)
            if valor <= 0:
                raise ValidationError("O valor deve ser maior que zero.")
            if not categoria_id:
                raise ValidationError("Selecione uma categoria.")
            if tipo_recorrencia not in TIPOS_RECORRENCIA:
                raise ValidationError("Tipo de recorrência inválido.")
            if tipo_recorrencia == "semanal" and dia_semana is None:
                raise ValidationError("Selecione o dia da semana.")
            if tipo_recorrencia in ("mensal", "boleto") and not dia_mes:
                raise ValidationError("Informe o dia do mês (1 a 31).")
            if dia_mes is not None and not (1 <= dia_mes <= 31):
                raise ValidationError("O dia do mês deve estar entre 1 e 31.")
            if data_fim and data_inicio and data_fim < data_inicio:
                raise ValidationError("A data final não pode ser antes da data de início.")

            despesa_fixa = DespesaFixa(
                descricao=descricao, valor=valor, categoria_id=categoria_id,
                tipo_recorrencia=tipo_recorrencia, dia_semana=dia_semana, dia_mes=dia_mes,
                data_inicio=data_inicio or date.today(), data_fim=data_fim,
                observacoes=observacoes or "",
            )
            session.add(despesa_fixa)
            session.commit()
            session.refresh(despesa_fixa)
            registrar_alteracao(usuario, f"Despesa fixa criada: {descricao} ({tipo_recorrencia})")
            return despesa_fixa
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "criar_despesa_fixa")
            raise
        finally:
            session.close()

    @staticmethod
    def listar(apenas_ativas: bool = False) -> list[DespesaFixa]:
        session = get_session()
        try:
            query = session.query(DespesaFixa)
            if apenas_ativas:
                query = query.filter_by(ativa=True)
            resultado = query.order_by(DespesaFixa.descricao).all()
            for d in resultado:
                _ = d.categoria.nome
            session.expunge_all()
            return resultado
        finally:
            session.close()

    @staticmethod
    def editar(despesa_fixa_id: int, descricao: str, valor: float, categoria_id: int,
               tipo_recorrencia: str, dia_semana: int | None = None, dia_mes: int | None = None,
               data_fim: date | None = None, observacoes: str = "",
               usuario: str = "sistema") -> None:
        session = get_session()
        try:
            despesa_fixa = session.get(DespesaFixa, despesa_fixa_id)
            if not despesa_fixa:
                raise ValidationError("Despesa fixa não encontrada.")
            if valor <= 0:
                raise ValidationError("O valor deve ser maior que zero.")
            if tipo_recorrencia not in TIPOS_RECORRENCIA:
                raise ValidationError("Tipo de recorrência inválido.")
            if tipo_recorrencia == "semanal" and dia_semana is None:
                raise ValidationError("Selecione o dia da semana.")
            if tipo_recorrencia in ("mensal", "boleto") and not dia_mes:
                raise ValidationError("Informe o dia do mês (1 a 31).")

            despesa_fixa.descricao = validar_texto_obrigatorio(descricao, "Descrição", 200)
            despesa_fixa.valor = valor
            despesa_fixa.categoria_id = categoria_id
            despesa_fixa.tipo_recorrencia = tipo_recorrencia
            despesa_fixa.dia_semana = dia_semana
            despesa_fixa.dia_mes = dia_mes
            despesa_fixa.data_fim = data_fim
            despesa_fixa.observacoes = observacoes or ""
            session.commit()
            registrar_alteracao(usuario, f"Despesa fixa editada: {despesa_fixa.descricao}")
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "editar_despesa_fixa")
            raise
        finally:
            session.close()

    @staticmethod
    def alternar_ativa(despesa_fixa_id: int, usuario: str = "sistema") -> None:
        """Pausa ou reativa a geração automática desta despesa fixa."""
        session = get_session()
        try:
            despesa_fixa = session.get(DespesaFixa, despesa_fixa_id)
            if despesa_fixa:
                despesa_fixa.ativa = not despesa_fixa.ativa
                session.commit()
                status = "ativada" if despesa_fixa.ativa else "pausada"
                registrar_alteracao(usuario, f"Despesa fixa {status}: {despesa_fixa.descricao}")
        finally:
            session.close()

    @staticmethod
    def excluir(despesa_fixa_id: int, usuario: str = "sistema") -> None:
        """
        Exclui a regra de despesa fixa. Os lançamentos já gerados na tabela
        Despesa permanecem no histórico (não são apagados).
        """
        session = get_session()
        try:
            despesa_fixa = session.get(DespesaFixa, despesa_fixa_id)
            if despesa_fixa:
                nome = despesa_fixa.descricao
                session.delete(despesa_fixa)
                session.commit()
                registrar_alteracao(usuario, f"Despesa fixa excluída: {nome}")
        except Exception as e:
            session.rollback()
            registrar_erro(e, "excluir_despesa_fixa")
            raise
        finally:
            session.close()

    # --- Cálculo de datas de recorrência ---

    @staticmethod
    def _proxima_data_apos(despesa_fixa: DespesaFixa, referencia: date) -> date | None:
        """Calcula a próxima data de ocorrência estritamente após `referencia`."""
        if despesa_fixa.tipo_recorrencia == "diaria":
            return referencia + timedelta(days=1)

        if despesa_fixa.tipo_recorrencia == "semanal":
            avanco = (despesa_fixa.dia_semana - referencia.weekday()) % 7
            avanco = avanco or 7  # garante que sempre avance, nunca fique parado no mesmo dia
            return referencia + timedelta(days=avanco)

        if despesa_fixa.tipo_recorrencia in ("mensal", "boleto"):
            ano, mes = referencia.year, referencia.month
            mes += 1
            if mes > 12:
                mes = 1
                ano += 1
            ultimo_dia_mes = calendar.monthrange(ano, mes)[1]
            dia = min(despesa_fixa.dia_mes, ultimo_dia_mes)
            return date(ano, mes, dia)

        return None

    @staticmethod
    def _primeira_data(despesa_fixa: DespesaFixa) -> date | None:
        """Calcula a primeira data de ocorrência a partir de data_inicio."""
        inicio = despesa_fixa.data_inicio

        if despesa_fixa.tipo_recorrencia == "diaria":
            return inicio

        if despesa_fixa.tipo_recorrencia == "semanal":
            avanco = (despesa_fixa.dia_semana - inicio.weekday()) % 7
            return inicio + timedelta(days=avanco)

        if despesa_fixa.tipo_recorrencia in ("mensal", "boleto"):
            ultimo_dia_mes = calendar.monthrange(inicio.year, inicio.month)[1]
            dia = min(despesa_fixa.dia_mes, ultimo_dia_mes)
            candidata = date(inicio.year, inicio.month, dia)
            if candidata >= inicio:
                return candidata
            # se o dia já passou neste mês, a primeira ocorrência é no mês seguinte
            return DespesaFixaController._proxima_data_apos(despesa_fixa, candidata)

        return None

    @staticmethod
    def gerar_lancamentos_pendentes(usuario: str = "sistema (automático)") -> int:
        """
        Gera na tabela Despesa todos os lançamentos pendentes de cada
        despesa fixa ativa, desde a última geração (ou desde data_inicio,
        na primeira vez) até hoje, inclusive.

        Deve ser chamado a cada início da aplicação (ver main.py).
        Retorna quantos lançamentos foram criados.
        """
        session = get_session()
        total_gerado = 0
        hoje = date.today()
        try:
            regras = session.query(DespesaFixa).filter_by(ativa=True).all()
            for regra in regras:
                if regra.data_fim and regra.data_fim < hoje:
                    continue

                if regra.ultima_geracao:
                    proxima = DespesaFixaController._proxima_data_apos(regra, regra.ultima_geracao)
                else:
                    proxima = DespesaFixaController._primeira_data(regra)

                geradas_nesta_regra = 0
                while (
                    proxima is not None
                    and proxima <= hoje
                    and (not regra.data_fim or proxima <= regra.data_fim)
                    and geradas_nesta_regra < LIMITE_GERACAO_POR_REGRA
                ):
                    session.add(Despesa(
                        descricao=regra.descricao,
                        valor=regra.valor,
                        data=proxima,
                        categoria_id=regra.categoria_id,
                        observacoes=regra.observacoes,
                        paga=False,
                        despesa_fixa_id=regra.id,
                    ))
                    regra.ultima_geracao = proxima
                    total_gerado += 1
                    geradas_nesta_regra += 1
                    proxima = DespesaFixaController._proxima_data_apos(regra, proxima)

            session.commit()
            if total_gerado:
                registrar_alteracao(
                    usuario, f"{total_gerado} lançamento(s) de despesa fixa gerado(s) automaticamente"
                )
            return total_gerado
        except Exception as e:
            session.rollback()
            registrar_erro(e, "gerar_lancamentos_pendentes_despesa_fixa")
            return 0
        finally:
            session.close()
