"""
utils/security.py
Funções de segurança: hash/verificação de senha com bcrypt.
"""
import bcrypt


def gerar_hash_senha(senha: str) -> str:
    """Gera hash bcrypt seguro para uma senha em texto puro."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(senha.encode("utf-8"), salt).decode("utf-8")


def verificar_senha(senha: str, senha_hash: str) -> bool:
    """Verifica se a senha em texto puro corresponde ao hash armazenado."""
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
