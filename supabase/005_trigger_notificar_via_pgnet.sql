-- Alternativa ao Database Webhook (a UI dessa instância deu erro
-- "schema supabase_functions does not exist"). Em vez de depender da
-- feature de Webhooks, o próprio trigger chama a Edge Function
-- notificar-ativacao direto via pg_net, assim que um código novo é
-- inserido em codigos_ativacao.
--
-- Troque a URL e o X-Webhook-Token abaixo pelos valores reais do seu
-- projeto antes de rodar.

create or replace function trg_codigos_ativacao_notificar()
returns trigger
language plpgsql
security definer
as $$
declare
  v_nome_empresa text;
begin
  select nome into v_nome_empresa from empresas where id = new.empresa_id;

  perform net.http_post(
    url := 'https://wvdalleynqnbdxbtqrca.supabase.co/functions/v1/notificar-ativacao',
    headers := jsonb_build_object(
      'Content-type', 'application/json',
      'X-Webhook-Token', 'bacon1015%'
    ),
    body := jsonb_build_object(
      'record', jsonb_build_object(
        'codigo', new.codigo,
        'empresa_id', new.empresa_id,
        'nome_empresa', coalesce(v_nome_empresa, 'desconhecida')
      )
    )
  );
  return new;
end;
$$;

drop trigger if exists on_codigo_ativacao_inserido on codigos_ativacao;
create trigger on_codigo_ativacao_inserido
  after insert on codigos_ativacao
  for each row
  execute function trg_codigos_ativacao_notificar();
