"""
utils/feriados.py
Feriados nacionais brasileiros e cálculo de dias úteis.
"""
from __future__ import annotations
from datetime import date, timedelta


def _pascoa(ano: int) -> date:
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano: int) -> set[date]:
    pascoa = _pascoa(ano)
    carnaval_seg = pascoa - timedelta(days=48)
    carnaval_ter = pascoa - timedelta(days=47)
    sexta_santa = pascoa - timedelta(days=2)
    corpus_christi = pascoa + timedelta(days=60)
    return {
        date(ano, 1, 1),
        carnaval_seg,
        carnaval_ter,
        sexta_santa,
        pascoa,
        corpus_christi,
        date(ano, 4, 21),
        date(ano, 5, 1),
        date(ano, 9, 7),
        date(ano, 10, 12),
        date(ano, 11, 2),
        date(ano, 11, 15),
        date(ano, 11, 20),
        date(ano, 12, 25),
    }


def eh_dia_util(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    if d in feriados_nacionais(d.year):
        return False
    return True


def proximo_dia_util(d: date) -> date:
    while not eh_dia_util(d):
        d += timedelta(days=1)
    return d


def adicionar_dias_uteis(d: date, quantidade: int) -> date:
    contados = 0
    atual = d
    while contados < quantidade:
        atual += timedelta(days=1)
        if eh_dia_util(atual):
            contados += 1
    return atual
