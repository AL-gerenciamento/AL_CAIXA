"""
controllers/mensagem_controller.py
Envio de mensagens por e-mail para usuários da plataforma. Usado pelo
super administrador, no painel administrativo separado
(admin_panel/app.py), para comunicados em massa: para todos os usuários,
somente administradores, todos os usuários de uma empresa específica, ou
um único usuário.
"""
from __future__ import annotations

from database import get_session
from models import Permissao, Usuario
from utils.email_sender import enviar_email_mensagem_admin
from utils.logger import registrar_erro

DESTINO_TODOS = "todos"
DESTINO_ADMINS = "admins"
DESTINO_EMPRESA = "empresa"
DESTINO_USUARIO = "usuario"

_DESTINOS_VALIDOS = {DESTINO_TODOS, DESTINO_ADMINS, DESTINO_EMPRESA, DESTINO_USUARIO}


class MensagemController:

    @staticmethod
    def _destinatarios(destino: str, destino_id: int | None) -> list[Usuario]:
        if destino not in _DESTINOS_VALIDOS:
            raise ValueError(f"Destino desconhecido: {destino}")
        if destino in (DESTINO_EMPRESA, DESTINO_USUARIO) and destino_id is None:
            raise ValueError("Selecione o destinatário.")

        sessao = get_session()
        try:
            consulta = sessao.query(Usuario).filter(
                Usuario.deletado.is_(False), Usuario.ativo.is_(True)
            )
            if destino == DESTINO_ADMINS:
                consulta = consulta.filter(
                    (Usuario.permissao == Permissao.ADMIN) | (Usuario.super_admin.is_(True))
                )
            elif destino == DESTINO_EMPRESA:
                consulta = consulta.filter(Usuario.empresa_id == destino_id)
            elif destino == DESTINO_USUARIO:
                consulta = consulta.filter(Usuario.id == destino_id)

            usuarios = consulta.all()
            for usuario in usuarios:
                sessao.expunge(usuario)
            return usuarios
        finally:
            sessao.close()

    @staticmethod
    def contar_destinatarios(destino: str, destino_id: int | None = None) -> int:
        """Quantos usuários do grupo escolhido têm e-mail cadastrado (efetivamente alcançáveis)."""
        return sum(1 for u in MensagemController._destinatarios(destino, destino_id) if u.email)

    @staticmethod
    def enviar(destino: str, assunto: str, corpo: str, destino_id: int | None = None) -> dict:
        """
        Envia a mensagem por e-mail para os destinatários do grupo escolhido.

        Retorna:
            {"enviados": int, "sem_email": int, "falhas": list[str]}
        """
        assunto = (assunto or "").strip()
        corpo = (corpo or "").strip()
        if not assunto:
            raise ValueError("Informe o assunto da mensagem.")
        if not corpo:
            raise ValueError("Informe o conteúdo da mensagem.")

        usuarios = MensagemController._destinatarios(destino, destino_id)
        enviados = 0
        sem_email = 0
        falhas: list[str] = []

        for usuario in usuarios:
            if not usuario.email:
                sem_email += 1
                continue
            try:
                enviar_email_mensagem_admin(usuario.email, usuario.nome, assunto, corpo)
                enviados += 1
            except Exception as e:
                registrar_erro(e, "mensagem_controller_enviar")
                falhas.append(usuario.email)

        return {"enviados": enviados, "sem_email": sem_email, "falhas": falhas}
