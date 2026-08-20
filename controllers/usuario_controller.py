"""
controllers/usuario_controller.py
Regras de negócio para autenticação e gestão de usuários.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timedelta

from database import get_session
from models import Usuario, Permissao, Empresa
from sqlalchemy.orm import joinedload
from utils.security import gerar_hash_senha, verificar_senha
from utils.validators import (
    validar_senha, validar_texto_obrigatorio, ValidationError,
    validar_nome_usuario_login,
)
from utils.logger import registrar_erro, registrar_alteracao
from utils.email_sender import enviar_email_recuperacao, enviar_email_verificacao
from utils.nuvem_auth import solicitar_ativacao_empresa
from utils.device import obter_device_id

# Validação simples de formato de e-mail. Se preferir, mova para utils/validators.py
_EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Tempo de validade do código de recuperação enviado por e-mail
VALIDADE_CODIGO_RECUPERACAO_MIN = 15


class UsuarioController:
    """Controla cadastro, autenticação e permissões de usuários."""

    @staticmethod
    def total_usuarios() -> int:
        session = get_session()
        try:
            return session.query(Usuario).count()
        finally:
            session.close()

    @staticmethod
    def _validar_email(email: str) -> str:
        email = (email or "").strip().lower()
        if not email or not _EMAIL_REGEX.match(email):
            raise ValidationError("Informe um e-mail válido.")
        return email

    @staticmethod
    def criar_usuario(nome: str, login: str, senha: str, email: str,
                       permissao: Permissao = Permissao.USUARIO,
                       criado_por: Usuario | None = None) -> Usuario:
        """Cria um sub-usuário vinculado à mesma empresa/conta principal de
        quem o criou (mesmo que também seja Administrador).

        `criado_por` é obrigatório: novos usuários só são criados por um
        administrador já autenticado, dentro da empresa dele. O cadastro
        da própria empresa (que gera o admin raiz) é feito por
        EmpresaController.cadastrar, não por este método.
        """
        if criado_por is None:
            raise ValidationError("Um administrador precisa estar autenticado para criar usuários.")

        session = get_session()
        try:
            nome = validar_texto_obrigatorio(nome, "Nome", 120)
            login = validar_nome_usuario_login(login)
            senha = validar_senha(senha)
            email = UsuarioController._validar_email(email)

            empresa_id = criado_por.empresa_id
            if session.query(Usuario).filter_by(empresa_id=empresa_id, login=login).first():
                raise ValidationError("Este login já está em uso nesta empresa.")
            if session.query(Usuario).filter_by(email=email).first():
                raise ValidationError("Este e-mail já está em uso.")

            criado_por_id = criado_por.id
            conta_principal_id = criado_por.conta_principal_id or criado_por.id

            codigo = f"{random.randint(0, 999999):06d}"

            usuario = Usuario(
                nome=nome,
                login=login,
                email=email,
                senha_hash=gerar_hash_senha(senha),
                permissao=permissao,
                empresa_id=empresa_id,
                criado_por_id=criado_por_id,
                conta_principal_id=conta_principal_id,
                email_verificado=False,
                codigo_verificacao=codigo,
                codigo_verificacao_expira=datetime.now() + timedelta(minutes=VALIDADE_CODIGO_RECUPERACAO_MIN),
            )
            session.add(usuario)
            session.commit()
            session.refresh(usuario)
            session.expunge(usuario)
            registrar_alteracao(login, "Cadastro criado, aguardando verificação de e-mail")

            try:
                enviar_email_verificacao(usuario.email, usuario.nome, codigo)
            except RuntimeError:
                pass

            return usuario
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "criar_usuario")
            raise
        finally:
            session.close()

    @staticmethod
    def reenviar_codigo_verificacao(usuario_id: int) -> None:
        session = get_session()
        try:
            usuario = session.get(Usuario, usuario_id)
            if not usuario:
                raise ValidationError("Usuário não encontrado.")
            codigo = f"{random.randint(0, 999999):06d}"
            usuario.codigo_verificacao = codigo
            usuario.codigo_verificacao_expira = datetime.now() + timedelta(
                minutes=VALIDADE_CODIGO_RECUPERACAO_MIN
            )
            session.commit()
            enviar_email_verificacao(usuario.email, usuario.nome, codigo)
        except ValidationError:
            raise
        except Exception as e:
            session.rollback()
            registrar_erro(e, "reenviar_codigo_verificacao")
            raise
        finally:
            session.close()

    @staticmethod
    def verificar_codigo_email(usuario_id: int, codigo: str) -> None:
        session = get_session()
        try:
            usuario = session.get(Usuario, usuario_id)
            codigo = (codigo or "").strip()
            if (
                not usuario
                or not usuario.codigo_verificacao
                or usuario.codigo_verificacao != codigo
                or not usuario.codigo_verificacao_expira
                or datetime.now() > usuario.codigo_verificacao_expira
            ):
                raise ValidationError("Código inválido ou expirado. Solicite um novo código.")

            usuario.email_verificado = True
            usuario.codigo_verificacao = None
            usuario.codigo_verificacao_expira = None
            session.commit()
            registrar_alteracao(usuario.login, "E-mail verificado")

            # Só agora que o e-mail é confirmado a empresa é registrada na
            # nuvem, disparando o código de ativação para o super admin
            # (ver supabase/functions/solicitar-ativacao). Evita gerar
            # código para cadastros nunca confirmados.
            empresa = session.get(Empresa, usuario.empresa_id)
            if empresa:
                solicitar_ativacao_empresa({
                    "uuid": empresa.uuid,
                    "nome": empresa.nome,
                    "sigla": empresa.sigla,
                    "tipo_pessoa": empresa.tipo_pessoa.name,
                    "nome_completo": empresa.nome_completo,
                    "cpf": empresa.cpf,
                    "data_nascimento": empresa.data_nascimento.isoformat() if empresa.data_nascimento else None,
                    "razao_social": empresa.razao_social,
                    "nome_fantasia": empresa.nome_fantasia,
                    "cnpj": empresa.cnpj,
                    "device_id": obter_device_id(),
                })
        except ValidationError:
            raise
        except Exception as e:
            session.rollback()
            registrar_erro(e, "verificar_codigo_email")
            raise
        finally:
            session.close()

    @staticmethod
    def solicitar_recuperacao_senha(email: str) -> None:
        """
        Gera um código de verificação e envia por e-mail para o usuário dono
        do e-mail informado. Não revela se o e-mail existe ou não no sistema,
        por segurança (mensagem de sucesso deve ser mostrada de qualquer forma
        pela tela que chamar este método).
        """
        session = get_session()
        try:
            email = UsuarioController._validar_email(email)
            usuario = session.query(Usuario).filter_by(email=email, ativo=True).first()
            if not usuario:
                return

            codigo = f"{random.randint(0, 999999):06d}"
            usuario.reset_token = codigo
            usuario.reset_token_expira = datetime.now() + timedelta(
                minutes=VALIDADE_CODIGO_RECUPERACAO_MIN
            )
            session.commit()

            enviar_email_recuperacao(usuario.email, usuario.nome, codigo)
        except ValidationError:
            raise
        except Exception as e:
            session.rollback()
            registrar_erro(e, "solicitar_recuperacao_senha")
            raise
        finally:
            session.close()

    @staticmethod
    def redefinir_senha_com_codigo(email: str, codigo: str, nova_senha: str) -> None:
        """Valida o código de recuperação e define a nova senha do usuário."""
        session = get_session()
        try:
            email = UsuarioController._validar_email(email)
            nova_senha = validar_senha(nova_senha)
            codigo = (codigo or "").strip()

            usuario = session.query(Usuario).filter_by(email=email, ativo=True).first()
            if (
                not usuario
                or not usuario.reset_token
                or usuario.reset_token != codigo
                or not usuario.reset_token_expira
                or datetime.now() > usuario.reset_token_expira
            ):
                raise ValidationError("Código inválido ou expirado. Solicite um novo código.")

            usuario.senha_hash = gerar_hash_senha(nova_senha)
            usuario.reset_token = None
            usuario.reset_token_expira = None
            session.commit()
            registrar_alteracao(usuario.login, "Redefiniu a senha via recuperação por e-mail")
        except ValidationError:
            raise
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "redefinir_senha_com_codigo")
            raise
        finally:
            session.close()

    @staticmethod
    def autenticar(login: str, senha: str) -> Usuario | None:
        """
        Retorna o usuário autenticado, ou None se as credenciais forem inválidas.
        Lança ValidationError se o usuário existir e a senha estiver certa, mas
        a conta estiver bloqueada ou o e-mail ainda não tiver sido verificado.

        Formato esperado: "usuario@SIGLA" (a sigla identifica a empresa).
        Exceção: o super administrador da plataforma não tem empresa e
        autentica apenas com o próprio login (sem "@").
        """
        session = get_session()
        try:
            login_bruto = (login or "").strip()

            if "@" in login_bruto:
                nome_usuario, _, sigla = login_bruto.partition("@")
                nome_usuario = nome_usuario.strip()
                sigla = sigla.strip()
                empresa = session.query(Empresa).filter(
                    Empresa.sigla.ilike(sigla), Empresa.deletado == False
                ).first()
                if not empresa:
                    return None
                usuario = session.query(Usuario).filter(
                    Usuario.empresa_id == empresa.id, Usuario.login.ilike(nome_usuario),
                    Usuario.ativo == True, Usuario.deletado == False,  # noqa: E712
                ).first()
            else:
                usuario = session.query(Usuario).filter(
                    Usuario.login.ilike(login_bruto), Usuario.ativo == True,  # noqa: E712
                    Usuario.super_admin == True, Usuario.deletado == False,  # noqa: E712
                ).first()

            if not usuario or not verificar_senha(senha, usuario.senha_hash):
                return None
            if usuario.bloqueado:
                raise ValidationError(usuario.motivo_bloqueio or "Conta bloqueada. Fale com o administrador.")
            if not usuario.email_verificado:
                raise ValidationError("E-mail ainda não verificado. Confirme o código enviado ao seu e-mail.")
            _ = usuario.empresa  # força o carregamento antes de destacar da sessão
            session.expunge(usuario)
            return usuario
        except ValidationError:
            raise
        except Exception as e:
            registrar_erro(e, "autenticar")
            return None
        finally:
            session.close()

    @staticmethod
    def usuario_nao_verificado(login: str) -> Usuario | None:
        """Retorna o usuário se ele existir mas ainda não tiver e-mail verificado."""
        session = get_session()
        try:
            login_bruto = (login or "").strip()
            if "@" in login_bruto:
                nome_usuario, _, sigla = login_bruto.partition("@")
                empresa = session.query(Empresa).filter(Empresa.sigla.ilike(sigla.strip())).first()
                if not empresa:
                    return None
                usuario = session.query(Usuario).filter(
                    Usuario.empresa_id == empresa.id, Usuario.login.ilike(nome_usuario.strip())
                ).first()
            else:
                usuario = session.query(Usuario).filter(
                    Usuario.login.ilike(login_bruto), Usuario.super_admin == True,  # noqa: E712
                ).first()
            if usuario and not usuario.email_verificado:
                session.expunge(usuario)
                return usuario
            return None
        finally:
            session.close()

    @staticmethod
    def listar_usuarios() -> list[Usuario]:
        session = get_session()
        try:
            usuarios = session.query(Usuario).options(
                joinedload(Usuario.empresa)
            ).filter_by(deletado=False).order_by(Usuario.nome).all()
            session.expunge_all()
            return usuarios
        finally:
            session.close()

    @staticmethod
    def alterar_permissao(usuario_id: int, permissao: Permissao) -> None:
        session = get_session()
        try:
            usuario = session.get(Usuario, usuario_id)
            if usuario:
                usuario.permissao = permissao
                session.commit()
        finally:
            session.close()

    @staticmethod
    def alterar_permissoes_modulos(usuario_id: int, modulos: list[str]) -> None:
        """Define a lista de módulos liberados para um sub-usuário (permissao=Usuario)."""
        session = get_session()
        try:
            usuario = session.get(Usuario, usuario_id)
            if usuario:
                usuario.permissoes_modulos = ",".join(modulos)
                session.commit()
        finally:
            session.close()

    @staticmethod
    def desativar_usuario(usuario_id: int) -> None:
        session = get_session()
        try:
            usuario = session.get(Usuario, usuario_id)
            if usuario:
                usuario.ativo = False
                session.commit()
        finally:
            session.close()

    @staticmethod
    def reativar_usuario(usuario_id: int) -> None:
        session = get_session()
        try:
            usuario = session.get(Usuario, usuario_id)
            if usuario:
                usuario.ativo = True
                session.commit()
        finally:
            session.close()

    @staticmethod
    def bloquear_usuario(usuario_id: int, motivo: str = "Bloqueado pelo administrador.",
                          usuario_admin: str = "sistema") -> None:
        session = get_session()
        try:
            usuario = session.get(Usuario, usuario_id)
            if not usuario:
                return
            if usuario.super_admin:
                raise ValidationError("Este usuário pertence à equipe de integração e não pode ser bloqueado.")
            usuario.bloqueado = True
            usuario.motivo_bloqueio = motivo
            session.commit()
            registrar_alteracao(usuario_admin, f"Usuário bloqueado: {usuario.login}")
        except ValidationError:
            raise
        finally:
            session.close()

    @staticmethod
    def desbloquear_usuario(usuario_id: int, usuario_admin: str = "sistema") -> None:
        session = get_session()
        try:
            usuario = session.get(Usuario, usuario_id)
            if usuario:
                usuario.bloqueado = False
                usuario.motivo_bloqueio = None
                session.commit()
                registrar_alteracao(usuario_admin, f"Usuário desbloqueado: {usuario.login}")
        finally:
            session.close()

    @staticmethod
    def excluir_usuario(usuario_id: int, usuario_admin: str = "sistema") -> None:
        """
        Exclusão definitiva de um único usuário, feita exclusivamente pelo
        super administrador da plataforma. Usa soft-delete (campo
        `deletado`) para que a exclusão seja propagada corretamente para a
        nuvem no próximo ciclo de sincronização; a conta some de imediato
        das listagens e não consegue mais autenticar.
        """
        session = get_session()
        try:
            usuario = session.get(Usuario, usuario_id)
            if not usuario:
                raise ValidationError("Usuário não encontrado.")
            if usuario.super_admin:
                raise ValidationError("Não é possível excluir o super administrador da plataforma.")

            usuario.deletado = True
            usuario.ativo = False
            usuario.bloqueado = True
            usuario.motivo_bloqueio = "Conta excluída pelo administrador da plataforma."
            login_completo = usuario.login_completo
            # Libera o e-mail cadastrado para que possa ser usado em um novo
            # cadastro (a coluna email é única no banco).
            usuario.email = None
            session.commit()
            registrar_alteracao(usuario_admin, f"Usuário excluído da nuvem: {login_completo}")
        except ValidationError:
            raise
        except Exception as e:
            session.rollback()
            registrar_erro(e, "excluir_usuario")
            raise
        finally:
            session.close()

    @staticmethod
    def listar_por_conta(conta_principal_id: int) -> list[Usuario]:
        session = get_session()
        try:
            usuarios = session.query(Usuario).filter(
                (Usuario.id == conta_principal_id) | (Usuario.conta_principal_id == conta_principal_id)
            ).order_by(Usuario.criado_em).all()
            session.expunge_all()
            return usuarios
        finally:
            session.close()

    @staticmethod
    def listar_por_empresa(empresa_id: int) -> list[Usuario]:
        session = get_session()
        try:
            usuarios = session.query(Usuario).filter_by(
                empresa_id=empresa_id
            ).order_by(Usuario.criado_em).all()
            session.expunge_all()
            return usuarios
        finally:
            session.close()

    @staticmethod
    def redefinir_senha_super_admin(login: str, nova_senha: str) -> None:
        """Redefine a senha do super administrador já existente (uso do
        script de provisionamento, quando o Aykon já foi criado antes)."""
        session = get_session()
        try:
            nova_senha = validar_senha(nova_senha)
            usuario = session.query(Usuario).filter_by(login=login, super_admin=True).first()
            if not usuario:
                raise ValidationError("Super administrador não encontrado.")
            usuario.senha_hash = gerar_hash_senha(nova_senha)
            session.commit()
            registrar_alteracao(login, "Senha do super administrador redefinida")
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "redefinir_senha_super_admin")
            raise
        finally:
            session.close()

    @staticmethod
    def criar_super_admin(nome: str, login: str, senha: str, email: str) -> Usuario:
        """
        Cria o super administrador da plataforma (ex.: Aykon). Não pertence
        a nenhuma empresa e enxerga o sistema inteiro pelo painel
        administrativo separado. Uso restrito a scripts de provisionamento
        (ver criar_admin_master.py); não é exposto em nenhuma tela do app
        principal.
        """
        session = get_session()
        try:
            nome = validar_texto_obrigatorio(nome, "Nome", 120)
            login = validar_nome_usuario_login(login)
            senha = validar_senha(senha)
            email = UsuarioController._validar_email(email)

            if session.query(Usuario).filter_by(login=login, super_admin=True).first():
                raise ValidationError("Já existe um super administrador com este login.")
            if session.query(Usuario).filter_by(email=email).first():
                raise ValidationError("Este e-mail já está em uso.")

            usuario = Usuario(
                nome=nome,
                login=login,
                email=email,
                senha_hash=gerar_hash_senha(senha),
                permissao=Permissao.ADMIN,
                empresa_id=None,
                super_admin=True,
                email_verificado=True,
            )
            session.add(usuario)
            session.commit()
            session.refresh(usuario)
            session.expunge(usuario)
            registrar_alteracao(login, "Super administrador da plataforma criado")
            return usuario
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "criar_super_admin")
            raise
        finally:
            session.close()

    @staticmethod
    def listar_contas_principais() -> list[Usuario]:
        session = get_session()
        try:
            usuarios = session.query(Usuario).filter_by(conta_principal_id=None).order_by(Usuario.nome).all()
            session.expunge_all()
            return usuarios
        finally:
            session.close()
