"""
utils/crypto_local.py
Cifra/decifra valores sensíveis (ex.: senha de app SMTP) para gravação no
banco local. A chave é derivada do device_id desta instalação (ver
utils/device.py), então o valor cifrado só pode ser lido neste mesmo
computador — se o database.db vazar ou for copiado para outra máquina,
o valor cifrado não é decifrável lá.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from utils.device import obter_device_id


def _obter_fernet() -> Fernet:
    chave_bruta = hashlib.sha256(obter_device_id().encode("utf-8")).digest()
    chave = base64.urlsafe_b64encode(chave_bruta)
    return Fernet(chave)


def cifrar(texto: str) -> str:
    """Cifra uma string; retorna o token cifrado (str)."""
    if not texto:
        return ""
    return _obter_fernet().encrypt(texto.encode("utf-8")).decode("utf-8")


def decifrar(token: str) -> str:
    """Decifra um token gerado por cifrar(); retorna '' se inválido/vazio
    (ex.: token cifrado em outro computador)."""
    if not token:
        return ""
    try:
        return _obter_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
