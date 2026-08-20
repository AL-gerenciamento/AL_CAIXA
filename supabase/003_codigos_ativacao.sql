-- Fase 3 do plano de segurança: ativação automática por código curto
-- (ver 002_jwt_empresa_id.md e functions/ativar-empresa/index.ts).
-- Substitui o fluxo anterior de gerar e repassar e-mail/senha técnicos
-- na mão (supabase/provisionar_empresa.py) por um código que o cliente
-- digita uma vez no app; a Edge Function cria/renova a credencial
-- técnica da empresa sozinha.

create table if not exists codigos_ativacao (
  codigo text primary key,
  empresa_id integer not null references empresas(id) on delete cascade,
  auth_user_id uuid,
  criado_em timestamptz not null default now(),
  expira_em timestamptz,
  revogado boolean not null default false
);

alter table codigos_ativacao enable row level security;

-- Sem policy nenhuma para anon/authenticated de propósito: só a
-- service_role (usada pela Edge Function, nunca pelo .exe) acessa esta
-- tabela. RLS sem policy = ninguém além de service_role lê/escreve,
-- então um código não pode ser listado/adivinhado via PostgREST.
