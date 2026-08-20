"""
utils/device.py
Identificador único e persistente deste computador/instalação (device_id),
usado para marcar a origem de cada registro sincronizável e para os
registros de fila (sync_queue) e log (sync_log) de sincronização.

Gerado uma única vez e gravado em "device_id.txt" na pasta persistente da
instalação (ver utils/paths.py); leituras seguintes reutilizam o mesmo
valor, inclusive entre reinstalações do executável (a pasta persiste em
Documentos do usuário).
"""
from __future__ import annotations

import os
import uuid as uuid_lib

from utils.paths import pasta_base

_ARQUIVO_DEVICE_ID = "device_id.txt"
_device_id_cache: str | None = None


def obter_device_id() -> str:
    """Retorna o device_id desta instalação, gerando e persistindo na
    primeira chamada."""
    global _device_id_cache
    if _device_id_cache:
        return _device_id_cache

    caminho = os.path.join(pasta_base(), _ARQUIVO_DEVICE_ID)
    try:
        if os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                valor = f.read().strip()
            if valor:
                _device_id_cache = valor
                return _device_id_cache
    except OSError:
        pass

    novo = str(uuid_lib.uuid4())
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(novo)
    except OSError:
        pass
    _device_id_cache = novo
    return novo
