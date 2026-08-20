"""
controllers/recibo_controller.py
Geração do recibo de venda (item 16 da especificação): PDF para impressão/
exportação e compartilhamento via WhatsApp. Envio por e-mail foi
propositalmente excluído a pedido do usuário.
"""
from __future__ import annotations

import os
import urllib.parse
import webbrowser

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

from controllers.config_controller import ConfigController
from utils.logger import registrar_erro
from utils.impressora import tamanho_papel_mm

LARGURA_RECIBO_PADRAO_MM = 80  # bobina térmica comum; a impressora, quando detectada, prevalece
MARGEM_TOPO_MM = 12
MARGEM_BASE_MM = 8


def _mascarar_cpf(cpf: str) -> str:
    """Formata o CPF e censura os 3 dígitos centrais: 123.***.**9-00."""
    cpf = "".join(ch for ch in (cpf or "") if ch.isdigit())
    if len(cpf) != 11:
        return cpf
    return f"{cpf[0:3]}.***.**{cpf[8]}-{cpf[9:11]}"


def _eh_juridica(empresa) -> bool:
    tipo = getattr(empresa, "tipo_pessoa", None)
    valor = getattr(tipo, "name", tipo)
    return str(valor) == "JURIDICA"


def _linhas_dados_empresa(empresa) -> list[str]:
    """Monta as linhas com os dados cadastrais da empresa para o recibo."""
    if not empresa:
        return []
    linhas = []
    if _eh_juridica(empresa):
        if empresa.nome_fantasia:
            linhas.append(empresa.nome_fantasia)
        if empresa.razao_social:
            linhas.append(empresa.razao_social)
        if empresa.cnpj:
            cnpj = empresa.cnpj
            linhas.append(f"CNPJ: {cnpj[0:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:14]}")
    else:
        if empresa.nome_completo:
            linhas.append(empresa.nome_completo)
        if empresa.cpf:
            linhas.append(f"CPF: {_mascarar_cpf(empresa.cpf)}")
    return linhas


