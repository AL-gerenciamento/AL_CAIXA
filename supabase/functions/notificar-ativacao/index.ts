// supabase/functions/notificar-ativacao/index.ts
//
// Disparada por uma Database Webhook (Dashboard > Database > Webhooks) em
// INSERT na tabela codigos_ativacao. Manda o código pro e-mail do super
// admin — nunca pro cliente diretamente, é você quem repassa.
//
// Segurança:
// - Confere um segredo compartilhado (header X-Webhook-Token) antes de
//   fazer qualquer coisa, pra ninguém conseguir chamar essa function de
//   fora e ficar recebendo e-mails de códigos alheios.
// - Usa uma senha de app do Gmail PRÓPRIA desta function (gere uma nova em
//   myaccount.google.com/security, não reaproveite a do app AL Caixa) —
//   assim dá pra revogar uma sem afetar a outra.
//
// Secrets necessárias (supabase secrets set NOME=valor):
//   WEBHOOK_TOKEN          segredo combinado com o campo "Custom header" do webhook
//   ADMIN_EMAIL            um ou mais e-mails separados por vírgula, ex: "a@x.com,b@y.com"
//   GMAIL_USER             conta Gmail remetente
//   GMAIL_APP_PASSWORD     senha de app de 16 dígitos (só desta function)
//
// Deploy: supabase functions deploy notificar-ativacao --no-verify-jwt

import { SMTPClient } from "npm:emailjs@4";

const WEBHOOK_TOKEN = Deno.env.get("WEBHOOK_TOKEN")!;
const ADMIN_EMAILS = (Deno.env.get("ADMIN_EMAIL") ?? "")
  .split(",")
  .map((e) => e.trim())
  .filter(Boolean);
const GMAIL_USER = Deno.env.get("GMAIL_USER")!;
const GMAIL_APP_PASSWORD = Deno.env.get("GMAIL_APP_PASSWORD")!;

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("method_not_allowed", { status: 405 });
  }
  if (req.headers.get("x-webhook-token") !== WEBHOOK_TOKEN) {
    return new Response("unauthorized", { status: 401 });
  }

  let payload: Record<string, unknown>;
  try {
    payload = await req.json();
  } catch {
    return new Response("corpo_invalido", { status: 400 });
  }

  const registro = (payload.record ?? {}) as Record<string, unknown>;
  const codigo = String(registro.codigo ?? "");
  const empresaId = registro.empresa_id;
  const nomeEmpresa = String(registro.nome_empresa ?? "").trim();
  if (!codigo || empresaId === undefined) {
    return new Response("payload_sem_codigo", { status: 400 });
  }
  if (ADMIN_EMAILS.length === 0) {
    return new Response("admin_email_nao_configurado", { status: 500 });
  }

  const client = new SMTPClient({
    user: GMAIL_USER,
    password: GMAIL_APP_PASSWORD,
    host: "smtp.gmail.com",
    ssl: true,
  });

  const identificacao = nomeEmpresa ? `${nomeEmpresa} (#${empresaId})` : `empresa #${empresaId}`;

  try {
    await client.sendAsync({
      from: GMAIL_USER,
      to: ADMIN_EMAILS.join(", "),
      subject: `Novo código de ativação — ${identificacao}`,
      text:
        `Empresa: ${identificacao}\n` +
        `Código de ativação: ${codigo}\n\n` +
        `Repasse este código ao cliente. Ele digita em Configurações > ` +
        `Backup > "Ativar" no AL Caixa.`,
    });
  } catch (_erro) {
    return new Response("falha_ao_enviar_email", { status: 500 });
  }

  return new Response("ok", { status: 200 });
});
