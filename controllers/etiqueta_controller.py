"""
controllers/etiqueta_controller.py
Gera etiquetas de produto (nome + código de barras + preço) em PDF,
prontas para impressora térmica de etiquetas (80mm x 50mm).
"""
import os
import re
import unicodedata

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.graphics.barcode import code128

from controllers.config_controller import ConfigController
from utils.validators import ValidationError
from utils.logger import registrar_erro
from utils.impressora import tamanho_papel_mm

LARGURA_ETIQUETA_PADRAO_MM = 80
ALTURA_ETIQUETA_PADRAO_MM = 50


def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-zA-Z0-9]+", "_", texto).strip("_")
    return texto.lower() or "produto"


def _tamanho_que_cabe(c, texto: str, fonte: str, tamanho: float, largura_disponivel: float, minimo: float = 5) -> float:
    """Reduz o tamanho da fonte até o texto caber em `largura_disponivel`,
    sem descer abaixo de `minimo`."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    while tamanho > minimo and stringWidth(texto, fonte, tamanho) > largura_disponivel:
        tamanho -= 0.5
    return tamanho


class EtiquetaController:

    @staticmethod
    def _tamanho_etiqueta_mm() -> tuple[float, float]:
        """
        Tamanho da etiqueta em mm, nesta ordem de prioridade:
        1) largura/altura configuradas manualmente em Configurações
           (a detecção automática pelo driver da impressora nem sempre
           bate com o tamanho físico real da etiqueta/rolo, cortando o
           conteúdo);
        2) tamanho detectado da impressora padrão;
        3) 80x50mm.
        """
        largura_config = (ConfigController.obter("etiqueta_largura_mm") or "").strip()
        altura_config = (ConfigController.obter("etiqueta_altura_mm") or "").strip()
        if largura_config and altura_config:
            try:
                return float(largura_config), float(altura_config)
            except ValueError:
                pass

        impressora = (ConfigController.obter("impressora_etiqueta") or "").strip() or None
        largura_mm, altura_mm = tamanho_papel_mm(
            LARGURA_ETIQUETA_PADRAO_MM, ALTURA_ETIQUETA_PADRAO_MM, impressora
        )
        return largura_mm, (altura_mm or ALTURA_ETIQUETA_PADRAO_MM)

    @staticmethod
    def gerar_pdf(produto, pasta: str | None = None, copias: int = 1) -> str:
        """Gera um PDF com uma etiqueta por cópia (nome, código de barras e preço)."""
        try:
            if copias < 1:
                raise ValidationError("Informe ao menos 1 cópia.")

            pasta = pasta or ConfigController.obter("pasta_exportacao")
            os.makedirs(pasta, exist_ok=True)
            caminho = os.path.join(pasta, f"etiqueta_{_slug(produto.nome)}_{produto.id}.pdf")

            codigo = (produto.codigo_barras or produto.codigo_sku or str(produto.id)).strip()
            moeda = ConfigController.obter("moeda")

            largura_mm, altura_mm = EtiquetaController._tamanho_etiqueta_mm()
            largura = largura_mm * mm
            altura = altura_mm * mm
            # Escala o layout (originalmente desenhado para 50mm de altura)
            # proporcionalmente à altura real configurada/detectada, para
            # não cortar o código de barras/preço em etiquetas menores.
            escala = max(0.4, min(2.0, altura_mm / ALTURA_ETIQUETA_PADRAO_MM))

            c = canvas.Canvas(caminho, pagesize=(largura, altura))
            margem_texto = 4 * mm
            largura_texto_disponivel = max(largura - margem_texto, 10 * mm)
            for _ in range(copias):
                nome = produto.nome if len(produto.nome) <= 30 else produto.nome[:27] + "..."
                tam_nome = _tamanho_que_cabe(
                    c, nome, "Helvetica-Bold", max(6, round(11 * escala)), largura_texto_disponivel
                )
                c.setFont("Helvetica-Bold", tam_nome)
                c.drawCentredString(largura / 2, altura - 9 * mm * escala, nome)

                margem_barra = 4 * mm
                largura_disponivel = max(largura - margem_barra, 10 * mm)
                bar_width = 0.32 * mm
                barra = code128.Code128(
                    codigo, barHeight=13 * mm * escala, barWidth=bar_width, humanReadable=False
                )
                if barra.width > largura_disponivel:
                    # A largura de barra padrão (0.32mm/módulo) não cabe
                    # nessa etiqueta com esse código; reduz até caber,
                    # respeitando um mínimo legível pelo leitor. A redução
                    # não é perfeitamente linear (há uma quiet zone fixa),
                    # então itera algumas vezes até convergir.
                    for _ in range(6):
                        if barra.width <= largura_disponivel or bar_width <= 0.15 * mm:
                            break
                        bar_width = max(0.15 * mm, bar_width * (largura_disponivel / barra.width))
                        barra = code128.Code128(
                            codigo, barHeight=13 * mm * escala, barWidth=bar_width, humanReadable=False
                        )
                x = (largura - barra.width) / 2
                barra.drawOn(c, x, 17 * mm * escala)

                tam_codigo = _tamanho_que_cabe(
                    c, codigo, "Helvetica", max(5, round(8 * escala)), largura_texto_disponivel
                )
                c.setFont("Helvetica", tam_codigo)
                c.drawCentredString(largura / 2, 13 * mm * escala, codigo)

                preco_unidade = f"/{produto.unidade_medida}" if produto.unidade_medida != "un" else ""
                texto_preco = f"{moeda} {produto.preco_venda:,.2f}{preco_unidade}"
                tam_preco = _tamanho_que_cabe(
                    c, texto_preco, "Helvetica-Bold", max(8, round(16 * escala)), largura_texto_disponivel
                )
                c.setFont("Helvetica-Bold", tam_preco)
                c.drawCentredString(largura / 2, 5 * mm * escala, texto_preco)
                c.showPage()
            c.save()
            return caminho
        except ValidationError:
            raise
        except Exception as e:
            registrar_erro(e, "gerar_etiqueta_pdf")
            raise
