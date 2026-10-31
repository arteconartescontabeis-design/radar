// =====================================================================
// RADAR ARTECON — Edge Function "radar-polir" (v0.61.0)
//
// v0.61.0 — o polimento entra no Consumo de IA do Portal: com o segredo RADAR_IA_GATEWAY_TOKEN (o mesmo token do
//   Radar na IA Central — o IA_GATEWAY_TOKEN que a radar-ia já tem serve), cada uso da Cleanvoice e da AssemblyAI é avisado à IA Central
//   (função ia-uso-externo do projeto Departamento Pessoal), que calcula o custo pelo preço por minuto e soma no
//   gasto do Radar. Sem o segredo, nada muda (o aviso é pulado). O aviso NUNCA trava o polimento.
//
// Polimento de vídeo SEM roteiro (ex.: os vídeos de venda): tira vícios de fala e pausas e limpa o áudio
// (Cleanvoice) e gera a legenda pt-BR (AssemblyAI). Diferente do corretor de reels (radar-video), que já faz
// isso MAS exige o roteiro para alinhar a fala — aqui não há roteiro, então a IA trabalha pela própria fala.
//
// Fluxo:
//   tela  preparar  {duracao_s} → confere papel (editor/admin) e a cota do mês; devolve {id, envio:{url,token}}
//                   para o navegador subir o vídeo em bucket PRIVADO (polimento/<id>/fonte.mp4) por TUS.
//         processar {id, duracao_s} → confere a cota de novo; manda a URL assinada da fonte à Cleanvoice e à
//                   AssemblyAI (as duas aceitam URL), guarda o tratado (polimento/<id>/tratado.mp4) e a legenda
//                   (polimento/<id>/legenda.srt), registra o uso e o custo (radar_polimento_registrar) e devolve
//                   {video_url, srt, transcricao, cota}.
//         cota      → radar_polimento_cota (ligado, segundos_mes, limite_s, custo_mes_brl).
//
// A chave interna do Supabase NUNCA é aceita como quem chama (403). Nenhum nome, fala, link ou segredo vai aos Logs.
//
// Segredos (Supabase → Edge Functions → Secrets):
//   CLEANVOICE_API_KEY   Cleanvoice (cabeçalho X-API-Key). Sem ela, "processar" recusa com aviso claro.
//   ASSEMBLYAI_API_KEY   AssemblyAI (cabeçalho authorization). Sem ela, a legenda é pulada (o resto segue).
//   (v0.61.0) o aviso usa o IA_GATEWAY_TOKEN que a radar-ia já tem no projeto; RADAR_IA_GATEWAY_TOKEN, se existir, prevalece.
// SUPABASE_URL e as chaves pública/interna o Supabase já fornece.
// =====================================================================

const VERSAO = "0.61.0";
const env = (nome: string, padrao = "") => Deno.env.get(nome) ?? padrao;
const SUPABASE_URL = env("SUPABASE_URL").replace(/\/+$/, "");
const BUCKET = "radar-videos";
const LINK_FONTE_S = 1800, LINK_RESULTADO_S = 600;           // prazos dos links assinados, fixos aqui
const ARMAZENAMENTO_MS = Number(env("RADAR_VIDEO_ARMAZENAMENTO_MS", "20000"));
const CLEANVOICE_BASE = env("CLEANVOICE_API_URL", "https://api.cleanvoice.ai/v2").replace(/\/+$/, "");
const ASSEMBLY_BASE = env("ASSEMBLYAI_API_URL", "https://api.assemblyai.com/v2").replace(/\/+$/, "");
const POLL_MS = 4000, POLL_MAX = 30;                          // espera a IA (até ~2 min); vídeos curtos
// v0.61.0: o aviso à IA Central (Portal → Consumo de IA); o endereço só muda nos testes
// o token do Radar na IA Central: o IA_GATEWAY_TOKEN que a radar-ia já tem neste projeto serve (os segredos
// valem para o projeto inteiro); um RADAR_IA_GATEWAY_TOKEN próprio, se existir, prevalece. Sem nenhum: aviso pulado.
const IA_CENTRAL_TOKEN = env("RADAR_IA_GATEWAY_TOKEN") || env("IA_GATEWAY_TOKEN");
const IA_USO_EXTERNO_URL = env("IA_USO_EXTERNO_URL", "https://fbxelwhdiisfmnwrerbl.supabase.co/functions/v1/ia-uso-externo").replace(/\/+$/, "");
/** Avisa a IA Central do uso de uma IA de vídeo. Sem o segredo, não faz nada; falha vira só uma linha de log
 *  (sem nome, sem link e sem segredo) e o polimento segue normal. */
