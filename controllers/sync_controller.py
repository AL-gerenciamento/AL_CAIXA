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
- Colisão de restrição única (mesmo registro de negócio cadastrado nos
  dois lados antes do primeiro sync, ou editado para um valor único já
  usado do outro lado) é resolvida sozinha, sem popup: a nuvem vence, a
  duplicata/alteração do lado local é descartada.
- Nada é apagado de fato durante o sync (soft-delete via campo `deletado`),
  então uma exclusão de um lado nunca "resurge" o registro do outro lado.

Roda em tempo real (logo após cada commit no banco local, ver
sincronizar_em_tempo_real / database.registrar_callback_pos_commit_local),
além de um polling curto de segurança e ao fechar o programa.
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy import UniqueConstraint

from database import get_session, get_session_cloud, nuvem_disponivel, registrar_dispositivo
from models import (
    Empresa, Usuario, Categoria, Receita, Despesa, DespesaFixa, Meta, Pagamento, Aviso,
    Produto, Venda, ItemVenda, VendaPagamento,
    Configuracao, ConfiguracaoPlataforma,
    SyncQueue, SyncLog,
)
from utils.device import obter_device_id

# Tabelas que participam da sincronização (todas usam SyncMixin: uuid,
# atualizado_em, deletado). Empresa vem antes de Usuario pois usuarios
# referenciam empresa_id. Produto vem antes de Venda/ItemVenda pois
# itens_venda.produto_id referencia produtos.id (FK precisa existir nos
# dois bancos antes do item ser inserido). Venda vem antes de ItemVenda e
# VendaPagamento pelo mesmo motivo (venda_id).
TABELAS_SINCRONIZAVEIS = [
    Empresa, Usuario, Categoria, Receita, Despesa, DespesaFixa, Meta, Pagamento, Aviso,
    Produto, Venda, ItemVenda, VendaPagamento, ConfiguracaoPlataforma,
]

# Colunas que nunca são comparadas/copiadas (são específicas de cada banco
# ou geridas à parte).
_COLUNAS_IGNORADAS = {"id"}

_CHAVE_CONFIG_ULTIMA_SYNC = "ultima_sincronizacao"

_MODELOS_POR_NOME = {m.__name__: m for m in TABELAS_SINCRONIZAVEIS}

# --- Empresa da instalação local atual, definida por app.py logo após o
# login (ver definir_empresa_ativa). Usada para checar, a cada ciclo, se
# o super admin ainda mantém a nuvem liberada para esta empresa. ---
_empresa_ativa_id: int | None = None


def definir_empresa_ativa(empresa_id: int | None) -> None:
    """Chamado após o login para registrar a empresa da instalação local."""
    global _empresa_ativa_id
    _empresa_ativa_id = empresa_id


def nuvem_liberada_para_empresa() -> bool:
    """
    Checagem leve (lê só a coluna nuvem_liberada da própria empresa) feita
    ANTES do sync pesado. Super admin não tem empresa (super_admin=True,
    empresa_id None) e sempre tem acesso liberado. Se a nuvem estiver fora
    do ar, assume liberado (quem decide bloquear é sempre o valor salvo na
    nuvem; sem nuvem não dá pra confirmar bloqueio nem liberação mesmo).
    """
    if _empresa_ativa_id is None:
        return True
    if not nuvem_disponivel():
        return True
    sessao_nuvem = get_session_cloud()
    try:
        empresa = sessao_nuvem.get(Empresa, _empresa_ativa_id)
        if empresa is None:
            return True
        return bool(empresa.nuvem_liberada)
    except Exception:
        return True
    finally:
        sessao_nuvem.close()

