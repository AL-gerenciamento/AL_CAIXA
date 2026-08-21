"""
database.py
Configura o engine SQLAlchemy local e, opcionalmente, o engine da nuvem.

Arquitetura "local-first":
- O banco LOCAL (SQLite) é sempre a fonte principal. Todo o app lê e
  grava nele o tempo todo, inclusive sem internet.
- O banco da NUVEM (Postgres/Supabase, via DATABASE_URL no .env) é usado
  apenas pelo sync_controller: em tempo real após cada commit local, além
  de um polling curto e ao fechar o app, para manter uma cópia atualizada
  e permitir acesso de outras máquinas.
- Se a nuvem estiver fora do ar, o app continua funcionando 100% local;
  a sincronização é tentada novamente no próximo ciclo.
"""
import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session

from utils.paths import pasta_base

BASE_DIR = pasta_base()
DB_PATH = os.path.join(BASE_DIR, "database.db")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# --- Banco local: sempre existe, é o que o app usa no dia a dia ---
# timeout alto evita "database is locked" quando o sync (transação longa,
# várias tabelas) e a UI gravam quase ao mesmo tempo; WAL permite leitores
# e um escritor simultâneos em vez de bloquear tudo com uma única gravação.
engine_local = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False, "timeout": 30},
)
SessionLocal = sessionmaker(bind=engine_local, autoflush=False, autocommit=False)


