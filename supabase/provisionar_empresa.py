"""
supabase/provisionar_empresa.py
Script de uso manual pelo SUPER ADMIN (nunca roda na máquina do cliente,
nunca entra no build do .exe — mesmo padrão de zerar_nuvem.py e
limpar_duplicados_super_admin.py). Cria o usuário técnico do Supabase
Auth de uma empresa (claim empresa_id no JWT, ver 002_jwt_empresa_id.md)
e imprime a credencial UMA vez para você repassar ao cliente, que digita
em Configurações > Backup > "Conectar" na primeira abertura.

Requer a service_role key do Supabase (só nesta máquina, nunca no .exe):
    SUPABASE_URL=https://SEU-PROJETO.supabase.co
    SUPABASE_SERVICE_ROLE_KEY=...

Uso:
    python supabase/provisionar_empresa.py --empresa-id 3 --sigla LOJAX
"""
from __future__ import annotations

import argparse
import os
import secrets

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _headers() -> dict:
    return {
        "apikey": SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def provisionar(empresa_id: int, sigla: str) -> tuple[str, str]:
    if not SUPABASE_URL or not SERVICE_ROLE_KEY:
        raise SystemExit(
            "Configure SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no .env desta máquina "
            "(painel Supabase > Project Settings > API)."
        )
    email = f"empresa-{empresa_id}-{sigla.lower()}@sync.local"
    senha = secrets.token_urlsafe(24)

    resposta = httpx.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=_headers(),
        json={
            "email": email,
            "password": senha,
            "email_confirm": True,
            "app_metadata": {"empresa_id": empresa_id},
        },
        timeout=15,
    )
    if resposta.status_code == 422 and "already been registered" in resposta.text:
        raise SystemExit(
            f"Já existe um usuário técnico para {email}. Se precisar trocar a senha, "
            "use o painel Supabase (Authentication > Users) em vez de recriar."
        )
    resposta.raise_for_status()
    return email, senha


def main() -> None:
    parser = argparse.ArgumentParser(description="Provisiona acesso técnico de uma empresa à nuvem.")
    parser.add_argument("--empresa-id", type=int, required=True)
    parser.add_argument("--sigla", type=str, required=True)
    args = parser.parse_args()

    email, senha = provisionar(args.empresa_id, args.sigla)
    print("\nCredencial técnica gerada (repasse ao cliente, não guarde em texto puro):")
    print(f"  e-mail: {email}")
    print(f"  senha:  {senha}")
    print(
        "\nO cliente digita isso uma única vez em Configurações > Backup > "
        "\"Conectar\" na instalação dele; depois disso o app guarda só o "
        "refresh_token cifrado e não pede de novo."
    )


if __name__ == "__main__":
    main()
