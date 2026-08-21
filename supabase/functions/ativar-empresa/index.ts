// supabase/functions/ativar-empresa/index.ts
//
// Recebe o código de ativação gerado pelo super admin
// (supabase/provisionar_empresa.py) e devolve um access_token/refresh_token
// já escopados por empresa (claim empresa_id, ver 002_jwt_empresa_id.md).
//
// A SUPABASE_SERVICE_ROLE_KEY só existe aqui (secret da function no painel
// Supabase), nunca no .exe distribuído — mesmo modelo de confiança do
// restante do projeto: o cliente nunca vê e-mail/senha técnicos, só o
// código curto de uma vez.
//
// Deploy: supabase functions deploy ativar-empresa --no-verify-jwt
// (--no-verify-jwt é necessário porque esta é a PRIMEIRA autenticação da
// instalação — ainda não existe um JWT de usuário nesse momento).

import { createClient } from "npm:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;

const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
  auth: { autoRefreshToken: false, persistSession: false },
});

function gerarSenha(): string {
  // Senha aleatória forte, usada só nesta invocação (nunca persistida em
  // texto puro — nem aqui, nem no app do cliente, que guarda somente o
  // refresh_token cifrado por device_id).
  return crypto.randomUUID() + crypto.randomUUID();
}

function jsonResponse(corpo: Record<string, unknown>, status: number): Response {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return jsonResponse({ erro: "method_not_allowed" }, 405);
  }

  let codigo: string;
  try {
    const corpo = await req.json();
    codigo = String(corpo?.codigo ?? "").trim().toUpperCase();
  } catch {
    return jsonResponse({ erro: "corpo_invalido" }, 400);
  }
  if (!codigo) {
    return jsonResponse({ erro: "codigo_obrigatorio" }, 400);
  }

  const { data: linha, error: erroConsulta } = await admin
    .from("codigos_ativacao")
    .select("codigo, empresa_id, auth_user_id, revogado, expira_em")
    .eq("codigo", codigo)
    .maybeSingle();

  if (erroConsulta || !linha) {
    return jsonResponse({ erro: "codigo_invalido" }, 404);
  }
  if (linha.revogado) {
    return jsonResponse({ erro: "codigo_revogado" }, 403);
  }
  if (linha.expira_em && new Date(linha.expira_em as string) < new Date()) {
    return jsonResponse({ erro: "codigo_expirado" }, 403);
  }

  const email = `empresa-${linha.empresa_id}@sync.local`;
  const senha = gerarSenha();
  let authUserId = linha.auth_user_id as string | null;

  // Se a linha não tem auth_user_id salvo, tenta achar um usuário técnico
  // já existente com esse e-mail (caso de linha órfã: usuário foi criado
  // numa tentativa anterior mas o update em codigos_ativacao não foi
  // persistido). Evita cair num createUser fadado a falhar com
  // email_exists.
  if (!authUserId) {
    const { data: listaUsuarios, error: erroBusca } = await admin.auth.admin.listUsers();
    if (!erroBusca) {
      const existente = listaUsuarios.users.find((u) => u.email === email);
      if (existente) {
        authUserId = existente.id;
        await admin.from("codigos_ativacao").update({ auth_user_id: authUserId }).eq("codigo", codigo);
      }
    }
  }

  if (authUserId) {
    const { error: erroSenha } = await admin.auth.admin.updateUserById(authUserId, { password: senha });
    if (erroSenha) {
      return jsonResponse({ erro: "falha_ao_renovar_credencial" }, 500);
    }
  } else {
    const { data: criado, error: erroCriar } = await admin.auth.admin.createUser({
      email,
      password: senha,
      email_confirm: true,
      app_metadata: { empresa_id: linha.empresa_id },
    });
    if (erroCriar || !criado?.user) {
      // Corrida: usuário foi criado entre a checagem acima e este ponto.
      // Busca de novo e tenta atualizar a senha em vez de falhar.
      if (erroCriar?.code === "email_exists") {
        const { data: listaUsuarios2 } = await admin.auth.admin.listUsers();
        const existente2 = listaUsuarios2?.users.find((u) => u.email === email);
        if (existente2) {
          authUserId = existente2.id;
          await admin.from("codigos_ativacao").update({ auth_user_id: authUserId }).eq("codigo", codigo);
          const { error: erroSenha2 } = await admin.auth.admin.updateUserById(authUserId, { password: senha });
          if (erroSenha2) {
            return jsonResponse({ erro: "falha_ao_renovar_credencial" }, 500);
          }
        } else {
          return jsonResponse({ erro: "falha_ao_criar_credencial" }, 500);
        }
      } else {
        return jsonResponse({ erro: "falha_ao_criar_credencial" }, 500);
      }
    } else {
      authUserId = criado.user.id;
      await admin.from("codigos_ativacao").update({ auth_user_id: authUserId }).eq("codigo", codigo);
    }
  }

  const respostaLogin = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { apikey: ANON_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: senha }),
  });
  if (respostaLogin.status !== 200) {
    return jsonResponse({ erro: "falha_ao_autenticar" }, 500);
  }
  const sessao = await respostaLogin.json();

  return jsonResponse(
    {
      access_token: sessao.access_token,
      refresh_token: sessao.refresh_token,
      empresa_id: linha.empresa_id,
    },
    200,
  );
});
