"""
utils/pix_payload.py
Construção do payload Pix "copia e cola" (padrão EMV/BR Code do Banco
Central), usado tanto pela chave Pix da loja (controllers/pix_controller.py)
quanto pelo Pix da mensalidade da plataforma (controllers/pagamento_controller.py).
"""
from __future__ import annotations

import re
import unicodedata

TIPOS_CHAVE = ["CPF", "CNPJ", "E-mail", "Telefone", "Chave aleatória"]


def normalizar_chave(chave: str, tipo: str) -> str:
    """Normaliza a chave Pix para o formato exigido pelo Banco Central conforme o tipo.

    Chaves com pontuação (CPF/CNPJ/telefone formatados) não são reconhecidas pelos
    bancos — precisam estar "cruas".
    """
    chave = (chave or "").strip()
    if tipo in ("CPF", "CNPJ"):
        return re.sub(r"\D", "", chave)
    if tipo == "Telefone":
        digitos = re.sub(r"\D", "", chave)
        if digitos.startswith("55") and len(digitos) in (12, 13):
            return "+" + digitos
        return "+55" + digitos
    if tipo == "E-mail":
        return chave.lower()
    return chave  # chave aleatória (EVP): mantém exatamente como cadastrada


def _normalizar_texto(texto: str, tamanho_maximo: int) -> str:
    """Remove acentos e caracteres não suportados pelo padrão EMV, maiúsculas."""
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    limpo = re.sub(r"[^A-Za-z0-9 ]", "", sem_acento).strip().upper() or "NAO INFORMADO"
    return limpo[:tamanho_maximo]


def _campo(id_campo: str, valor: str) -> str:
    return f"{id_campo}{len(valor):02d}{valor}"


def _crc16(payload: str) -> str:
    """CRC16-CCITT (0xFFFF), exigido ao final do payload Pix."""
    polinomio = 0x1021
    resultado = 0xFFFF
    for byte in payload.encode("utf-8"):
        resultado ^= byte << 8
        for _ in range(8):
            if resultado & 0x8000:
                resultado = ((resultado << 1) ^ polinomio) & 0xFFFF
            else:
                resultado = (resultado << 1) & 0xFFFF
    return f"{resultado:04X}"


class PixNaoConfiguradoError(Exception):
    pass


def gerar_payload(
    chave: str, tipo_chave: str, nome_recebedor: str, cidade: str,
    valor: float, identificador: str = "",
) -> str:
    """Monta o BR Code (copia e cola) com o valor já preenchido."""
    chave_normalizada = normalizar_chave(chave, tipo_chave)
    if not chave_normalizada:
        raise PixNaoConfiguradoError("Nenhuma chave Pix configurada.")
    nome = _normalizar_texto(nome_recebedor, 25)
    cidade_norm = _normalizar_texto(cidade, 15)
    txid = re.sub(r"[^A-Za-z0-9]", "", identificador)[:25] or "***"

    merchant_account = _campo("00", "BR.GOV.BCB.PIX") + _campo("01", chave_normalizada)
    valor_txt = f"{valor:.2f}"

    payload_sem_crc = (
        _campo("00", "01")
        + _campo("26", merchant_account)
        + _campo("52", "0000")
        + _campo("53", "986")
        + _campo("54", valor_txt)
        + _campo("58", "BR")
        + _campo("59", nome)
        + _campo("60", cidade_norm)
        + _campo("62", _campo("05", txid))
        + "6304"
    )
    return payload_sem_crc + _crc16(payload_sem_crc)


def gerar_qrcode_bytes(payload: str) -> bytes:
    """Retorna os bytes PNG do QR Code para o payload Pix informado."""
    import io
    try:
        import qrcode
    except ImportError as e:
        raise PixNaoConfiguradoError(
            "Biblioteca 'qrcode' não instalada. Rode: pip install qrcode"
        ) from e
    img = qrcode.make(payload, box_size=8, border=2)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
