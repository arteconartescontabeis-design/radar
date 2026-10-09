// =====================================================================
// RADAR ARTECON — Edge Function "radar-redes" (v0.17.0)
//
// Publica no Instagram e no Facebook da Artecon, pela API da Meta (Graph API), o conteúdo que o administrador
// autorizou na tela do assunto (passos 6 e 7 da trilha). Nada sai sem essa autorização: a função só envia
// autorizações registradas por radar_autorizar_rede, uma vez cada (radar_rede_iniciar marca "enviando").
//
// Quem pode chamar: o administrador logado (o botão "Autorizar e publicar" da tela chama logo depois de autorizar) e,
// v0.17.0, o robô do site com a chave interna — só para as autorizações do "Publicar em todos" (feitas pelo administrador
// junto com o site), logo depois que a notícia entra no site.
//
// Ações:
//   publicar     { envio }  → envia a imagem ao armazenamento público, publica e registra o link do post
//   excluir      { envio }  → v0.17.0: apaga a publicação na rede (pedido do administrador) e registra a exclusão
//   diagnostico             → confere os segredos, a Página do Facebook, a conta do Instagram e o armazenamento
//
// Como publica:
//   Instagram: POST /{ig-user-id}/media (image_url + caption) → espera o contêiner ficar pronto → POST /{ig-user-id}/media_publish
//   Facebook:  POST /{page-id}/photos (url + message)
// Como exclui (v0.17.0): DELETE /{id do post} — no Facebook com o token da Página (pages_manage_posts); no Instagram com o
// token do Instagram. Se a Meta não deixar apagar pelo aplicativo, a tela oferece "Já apaguei na rede" para registrar à mão.
// A imagem (JPEG quadrado montado pela tela) vai para o bucket público "radar-redes" do Supabase Storage, porque a
// Meta só aceita imagem por link público.
//
// Segredos (Supabase → Edge Functions → Secrets):
//   META_PAGE_ID       id da Página do Facebook da Artecon
//   META_PAGE_TOKEN    token do usuário do sistema (Business → Usuários do sistema → Gerar token, "Nunca expira") ou o próprio
//                      token da Página; nunca vai para o GitHub nem para o chat. v0.14.1: com o token do usuário do sistema, a
//                      função busca sozinha o token da Página (GET /{page-id}?fields=access_token) antes de falar com a Meta
//   META_IG_USER_ID    id da conta do Instagram profissional ligada à Página (só para o Instagram; o "Testar conexão" mostra qual é)
//   META_IG_TOKEN      v0.14.4, opcional: token do usuário do sistema gerado no aplicativo do Instagram (instagram_basic,
//                      instagram_content_publish). Sem ele, o Instagram usa o mesmo token da Página.
//   META_GRAPH_URL     opcional; padrão https://graph.facebook.com/v23.0
// SUPABASE_URL, SUPABASE_ANON_KEY e a chave interna (SUPABASE_SECRET_KEYS ou SUPABASE_SERVICE_ROLE_KEY) o Supabase já fornece.
// =====================================================================

const VERSAO = "0.17.0";
const env = (nome: string, padrao = "") => Deno.env.get(nome) ?? padrao;

const SUPABASE_URL = env("SUPABASE_URL").replace(/\/+$/, "");
const ANON = env("SUPABASE_ANON_KEY");
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
/** Falha depois de o pedido de publicação ter sido enviado sem resposta clara: pode ter saído. Nunca vira "erro" (que deixa
 *  tentar de novo): a autorização fica "enviando" e a tela pede para conferir na rede antes de qualquer coisa. */
class Incerto extends Erro {}
// O Supabase encerra a chamada perto de 150 s: a publicação só é pedida até 55 s depois do início do pedido, para caber
// o pior caso depois dela (publicar 40 s + link 8 s + registro 2 × 15 s ≈ 135 s). A tela espera 150 s.
const LIMITE_PUBLICAR_MS = 55_000, TEMPO_PUBLICAR_MS = 40_000;
const responder = (status: number, corpo: unknown) =>
  new Response(JSON.stringify(corpo), { status, headers: { ...CORS, "Content-Type": "application/json" } });

