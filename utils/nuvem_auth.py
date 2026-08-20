"""
utils/nuvem_auth.py
Autenticação contra o Supabase Auth (grant_type=password) para obter o
JWT escopado por empresa (claim "empresa_id" injetado via Custom Access
Token Hook, ver supabase/002_jwt_empresa_id.md) usado em toda chamada
REST à nuvem (utils/supabase_rest.py).

Não guarda a senha do usuário técnico da instalação em nenhum momento
além da chamada de login em si — só o refresh_token, cifrado por
device_id (utils/credencial_nuvem.py). O .exe nunca tem acesso à
credencial mestre do Postgres.
"""
from __future__ import annotations

import httpx

from utils import credencial_nuvem, supabase_rest
from utils.logger import registrar_erro

def _auth_url() -> str:
    return f"{supabase_rest.SUPABASE_URL}/auth/v1" if supabase_rest.SUPABASE_URL else ""


class ErroAutenticacaoNuvem(Exception):
    """Erro de autenticação/comunicação com o Supabase Auth."""
    pass


def _headers_auth() -> dict:
    return {"apikey": supabase_rest.SUPABASE_ANON_KEY, "Content-Type": "application/json"}


def _aplicar_sessao(dados: dict) -> str:
    access_token = dados.get("access_token")
    refresh_token = dados.get("refresh_token")
    if not access_token:
        raise ErroAutenticacaoNuvem("Resposta da nuvem sem access_token.")
    supabase_rest.definir_jwt_atual(access_token)
    if refresh_token:
        credencial_nuvem.salvar_refresh_token(refresh_token)
    return access_token


def autenticar_nuvem(email_tecnico: str, senha: str) -> str:
    """
    Login inicial da instalação com o usuário técnico da empresa (criado
    na ativação, não é o login de um usuário do sistema — ver
    supabase/002_jwt_empresa_id.md). Guarda o JWT em memória
    (supabase_rest) e o refresh_token cifrado em disco para as próximas
    aberturas do app não pedirem login de novo.
    """
    if not supabase_rest.SUPABASE_URL or not supabase_rest.SUPABASE_ANON_KEY:
        raise ErroAutenticacaoNuvem(
            "Nuvem não configurada (SUPABASE_URL/SUPABASE_ANON_KEY ausentes no .env)."
        )
    try:
        resposta = httpx.post(
            f"{_auth_url()}/token?grant_type=password",
            headers=_headers_auth(),
            json={"email": email_tecnico, "password": senha},
            timeout=10.0,
        )
    except httpx.RequestError:
        raise ErroAutenticacaoNuvem("Não foi possível falar com a nuvem (sem internet ou fora do ar).")

    if resposta.status_code != 200:
        try:
            mensagem = resposta.json().get("error_description", "Falha na autenticação com a nuvem.")
        except ValueError:
            mensagem = f"Falha na autenticação com a nuvem (HTTP {resposta.status_code})."
        raise ErroAutenticacaoNuvem(mensagem)

    return _aplicar_sessao(resposta.json())


def solicitar_ativacao_empresa(dados_empresa: dict) -> None:
    """
    Chamada automaticamente por EmpresaController.cadastrar() logo após
    criar a empresa localmente. Registra a mesma empresa na nuvem (Edge
    Function solicitar-ativacao) usando o `uuid` já gerado localmente —
    isso dispara os triggers que geram o código de ativação e avisam o
    super admin por e-mail. Nunca lança para o fluxo de cadastro: falha
    de rede/nuvem aqui não pode travar o cadastro local, só fica
    registrada em log_erros para diagnóstico.
    """
    if not supabase_rest.SUPABASE_URL or not supabase_rest.SUPABASE_ANON_KEY:
        registrar_erro(
            RuntimeError("SUPABASE_URL/SUPABASE_ANON_KEY ausentes no .env"),
            "solicitar_ativacao_empresa",
        )
        return
    try:
        resposta = httpx.post(
            f"{supabase_rest.SUPABASE_URL}/functions/v1/solicitar-ativacao",
            headers=_headers_auth(),
            json=dados_empresa,
            timeout=10.0,
        )
        if resposta.status_code != 200:
            registrar_erro(
                RuntimeError(f"solicitar-ativacao HTTP {resposta.status_code}: {resposta.text}"),
                "solicitar_ativacao_empresa",
            )
    except httpx.RequestError as e:
        registrar_erro(e, "solicitar_ativacao_empresa")


