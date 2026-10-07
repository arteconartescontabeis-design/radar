// =====================================================================
// RADAR ARTECON — Edge Function "radar-redes" (v0.13.0)
//
// Publica no Instagram e no Facebook da Artecon, pela API da Meta (Graph API), o conteúdo que o administrador
// autorizou na tela do assunto (passos 6 e 7 da trilha). Nada sai sem essa autorização: a função só envia
// autorizações registradas por radar_autorizar_rede, uma vez cada (radar_rede_iniciar marca "enviando").
//
// Quem pode chamar: só o administrador logado (o botão "Autorizar e publicar" da tela chama logo depois de autorizar).
//
// Ações:
//   publicar     { envio }  → envia a imagem ao armazenamento público, publica e registra o link do post
//   diagnostico             → confere os segredos, a Página do Facebook, a conta do Instagram e o armazenamento
//
// Como publica:
//   Instagram: POST /{ig-user-id}/media (image_url + caption) → espera o contêiner ficar pronto → POST /{ig-user-id}/media_publish
//   Facebook:  POST /{page-id}/photos (url + message)
// A imagem (JPEG quadrado montado pela tela) vai para o bucket público "radar-redes" do Supabase Storage, porque a
// Meta só aceita imagem por link público.
//
// Segredos (Supabase → Edge Functions → Secrets):
//   META_PAGE_ID       id da Página do Facebook da Artecon
//   META_PAGE_TOKEN    token de acesso da Página (de longa duração; nunca vai para o GitHub nem para o chat)
//   META_IG_USER_ID    id da conta do Instagram profissional ligada à Página (só para o Instagram)
//   META_GRAPH_URL     opcional; padrão https://graph.facebook.com/v23.0
// SUPABASE_URL, SUPABASE_ANON_KEY e SUPABASE_SERVICE_ROLE_KEY o Supabase já fornece.
// =====================================================================

const VERSAO = "0.13.0";
const env = (nome: string, padrao = "") => Deno.env.get(nome) ?? padrao;

const SUPABASE_URL = env("SUPABASE_URL").replace(/\/+$/, "");
const ANON = env("SUPABASE_ANON_KEY");
const SERVICO = env("SUPABASE_SERVICE_ROLE_KEY");
const GRAPH = env("META_GRAPH_URL", "https://graph.facebook.com/v23.0").replace(/\/+$/, "");
const BUCKET = "radar-redes";
// a Meta às vezes demora para baixar a imagem: o contêiner do Instagram é consultado por até ~40 s
const ESPERA_IG_MS = Number(env("RADAR_REDES_ESPERA_MS", "40000")), PASSO_IG_MS = Number(env("RADAR_REDES_PASSO_MS", "3000"));

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

class Erro extends Error {
  status: number;
  constructor(status: number, mensagem: string) { super(mensagem); this.status = status; }
}
const responder = (status: number, corpo: unknown) =>
  new Response(JSON.stringify(corpo), { status, headers: { ...CORS, "Content-Type": "application/json" } });

