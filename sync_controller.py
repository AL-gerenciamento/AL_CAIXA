"""
controllers/sync_controller.py
Sincronização entre o banco LOCAL (sempre presente, usado offline) e o
banco da NUVEM (Supabase/Postgres, opcional).

Regra combinada com o usuário:
- Todo registro novo de um lado é copiado para o outro (nada se perde).
- Se um registro existe nos dois lados e só um lado mudou desde a última
  sincronização, a versão mais nova é aplicada automaticamente no outro
  lado (não é conflito real).
- Se um registro existe nos dois lados e AMBOS mudaram desde a última
  sincronização (conflito de verdade), nada é sobrescrito sozinho: o
  registro entra na lista de conflitos, e quem estiver sincronizando por
  último vê as duas versões na tela e escolhe qual delas vale.
- Nada é apagado de fato durante o sync (soft-delete via campo `deletado`),
  então uma exclusão de um lado nunca "resurge" o registro do outro lado.

Rodar a cada 10 minutos (thread/agendador no app.py) e também ao fechar
o programa.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from database import get_session, get_session_cloud, nuvem_disponivel
from models import (
    Usuario, Categoria, Receita, Despesa, DespesaFixa, Meta, Pagamento, Aviso,
    Configuracao,
)

# Tabelas que participam da sincronização (todas usam SyncMixin: uuid,
# atualizado_em, deletado).
TABELAS_SINCRONIZAVEIS = [Usuario, Categoria, Receita, Despesa, DespesaFixa, Meta, Pagamento, Aviso]

# Colunas que nunca são comparadas/copiadas (são específicas de cada banco
# ou geridas à parte).
_COLUNAS_IGNORADAS = {"id"}

_CHAVE_CONFIG_ULTIMA_SYNC = "ultima_sincronizacao"


def _colunas_modelo(modelo) -> list[str]:
    return [c.name for c in modelo.__table__.columns if c.name not in _COLUNAS_IGNORADAS]


def _linha_para_dict(obj, colunas: list[str]) -> dict[str, Any]:
    return {c: getattr(obj, c) for c in colunas}


def _obter_ultima_sincronizacao(sessao) -> datetime:
    cfg = sessao.query(Configuracao).filter_by(chave=_CHAVE_CONFIG_ULTIMA_SYNC).first()
    if cfg and cfg.valor:
        try:
            return datetime.fromisoformat(cfg.valor)
        except ValueError:
            pass
    return datetime.min


def _gravar_ultima_sincronizacao(sessao, momento: datetime) -> None:
    cfg = sessao.query(Configuracao).filter_by(chave=_CHAVE_CONFIG_ULTIMA_SYNC).first()
    if cfg is None:
        cfg = Configuracao(chave=_CHAVE_CONFIG_ULTIMA_SYNC, valor=momento.isoformat())
        sessao.add(cfg)
    else:
        cfg.valor = momento.isoformat()


def sincronizar() -> dict:
    """
    Executa um ciclo completo de sincronização entre local e nuvem.

    Retorna:
        {
          "sincronizado": bool,       # False se a nuvem não estava disponível
          "aplicados": int,           # nº de registros copiados/atualizados automaticamente
          "conflitos": [              # conflitos reais, precisam de decisão manual
              {
                "tabela": "Despesa",
                "uuid": "...",
                "local": {...},
                "nuvem": {...},
              }, ...
          ],
        }
    """
    if not nuvem_disponivel():
        return {"sincronizado": False, "aplicados": 0, "conflitos": []}

    sessao_local = get_session()
    sessao_nuvem = get_session_cloud()
    aplicados = 0
    conflitos: list[dict] = []
    agora = datetime.now()

    try:
        ultima_sync = _obter_ultima_sincronizacao(sessao_local)

        for modelo in TABELAS_SINCRONIZAVEIS:
            colunas = _colunas_modelo(modelo)
            locais = {r.uuid: r for r in sessao_local.query(modelo).all()}
            nuvens = {r.uuid: r for r in sessao_nuvem.query(modelo).all()}

            todos_uuids = set(locais.keys()) | set(nuvens.keys())

            for u in todos_uuids:
                reg_local = locais.get(u)
                reg_nuvem = nuvens.get(u)

                # --- Só existe em um dos lados: copia para o outro ---
                if reg_local is None:
                    dados = _linha_para_dict(reg_nuvem, colunas)
                    sessao_local.add(modelo(**dados))
                    aplicados += 1
                    continue
                if reg_nuvem is None:
                    dados = _linha_para_dict(reg_local, colunas)
                    sessao_nuvem.add(modelo(**dados))
                    aplicados += 1
                    continue

                # --- Existe nos dois lados: compara conteúdo ---
                d_local = _linha_para_dict(reg_local, colunas)
                d_nuvem = _linha_para_dict(reg_nuvem, colunas)
                if d_local == d_nuvem:
                    continue  # já iguais, nada a fazer

                mudou_local = reg_local.atualizado_em > ultima_sync
                mudou_nuvem = reg_nuvem.atualizado_em > ultima_sync

                if mudou_local and mudou_nuvem:
                    # Conflito real: os dois lados mudaram desde a última sync.
                    conflitos.append({
                        "tabela": modelo.__name__,
                        "uuid": u,
                        "local": d_local,
                        "nuvem": d_nuvem,
                    })
                elif mudou_local:
                    # Só o local mudou -> aplica na nuvem
                    for c in colunas:
                        if c != "uuid":
                            setattr(reg_nuvem, c, d_local[c])
                    aplicados += 1
                else:
                    # Só a nuvem mudou (ou nenhum, por segurança aplica nuvem) -> aplica no local
                    for c in colunas:
                        if c != "uuid":
                            setattr(reg_local, c, d_nuvem[c])
                    aplicados += 1

        _gravar_ultima_sincronizacao(sessao_local, agora)
        sessao_local.commit()
        sessao_nuvem.commit()
    except Exception:
        sessao_local.rollback()
        sessao_nuvem.rollback()
        raise
    finally:
        sessao_local.close()
        sessao_nuvem.close()

    return {"sincronizado": True, "aplicados": aplicados, "conflitos": conflitos}


def resolver_conflito(tabela: str, uuid_registro: str, escolha: str) -> None:
    """
    Aplica a decisão do usuário para um conflito específico.

    escolha: "local" para manter a versão local (copiada para a nuvem),
             "nuvem" para manter a versão da nuvem (copiada para o local).
    A versão vencedora é gravada nos dois bancos com um novo atualizado_em,
    para não gerar o mesmo conflito de novo no próximo ciclo.
    """
    modelo = next((m for m in TABELAS_SINCRONIZAVEIS if m.__name__ == tabela), None)
    if modelo is None:
        raise ValueError(f"Tabela sincronizável desconhecida: {tabela}")

    colunas = _colunas_modelo(modelo)
    sessao_local = get_session()
    sessao_nuvem = get_session_cloud()
    if sessao_nuvem is None:
        sessao_local.close()
        raise RuntimeError("Nuvem indisponível no momento; tente novamente depois.")

    try:
        reg_local = sessao_local.query(modelo).filter_by(uuid=uuid_registro).first()
        reg_nuvem = sessao_nuvem.query(modelo).filter_by(uuid=uuid_registro).first()
        if reg_local is None or reg_nuvem is None:
            raise ValueError("Registro em conflito não encontrado em um dos bancos.")

        origem = reg_local if escolha == "local" else reg_nuvem
        vencedor = _linha_para_dict(origem, colunas)
        vencedor["atualizado_em"] = datetime.now()

        for c in colunas:
            if c == "uuid":
                continue
            setattr(reg_local, c, vencedor[c])
            setattr(reg_nuvem, c, vencedor[c])

        sessao_local.commit()
        sessao_nuvem.commit()
    except Exception:
        sessao_local.rollback()
        sessao_nuvem.rollback()
        raise
    finally:
        sessao_local.close()
        sessao_nuvem.close()
