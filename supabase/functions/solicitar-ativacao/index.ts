// supabase/functions/solicitar-ativacao/index.ts
//
// Chamada automaticamente pelo próprio app (controllers/empresa_controller.py)
// assim que uma empresa nova é cadastrada localmente. Cria a mesma empresa
// na nuvem (usando o mesmo `uuid` gerado localmente, pra sync casar os
// registros depois), o que dispara os triggers já existentes:
//   - trg_empresas_gerar_codigo_ativacao (004): gera o código
//   - trg_codigos_ativacao_notificar (005): manda o e-mail pro super admin
// O cliente NUNCA recebe o código aqui — só o super admin, por e-mail, que
// decide repassar (ou não) pro cliente.
//
// Só usa a anon key (embutida no .exe), nunca a service_role no cliente.
// A criação em si usa service_role internamente, só dentro da function.
//
// Deploy: supabase functions deploy solicitar-ativacao --no-verify-jwt

import { createClient } from "npm:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
  auth: { autoRefreshToken: false, persistSession: false },
});

function jsonResponse(corpo: Record<string, unknown>, status: number): Response {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// Campos aceitos, espelhando EmpresaController.cadastrar() do app.
const CAMPOS_PERMITIDOS = [
  "uuid", "nome", "sigla", "tipo_pessoa",
  "nome_completo", "cpf", "data_nascimento",
  "razao_social", "nome_fantasia", "cnpj",
  "device_id",
] as const;

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return jsonResponse({ erro: "method_not_allowed" }, 405);
  }

  let corpo: Record<string, unknown>;
  try {
    corpo = await req.json();
  } catch {
    return jsonResponse({ erro: "corpo_invalido" }, 400);
  }

  if (!corpo.uuid || !corpo.nome || !corpo.sigla || !corpo.tipo_pessoa) {
    return jsonResponse({ erro: "campos_obrigatorios_ausentes" }, 400);
  }

  // Idempotente: se essa instalação já pediu ativação antes (reenvio,
  // reinício do app), não duplica a empresa nem gera um código novo.
  const { data: existente } = await admin
    .from("empresas")
    .select("id")
    .eq("uuid", corpo.uuid)
    .maybeSingle();

  if (existente) {
    return jsonResponse({ ok: true, ja_existia: true }, 200);
  }

  const dados: Record<string, unknown> = {
    criado_em: new Date().toISOString(),
    atualizado_em: new Date().toISOString(),
    deletado: false,
    sync_version: 1,
  };
  for (const campo of CAMPOS_PERMITIDOS) {
    if (corpo[campo] !== undefined && corpo[campo] !== null) {
      dados[campo] = corpo[campo];
    }
  }

  const { error: erroInsercao } = await admin.from("empresas").insert(dados);
  if (erroInsercao) {
    return jsonResponse({ erro: "falha_ao_registrar", detalhe: erroInsercao.message }, 500);
  }

  return jsonResponse({ ok: true, ja_existia: false }, 200);
});
