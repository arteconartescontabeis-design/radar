// =====================================================================
// RADAR ARTECON — Edge Function "radar-concorrentes" (v0.19.1, opcional) — SÓ LEITURA NA META
//
// Lê, pela API oficial da Meta (Instagram Graph API, "Business Discovery"), os dados públicos de perfis comerciais (ou de
// criador) do Instagram de outros escritórios de contabilidade e dos posts recentes deles, para a análise de engajamento
// (que formatos e temas funcionam). Na Meta, só lê (GET): não publica, comenta, curte ou segue, e não guarda imagem. As ações
// "ler" e "diagnostico" só devolvem o que a Meta mostra, sem gravar nada; desde a v0.34.0, a ação "setor_coletar" grava no banco
// só as métricas da aba Setor (tabelas radar_setor_*, pelas funções do banco), com a legenda cortada em 300 caracteres (veja
// abaixo). A análise serve para formatos e temas, nunca para copiar posts (Código de Ética Profissional do Contador).
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
// v0.34.0 — aba Setor (como estão as publicações de um setor, como a contabilidade). Três ações novas:
//   setor_coletar  (a agenda do banco, com a chave, ou o administrador, pelo botão "Atualizar a análise") → pergunta ao banco quem ler
//                  (radar_setor_iniciar: até 12 contas devidas; o banco decide: uma vez por semana, sem pausa da Meta, nada em dobro),
//                  lê uma conta por vez e grava cada resultado (radar_setor_gravar) antes da seguinte; no fim, fecha a rodada
//                  (radar_setor_concluir) com as chamadas, o uso que a Meta informou e a pausa;
//   setor_propria  (só o administrador) → o @ da conta da Artecon (1 chamada), para o botão "Incluir a conta da Artecon";
//   setor_teste    (a chave ou o administrador) → {ok, versao}, sem tocar na Meta (o teste do fim do sql/radar-setor-agenda.sql).
// Agora a função GRAVA no banco do Radar, mas só nas tabelas da aba Setor e só pelas funções radar_setor_* (pela chave interna). Na
// Meta, continua só fazendo GET: nunca publica, comenta, curte ou segue. Campos pedidos (os oficiais, sem imagem, nome, biografia ou
// site): id, username, followers_count e media_count da conta; id, timestamp, media_type, media_product_type, like_count,
// comments_count, caption e permalink de até 50 publicações (1 chamada por conta; até 3 páginas se a Meta mandar menos por página).
// Limites: 1,5 s de pausa entre as chamadas, até 12 contas por chamada, a mesma @ em dois setores lida uma vez só; lê os cabeçalhos
// X-App-Usage e X-Business-Use-Case-Usage e, com 80% de uso ou com a recusa de limite (4, 17, 32, 613, 80002), para na hora e grava a
// pausa (60 minutos, ou o tempo que a Meta informar, se for maior; o banco limita a 24 horas). Token vencido, permissão ou o
// META_IG_USER_ID errado: para e pausa só a agenda por 6 horas (o botão do administrador continua, para testar depois de trocar o
// token). A legenda vai cortada em 300 caracteres (só para os temas) e as hashtags dela, à parte (até 20).
// A Meta ou a rede fora do ar não é falha da conta: sem conseguir falar com a Meta (rede), ou com duas contas seguidas sem resposta,
// com resposta ilegível ou com os códigos 1 e 2 da Meta (erro desconhecido, serviço indisponível), a rodada para e nenhuma conta leva
// falha; elas continuam devidas e a agenda tenta de novo na hora seguinte (sem pausa). Uma conta só com essa falha (a seguinte leu)
// leva a falha, como antes.
// Hashtag (só com radar_config.setor.hashtag_ligada, depois que a Meta aprovar o Instagram Public Content Access): GET
// /ig_hashtag_search (uma vez na vida de cada hashtag: o banco guarda o número dela; a Meta permite 30 hashtags diferentes a cada 7
// dias) e GET /{hashtag}/top_media (e /recent_media, conforme o modo), até 50 publicações. A recusa da hashtag não para as contas.
// O registro (log) da aba Setor também só tem contagens e códigos: nunca nome de conta, hashtag, legenda ou link.
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

