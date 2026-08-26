// supabase/functions/login-usuario/index.ts
//
// Login de usuário individual para o app Android (mobile), que não tem
// SQLite local. Valida login/senha contra a tabela `usuarios` (bcrypt,
// mesmo hash do desktop) e devolve o JWT técnico da empresa (mesmo
// usado pelo sync do desktop, RLS por empresa_id) + dados do usuário
// autenticado (id, nome, permissao) para o app aplicar as regras de
// tela localmente.
//
// Reaproveita o padrão de ativar-empresa: gira a senha do usuário
// técnico `empresa-{id}@sync.local` a cada login e autentica com ela.
// O app Android nunca vê essa credencial técnica, só o access_token
// final.
//
// Deploy: supabase functions deploy login-usuario --no-verify-jwt

import { createClient } from "npm:@supabase/supabase-js@2";
import * as bcrypt from "npm:bcryptjs@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;

const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
  auth: { autoRefreshToken: false, persistSession: false },
});

function gerarSenha(): string {
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

  let sigla: string, login: string, senha: string;
  try {
    const corpo = await req.json();
    sigla = String(corpo?.sigla ?? "").trim();
    login = String(corpo?.login ?? "").trim();
    senha = String(corpo?.senha ?? "");
  } catch {
    return jsonResponse({ erro: "corpo_invalido" }, 400);
  }
  if (!sigla || !login || !senha) {
    return jsonResponse({ erro: "campos_obrigatorios" }, 400);
  }

  const { data: empresa, error: erroEmpresa } = await admin
    .from("empresas")
    .select("id, deletado")
    .ilike("sigla", sigla)
    .maybeSingle();
  if (erroEmpresa || !empresa || empresa.deletado) {
    return jsonResponse({ erro: "credenciais_invalidas" }, 401);
  }

  const { data: usuario, error: erroUsuario } = await admin
    .from("usuarios")
    .select("id, nome, login, senha_hash, permissao, ativo, bloqueado, motivo_bloqueio, email_verificado, deletado")
    .eq("empresa_id", empresa.id)
    .ilike("login", login)
    .maybeSingle();
  if (erroUsuario || !usuario || usuario.deletado || !usuario.ativo) {
    return jsonResponse({ erro: "credenciais_invalidas" }, 401);
  }
  if (!bcrypt.compareSync(senha, usuario.senha_hash)) {
    return jsonResponse({ erro: "credenciais_invalidas" }, 401);
  }
  if (usuario.bloqueado) {
    return jsonResponse({ erro: "conta_bloqueada", mensagem: usuario.motivo_bloqueio ?? "" }, 403);
  }
  if (!usuario.email_verificado) {
    return jsonResponse({ erro: "email_nao_verificado" }, 403);
  }

  const emailTecnico = `empresa-${empresa.id}@sync.local`;
  const senhaTecnica = gerarSenha();

  const { data: listaUsuarios, error: erroBusca } = await admin.auth.admin.listUsers();
  if (erroBusca) {
    return jsonResponse({ erro: "falha_infra" }, 500);
  }
  const contaTecnica = listaUsuarios.users.find((u) => u.email === emailTecnico);
  if (!contaTecnica) {
    return jsonResponse({ erro: "empresa_sem_credencial_tecnica" }, 500);
  }

  const { error: erroSenha } = await admin.auth.admin.updateUserById(contaTecnica.id, {
    password: senhaTecnica,
  });
  if (erroSenha) {
    return jsonResponse({ erro: "falha_ao_renovar_credencial" }, 500);
  }

  const respostaLogin = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { apikey: ANON_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ email: emailTecnico, password: senhaTecnica }),
  });
  if (respostaLogin.status !== 200) {
    return jsonResponse({ erro: "falha_ao_autenticar" }, 500);
  }
  const sessao = await respostaLogin.json();

  return jsonResponse(
    {
      access_token: sessao.access_token,
      refresh_token: sessao.refresh_token,
      expires_in: sessao.expires_in,
      empresa_id: empresa.id,
      usuario: {
        id: usuario.id,
        nome: usuario.nome,
        login: usuario.login,
        permissao: usuario.permissao,
      },
    },
    200,
  );
});
