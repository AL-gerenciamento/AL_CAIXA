# Fase 2 — JWT escopado por empresa

Objetivo: cada instalação (`.exe`) autentica com um JWT que carrega o
claim `empresa_id`, usado pelas policies de RLS (`001_rls_isolamento_empresa.sql`).

## Abordagem: Supabase Auth + Custom Access Token Hook

1. **Um usuário técnico do Supabase Auth por empresa**, criado no
   primeiro cadastro/ativação (não é login de pessoa, é a credencial da
   instalação): `empresa_<id>@sync.local` com senha aleatória forte,
   salva só no `device_id`/local da instalação (nunca em texto puro no
   `.exe` distribuído — grava cifrada com `crypto_local.py`, mesmo padrão
   já usado pro e-mail).
   - Ao criar, gravar `app_metadata.empresa_id = <id da empresa>` (campo
     que só admin/service_role altera — o usuário final não consegue
     forjar via signup, diferente de `user_metadata`).

2. **Custom Access Token Hook** (Authentication > Hooks, no painel
   Supabase): função Postgres que injeta `empresa_id` no JWT a partir do
   `app_metadata` do usuário, executada pelo Supabase a cada emissão de
   token:

   ```sql
   create or replace function public.hook_empresa_id_no_jwt(event jsonb)
   returns jsonb
   language plpgsql
   as $$
   declare
     claims jsonb;
     empresa_id_usuario int;
   begin
     empresa_id_usuario := (event->'user'->'app_metadata'->>'empresa_id')::int;
     claims := event->'claims';
     if empresa_id_usuario is not null then
       claims := jsonb_set(claims, '{empresa_id}', to_jsonb(empresa_id_usuario));
     end if;
     event := jsonb_set(event, '{claims}', claims);
     return event;
   end;
   $$;

   grant execute on function public.hook_empresa_id_no_jwt to supabase_auth_admin;
   ```

   Depois, em Authentication > Hooks, selecionar essa função como
   "Customize Access Token (JWT) Claims hook".

3. **Login do `.exe`**: em vez de abrir conexão Postgres direta, chama
   `POST {SUPABASE_URL}/auth/v1/token?grant_type=password` com o
   e-mail/senha técnicos da instalação, recebe `access_token` (JWT, já
   com `empresa_id`) e `refresh_token`. Guarda os dois cifrados por
   `device_id`; renova via `grant_type=refresh_token` quando expirar
   (padrão 1h).

4. **super_admin** (sem empresa): usuário técnico próprio com
   `app_metadata.empresa_id` ausente — hook não injeta o claim, RLS
   normal barra tudo. Acesso irrestrito do painel super admin usa a
   `service_role key` do Supabase (nunca embutida no `.exe` de cliente,
   só no `admin_panel/app.py`, que roda em servidor/máquina controlada,
   nunca distribuído).

## Variáveis de ambiente resultantes (ver `.env.example`)

```
SUPABASE_URL=https://<projeto>.supabase.co
SUPABASE_ANON_KEY=<anon key, pública, vai no .exe>
```

`SUPABASE_JWT` não é uma env fixa — é obtido em runtime pelo login
(passo 3) e cifrado localmente por `device_id`, igual à senha de SMTP.
Nunca é uma "senha mestra": revogar uma instalação = desabilitar o
usuário técnico dela no Supabase Auth, sem afetar as demais.