def ativar_com_codigo(codigo: str) -> int:
    """
    Ativação de uma instalação nova via código curto (gerado por
    supabase/provisionar_empresa.py, digitado uma vez em Configurações >
    Backup > "Ativar"). Chama a Edge Function ativar-empresa, que
    cria/renova a credencial técnica da empresa e já devolve o JWT — o
    app nunca mais lida com e-mail/senha técnicos. Devolve o empresa_id
    vinculado ao código.
    """
    if not supabase_rest.SUPABASE_URL or not supabase_rest.SUPABASE_ANON_KEY:
        raise ErroAutenticacaoNuvem(
            "Nuvem não configurada (SUPABASE_URL/SUPABASE_ANON_KEY ausentes no .env)."
        )
    try:
        resposta = httpx.post(
            f"{supabase_rest.SUPABASE_URL}/functions/v1/ativar-empresa",
            headers=_headers_auth(),
            json={"codigo": codigo.strip()},
            timeout=15.0,
        )
    except httpx.RequestError:
        raise ErroAutenticacaoNuvem("Não foi possível falar com a nuvem (sem internet ou fora do ar).")

    if resposta.status_code != 200:
        mensagens = {
            "codigo_invalido": "Código de ativação inválido.",
            "codigo_revogado": "Este código de ativação foi revogado.",
            "codigo_expirado": "Este código de ativação expirou.",
            "codigo_obrigatorio": "Informe o código de ativação.",
        }
        try:
            chave_erro = resposta.json().get("erro", "")
        except ValueError:
            chave_erro = ""
        raise ErroAutenticacaoNuvem(
            mensagens.get(chave_erro, "Falha ao ativar (código inválido ou serviço indisponível).")
        )

    dados = resposta.json()
    _aplicar_sessao(dados)
    return dados.get("empresa_id")


def renovar_sessao_nuvem() -> str | None:
    """
    Tenta usar o refresh_token salvo desta instalação para obter um novo
    access_token sem pedir login de novo. Chamado no início do app e
    quando um JWT expirado é detectado. Devolve None se não havia sessão
    salva ou se o refresh também falhou (nesse caso é preciso logar de
    novo com autenticar_nuvem).
    """
    refresh_token = credencial_nuvem.carregar_refresh_token()
    if not refresh_token:
        registrar_erro(
            RuntimeError("Nenhum refresh_token salvo nesta instalação."),
            "renovar_sessao_nuvem",
        )
        return None
    if not supabase_rest.SUPABASE_URL:
        registrar_erro(
            RuntimeError("SUPABASE_URL ausente no .env ao tentar renovar sessão."),
            "renovar_sessao_nuvem",
        )
        return None
    try:
        resposta = httpx.post(
            f"{_auth_url()}/token?grant_type=refresh_token",
            headers=_headers_auth(),
            json={"refresh_token": refresh_token},
            timeout=10.0,
        )
    except httpx.RequestError as e:
        registrar_erro(e, "renovar_sessao_nuvem")
        return None
    if resposta.status_code != 200:
        registrar_erro(
            RuntimeError(f"refresh_token recusado HTTP {resposta.status_code}: {resposta.text}"),
            "renovar_sessao_nuvem",
        )
        credencial_nuvem.limpar_refresh_token()
        return None
    return _aplicar_sessao(resposta.json())


def obter_token_nuvem() -> str | None:
    """Token JWT da sessão atual (None se nunca autenticou ou expirou)."""
    return supabase_rest._jwt_atual


def limpar_token_nuvem() -> None:
    supabase_rest.definir_jwt_atual(None)
    credencial_nuvem.limpar_refresh_token()
