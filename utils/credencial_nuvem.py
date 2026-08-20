"""
utils/credencial_nuvem.py
Guarda o refresh_token do Supabase Auth (não a senha) cifrado em disco,
com chave derivada do device_id desta instalação — mesmo princípio já
usado para o fallback de SMTP: nada de sensível fica em texto puro, e a
chave não sai da máquina, então o arquivo cifrado sozinho não serve pra
nada fora dela.

Guardamos o refresh_token, não a senha: se vazar o arquivo cifrado e a
chave (só possível com acesso à própria máquina), dá pra revogar essa
sessão no Supabase Auth sem precisar trocar a senha de mais ninguém.
"""
from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from utils.device import obter_device_id
from utils.paths import pasta_base

_ARQUIVO = "nuvem_credencial.enc"


def _fernet() -> Fernet:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"al_caixa_nuvem", iterations=200_000)
    chave = base64.urlsafe_b64encode(kdf.derive(obter_device_id().encode("utf-8")))
    return Fernet(chave)


def salvar_refresh_token(refresh_token: str) -> None:
    caminho = os.path.join(pasta_base(), _ARQUIVO)
    try:
        with open(caminho, "wb") as f:
            f.write(_fernet().encrypt(refresh_token.encode("utf-8")))
    except OSError:
        pass


def carregar_refresh_token() -> str | None:
    caminho = os.path.join(pasta_base(), _ARQUIVO)
    if not os.path.exists(caminho):
        return None
    try:
        with open(caminho, "rb") as f:
            return _fernet().decrypt(f.read()).decode("utf-8")
    except (OSError, InvalidToken):
        return None


def limpar_refresh_token() -> None:
    caminho = os.path.join(pasta_base(), _ARQUIVO)
    try:
        os.remove(caminho)
    except OSError:
        pass
