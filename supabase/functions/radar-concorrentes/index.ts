// =====================================================================
// RADAR ARTECON — Edge Function "radar-concorrentes" (v0.19.1, opcional) — SOMENTE LEITURA
//
// Lê, pela API oficial da Meta (Instagram Graph API, "Business Discovery"), os dados públicos de perfis comerciais (ou de
// criador) do Instagram de outros escritórios de contabilidade e dos posts recentes deles, para a análise de engajamento
// (que formatos e temas funcionam). Não publica nada, não grava nada no banco e não guarda imagem: só devolve o que a Meta
// mostra. A análise serve para formatos e temas, nunca para copiar posts (Código de Ética Profissional do Contador).
//
// Quem pode chamar ("Verify JWT" DESLIGADO no deploy, como a radar-itc: a função confere sozinha):
//   * o banco (net.http_post, veja o fim de sql/radar-concorrentes.sql) ou um script, com o cabeçalho x-radar-chave — a chave
//     fica no Vault e quem confere é public.radar_concorrentes_conferir, que só a chave interna executa;
//   * o administrador logado (Authorization: Bearer <sessão>).
//
// Ações:
//   ler (padrão)  { perfis: ["usuario", ...], posts: 50 } → conta e posts recentes de cada perfil (1 a 12 perfis; 1 a 100 posts)
//   diagnostico                                           → confere os segredos e lê a própria conta da Artecon pela Business
//                                                           Discovery (prova que a permissão funciona)
//
// Como lê: GET /{META_IG_USER_ID}?fields=business_discovery.username(<u>){conta,media.limit(<n>){posts}} e, para o resto dos
// posts, media.after(<cursor>).limit(...) (nessa consulta a Meta não devolve os links next/previous, só paging.cursors.after).
// Se a Meta recusar um campo (#100), tenta de novo sem view_count e depois sem media_product_type. Um perfil com erro não
// derruba os outros. O que NÃO dá para ler: alcance, salvamentos, compartilhamentos, visitas e clientes (dados privados de cada
// conta); curtidas ocultas pelo dono voltam como null.
//
// Privacidade: o registro (log) só tem contagens e códigos de erro da Meta — nunca nome de perfil, legenda ou token.
//
// Segredos (Supabase → Edge Functions → Secrets), os mesmos da radar-redes:
//   META_IG_USER_ID   id da conta do Instagram profissional da Artecon (a consulta é feita "a partir" dela)
//   META_IG_TOKEN     token do usuário do sistema do aplicativo "Radar Artecon Publicações", com instagram_basic e
//                     instagram_manage_insights (esta é a que a Business Discovery exige). Sem ele, a função responde 503:
//                     o META_PAGE_TOKEN não é usado aqui (só entra na limpeza das mensagens de erro)
//   META_GRAPH_URL    opcional; padrão https://graph.facebook.com/v23.0
// SUPABASE_URL, a chave pública (SUPABASE_PUBLISHABLE_KEYS ou SUPABASE_ANON_KEY) e a chave interna (SUPABASE_SECRET_KEYS ou
// SUPABASE_SERVICE_ROLE_KEY) o Supabase já fornece.
// =====================================================================

const VERSAO = "0.22.0";                 // v0.22.0 (rodada 2): a chave pública nova (SUPABASE_PUBLISHABLE_KEYS)
const env = (nome: string, padrao = "") => Deno.env.get(nome) ?? padrao;

