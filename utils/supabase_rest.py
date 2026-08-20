"""
utils/supabase_rest.py
Acesso à nuvem via API REST do Supabase (PostgREST) no lugar de conexão
Postgres direta. RestSession imita o suficiente da interface de Session
do SQLAlchemy (get/query/add/delete/flush/commit/rollback/close,
begin_nested) para controllers/sync_controller.py mudar o mínimo possível.

Autenticação: token JWT por instalação, obtido no login (ver
supabase/002_jwt_empresa_id.md) e injetado via definir_jwt_atual(). O
isolamento por empresa é garantido pelo Postgres (RLS), não por este
código — mesmo que um filtro aqui esteja errado, o banco barra a leitura/
escrita de outra empresa.

Limitação conhecida: cada escrita vira uma chamada HTTP independente,
aplicada no momento do flush()/commit() — não existe uma transação única
cobrindo o ciclo de sync inteiro do lado da nuvem (PostgREST não expõe
transação multi-request). Se um erro inesperado interromper o sync no
meio, registros já enviados nesta rodada permanecem na nuvem; o próximo
ciclo reconcilia o que faltou (mesma tolerância a interrupção que o app
já tem hoje ao perder conexão no meio de um sync).
"""
from __future__ import annotations

import os
import enum
import operator as _pyop
from datetime import datetime, date
from typing import Any

import httpx
from sqlalchemy.exc import IntegrityError

VERSAO_ARQUIVO = "supabase_rest.py v8 (checagem de existência restrita a empresas; sem debug log por linha)"

# Mapeia o operador Python usado em `modelo.coluna > valor` etc. para o
# operador equivalente do PostgREST. Usado só por RestQuery.filter() —
# RestQuery.filter_by() continua sempre igualdade (eq.).
_OPERADORES_POSTGREST = {
    _pyop.eq: "eq",
    _pyop.gt: "gt",
    _pyop.lt: "lt",
    _pyop.ge: "gte",
    _pyop.le: "lte",
}

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
_REST_URL = f"{SUPABASE_URL}/rest/v1" if SUPABASE_URL else ""

_jwt_atual: str | None = None


def definir_jwt_atual(jwt: str | None) -> None:
    """Chamado após login/refresh (utils/nuvem_auth.py) para que as
    próximas sessões da nuvem usem o token corrente da instalação."""
    global _jwt_atual
    _jwt_atual = jwt


def configurado() -> bool:
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY and _jwt_atual)


def _headers() -> dict:
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {_jwt_atual}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _tabela(modelo) -> str:
    return modelo.__tablename__


def _coagir(modelo, dados: dict) -> dict:
    """Converte valores vindos do JSON (strings ISO, nomes de enum) para os
    tipos Python que o resto do código espera (datetime/date/Enum), igual
    ao que o driver do Postgres faria automaticamente numa conexão
    direta."""
    colunas = {c.name: c for c in modelo.__table__.columns}
    coagidos = {}
    for chave, valor in dados.items():
        coluna = colunas.get(chave)
        if valor is not None and coluna is not None:
            tipo_coluna = getattr(coluna.type, "enum_class", None)
            if tipo_coluna is not None and isinstance(valor, str):
                # Nome do membro (ex.: "FISICA"), não o .value de exibição.
                valor = tipo_coluna[valor]
            else:
                try:
                    tipo = coluna.type.python_type
                except NotImplementedError:
                    tipo = None
                if tipo is datetime and isinstance(valor, str):
                    valor = datetime.fromisoformat(valor.replace("Z", "+00:00")).replace(tzinfo=None)
                elif tipo is date and isinstance(valor, str):
                    valor = date.fromisoformat(valor[:10])
        coagidos[chave] = valor
    return coagidos


def _payload(obj) -> dict:
    modelo = type(obj)
    dados = {}
    for c in modelo.__table__.columns:
        if c.name == "id":
            continue
        valor = getattr(obj, c.name, None)
        if isinstance(valor, enum.Enum):
            # O tipo enum no Postgres usa o NOME do membro Python
            # (ex.: "FISICA"), não o .value de exibição (ex.: "Pessoa
            # Física") — mesmo em enums que herdam de str, onde o valor
            # de exibição seria serializado por engano se não tratado.
            valor = valor.name
        elif isinstance(valor, (datetime, date)):
            valor = valor.isoformat()
        dados[c.name] = valor
    return dados


