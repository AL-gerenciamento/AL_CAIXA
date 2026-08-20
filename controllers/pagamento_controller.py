"""
controllers/pagamento_controller.py
Mensalidade por conta principal: vencimento dia 5 (ajustado para o próximo
dia útil se cair em fim de semana ou feriado nacional), bloqueio automático
da conta (admin + sub-usuários) após 3 dias úteis sem pagamento confirmado.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

from database import get_session
from models import Usuario, Empresa, Pagamento, StatusPagamento, ConfiguracaoPlataforma, UUID_CONFIGURACAO_PLATAFORMA
from utils.feriados import proximo_dia_util, adicionar_dias_uteis, eh_dia_util
from utils.validators import ValidationError
from utils.logger import registrar_erro, registrar_alteracao
from utils.pix_payload import TIPOS_CHAVE, gerar_payload as _gerar_payload_pix
from utils.email_sender import (
    enviar_email_cobranca,
    enviar_email_prorrogacao_emergencial,
    enviar_email_comprovante_enviado,
    enviar_email_confirmacao_imprensa,
    EMAIL_FINANCEIRO,
    HORARIO_FINANCEIRO,
)

DIA_VENCIMENTO = 5
DIAS_UTEIS_TOLERANCIA = 3
VALOR_PADRAO_MENSALIDADE = 25.0
PRORROGACAO_HORAS = 12

# Valores usados apenas para CRIAR a linha de configuração da mensalidade na
# primeira vez que o sistema roda (se ninguém no super admin ainda mexeu
# nela). A partir daí, tudo é lido/gravado em ConfiguracaoPlataforma e
# muda a qualquer momento pelo painel administrativo.
_PIX_MENSALIDADE_PADRAO = dict(
    chave="algl.gerenciamento@gmail.com",
    tipo_chave="E-mail",
    nome_recebedor="Aykon Lucas Goncalves Lei",
    cidade="SAO PAULO",
)


class PagamentoController:

    @staticmethod
    def _obter_ou_criar_config(session) -> ConfiguracaoPlataforma:
        """Busca a linha (única) de configuração da mensalidade; cria com os
        valores padrão se ainda não existir (primeira execução do sistema)."""
        config = session.query(ConfiguracaoPlataforma).filter_by(
            uuid=UUID_CONFIGURACAO_PLATAFORMA
        ).first()
        if config is None:
            config = ConfiguracaoPlataforma(
                uuid=UUID_CONFIGURACAO_PLATAFORMA,
                mensalidade_valor=VALOR_PADRAO_MENSALIDADE,
                pix_chave=_PIX_MENSALIDADE_PADRAO["chave"],
                pix_tipo_chave=_PIX_MENSALIDADE_PADRAO["tipo_chave"],
                pix_nome_recebedor=_PIX_MENSALIDADE_PADRAO["nome_recebedor"],
                pix_cidade=_PIX_MENSALIDADE_PADRAO["cidade"],
            )
            session.add(config)
            session.flush()
        return config

    @staticmethod
    def obter_configuracao_mensalidade() -> dict:
        """Lê a configuração atual da mensalidade da plataforma (valor + dados do Pix)."""
        session = get_session()
        try:
            config = PagamentoController._obter_ou_criar_config(session)
            dados = {
                "valor": config.mensalidade_valor,
                "pix_chave": config.pix_chave,
                "pix_tipo_chave": config.pix_tipo_chave,
                "pix_nome_recebedor": config.pix_nome_recebedor,
                "pix_cidade": config.pix_cidade,
            }
            session.commit()  # grava a linha padrão se acabou de ser criada
            return dados
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def definir_configuracao_mensalidade(
        valor: float, pix_chave: str, pix_tipo_chave: str,
        pix_nome_recebedor: str, pix_cidade: str, usuario: str = "sistema",
    ) -> None:
        """
        Altera o valor da mensalidade e/ou os dados do Pix usado para
        pagá-la. Exclusivo do super administrador (painel administrativo).
        A mudança sobe pra nuvem no próximo ciclo de sincronização (em
        tempo real) e chega às demais instalações dali a pouco, refletindo
        automaticamente na tela "Administração" de cada empresa.
        """
        if valor is None or valor <= 0:
            raise ValidationError("Informe um valor de mensalidade válido (maior que zero).")
        pix_chave = (pix_chave or "").strip()
        if not pix_chave:
            raise ValidationError("Informe a chave Pix da mensalidade.")
        if pix_tipo_chave not in TIPOS_CHAVE:
            pix_tipo_chave = TIPOS_CHAVE[0]

        session = get_session()
        try:
            config = PagamentoController._obter_ou_criar_config(session)
            config.mensalidade_valor = float(valor)
            config.pix_chave = pix_chave
            config.pix_tipo_chave = pix_tipo_chave
            config.pix_nome_recebedor = (pix_nome_recebedor or "").strip()
            config.pix_cidade = (pix_cidade or "").strip()
            session.commit()
            registrar_alteracao(
                usuario,
                f"Mensalidade da plataforma alterada para R$ {float(valor):.2f}",
            )
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "definir_configuracao_mensalidade")
            raise
        finally:
            session.close()

    @staticmethod
    def valor_mensalidade_atual() -> float:
        return PagamentoController.obter_configuracao_mensalidade()["valor"]

    @staticmethod
    def codigo_pix_mensalidade_atual(identificador: str = "") -> str:
        """Gera o payload Pix (copia e cola) da mensalidade já com o valor atual embutido."""
        config = PagamentoController.obter_configuracao_mensalidade()
        return _gerar_payload_pix(
            config["pix_chave"], config["pix_tipo_chave"],
            config["pix_nome_recebedor"], config["pix_cidade"],
            config["valor"], identificador,
        )

    @staticmethod
    def calcular_vencimento(ano: int, mes: int) -> date:
        base = date(ano, mes, min(DIA_VENCIMENTO, calendar.monthrange(ano, mes)[1]))
        if eh_dia_util(base):
            return base
        return proximo_dia_util(base)

    @staticmethod
    def gerar_pagamentos_pendentes(usuario: str = "sistema (automático)") -> int:
        """Garante que toda conta principal tenha o pagamento do mês corrente gerado."""
        session = get_session()
        gerados = 0
        try:
            hoje = date.today()
            referencia = f"{hoje.year:04d}-{hoje.month:02d}"
            vencimento = PagamentoController.calcular_vencimento(hoje.year, hoje.month)

            contas_principais = session.query(Usuario).filter_by(
                conta_principal_id=None, deletado=False, super_admin=False
            ).all()

            valor_atual = PagamentoController._obter_ou_criar_config(session).mensalidade_valor

            for conta in contas_principais:
                existe = session.query(Pagamento).filter_by(
                    conta_principal_id=conta.id, referencia=referencia
                ).first()
                if existe:
                    continue
                session.add(Pagamento(
                    conta_principal_id=conta.id,
                    referencia=referencia,
                    vencimento=vencimento,
                    valor=valor_atual,
                    status=StatusPagamento.PENDENTE,
                ))
                gerados += 1

            session.commit()
            if gerados:
                registrar_alteracao(usuario, f"{gerados} pagamento(s) mensal(is) gerado(s)")
            return gerados
        except Exception as e:
            session.rollback()
            registrar_erro(e, "gerar_pagamentos_pendentes")
            return 0
        finally:
            session.close()

    @staticmethod
    def verificar_bloqueios(usuario: str = "sistema (automático)") -> int:
        """Bloqueia contas cujo pagamento venceu há mais de 3 dias úteis e não foi pago."""
        session = get_session()
        bloqueadas = 0
        try:
            hoje = date.today()
            pendentes = session.query(Pagamento).filter(
                Pagamento.status.in_([StatusPagamento.PENDENTE, StatusPagamento.ATRASADO]),
                Pagamento.deletado == False,
            ).all()

            for pagamento in pendentes:
                limite = adicionar_dias_uteis(pagamento.vencimento, DIAS_UTEIS_TOLERANCIA)

                # Prorrogação emergencial de 12h ativa: não bloqueia até ela expirar.
                if pagamento.prorrogacao_expira and datetime.now() < pagamento.prorrogacao_expira:
                    continue

                # Comprovante de pagamento (imprensa) enviado, aguardando o
                # equipe financeira conferir: pausa o bloqueio automático.
                if pagamento.aguardando_confirmacao:
                    continue

                if hoje > limite:
                    pagamento.status = StatusPagamento.ATRASADO
                    membros = session.query(Usuario).filter(
                        (Usuario.id == pagamento.conta_principal_id)
                        | (Usuario.conta_principal_id == pagamento.conta_principal_id)
                    ).all()
                    motivo = (
                        f"Mensalidade {pagamento.referencia} em atraso. "
                        f"Regularize o pagamento para reativar o acesso. "
                        f"Contato: {EMAIL_FINANCEIRO} ({HORARIO_FINANCEIRO})."
                    )
                    for membro in membros:
                        if membro.super_admin:
                            continue
                        if not membro.bloqueado:
                            membro.bloqueado = True
                            membro.motivo_bloqueio = motivo
                            bloqueadas += 1

            session.commit()
            if bloqueadas:
                registrar_alteracao(usuario, f"{bloqueadas} usuário(s) bloqueado(s) por falta de pagamento")
            return bloqueadas
        except Exception as e:
            session.rollback()
            registrar_erro(e, "verificar_bloqueios_pagamento")
            return 0
        finally:
            session.close()

    @staticmethod
    def pagamento_a_vencer(conta_principal_id: int, dias_aviso: int = 3) -> Pagamento | None:
        session = get_session()
        try:
            hoje = date.today()
            pagamento = session.query(Pagamento).filter(
                Pagamento.conta_principal_id == conta_principal_id,
                Pagamento.status.in_([StatusPagamento.PENDENTE, StatusPagamento.ATRASADO]),
                Pagamento.deletado == False,
            ).order_by(Pagamento.vencimento.asc()).first()
            if not pagamento:
                return None
            dias_restantes = (pagamento.vencimento - hoje).days
            if dias_restantes <= dias_aviso:
                session.expunge(pagamento)
                return pagamento
            return None
        finally:
            session.close()

    @staticmethod
    def enviar_comprovante_imprensa(pagamento_id: int, comprovante_path: str,
                                     usuario: str = "sistema") -> None:
        """
        A empresa (imprensa) informa que pagou e anexa o comprovante.
        O pagamento fica "em processamento" (aguardando_confirmacao=True):
        não é contabilizado como pago ainda, só depois que a equipe financeira
        conferir e confirmar manualmente (ver `marcar_pago`). Notifica a
        equipe (integração + financeiro) por e-mail.
        """
        session = get_session()
        try:
            pagamento = session.get(Pagamento, pagamento_id)
            if not pagamento:
                raise ValidationError("Pagamento não encontrado.")
            if pagamento.status == StatusPagamento.PAGO:
                raise ValidationError("Este pagamento já foi confirmado.")
            if not (comprovante_path or "").strip():
                raise ValidationError("Anexe o comprovante do pagamento.")

            pagamento.comprovante_path = comprovante_path.strip()
            pagamento.aguardando_confirmacao = True
            pagamento.enviado_em = datetime.now()

            conta = session.get(Usuario, pagamento.conta_principal_id)
            nome_conta = conta.nome if conta else "Conta"
            login_conta = conta.login_completo if conta else "-"
            referencia = pagamento.referencia

            session.commit()
            registrar_alteracao(
                usuario, f"Comprovante da mensalidade {referencia} enviado, aguardando confirmação"
            )

            try:
                enviar_email_comprovante_enviado(nome_conta, login_conta, referencia, comprovante_path)
            except RuntimeError as e:
                registrar_erro(e, "enviar_comprovante_imprensa_email")
        except ValidationError:
            raise
        except Exception as e:
            session.rollback()
            registrar_erro(e, "enviar_comprovante_imprensa")
            raise
        finally:
            session.close()

    @staticmethod
    def marcar_pago(pagamento_id: int, usuario: str = "sistema") -> None:
        """
        Confirmação final do pagamento, feita exclusivamente pelo admin
        master. Só a partir daqui a mensalidade é de fato contabilizada
        como paga. Se havia um comprovante enviado pela imprensa aguardando
        confirmação, avisa a imprensa por e-mail que o pagamento foi
        confirmado.
        """
        session = get_session()
        try:
            pagamento = session.get(Pagamento, pagamento_id)
            if not pagamento:
                raise ValidationError("Pagamento não encontrado.")

            tinha_comprovante_pendente = pagamento.aguardando_confirmacao

            pagamento.status = StatusPagamento.PAGO
            pagamento.pago_em = datetime.now()
            pagamento.aguardando_confirmacao = False

            membros = session.query(Usuario).filter(
                (Usuario.id == pagamento.conta_principal_id)
                | (Usuario.conta_principal_id == pagamento.conta_principal_id)
            ).all()
            for membro in membros:
                if membro.bloqueado and "Mensalidade" in (membro.motivo_bloqueio or ""):
                    membro.bloqueado = False
                    membro.motivo_bloqueio = None

            conta = session.get(Usuario, pagamento.conta_principal_id)
            email_imprensa = conta.email if conta else None
            nome_conta = conta.nome if conta else "Conta"
            referencia = pagamento.referencia

            session.commit()
            registrar_alteracao(usuario, f"Pagamento {pagamento.referencia} marcado como pago")

            if tinha_comprovante_pendente and email_imprensa:
                try:
                    enviar_email_confirmacao_imprensa(email_imprensa, nome_conta, referencia)
                except RuntimeError as e:
                    registrar_erro(e, "marcar_pago_email_confirmacao")
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "marcar_pago")
            raise
        finally:
            session.close()

    @staticmethod
    def listar_todos() -> list[Pagamento]:
        """Lista os pagamentos de todas as contas (uso do painel do super administrador)."""
        session = get_session()
        try:
            pagamentos = session.query(Pagamento).filter_by(deletado=False).order_by(
                Pagamento.vencimento.desc()
            ).all()
            session.expunge_all()
            return pagamentos
        finally:
            session.close()

    @staticmethod
    def listar_por_conta(conta_principal_id: int) -> list[Pagamento]:
        session = get_session()
        try:
            pagamentos = session.query(Pagamento).filter_by(
                conta_principal_id=conta_principal_id, deletado=False
            ).order_by(Pagamento.vencimento.desc()).all()
            session.expunge_all()
            return pagamentos
        finally:
            session.close()

    @staticmethod
    def enviar_emails_cobranca(usuario: str = "sistema (automático)") -> int:
        """
        Envia e-mail de cobrança para a conta principal todo dia, a partir
        de 1 dia antes do vencimento até a data de corte (bloqueio
        automático por atraso), enquanto o pagamento do mês não for
        confirmado. No máximo um e-mail por dia por mensalidade.
        """
        session = get_session()
        enviados = 0
        try:
            hoje = date.today()
            pendentes = session.query(Pagamento).filter(
                Pagamento.status.in_([StatusPagamento.PENDENTE, StatusPagamento.ATRASADO]),
                Pagamento.deletado == False,
            ).all()

            for pagamento in pendentes:
                limite = adicionar_dias_uteis(pagamento.vencimento, DIAS_UTEIS_TOLERANCIA)
                inicio_cobranca = pagamento.vencimento - timedelta(days=1)
                if not (inicio_cobranca <= hoje <= limite):
                    continue
                if pagamento.ultimo_email_cobranca == hoje:
                    continue  # já enviado hoje

                conta = session.get(Usuario, pagamento.conta_principal_id)
                if not conta or not conta.email:
                    continue

                try:
                    enviar_email_cobranca(
                        conta.email, conta.nome, pagamento.referencia,
                        pagamento.vencimento, hoje > pagamento.vencimento,
                    )
                    pagamento.ultimo_email_cobranca = hoje
                    enviados += 1
                except RuntimeError as e:
                    registrar_erro(e, "enviar_emails_cobranca_envio")

            session.commit()
            if enviados:
                registrar_alteracao(usuario, f"{enviados} e-mail(s) de cobrança enviado(s)")
            return enviados
        except Exception as e:
            session.rollback()
            registrar_erro(e, "enviar_emails_cobranca")
            return 0
        finally:
            session.close()

    @staticmethod
    def solicitar_prorrogacao_emergencial(login: str) -> None:
        """
        Usuário bloqueado por falta de pagamento pode solicitar, uma única
        vez por mensalidade em atraso, uma prorrogação emergencial de 12h
        para acessar o sistema enquanto regulariza o pagamento. Libera
        imediatamente o acesso de toda a conta (admin + sub-usuários) e
        avisa a equipe (integração + financeiro) por e-mail.
        """
        session = get_session()
        try:
            login_bruto = (login or "").strip()
            if "@" not in login_bruto:
                raise ValidationError("Prorrogação disponível apenas para contas de empresa.")

            nome_usuario, _, sigla = login_bruto.partition("@")
            empresa = session.query(Empresa).filter(
                Empresa.sigla.ilike(sigla.strip()), Empresa.deletado == False
            ).first()
            if not empresa:
                raise ValidationError("Usuário não encontrado.")

            usuario = session.query(Usuario).filter_by(
                empresa_id=empresa.id, login=nome_usuario.strip(), deletado=False
            ).first()
            if not usuario:
                raise ValidationError("Usuário não encontrado.")

            conta_principal_id = usuario.conta_principal_id or usuario.id

            pagamento = session.query(Pagamento).filter(
                Pagamento.conta_principal_id == conta_principal_id,
                Pagamento.status.in_([StatusPagamento.PENDENTE, StatusPagamento.ATRASADO]),
                Pagamento.deletado == False,
            ).order_by(Pagamento.vencimento.desc()).first()

            if not pagamento:
                raise ValidationError("Não há mensalidade em aberto para solicitar prorrogação.")
            if pagamento.prorrogacao_utilizada:
                raise ValidationError(
                    "A prorrogação emergencial de 12h já foi utilizada para esta "
                    f"mensalidade. Fale com {EMAIL_FINANCEIRO} ({HORARIO_FINANCEIRO})."
                )

            pagamento.prorrogacao_utilizada = True
            pagamento.prorrogacao_expira = datetime.now() + timedelta(hours=PRORROGACAO_HORAS)

            membros = session.query(Usuario).filter(
                (Usuario.id == conta_principal_id) | (Usuario.conta_principal_id == conta_principal_id)
            ).all()
            for membro in membros:
                if membro.bloqueado and "Mensalidade" in (membro.motivo_bloqueio or ""):
                    membro.bloqueado = False
                    membro.motivo_bloqueio = None

            nome_solicitante = usuario.nome
            login_completo = usuario.login_completo
            referencia = pagamento.referencia
            novo_prazo = pagamento.prorrogacao_expira

            session.commit()
            registrar_alteracao(
                usuario.login,
                f"Prorrogação emergencial de 12h solicitada (mensalidade {referencia})",
            )

            try:
                enviar_email_prorrogacao_emergencial(
                    nome_solicitante, login_completo, referencia, novo_prazo,
                )
            except RuntimeError as e:
                registrar_erro(e, "solicitar_prorrogacao_emergencial_email")
        except ValidationError:
            raise
        except Exception as e:
            session.rollback()
            registrar_erro(e, "solicitar_prorrogacao_emergencial")
            raise
        finally:
            session.close()