async function avisarCentral(provedor: "cleanvoice" | "assemblyai", segundos: number): Promise<void> {
  if (!IA_CENTRAL_TOKEN) return;
  try {
    const r = await fetch(IA_USO_EXTERNO_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-api-key": IA_CENTRAL_TOKEN },
      body: JSON.stringify({ provedor, segundos, detalhe: "polimento de vídeo (Radar)" }),
      signal: AbortSignal.timeout(10_000),
    });
    if (!r.ok) console.log("radar-polir: a IA Central não registrou o uso", r.status);
    await r.body?.cancel().catch(() => {});
  } catch { console.log("radar-polir: IA Central fora de alcance (uso não registrado lá)"); }
}

function chavePublica(): string {
  try {
    const k = JSON.parse(env("SUPABASE_PUBLISHABLE_KEYS") || "{}");
    const v = k?.default ?? Object.values(k ?? {}).find((x) => typeof x === "string" && x);
    if (typeof v === "string" && v.trim()) return v.trim();
  } catch { /* sem a lista nova: fica a anon */ }
  return env("SUPABASE_ANON_KEY").trim();
}
const ANON = chavePublica();

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
class Erro extends Error { status: number; constructor(status: number, m: string) { super(m); this.status = status; } }
const responder = (status: number, corpo: unknown) =>
  new Response(JSON.stringify(corpo), { status, headers: { ...CORS, "Content-Type": "application/json" } });
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
function uuid(x: unknown): string {
  const s = String(x ?? "");
  if (!UUID.test(s)) throw new Erro(400, "Informe o vídeo (id).");
  return s;
}
function duracao(x: unknown): number {
  const n = Number(x);
  if (!Number.isFinite(n) || n <= 0 || n > 3600) throw new Erro(400, "Informe a duração do vídeo (em segundos).");
  return Math.round(n * 10) / 10;
}
const dorme = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ------------------------------------------------------------------ banco
async function banco(quem: string | Record<string, string>, metodo: string, caminho: string, corpo?: unknown, tempo = 30_000): Promise<any> {
  let r: Response;
  try {
    r = await fetch(`${SUPABASE_URL}/rest/v1/${caminho}`, {
      method: metodo,
      headers: { ...(typeof quem === "string" ? { apikey: ANON || quem, Authorization: quem } : quem), "Content-Type": "application/json" },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
      signal: AbortSignal.timeout(tempo),
    });
  } catch { throw new Erro(502, "O banco não respondeu. Tente de novo em alguns minutos."); }
  const texto = await r.text();
  let dados: any = null;
  try { dados = texto ? JSON.parse(texto) : null; } catch { dados = { message: texto }; }
  if (!r.ok) {
    const m = String(dados?.message ?? "");
    const radar = /RADAR\d+:\s*(.*)/s.exec(m);
    if (r.status >= 500 && !radar) throw new Erro(502, "O banco não respondeu. Tente de novo em alguns minutos.");
    throw new Erro(r.status === 401 ? 401 : r.status === 403 ? 403 : 400, radar ? radar[1].slice(0, 400) : `Erro ${r.status} no banco.`);
  }
  return dados;
}
function chaveInterna(): string {
  try {
    const k = JSON.parse(env("SUPABASE_SECRET_KEYS") || "{}");
    const v = k?.default ?? Object.values(k ?? {}).find((x) => typeof x === "string" && x);
    if (typeof v === "string" && v.trim()) return v.trim();
  } catch { /* sem a lista nova */ }
  return env("SUPABASE_SERVICE_ROLE_KEY").trim();
}
const ehJwt = (k: string) => /^[\w-]+\.[\w-]+\.[\w-]+$/.test(k);
const comoServico = (): Record<string, string> => {
  const k = chaveInterna();
  if (!k) throw new Erro(503, "A função está sem a chave interna do Supabase.");
  return ehJwt(k) ? { apikey: k, Authorization: "Bearer " + k } : { apikey: k };
};
function ehChaveInterna(req: Request): boolean {
  const auth = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "").trim(), apikey = (req.headers.get("apikey") ?? "").trim();
  const chaves = [env("SUPABASE_SERVICE_ROLE_KEY").trim()];
  try { chaves.push(...Object.values(JSON.parse(env("SUPABASE_SECRET_KEYS") || "{}") ?? {}).filter((v): v is string => typeof v === "string")); }
  catch { /* sem a lista nova */ }
  if (chaves.some((k) => k.length >= 20 && (k === auth || k === apikey))) return true;
  if (auth.startsWith("sb_secret_") || apikey.startsWith("sb_secret_")) return true;
  return [auth, apikey].some((t) => {
    if (!ehJwt(t)) return false;
    try { return ["service_role", "supabase_admin"].includes(String(JSON.parse(atob(t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")))?.role ?? "")); }
    catch { return false; }
  });
}
async function sessaoDaTela(req: Request): Promise<string> {
  const sessao = req.headers.get("Authorization") ?? "";
  if (!/^Bearer\s+\S+/.test(sessao)) throw new Erro(401, "Sessão não informada.");
  const papel = await banco(sessao, "POST", "rpc/radar_papel", {});
  if (papel !== "admin" && papel !== "editor") throw new Erro(403, "Só o editor ou o administrador usa o polimento.");
  return sessao;
}
// A cota do mês. Recusa se o novo trabalho passar do limite (confere na tela e aqui, antes de chamar a IA paga).
async function conferirCota(sessao: string, novoS: number): Promise<any> {
  const c = await banco(sessao, "POST", "rpc/radar_polimento_cota", {});
  if (c?.ligado === false) throw new Erro(403, "O polimento está desligado em Configurações → Polimento.");
  if (Number(c?.segundos_mes ?? 0) + novoS > Number(c?.limite_s ?? 0)) {
    throw new Erro(403, "Cota de polimento do mês atingida. Aumente o limite em Configurações → Polimento ou espere o próximo mês.");
  }
  return c;
}

// ------------------------------------------------------------------ armazenamento (bucket privado)
async function armazenamento(metodo: string, caminho: string, corpo?: unknown): Promise<{ ok: boolean; status: number; dados: any }> {
  let r: Response;
  try {
    r = await fetch(`${SUPABASE_URL}/storage/v1/${caminho}`, {
      method: metodo, headers: { ...comoServico(), "Content-Type": "application/json" },
      body: corpo === undefined ? undefined : JSON.stringify(corpo), signal: AbortSignal.timeout(ARMAZENAMENTO_MS),
    });
  } catch { throw new Erro(502, "O armazenamento não respondeu. Tente de novo em alguns minutos."); }
  const dados = await r.json().catch(() => null);
  return { ok: r.ok, status: r.status, dados };
}
async function garantirBucketPrivado(): Promise<void> {
  const g = await armazenamento("GET", `bucket/${BUCKET}`);
  if (g.ok) {
    if (g.dados?.public === false) return;
    const u = await armazenamento("PUT", `bucket/${BUCKET}`, { public: false });
    if (!u.ok) throw new Erro(502, `O armazenamento "${BUCKET}" está público: no Supabase → Storage, desligue “Public bucket”.`);
    return;
  }
  const c = await armazenamento("POST", "bucket", { id: BUCKET, name: BUCKET, public: false });
  if (!c.ok && c.status !== 409) throw new Erro(502, "Não foi possível preparar o armazenamento dos vídeos.");
}
async function tokenDeEnvio(caminho: string): Promise<{ url: string; token: string }> {
  const r = await armazenamento("POST", `object/upload/sign/${BUCKET}/${caminho}`, {});
  let token = "";
  try { token = new URL(SUPABASE_URL + "/storage/v1" + String(r.dados?.url ?? "")).searchParams.get("token") ?? ""; } catch { /* sem url */ }
  if (!token && typeof r.dados?.token === "string") token = r.dados.token;
  if (!r.ok || !token) throw new Erro(502, "Não foi possível preparar o envio no armazenamento. Tente de novo.");
  return { url: `${SUPABASE_URL}/storage/v1/object/upload/sign/${BUCKET}/${caminho}?token=${encodeURIComponent(token)}`, token };
}
async function linkDeLeitura(caminho: string, segundos: number, baixarComo = ""): Promise<string> {
  const r = await armazenamento("POST", `object/sign/${BUCKET}/${caminho}`, { expiresIn: segundos });
  const assinado = String(r.dados?.signedURL ?? r.dados?.signedUrl ?? "");
  if (!r.ok || !assinado.startsWith(`/object/sign/${BUCKET}/`)) {
    throw new Erro(502, "Não foi possível preparar o link do armazenamento (o arquivo pode não ter chegado). Tente de novo.");
  }
  return `${SUPABASE_URL}/storage/v1${assinado}` + (baixarComo ? `&download=${encodeURIComponent(baixarComo)}` : "");
}
async function existe(caminho: string): Promise<boolean> {
  const barra = caminho.lastIndexOf("/");
  const pasta = caminho.slice(0, barra), nome = caminho.slice(barra + 1);
  const r = await armazenamento("POST", `object/list/${BUCKET}`, { prefix: pasta, limit: 100 });
  return r.ok && Array.isArray(r.dados) && r.dados.some((o: any) => String(o?.name ?? "") === nome);
}
async function guardar(caminho: string, corpo: BodyInit, tipo: string): Promise<void> {
  let r: Response;
  try {
    r = await fetch(`${SUPABASE_URL}/storage/v1/object/${BUCKET}/${caminho}`, {
      method: "POST", headers: { ...comoServico(), "Content-Type": tipo, "x-upsert": "true", "cache-control": "60" },
      body: corpo, signal: AbortSignal.timeout(ARMAZENAMENTO_MS),
    });
  } catch { throw new Erro(502, "O armazenamento não recebeu o resultado. Tente de novo."); }
  if (!r.ok) { await r.body?.cancel(); throw new Erro(502, "O armazenamento não guardou o resultado. Tente de novo."); }
}

// ------------------------------------------------------------------ Cleanvoice (vícios/pausas/áudio)
async function cleanvoice(fonteUrl: string): Promise<ArrayBuffer> {
  const key = env("CLEANVOICE_API_KEY").trim();
  if (!key) throw new Erro(503, "A função está sem a chave da Cleanvoice (CLEANVOICE_API_KEY).");
  const cab = { "X-API-Key": key, "Content-Type": "application/json" };
  const cfg = { long_silences: true, fillers: true, stutters: true, mouth_sounds: true, normalize: true };
  let r = await fetch(`${CLEANVOICE_BASE}/edits`, { method: "POST", headers: cab, body: JSON.stringify({ input: { files: [fonteUrl], config: cfg } }), signal: AbortSignal.timeout(30_000) });
  const criado = await r.json().catch(() => null);
  const id = String(criado?.id ?? "");
  if (!r.ok || !id) throw new Erro(502, "A Cleanvoice não aceitou o vídeo. Tente de novo em alguns minutos.");
  for (let i = 0; i < POLL_MAX; i++) {
    await dorme(POLL_MS);
    r = await fetch(`${CLEANVOICE_BASE}/edits/${id}`, { headers: { "X-API-Key": key }, signal: AbortSignal.timeout(20_000) });
    const e = await r.json().catch(() => null);
    const st = String(e?.status ?? "").toUpperCase();
    if (st === "SUCCESS") {
      const saida = String(e?.result?.download_url ?? e?.result?.video ?? e?.result?.url ?? "");
      if (!saida) throw new Erro(502, "A Cleanvoice terminou, mas não devolveu o vídeo. Tente de novo.");
      const d = await fetch(saida, { signal: AbortSignal.timeout(60_000) });
      if (!d.ok) throw new Erro(502, "Não foi possível baixar o vídeo tratado da Cleanvoice.");
      return await d.arrayBuffer();
    }
    if (st === "FAILURE" || st === "FAILED" || st === "ERROR") throw new Erro(502, "A Cleanvoice não conseguiu tratar este vídeo.");
  }
  throw new Erro(504, "A Cleanvoice demorou demais. Tente de novo (vídeos mais curtos funcionam melhor).");
}

// ------------------------------------------------------------------ AssemblyAI (legenda pt-BR)
async function assemblyai(fonteUrl: string): Promise<{ srt: string; texto: string }> {
  const key = env("ASSEMBLYAI_API_KEY").trim();
  if (!key) return { srt: "", texto: "" };                 // sem a chave, pula a legenda e segue
  const cab = { "authorization": key, "content-type": "application/json" };
  let r = await fetch(`${ASSEMBLY_BASE}/transcript`, { method: "POST", headers: cab, body: JSON.stringify({ audio_url: fonteUrl, language_code: "pt" }), signal: AbortSignal.timeout(30_000) });
  const criado = await r.json().catch(() => null);
  const id = String(criado?.id ?? "");
  if (!r.ok || !id) return { srt: "", texto: "" };
  for (let i = 0; i < POLL_MAX; i++) {
    await dorme(POLL_MS);
    r = await fetch(`${ASSEMBLY_BASE}/transcript/${id}`, { headers: { authorization: key }, signal: AbortSignal.timeout(20_000) });
    const t = await r.json().catch(() => null);
    const st = String(t?.status ?? "");
    if (st === "completed") {
      const s = await fetch(`${ASSEMBLY_BASE}/transcript/${id}/srt`, { headers: { authorization: key }, signal: AbortSignal.timeout(20_000) });
      const srt = s.ok ? await s.text() : "";
      return { srt, texto: String(t?.text ?? "") };
    }
    if (st === "error") return { srt: "", texto: "" };
  }
  return { srt: "", texto: "" };
}

// ------------------------------------------------------------------ ações
async function preparar(req: Request, corpo: any): Promise<Response> {
  const sessao = await sessaoDaTela(req);
  const dur = duracao(corpo?.duracao_s);
  await conferirCota(sessao, dur);
  await garantirBucketPrivado();
  const id = crypto.randomUUID();
  const envio = await tokenDeEnvio(`polimento/${id}/fonte.mp4`);
  return responder(200, { id, versao: VERSAO, envio });
}

async function processar(req: Request, corpo: any): Promise<Response> {
  const sessao = await sessaoDaTela(req);
  const id = uuid(corpo?.id);
  const dur = duracao(corpo?.duracao_s);
  await conferirCota(sessao, dur);
  if (!await existe(`polimento/${id}/fonte.mp4`)) throw new Erro(404, "O vídeo não chegou ao armazenamento. Envie de novo.");
  const fonteUrl = await linkDeLeitura(`polimento/${id}/fonte.mp4`, LINK_FONTE_S);

  // 1) Cleanvoice: tira vícios/pausas, limpa o áudio
  let srtTexto = { srt: "", texto: "" };
  try {
    const tratado = await cleanvoice(fonteUrl);
    await guardar(`polimento/${id}/tratado.mp4`, tratado, "video/mp4");
    await banco(comoServico(), "POST", "rpc/radar_polimento_registrar", { p_peca: null, p_provedor: "cleanvoice", p_segundos: dur });
    await avisarCentral("cleanvoice", dur);                   // v0.61.0: o gasto aparece no Portal → Consumo de IA
    // 2) AssemblyAI: legenda pt-BR (da fonte; não trava o resultado se falhar)
    srtTexto = await assemblyai(fonteUrl);
    if (srtTexto.srt) {
      await guardar(`polimento/${id}/legenda.srt`, srtTexto.srt, "text/plain; charset=utf-8");
      await banco(comoServico(), "POST", "rpc/radar_polimento_registrar", { p_peca: null, p_provedor: "assemblyai", p_segundos: dur });
      await avisarCentral("assemblyai", dur);                 // v0.61.0: idem
    }
  } catch (e) {
    await banco(comoServico(), "POST", "rpc/radar_polimento_registrar", { p_peca: null, p_provedor: "cleanvoice", p_segundos: 0, p_status: "erro", p_erro: (e as Error).message }).catch(() => {});
    throw e;
  }
  const videoUrl = await linkDeLeitura(`polimento/${id}/tratado.mp4`, LINK_RESULTADO_S, `polido-${new Date().toISOString().slice(0, 10)}.mp4`);
  const cota = await banco(sessao, "POST", "rpc/radar_polimento_cota", {});
  return responder(200, { id, video_url: videoUrl, srt: srtTexto.srt, transcricao: srtTexto.texto, cota });
}

async function cota(req: Request): Promise<Response> {
  const sessao = await sessaoDaTela(req);
  return responder(200, await banco(sessao, "POST", "rpc/radar_polimento_cota", {}));
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  if (req.method !== "POST") return responder(405, { erro: "Use POST." });
  try {
    if (ehChaveInterna(req)) throw new Erro(403, "A chave interna do Supabase não chama esta função.");
    const corpo = await req.json().catch(() => ({}));
    const acao = String(corpo?.acao ?? "");
    if (acao === "preparar") return await preparar(req, corpo);
    if (acao === "processar") return await processar(req, corpo);
    if (acao === "cota") return await cota(req);
    throw new Erro(400, "Ação desconhecida.");
  } catch (e) {
    const err = e as Erro;
    console.log("radar-polir:", err?.status ?? 500, acaoDe(err));
    return responder(err?.status ?? 500, { erro: err?.message ?? "Erro inesperado." });
  }
});
function acaoDe(e: Erro): string { return e?.status ? `status ${e.status}` : "erro"; }