def _erro_e_conflito(resp: httpx.Response) -> bool:
    # PostgREST devolve 409 (unique_violation) ou 23505 no corpo.
    return resp.status_code == 409


def _checar_resposta(r: httpx.Response) -> None:
    """raise_for_status() sozinho não mostra o corpo da resposta (onde o
    Postgres/PostgREST explica qual coluna/constraint recusou) — inclui o
    texto da resposta na mensagem antes de propagar, pra log_erros ficar
    útil para diagnóstico."""
    if r.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"{r.status_code} em {r.request.method} {r.request.url}: {r.text}",
            request=r.request, response=r,
        )


def _chave_identidade(obj) -> tuple[str, Any]:
    """A maioria das tabelas sincronizáveis usa `uuid` (SyncMixin) como
    chave estável entre local e nuvem. `Dispositivo` é exceção: não tem
    `uuid`, usa `device_id` como chave natural. Escolhe a coluna certa
    pra filtrar PATCH/DELETE, em vez de assumir `uuid` sempre."""
    if getattr(obj, "uuid", None):
        return "uuid", obj.uuid
    if getattr(obj, "device_id", None):
        return "device_id", obj.device_id
    raise AttributeError(
        f"{type(obj).__name__} não tem `uuid` nem `device_id` — não dá pra "
        f"identificar essa linha na nuvem de forma estável."
    )


class RestQuery:
    def __init__(self, sessao: "RestSession", modelo):
        self.sessao = sessao
        self.modelo = modelo
        self.filtros: dict[str, str] = {}

    def filter_by(self, **kwargs) -> "RestQuery":
        for chave, valor in kwargs.items():
            self.filtros[chave] = f"eq.{valor}"
        return self

    def filter(self, *criterios) -> "RestQuery":
        # Suporta comparações simples (getattr(modelo, col) OP valor) com
        # OP em {==, >, <, >=, <=} — o suficiente pro que sync_controller.py
        # usa (igualdade e a filtragem incremental por atualizado_em).
        for criterio in criterios:
            coluna = criterio.left.name
            valor = criterio.right.value
            op = _OPERADORES_POSTGREST.get(criterio.operator, "eq")
            if isinstance(valor, (datetime, date)):
                valor = valor.isoformat()
            self.filtros[coluna] = f"{op}.{valor}"
        return self

    def all(self) -> list:
        params = {"select": "*", **self.filtros}
        r = httpx.get(f"{_REST_URL}/{_tabela(self.modelo)}", params=params,
                       headers=_headers(), timeout=20)
        _checar_resposta(r)
        linhas = [self.modelo(**_coagir(self.modelo, linha)) for linha in r.json()]
        for linha in linhas:
            self.sessao._registrar(linha)
        return linhas

    def first(self):
        params = {"select": "*", "limit": "1", **self.filtros}
        r = httpx.get(f"{_REST_URL}/{_tabela(self.modelo)}", params=params,
                       headers=_headers(), timeout=20)
        _checar_resposta(r)
        linhas = r.json()
        if not linhas:
            return None
        obj = self.modelo(**_coagir(self.modelo, linhas[0]))
        self.sessao._registrar(obj)
        return obj

    def update(self, valores: dict, synchronize_session: bool = False) -> int:
        r = httpx.patch(f"{_REST_URL}/{_tabela(self.modelo)}", params=self.filtros,
                         headers=_headers(), json=valores, timeout=20)
        _checar_resposta(r)
        return len(r.json())


