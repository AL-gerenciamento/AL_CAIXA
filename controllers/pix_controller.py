"""
controllers/pix_controller.py
Geração do código Pix "copia e cola" (padrão EMV/BR Code do Banco Central)
a partir da chave Pix cadastrada pelo usuário, e do respectivo QR Code,
já com o valor da venda embutido.
"""
from __future__ import annotations

from controllers.config_controller import ConfigController
from utils.pix_payload import (
    TIPOS_CHAVE, PixNaoConfiguradoError, normalizar_chave, gerar_payload, gerar_qrcode_bytes,
)

_CHAVES_CONFIG = ("pix_chave", "pix_nome_recebedor", "pix_cidade")


class PixController:
    """Monta o payload Pix estático/dinâmico e gera o QR Code correspondente."""

    @staticmethod
    def configurado() -> bool:
        return bool(ConfigController.obter("pix_chave").strip())

    @staticmethod
    def obter_configuracao() -> dict:
        return {
            "chave": ConfigController.obter("pix_chave"),
            "tipo_chave": ConfigController.obter("pix_tipo_chave") or TIPOS_CHAVE[0],
            "nome_recebedor": ConfigController.obter("pix_nome_recebedor"),
            "cidade": ConfigController.obter("pix_cidade"),
        }

    @staticmethod
    def salvar_configuracao(chave: str, tipo_chave: str, nome_recebedor: str, cidade: str) -> None:
        chave = (chave or "").strip()
        if not chave:
            raise ValueError("Informe a chave Pix.")
        if tipo_chave not in TIPOS_CHAVE:
            tipo_chave = TIPOS_CHAVE[0]
        ConfigController.definir("pix_chave", chave)
        ConfigController.definir("pix_tipo_chave", tipo_chave)
        ConfigController.definir("pix_nome_recebedor", (nome_recebedor or "").strip())
        ConfigController.definir("pix_cidade", (cidade or "").strip())

    @staticmethod
    def gerar_payload(valor: float, identificador: str = "") -> str:
        """Monta o BR Code (copia e cola) com o valor já preenchido."""
        config = PixController.obter_configuracao()
        return gerar_payload(
            config["chave"], config["tipo_chave"], config["nome_recebedor"], config["cidade"],
            valor, identificador,
        )

    @staticmethod
    def gerar_qrcode_bytes(valor: float, identificador: str = "") -> bytes:
        """Retorna os bytes PNG do QR Code do Pix com o valor informado."""
        payload = PixController.gerar_payload(valor, identificador)
        return gerar_qrcode_bytes(payload)

    @staticmethod
    def gerar_qrcode_de_texto(conteudo: str) -> bytes:
        """
        Gera um QR Code a partir de qualquer conteúdo informado (link de
        pagamento, código Pix de outra chave/conta, código "copia e cola" de
        outro app, etc.) — não depende da chave Pix cadastrada na empresa.
        """
        conteudo = (conteudo or "").strip()
        if not conteudo:
            raise ValueError("Informe o código ou link a ser transformado em QR Code.")
        return gerar_qrcode_bytes(conteudo)
