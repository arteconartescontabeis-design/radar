// =====================================================================
// RADAR ARTECON — Edge Function "radar-meta-webhook" (v0.35.2) — MÓDULO RESPOSTAS AUTOMÁTICAS
//
// A Meta chama esta função a cada comentário novo nas publicações da Artecon (Instagram e página do Facebook). A função confere a
// assinatura da chamada, pergunta ao banco o que fazer (radar_respostas_receber: o banco decide — gatilho ativo, palavra-chave,
// própria conta, repetido, pausado, limite por hora) e, quando o banco manda responder, envia a resposta pública ao comentário e a
// mensagem privada com o link do material. O resultado volta para o banco (radar_respostas_resultado). O que passar do limite por
// hora fica pendente e sai pela agenda (sql/radar-respostas-agenda.sql), que chama a ação "pendentes" a cada 5 minutos — só quando
// há o que mandar.
//
// Quem pode chamar ("Verify JWT" DESLIGADO no deploy: a Meta não manda JWT; a função confere sozinha):
//   * a Meta: GET com hub.verify_token (a verificação do webhook) e POST com o cabeçalho X-Hub-Signature-256 (o HMAC SHA-256 do
//     corpo com o META_APP_SECRET; chamada sem assinatura válida é recusada e nada é processado);
//   * o banco (a agenda, via net.http_post) ou um script, com o cabeçalho x-radar-chave — a chave fica no Vault e quem confere é
//     public.radar_respostas_conferir (criada pelo sql/radar-respostas-agenda.sql), que só a chave interna executa;
//   * o administrador logado (Authorization: Bearer <sessão>), para o "Testar conexão" e os pendentes pelo botão.
//
// Ações (POST com JSON {"acao": …}, sem o cabeçalho da Meta):
//   pendentes     (a chave ou o administrador) → envia os pendentes que já podem sair (o banco lista, dentro do limite por hora)
//   diagnostico   (só o administrador)         → confere os segredos e lê a própria página pela Graph API (GET /me, com o
//                                                Instagram ligado); grava as contas (radar_respostas_conta_salvar) e inscreve o
//                                                app na própria página (POST /{página}/subscribed_apps, campo "feed" — sem a
//                                                inscrição a Meta não entrega os avisos de comentário) — é o "Testar conexão"
//   agenda_teste  (a chave ou o administrador) → {ok, versao}, sem tocar na Meta (o teste do fim do sql/radar-respostas-agenda.sql)
//
// Como responde (Graph API, api oficial; nunca curte, segue nem publica post):
//   * resposta pública: POST /{id-do-comentário}/replies (Instagram) ou POST /{id-do-comentário}/comments (Facebook);
//   * mensagem privada: POST /{id-da-página}/messages com recipient {comment_id} — a "Private Reply" da Meta: vale UMA vez por
//     comentário e até 7 DIAS depois dele (o banco já descarta o que passar disso). A página vem de radar_respostas_pagina()
//     (gravada pelo "Testar conexão"); sem ela, a resposta pública sai e a privada fica anotada como pendência no registro.
//   * a resposta pública que deu certo não sai de novo: se só a privada falhar, o registro fica "enviado" com privada_ok = false
//     e o erro anotado (reenviar de novo faria a resposta pública em dobro).
//
// AGUARDANDO A META: os avisos de comentário (webhook "comments" do Instagram e "feed" da página) só chegam depois que a Meta
// aprovar o acesso avançado do aplicativo (Análise do App). Até lá, o GET de verificação e as ações já funcionam.
//
// Privacidade: o registro (log) desta função só tem contagens e códigos — nunca nome, texto de comentário ou token.
//
// Segredos (Supabase → Edge Functions → Secrets):
//   META_APP_SECRET    o segredo do aplicativo da Meta (valida a assinatura X-Hub-Signature-256)
//   META_VERIFY_TOKEN  o token de verificação do webhook (você inventa; o mesmo vai no painel da Meta)
//   META_PAGE_TOKEN    o token de longa duração da PÁGINA do Facebook — ou o token do USUÁRIO DE SISTEMA do Gerenciador de
//                      Negócios: a função percebe e troca sozinha pelo da página (GET /me/accounts), guardando só na memória.
//                      Espaços e quebras de linha de colagem são ignorados. Permissões de comentários e mensagens aprovadas pela Meta.
//   META_GRAPH_URL     opcional; padrão https://graph.facebook.com/v23.0
// SUPABASE_URL, a chave pública (SUPABASE_PUBLISHABLE_KEYS ou SUPABASE_ANON_KEY) e a chave interna (SUPABASE_SECRET_KEYS ou
// SUPABASE_SERVICE_ROLE_KEY) o Supabase já fornece.
// =====================================================================