const SUPABASE_URL = env("SUPABASE_URL").replace(/\/+$/, "");
// v0.22.0 (rodada 2 da varredura geral): a chave pública do projeto, para o apikey dos pedidos feitos com o token de quem chamou. A
// nova (sb_publishable_…, em SUPABASE_PUBLISHABLE_KEYS) vem antes: a anon antiga (SUPABASE_ANON_KEY, JWT) o Supabase desliga até o
// fim de 2026, e desligada ela seria recusada no apikey. Sem a lista nova, fica a anon.
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
const MAX_PERFIS = 12, MAX_POSTS = 100, POSTS_PADRAO = 50;
// posts por chamada à Meta; se ela pedir menos dados ("reduce the amount of data"), o lote cai pela metade até 10
const POR_PAGINA = 50, MENOR_LOTE = 10, MAX_PAGINAS = 20;
// O Supabase encerra a chamada perto de 150 s: cada chamada à Meta espera até 15 s e o pedido inteiro trabalha até 120 s.
// Um perfil (ou a página seguinte de posts) só começa se sobrarem 5 s; os perfis que não couberem voltam para pedir de novo.
const PRAZO_META_MS = Number(env("RADAR_CONCORRENTES_PRAZO_MS", "15000"));           // só os testes trocam
const ORCAMENTO_MS = Number(env("RADAR_CONCORRENTES_ORCAMENTO_MS", "120000"));
const COMECAR_MS = Math.min(5_000, PRAZO_META_MS / 3);
const NAO_COUBE = "não coube no tempo; peça de novo só esses";
// o nome do perfil vai dentro da consulta da Graph API: só letras minúsculas, números, ponto e sublinhado (nada de injeção)
const USUARIO = /^[a-z0-9._]{1,30}$/;
// o cursor da Meta também vai dentro da consulta: base64 (com + / =, ou - _ na versão para endereço), % e ponto; nada de
// parêntese, chave, vírgula ou espaço, que mudariam a consulta da Graph API
const CURSOR = /^[A-Za-z0-9_\-=%.+\/]{1,2048}$/;
const CAMPOS_CONTA = "username,name,biography,website,followers_count,follows_count,media_count";
const CAMPOS_POST = ["id", "caption", "media_type", "media_product_type", "timestamp", "like_count", "comments_count", "view_count",
                     "permalink", "media_url", "thumbnail_url"];
// campos que saem, nesta ordem, se a Meta recusar (#100 de campo inexistente ou não suportado)
const OPCIONAIS = ["view_count", "media_product_type"];
const AVISO_CAMPO: Record<string, string> = {
  view_count: "a Meta não aceitou o campo view_count: as visualizações ficaram null",
  media_product_type: "a Meta não aceitou o campo media_product_type: o produto (FEED, REELS) ficou null",
};

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

class Erro extends Error {
  status: number;
  constructor(status: number, mensagem: string) { super(mensagem); this.status = status; }
}
/** Recusa ou falha da Meta, já sem o token. "geral" = vale para qualquer perfil (token, permissão, limite, conta da Artecon):
 *  os perfis seguintes nem são pedidos. "bruta" guarda a mensagem da Meta (sem o token) para reconhecer o tipo de recusa. */
class ErroMeta extends Erro {
  codigo: number | null; sub: number | null; bruta: string; geral: boolean;
  constructor(status: number, mensagem: string, o: { codigo?: number | null; sub?: number | null; bruta?: string; geral?: boolean } = {}) {
    super(status, mensagem);
    this.codigo = o.codigo ?? null; this.sub = o.sub ?? null; this.bruta = o.bruta ?? ""; this.geral = o.geral ?? false;
  }
}
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
/** Cabeçalhos para falar com o banco como a própria função (acima das regras de acesso). */
const comoServico = (): Record<string, string> => {
  const k = chaveInterna();
  if (!k) throw new Erro(503, "A função está sem a chave interna do Supabase (SUPABASE_SECRET_KEYS ou SUPABASE_SERVICE_ROLE_KEY).");
  return ehJwt(k) ? { apikey: k, Authorization: "Bearer " + k } : { apikey: k };
};

/** Quem chamou: o banco ou um script com a chave do Vault, ou o administrador logado. Qualquer outro é recusado (401/403).
 *  A recusa da chave é sempre a mesma frase: não diz se a conferência existe, falhou ou se a chave só está errada. */
