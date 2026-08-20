"""
utils/mascaras.py
Pontuação automática (máscara) durante a digitação em campos CTkEntry.
Não substitui a validação real (utils/validators.py) — apenas formata
visualmente o que a pessoa está digitando, usando somente os dígitos.
"""
from __future__ import annotations

import customtkinter as ctk


def _somente_digitos(valor: str) -> str:
    return "".join(ch for ch in valor if ch.isdigit())


def _formatar_cpf(digitos: str) -> str:
    digitos = digitos[:11]
    partes = []
    if len(digitos) > 9:
        return f"{digitos[0:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    if len(digitos) > 6:
        return f"{digitos[0:3]}.{digitos[3:6]}.{digitos[6:]}"
    if len(digitos) > 3:
        return f"{digitos[0:3]}.{digitos[3:]}"
    return digitos


def _formatar_cnpj(digitos: str) -> str:
    digitos = digitos[:14]
    if len(digitos) > 12:
        return f"{digitos[0:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
    if len(digitos) > 8:
        return f"{digitos[0:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:]}"
    if len(digitos) > 5:
        return f"{digitos[0:2]}.{digitos[2:5]}.{digitos[5:]}"
    if len(digitos) > 2:
        return f"{digitos[0:2]}.{digitos[2:]}"
    return digitos


def _formatar_data(digitos: str) -> str:
    digitos = digitos[:8]
    if len(digitos) > 4:
        return f"{digitos[0:2]}/{digitos[2:4]}/{digitos[4:]}"
    if len(digitos) > 2:
        return f"{digitos[0:2]}/{digitos[2:]}"
    return digitos


def _aplicar_mascara(entry: ctk.CTkEntry, formatador) -> None:
    """Liga a máscara a um CTkEntry: a cada tecla, reformata o conteúdo
    mantendo o cursor no fim (suficiente para os campos curtos usados aqui:
    CPF, CNPJ e data de nascimento)."""

    def _on_key(_event=None) -> None:
        bruto = _somente_digitos(entry.get())
        formatado = formatador(bruto)
        if formatado != entry.get():
            entry.delete(0, "end")
            entry.insert(0, formatado)

    entry.bind("<KeyRelease>", _on_key)


def aplicar_mascara_cpf(entry: ctk.CTkEntry) -> None:
    _aplicar_mascara(entry, _formatar_cpf)


def aplicar_mascara_cnpj(entry: ctk.CTkEntry) -> None:
    _aplicar_mascara(entry, _formatar_cnpj)


def aplicar_mascara_data(entry: ctk.CTkEntry) -> None:
    _aplicar_mascara(entry, _formatar_data)
