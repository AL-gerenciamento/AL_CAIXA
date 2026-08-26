// supabase/functions/criar-usuario/index.ts
//
// Cria um sub-usuário a partir do app Android. Espelha
// UsuarioController.criar_usuario do desktop, mas gera o hash bcrypt no
// servidor (o app não deve manipular hash de senha). Requer JWT válido
// (verify_jwt=true, verificado pelo gateway) e usa o claim empresa_id
// do payload para isolar a criação.
//
// Deploy: supabase functions deploy criar-usuario

import { createClient } from "npm:@supabase/supabase-js@2";
import * as bcrypt from "npm:bcryptjs@2";

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

// O gateway do Supabase (verify_jwt=true) já validou a assinatura antes
// de a requisição chegar aqui; só precisamos ler o claim empresa_id do
// payload, sem depender de nenhuma lib externa de JWT.
function empresaIdDoToken(token: string): number | null {
  const partes = token.split(".");
  if (partes.length !== 3) return null;
  try {
    const payloadBase64 = partes[1].replace(/-/g, "+").replace(/_/g, "/");
    const payloadJson = atob(payloadBase64.padEnd(payloadBase64.length + (4 - (payloadBase64.length % 4)) % 4, "="));
    const payload = JSON.parse(payloadJson);
    const empresaId = Number(payload?.empresa_id);
    return empresaId || null;
  } catch {
    return null;
  }
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return jsonResponse({ erro: "method_not_allowed" }, 405);
  }

  const authHeader = req.headers.get("Authorization") ?? "";
  const token = authHeader.replace(/^Bearer\s+/i, "");
  const empresaId = token ? empresaIdDoToken(token) : null;
  if (!empresaId) {
    return jsonResponse({ erro: "token_invalido" }, 401);
  }

  let nome: string, login: string, email: string, senha: string, permissao: string;
  try {
    const corpo = await req.json();
    nome = String(corpo?.nome ?? "").trim();
    login = String(corpo?.login ?? "").trim();
    email = String(corpo?.email ?? "").trim().toLowerCase();
    senha = String(corpo?.senha ?? "");
    permissao = String(corpo?.permissao ?? "USUARIO");
  } catch {
    return jsonResponse({ erro: "corpo_invalido" }, 400);
  }
  if (!nome || !login || !email || senha.length < 6) {
    return jsonResponse({ erro: "campos_invalidos" }, 400);
  }

  const { data: loginExistente } = await admin
    .from("usuarios")
    .select("id")
    .eq("empresa_id", empresaId)
    .ilike("login", login)
    .maybeSingle();
  if (loginExistente) {
    return jsonResponse({ erro: "login_em_uso" }, 409);
  }
  const { data: emailExistente } = await admin
    .from("usuarios")
    .select("id")
    .eq("email", email)
    .maybeSingle();
  if (emailExistente) {
    return jsonResponse({ erro: "email_em_uso" }, 409);
  }

  const senhaHash = bcrypt.hashSync(senha, 10);

  const { data: novo, error } = await admin
    .from("usuarios")
    .insert({
      empresa_id: empresaId,
      nome,
      login,
      email,
      senha_hash: senhaHash,
      permissao,
      ativo: true,
      email_verificado: true,
    })
    .select("id, nome, login, email, permissao")
    .single();

  if (error || !novo) {
    return jsonResponse({ erro: "falha_ao_criar" }, 500);
  }

  return jsonResponse({ usuario: novo }, 200);
});