# Colunas de chave estrangeira que guardam o id NUMÉRICO de outra tabela
# sincronizável. Esse id é autoincrementado de forma independente em cada
# banco (local e nuvem), então o mesmo registro tem ids diferentes dos dois
# lados — nunca dá pra copiar o número direto. Por isso, ao sincronizar,
# cada uma dessas colunas é traduzida usando o `uuid` do registro
# referenciado como ponte estável entre os dois bancos.
FK_SINCRONIZAVEIS: dict[str, dict[str, str]] = {
    "Usuario": {
        "empresa_id": "Empresa", "criado_por_id": "Usuario", "conta_principal_id": "Usuario",
    },
    "Receita": {"empresa_id": "Empresa", "categoria_id": "Categoria", "usuario_id": "Usuario"},
    "Despesa": {
        "empresa_id": "Empresa", "categoria_id": "Categoria", "usuario_id": "Usuario", "despesa_fixa_id": "DespesaFixa",
    },
    "DespesaFixa": {"empresa_id": "Empresa", "categoria_id": "Categoria"},
    "Pagamento": {"empresa_id": "Empresa", "conta_principal_id": "Usuario"},
    "Produto": {"empresa_id": "Empresa"},
    "Categoria": {"empresa_id": "Empresa"},
    "Meta": {"empresa_id": "Empresa"},
    "Aviso": {"empresa_id": "Empresa"},
    "Venda": {"empresa_id": "Empresa", "usuario_id": "Usuario"},
    "VendaPagamento": {"venda_id": "Venda"},
    "ItemVenda": {"venda_id": "Venda", "produto_id": "Produto"},
}


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


def _remapear_fks(sessao_origem, sessao_destino, nome_modelo: str, dados: dict) -> dict | None:
    """
    Traduz as colunas de FK de `dados` (lidas do lado de `sessao_origem`)
    para os ids numéricos equivalentes no lado de `sessao_destino`, usando o
    uuid do registro referenciado como ponte — os ids numéricos nunca
    coincidem entre local e nuvem, só o uuid é estável nos dois bancos.

    Devolve None se alguma referência obrigatória ainda não existe de um dos
    lados (a linha referenciada ainda não foi sincronizada); nesse caso quem
    chamou deve pular o registro nesta rodada e tentar de novo no próximo
    ciclo, quando a dependência já estiver presente.
    """
    fk_colunas = FK_SINCRONIZAVEIS.get(nome_modelo)
    if not fk_colunas:
        return dict(dados)
    dados = dict(dados)
    for coluna, nome_modelo_ref in fk_colunas.items():
        valor = dados.get(coluna)
        if valor is None:
            continue
        modelo_ref = _MODELOS_POR_NOME[nome_modelo_ref]
        ref_origem = sessao_origem.get(modelo_ref, valor)
        if ref_origem is None:
            return None
        ref_destino = sessao_destino.query(modelo_ref).filter_by(uuid=ref_origem.uuid).first()
        if ref_destino is None:
            return None
        dados[coluna] = ref_destino.id
    return dados


# Lock global: garante que só exista UM sincronizar() rodando por vez,
# não importa quem chamou (timer periódico do app.py, botão "Sincronizar
# agora" da tela de configurações, ou o disparo em tempo real após commit).
# Sem isso, duas chamadas concorrentes abrem duas transações de escrita no
# SQLite local ao mesmo tempo; como o ciclo faz várias chamadas HTTP à
# nuvem (lentas) dentro da transação aberta, ela pode ficar presa por mais
# tempo que o busy_timeout do SQLite, gerando "database is locked".
_lock_sincronizar = threading.Lock()