class RestSession:
    """Sessão da nuvem via PostgREST. Cada linha trafega como instância
    do modelo SQLAlchemy correspondente, usada só como contêiner de
    atributos (nunca é vinculada/persistida por um Session real)."""

    def __init__(self):
        self._novos: list = []
        self._del: list = []
        # id(obj) -> (obj, snapshot do payload no último sync com a nuvem)
        self._conhecidos: dict[int, tuple[Any, dict]] = {}

    def query(self, modelo) -> RestQuery:
        return RestQuery(self, modelo)

    def get(self, modelo, pk):
        r = httpx.get(f"{_REST_URL}/{_tabela(modelo)}", params={"select": "*", "id": f"eq.{pk}"},
                       headers=_headers(), timeout=20)
        _checar_resposta(r)
        linhas = r.json()
        if not linhas:
            return None
        obj = modelo(**_coagir(modelo, linhas[0]))
        self._registrar(obj)
        return obj

    def add(self, obj) -> None:
        # Objetos criados direto numa sessão da nuvem (sem passar pelo
        # banco local primeiro, ex.: registrar_dispositivo) não recebem os
        # defaults do SyncMixin (uuid, criado_em, atualizado_em,
        # sync_version, deletado) — esses defaults só são aplicados pelo
        # SQLAlchemy num flush() de verdade contra um engine. Preenche
        # aqui pra não mandar NULL pro Postgres em colunas NOT NULL.
        if hasattr(obj, "uuid") and getattr(obj, "uuid", None) is None:
            import uuid as _uuid_mod
            obj.uuid = str(_uuid_mod.uuid4())
        if hasattr(obj, "criado_em") and getattr(obj, "criado_em", None) is None:
            obj.criado_em = datetime.now()
        if hasattr(obj, "atualizado_em") and getattr(obj, "atualizado_em", None) is None:
            obj.atualizado_em = datetime.now()
        if hasattr(obj, "sync_version") and getattr(obj, "sync_version", None) is None:
            obj.sync_version = 1
        if hasattr(obj, "deletado") and getattr(obj, "deletado", None) is None:
            obj.deletado = False
        self._novos.append(obj)

    def delete(self, obj) -> None:
        self._del.append(obj)

    def expire(self, obj) -> None:
        pass  # sem cache local a invalidar nesta sessão

    def begin_nested(self):
        return _NullContext()

    def _registrar(self, obj) -> None:
        self._conhecidos[id(obj)] = (obj, _payload(obj))

    def flush(self) -> None:
        novos, self._novos = self._novos, []
        for obj in novos:
            tabela = _tabela(type(obj))
            # A checagem de "já existe?" só é necessária pra `empresas`:
            # é a única tabela que pode chegar na nuvem por outro caminho
            # antes do primeiro sync do cliente (Edge Function
            # solicitar-ativacao). Fazer isso pra toda tabela soma um GET
            # extra por linha nova, em toda tabela — foi o que deixou o
            # ciclo de sync extremamente lento (minutos) e travando o
            # SQLite local por tempo demais. As demais tabelas já lidam
            # com conflito via 409/IntegrityError normalmente.
            if tabela == "empresas":
                try:
                    campo_chave, valor_chave = _chave_identidade(obj)
                except AttributeError:
                    campo_chave, valor_chave = None, None
                if campo_chave:
                    r_existe = httpx.get(
                        f"{_REST_URL}/{tabela}", params={"select": "*", campo_chave: f"eq.{valor_chave}"},
                        headers=_headers(), timeout=20,
                    )
                    _checar_resposta(r_existe)
                    linhas_existentes = r_existe.json()
                    if linhas_existentes:
                        self._registrar(obj)
                        continue

            r = httpx.post(f"{_REST_URL}/{tabela}", headers=_headers(),
                            json=_payload(obj), timeout=20)
            if _erro_e_conflito(r):
                raise IntegrityError("insert", {}, Exception(r.text))
            _checar_resposta(r)
            self._registrar(obj)

        for chave in list(self._conhecidos.keys()):
            obj, snapshot = self._conhecidos[chave]
            atual = _payload(obj)
            if atual == snapshot:
                continue
            campo_chave, valor_chave = _chave_identidade(obj)
            r = httpx.patch(f"{_REST_URL}/{_tabela(type(obj))}", params={campo_chave: f"eq.{valor_chave}"},
                             headers=_headers(), json=atual, timeout=20)
            if _erro_e_conflito(r):
                del self._conhecidos[chave]
                raise IntegrityError("update", {}, Exception(r.text))
            _checar_resposta(r)
            self._conhecidos[chave] = (obj, atual)

        dels, self._del = self._del, []
        for obj in dels:
            campo_chave, valor_chave = _chave_identidade(obj)
            r = httpx.delete(f"{_REST_URL}/{_tabela(type(obj))}", params={campo_chave: f"eq.{valor_chave}"},
                              headers=_headers(), timeout=20)
            _checar_resposta(r)
            self._conhecidos.pop(id(obj), None)

    def commit(self) -> None:
        self.flush()

    def rollback(self) -> None:
        self._novos.clear()
        self._del.clear()
        # objetos "conhecidos" e já sujos (setattr aplicado) ficam como
        # estão em memória; como a sessão é descartada logo após (ver
        # sincronizar()), não há retomada indevida deles.

    def close(self) -> None:
        pass


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, tb):
        return False
