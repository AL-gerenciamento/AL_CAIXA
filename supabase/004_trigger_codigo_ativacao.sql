-- Gera o código de ativação sozinho assim que uma empresa nova é
-- inserida em `empresas` — acaba com o passo manual de rodar
-- provisionar_empresa.py. O aviso por e-mail é disparado à parte, por uma
-- Database Webhook (configurada no painel) na tabela codigos_ativacao,
-- ver supabase/functions/notificar-ativacao/index.ts.

create or replace function gerar_codigo_ativacao()
returns text
language plpgsql
as $$
declare
  alfabeto text := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; -- sem 0/O/1/I
  resultado text := '';
  i int;
begin
  for i in 1..8 loop
    if i = 5 then
      resultado := resultado || '-';
    end if;
    resultado := resultado || substr(alfabeto, floor(random() * length(alfabeto) + 1)::int, 1);
  end loop;
  return resultado;
end;
$$;

create or replace function trg_empresas_gerar_codigo_ativacao()
returns trigger
language plpgsql
security definer
as $$
begin
  insert into codigos_ativacao (codigo, empresa_id)
  values (gerar_codigo_ativacao(), new.id);
  return new;
end;
$$;

drop trigger if exists on_empresa_inserida_gerar_codigo on empresas;
create trigger on_empresa_inserida_gerar_codigo
  after insert on empresas
  for each row
  execute function trg_empresas_gerar_codigo_ativacao();