async function autorizar(req: Request): Promise<"chave" | "admin"> {
  const chave = (req.headers.get("x-radar-chave") ?? "").trim();
  if (chave) {
    let ok = false;
    if (chave.length >= 32 && chave.length <= 200) {
      try { ok = (await banco(comoServico(), "POST", "rpc/radar_concorrentes_conferir", { p_chave: chave }, 10_000)) === true; }
      catch (e) {
        if (e instanceof Erro && e.status === 503) throw e;                       // função sem a chave interna: configuração
        console.log(`radar-concorrentes: conferência da chave falhou (${e instanceof Erro ? e.status : "sem resposta do banco"})`);
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
  if (papel !== "admin") throw new Erro(403, "Só o administrador lê os perfis dos concorrentes.");
  return "admin";
}

// ------------------------------------------------------------------ Meta
const faltamSegredos = () => ["META_IG_USER_ID", "META_IG_TOKEN"].filter((n) => !env(n).trim());
const explicarFalta = (faltam: string[]) => `Faltam os segredos ${faltam.join(", ")} (Supabase → Edge Functions → Secrets).` +
  (faltam.includes("META_IG_TOKEN") ? " Esta função usa só o META_IG_TOKEN (token do aplicativo \"Radar Artecon Publicações\", com " +
    "instagram_basic e instagram_manage_insights); o META_PAGE_TOKEN não é usado aqui." : "");

/** Relógio do pedido (orçamento total), os códigos de erro da Meta vistos (para o registro) e a recusa que vale para todos os
 *  perfis (token, permissão, limite): depois dela, os perfis seguintes nem são pedidos. */
type Contexto = { resta: () => number; codigos: Set<string>; geral: string };
const contexto = (inicio: number): Contexto => ({ resta: () => ORCAMENTO_MS - (Date.now() - inicio), codigos: new Set(), geral: "" });

/** Tira da mensagem qualquer token cadastrado (a Meta às vezes repete o token recebido). */
const limpar = (m: string) => [env("META_IG_TOKEN").trim(), env("META_PAGE_TOKEN").trim()].filter(Boolean)
  .reduce((s, t) => s.split(t).join("***"), m);

/** A recusa da Meta em português, com o código (para conferir na documentação da Meta). */
function traduzir(codigo: number | null, sub: number | null, bruta: string, status: number): { mensagem: string; geral: boolean } {
  const cod = `Meta ${codigo ?? "HTTP " + status}${sub ? "/" + sub : ""}`;
  if (codigo === 110 || sub === 2207013) {
    return { geral: false, mensagem: `conta não encontrada ou não é comercial/criador (a Meta só mostra perfis comerciais ou de criador) (${cod})` };
  }
  if (codigo === 190) {
    return { geral: true, mensagem: "o token da Meta venceu, foi revogado ou foi copiado errado: gere outro no Business (Usuários do " +
      `sistema) e troque o segredo META_IG_TOKEN (${cod})` };
  }
  if (codigo === 10 || (codigo !== null && codigo >= 200 && codigo <= 299) || /instagram_manage_insights/i.test(bruta)) {
    return { geral: true, mensagem: "falta permissão no META_IG_TOKEN: o aplicativo \"Radar Artecon Publicações\" precisa de " +
      `instagram_basic e instagram_manage_insights (${cod})` };
  }
  if (codigo !== null && [4, 17, 32, 613, 80002].includes(codigo)) {
    return { geral: true, mensagem: `limite de chamadas da Meta atingido: espere cerca de 1 hora e peça de novo (${cod})` };
  }
  if (codigo === 100 && (sub === 33 || /nonexisting field \(business_discovery\)/i.test(bruta))) {
    return { geral: true, mensagem: `o META_IG_USER_ID não é a conta do Instagram profissional da Artecon que o token alcança (${cod})` };
  }
  return { geral: false, mensagem: `a Meta recusou (${cod}): ${bruta}` };
}

/** O prazo da chamada acabou? (vem como DOMException "TimeoutError"; "AbortError" em versões antigas) */
const ehPrazo = (e: unknown) => ["TimeoutError", "AbortError"].includes(String((e as { name?: unknown } | null)?.name ?? ""));
/** Erro de prazo estourado: "não coube no tempo" se o orçamento acabou; senão, "não respondeu em N s". */
function semResposta(prazo: number, ctx: Contexto): never {
  ctx.codigos.add("sem_resposta");
  if (ctx.resta() < 100) throw new ErroMeta(504, NAO_COUBE);
  throw new ErroMeta(504, `a Meta não respondeu em ${Math.round(prazo / 1000)} s; tente de novo em alguns minutos`);
}

/** GET na Graph API com o META_IG_TOKEN. O token vai na consulta e nunca aparece em mensagem de erro nem no registro. */
async function chamarMeta(caminho: string, fields: string, ctx: Contexto): Promise<any> {
  const resta = ctx.resta();
  if (resta < 100) throw new ErroMeta(504, NAO_COUBE);
  const prazo = Math.min(PRAZO_META_MS, resta);
  const p = new URLSearchParams({ fields, access_token: env("META_IG_TOKEN").trim() });
  let r: Response;
  try {
    r = await fetch(`${GRAPH}/${encodeURIComponent(caminho)}?${p}`, { signal: AbortSignal.timeout(prazo) });
  } catch (e) {
    // a mensagem de erro do fetch pode trazer o endereço (com o token): nunca é usada, só o tipo do erro
    if (ehPrazo(e)) semResposta(prazo, ctx);
    // falhou na hora: conexão recusada, DNS, TLS ou META_GRAPH_URL errado — esperar não adianta, é rede ou configuração
    ctx.codigos.add("rede");
    throw new ErroMeta(502, "não foi possível falar com a Meta (rede ou META_GRAPH_URL errado); tente de novo em alguns minutos");
  }
  // o prazo também vale para a leitura do corpo: corpo atrasado é "não respondeu", não "ilegível"
  let d: any = null;
  try { d = await r.json(); } catch (e) { if (ehPrazo(e)) semResposta(prazo, ctx); }
  if (!d) {
    ctx.codigos.add("ilegivel");
    if (ctx.resta() < 100) throw new ErroMeta(504, NAO_COUBE);
    throw new ErroMeta(502, `a Meta devolveu uma resposta ilegível (HTTP ${r.status}); tente de novo`);
  }
  if (!r.ok || d.error) {
    const e = d.error ?? {};
    const codigo = Number.isInteger(e.code) ? Number(e.code) : null, sub = Number.isInteger(e.error_subcode) ? Number(e.error_subcode) : null;
    const bruta = limpar([e.message, e.error_user_msg].filter((x) => typeof x === "string" && x).join(" — ") || `erro ${r.status}`).slice(0, 300);
    ctx.codigos.add(String(codigo ?? "http" + r.status) + (sub ? "/" + sub : ""));
    const t = traduzir(codigo, sub, bruta, r.status);
    throw new ErroMeta(502, t.mensagem, { codigo, sub, bruta, geral: t.geral });
  }
  return d;
}

/** Recusa de campo da Meta (#100 de campo inexistente ou não suportado) que não é a da conta da Artecon (essa é "geral"). */
const recusaDeCampo = (e: unknown): e is ErroMeta => e instanceof ErroMeta && e.codigo === 100 && !e.geral && /field/i.test(e.bruta);
// campos que a recusa pode citar pelo nome ("name" e "id" ficam de fora: são palavras comuns nas mensagens da Meta)
const CITAVEIS = [...CAMPOS_POST, ...CAMPOS_CONTA.split(",")].filter((c) => c !== "id" && c !== "name");
/** O campo que a Meta citou na recusa — de qualquer nó, da conta ou dos posts, mesmo fora das nossas listas; null se não citou. */
function campoCitado(bruta: string): string | null {
  const m = /nonexisting field \((\w+)\)/i.exec(bruta);
  return m ? m[1] : CITAVEIS.find((c) => new RegExp(`\\b${c}\\b`).test(bruta)) ?? null;
}
/** Campo recusado pela Meta que dá para tirar e tentar de novo; null se não for recusa de campo ou se o campo for essencial. */
function campoRecusado(e: unknown, campos: string[]): string | null {
  if (!recusaDeCampo(e)) return null;
  const citado = campoCitado(e.bruta);
  // citou um campo: só sai se for opcional (e ainda estiver na consulta); essencial ou de outro nó: não há o que tirar
  if (citado) return OPCIONAIS.includes(citado) && campos.includes(citado) ? citado : null;
  return OPCIONAIS.find((c) => campos.includes(c)) ?? null;               // não disse qual: tira na ordem de OPCIONAIS
}
/** A Meta pediu menos dados por chamada (acontece com muitos posts e legendas longas). */
const pedeMenos = (e: unknown) => e instanceof ErroMeta && !e.geral && (e.codigo === 1 || /reduce the amount of data/i.test(e.bruta));

const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const txt = (v: unknown) => (typeof v === "string" && v ? v : null);

function post(m: any) {
  const tipo = txt(m?.media_type);
  return {
    id: String(m?.id ?? ""), data: txt(m?.timestamp), tipo, produto: txt(m?.media_product_type),
    curtidas: num(m?.like_count),                        // a Meta não manda o campo quando o dono oculta as curtidas
    comentarios: num(m?.comments_count), visualizacoes: num(m?.view_count),
    legenda: typeof m?.caption === "string" ? m.caption : "", link: txt(m?.permalink),
    // em vídeo, media_url é o arquivo do vídeo: a imagem é a capa (thumbnail_url)
    imagem: tipo === "VIDEO" ? (txt(m?.thumbnail_url) ?? txt(m?.media_url)) : (txt(m?.media_url) ?? txt(m?.thumbnail_url)),
  };
}

/** Campos dos posts pedidos nesta chamada: o que a Meta recusar sai também para os perfis seguintes. */
type Pedido = { campos: string[]; retirados: string[] };
type Perfil = { usuario: string; ok: true; conta: Record<string, unknown>; posts: ReturnType<typeof post>[]; aviso?: string };
type Falha = { usuario: string; ok: false; erro: string };

/** Conta e posts recentes de um perfil (até n), em páginas. Erro na primeira página: o perfil volta com erro (lança). */
async function lerPerfil(u: string, n: number, pedido: Pedido, ctx: Contexto): Promise<Perfil> {
  const ig = env("META_IG_USER_ID").trim();
  let lote = POR_PAGINA;
  /** Uma página: a primeira traz também a conta; as outras, só os posts depois do cursor. */
  const pagina = async (falta: number, cursor: string | null): Promise<any> => {
    for (;;) {
      const limite = Math.min(falta, lote);
      const midia = `${cursor ? `media.after(${cursor})` : "media"}.limit(${limite}){${pedido.campos.join(",")}}`;
      try {
        const d = await chamarMeta(ig, `business_discovery.username(${u}){${cursor ? midia : CAMPOS_CONTA + "," + midia}}`, ctx);
        const bd = d?.business_discovery;
        if (!bd || typeof bd !== "object") throw new ErroMeta(502, "a Meta respondeu sem os dados do perfil; tente de novo");
        return bd;
      } catch (e) {
        const campo = campoRecusado(e, pedido.campos);
        if (campo) {
          pedido.campos = pedido.campos.filter((c) => c !== campo);
          pedido.retirados.push(campo);
          continue;
        }
        if (pedeMenos(e) && limite > MENOR_LOTE) { lote = Math.max(MENOR_LOTE, Math.ceil(limite / 2)); continue; }
        // campo essencial recusado na 1ª página: a consulta é a mesma para todos os perfis, então vale para todos (não insiste).
        // Numa página seguinte a 1ª já funcionou com os mesmos campos: a recusa é só deste perfil e vira aviso dele
        if (recusaDeCampo(e) && !cursor) e.geral = true;
        throw e;
      }
    }
  };

  const bd = await pagina(n, null);
  const vistos = new Set<string>(), brutos: any[] = [], avisos: string[] = [];
  let media = bd.media;
  for (let paginas = 1; ; paginas++) {
    const dados: any[] = Array.isArray(media?.data) ? media.data : [];
    let novos = 0;
    for (const m of dados) {
      const id = String(m?.id ?? "");
      if (!m || !id || vistos.has(id)) continue;
      vistos.add(id);
      brutos.push(m);
      novos++;
    }
    const cursor = media?.paging?.cursors?.after;
    // fim normal: completou o pedido, ou acabaram os posts (página vazia ou sem cursor para a seguinte)
    if (brutos.length >= n || !dados.length || cursor === undefined || cursor === null || cursor === "") break;
    // as outras paradas deixam o perfil com menos posts do que o pedido: sem o aviso, ele pareceria completo
    const parada = !novos ? "a Meta repetiu os posts da página anterior"
      : typeof cursor !== "string" || !CURSOR.test(cursor) ? "a Meta não mandou como continuar"
      : paginas >= MAX_PAGINAS ? `a Meta mandou poucos posts por página e a leitura parou em ${MAX_PAGINAS} páginas` : "";
    if (parada) {
      avisos.push(`vieram ${brutos.length} dos ${n} posts pedidos: ${parada}`);
      break;
    }
    if (ctx.resta() < COMECAR_MS) {
      avisos.push(`vieram ${brutos.length} dos ${n} posts pedidos: o tempo da chamada acabou (peça de novo este perfil sozinho)`);
      break;
    }
    try { media = (await pagina(n - brutos.length, cursor)).media; }
    catch (e) {
      // os posts que já vieram ficam; a página que falhou vira aviso
      if (e instanceof ErroMeta && e.geral) ctx.geral = e.message;
      avisos.push(`vieram ${brutos.length} dos ${n} posts pedidos: ${e instanceof Erro && e.message !== NAO_COUBE ? e.message
        : "o tempo da chamada acabou (peça de novo este perfil sozinho)"}`);
      break;
    }
  }
  avisos.unshift(...pedido.retirados.map((c) => AVISO_CAMPO[c]));
  const r: Perfil = {
    usuario: u, ok: true,
    conta: { username: txt(bd.username) ?? u, name: txt(bd.name), biografia: txt(bd.biography), site: txt(bd.website),
             seguidores: num(bd.followers_count), seguindo: num(bd.follows_count), posts_total: num(bd.media_count) },
    posts: brutos.slice(0, n).map(post),
  };
  if (avisos.length) r.aviso = avisos.join("; ") + ".";
  return r;
}

// ------------------------------------------------------------------ ações
async function ler(perfis: string[], n: number, inicio: number, quem: string) {
  const ctx = contexto(inicio);
  const pedido: Pedido = { campos: [...CAMPOS_POST], retirados: [] };
  const saida: (Perfil | Falha)[] = [];
  for (const u of perfis) {                          // um de cada vez: o limite de chamadas da Meta agradece
    if (ctx.geral) { saida.push({ usuario: u, ok: false, erro: ctx.geral }); continue; }   // não insiste
    if (ctx.resta() < COMECAR_MS) { saida.push({ usuario: u, ok: false, erro: NAO_COUBE }); continue; }
    try { saida.push(await lerPerfil(u, n, pedido, ctx)); }
    catch (e) {
      if (e instanceof ErroMeta && e.geral) ctx.geral = e.message;
      if (!(e instanceof Erro)) console.error("radar-concorrentes: erro inesperado num perfil", e instanceof Error ? e.name : "");
      saida.push({ usuario: u, ok: false, erro: e instanceof Erro ? e.message : "erro inesperado ao ler este perfil" });
    }
  }
  const lidos = saida.filter((p): p is Perfil => p.ok);
  // só contagens e códigos: nome de perfil, legenda e token nunca vão para o registro
  console.log(`radar-concorrentes (${quem}): ${perfis.length} perfil(s), ${lidos.length} lido(s), ${perfis.length - lidos.length} com erro, ` +
    `${lidos.reduce((s, p) => s + p.posts.length, 0)} post(s)` + (pedido.retirados.length ? `, campos retirados: ${pedido.retirados.join(",")}` : "") +
    (ctx.codigos.size ? `, códigos da Meta: ${[...ctx.codigos].join(",")}` : ""));
  return { versao: VERSAO, perfis: saida };
}

async function diagnostico(inicio: number) {
  const itens: { item: string; ok: boolean; detalhe: string }[] = [];
  itens.push({ item: "Função radar-concorrentes instalada", ok: true, detalhe: `versão ${VERSAO} (somente leitura)` });
  const faltam = faltamSegredos();
  itens.push({ item: "Segredos da Meta", ok: !faltam.length,
               detalhe: faltam.length ? explicarFalta(faltam) : "META_IG_USER_ID e META_IG_TOKEN cadastrados" });
  // a conferência da chave (sql/radar-concorrentes.sql): uma chave qualquer tem de dar "não confere", sem erro
  try {
    const r = await banco(comoServico(), "POST", "rpc/radar_concorrentes_conferir", { p_chave: crypto.randomUUID() + crypto.randomUUID() }, 10_000);
    itens.push({ item: "Chave para chamar pelo banco", ok: r === false, detalhe: r === false ? "instalada (sql/radar-concorrentes.sql)" : "resposta inesperada do banco" });
  } catch {
    itens.push({ item: "Chave para chamar pelo banco", ok: false,
                 detalhe: "não instalada: rode sql/radar-concorrentes.sql no SQL Editor (só é preciso para chamar pelo banco ou por script)" });
  }
  if (!faltam.length) {
    const ctx = contexto(inicio);
    let usuario = "";
    try {
      const eu = await chamarMeta(env("META_IG_USER_ID").trim(), "username", ctx);
      usuario = String(eu?.username ?? "").toLowerCase();
      itens.push({ item: "Conta do Instagram da Artecon", ok: USUARIO.test(usuario),
                   detalhe: USUARIO.test(usuario) ? "@" + usuario : "a Meta não devolveu o nome da conta do META_IG_USER_ID" });
    } catch (e) { itens.push({ item: "Conta do Instagram da Artecon", ok: false, detalhe: e instanceof Error ? e.message : "erro" }); }
    if (USUARIO.test(usuario)) {
      try {
        const pedido: Pedido = { campos: [...CAMPOS_POST], retirados: [] };
        const r = await lerPerfil(usuario, 1, pedido, ctx);
        itens.push({ item: "Leitura de perfis (Business Discovery, instagram_manage_insights)", ok: true,
                     detalhe: `leu a própria conta: ${r.conta.seguidores ?? "?"} seguidores, ${r.conta.posts_total ?? "?"} posts` +
                       (pedido.retirados.length ? `; a Meta não aceitou ${pedido.retirados.join(", ")} (fica null)` : "") });
      } catch (e) {
        itens.push({ item: "Leitura de perfis (Business Discovery, instagram_manage_insights)", ok: false,
                     detalhe: e instanceof Error ? e.message : "erro" });
      }
    }
  }
  return { itens, tudo_certo: itens.every((i) => i.ok), versao: VERSAO };
}

// ------------------------------------------------------------------ pedido
function validarPerfis(lista: unknown): string[] {
  if (!Array.isArray(lista) || lista.length < 1 || lista.length > MAX_PERFIS) {
    throw new Erro(400, `Informe de 1 a ${MAX_PERFIS} perfis em "perfis" (lista de nomes do Instagram).`);
  }
  const perfis: string[] = [];
  lista.forEach((x, i) => {
    const u = typeof x === "string" ? x.trim().replace(/^@/, "").toLowerCase() : "";
    // o nome recusado não volta na resposta: só a posição
    if (!USUARIO.test(u)) {
      throw new Erro(400, `O ${i + 1}º perfil não é um nome válido do Instagram (só letras, números, ponto e sublinhado; até 30, sem espaço).`);
    }
    if (!perfis.includes(u)) perfis.push(u);
  });
  return perfis;
}

function validarPosts(v: unknown): number {
  if (v === undefined || v === null) return POSTS_PADRAO;
  if (typeof v !== "number" || !Number.isInteger(v) || v < 1 || v > MAX_POSTS) {
    throw new Erro(400, `"posts" deve ser um número inteiro de 1 a ${MAX_POSTS} (padrão ${POSTS_PADRAO}).`);
  }
  return v;
}

async function tratar(req: Request): Promise<Response> {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  const inicio = Date.now();                                  // por pedido: dois pedidos ao mesmo tempo não dividem o relógio
  try {
    if (req.method !== "POST") throw new Erro(405, "Use POST.");
    if (!SUPABASE_URL) throw new Erro(503, "A função está sem SUPABASE_URL.");
    const quem = await autorizar(req);
    const pedido = await req.json().catch(() => ({}));
    const acao = String(pedido?.acao ?? "ler");
    if (acao === "diagnostico") {
      const r = await diagnostico(inicio);
      console.log(`radar-concorrentes (${quem}): diagnóstico, ${r.itens.filter((i) => i.ok).length} de ${r.itens.length} item(ns) OK`);
      return responder(200, r);
    }
    if (acao !== "ler") throw new Erro(400, "Ação desconhecida.");
    const perfis = validarPerfis(pedido?.perfis);
    const n = validarPosts(pedido?.posts);
    const faltam = faltamSegredos();
    if (faltam.length) throw new Erro(503, explicarFalta(faltam));
    return responder(200, await ler(perfis, n, inicio, quem));
  } catch (e) {
    if (e instanceof Erro) return responder(e.status, { message: e.message });
    console.error("radar-concorrentes: erro inesperado", e instanceof Error ? e.name : "");
    return responder(500, { message: "Erro inesperado na leitura dos perfis." });
  }
}

const portaLocal = Deno.env.get("RADAR_PORTA_LOCAL");       // só para rodar/testar fora do Supabase
portaLocal ? Deno.serve({ port: Number(portaLocal), hostname: "127.0.0.1" }, tratar) : Deno.serve(tratar);