@event.listens_for(engine_local, "connect")
def _configurar_sqlite(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()

# --- Banco da nuvem: opcional, só para sincronização ---
# Modo padrão (distribuído aos clientes): REST do Supabase (PostgREST),
# sem credencial mestre do Postgres no .exe — ver utils/supabase_rest.py
# e PROGRESSO_SEGURANCA.md. DATABASE_URL (conexão direta) só existe como
# modo interno/dev (flag), nunca deve ir no build distribuído (Fase 6).
from utils import supabase_rest

USAR_REST_NUVEM = bool(supabase_rest.SUPABASE_URL)

engine_cloud = None
SessionCloud = None
if not USAR_REST_NUVEM and DATABASE_URL:
    try:
        engine_cloud = create_engine(
            DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={"connect_timeout": 5},
        )
        SessionCloud = sessionmaker(bind=engine_cloud, autoflush=False, autocommit=False)
    except Exception:
        engine_cloud = None
        SessionCloud = None

# Alias mantido por compatibilidade com código existente que usa "engine"
# (sempre aponta para o banco local, que é o principal).
engine = engine_local


def get_session() -> Session:
    """Retorna uma nova sessão do banco LOCAL (uso normal da aplicação)."""
    return SessionLocal()


# --- Sync em tempo real: dispara callbacks logo após qualquer commit no
# banco local (toda gravação de tela/controller usa get_session()) ---
_callbacks_pos_commit_local: list = []


def registrar_callback_pos_commit_local(callback) -> None:
    """Registra função (sem args) a ser chamada após todo commit no banco local."""
    _callbacks_pos_commit_local.append(callback)


@event.listens_for(SessionLocal, "after_commit")
def _apos_commit_local(session: Session) -> None:
    for callback in _callbacks_pos_commit_local:
        try:
            callback()
        except Exception:
            pass


def get_session_cloud():
    """Retorna uma nova sessão da NUVEM (RestSession via Supabase REST, ou
    Session SQLAlchemy no modo dev com DATABASE_URL), ou None se
    não configurado/indisponível."""
    if USAR_REST_NUVEM:
        if not supabase_rest.configurado():
            return None
        return supabase_rest.RestSession()
    if SessionCloud is None:
        return None
    return SessionCloud()


def nuvem_disponivel() -> bool:
    """Testa rapidamente se a nuvem está acessível agora."""
    ok, _ = testar_conexao_nuvem()
    return ok


def _claims_jwt_atual() -> dict:
    """Decodifica (sem validar assinatura — só para diagnóstico local) o
    payload do JWT em uso agora, pra conferir qual empresa_id/e-mail a
    sessão ativada realmente carrega."""
    import base64
    import json
    token = supabase_rest._jwt_atual
    if not token:
        return {}
    try:
        partes = token.split(".")
        payload = partes[1] + "=" * (-len(partes[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception as e:
        return {"erro_ao_decodificar": str(e)}


def testar_conexao_nuvem() -> tuple[bool, str]:
    """
    Testa a conexão com a nuvem e devolve (ok, mensagem_detalhada) — útil para
    diagnosticar o motivo real da falha (URL ausente, driver ausente, host
    inalcançável, autenticação, JWT expirado, etc.).
    """
    if USAR_REST_NUVEM:
        if supabase_rest.modo_service_role():
            # Painel super admin (admin_panel/app.py): service_role key
            # bypassa RLS por completo, sem login/JWT de instalação.
            try:
                import httpx
                r = httpx.get(
                    f"{supabase_rest._REST_URL}/usuarios",
                    params={"select": "id", "limit": "1"},
                    headers=supabase_rest._headers(),
                    timeout=5,
                )
                if r.status_code == 200:
                    return True, "Conectado com sucesso (service_role)."
                return False, f"Resposta inesperada da nuvem (service_role): {r.status_code} {r.text}"
            except Exception as e:
                return False, str(e)
        if not supabase_rest.SUPABASE_ANON_KEY:
            return False, "SUPABASE_ANON_KEY não configurada no arquivo .env."
        if not supabase_rest._jwt_atual:
            # Processo acabou de iniciar (memória perdida no reinício) —
            # tenta restaurar a sessão com o refresh_token salvo antes de
            # desistir, em vez de pedir ativação de novo à toa.
            from utils.nuvem_auth import renovar_sessao_nuvem
            renovar_sessao_nuvem()
            if not supabase_rest._jwt_atual:
                return False, "Sem login na nuvem ainda (JWT da instalação não definido)."
        try:
            import httpx
            # O endpoint raiz (/rest/v1/, sem tabela) passou a exigir
            # secret key no formato novo de chaves do Supabase — não serve
            # mais pra esse teste. Usa uma tabela real (só 1 linha, campo
            # mínimo) pra testar se o JWT/anon key realmente autenticam.
            r = httpx.get(
                f"{supabase_rest._REST_URL}/usuarios",
                params={"select": "id", "limit": "1"},
                headers=supabase_rest._headers(),
                timeout=5,
            )
            if r.status_code == 200:
                from utils.logger import registrar_erro
                registrar_erro(
                    RuntimeError(f"conexão OK. Claims do JWT ativo: {_claims_jwt_atual()}"),
                    "testar_conexao_nuvem.debug_jwt",
                )
                return True, "Conectado com sucesso."
            if r.status_code == 401:
                # access_token expirado (comum, dura ~1h): renova com o
                # refresh_token salvo e tenta de novo antes de reportar erro.
                from utils.nuvem_auth import renovar_sessao_nuvem
                from utils.logger import registrar_erro
                if renovar_sessao_nuvem():
                    r2 = httpx.get(
                        f"{supabase_rest._REST_URL}/usuarios",
                        params={"select": "id", "limit": "1"},
                        headers=supabase_rest._headers(),
                        timeout=5,
                    )
                    if r2.status_code == 200:
                        return True, "Conectado com sucesso."
                    registrar_erro(
                        RuntimeError(
                            f"401 mesmo após renovar sessão. 1a resposta: {r.text} | "
                            f"2a resposta ({r2.status_code}): {r2.text}"
                        ),
                        "testar_conexao_nuvem",
                    )
                else:
                    registrar_erro(
                        RuntimeError(f"401 e renovar_sessao_nuvem falhou. Resposta: {r.text}"),
                        "testar_conexao_nuvem",
                    )
                return False, "JWT inválido ou expirado."
            return False, f"Resposta inesperada da nuvem: {r.status_code}."
        except Exception as e:
            return False, str(e)
    if not DATABASE_URL:
        return False, "DATABASE_URL não configurada no arquivo .env (modo dev)."
    if engine_cloud is None:
        return False, "Não foi possível criar a conexão (DATABASE_URL com formato inválido ou driver do Postgres ausente)."
    try:
        with engine_cloud.connect():
            return True, "Conectado com sucesso."
    except Exception as e:
        return False, str(e)


_COLUNAS_NOVAS = [
    ("usuarios", "permissoes_modulos", "VARCHAR(500) DEFAULT ''"),
    ("empresas", "logo_path", "VARCHAR(300)"),
    ("empresas", "nuvem_liberada", "BOOLEAN DEFAULT 1"),
    ("vendas", "aberta", "BOOLEAN DEFAULT 0"),
    ("vendas", "fechada_em", "DATETIME"),
    ("vendas", "subtotal", "FLOAT DEFAULT 0"),
    ("vendas", "desconto_percentual", "FLOAT DEFAULT 0"),
    ("vendas", "acrescimo_percentual", "FLOAT DEFAULT 0"),
    ("vendas", "justificativa_acrescimo", "VARCHAR(300) DEFAULT ''"),
    ("produtos", "empresa_id", "INTEGER"),
    ("vendas", "empresa_id", "INTEGER"),
]


def _tipo_sql_para_dialeto(tipo_sql: str, dialeto: str) -> str:
    """Ajusta a sintaxe (pensada p/ SQLite) para o dialeto real do engine.

    Postgres não aceita "BOOLEAN DEFAULT 1/0" (precisa TRUE/FALSE) nem o
    tipo "DATETIME" (precisa TIMESTAMP) — sem isso o ALTER TABLE falha
    silenciosamente na nuvem e a coluna nunca é criada lá.
    """
    if dialeto != "postgresql":
        return tipo_sql
    ajustado = tipo_sql
    ajustado = ajustado.replace("BOOLEAN DEFAULT 1", "BOOLEAN DEFAULT TRUE")
    ajustado = ajustado.replace("BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT FALSE")
    ajustado = ajustado.replace("DATETIME", "TIMESTAMP")
    return ajustado


def _migrar_colunas_novas(eng) -> None:
    """Adiciona colunas criadas após o primeiro deploy em bancos já existentes."""
    dialeto = eng.dialect.name
    with eng.connect() as conn:
        for tabela, coluna, tipo_sql in _COLUNAS_NOVAS:
            tipo_sql = _tipo_sql_para_dialeto(tipo_sql, dialeto)
            try:
                conn.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo_sql}"))
                conn.commit()
            except Exception:
                conn.rollback()
        try:
            conn.execute(text(
                "UPDATE vendas SET fechada_em = data_hora "
                "WHERE fechada_em IS NULL AND (aberta IS NULL OR aberta = 0)"
            ))
            conn.commit()
        except Exception:
            conn.rollback()
        try:
            conn.execute(text(
                "UPDATE vendas SET subtotal = valor_total "
                "WHERE subtotal IS NULL OR subtotal = 0"
            ))
            conn.commit()
        except Exception:
            conn.rollback()
        # Backfill de empresa_id em vendas: a venda já tem usuario_id, que
        # aponta pra um usuário com empresa_id definido — copia de lá.
        try:
            conn.execute(text(
                "UPDATE vendas SET empresa_id = ("
                "  SELECT empresa_id FROM usuarios WHERE usuarios.id = vendas.usuario_id"
                ") WHERE empresa_id IS NULL AND usuario_id IS NOT NULL"
            ))
            conn.commit()
        except Exception:
            conn.rollback()
        # Backfill de empresa_id em produtos: como a tabela era global até
        # aqui, só dá pra resolver sozinho se existir exatamente 1 empresa
        # cadastrada (instalação de um único cliente). Com 2+ empresas não
        # há como adivinhar de quem é cada produto — fica NULL e precisa de
        # ajuste manual (ver aviso no log).
        try:
            total_empresas = conn.execute(text("SELECT COUNT(*) FROM empresas")).scalar()
            if total_empresas == 1:
                conn.execute(text(
                    "UPDATE produtos SET empresa_id = (SELECT id FROM empresas LIMIT 1) "
                    "WHERE empresa_id IS NULL"
                ))
                conn.commit()
        except Exception:
            conn.rollback()


def _migrar_colunas_sync_mixin(eng) -> None:
    """
    Garante que toda tabela sincronizável (identificada por ter a coluna
    "uuid", marca registrada pelo SyncMixin) possua as colunas da
    arquitetura de sincronização: device_id, sync_version e criado_em.
    Adiciona a coluna que estiver faltando em bancos já existentes,
    criados antes dessas colunas serem introduzidas. Genérico (varre o
    metadata) em vez de lista fixa, para cobrir tabelas novas sem exigir
    manutenção manual desta lista a cada modelo adicionado.
    """
    from sqlalchemy import inspect
    from models import Base

    dialeto = eng.dialect.name
    inspetor = inspect(eng)
    colunas_desejadas = {
        "device_id": "VARCHAR(40)",
        "sync_version": "INTEGER DEFAULT 1",
        "criado_em": "DATETIME",
    }
    with eng.connect() as conn:
        for tabela in Base.metadata.tables.values():
            if "uuid" not in tabela.columns:
                continue
            try:
                colunas_existentes = {c["name"] for c in inspetor.get_columns(tabela.name)}
            except Exception:
                continue
            for coluna, tipo_sql in colunas_desejadas.items():
                if coluna in colunas_existentes:
                    continue
                tipo_sql = _tipo_sql_para_dialeto(tipo_sql, dialeto)
                try:
                    conn.execute(text(f"ALTER TABLE {tabela.name} ADD COLUMN {coluna} {tipo_sql}"))
                    conn.commit()
                except Exception:
                    conn.rollback()
                    continue
                if coluna == "criado_em" and "atualizado_em" in tabela.columns:
                    try:
                        conn.execute(text(
                            f"UPDATE {tabela.name} SET criado_em = atualizado_em WHERE criado_em IS NULL"
                        ))
                        conn.commit()
                    except Exception:
                        conn.rollback()
        try:
            conn.execute(text(
                "UPDATE dispositivos SET nome = device_id WHERE nome IS NULL OR nome = ''"
            ))
            conn.commit()
        except Exception:
            conn.rollback()


def registrar_dispositivo(sessao, nome: str = "") -> None:
    """Garante que exista uma linha em `dispositivos` para o device_id
    desta instalação (seção 6 e 16 da arquitetura de sincronização),
    atualizando `ultima_sincronizacao`. Chamado a cada ciclo de sync."""
    from datetime import datetime as _dt
    from models import Dispositivo
    from utils.device import obter_device_id

    device_id = obter_device_id()
    registro = sessao.query(Dispositivo).filter_by(device_id=device_id).first()
    if registro is None:
        registro = Dispositivo(device_id=device_id, nome=nome or device_id)
        sessao.add(registro)
    registro.ultima_sincronizacao = _dt.now()


def init_db() -> None:
    """Cria todas as tabelas definidas em models.py no banco local (e na nuvem, se disponível)."""
    from models import Base  # import local evita import circular
    Base.metadata.create_all(bind=engine_local)
    _migrar_colunas_novas(engine_local)
    _migrar_colunas_sync_mixin(engine_local)
    if engine_cloud is not None:
        # Só roda no modo dev/interno (DATABASE_URL). No modo REST
        # (distribuído), o schema da nuvem é versionado em supabase/*.sql
        # e aplicado manualmente — o .exe do cliente não tem privilégio
        # de DDL (nem conexão direta) para alterar o schema.
        try:
            Base.metadata.create_all(bind=engine_cloud)
            _migrar_colunas_novas(engine_cloud)
            _migrar_colunas_sync_mixin(engine_cloud)
        except Exception:
            pass
