import { connect } from 'cloudflare:sockets';

function toArray(to) {
  return Array.isArray(to) ? to : [to];
}

async function sendSMTP(env, { to, subject, text, attachment }) {
  const enc = new TextEncoder();
  const dec = new TextDecoder();
  const destinatarios = toArray(to);

  const socket = connect({ hostname: 'smtp.gmail.com', port: 587 }, { secureTransport: 'starttls' });
  let writer = socket.writable.getWriter();
  let reader = socket.readable.getReader();

  async function send(w, cmd) { await w.write(enc.encode(cmd + '\r\n')); }
  async function recv(r) {
    const { value, done } = await r.read();
    if (done) throw new Error('conexao fechada');
    return dec.decode(value);
  }

  await recv(reader);
  await send(writer, 'EHLO workers.dev');
  await recv(reader);
  await send(writer, 'STARTTLS');
  await recv(reader);

  writer.releaseLock();
  reader.releaseLock();

  const tlsSocket = socket.startTls();
  writer = tlsSocket.writable.getWriter();
  reader = tlsSocket.readable.getReader();

  await send(writer, 'EHLO workers.dev');
  await recv(reader);
  await send(writer, 'AUTH LOGIN');
  await recv(reader);
  await send(writer, btoa(env.SMTP_USER));
  await recv(reader);
  await send(writer, btoa(env.SMTP_PASSWORD));
  const authResp = await recv(reader);
  if (!authResp.startsWith('235')) throw new Error('falha na autenticacao SMTP');

  await send(writer, `MAIL FROM:<${env.SMTP_USER}>`);
  await recv(reader);
  for (const dest of destinatarios) {
    await send(writer, `RCPT TO:<${dest}>`);
    await recv(reader);
  }
  await send(writer, 'DATA');
  await recv(reader);

  let msg;
  if (attachment) {
    const boundary = 'ALGERENC' + Date.now();
    msg =
      `From: AL Gerenciamento <${env.SMTP_USER}>\r\n` +
      `To: ${destinatarios.join(', ')}\r\n` +
      `Subject: ${subject}\r\n` +
      `MIME-Version: 1.0\r\n` +
      `Content-Type: multipart/mixed; boundary="${boundary}"\r\n\r\n` +
      `--${boundary}\r\n` +
      `Content-Type: text/plain; charset=utf-8\r\n\r\n${text}\r\n\r\n` +
      `--${boundary}\r\n` +
      `Content-Type: ${attachment.content_type || 'application/octet-stream'}; name="${attachment.filename}"\r\n` +
      `Content-Disposition: attachment; filename="${attachment.filename}"\r\n` +
      `Content-Transfer-Encoding: base64\r\n\r\n` +
      `${attachment.content_base64}\r\n` +
      `--${boundary}--\r\n.`;
  } else {
    msg =
      `From: AL Gerenciamento <${env.SMTP_USER}>\r\n` +
      `To: ${destinatarios.join(', ')}\r\n` +
      `Subject: ${subject}\r\n` +
      `Content-Type: text/plain; charset=utf-8\r\n\r\n${text}\r\n.`;
  }

  await send(writer, msg);
  const dataResp = await recv(reader);
  if (!dataResp.startsWith('250')) throw new Error('falha ao enviar');

  await send(writer, 'QUIT');
}

export default {
  async fetch(request, env) {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });
    if (request.headers.get('Authorization') !== `Bearer ${env.API_KEY}`) {
      return new Response('Unauthorized', { status: 401 });
    }
    let body;
    try { body = await request.json(); } catch { return new Response('JSON invalido', { status: 400 }); }
    const { to, subject, text, attachment } = body;
    if (!to || !subject || !text) return new Response('faltam campos: to, subject, text', { status: 400 });
    try {
      await sendSMTP(env, { to, subject, text, attachment });
      return Response.json({ ok: true });
    } catch (e) {
      return Response.json({ ok: false, erro: String(e) }, { status: 500 });
    }
  }
};