// ------------------------------------------------------------------ banco
/** "quem" é a sessão do usuário ("Bearer …", com a chave pública) ou os cabeçalhos da chave interna (comoServico). */
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
// v0.14.2: chave interna do Supabase. A nova (sb_secret_…, em SUPABASE_SECRET_KEYS — e, em projetos novos, também no lugar da
// antiga em SUPABASE_SERVICE_ROLE_KEY) só vale no cabeçalho apikey: mandada como "Authorization: Bearer", o Supabase recusa
// ("Invalid Compact JWS"). A antiga (JWT service_role) continua indo nos dois cabeçalhos.
function chaveInterna(): string {
  try {
    const k = JSON.parse(env("SUPABASE_SECRET_KEYS") || "{}");
    const v = k?.default ?? Object.values(k ?? {}).find((x) => typeof x === "string" && x);
    if (typeof v === "string" && v.trim()) return v.trim();
  } catch { /* sem a lista nova: fica a antiga */ }
  return env("SUPABASE_SERVICE_ROLE_KEY").trim();
}
const ehJwt = (k: string) => /^[\w-]+\.[\w-]+\.[\w-]+$/.test(k);
/** Cabeçalhos para falar com o banco e o armazenamento como a própria função (acima das regras de acesso). */
const comoServico = (): Record<string, string> => {
  const k = chaveInterna();
  if (!k) throw new Erro(503, "A função está sem a chave interna do Supabase (SUPABASE_SECRET_KEYS ou SUPABASE_SERVICE_ROLE_KEY).");
  return ehJwt(k) ? { apikey: k, Authorization: "Bearer " + k } : { apikey: k };
};

/** v0.17.0: a chamada vem do robô do site com a chave interna do projeto? Vale a mesma chave que o Supabase dá a esta função
 *  ou a chave antiga do robô (JWT service_role, a do GitHub) — essa quem confere é o próprio banco: só o papel do robô executa
 *  radar_pendencia_assunto (a pergunta é por um assunto que não existe; não muda nada). */
