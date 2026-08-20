"""
controllers/config_controller.py
Leitura e gravação de configurações do sistema (tema, moeda, pasta de
exportação) armazenadas na tabela configuracoes como pares chave/valor.
"""
from __future__ import annotations

import os

from database import get_session
from models import Configuracao

from utils.paths import pasta_base
from utils.crypto_local import cifrar, decifrar
BASE_DIR = pasta_base()

CHAVE_SMTP_USER = "smtp_usuario"
CHAVE_SMTP_SENHA = "smtp_senha_cifrada"

PADROES = {
    "tema": "dark",
    "moeda": "R$",
    "pasta_exportacao": os.path.join(BASE_DIR, "exports"),
    "etiqueta_largura_mm": "",
    "etiqueta_altura_mm": "",
    "recibo_largura_mm": "",
    "impressora_recibo": "",
    "impressora_etiqueta": "",
    "desconto_maximo_percentual": "0",
    "acrescimo_maximo_percentual": "0",
}


class ConfigController:
    """Gerencia configurações persistentes do sistema."""

    @staticmethod
    def obter(chave: str) -> str:
        session = get_session()
        try:
            config = session.query(Configuracao).filter_by(chave=chave).first()
            if config:
                return config.valor
            return PADROES.get(chave, "")
        finally:
            session.close()

    @staticmethod
    def definir(chave: str, valor: str) -> None:
        session = get_session()
        try:
            config = session.query(Configuracao).filter_by(chave=chave).first()
            if config:
                config.valor = valor
            else:
                session.add(Configuracao(chave=chave, valor=valor))
            session.commit()
        finally:
            session.close()

    @staticmethod
    def obter_todas() -> dict:
        session = get_session()
        try:
            configs = {c.chave: c.valor for c in session.query(Configuracao).all()}
            resultado = dict(PADROES)
            resultado.update(configs)
            return resultado
        finally:
            session.close()

    @staticmethod
    def obter_smtp() -> tuple[str, str]:
        """Retorna (usuario, senha) do e-mail do sistema configurado no app
        (Configurações > Administração). Senha fica cifrada no banco, ligada
        a este computador; retorna ('', '') se não configurado."""
        usuario = ConfigController.obter(CHAVE_SMTP_USER)
        senha = decifrar(ConfigController.obter(CHAVE_SMTP_SENHA))
        return usuario, senha

    @staticmethod
    def salvar_smtp(usuario: str, senha: str) -> None:
        """Salva as credenciais do e-mail do sistema; a senha é cifrada
        antes de gravar no banco."""
        ConfigController.definir(CHAVE_SMTP_USER, usuario.strip())
        ConfigController.definir(CHAVE_SMTP_SENHA, cifrar(senha.strip()))
