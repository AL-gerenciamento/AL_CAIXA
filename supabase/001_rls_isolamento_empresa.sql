-- Fase 1 do plano de segurança (PROGRESSO_SEGURANCA.md, Opção B).
-- Ativa RLS e isola por empresa_id nas tabelas que possuem essa coluna
-- (direta ou via join até usuarios/vendas). Rodar no SQL Editor do
-- Supabase, uma vez, com a conta atual (superusuário/owner do schema).
--
-- Pré-requisito: o JWT emitido para cada instalação precisa conter o
-- claim "empresa_id" (ver supabase/002_jwt_empresa_id.md). super_admin
-- (sem empresa) usa um JWT com empresa_id nulo/ausente e é tratado à
-- parte (service role, fora do escopo de RLS normal).
--
-- GAP CONHECIDO: categorias, metas, despesas_fixas, avisos e
-- configuracoes_plataforma NÃO têm empresa_id (nem caminho indireto até
-- empresa) no schema atual — são compartilhadas por todos os clientes
-- hoje. RLS não isola o que o schema não sabe a quem pertence. Ficam
-- com policy "todo usuário autenticado lê/escreve" (mesmo comportamento
-- de hoje, sem regressão) até decisão de adicionar empresa_id a elas.

alter table empresas enable row level security;
alter table usuarios enable row level security;
alter table produtos enable row level security;
alter table vendas enable row level security;
alter table itens_venda enable row level security;
alter table vendas_pagamentos enable row level security;
alter table receitas enable row level security;
alter table despesas enable row level security;
alter table categorias enable row level security;
alter table despesas_fixas enable row level security;
alter table metas enable row level security;
alter table avisos enable row level security;
alter table pagamentos enable row level security;
alter table configuracoes_plataforma enable row level security;
alter table dispositivos enable row level security;
alter table sync_queue enable row level security;
alter table sync_log enable row level security;

-- Helper: empresa_id do JWT da instalação atual (null = super_admin/service).
create or replace function empresa_id_atual()
returns integer
language sql stable
as $$
  select nullif(current_setting('request.jwt.claims', true)::jsonb ->> 'empresa_id', '')::integer
$$;

-- empresas: só a própria linha.
create policy empresas_isolamento on empresas
  for all using (id = empresa_id_atual())
  with check (id = empresa_id_atual());

-- usuarios: só usuários da própria empresa.
create policy usuarios_isolamento on usuarios
  for all using (empresa_id = empresa_id_atual())
  with check (empresa_id = empresa_id_atual());

-- produtos: coluna direta.
create policy produtos_isolamento on produtos
  for all using (empresa_id = empresa_id_atual())
  with check (empresa_id = empresa_id_atual());

-- vendas: coluna direta.
create policy vendas_isolamento on vendas
  for all using (empresa_id = empresa_id_atual())
  with check (empresa_id = empresa_id_atual());

-- itens_venda / vendas_pagamentos: via venda_id -> vendas.empresa_id.
create policy itens_venda_isolamento on itens_venda
  for all using (
    venda_id in (select id from vendas where empresa_id = empresa_id_atual())
  )
  with check (
    venda_id in (select id from vendas where empresa_id = empresa_id_atual())
  );

create policy vendas_pagamentos_isolamento on vendas_pagamentos
  for all using (
    venda_id in (select id from vendas where empresa_id = empresa_id_atual())
  )
  with check (
    venda_id in (select id from vendas where empresa_id = empresa_id_atual())
  );

-- receitas / despesas: via usuario_id -> usuarios.empresa_id (nullable:
-- lançamento sem usuario_id fica inacessível via RLS até ser corrigido,
-- não há empresa pra checar).
create policy receitas_isolamento on receitas
  for all using (
    usuario_id in (select id from usuarios where empresa_id = empresa_id_atual())
  )
  with check (
    usuario_id in (select id from usuarios where empresa_id = empresa_id_atual())
  );

create policy despesas_isolamento on despesas
  for all using (
    usuario_id in (select id from usuarios where empresa_id = empresa_id_atual())
  )
  with check (
    usuario_id in (select id from usuarios where empresa_id = empresa_id_atual())
  );

-- pagamentos (mensalidade da plataforma): via conta_principal_id -> usuarios.empresa_id.
create policy pagamentos_isolamento on pagamentos
  for all using (
    conta_principal_id in (select id from usuarios where empresa_id = empresa_id_atual())
  )
  with check (
    conta_principal_id in (select id from usuarios where empresa_id = empresa_id_atual())
  );

-- dispositivos / sync_queue / sync_log: sem empresa_id hoje; qualquer
-- instalação autenticada pode ler/escrever (igual ao comportamento
-- atual). Restringir exigiria adicionar empresa_id a essas tabelas.
create policy dispositivos_autenticado on dispositivos
  for all using (auth.role() = 'authenticated') with check (auth.role() = 'authenticated');
create policy sync_queue_autenticado on sync_queue
  for all using (auth.role() = 'authenticated') with check (auth.role() = 'authenticated');
create policy sync_log_autenticado on sync_log
  for all using (auth.role() = 'authenticated') with check (auth.role() = 'authenticated');

-- categorias / despesas_fixas / metas / avisos / configuracoes_plataforma:
-- GAP acima — mantidas globais, só exige autenticação (sem regressão).
create policy categorias_autenticado on categorias
  for all using (auth.role() = 'authenticated') with check (auth.role() = 'authenticated');
create policy despesas_fixas_autenticado on despesas_fixas
  for all using (auth.role() = 'authenticated') with check (auth.role() = 'authenticated');
create policy metas_autenticado on metas
  for all using (auth.role() = 'authenticated') with check (auth.role() = 'authenticated');
create policy avisos_autenticado on avisos
  for all using (auth.role() = 'authenticated') with check (auth.role() = 'authenticated');
create policy config_plataforma_autenticado on configuracoes_plataforma
  for all using (auth.role() = 'authenticated') with check (auth.role() = 'authenticated');