async function ehRobo(req: Request): Promise<boolean> {
  const auth = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "").trim(), apikey = (req.headers.get("apikey") ?? "").trim();
  const chaves = [env("SUPABASE_SERVICE_ROLE_KEY").trim()];
  try { chaves.push(...Object.values(JSON.parse(env("SUPABASE_SECRET_KEYS") || "{}") ?? {}).filter((v): v is string => typeof v === "string")); }
  catch { /* sem a lista nova */ }
  if (chaves.some((k) => k.length >= 20 && (k === auth || k === apikey))) return true;
  if (!ehJwt(auth)) return false;
  let papel = "";
  try { papel = String(JSON.parse(atob(auth.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")))?.role ?? ""); } catch { return false; }
  if (papel !== "service_role") return false;
  try { await banco({ apikey: auth, Authorization: "Bearer " + auth }, "POST", "rpc/radar_pendencia_assunto", { p_assunto: 0 }, 10_000); return true; }
  catch { return false; }
}

/** Quem chamou: o administrador logado (devolve a sessão dele) ou o robô (null). Qualquer outro é recusado. */
async function quemChamou(req: Request): Promise<string | null> {
  if (await ehRobo(req)) return null;
  const token = req.headers.get("Authorization") ?? "";
  if (!/^Bearer\s+\S+/.test(token)) throw new Erro(401, "Sessão não informada.");
  const papel = await banco(token, "POST", "rpc/radar_papel", {});
  if (papel !== "admin") throw new Erro(403, "Só o administrador publica no Instagram e no Facebook.");
  return token;
}

// ------------------------------------------------------------------ Meta
function configMeta(canal?: string) {
  const precisa = ["META_PAGE_ID", "META_PAGE_TOKEN", ...(canal === "facebook" ? [] : ["META_IG_USER_ID"])];
  return { faltam: precisa.filter((n) => !env(n).trim()), pagina: env("META_PAGE_ID").trim(),
           token: env("META_PAGE_TOKEN").trim(), ig: env("META_IG_USER_ID").trim() };
}

// v0.14.1: token da Página obtido a partir do META_PAGE_TOKEN (fica guardado enquanto a função estiver de pé; só o que deu certo)
let tokenGuardado: { de: string; token: string; origem: string } | null = null;
/** Token para falar com a Página e com o Instagram. Com o token do usuário do sistema, a Meta devolve o token da Página;
 *  se o cadastrado já for o token da Página, ele é usado como está. Se o token não alcança a Página, para AQUI, antes de publicar. */
async function tokenDaPagina(): Promise<{ token: string; origem: string }> {
  const c = configMeta("facebook");
  if (tokenGuardado?.de === c.token) return tokenGuardado;
  // Meta fora do ar não vira "token sem acesso": só a recusa da Meta segue para a conferência abaixo
  const d = await chamarMeta("GET", c.pagina, { fields: "access_token" }, c.token)
    .catch((e) => { if (e instanceof Erro && e.status === 504) throw e; return null; });
  let r: { token: string; origem: string } | null = null;
  if (typeof d?.access_token === "string" && d.access_token) {
    r = { token: d.access_token, origem: d.access_token === c.token ? "META_PAGE_TOKEN é o token da própria Página"
                                                                    : "token da Página obtido pelo token do usuário do sistema" };
  } else {
    const eu = await chamarMeta("GET", "me", { fields: "id" }, c.token);    // erro de token (190) aparece aqui, em português
    if (String(eu?.id ?? "") === c.pagina) r = { token: c.token, origem: "META_PAGE_TOKEN é o token da própria Página" };
  }
  if (!r) throw new Erro(502, "O token cadastrado (META_PAGE_TOKEN) não alcança a Página do META_PAGE_ID. No Business, em Usuários do sistema → " +
    "Atribuir ativos → Páginas, dê à Página da Artecon controle total para o usuário do sistema e confira o META_PAGE_ID.");
  tokenGuardado = { de: c.token, ...r };
  return tokenGuardado;
}

/** Chama a Graph API com o token da Página. */
async function meta(metodo: "GET" | "POST" | "DELETE", caminho: string, params: Record<string, string>, publicacao = false): Promise<any> {
  const { token } = await tokenDaPagina();
  try { return await chamarMeta(metodo, caminho, params, token, publicacao); }
  catch (e) { if (e instanceof Erro && /\(190\)/.test(e.message)) tokenGuardado = null; throw e; }   // token revogado: busca de novo na próxima
}

/** v0.14.4: chamadas do Instagram usam o META_IG_TOKEN (aplicativo do Instagram) quando ele existe. */
async function metaIg(metodo: "GET" | "POST" | "DELETE", caminho: string, params: Record<string, string>, publicacao = false): Promise<any> {
  const ig = env("META_IG_TOKEN").trim();
  return ig ? chamarMeta(metodo, caminho, params, ig, publicacao, "META_IG_TOKEN") : meta(metodo, caminho, params, publicacao);
}

/** Chama a Graph API. O token vai no corpo/consulta e nunca aparece em mensagem de erro. */
async function chamarMeta(metodo: "GET" | "POST" | "DELETE", caminho: string, params: Record<string, string>, token: string,
                          publicacao = false, segredo = "META_PAGE_TOKEN"): Promise<any> {
  const c = configMeta("facebook");
  const p = new URLSearchParams({ ...params, access_token: token });
  const tempo = publicacao ? TEMPO_PUBLICAR_MS : metodo === "GET" ? 8_000 : 30_000;
  const incerto = () => new Incerto(504, "A Meta não respondeu se a publicação saiu. Confira na rede antes de qualquer coisa: " +
    "se saiu, não publique de novo; se não saiu, espere 10 minutos, cancele a autorização e autorize de novo.");
  let r: Response;
  try {
    r = metodo !== "POST"
      ? await fetch(`${GRAPH}/${caminho}?${p}`, { method: metodo, signal: AbortSignal.timeout(tempo) })
      : await fetch(`${GRAPH}/${caminho}`, { method: "POST", body: p, signal: AbortSignal.timeout(tempo),
                                             headers: { "Content-Type": "application/x-www-form-urlencoded" } });
  } catch {
    if (publicacao) throw incerto();
    throw new Erro(504, "Não foi possível falar com a Meta agora. Tente de novo em alguns minutos.");
  }
  if (publicacao && r.status >= 500) throw incerto();               // erro do lado da Meta: não dá para saber se saiu
  const d: any = await r.json().catch(() => ({}));
  if (!r.ok || d?.error) {
    const e = d?.error ?? {};
    const msg = String(e.error_user_msg || e.message || `erro ${r.status}`).slice(0, 300);
    const limpa = [c.token, token, env("META_IG_TOKEN").trim()].filter(Boolean).reduce((m, t) => m.split(t).join("***"), msg);
    const dica = e.code === 190 ? ` O token venceu, foi revogado ou foi copiado errado: gere outro no Business (Usuários do sistema) e troque o ${segredo}.`
      : e.code === 10 || e.code === 200 ? " Falta permissão no aplicativo da Meta (instagram_content_publish / pages_manage_posts)."
      : e.code === 4 || e.code === 32 || e.code === 613 ? " Limite de publicações da Meta atingido: tente mais tarde." : "";
    throw new Erro(502, `A Meta recusou (${e.code ?? r.status}): ${limpa}.${dica}`);
  }
  return d;
}

// ------------------------------------------------------------------ armazenamento público da imagem
async function garantirBucket() {
  const r = await fetch(`${SUPABASE_URL}/storage/v1/bucket/${BUCKET}`, { headers: comoServico() });
  await r.body?.cancel();
  if (r.ok) return;
  const c = await fetch(`${SUPABASE_URL}/storage/v1/bucket`, {
    method: "POST", headers: { ...comoServico(), "Content-Type": "application/json" },
    body: JSON.stringify({ id: BUCKET, name: BUCKET, public: true, file_size_limit: 8 * 1024 * 1024, allowed_mime_types: ["image/jpeg"] }),
  });
  const d: any = await c.json().catch(() => ({}));
  // já existe (o Supabase responde 409, ou 400 com statusCode "409"): está pronto
  if (c.ok || c.status === 409 || String(d?.statusCode ?? "") === "409") return;
  throw new Erro(502, `Não foi possível criar o armazenamento das imagens (${c.status}${d?.message ? ": " + String(d.message).slice(0, 120) : ""}).`);
}

async function enviarImagem(dataUrl: string, nome: string): Promise<string> {
  const m = /^data:image\/jpeg;base64,([A-Za-z0-9+/=]+)$/.exec(dataUrl);
  if (!m) throw new Erro(400, "A imagem da publicação não é um JPEG válido.");
  const bytes = Uint8Array.from(atob(m[1]), (ch) => ch.charCodeAt(0));
  await garantirBucket();
  const r = await fetch(`${SUPABASE_URL}/storage/v1/object/${BUCKET}/${nome}`, {
    method: "POST", body: bytes,
    headers: { ...comoServico(), "Content-Type": "image/jpeg", "x-upsert": "true" },
  });
  if (!r.ok) throw new Erro(502, `Não foi possível guardar a imagem para a Meta (${r.status}).`);
  return `${SUPABASE_URL}/storage/v1/object/public/${BUCKET}/${nome}`;
}

// ------------------------------------------------------------------ publicar
const dormir = (ms: number) => new Promise((ok) => setTimeout(ok, ms));
const aindaDaTempo = (inicio: number) => {
  if (Date.now() - inicio > LIMITE_PUBLICAR_MS) throw new Erro(504, "A Meta demorou para preparar a publicação. Nada foi publicado: tente de novo.");
};

async function publicarInstagram(imagemUrl: string, legenda: string, inicio: number) {
  const c = configMeta("instagram");
  const cont = await metaIg("POST", `${c.ig}/media`, { image_url: imagemUrl, caption: legenda });
  for (let t = 0; t * PASSO_IG_MS <= ESPERA_IG_MS && Date.now() - inicio < LIMITE_PUBLICAR_MS; t++) {
    const s = await metaIg("GET", cont.id, { fields: "status_code" });
    if (s.status_code === "FINISHED") break;
    if (s.status_code === "ERROR" || s.status_code === "EXPIRED") throw new Erro(502, "O Instagram não aceitou a imagem (contêiner com erro).");
    if ((t + 1) * PASSO_IG_MS > ESPERA_IG_MS) throw new Erro(504, "O Instagram demorou para processar a imagem. Tente de novo.");
    await dormir(PASSO_IG_MS);
  }
  aindaDaTempo(inicio);
  const pub = await metaIg("POST", `${c.ig}/media_publish`, { creation_id: cont.id }, true);
  let url = "";
  try { url = (await metaIg("GET", pub.id, { fields: "permalink" })).permalink ?? ""; } catch { /* o post saiu; o link é só conveniência */ }
  return { post_id: String(pub.id), url };
}

async function publicarFacebook(imagemUrl: string, legenda: string, inicio: number) {
  const c = configMeta("facebook");
  aindaDaTempo(inicio);
  const pub = await meta("POST", `${c.pagina}/photos`, { url: imagemUrl, message: legenda }, true);
  const post = String(pub.post_id ?? pub.id);
  let url = "";
  try { url = (await meta("GET", post, { fields: "permalink_url" })).permalink_url ?? ""; } catch { /* idem */ }
  return { post_id: post, url };
}

async function publicar(envio: number, inicio: number, peloRobo = false) {
  const servico = comoServico();
  // confere a configuração ANTES de pegar a autorização: sem a Meta configurada, ela continua aguardando
  const [linha] = await banco(servico, "GET", `radar_redes_envios?select=canal,situacao,junto_com_site&id=eq.${envio}`);
  if (!linha) throw new Erro(404, "Autorização não encontrada.");
  // v0.17.0: o robô só manda o que o administrador autorizou junto com o site ("Publicar em todos")
  if (peloRobo && !linha.junto_com_site) throw new Erro(403, "O robô só publica o que foi autorizado junto com o site.");
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
    const r = e.canal === "instagram" ? await publicarInstagram(imagemUrl, e.legenda, inicio) : await publicarFacebook(imagemUrl, e.legenda, inicio);
    // saiu: o registro tenta duas vezes; se não entrar, a autorização fica "enviando" (nunca "erro", que deixaria publicar de novo)
    const fim = { p_envio: envio, p_ok: true, p_post_id: r.post_id, p_url: r.url || null, p_imagem_url: imagemUrl, p_erro: null };
    try { await banco(servico, "POST", "rpc/radar_rede_concluir", fim, 15_000); }
    catch { try { await dormir(500); await banco(servico, "POST", "rpc/radar_rede_concluir", fim, 15_000); }
            catch { return { situacao: "publicado", url: r.url, post_id: r.post_id,
                             mensagem: "Publicado, mas o registro no Radar não entrou. Não publique de novo." }; } }
    return { situacao: "publicado", url: r.url, post_id: r.post_id };
  } catch (x) {
    if (x instanceof Incerto) throw x;                                     // fica "enviando": não oferece "tentar de novo"
    const msg = x instanceof Erro ? x.message : "Erro inesperado ao publicar.";
    await banco(servico, "POST", "rpc/radar_rede_concluir",
                { p_envio: envio, p_ok: false, p_post_id: null, p_url: null, p_imagem_url: imagemUrl || null, p_erro: msg }).catch(() => {});
    throw x instanceof Erro ? x : new Erro(500, msg);
  }
}

// ------------------------------------------------------------------ excluir (v0.17.0)
/** Apaga a publicação na rede, a pedido do administrador, e registra (como ele: a função do banco confere o perfil). */
async function excluir(envio: number, sessao: string) {
  const [e] = await banco(comoServico(), "GET", `radar_redes_envios?select=id,canal,situacao,post_id,url&id=eq.${envio}`);
  if (!e) throw new Erro(404, "Publicação não encontrada.");
  if (e.situacao !== "publicado") throw new Erro(400, "Esta publicação não está publicada (já foi excluída ou não saiu).");
  const nome = e.canal === "instagram" ? "Instagram" : "Facebook";
  if (!e.post_id) throw new Erro(400, `O Radar não guardou o número do post no ${nome}: apague direto no ${nome} e clique em “Já apaguei”.`);
  const cfg = configMeta(e.canal);
  if (cfg.faltam.length) throw new Erro(503, `O ${nome} não está configurado: faltam os segredos ${cfg.faltam.join(", ")}.`);
  try {
    const r = e.canal === "instagram" ? await metaIg("DELETE", e.post_id, {}) : await meta("DELETE", e.post_id, {});
    if (r?.success === false) throw new Erro(502, `A Meta não confirmou a exclusão no ${nome}.`);
  } catch (x) {
    // nada é dado como excluído sem a confirmação da Meta ("Unsupported delete request" tanto pode ser post que não existe mais
    // quanto rede que não deixa apagar pelo aplicativo): quem confere e registra, nesse caso, é o administrador
    const msg = x instanceof Erro ? x.message : "Erro inesperado ao excluir.";
    const naoDeixa = /Unsupported delete|\((10|200|3)\)/i.test(msg);
    throw new Erro(x instanceof Erro && x.status < 500 ? x.status : 502,
      (naoDeixa ? `A Meta não deixou apagar este post pelo Radar (${msg.replace(/\.$/, "")}).` : msg) +
      ` Confira no ${nome}: se o post ainda estiver lá, apague direto no ${nome}; depois clique em “Já apaguei” para registrar.`);
  }
  await banco(sessao, "POST", "rpc/radar_rede_marcar_excluida", { p_envio: envio, p_como: "api" });
  return { situacao: "excluido", canal: e.canal };
}

async function diagnostico() {
  const itens: { item: string; ok: boolean; detalhe: string }[] = [];
  const c = configMeta("instagram");
  itens.push({ item: "Segredos da Meta", ok: !c.faltam.length,
               detalhe: c.faltam.length ? "Faltam: " + c.faltam.join(", ") : "META_PAGE_ID, META_PAGE_TOKEN e META_IG_USER_ID cadastrados" });
  if (c.pagina && c.token) {
    try {
      const t = await tokenDaPagina();
      itens.push({ item: "Token de acesso", ok: true, detalhe: t.origem });
    } catch (e) { itens.push({ item: "Token de acesso", ok: false, detalhe: e instanceof Error ? e.message : "erro" }); }
    try {
      const p = await meta("GET", c.pagina, { fields: "name" });
      itens.push({ item: "Página do Facebook", ok: true, detalhe: String(p.name ?? c.pagina) });
    } catch (e) { itens.push({ item: "Página do Facebook", ok: false, detalhe: e instanceof Error ? e.message : "erro" }); }
  }
  if (c.ig && c.token) {
    try {
      const ig = await metaIg("GET", c.ig, { fields: "username" });
      itens.push({ item: "Conta do Instagram", ok: true, detalhe: "@" + String(ig.username ?? c.ig) +
        (env("META_IG_TOKEN").trim() ? " (pelo META_IG_TOKEN)" : " (pelo token da Página)") });
    } catch (e) { itens.push({ item: "Conta do Instagram", ok: false, detalhe: e instanceof Error ? e.message : "erro" }); }
  } else if (c.pagina && c.token) {
    // v0.14.4: sem o META_IG_USER_ID, procura a conta do Instagram ligada à Página e mostra o número a gravar
    try {
      const p = await metaIg("GET", c.pagina, { fields: "instagram_business_account{id,username}" });
      const conta = p?.instagram_business_account;
      itens.push({ item: "Conta do Instagram", ok: false, detalhe: conta?.id
        ? `Encontrada: @${conta.username ?? "?"}. Grave o segredo META_IG_USER_ID = ${conta.id} (Supabase → Edge Functions → Secrets).`
        : "Nenhuma conta do Instagram profissional ligada à Página (ou o token não tem instagram_basic). Ligue a conta à Página no Business." });
    } catch (e) { itens.push({ item: "Conta do Instagram", ok: false, detalhe: e instanceof Error ? e.message : "erro" }); }
  }
  try { await garantirBucket(); itens.push({ item: "Armazenamento das imagens", ok: true, detalhe: `bucket público "${BUCKET}"` }); }
  catch (e) { itens.push({ item: "Armazenamento das imagens", ok: false, detalhe: e instanceof Error ? e.message : "erro" }); }
  return { itens, tudo_certo: itens.every((i) => i.ok), versao: VERSAO };
}

async function tratar(req: Request): Promise<Response> {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  const inicio = Date.now();                                  // por pedido: dois pedidos ao mesmo tempo não dividem o relógio
  try {
    if (req.method !== "POST") throw new Erro(405, "Use POST.");
    if (!SUPABASE_URL) throw new Erro(503, "A função está sem SUPABASE_URL.");
    const sessao = await quemChamou(req);                     // null = o robô do site (só "publicar" do que foi junto com o site)
    const pedido = await req.json().catch(() => ({}));
    const acao = String(pedido?.acao ?? "");
    if (!["publicar", "excluir", "diagnostico"].includes(acao)) throw new Erro(400, "Ação desconhecida.");
    if (sessao === null && acao !== "publicar") throw new Erro(403, "O robô só publica o que foi autorizado junto com o site.");
    if (acao === "diagnostico") return responder(200, await diagnostico());
    const envio = Number(pedido?.envio);
    if (!Number.isSafeInteger(envio) || envio <= 0) throw new Erro(400, "Informe a autorização (envio).");
    if (acao === "excluir") {
      const x = await excluir(envio, sessao as string);
      console.log(`radar-redes: envio ${envio} → excluído`);
      return responder(200, x);
    }
    const r = await publicar(envio, inicio, sessao === null);
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