def sincronizar() -> dict:
    """
    Executa um ciclo completo de sincronização entre local e nuvem.
    Se já houver um ciclo em andamento (chamado de outro lugar), retorna
    imediatamente sem tentar de novo — evita duas transações de escrita
    concorrentes no SQLite local, causa raiz do "database is locked".

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
    if not _lock_sincronizar.acquire(blocking=False):
        return {"sincronizado": False, "aplicados": 0, "conflitos": [], "ja_em_andamento": True}
    try:
        return _sincronizar_impl()
    finally:
        _lock_sincronizar.release()


def _sincronizar_impl() -> dict:
    if not nuvem_disponivel():
        return {"sincronizado": False, "aplicados": 0, "conflitos": []}

    if not nuvem_liberada_para_empresa():
        return {"sincronizado": False, "aplicados": 0, "conflitos": [], "nuvem_bloqueada": True}

    sessao_local = get_session()
    sessao_nuvem = get_session_cloud()
    aplicados = 0
    conflitos: list[dict] = []
    agora = datetime.now()
    device_id_atual = obter_device_id()
    log = SyncLog(device_id=device_id_atual, inicio=agora)
    sessao_local.add(log)

    try:
        ultima_sync = _obter_ultima_sincronizacao(sessao_local)
        registrar_dispositivo(sessao_local)
        registrar_dispositivo(sessao_nuvem)

        for modelo in TABELAS_SINCRONIZAVEIS:
            nome_modelo = modelo.__name__
            colunas = _colunas_modelo(modelo)
            locais = {r.uuid: r for r in sessao_local.query(modelo).all()}
            nuvens = {r.uuid: r for r in sessao_nuvem.query(modelo).all()}

            todos_uuids = set(locais.keys()) | set(nuvens.keys())

            for u in todos_uuids:
                reg_local = locais.get(u)
                reg_nuvem = nuvens.get(u)

                # --- Só existe em um dos lados: copia para o outro ---
                if reg_local is None:
                    dados = _remapear_fks(
                        sessao_nuvem, sessao_local, nome_modelo, _linha_para_dict(reg_nuvem, colunas)
                    )
                    if dados is None:
                        continue  # depende de algo que ainda não existe no local; tenta no próximo ciclo
                    try:
                        with sessao_local.begin_nested():
                            sessao_local.add(modelo(**dados))
                            sessao_local.flush()
                        aplicados += 1
                    except IntegrityError:
                        # Registro colide com um já existente localmente (ex.: mesmo
                        # login/sigla criado nos dois lados antes do primeiro sync).
                        # Resolve sozinho, sem popup: a nuvem vence, a duplicata local é removida.
                        sessao_local.rollback()
                        _aplicar_resolucao_duplicata(
                            sessao_local, sessao_nuvem, modelo, nome_modelo,
                            {"local": None, "nuvem": _linha_para_dict(reg_nuvem, colunas)},
                            "nuvem",
                        )
                        aplicados += 1
                    continue
                if reg_nuvem is None:
                    dados = _remapear_fks(
                        sessao_local, sessao_nuvem, nome_modelo, _linha_para_dict(reg_local, colunas)
                    )
                    if dados is None:
                        continue  # depende de algo que ainda não existe na nuvem; tenta no próximo ciclo
                    try:
                        with sessao_nuvem.begin_nested():
                            sessao_nuvem.add(modelo(**dados))
                            sessao_nuvem.flush()
                        aplicados += 1
                    except IntegrityError:
                        # Local tem um registro que colide com uma restrição única já
                        # existente na nuvem: a nuvem vence, a duplicata local é removida.
                        sessao_nuvem.rollback()
                        _aplicar_resolucao_duplicata(
                            sessao_local, sessao_nuvem, modelo, nome_modelo,
                            {"local": _linha_para_dict(reg_local, colunas), "nuvem": None},
                            "nuvem",
                        )
                        aplicados += 1
                    continue

                # --- Existe nos dois lados: compara conteúdo (remapeando FK antes) ---
                d_local = _linha_para_dict(reg_local, colunas)
                d_nuvem = _linha_para_dict(reg_nuvem, colunas)
                d_local_no_espaco_nuvem = _remapear_fks(sessao_local, sessao_nuvem, nome_modelo, d_local)
                if d_local_no_espaco_nuvem is not None and d_local_no_espaco_nuvem == d_nuvem:
                    continue  # já iguais, nada a fazer

                mudou_local = reg_local.atualizado_em > ultima_sync
                mudou_nuvem = reg_nuvem.atualizado_em > ultima_sync

                if mudou_local and mudou_nuvem:
                    # Conflito real: os dois lados mudaram desde a última sync.
                    conflitos.append({
                        "tabela": nome_modelo,
                        "uuid": u,
                        "local": d_local,
                        "nuvem": d_nuvem,
                    })
                elif mudou_local:
                    # Só o local mudou -> aplica na nuvem
                    dados = _remapear_fks(sessao_local, sessao_nuvem, nome_modelo, d_local)
                    if dados is None:
                        continue
                    try:
                        with sessao_nuvem.begin_nested():
                            for c in colunas:
                                if c != "uuid":
                                    setattr(reg_nuvem, c, dados[c])
                            sessao_nuvem.flush()
                        aplicados += 1
                    except IntegrityError:
                        # A alteração local colide com uma restrição única na nuvem.
                        # Nuvem vence: descarta a alteração local, sem popup.
                        sessao_nuvem.expire(reg_nuvem)
                        dados_volta = _remapear_fks(sessao_nuvem, sessao_local, nome_modelo, d_nuvem)
                        if dados_volta is not None:
                            with sessao_local.begin_nested():
                                for c in colunas:
                                    if c != "uuid":
                                        setattr(reg_local, c, dados_volta[c])
                                sessao_local.flush()
                            aplicados += 1
                else:
                    # Só a nuvem mudou (ou nenhum, por segurança aplica nuvem) -> aplica no local
                    dados = _remapear_fks(sessao_nuvem, sessao_local, nome_modelo, d_nuvem)
                    if dados is None:
                        continue
                    try:
                        with sessao_local.begin_nested():
                            for c in colunas:
                                if c != "uuid":
                                    setattr(reg_local, c, dados[c])
                            sessao_local.flush()
                        aplicados += 1
                    except IntegrityError:
                        # O dado da nuvem colide com uma duplicata local (mesma
                        # chave única, uuid diferente). Nuvem vence, sem popup:
                        # remove a duplicata local e grava a versão da nuvem.
                        sessao_local.expire(reg_local)
                        _aplicar_resolucao_duplicata(
                            sessao_local, sessao_nuvem, modelo, nome_modelo,
                            {"local": d_local, "nuvem": d_nuvem}, "nuvem",
                        )
                        aplicados += 1

            # Antes de passar pra próxima tabela, garante que os registros
            # recém-adicionados aqui já tenham id gravado nos dois bancos —
            # tabelas seguintes (ex.: Venda depende de Usuario) precisam
            # encontrar esse uuid já com id numérico ao fazer o remapeamento.
            sessao_local.flush()
            sessao_nuvem.flush()

            # Libera o lock de escrita do SQLite entre uma tabela e outra
            # (commit real, não só flush) — o restante do ciclo ainda tem
            # chamadas de rede lentas pra nuvem, e segurar a transação
            # local aberta esse tempo todo é o que causa "database is
            # locked" quando o usuário tenta salvar algo pela UI durante
            # a sincronização. Seguro fazer aqui: a reconciliação é
            # idempotente por uuid, então retomar do meio em caso de falha
            # não duplica nem perde nada.
            sessao_local.commit()

        _gravar_ultima_sincronizacao(sessao_local, agora)

        # Marca como SINCRONIZADO todo evento pendente da fila que este
        # device gerou até agora (a cópia dos dados já foi aplicada acima
        # pelo merge completo por tabela; a fila serve de trilha de
        # auditoria do que foi gerado localmente entre ciclos).
        enviados = (
            sessao_local.query(SyncQueue)
            .filter_by(device_id=device_id_atual, status="PENDENTE")
            .update({"status": "SINCRONIZADO"}, synchronize_session=False)
        )
        log.fim = datetime.now()
        log.enviados = enviados
        log.recebidos = aplicados

        sessao_local.commit()
        sessao_nuvem.commit()
    except Exception as e:
        sessao_local.rollback()
        sessao_nuvem.rollback()
        try:
            sessao_erro = get_session()
            sessao_erro.add(SyncLog(device_id=device_id_atual, inicio=agora, fim=datetime.now(), erro=str(e)[:2000]))
            sessao_erro.commit()
            sessao_erro.close()
        except Exception:
            pass
        raise
    finally:
        sessao_local.close()
        sessao_nuvem.close()

    return {"sincronizado": True, "aplicados": aplicados, "conflitos": conflitos}


# --- Disparo em tempo real ---------------------------------------------
# Chamado automaticamente logo após qualquer commit no banco local (ver
# database.registrar_callback_pos_commit_local, registrado no app.py).
# Em vez de disparar um sync completo a CADA commit (uma venda com vários
# itens gera vários commits em sequência, cada um varrendo todas as
# tabelas), usa debounce: espera a rajada de commits terminar (janela de
# silêncio) antes de rodar um único sincronizar(). O lock impede reentrância
# e sync simultâneo com o polling.
_lock_sync_tempo_real = threading.Lock()
_debounce_timer: threading.Timer | None = None
_debounce_janela_seg = 2.5


def _executar_sync_protegido() -> None:
    if not _lock_sync_tempo_real.acquire(blocking=False):
        return
    try:
        sincronizar()
    except Exception:
        pass
    finally:
        _lock_sync_tempo_real.release()


def sincronizar_em_tempo_real() -> None:
    """Agenda sincronizar() em background após uma janela de silêncio,
    reiniciando a contagem a cada novo commit (debounce) para não empilhar
    um sync completo por item/linha gravada."""
    global _debounce_timer
    if _debounce_timer is not None:
        _debounce_timer.cancel()
    _debounce_timer = threading.Timer(_debounce_janela_seg, _executar_sync_protegido)
    _debounce_timer.daemon = True
    _debounce_timer.start()


def _colunas_unicas(modelo) -> list[list[str]]:
    """
    Agrupa as colunas que formam alguma restrição única do modelo (colunas
    isoladas com unique=True e UniqueConstraint compostas), ignorando uuid/id
    — usadas para achar, no lado de destino, a linha "duplicata" que colide
    com o registro vencedor por ter os mesmos dados de negócio (ex.: mesmo
    login) só que com uuid diferente (criada independentemente nos dois
    lados antes do primeiro sync).
    """
    grupos: list[list[str]] = []
    for coluna in modelo.__table__.columns:
        if coluna.unique and coluna.name not in ("uuid", "id"):
            grupos.append([coluna.name])
    for restricao in modelo.__table__.constraints:
        if isinstance(restricao, UniqueConstraint):
            nomes = [c.name for c in restricao.columns if c.name not in ("uuid", "id")]
            if nomes:
                grupos.append(nomes)
    return grupos


def _aplicar_resolucao_duplicata(
    sessao_local, sessao_nuvem, modelo, tabela: str, conflito: dict, escolha: str
) -> None:
    """
    Núcleo de resolver_duplicata, operando em sessões já abertas (usado tanto
    pela resolução manual via UI quanto pela automática dentro de sincronizar()).
    Não commita nem fecha as sessões — quem chamou decide.

    escolha: "local" mantém a versão local; "nuvem" mantém a versão da nuvem.

    Se o lado escolhido não tiver dados capturados no conflito (dados_origem
    None), é porque esse lado nunca teve esse uuid: o dado de negócio já
    está garantido do outro lado por uma linha duplicada (uuid diferente,
    mesma chave única) que bloqueou a cópia original. Nesse caso não há o
    que gravar — só remove a linha órfã que ficou presa no lado rejeitado.
    """
    dados_origem = conflito["local"] if escolha == "local" else conflito["nuvem"]

    if dados_origem is None:
        orfao = conflito["nuvem"] if escolha == "local" else conflito["local"]
        sessao_orfa = sessao_nuvem if escolha == "local" else sessao_local
        if orfao is not None:
            linha = sessao_orfa.query(modelo).filter_by(uuid=orfao["uuid"]).first()
            if linha is not None:
                sessao_orfa.delete(linha)
                sessao_orfa.flush()
        return

    colunas = _colunas_modelo(modelo)
    grupos_unicos = _colunas_unicas(modelo)

    if escolha == "local":
        sessao_origem, sessao_destino = sessao_local, sessao_nuvem
    else:
        sessao_origem, sessao_destino = sessao_nuvem, sessao_local

    dados = _remapear_fks(sessao_origem, sessao_destino, tabela, dados_origem)
    if dados is None:
        raise ValueError(
            "Não foi possível aplicar a versão escolhida: alguma referência"
            " (usuário, categoria, produto, etc.) ainda não existe do outro lado."
        )

    for grupo in grupos_unicos:
        if any(dados.get(c) is None for c in grupo):
            continue
        consulta = sessao_destino.query(modelo)
        for c in grupo:
            consulta = consulta.filter(getattr(modelo, c) == dados[c])
        duplicata = consulta.first()
        if duplicata is not None and duplicata.uuid != dados["uuid"]:
            sessao_destino.delete(duplicata)
            sessao_destino.flush()

    existente = sessao_destino.query(modelo).filter_by(uuid=dados["uuid"]).first()
    if existente is None:
        sessao_destino.add(modelo(**dados))
    else:
        for c in colunas:
            if c != "uuid":
                setattr(existente, c, dados[c])
    sessao_destino.flush()


def resolver_duplicata(tabela: str, conflito: dict, escolha: str) -> None:
    """
    Resolve manualmente (via UI) um conflito do tipo "restricao_unica".
    escolha: "local" ou "nuvem" — ver _aplicar_resolucao_duplicata.
    """
    modelo = next((m for m in TABELAS_SINCRONIZAVEIS if m.__name__ == tabela), None)
    if modelo is None:
        raise ValueError(f"Tabela sincronizável desconhecida: {tabela}")

    sessao_local = get_session()
    sessao_nuvem = get_session_cloud()
    if sessao_nuvem is None:
        sessao_local.close()
        raise RuntimeError("Nuvem indisponível no momento; tente novamente depois.")

    sessao_destino = sessao_local if escolha == "nuvem" else sessao_nuvem
    try:
        _aplicar_resolucao_duplicata(sessao_local, sessao_nuvem, modelo, tabela, conflito, escolha)
        sessao_destino.commit()
    except Exception:
        sessao_destino.rollback()
        raise
    finally:
        sessao_local.close()
        sessao_nuvem.close()


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

        if escolha == "local":
            vencedor_no_local, vencedor_na_nuvem = vencedor, _remapear_fks(
                sessao_local, sessao_nuvem, tabela, vencedor
            )
        else:
            vencedor_na_nuvem, vencedor_no_local = vencedor, _remapear_fks(
                sessao_nuvem, sessao_local, tabela, vencedor
            )
        if vencedor_no_local is None or vencedor_na_nuvem is None:
            raise ValueError(
                "Não foi possível aplicar a versão escolhida: alguma referência"
                " (usuário, categoria, produto, etc.) ainda não existe do outro lado."
            )

        for c in colunas:
            if c == "uuid":
                continue
            setattr(reg_local, c, vencedor_no_local[c])
            setattr(reg_nuvem, c, vencedor_na_nuvem[c])

        sessao_local.commit()
        sessao_nuvem.commit()
    except Exception:
        sessao_local.rollback()
        sessao_nuvem.rollback()
        raise
    finally:
        sessao_local.close()
        sessao_nuvem.close()
