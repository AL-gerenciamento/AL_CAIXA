"""
utils/impressora.py
Detecta o tamanho de papel configurado na impressora padrão do sistema,
para que etiquetas e recibos sejam gerados no tamanho da impressora
realmente em uso, em vez de um tamanho fixo hardcoded no código.

Também imprime PDFs diretamente via GDI (win32ui + PyMuPDF), sem depender
de haver um leitor de PDF associado ao sistema operacional para o verbo
"print" do Windows (é isso que causa o aviso "Não há um leitor de PDF
associado para impressão automática").
"""
from __future__ import annotations

import os


def tamanho_papel_mm(
    largura_padrao_mm: float,
    altura_padrao_mm: float | None = None,
    nome_impressora: str | None = None,
) -> tuple[float, float | None]:
    """
    Retorna (largura_mm, altura_mm) do papel configurado na impressora
    informada em `nome_impressora` (ou na impressora padrão do Windows,
    se omitido).

    `altura_mm` pode vir None quando a impressora é uma bobina contínua
    (recibo térmico) e o driver não informa um comprimento fixo; nesse
    caso quem chamar deve calcular a altura de acordo com o conteúdo.

    Fora do Windows, sem o pywin32 instalado, sem impressora configurada,
    ou se o driver não informar o tamanho do papel, devolve os valores
    padrão recebidos sem lançar erro (fallback silencioso).
    """
    try:
        import win32print

        nome = nome_impressora or win32print.GetDefaultPrinter()
        hprinter = win32print.OpenPrinter(nome)
        try:
            info = win32print.GetPrinter(hprinter, 2)
            devmode = info.get("pDevMode")
            largura_decimo = getattr(devmode, "PaperWidth", 0) if devmode else 0
            altura_decimo = getattr(devmode, "PaperLength", 0) if devmode else 0
            if largura_decimo:
                largura = largura_decimo / 10  # DEVMODE guarda em décimos de mm
                altura = (altura_decimo / 10) if altura_decimo else altura_padrao_mm
                return largura, altura
        finally:
            win32print.ClosePrinter(hprinter)
    except Exception:
        pass
    return largura_padrao_mm, altura_padrao_mm


def listar_impressoras() -> list[str]:
    """
    Retorna os nomes das impressoras instaladas no Windows.

    Fora do Windows, sem o pywin32 instalado, ou se a enumeração falhar,
    devolve uma lista vazia (fallback silencioso).
    """
    try:
        import win32print

        impressoras = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        return sorted(item[2] for item in impressoras)
    except Exception:
        return []


def imprimir_pdf_direto(caminho: str, nome_impressora: str | None = None) -> bool:
    """
    Imprime o PDF diretamente na impressora via GDI, renderizando cada
    página como imagem e enviando para a impressora padrão (ou a
    informada em `nome_impressora`) — sem precisar de nenhum leitor de
    PDF instalado/associado ao Windows.

    Retorna True se enviou o trabalho de impressão com sucesso. Retorna
    False (sem lançar erro) quando os pré-requisitos não estão disponíveis
    (fora do Windows, pywin32 ou PyMuPDF não instalados) ou algo falha no
    caminho, para quem chamar cair no fallback antigo (abrir o PDF para
    impressão manual).
    """
    try:
        import fitz  # PyMuPDF
        import win32con
        import win32print
        import win32ui
        from PIL import Image, ImageWin
    except ImportError:
        return False

    documento = None
    dc = None
    try:
        nome_impressora = nome_impressora or win32print.GetDefaultPrinter()
        dc = win32ui.CreateDC()
        dc.CreatePrinterDC(nome_impressora)

        dpi_x = dc.GetDeviceCaps(win32con.LOGPIXELSX)
        dpi_y = dc.GetDeviceCaps(win32con.LOGPIXELSY)
        largura_disponivel_px = dc.GetDeviceCaps(win32con.HORZRES)
        altura_disponivel_px = dc.GetDeviceCaps(win32con.VERTRES)

        documento = fitz.open(caminho)
        dc.StartDoc(os.path.basename(caminho))
        for pagina in documento:
            dc.StartPage()
            zoom_x = dpi_x / 72
            zoom_y = dpi_y / 72
            pixmap = pagina.get_pixmap(matrix=fitz.Matrix(zoom_x, zoom_y))
            imagem = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            dib = ImageWin.Dib(imagem)
            largura_destino = min(pixmap.width, largura_disponivel_px)
            altura_destino = min(pixmap.height, altura_disponivel_px)
            destino = (0, 0, largura_destino, altura_destino)
            dib.draw(dc.GetHandleOutput(), destino)
            dc.EndPage()
        dc.EndDoc()
        return True
    except Exception:
        import traceback

        traceback.print_exc()
        try:
            if dc is not None:
                dc.AbortDoc()
        except Exception:
            pass
        return False
    finally:
        if documento is not None:
            documento.close()
        if dc is not None:
            dc.DeleteDC()
