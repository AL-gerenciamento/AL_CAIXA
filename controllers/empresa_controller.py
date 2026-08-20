"""
controllers/empresa_controller.py
Cadastro de empresas (tenants) e do respectivo usuário administrador
principal, criados juntos em uma única operação atômica.

Regras:
- Nome e sigla da empresa são únicos e imutáveis após o cadastro (não há
  método de alteração aqui de propósito).
- Pessoa Física exige nome completo, CPF (validado) e data de nascimento.
- Pessoa Jurídica exige razão social, nome fantasia e CNPJ (validado).
- O usuário criado junto com a empresa é sempre Administrador
  (conta principal, criado_por_id = None).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import os
import random
import shutil
import uuid

from database import get_session, get_session_cloud
from utils.paths import pasta_base
from models import Empresa, TipoPessoa, Usuario, Permissao
from utils.security import gerar_hash_senha
from utils.validators import (
    ValidationError, validar_nome_empresa, validar_sigla, validar_cpf,
    validar_cnpj, validar_texto_obrigatorio, validar_nome_usuario_login,
    validar_senha,
)
from utils.logger import registrar_erro, registrar_alteracao
from utils.email_sender import enviar_email_verificacao
from utils import nuvem_auth

_EMAIL_REGEX_MSG = "Informe um e-mail válido."


def _validar_email(email: str) -> str:
    import re
    email = (email or "").strip().lower()
    if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ValidationError(_EMAIL_REGEX_MSG)
    return email


class EmpresaController:
    """Cadastro e consulta de empresas (tenants) do sistema."""

    @staticmethod
    def listar_todas() -> list[Empresa]:
        session = get_session()
        try:
            empresas = session.query(Empresa).filter_by(
                deletado=False
            ).order_by(Empresa.nome).all()
            session.expunge_all()
            return empresas
        finally:
            session.close()

    @staticmethod
    def definir_nuvem_liberada(empresa_id: int, liberada: bool) -> None:
        """Super admin liga/desliga o acesso à nuvem de uma empresa (ex.: inadimplência)."""
        session = get_session_cloud() or get_session()
        try:
            empresa = session.get(Empresa, empresa_id)
            if not empresa:
                raise ValidationError("Empresa não encontrada.")
            empresa.nuvem_liberada = liberada
            session.commit()
        finally:
            session.close()

    @staticmethod
    def excluir_empresa(empresa_id: int, usuario_admin: str = "sistema") -> None:
        """
        Exclusão definitiva de uma empresa inteira (todos os seus
        usuários), feita exclusivamente pelo super administrador da
        plataforma. Usa soft-delete (campo `deletado`) para que a exclusão
        seja propagada corretamente para a nuvem no próximo ciclo de
        sincronização.
        """
        session = get_session()
        try:
            empresa = session.get(Empresa, empresa_id)
            if not empresa:
                raise ValidationError("Empresa não encontrada.")

            empresa.deletado = True
            usuarios = session.query(Usuario).filter_by(empresa_id=empresa_id).all()
            for usuario in usuarios:
                usuario.deletado = True
                usuario.ativo = False
                usuario.bloqueado = True
                usuario.motivo_bloqueio = "Empresa excluída pelo administrador da plataforma."
                # Libera o e-mail cadastrado (coluna única) para reuso futuro.
                usuario.email = None

            nome_empresa, sigla_empresa = empresa.nome, empresa.sigla
            session.commit()
            registrar_alteracao(
                usuario_admin, f"Empresa excluída da nuvem: {nome_empresa} ({sigla_empresa})"
            )
        except ValidationError:
            raise
        except Exception as e:
            session.rollback()
            registrar_erro(e, "excluir_empresa")
            raise
        finally:
            session.close()

    @staticmethod
    def cadastrar(
        tipo_pessoa: TipoPessoa,
        nome_empresa: str,
        sigla_empresa: str,
        admin_nome_completo_login: str,
        admin_senha: str,
        admin_email: str,
        *,
        # Pessoa Física
        nome_completo: str | None = None,
        cpf: str | None = None,
        data_nascimento: date | None = None,
        # Pessoa Jurídica
        razao_social: str | None = None,
        nome_fantasia: str | None = None,
        cnpj: str | None = None,
    ) -> tuple[Empresa, Usuario]:
        """
        Cadastra a empresa e o usuário administrador principal em uma
        única transação. Retorna (empresa, usuario_admin).
        """
        session = get_session()
        try:
            nome_empresa = validar_nome_empresa(nome_empresa)
            sigla_empresa = validar_sigla(sigla_empresa)
            admin_login = validar_nome_usuario_login(admin_nome_completo_login)
            admin_senha = validar_senha(admin_senha)
            admin_email = _validar_email(admin_email)

            if session.query(Empresa).filter(Empresa.nome.ilike(nome_empresa)).first():
                raise ValidationError("Já existe uma empresa cadastrada com este nome.")
            if session.query(Empresa).filter(Empresa.sigla.ilike(sigla_empresa)).first():
                raise ValidationError("Já existe uma empresa cadastrada com esta sigla.")
            if session.query(Usuario).filter_by(email=admin_email).first():
                raise ValidationError("Este e-mail já está em uso.")

            dados_empresa = dict(
                nome=nome_empresa, sigla=sigla_empresa, tipo_pessoa=tipo_pessoa,
            )

            if tipo_pessoa == TipoPessoa.FISICA:
                nome_completo = validar_texto_obrigatorio(nome_completo, "Nome completo", 150)
                cpf = validar_cpf(cpf)
                if not data_nascimento:
                    raise ValidationError("Informe a data de nascimento.")
                if session.query(Empresa).filter_by(cpf=cpf).first():
                    raise ValidationError("Já existe um cadastro com este CPF.")
                dados_empresa.update(
                    nome_completo=nome_completo, cpf=cpf, data_nascimento=data_nascimento,
                )
            elif tipo_pessoa == TipoPessoa.JURIDICA:
                razao_social = validar_texto_obrigatorio(razao_social, "Razão Social", 150)
                nome_fantasia = validar_texto_obrigatorio(nome_fantasia, "Nome Fantasia", 150)
                cnpj = validar_cnpj(cnpj)
                if session.query(Empresa).filter_by(cnpj=cnpj).first():
                    raise ValidationError("Já existe um cadastro com este CNPJ.")
                dados_empresa.update(
                    razao_social=razao_social, nome_fantasia=nome_fantasia, cnpj=cnpj,
                )
            else:
                raise ValidationError("Selecione o tipo de pessoa: Física ou Jurídica.")

            empresa = Empresa(**dados_empresa)
            session.add(empresa)
            session.flush()  # garante empresa.id antes de criar o usuário

            # Login já validado quanto a formato; unicidade é garantida pela
            # UniqueConstraint(empresa_id, login), mas como a empresa é nova
            # não há conflito possível aqui.
            codigo = f"{random.randint(0, 999999):06d}"
            admin_nome = nome_completo or razao_social or admin_login

            usuario = Usuario(
                nome=admin_nome,
                login=admin_login,
                email=admin_email,
                senha_hash=gerar_hash_senha(admin_senha),
                permissao=Permissao.ADMIN,
                empresa_id=empresa.id,
                criado_por_id=None,
                conta_principal_id=None,
                email_verificado=False,
                codigo_verificacao=codigo,
                codigo_verificacao_expira=datetime.now() + timedelta(minutes=15),
            )
            session.add(usuario)
            session.commit()
            session.refresh(empresa)
            session.refresh(usuario)
            session.expunge(empresa)
            session.expunge(usuario)

            registrar_alteracao(
                admin_login, f"Empresa cadastrada: {nome_empresa} ({sigla_empresa})"
            )

            try:
                enviar_email_verificacao(usuario.email, usuario.nome, codigo)
            except RuntimeError:
                pass

            dados_ativacao = dict(
                uuid=str(empresa.uuid),
                nome=empresa.nome,
                sigla=empresa.sigla,
                tipo_pessoa=empresa.tipo_pessoa.value,
            )
            if tipo_pessoa == TipoPessoa.FISICA:
                dados_ativacao.update(
                    nome_completo=empresa.nome_completo,
                    cpf=empresa.cpf,
                    data_nascimento=empresa.data_nascimento.isoformat()
                    if empresa.data_nascimento else None,
                )
            else:
                dados_ativacao.update(
                    razao_social=empresa.razao_social,
                    nome_fantasia=empresa.nome_fantasia,
                    cnpj=empresa.cnpj,
                )
            nuvem_auth.solicitar_ativacao_empresa(dados_ativacao)

            return empresa, usuario
        except Exception as e:
            session.rollback()
            if not isinstance(e, ValidationError):
                registrar_erro(e, "cadastrar_empresa")
            raise
        finally:
            session.close()

    @staticmethod
    def definir_logo(empresa_id: int, caminho_origem: str) -> str:
        """Copia a imagem escolhida para assets/images e vincula à empresa."""
        session = get_session()
        try:
            empresa = session.get(Empresa, empresa_id)
            if not empresa:
                raise ValidationError("Empresa não encontrada.")

            pasta = os.path.join(pasta_base(), "assets", "images")
            os.makedirs(pasta, exist_ok=True)
            extensao = os.path.splitext(caminho_origem)[1]
            nome_arquivo = f"logo_{empresa_id}_{uuid.uuid4().hex[:8]}{extensao}"
            destino = os.path.join(pasta, nome_arquivo)
            shutil.copy2(caminho_origem, destino)

            empresa.logo_path = destino
            session.commit()
            registrar_alteracao("sistema", f"Logo atualizado para a empresa {empresa.sigla}")
            return destino
        except ValidationError:
            raise
        except Exception as e:
            session.rollback()
            registrar_erro(e, "definir_logo")
            raise
        finally:
            session.close()