const VERSAO = "0.34.0";                 // v0.34.0: as ações da aba Setor (v0.22.0: a chave pública nova)
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
// v0.34.0: a aba Setor. Só os campos oficiais pedidos: nada de imagem (media_url, thumbnail_url), nome, biografia, site ou view_count
const CAMPOS_CONTA_SETOR = "id,username,followers_count,media_count";
const CAMPOS_POST_SETOR = ["id", "timestamp", "media_type", "media_product_type", "like_count", "comments_count", "caption", "permalink"];
const CAMPOS_HASHTAG = "id,media_type,comments_count,like_count,caption,permalink,timestamp";
const MAX_CONTAS_SETOR = 12, MAX_PAGINAS_SETOR = 3, LEGENDA_MAX = 300, HASHTAGS_MAX = 20, USO_LIMITE = 80;
const PAUSA_MS = Number(env("RADAR_SETOR_PAUSA_MS", "1500"));                       // entre uma chamada à Meta e a seguinte (só os testes trocam)
// a hashtag também vai dentro da consulta: só letras (com acento), números e sublinhado, como o banco guarda
const HASHTAG = /^[0-9a-z_à-öø-ÿ]{1,100}$/;
const LIMITE_META = [4, 17, 32, 613, 80002];
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
// v0.34.0: e as chamadas feitas, o maior uso informado pela Meta (%), o tempo que ela pediu para esperar (minutos), a pausa entre as
// chamadas (só na aba Setor), o tipo da recusa geral (limite ou configuração) e a recusa da hashtag (vale para as outras hashtags)
// (revisão da v0.34.0: e se a recusa geral é a Meta ou a rede fora do ar — "passageira": a rodada para, sem pausa)
type Contexto = { resta: () => number; codigos: Set<string>; geral: string; chamadas: number; uso: number; recuperarMin: number;
                  pausaMs: number; limite: boolean; hashtag: string; passageira: boolean };
const contexto = (inicio: number, pausaMs = 0): Contexto => ({ resta: () => ORCAMENTO_MS - (Date.now() - inicio), codigos: new Set(), geral: "",
  chamadas: 0, uso: 0, recuperarMin: 0, pausaMs, limite: false, hashtag: "", passageira: false });

/** Tira da mensagem qualquer token cadastrado (a Meta às vezes repete o token recebido). */
const limpar = (m: string) => [env("META_IG_TOKEN").trim(), env("META_PAGE_TOKEN").trim()].filter(Boolean)
  .reduce((s, t) => s.split(t).join("***"), m);