class ReciboController:

    @staticmethod
    def _pasta_exportacao() -> str:
        pasta = ConfigController.obter("pasta_exportacao")
        os.makedirs(pasta, exist_ok=True)
        return pasta

    @staticmethod
    def gerar_pdf(venda, nome_empresa: str = "", empresa=None) -> str:
        """Gera o PDF do recibo e retorna o caminho do arquivo.

        A largura segue o papel da impressora padrão (ou 80mm, se não
        detectada); a altura é calculada a partir do próprio conteúdo do
        recibo (nº de itens, forma de pagamento etc.), como numa bobina de
        impressora térmica, em vez de um tamanho de página fixo que corta
        recibos longos ou sobra papel em recibos curtos.
        """
        try:
            pasta = ReciboController._pasta_exportacao()
            caminho = os.path.join(pasta, f"recibo_venda_{venda.numero_venda}.pdf")
            moeda = ConfigController.obter("moeda")

            largura_config = (ConfigController.obter("recibo_largura_mm") or "").strip()
            if largura_config:
                try:
                    largura_mm = float(largura_config.replace(",", "."))
                except ValueError:
                    largura_mm = LARGURA_RECIBO_PADRAO_MM
            else:
                impressora = (ConfigController.obter("impressora_recibo") or "").strip() or None
                largura_mm, _ = tamanho_papel_mm(LARGURA_RECIBO_PADRAO_MM, nome_impressora=impressora)
            largura = largura_mm * mm

            # Monta a lista de linhas primeiro (texto, tamanho, negrito, espaço
            # até a próxima linha) para poder somar a altura necessária antes
            # de criar o Canvas.
            linhas: list[tuple[str, int, bool, float]] = []

            def linha(texto, tamanho=9, negrito=False, espaco=5 * mm):
                linhas.append((texto, tamanho, negrito, espaco))

            dados_empresa = _linhas_dados_empresa(empresa)
            if dados_empresa:
                linha(dados_empresa[0], 12, negrito=True)
                for extra in dados_empresa[1:]:
                    linha(extra, 8, espaco=4 * mm)
                linha("", espaco=2 * mm)
            elif nome_empresa:
                linha(nome_empresa, 12, negrito=True, espaco=7 * mm)
            linha(f"Venda nº {venda.numero_venda}", 10, negrito=True)
            linha(f"Data: {venda.data_hora.strftime('%d/%m/%Y %H:%M')}")
            if venda.cliente:
                linha(f"Cliente: {venda.cliente}")
            if len(venda.pagamentos) > 1:
                linha("Pagamento:", negrito=True)
                for p in venda.pagamentos:
                    linha(f"  {p.forma_pagamento}: {moeda} {p.valor:.2f}", 8)
            else:
                linha(f"Forma de pagamento: {venda.forma_pagamento}")
            linha("-" * 40, espaco=6 * mm)

            for item in venda.itens:
                linha(f"{item.quantidade:g}x {item.produto.nome}", 9)
                linha(
                    f"   {moeda} {item.valor_unitario:.2f}  =  {moeda} {item.valor_total:.2f}",
                    8, espaco=6 * mm,
                )

            linha("-" * 40, espaco=6 * mm)

            if venda.desconto_percentual or venda.acrescimo_percentual:
                linha(f"Subtotal: {moeda} {venda.subtotal:.2f}", 9)
                if venda.desconto_percentual:
                    valor_desconto = venda.subtotal * venda.desconto_percentual / 100
                    espaco_desconto = 4 * mm if venda.acrescimo_percentual else 6 * mm
                    linha(f"Desconto ({venda.desconto_percentual:g}%): -{moeda} {valor_desconto:.2f}", 9, espaco=espaco_desconto)
                if venda.acrescimo_percentual:
                    valor_acrescimo = venda.subtotal * venda.acrescimo_percentual / 100
                    linha(f"Acréscimo ({venda.acrescimo_percentual:g}%): +{moeda} {valor_acrescimo:.2f}", 9, espaco=6 * mm)

            linha(f"TOTAL: {moeda} {venda.valor_total:.2f}", 12, negrito=True, espaco=8 * mm)
            linha(f"Código da venda: {venda.uuid[:8]}", 7, espaco=0)

            altura_conteudo = sum(espaco for _, _, _, espaco in linhas)
            altura = MARGEM_TOPO_MM * mm + altura_conteudo + MARGEM_BASE_MM * mm

            c = canvas.Canvas(caminho, pagesize=(largura, altura))
            y = altura - MARGEM_TOPO_MM * mm
            for texto, tamanho, negrito, espaco in linhas:
                c.setFont("Helvetica-Bold" if negrito else "Helvetica", tamanho)
                c.drawString(6 * mm, y, texto)
                y -= espaco

            c.showPage()
            c.save()
            return caminho
        except Exception as e:
            registrar_erro(e, "gerar_pdf_recibo")
            raise

    @staticmethod
    def texto_recibo(venda, nome_empresa: str = "", empresa=None) -> str:
        """Texto simples do recibo, usado no compartilhamento via WhatsApp."""
        moeda = ConfigController.obter("moeda")
        linhas = []
        dados_empresa = _linhas_dados_empresa(empresa)
        if dados_empresa:
            linhas.append(f"*{dados_empresa[0]}*")
            linhas.extend(dados_empresa[1:])
        elif nome_empresa:
            linhas.append(f"*{nome_empresa}*")
        linhas.append(f"Recibo - Venda nº {venda.numero_venda}")
        linhas.append(f"Data: {venda.data_hora.strftime('%d/%m/%Y %H:%M')}")
        if venda.cliente:
            linhas.append(f"Cliente: {venda.cliente}")
        linhas.append("")
        for item in venda.itens:
            linhas.append(
                f"{item.quantidade:g}x {item.produto.nome} - {moeda} {item.valor_total:.2f}"
            )
        linhas.append("")
        linhas.append(f"*Total: {moeda} {venda.valor_total:.2f}*")
        if len(venda.pagamentos) > 1:
            for p in venda.pagamentos:
                linhas.append(f"{p.forma_pagamento}: {moeda} {p.valor:.2f}")
        else:
            linhas.append(f"Forma de pagamento: {venda.forma_pagamento}")
        return "\n".join(linhas)

    @staticmethod
    def enviar_whatsapp(venda, telefone: str, nome_empresa: str = "", empresa=None) -> None:
        """Abre o WhatsApp (Web ou app) com o texto do recibo pronto para envio."""
        telefone_limpo = "".join(ch for ch in telefone if ch.isdigit())
        if not telefone_limpo:
            raise ValueError("Informe um telefone válido para enviar pelo WhatsApp.")
        texto = ReciboController.texto_recibo(venda, nome_empresa, empresa)
        url = f"https://wa.me/{telefone_limpo}?text={urllib.parse.quote(texto)}"
        webbrowser.open(url)
