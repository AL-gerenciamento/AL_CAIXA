"""
controllers/backup_controller.py
Backup e restauração do banco de dados SQLite, além de backup automático
disparado periodicamente pela aplicação.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime

from database import DB_PATH
from utils.logger import registrar_erro, registrar_alteracao

from utils.paths import pasta_base
BASE_DIR = pasta_base()
BACKUP_DIR = os.path.join(BASE_DIR, "reports", "backups")


class BackupController:
    """Cria e restaura backups do arquivo database.db."""

    @staticmethod
    def criar_backup(pasta_destino: str | None = None, usuario: str = "sistema") -> str:
        """Copia o arquivo do banco de dados para a pasta de backups com timestamp."""
        try:
            destino = pasta_destino or BACKUP_DIR
            os.makedirs(destino, exist_ok=True)
            nome_arquivo = f"backup_{datetime.now():%Y%m%d_%H%M%S}.db"
            caminho_destino = os.path.join(destino, nome_arquivo)
            shutil.copy2(DB_PATH, caminho_destino)
            registrar_alteracao(usuario, f"Backup criado: {nome_arquivo}")
            return caminho_destino
        except Exception as e:
            registrar_erro(e, "criar_backup")
            raise

    @staticmethod
    def restaurar_backup(caminho_backup: str, usuario: str = "sistema") -> None:
        """Restaura o banco de dados a partir de um arquivo de backup."""
        try:
            if not os.path.isfile(caminho_backup):
                raise FileNotFoundError("Arquivo de backup não encontrado.")
            # Faz um backup de segurança do estado atual antes de sobrescrever
            shutil.copy2(DB_PATH, DB_PATH + ".antes_restauracao")
            shutil.copy2(caminho_backup, DB_PATH)
            registrar_alteracao(usuario, f"Backup restaurado a partir de: {caminho_backup}")
        except Exception as e:
            registrar_erro(e, "restaurar_backup")
            raise

    @staticmethod
    def listar_backups() -> list[str]:
        """Lista os arquivos de backup disponíveis na pasta padrão."""
        os.makedirs(BACKUP_DIR, exist_ok=True)
        arquivos = [
            os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR) if f.endswith(".db")
        ]
        return sorted(arquivos, reverse=True)