/** A recusa da Meta em português, com o código (para conferir na documentação da Meta). */
function traduzir(codigo: number | null, sub: number | null, bruta: string, status: number): { mensagem: string; geral: boolean } {
  const cod = `Meta ${codigo ?? "HTTP " + status}${sub ? "/" + sub : ""}`;
  if (codigo === 110 || sub === 2207013) {
    return { geral: false, mensagem: "conta não encontrada, privada ou que não é comercial/criador (a Meta só mostra perfis comerciais ou de " +
      `criador públicos): confira o @ (${cod})` };
  }
  if (codigo === 190) {
    return { geral: true, mensagem: "o token da Meta venceu, foi revogado ou foi copiado errado: gere outro no Business (Usuários do " +
      `sistema) e troque o segredo META_IG_TOKEN (${cod})` };
  }
  if (codigo === 10 || (codigo !== null && codigo >= 200 && codigo <= 299) || /instagram_manage_insights/i.test(bruta)) {
    return { geral: true, mensagem: "falta permissão no META_IG_TOKEN: o aplicativo \"Radar Artecon Publicações\" precisa de " +
      `instagram_basic e instagram_manage_insights (${cod})` };
  }
  if (codigo !== null && LIMITE_META.includes(codigo)) {
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

/** v0.34.0: o uso informado pela Meta nos cabeçalhos X-App-Usage ({call_count, total_cputime, total_time}, em %) e
 *  X-Business-Use-Case-Usage ({"<id>": [{type, call_count, ..., estimated_time_to_regain_access}]}): guarda o maior. Ilegível: ignora. */
function lerUso(cab: Headers, ctx: Contexto) {
  const visitar = (o: unknown): void => {
    if (Array.isArray(o)) { o.forEach(visitar); return; }
    if (!o || typeof o !== "object") return;
    for (const [k, v] of Object.entries(o as Record<string, unknown>)) {
      if (["call_count", "total_cputime", "total_time"].includes(k) && typeof v === "number" && Number.isFinite(v)) ctx.uso = Math.max(ctx.uso, v);
      else if (k === "estimated_time_to_regain_access" && typeof v === "number" && Number.isFinite(v)) ctx.recuperarMin = Math.max(ctx.recuperarMin, v);
      else visitar(v);
    }
  };
  for (const nome of ["x-app-usage", "x-business-use-case-usage"]) {
    const v = cab.get(nome);
    if (!v) continue;
    try { visitar(JSON.parse(v)); } catch { /* cabeçalho ilegível: ignora */ }
  }
}

/** GET na Graph API com o META_IG_TOKEN. O token vai na consulta e nunca aparece em mensagem de erro nem no registro.
 *  v0.34.0: o caminho pode vir em partes (["<id da hashtag>", "top_media"]), cada uma codificada; "extra" entra na consulta (user_id,
 *  q, limit); com ctx.pausaMs (só a aba Setor), espera entre uma chamada e a seguinte; lê o uso informado pela Meta. */
async function chamarMeta(caminho: string | string[], fields: string, ctx: Contexto, extra: Record<string, string> = {}): Promise<any> {
  if (ctx.pausaMs > 0 && ctx.chamadas > 0) {
    const espera = Math.min(ctx.pausaMs, ctx.resta() - 100);
    if (espera > 0) await new Promise((ok) => setTimeout(ok, espera));
  }
  const resta = ctx.resta();
  if (resta < 100) throw new ErroMeta(504, NAO_COUBE);
  const prazo = Math.min(PRAZO_META_MS, resta);
  const p = new URLSearchParams({ ...extra, ...(fields ? { fields } : {}), access_token: env("META_IG_TOKEN").trim() });
  const rota = (Array.isArray(caminho) ? caminho : [caminho]).map((x) => encodeURIComponent(x)).join("/");
  ctx.chamadas++;
  let r: Response;
  try {
    r = await fetch(`${GRAPH}/${rota}?${p}`, { signal: AbortSignal.timeout(prazo) });
  } catch (e) {
    // a mensagem de erro do fetch pode trazer o endereço (com o token): nunca é usada, só o tipo do erro
    if (ehPrazo(e)) semResposta(prazo, ctx);
    // falhou na hora: conexão recusada, DNS, TLS ou META_GRAPH_URL errado — esperar não adianta, é rede ou configuração
    ctx.codigos.add("rede");
    throw new ErroMeta(502, "não foi possível falar com a Meta (rede ou META_GRAPH_URL errado); tente de novo em alguns minutos");
  }
  lerUso(r.headers, ctx);
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
    if (codigo !== null && LIMITE_META.includes(codigo)) ctx.limite = true;            // v0.34.0: a aba Setor pausa a leitura
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
type Perfil = { usuario: string; ok: true; conta: Record<string, unknown>; posts: any[]; aviso?: string; metaId?: string | null };
type Falha = { usuario: string; ok: false; erro: string };

/** Conta e posts recentes de um perfil (até n), em páginas. Erro na primeira página: o perfil volta com erro (lança).
 *  v0.34.0: a aba Setor pede outros campos da conta, no máximo 3 páginas e monta o post do seu jeito (postSetor); devolve também o
 *  número da conta (metaId), que a ação "ler" não mostra. */
async function lerPerfil(u: string, n: number, pedido: Pedido, ctx: Contexto, contaCampos = CAMPOS_CONTA, maxPaginas = MAX_PAGINAS,
                         mapear: (m: any) => unknown = post): Promise<Perfil> {
  const ig = env("META_IG_USER_ID").trim();
  let lote = POR_PAGINA;
  /** Uma página: a primeira traz também a conta; as outras, só os posts depois do cursor. */
  const pagina = async (falta: number, cursor: string | null): Promise<any> => {
    for (;;) {
      const limite = Math.min(falta, lote);
      const midia = `${cursor ? `media.after(${cursor})` : "media"}.limit(${limite}){${pedido.campos.join(",")}}`;
      try {
        const d = await chamarMeta(ig, `business_discovery.username(${u}){${cursor ? midia : contaCampos + "," + midia}}`, ctx);
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
      : paginas >= maxPaginas ? `a Meta mandou poucos posts por página e a leitura parou em ${maxPaginas} páginas` : "";
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
    posts: brutos.slice(0, n).map(mapear), metaId: txt(bd.id),
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
    try { const { metaId: _, ...p } = await lerPerfil(u, n, pedido, ctx); saida.push(p); }   // v0.34.0: o número da conta não sai
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

// ------------------------------------------------------------------ v0.34.0: aba Setor
/** Corta por ponto de código (Array.from): não parte um emoji no meio. */
const trecho = (t: string, n: number) => Array.from(t).slice(0, n).join("");
/** As hashtags da legenda INTEIRA (antes do corte), minúsculas, sem repetir, até 20. */
function extrairHashtags(t: string): string[] {
  const saida: string[] = [];
  for (const m of t.matchAll(/#([\p{L}\p{N}_]{2,60})/gu)) {
    const h = m[1].toLowerCase();
    if (!saida.includes(h)) saida.push(h);
    if (saida.length >= HASHTAGS_MAX) break;
  }
  return saida;
}
/** A publicação como a aba Setor guarda: sem imagem; a legenda cortada em 300 caracteres e as hashtags à parte. A data vai em ISO
 *  ("+0000" da Meta vira "+00:00"); a que não for data o banco recusa (a publicação é pulada). */
function postSetor(m: any) {
  const ts = txt(m?.timestamp);
  const quando = ts ? new Date(ts.replace(/([+-]\d{2})(\d{2})$/, "$1:$2")) : null;
  const legenda = typeof m?.caption === "string" ? m.caption : "";
  return {
    id: String(m?.id ?? ""), data: quando && !isNaN(quando.getTime()) ? quando.toISOString() : ts, tipo: txt(m?.media_type),
    produto: txt(m?.media_product_type), curtidas: num(m?.like_count), comentarios: num(m?.comments_count),
    legenda: trecho(legenda, LEGENDA_MAX), hashtags: extrairHashtags(legenda), link: txt(m?.permalink),
  };
}
/** O código da recusa para o banco ("110/2207013", "190", "sem_resposta"...). */
const codigoDe = (e: unknown) => e instanceof ErroMeta
  ? (e.codigo !== null ? String(e.codigo) + (e.sub ? "/" + e.sub : "") : e.message === NAO_COUBE ? "tempo" : /não respondeu/.test(e.message)
     ? "sem_resposta" : /ilegível/.test(e.message) ? "ilegivel" : /falar com a Meta/.test(e.message) ? "rede" : "http" + e.status)
  : "inesperado";
/** A falha que não é da conta, mas da Meta ou da rede, e passa sozinha. "certa": não deu para falar com a Meta (rede, DNS, conexão
 *  recusada): vale para todas. "talvez": a Meta não respondeu a tempo, respondeu ilegível ou com o código 1 ou 2 (erro desconhecido,
 *  serviço indisponível) — pode ser só daquela conta (uma conta grande demais): vale para todas só se a conta seguinte também falhar assim. */
function passageira(e: unknown): "certa" | "talvez" | null {
  if (!(e instanceof ErroMeta) || e.geral || e.message === NAO_COUBE) return null;
  const c = codigoDe(e);
  if (c === "rede") return "certa";
  return c === "sem_resposta" || c === "ilegivel" || e.codigo === 1 || e.codigo === 2 ? "talvez" : null;
}
/** A recusa como o banco grava. A que vale para todas (token, permissão, limite) para a rodada (ctx.geral) e diz se é de limite. */
function falhaDe(e: unknown, ctx: Contexto): Record<string, unknown> {
  const geral = e instanceof ErroMeta && e.geral;
  if (geral) ctx.geral = (e as ErroMeta).message;
  if (!(e instanceof Erro)) console.error("radar-concorrentes: erro inesperado numa conta do setor", e instanceof Error ? e.name : "");
  const p = passageira(e);
  return { ok: false, erro: e instanceof Erro ? e.message : "erro inesperado ao ler esta conta", codigo: codigoDe(e), geral, ...(p ? { passageira: p } : {}) };
}
/** A recusa da busca por hashtag em português (null: não é dela; segue a tradução de sempre). Os códigos ainda não foram conferidos
 *  na Meta de verdade (o recurso Instagram Public Content Access não está aprovado): vêm da documentação. */
function recusaHashtag(e: ErroMeta): string | null {
  const c = e.codigo, cod = `Meta ${c ?? "HTTP " + e.status}${e.sub ? "/" + e.sub : ""}`;
  if (/30 unique hashtags|hashtag limit/i.test(e.bruta) || c === 24) {
    return `limite da Meta: 30 hashtags diferentes a cada 7 dias; espere alguns dias (${cod})`;
  }
  if (c === 10 || (c !== null && c >= 200 && c <= 299) || /public content access/i.test(e.bruta)) {
    return `a Meta ainda não liberou a busca por hashtag (recurso Instagram Public Content Access na Análise do App) (${cod})`;
  }
  return null;
}
/** Uma hashtag: o número dela (ig_hashtag_search, só se o banco ainda não tem) e as publicações (top_media e/ou recent_media). */
async function lerHashtag(nome: string, metaId: unknown, modo: unknown, ctx: Contexto): Promise<Record<string, unknown>> {
  if (ctx.hashtag) return { ok: false, erro: ctx.hashtag, codigo: "hashtag", geral: false };     // a recusa vale para as outras: não insiste
  const ig = env("META_IG_USER_ID").trim();
  let id = typeof metaId === "string" && /^\d{1,30}$/.test(metaId) ? metaId : "";
  let buscada = false;
  try {
    if (!id) {
      const r = await chamarMeta("ig_hashtag_search", "id", ctx, { user_id: ig, q: nome });
      const achado = (Array.isArray(r?.data) ? r.data : []).map((x: any) => String(x?.id ?? "")).find((x: string) => /^\d{1,30}$/.test(x));
      if (!achado) return { ok: false, erro: "a Meta não encontrou esta hashtag", codigo: "hashtag_vazia", geral: false };
      id = achado;
      buscada = true;
    }
    const arestas = modo === "recentes" ? ["recent_media"] : modo === "ambos" ? ["top_media", "recent_media"] : ["top_media"];
    const vistos = new Set<string>(), posts: ReturnType<typeof postSetor>[] = [];
    for (const aresta of arestas) {
      const r = await chamarMeta([id, aresta], CAMPOS_HASHTAG, ctx, { user_id: ig, limit: "50" });
      for (const m of Array.isArray(r?.data) ? r.data : []) {
        const p = postSetor(m);
        if (p.id && !vistos.has(p.id)) { vistos.add(p.id); posts.push(p); }
      }
    }
    return { ok: true, meta_id: id, buscada, seguidores: null, posts_total: null, posts };
  } catch (e) {
    const propria = e instanceof ErroMeta && !LIMITE_META.includes(e.codigo ?? -1) && e.codigo !== 190 ? recusaHashtag(e) : null;
    if (propria) ctx.hashtag = propria;
    const falha = propria ? { ok: false, erro: propria, codigo: codigoDe(e), geral: false } : falhaDe(e, ctx);
    // a busca do número já foi feita (conta para as 30 hashtags da Meta em 7 dias): o banco registra e guarda o número
    return buscada ? { ...falha, buscada: true, meta_id: id } : falha;
  }
}

/** "Atualizar a análise" e a leitura automática: até 12 contas devidas (o banco escolhe), uma por vez, cada uma gravada antes da
 *  seguinte. Para na recusa geral, com 80% de uso ou sem tempo para mais uma: o que sobrar continua devido para a próxima rodada. */
async function setorColetar(quem: "chave" | "admin", inicio: number) {
  const faltam = faltamSegredos();
  if (faltam.length) throw new Erro(503, explicarFalta(faltam));
  const origem = quem === "chave" ? "agenda" : "admin";
  const servico = comoServico();
  let ini: any;
  try { ini = await banco(servico, "POST", "rpc/radar_setor_iniciar", { p_origem: origem, p_limite: MAX_CONTAS_SETOR }); }
  catch (e) {
    if (e instanceof Erro && /radar_setor_iniciar/.test(e.message)) {
      throw new Erro(503, "O banco ainda não tem a aba Setor: rode o sql/radar-setup desta versão (Supabase → SQL Editor).");
    }
    throw e;
  }
  if (!ini || typeof ini !== "object" || ini.motivo || !Array.isArray(ini.contas)) {
    const motivo = String(ini?.motivo ?? "nada");
    console.log(`radar-concorrentes (${quem}): setor, nada a ler (${motivo.replace(/[^a-z_]/g, "")})`);
    return { versao: VERSAO, motivo, ...(ini?.pausa_ate ? { pausa_ate: ini.pausa_ate, pausa_motivo: ini.pausa_motivo } : {}) };
  }
  const ctx = contexto(inicio, PAUSA_MS);
  const pedido: Pedido = { campos: [...CAMPOS_POST_SETOR], retirados: [] };
  const ig = env("META_IG_USER_ID").trim();
  const n = Number.isInteger(ini.posts) && ini.posts >= 10 && ini.posts <= 50 ? ini.posts : 50;
  const contas: { tipo: string; nome: string; ok: boolean; erro?: string }[] = [];
  let lidas = 0, comErro = 0, posts = 0;
  /** Grava o resultado de uma conta (ou hashtag) e conta. Banco fora: só o registro (a conta continua devida). */
  const gravar = async (tipo: string, nome: string, dados: Record<string, unknown>) => {
    try {
      await banco(servico, "POST", "rpc/radar_setor_gravar", { p_coleta: ini.coleta, p_tipo: tipo, p_nome: nome, p_dados: dados });
    } catch (e) {
      console.log(`radar-concorrentes (${quem}): setor, uma conta não foi gravada (${e instanceof Erro ? e.status : "sem resposta do banco"})`);
      return;
    }
    if (dados.ok) { lidas++; posts += Array.isArray(dados.posts) ? dados.posts.length : 0; contas.push({ tipo, nome, ok: true }); }
    else { comErro++; contas.push({ tipo, nome, ok: false, erro: String(dados.erro) }); }
  };
  // a falha "talvez passageira" espera a conta seguinte: se ela também falhar assim, é a Meta (ou a rede) fora do ar
  let suspeita: { tipo: string; nome: string; dados: Record<string, unknown> } | null = null;
  for (const item of ini.contas) {
    if (ctx.geral || ctx.uso >= USO_LIMITE || ctx.resta() < COMECAR_MS + PAUSA_MS) break;     // o resto continua devido
    const tipo = String(item?.tipo ?? ""), nome = String(item?.nome ?? "");
    let dados: Record<string, unknown>;
    if (tipo === "conta" && USUARIO.test(nome)) {
      try {
        const r = await lerPerfil(nome, n, pedido, ctx, CAMPOS_CONTA_SETOR, MAX_PAGINAS_SETOR, postSetor);
        dados = { ok: true, meta_id: r.metaId ?? null, propria: !!r.metaId && r.metaId === ig, seguidores: r.conta.seguidores,
                  posts_total: r.conta.posts_total, aviso: r.aviso ?? null, posts: r.posts };
      } catch (e) {
        if (e instanceof ErroMeta && e.message === NAO_COUBE) break;                          // sem tempo: fica para a próxima rodada
        dados = falhaDe(e, ctx);
      }
    } else if (tipo === "hashtag" && HASHTAG.test(nome)) {
      dados = await lerHashtag(nome, item?.meta_id, ini.hashtag_modo, ctx);
      if (!dados.ok && dados.codigo === "tempo") break;
    } else {
      dados = { ok: false, erro: "nome fora do padrão do Instagram", codigo: "nome", geral: false };     // nem chega à Meta
    }
    const falha = dados.ok ? null : dados.passageira;
    if (falha === "certa" || (falha === "talvez" && suspeita)) {
      // a Meta (ou a rede) está fora: a rodada para e ninguém leva falha (continuam devidas; a agenda tenta de novo na hora seguinte)
      ctx.geral = String(dados.erro);
      ctx.passageira = true;
      for (const x of [suspeita, { tipo, nome, dados }]) if (x) await gravar(x.tipo, x.nome, { ...x.dados, geral: true });
      suspeita = null;
      break;
    }
    if (suspeita) { await gravar(suspeita.tipo, suspeita.nome, suspeita.dados); suspeita = null; }   // esta respondeu: a falha era só daquela
    if (falha === "talvez") { suspeita = { tipo, nome, dados }; continue; }
    await gravar(tipo, nome, dados);
  }
  if (suspeita) await gravar(suspeita.tipo, suspeita.nome, suspeita.dados);     // sem a seguinte para comparar: falha da conta, como antes
  // a pausa: limite da Meta (a recusa ou 80% de uso) → 60 minutos ou o que a Meta pediu; token, permissão ou conta da Artecon → 6 horas,
  // só para a agenda (o botão do administrador continua, para testar logo depois de trocar o token); a Meta ou a rede fora do ar → sem
  // pausa (a agenda, de hora em hora, tenta de novo na hora seguinte)
  const limite = ctx.limite || ctx.uso >= USO_LIMITE;
  const pausa = limite ? { pausa_minutos: Math.max(60, Math.ceil(ctx.recuperarMin)), pausa_motivo: "limite" }
    : ctx.geral && !ctx.passageira ? { pausa_minutos: 360, pausa_motivo: "configuracao" } : { pausa_minutos: 0 };
  const geral = ctx.geral || (ctx.uso >= USO_LIMITE ? `a Meta informou ${Math.round(ctx.uso)}% de uso das chamadas: a leitura parou para não passar do limite` : "");
  const fim = await banco(servico, "POST", "rpc/radar_setor_concluir", { p_coleta: ini.coleta, p_resumo: {
    chamadas: ctx.chamadas, uso_max: Math.round(ctx.uso), codigos: [...ctx.codigos].join(","), ...pausa, geral: geral || null,
  } });
  // só contagens e códigos: nome de conta, hashtag, legenda, link e token nunca vão para o registro
  console.log(`radar-concorrentes (${quem}): setor, ${ini.contas.length} conta(s), ${lidas} lida(s), ${comErro} com erro, ${posts} post(s), ` +
    `${ctx.chamadas} chamada(s)` + (ctx.uso ? `, uso ${Math.round(ctx.uso)}%` : "") +
    (pedido.retirados.length ? `, campos retirados: ${pedido.retirados.join(",")}` : "") +
    (ctx.codigos.size ? `, códigos da Meta: ${[...ctx.codigos].join(",")}` : ""));
  return { versao: VERSAO, coleta: ini.coleta, lidas, com_erro: comErro, faltam: Number(fim?.faltam ?? 0), chamadas: ctx.chamadas,
           ...(fim?.pausa_ate ? { pausa_ate: fim.pausa_ate, pausa_motivo: pausa.pausa_motivo } : {}), ...(geral ? { geral } : {}), contas };
}

/** O @ da conta da Artecon (1 chamada), para o botão "Incluir a conta da Artecon". */
async function setorPropria(inicio: number) {
  const faltam = faltamSegredos();
  if (faltam.length) throw new Erro(503, explicarFalta(faltam));
  const eu = await chamarMeta(env("META_IG_USER_ID").trim(), "username", contexto(inicio));
  const usuario = String(eu?.username ?? "").toLowerCase();
  if (!USUARIO.test(usuario)) throw new Erro(502, "A Meta não devolveu o nome da conta do META_IG_USER_ID.");
  console.log("radar-concorrentes (admin): setor, a conta da Artecon foi lida");
  return { versao: VERSAO, usuario };
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
    // v0.34.0: a aba Setor (a agenda, com a chave, ou o administrador; a conta da Artecon, só o administrador)
    if (acao === "setor_teste") return responder(200, { ok: true, versao: VERSAO });
    if (acao === "setor_coletar") return responder(200, await setorColetar(quem, inicio));
    if (acao === "setor_propria") {
      if (quem !== "admin") throw new Erro(403, "Só o administrador lê a conta da Artecon por aqui.");
      return responder(200, await setorPropria(inicio));
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
