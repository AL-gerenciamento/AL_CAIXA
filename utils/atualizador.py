"""
utils/atualizador.py
Sistema de atualização automática via Google Drive — compartilhado pelo
app da loja (ORVYN.exe) e pelo Painel Super Admin (ORVYN-Master.exe).
Cada um tem seu PRÓPRIO manifest.json/versão no Drive (pastas de
instalação diferentes, version.txt independente em cada uma).

Funcionamento (ver ATUALIZACOES.txt na raiz do projeto para o passo a
passo completo de como publicar uma nova versão):

1. Um arquivo `manifest.json` público no Google Drive descreve a versão
   mais recente disponível (versao, url do .zip da atualização, sha256
   do .zip e notas). Esse .json é o único arquivo que o app baixa
   automaticamente e sem confirmação — é pequeno e não executa nada.
2. O app local compara a versão do manifesto com `version.txt` (gravado
   ao lado do executável). Se for maior, avisa o usuário (ou, se
   disparado pelo Super Admin, todos os clientes na próxima checagem).
3. Só ao confirmar a atualização o .zip é baixado, o SHA-256 é
   conferido (garante que o arquivo não foi corrompido/adulterado no
   caminho) e extraído para uma pasta temporária.
4. Um pequeno script "aplicador" (gerado na hora, batch no Windows e
   shell no macOS/Linux) espera o programa principal fechar, copia os
   arquivos novos por cima da instalação (preservando database.db, .env
   e as pastas de dados do usuário) e reabre o app na nova versão.

Este módulo NUNCA sobrescreve: database.db, .env, reports/, exports/,
comprovantes/, assets/images (logos enviados pela empresa).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from utils.paths import pasta_base

VERSAO_ARQUIVO = os.path.join(pasta_base(), "version.txt")

# Pasta real da instalação (onde o executável/app vive de fato), diferente
# de _MEIPASS quando empacotado com PyInstaller --onefile.
PASTA_INSTALACAO = pasta_base()

# Pastas/arquivos que a atualização NUNCA sobrescreve nem apaga.
PROTEGIDOS = {
    "database.db", ".env", "reports", "exports", "comprovantes",
    "assets/images", "version.txt",
}

MANIFEST_URL_PADRAO = "https://drive.google.com/uc?export=download&id=SEU_ID_DO_MANIFEST_AQUI"

MANIFEST_URL = os.getenv("ORVYN_UPDATE_MANIFEST_URL", MANIFEST_URL_PADRAO)


def versao_atual() -> str:
    try:
        with open(VERSAO_ARQUIVO, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "0.0.0"


def _versao_tupla(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.strip().split("."))


def _google_drive_url_direta(url: str) -> str:
    """Converte um link de compartilhamento comum do Drive em link de download direto."""
    if "drive.google.com/file/d/" in url:
        file_id = url.split("/file/d/")[1].split("/")[0]
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return url


def verificar_atualizacao(manifest_url_env: str = "ORVYN_UPDATE_MANIFEST_URL") -> dict | None:
    """
    Consulta o manifest.json no Drive. Retorna None se já está na versão
    mais recente, se o manifesto está inacessível, ou em caso de erro
    (nunca lança exceção — checagem de atualização não pode derrubar o app).

    `manifest_url_env`: nome da variável de ambiente (.env) que traz o
    link do manifest.json. Use "ORVYN_UPDATE_MANIFEST_URL" para o app da
    loja e "ORVYN_MASTER_UPDATE_MANIFEST_URL" para o Painel Super Admin —
    cada app tem sua própria versão/publicação no Drive.
    """
    try:
        url_bruta = os.getenv(manifest_url_env, MANIFEST_URL_PADRAO)
        url = _google_drive_url_direta(url_bruta)
        with urllib.request.urlopen(url, timeout=8) as resp:
            manifesto = json.loads(resp.read().decode("utf-8"))

        remota = manifesto.get("versao", "0.0.0")
        if _versao_tupla(remota) > _versao_tupla(versao_atual()):
            manifesto["url_download"] = _google_drive_url_direta(manifesto["url_download"])
            return manifesto
        return None
    except Exception:
        return None


def _sha256_arquivo(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar_atualizacao(manifesto: dict, progresso=None) -> str:
    """Baixa o .zip da atualização, confere o SHA-256 e devolve o caminho local."""
    destino = os.path.join(tempfile.gettempdir(), f"orvyn_update_{manifesto['versao']}.zip")

    with urllib.request.urlopen(manifesto["url_download"], timeout=30) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        baixado = 0
        with open(destino, "wb") as f:
            while True:
                bloco = resp.read(1 << 16)
                if not bloco:
                    break
                f.write(bloco)
                baixado += len(bloco)
                if progresso and total:
                    progresso(baixado / total)

    sha_esperado = manifesto.get("sha256", "")
    if sha_esperado and _sha256_arquivo(destino) != sha_esperado.lower():
        os.remove(destino)
        raise ValueError("Arquivo de atualização corrompido (SHA-256 não confere). Baixe novamente.")

    return destino


def _gerar_script_aplicador(zip_path: str, pasta_destino: str, pid_atual: int, nome_executavel_win: str) -> str:
    """
    Gera um script que: espera o processo atual encerrar, extrai o zip por
    cima da instalação (pulando PROTEGIDOS) e reabre o app.

    `nome_executavel_win`: nome do .exe a reabrir no Windows (ex.:
    "ORVYN.exe" para o app da loja, "ORVYN-Master.exe" para o Painel
    Super Admin). No Linux/macOS o binário é sempre "ORVYN" (não há
    versão Master separada nesses SOs por enquanto).
    """
    tag = os.path.splitext(nome_executavel_win)[0].lower().replace("-", "_")
    pasta_temp_extracao = os.path.join(tempfile.gettempdir(), f"orvyn_update_extraido_{tag}")
    if os.path.exists(pasta_temp_extracao):
        shutil.rmtree(pasta_temp_extracao, ignore_errors=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(pasta_temp_extracao)

    if sys.platform == "win32":
        script_path = os.path.join(tempfile.gettempdir(), f"orvyn_apply_update_{tag}.bat")
        executavel = os.path.join(pasta_destino, nome_executavel_win)
        protegidos_robocopy = " ".join(f'/XF "{p}" /XD "{p}"' for p in PROTEGIDOS)
        conteudo = f"""@echo off
