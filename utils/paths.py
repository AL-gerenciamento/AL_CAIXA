"""
utils/paths.py
Ponto único de verdade para "onde fica a pasta de instalação persistente".

Por que isso existe: com PyInstaller em modo --onefile (usado nos
instaladores Windows/Linux, ver packaging/), o programa se extrai
sozinho para uma pasta TEMPORÁRIA a cada execução (sys._MEIPASS) e essa
pasta é apagada ao fechar. Se database.db, .env, reports/, exports/ e
comprovantes/ fossem gravados ali, tudo se perderia a cada reinício.

Além disso, quando instalado em "Program Files", o programa não tem
permissão de escrita ali sem rodar como administrador. Por isso, em
modo instalado (frozen), os dados persistentes ficam em uma pasta com
o nome do app dentro de Documentos do usuário
(ex.: C:\\Users\\<usuario>\\Documents\\AL Caixa).
Em modo dev (rodando o .py direto), continua usando a raiz do projeto.
"""
from __future__ import annotations

import os
import shutil
import sys


def pasta_base() -> str:
    """Pasta persistente da instalação."""
    if getattr(sys, "frozen", False):
        nome_app = os.path.splitext(os.path.basename(sys.executable))[0]
        pasta = os.path.join(os.path.expanduser("~"), "Documents", nome_app)
        os.makedirs(pasta, exist_ok=True)
        _garantir_env(pasta)
        return pasta
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _garantir_env(pasta_destino: str) -> None:
    """Copia o .env empacotado para a pasta persistente na primeira execução;
    em execuções seguintes, só acrescenta chaves novas que ainda não existem
    no .env já instalado (preserva valores já customizados pelo usuário),
    já que o app se extrai em uma pasta temporária a cada vez."""
    destino = os.path.join(pasta_destino, ".env")
    origem = os.path.join(getattr(sys, "_MEIPASS", ""), ".env")
    if not os.path.exists(origem):
        return
    if not os.path.exists(destino):
        shutil.copyfile(origem, destino)
        return

    with open(origem, "r", encoding="utf-8") as f:
        linhas_origem = f.readlines()
    with open(destino, "r", encoding="utf-8") as f:
        conteudo_destino = f.read()
    chaves_existentes = {
        linha.split("=", 1)[0].strip()
        for linha in conteudo_destino.splitlines()
        if linha.strip() and not linha.strip().startswith("#") and "=" in linha
    }

    novas = [
        linha for linha in linhas_origem
        if "=" in linha and linha.split("=", 1)[0].strip() not in chaves_existentes
        and not linha.strip().startswith("#")
    ]
    if novas:
        with open(destino, "a", encoding="utf-8") as f:
            if not conteudo_destino.endswith("\n"):
                f.write("\n")
            f.writelines(novas)
