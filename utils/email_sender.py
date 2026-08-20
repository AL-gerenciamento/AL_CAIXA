"""
utils/email_sender.py
Envio de e-mails via Worker Cloudflare (o Worker fala SMTP com o Gmail;
a senha SMTP fica cifrada só no lado do Worker, nunca neste executável).
Painel: Cloudflare > Workers > email-worker.
"""
import base64
import os

import httpx

from utils.logger import registrar_erro

WORKER_URL = os.getenv("EMAIL_WORKER_URL", "https://email-worker.algl-gerenciamento.workers.dev")
WORKER_API_KEY = os.getenv("EMAIL_WORKER_API_KEY", "bacon")

EMAIL_FINANCEIRO = "algl.gerenciamento@gmail.com"
HORARIO_FINANCEIRO = "segunda a sexta, das 14h às 17h"
EMAIL_SUPER_ADMIN = "aykonlucas63@gmail.com"


def _enviar(to, subject: str, text: str, attachment: dict | None = None) -> None:
    payload = {"to": to, "subject": subject, "text": text}
    if attachment:
        payload["attachment"] = attachment
    try:
        resp = httpx.post(
            WORKER_URL,
            headers={"Authorization": f"Bearer {WORKER_API_KEY}"},
            json=payload,
            timeout=20,
        )
        dados = resp.json()
        if not dados.get("ok"):
            raise RuntimeError(dados.get("erro", "erro desconhecido"))
    except Exception as e:
        registrar_erro(e, "email_sender._enviar")
        raise RuntimeError(
            "Não foi possível enviar o e-mail. Tente novamente mais tarde."
        ) from e


def enviar_email_mensagem_admin(destinatario: str, nome_usuario: str, assunto: str, corpo: str) -> None:
    corpo_final = f"Olá, {nome_usuario}!\n\n{corpo}\n"
    _enviar(destinatario, assunto, corpo_final)


def enviar_email_recuperacao(destinatario: str, nome_usuario: str, codigo: str) -> None:
    assunto = "Recuperação de senha - AL Gerenciamento"
    corpo = (
        f"Olá, {nome_usuario}!\n\n"
        f"Recebemos uma solicitação para redefinir sua senha no sistema "
        f"AL Gerenciamento.\n\n"
        f"Seu código de verificação é: {codigo}\n\n"
        f"Esse código é válido por 15 minutos. Se você não solicitou essa "
        f"recuperação, apenas ignore este e-mail; sua senha continuará a mesma.\n"
    )
    _enviar(destinatario, assunto, corpo)


def enviar_email_verificacao(destinatario: str, nome_usuario: str, codigo: str) -> None:
    assunto = "Confirme seu e-mail - AL Gerenciamento"
    corpo = (
        f"Olá, {nome_usuario}!\n\n"
        f"Para concluir seu cadastro no sistema AL Gerenciamento, informe "
        f"o código de verificação abaixo:\n\n"
        f"Código: {codigo}\n\n"
        f"Esse código é válido por 15 minutos.\n"
    )
    _enviar(destinatario, assunto, corpo)


def enviar_email_cobranca(destinatario: str, nome_usuario: str, referencia: str,
                           vencimento, atrasado: bool) -> None:
    data_formatada = vencimento.strftime("%d/%m/%Y")
    if atrasado:
        assunto = f"Mensalidade {referencia} em atraso - AL Gerenciamento"
        corpo = (
            f"Olá, {nome_usuario}!\n\n"
            f"Sua mensalidade referente a {referencia}, com vencimento em "
            f"{data_formatada}, ainda não foi confirmada como paga.\n\n"
            f"Regularize o quanto antes para evitar (ou encerrar, caso já "
            f"esteja em curso) o bloqueio automático do acesso.\n\n"
            f"Dúvidas ou já efetuou o pagamento? Fale com a gente: "
            f"{EMAIL_FINANCEIRO} ({HORARIO_FINANCEIRO}).\n"
        )
    else:
        assunto = f"Mensalidade {referencia} vence amanhã - AL Gerenciamento"
        corpo = (
            f"Olá, {nome_usuario}!\n\n"
            f"Passando para lembrar que sua mensalidade referente a "
            f"{referencia} vence em {data_formatada}.\n\n"
            f"Regularize o pagamento até a data de vencimento para evitar o "
            f"bloqueio automático da conta.\n\n"
            f"Dúvidas? Fale com a gente: {EMAIL_FINANCEIRO} ({HORARIO_FINANCEIRO}).\n"
        )
    _enviar(destinatario, assunto, corpo)


def enviar_email_comprovante_enviado(nome_conta: str, login_completo: str, referencia: str,
                                      comprovante_path: str) -> None:
    destinatarios = [EMAIL_SUPER_ADMIN, EMAIL_FINANCEIRO]
    assunto = f"Comprovante de pagamento enviado - {login_completo}"
    corpo = (
        f"A conta {nome_conta} ({login_completo}) marcou a mensalidade "
        f"{referencia} como paga e anexou o comprovante (em anexo neste e-mail).\n\n"
        f"O pagamento está em processamento e só será contabilizado após a "
        f"confirmação da equipe financeira.\n"
    )

    attachment = None
    if comprovante_path and os.path.isfile(comprovante_path):
        with open(comprovante_path, "rb") as arquivo:
            conteudo_base64 = base64.b64encode(arquivo.read()).decode("ascii")
        attachment = {
            "filename": os.path.basename(comprovante_path),
            "content_base64": conteudo_base64,
            "content_type": "application/octet-stream",
        }
    else:
        registrar_erro(
            FileNotFoundError(comprovante_path or "(vazio)"),
            "enviar_email_comprovante_enviado_anexo_ausente",
        )

    _enviar(destinatarios, assunto, corpo, attachment)


def enviar_email_confirmacao_imprensa(destinatario: str, nome_conta: str, referencia: str) -> None:
    assunto = f"Pagamento confirmado - Mensalidade {referencia}"
    corpo = (
        f"Olá, {nome_conta}!\n\n"
        f"Confirmamos o recebimento do pagamento da mensalidade {referencia}. "
        f"O acesso está regularizado.\n\n"
        f"Obrigado!\n"
    )
    _enviar(destinatario, assunto, corpo)


def enviar_email_prorrogacao_emergencial(nome_solicitante: str, login_completo: str,
                                          referencia: str, novo_prazo) -> None:
    destinatarios = [EMAIL_SUPER_ADMIN, EMAIL_FINANCEIRO]
    assunto = f"Prorrogação emergencial de 12h solicitada - {login_completo}"
    corpo = (
        f"O usuário {nome_solicitante} ({login_completo}) solicitou a "
        f"prorrogação emergencial de 12h de acesso por falta de pagamento.\n\n"
        f"Mensalidade em atraso: {referencia}\n"
        f"Acesso liberado até: {novo_prazo.strftime('%d/%m/%Y %H:%M')}\n\n"
        f"Se o pagamento não for regularizado até esse horário, o bloqueio "
        f"automático será reaplicado.\n"
    )
    _enviar(destinatarios, assunto, corpo)