:esperar
tasklist /FI "PID eq {pid_atual}" | find "{pid_atual}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto esperar
)
robocopy "{pasta_temp_extracao}" "{pasta_destino}" /E /XF database.db .env version.txt /XD reports exports comprovantes images
start "" "{executavel}"
rmdir /s /q "{pasta_temp_extracao}"
del "%~f0"
"""
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(conteudo)
        return script_path

    script_path = os.path.join(tempfile.gettempdir(), f"orvyn_apply_update_{tag}.sh")
    executavel = os.path.join(pasta_destino, "ORVYN")
    excecoes = " ".join(f"! -name '{p}' ! -path '*/{p}/*'" for p in PROTEGIDOS)
    conteudo = f"""#!/bin/bash
while kill -0 {pid_atual} 2>/dev/null; do sleep 1; done
rsync -a --exclude='database.db' --exclude='.env' --exclude='version.txt' \\
  --exclude='reports/' --exclude='exports/' --exclude='comprovantes/' --exclude='assets/images/' \\
  "{pasta_temp_extracao}/" "{pasta_destino}/"
chmod +x "{executavel}" 2>/dev/null
nohup "{executavel}" >/dev/null 2>&1 &
rm -rf "{pasta_temp_extracao}"
rm -- "$0"
"""
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(conteudo)
    os.chmod(script_path, 0o755)
    return script_path


def aplicar_atualizacao_e_reiniciar(manifesto: dict, zip_path: str, nome_executavel_win: str = "ORVYN.exe") -> None:
    """
    Prepara o script aplicador, dispara em processo separado e encerra o
    app atual. A troca de arquivos só acontece DEPOIS que este processo
    já não estiver mais rodando (evita arquivo em uso / travamento).

    `nome_executavel_win`: passe "ORVYN-Master.exe" ao chamar a partir do
    Painel Super Admin.
    """
    pid = os.getpid()
    script = _gerar_script_aplicador(zip_path, PASTA_INSTALACAO, pid, nome_executavel_win)

    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", script], creationflags=subprocess.DETACHED_PROCESS)
    else:
        subprocess.Popen(["/bin/bash", script], start_new_session=True)

    sys.exit(0)