const VERSAO = "0.35.2";
const env = (nome: string, padrao = "") => Deno.env.get(nome) ?? padrao;

const SUPABASE_URL = env("SUPABASE_URL").replace(/\/+$/, "");
function chavePublica(): string {
  try {
    const k = JSON.parse(env("SUPABASE_PUBLISHABLE_KEYS") || "{}");
    const v = k?.default ?? Object.values(k ?? {}).find((x) => typeof x === "string" && x);
    if (typeof v === "string" && v.trim()) return v.trim();
  } catch { /* sem a lista nova: fica a anon */ }
  return env("SUPABASE_ANON_KEY").trim();
}
const ANON = chavePublica();
const GRAPH = env("META_GRAPH_URL", "https://graph.facebook.com/v23.0").replace(/\/+$/, "");
const PRAZO_META_MS = Number(env("RADAR_RESPOSTAS_PRAZO_MS", "15000"));          // só os testes trocam
const MAX_EVENTOS = 50;                                                          // comentários por chamada da Meta (sobra vira pendente? não: a Meta manda poucos por vez)
const PENDENTES_POR_VEZ = 25;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

class Erro extends Error {
  status: number;
  constructor(status: number, mensagem: string) { super(mensagem); this.status = status; }
}
const responder = (status: number, corpo: unknown) =>
  new Response(JSON.stringify(corpo), { status, headers: { ...CORS, "Content-Type": "application/json" } });