// ------------------------------------------------------------------ banco
async function banco(chave: string, metodo: string, caminho: string, corpo?: unknown): Promise<any> {
  const r = await fetch(`${SUPABASE_URL}/rest/v1/${caminho}`, {
    method: metodo,
    headers: { apikey: ANON || chave, Authorization: chave, "Content-Type": "application/json" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
    signal: AbortSignal.timeout(30_000),
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
const comoServico = () => {
  if (!SERVICO) throw new Erro(503, "A função está sem a chave interna do Supabase (SUPABASE_SERVICE_ROLE_KEY).");
  return "Bearer " + SERVICO;
};

async function exigirAdmin(req: Request) {
  const token = req.headers.get("Authorization") ?? "";
  if (!/^Bearer\s+\S+/.test(token)) throw new Erro(401, "Sessão não informada.");
  const papel = await banco(token, "POST", "rpc/radar_papel", {});
  if (papel !== "admin") throw new Erro(403, "Só o administrador publica no Instagram e no Facebook.");
}

// ------------------------------------------------------------------ Meta
function configMeta(canal?: string) {
  const precisa = ["META_PAGE_ID", "META_PAGE_TOKEN", ...(canal === "facebook" ? [] : ["META_IG_USER_ID"])];
  return { faltam: precisa.filter((n) => !env(n).trim()), pagina: env("META_PAGE_ID").trim(),
           token: env("META_PAGE_TOKEN").trim(), ig: env("META_IG_USER_ID").trim() };
}

/** Chama a Graph API. O token vai no corpo/consulta e nunca aparece em mensagem de erro. */
async function meta(metodo: "GET" | "POST", caminho: string, params: Record<string, string>): Promise<any> {
  const c = configMeta("facebook");
  const p = new URLSearchParams({ ...params, access_token: c.token });
  let r: Response;
  try {
    r = metodo === "GET"
      ? await fetch(`${GRAPH}/${caminho}?${p}`, { signal: AbortSignal.timeout(30_000) })
      : await fetch(`${GRAPH}/${caminho}`, { method: "POST", body: p, signal: AbortSignal.timeout(60_000),
                                             headers: { "Content-Type": "application/x-www-form-urlencoded" } });
  } catch { throw new Erro(504, "Não foi possível falar com a Meta agora. Tente de novo em alguns minutos."); }
  const d: any = await r.json().catch(() => ({}));
  if (!r.ok || d?.error) {
    const e = d?.error ?? {};
    const msg = String(e.error_user_msg || e.message || `erro ${r.status}`).slice(0, 300);
    const limpa = c.token ? msg.split(c.token).join("***") : msg;
    const dica = e.code === 190 ? " O token da Página venceu ou foi revogado: gere outro e troque o META_PAGE_TOKEN."
      : e.code === 10 || e.code === 200 ? " Falta permissão no aplicativo da Meta (instagram_content_publish / pages_manage_posts)."
      : e.code === 4 || e.code === 32 || e.code === 613 ? " Limite de publicações da Meta atingido: tente mais tarde." : "";
    throw new Erro(502, `A Meta recusou (${e.code ?? r.status}): ${limpa}.${dica}`);
  }
  return d;
}

// ------------------------------------------------------------------ armazenamento público da imagem
async function garantirBucket() {
  const r = await fetch(`${SUPABASE_URL}/storage/v1/bucket/${BUCKET}`, { headers: { Authorization: comoServico(), apikey: ANON || SERVICO } });
  if (r.ok) return;
  const c = await fetch(`${SUPABASE_URL}/storage/v1/bucket`, {
    method: "POST", headers: { Authorization: comoServico(), apikey: ANON || SERVICO, "Content-Type": "application/json" },
    body: JSON.stringify({ id: BUCKET, name: BUCKET, public: true, file_size_limit: 8 * 1024 * 1024, allowed_mime_types: ["image/jpeg"] }),
  });
  if (!c.ok && c.status !== 409) throw new Erro(502, `Não foi possível criar o armazenamento das imagens (${c.status}).`);
}

async function enviarImagem(dataUrl: string, nome: string): Promise<string> {
  const m = /^data:image\/jpeg;base64,([A-Za-z0-9+/=]+)$/.exec(dataUrl);
  if (!m) throw new Erro(400, "A imagem da publicação não é um JPEG válido.");
  const bytes = Uint8Array.from(atob(m[1]), (ch) => ch.charCodeAt(0));
  await garantirBucket();
  const r = await fetch(`${SUPABASE_URL}/storage/v1/object/${BUCKET}/${nome}`, {
    method: "POST", body: bytes,
    headers: { Authorization: comoServico(), apikey: ANON || SERVICO, "Content-Type": "image/jpeg", "x-upsert": "true" },
  });
  if (!r.ok) throw new Erro(502, `Não foi possível guardar a imagem para a Meta (${r.status}).`);
  return `${SUPABASE_URL}/storage/v1/object/public/${BUCKET}/${nome}`;
}

// ------------------------------------------------------------------ publicar
const dormir = (ms: number) => new Promise((ok) => setTimeout(ok, ms));

async function publicarInstagram(imagemUrl: string, legenda: string) {
  const c = configMeta("instagram");
  const cont = await meta("POST", `${c.ig}/media`, { image_url: imagemUrl, caption: legenda });
  for (let t = 0; t * PASSO_IG_MS <= ESPERA_IG_MS; t++) {
    const s = await meta("GET", cont.id, { fields: "status_code" });
    if (s.status_code === "FINISHED") break;
    if (s.status_code === "ERROR" || s.status_code === "EXPIRED") throw new Erro(502, "O Instagram não aceitou a imagem (contêiner com erro).");
    if ((t + 1) * PASSO_IG_MS > ESPERA_IG_MS) throw new Erro(504, "O Instagram demorou para processar a imagem. Tente de novo.");
    await dormir(PASSO_IG_MS);
  }
  const pub = await meta("POST", `${c.ig}/media_publish`, { creation_id: cont.id });
  let url = "";
  try { url = (await meta("GET", pub.id, { fields: "permalink" })).permalink ?? ""; } catch { /* o post saiu; o link é só conveniência */ }
  return { post_id: String(pub.id), url };
}

async function publicarFacebook(imagemUrl: string, legenda: string) {
  const c = configMeta("facebook");
  const pub = await meta("POST", `${c.pagina}/photos`, { url: imagemUrl, message: legenda });
  const post = String(pub.post_id ?? pub.id);
  let url = "";
  try { url = (await meta("GET", post, { fields: "permalink_url" })).permalink_url ?? ""; } catch { /* idem */ }
  return { post_id: post, url };
}

async function publicar(envio: number) {
  const servico = comoServico();
  // confere a configuração ANTES de pegar a autorização: sem a Meta configurada, ela continua aguardando
  const [linha] = await banco(servico, "GET", `radar_redes_envios?select=canal,situacao&id=eq.${envio}`);
  if (!linha) throw new Erro(404, "Autorização não encontrada.");
  const cfg = configMeta(linha.canal);
  if (cfg.faltam.length) {
    throw new Erro(503, `${linha.canal === "instagram" ? "O Instagram" : "O Facebook"} ainda não está configurado: faltam os segredos ` +
      cfg.faltam.join(", ") + " (Supabase → Edge Functions → Secrets). A autorização continua guardada; publique depois.");
  }
  const e = await banco(servico, "POST", "rpc/radar_rede_iniciar", { p_envio: envio });
  if (e?.cancelado) return { situacao: "cancelado", mensagem: "O conteúdo mudou depois de autorizado: a autorização caiu. Confira e autorize de novo." };
  if (e?.erro) return { situacao: "erro", mensagem: String(e.erro) };
  let imagemUrl = e.imagem_url ?? "";
  try {
    if (!imagemUrl) imagemUrl = await enviarImagem(e.imagem, `${e.conteudo_id}-${e.canal}-${e.id}.jpg`);
    const r = e.canal === "instagram" ? await publicarInstagram(imagemUrl, e.legenda) : await publicarFacebook(imagemUrl, e.legenda);
    await banco(servico, "POST", "rpc/radar_rede_concluir",
                { p_envio: envio, p_ok: true, p_post_id: r.post_id, p_url: r.url || null, p_imagem_url: imagemUrl, p_erro: null });
    return { situacao: "publicado", url: r.url, post_id: r.post_id };
  } catch (x) {
    const msg = x instanceof Erro ? x.message : "Erro inesperado ao publicar.";
    await banco(servico, "POST", "rpc/radar_rede_concluir",
                { p_envio: envio, p_ok: false, p_post_id: null, p_url: null, p_imagem_url: imagemUrl || null, p_erro: msg }).catch(() => {});
    throw x instanceof Erro ? x : new Erro(500, msg);
  }
}

async function diagnostico() {
  const itens: { item: string; ok: boolean; detalhe: string }[] = [];
  const c = configMeta("instagram");
  itens.push({ item: "Segredos da Meta", ok: !c.faltam.length,
               detalhe: c.faltam.length ? "Faltam: " + c.faltam.join(", ") : "META_PAGE_ID, META_PAGE_TOKEN e META_IG_USER_ID cadastrados" });
  if (c.pagina && c.token) {
    try {
      const p = await meta("GET", c.pagina, { fields: "name" });
      itens.push({ item: "Página do Facebook", ok: true, detalhe: String(p.name ?? c.pagina) });
    } catch (e) { itens.push({ item: "Página do Facebook", ok: false, detalhe: e instanceof Error ? e.message : "erro" }); }
  }
  if (c.ig && c.token) {
    try {
      const ig = await meta("GET", c.ig, { fields: "username" });
      itens.push({ item: "Conta do Instagram", ok: true, detalhe: "@" + String(ig.username ?? c.ig) });
    } catch (e) { itens.push({ item: "Conta do Instagram", ok: false, detalhe: e instanceof Error ? e.message : "erro" }); }
  }
  try { await garantirBucket(); itens.push({ item: "Armazenamento das imagens", ok: true, detalhe: `bucket público "${BUCKET}"` }); }
  catch (e) { itens.push({ item: "Armazenamento das imagens", ok: false, detalhe: e instanceof Error ? e.message : "erro" }); }
  return { itens, tudo_certo: itens.every((i) => i.ok), versao: VERSAO };
}

async function tratar(req: Request): Promise<Response> {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  try {
    if (req.method !== "POST") throw new Erro(405, "Use POST.");
    if (!SUPABASE_URL) throw new Erro(503, "A função está sem SUPABASE_URL.");
    await exigirAdmin(req);
    const pedido = await req.json().catch(() => ({}));
    const acao = String(pedido?.acao ?? "");
    if (acao === "diagnostico") return responder(200, await diagnostico());
    if (acao !== "publicar") throw new Erro(400, "Ação desconhecida.");
    const envio = Number(pedido?.envio);
    if (!Number.isSafeInteger(envio) || envio <= 0) throw new Erro(400, "Informe a autorização (envio).");
    const r = await publicar(envio);
    console.log(`radar-redes: envio ${envio} → ${r.situacao}`);
    return responder(200, r);
  } catch (e) {
    if (e instanceof Erro) return responder(e.status, { message: e.message });
    console.error("radar-redes: erro inesperado", e instanceof Error ? e.name : "");
    return responder(500, { message: "Erro inesperado na publicação." });
  }
}

const portaLocal = Deno.env.get("RADAR_PORTA_LOCAL");       // só para rodar/testar fora do Supabase
portaLocal ? Deno.serve({ port: Number(portaLocal), hostname: "127.0.0.1" }, tratar) : Deno.serve(tratar);