// ------------------------------------------------------------------ banco
async function banco(quem: string | Record<string, string>, metodo: string, caminho: string, corpo?: unknown, tempo = 30_000): Promise<any> {
  const r = await fetch(`${SUPABASE_URL}/rest/v1/${caminho}`, {
    method: metodo,
    headers: { ...(typeof quem === "string" ? { apikey: ANON || quem, Authorization: quem } : quem), "Content-Type": "application/json" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
    signal: AbortSignal.timeout(tempo),
  });
  const texto = await r.text();
  let dados: any = null;
  try { dados = texto ? JSON.parse(texto) : null; } catch { dados = { message: texto }; }
  if (!r.ok) {
    const m = String(dados?.message ?? "");
    const radar = /RADAR\d+:\s*(.*)/s.exec(m);
    throw new Erro(r.status === 401 ? 401 : r.status === 403 ? 403 : 400, radar ? radar[1] : (m || `Erro ${r.status} no banco`).slice(0, 300));
  }
  return dados;
}
function chaveInterna(): string {
  try {
    const k = JSON.parse(env("SUPABASE_SECRET_KEYS") || "{}");
    const v = k?.default ?? Object.values(k ?? {}).find((x) => typeof x === "string" && x);
    if (typeof v === "string" && v.trim()) return v.trim();
  } catch { /* sem a lista nova: fica a antiga */ }
  return env("SUPABASE_SERVICE_ROLE_KEY").trim();
}
const ehJwt = (k: string) => /^[\w-]+\.[\w-]+\.[\w-]+$/.test(k);
const comoServico = (): Record<string, string> => {
  const k = chaveInterna();
  if (!k) throw new Erro(503, "A função está sem a chave interna do Supabase (SUPABASE_SECRET_KEYS ou SUPABASE_SERVICE_ROLE_KEY).");
  return ehJwt(k) ? { apikey: k, Authorization: "Bearer " + k } : { apikey: k };
};

/** Quem chamou uma AÇÃO: o banco (a agenda) com a chave do Vault, ou um usuário logado. A recusa é sempre a mesma frase. */
async function autorizar(req: Request): Promise<"chave" | "admin"> {
  const chave = (req.headers.get("x-radar-chave") ?? "").trim();
  if (chave) {
    let ok = false;
    if (chave.length >= 32 && chave.length <= 200) {
      try { ok = (await banco(comoServico(), "POST", "rpc/radar_respostas_conferir", { p_chave: chave }, 10_000)) === true; }
      catch (e) {
        if (e instanceof Erro && e.status === 503) throw e;
        console.log(`radar-meta-webhook: conferência da chave falhou (${e instanceof Erro ? e.status : "sem resposta do banco"})`);
      }
    }
    if (ok) return "chave";
    throw new Erro(401, "Chave não confere.");
  }
  const token = req.headers.get("Authorization") ?? "";
  if (!/^Bearer\s+\S+/.test(token)) throw new Erro(401, "Sessão não informada.");
  let papel: unknown = null;
  try { papel = await banco(token, "POST", "rpc/radar_papel", {}, 10_000); }
  catch (e) {
    if (e instanceof Erro && (e.status === 401 || e.status === 403)) throw new Erro(401, "Sessão inválida ou vencida. Entre de novo.");
    throw e;
  }
  if (papel !== "admin") throw new Erro(403, "Só o administrador mexe nas respostas automáticas por aqui.");
  return "admin";
}

// ------------------------------------------------------------------ assinatura da Meta
const te = new TextEncoder();
async function assinaturaConfere(corpo: Uint8Array, cabecalho: string): Promise<boolean> {
  const segredo = env("META_APP_SECRET").trim();
  if (!segredo) return false;
  const m = /^sha256=([0-9a-f]{64})$/.exec((cabecalho ?? "").trim());
  if (!m) return false;
  const chave = await crypto.subtle.importKey("raw", te.encode(segredo), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", chave, corpo as BufferSource));
  const esperada = Array.from(mac).map((b) => b.toString(16).padStart(2, "0")).join("");
  // comparação em tempo constante (os dois têm 64 caracteres)
  let dif = 0;
  for (let i = 0; i < 64; i++) dif |= esperada.charCodeAt(i) ^ m[1].charCodeAt(i);
  return dif === 0;
}

// ------------------------------------------------------------------ Meta (Graph API)
const faltamSegredos = () => ["META_APP_SECRET", "META_VERIFY_TOKEN", "META_PAGE_TOKEN"].filter((n) => !env(n).trim());
/** A mensagem da Meta sem nada sensível: nunca token, nome ou texto. */
function limparErro(x: unknown): string {
  const m = typeof x === "string" ? x : x instanceof Error ? (x.name === "TimeoutError" ? "a Meta não respondeu a tempo" : x.message) : String(x ?? "");
  return m.replace(/access_token=[^&\s"']+/gi, "access_token=…").replace(/Bearer\s+\S+/gi, "Bearer …").slice(0, 200);
}

// O segredo META_PAGE_TOKEN aceita o token da PÁGINA ou o do USUÁRIO DE SISTEMA: com o do usuário, /me/accounts lista as páginas
// e a função usa o token da primeira — a troca manual deixou de existir. O token vai SÓ no cabeçalho (como nas outras chamadas) e
// o trocado fica só na memória da instância; a Meta fora do ar na troca não é gravada (a próxima chamada tenta de novo).
let tokenPaginaMemo = "";
let trocaSemPagina = false;        // o token é de usuário, a Meta respondeu, mas nenhuma página está atribuída a ele
async function tokenPagina(): Promise<string> {
  if (tokenPaginaMemo) return tokenPaginaMemo;
  const bruto = env("META_PAGE_TOKEN").replace(/\s+/g, "").replace(/^["']+|["']+$/g, "");
  if (!bruto) return "";
  try {
    const r = await fetch(`${GRAPH}/me/accounts?fields=access_token&limit=25`,
                          { headers: { Authorization: "Bearer " + bruto }, signal: AbortSignal.timeout(PRAZO_META_MS) });
    const d = await r.json().catch(() => null);
    const primeira = Array.isArray(d?.data) ? d.data.find((p: any) => typeof p?.access_token === "string" && p.access_token) : null;
    trocaSemPagina = !primeira && Array.isArray(d?.data) && !d?.error;
    tokenPaginaMemo = primeira ? String(primeira.access_token) : bruto;   // sem lista = já é o token da página (ou o erro sai claro adiante)
    return tokenPaginaMemo;
  } catch { return bruto; }
}

async function meta(caminho: string, corpo: Record<string, unknown>): Promise<{ ok: boolean; dados: any; erro: string; codigo: number | null }> {
  try {
    const r = await fetch(`${GRAPH}/${caminho}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + await tokenPagina() },
      body: JSON.stringify(corpo),
      signal: AbortSignal.timeout(PRAZO_META_MS),
    });
    const texto = await r.text();
    let dados: any = null;
    try { dados = texto ? JSON.parse(texto) : null; } catch { dados = null; }
    if (!r.ok) {
      const e = dados?.error ?? {};
      return { ok: false, dados, erro: `Meta ${e.code ?? r.status}${e.error_subcode ? "/" + e.error_subcode : ""}: ${limparErro(e.message ?? texto)}`,
               codigo: typeof e.code === "number" ? e.code : null };
    }
    return { ok: true, dados, erro: "", codigo: null };
  } catch (e) {
    return { ok: false, dados: null, erro: limparErro(e), codigo: null };
  }
}

/** Envia a resposta pública e a mensagem privada de um comentário; devolve o que o banco precisa saber. */
async function enviar(rede: string, comentario: string, publica: string, privada: string, link: string):
    Promise<{ ok: boolean; respostaId: string; privadaOk: boolean; erro: string }> {
  const pub = await meta(`${comentario}/${rede === "instagram" ? "replies" : "comments"}`, { message: publica });
  if (!pub.ok) return { ok: false, respostaId: "", privadaOk: false, erro: pub.erro };
  const respostaId = String(pub.dados?.id ?? "");
  let pagina = "";
  try { pagina = String((await banco(comoServico(), "POST", "rpc/radar_respostas_pagina", {}, 10_000)) ?? ""); } catch { pagina = ""; }
  if (!/^[0-9]{1,30}$/.test(pagina)) {
    return { ok: true, respostaId, privadaOk: false, erro: "A mensagem privada não saiu: rode o Testar conexão (a página não está gravada)." };
  }
  const texto = link ? `${privada}\n${link}` : privada;
  const priv = await meta(`${pagina}/messages`, { recipient: { comment_id: comentario }, message: { text: texto } });
  if (!priv.ok) return { ok: true, respostaId, privadaOk: false, erro: `A resposta pública saiu; a mensagem privada não: ${priv.erro}` };
  return { ok: true, respostaId, privadaOk: true, erro: "" };
}

/** Pergunta ao banco e, se for para responder, envia e conta o resultado. Devolve a ação decidida. */
async function tratarComentario(rede: string, midia: string, comentario: string, autorId: string, autorNome: string, texto: string): Promise<string> {
  const d = await banco(comoServico(), "POST", "rpc/radar_respostas_receber",
                        { p_rede: rede, p_midia: midia, p_comentario: comentario, p_autor_id: autorId, p_autor_nome: autorNome, p_texto: texto });
  if (d?.acao !== "responder") return String(d?.acao ?? "ignorado");
  const r = await enviar(rede, String(d.comentario_id), String(d.resposta_publica), String(d.mensagem_privada), String(d.link ?? ""));
  await banco(comoServico(), "POST", "rpc/radar_respostas_resultado",
              { p_registro: d.registro, p_ok: r.ok, p_resposta_id: r.respostaId, p_privada: r.privadaOk, p_erro: r.erro });
  return r.ok ? "enviado" : "erro";
}

/** Os eventos de um POST da Meta: comentários do Instagram (field "comments") e da página do Facebook (field "feed", comentário). */
function extrairComentarios(aviso: any): Array<{ rede: string; midia: string; comentario: string; autorId: string; autorNome: string; texto: string }> {
  const lista: Array<{ rede: string; midia: string; comentario: string; autorId: string; autorNome: string; texto: string }> = [];
  const objeto = String(aviso?.object ?? "");
  for (const entrada of Array.isArray(aviso?.entry) ? aviso.entry : []) {
    for (const mudanca of Array.isArray(entrada?.changes) ? entrada.changes : []) {
      const v = mudanca?.value ?? {};
      if (objeto === "instagram" && mudanca?.field === "comments" && v?.id) {
        lista.push({ rede: "instagram", midia: String(v?.media?.id ?? ""), comentario: String(v.id),
                     autorId: String(v?.from?.id ?? ""), autorNome: String(v?.from?.username ?? ""), texto: String(v?.text ?? "") });
      }
      if (objeto === "page" && mudanca?.field === "feed" && v?.item === "comment" && v?.verb === "add" && v?.comment_id) {
        lista.push({ rede: "facebook", midia: String(v?.post_id ?? ""), comentario: String(v.comment_id),
                     autorId: String(v?.from?.id ?? ""), autorNome: String(v?.from?.name ?? ""), texto: String(v?.message ?? "") });
      }
      if (lista.length >= MAX_EVENTOS) return lista;
    }
  }
  return lista;
}

// ------------------------------------------------------------------ ações
async function pendentes(): Promise<{ ok: boolean; versao: string; pendentes: number; enviados: number; erros: number }> {
  const fila = await banco(comoServico(), "POST", "rpc/radar_respostas_pendentes", { p_max: PENDENTES_POR_VEZ });
  let enviados = 0, erros = 0;
  for (const p of Array.isArray(fila) ? fila : []) {
    const r = await enviar(String(p.rede), String(p.comentario_id), String(p.resposta_publica), String(p.mensagem_privada), String(p.link ?? ""));
    await banco(comoServico(), "POST", "rpc/radar_respostas_resultado",
                { p_registro: p.registro, p_ok: r.ok, p_resposta_id: r.respostaId, p_privada: r.privadaOk, p_erro: r.erro });
    r.ok ? enviados++ : erros++;
  }
  return { ok: true, versao: VERSAO, pendentes: Array.isArray(fila) ? fila.length : 0, enviados, erros };
}

async function diagnostico(): Promise<Record<string, unknown>> {
  const faltam = faltamSegredos();
  if (faltam.length) {
    return { ok: false, versao: VERSAO, faltam,
             message: `Faltam os segredos ${faltam.join(", ")} (Supabase → Edge Functions → Secrets).` };
  }
  const r = await (async () => {
    try {
      const resp = await fetch(`${GRAPH}/me?fields=id,name,instagram_business_account{id,username}`, {
        headers: { Authorization: "Bearer " + await tokenPagina() }, signal: AbortSignal.timeout(PRAZO_META_MS),
      });
      const dados = await resp.json().catch(() => null);
      if (!resp.ok) {
        const e = dados?.error ?? {};
        return { ok: false as const, erro: `Meta ${e.code ?? resp.status}: ${limparErro(e.message ?? "")}` };
      }
      return { ok: true as const, dados };
    } catch (e) { return { ok: false as const, erro: limparErro(e) }; }
  })();
  if (!r.ok) {
    const dica = trocaSemPagina
      ? " O token é do usuário de sistema, mas nenhuma página está atribuída a ele: no Gerenciador de Negócios, abra o usuário de" +
        " sistema → Atribuir ativos → marque a página da Artecon com acesso de GERENCIAR → gere um token novo e cole de novo."
      : "";
    return { ok: false, versao: VERSAO, message: `O token não passou no teste: ${r.erro}.${dica}` };
  }
  const contas: Array<Record<string, string>> = [];
  if (/^[0-9]{1,30}$/.test(String(r.dados?.id ?? ""))) {
    await banco(comoServico(), "POST", "rpc/radar_respostas_conta_salvar",
                { p_rede: "facebook", p_conta: String(r.dados.id), p_nome: String(r.dados?.name ?? "") });
    contas.push({ rede: "facebook", conta_id: String(r.dados.id), nome: String(r.dados?.name ?? "") });
  }
  const iba = r.dados?.instagram_business_account;
  if (/^[0-9]{1,30}$/.test(String(iba?.id ?? ""))) {
    await banco(comoServico(), "POST", "rpc/radar_respostas_conta_salvar",
                { p_rede: "instagram", p_conta: String(iba.id), p_nome: String(iba?.username ?? "") });
    contas.push({ rede: "instagram", conta_id: String(iba.id), nome: String(iba?.username ?? "") });
  }
  const avisos: string[] = contas.length < 2 ? ["A página não tem um Instagram profissional ligado (ou o token não o enxerga)."] : [];
  // v0.35.2: inscreve o app na própria página (campo "feed") — sem a inscrição a Meta não entrega os avisos de comentário.
  // Pode rodar de novo à vontade: inscrever quem já está inscrito não muda nada.
  let paginaInscrita = false;
  if (/^[0-9]{1,30}$/.test(String(r.dados?.id ?? ""))) {
    const s = await meta(`${r.dados.id}/subscribed_apps`, { subscribed_fields: "feed" });
    paginaInscrita = s.ok && s.dados?.success === true;
    if (!paginaInscrita) avisos.push(`O app não ficou inscrito na página (os avisos de comentário não chegariam): ${s.erro || "resposta inesperada da Meta"}`);
  }
  return { ok: true, versao: VERSAO, contas, pagina_inscrita: paginaInscrita, avisos };
}

// ------------------------------------------------------------------ o tratador
async function tratar(req: Request): Promise<Response> {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  try {
    if (!SUPABASE_URL && req.method !== "GET") throw new Erro(503, "A função está sem SUPABASE_URL.");
    if (req.method === "GET") {
      // a verificação do webhook, no cadastro do painel da Meta
      const u = new URL(req.url);
      const modo = u.searchParams.get("hub.mode"), token = u.searchParams.get("hub.verify_token"), desafio = u.searchParams.get("hub.challenge");
      const esperado = env("META_VERIFY_TOKEN").trim();
      if (!esperado) throw new Erro(503, "Falta o segredo META_VERIFY_TOKEN (Supabase → Edge Functions → Secrets).");
      if (modo === "subscribe" && token === esperado && desafio !== null) {
        return new Response(desafio, { status: 200, headers: { ...CORS, "Content-Type": "text/plain" } });
      }
      throw new Erro(403, "Verificação recusada.");
    }
    if (req.method !== "POST") throw new Erro(405, "Use GET (verificação) ou POST.");

    const assinatura = req.headers.get("x-hub-signature-256");
    if (assinatura !== null) {
      // um aviso da Meta: a assinatura primeiro, sempre sobre o corpo cru
      const corpo = new Uint8Array(await req.arrayBuffer());
      if (!env("META_APP_SECRET").trim()) throw new Erro(503, "Falta o segredo META_APP_SECRET (Supabase → Edge Functions → Secrets).");
      if (!(await assinaturaConfere(corpo, assinatura))) throw new Erro(401, "Assinatura não confere.");
      let aviso: any = null;
      try { aviso = JSON.parse(new TextDecoder().decode(corpo)); } catch { aviso = null; }
      const comentarios = extrairComentarios(aviso);
      const contagem: Record<string, number> = {};
      for (const c of comentarios) {
        try {
          const acao = await tratarComentario(c.rede, c.midia, c.comentario, c.autorId, c.autorNome, c.texto);
          contagem[acao] = (contagem[acao] ?? 0) + 1;
        } catch (e) {
          contagem.falha = (contagem.falha ?? 0) + 1;
          console.log("radar-meta-webhook: comentário não tratado", e instanceof Erro ? e.status : "");
        }
      }
      console.log(`radar-meta-webhook (meta): eventos=${comentarios.length} ` +
                  Object.entries(contagem).map(([k, v]) => `${k}=${v}`).join(" "));
      return responder(200, { ok: true });
    }

    // uma ação do Radar (a agenda com a chave, ou o administrador)
    const quem = await autorizar(req);
    const pedido = await req.json().catch(() => ({}));
    const acao = String(pedido?.acao ?? "");
    if (acao === "agenda_teste") return responder(200, { ok: true, versao: VERSAO });
    if (acao === "pendentes") {
      const r = await pendentes();
      console.log(`radar-meta-webhook (${quem}): pendentes=${r.pendentes} enviados=${r.enviados} erros=${r.erros}`);
      return responder(200, r);
    }
    if (acao === "diagnostico") {
      if (quem !== "admin") throw new Erro(403, "Só o administrador testa a conexão.");
      const r = await diagnostico();
      console.log(`radar-meta-webhook (admin): diagnóstico ${r.ok ? "ok" : "com pendência"}`);
      return responder(r.ok ? 200 : 503, r);
    }
    throw new Erro(400, "Ação desconhecida.");
  } catch (e) {
    if (e instanceof Erro) return responder(e.status, { message: e.message });
    console.error("radar-meta-webhook: erro inesperado", e instanceof Error ? e.name : "");
    return responder(500, { message: "Erro inesperado nas respostas automáticas." });
  }
}

if (env("META_PAGE_TOKEN").trim()) tokenPagina().catch(() => {});   // aquece a troca no arranque; se falhar, a próxima chamada refaz

const portaLocal = Deno.env.get("RADAR_PORTA_LOCAL");       // só para rodar/testar fora do Supabase
portaLocal ? Deno.serve({ port: Number(portaLocal), hostname: "127.0.0.1" }, tratar) : Deno.serve(tratar);
