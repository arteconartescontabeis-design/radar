// =====================================================================
// RADAR ARTECON — Edge Function "radar-redes" (v0.29.0)
//
// Publica no Instagram e no Facebook da Artecon, pela API da Meta (Graph API), o conteúdo que o administrador
// autorizou na tela do assunto (passos 6 e 7 da trilha) e, v0.21.0, a peça da Pauta que ele aprovou para sair pela agenda.
// Nada sai sem essa autorização: a função só envia autorizações registradas por radar_autorizar_rede (ou radar_pauta_aprovar),
// uma vez cada (radar_rede_iniciar, ou radar_pauta_iniciar na peça, marca "enviando").
//
// Quem pode chamar: o administrador logado (o botão "Autorizar e publicar" da tela chama logo depois de autorizar) e,
// v0.17.0, o robô do site com a chave interna — só para as autorizações do "Publicar em todos" (feitas pelo administrador
// junto com o site), logo depois que a notícia entra no site. v0.19.0: só o administrador aciona o robô do site (acionar_robo).
// v0.21.0: a agenda do banco (pg_cron, sql/radar-redes-agenda.sql, de 5 em 5 minutos), com a chave 'radar_redes_agenda' do Vault
// no cabeçalho x-radar-agenda (quem confere é o banco: radar_redes_conferir_agenda) e a chave anon pública no Authorization (o
// "Verify JWT" continua ligado). A agenda só publica peça da Pauta, e só a que já venceu (radar_pauta_iniciar confere a hora e
// tudo o mais de novo), e faz o teste da instalação (agenda_teste). Nada da notícia passa pela agenda.
//
// Ações:
//   publicar     { envio }  → guarda a imagem no armazenamento privado, publica (a Meta baixa por um link de 10 min) e registra o post
//   excluir      { envio }  → v0.17.0: apaga a publicação na rede (pedido do administrador) e registra a exclusão
//   diagnostico             → confere os segredos, a Página do Facebook, a conta do Instagram e os armazenamentos
//   acionar_robo            → v0.19.0: aciona na hora o robô do site no GitHub (workflow radar-site-publicar.yml), se houver
//                             publicação, envio junto com o site ou exclusão esperando por ele. Responde sempre 200 com
//                             { acionado, motivo?, em?, mensagem }: se não der para acionar, a autorização continua guardada
//                             e sai na próxima rodada automática (o agendamento do GitHub, que é a reserva)
//   agenda_teste            → v0.21.0: só a agenda do banco (o teste do sql/radar-redes-agenda.sql). Responde { ok, versao }
//                             sem tocar na Meta nem no armazenamento
//   manter_robos            → v0.22.0 (rodada 2 da varredura geral): a agenda do banco (uma vez por dia) ou o administrador. No
//                             repositório PÚBLICO, o GitHub desliga sozinho os workflows agendados (coleta, robô do site, resumo)
//                             depois de 60 dias sem atividade, e eles só voltam com "Enable workflow". A função religa o desligado
//                             por inatividade e renova o ativo (PUT .../enable); o desligado à mão fica como está. Responde
//                             { ok, robos: [{ workflow, estado, religado }] }. v0.29.0: o robô dos lembretes (radar-lembretes.yml)
//                             entra na lista
//   acionar_lembretes       → v0.29.0: só a agenda do banco (sql/radar-redes-agenda.sql, de 15 em 15 minutos, e só quando o banco diz
//                             que há lembrete para mandar: radar_lembretes_acionar). Aciona o robô dos lembretes por e-mail no GitHub
//                             (workflow FIXO radar-lembretes.yml, nunca vindo do pedido), com o mesmo RADAR_GITHUB_TOKEN. Responde 200
//                             com { acionado, motivo? }; sem dar para acionar, a rodada de hora em hora do próprio workflow é a reserva
//
// Como publica:
//   Instagram: POST /{ig-user-id}/media (image_url + caption) → espera o contêiner ficar pronto → POST /{ig-user-id}/media_publish
//   Facebook:  POST /{page-id}/photos (url + message)
// Como exclui (v0.17.0): DELETE /{id do post} — no Facebook com o token da Página (pages_manage_posts); no Instagram com o
// token do Instagram. Se a Meta não deixar apagar pelo aplicativo, a tela oferece "Já apaguei na rede" para registrar à mão.
// A Meta só aceita imagem por link. v0.21.0: a arte da peça da Pauta (que pode ter foto da equipe) vai para o bucket PRIVADO
// "radar-pauta", com nome aleatório, e a Meta recebe só um link assinado que vale 10 minutos. No banco fica o endereço interno
// (que não abre sem a chave interna): a nova tentativa assina de novo, sem reenviar a imagem. v0.22.0 (rodada 2 da varredura
// geral): a imagem da notícia (JPEG vertical 1080×1350 montado pela tela) também; antes ela ia para o bucket PÚBLICO "radar-redes"
// com nome previsível (<conteúdo>-<canal>-<envio>.jpg) e ficava lá para sempre, mesmo depois de excluída da rede ou cancelada. O
// envio antigo, com o link público já gravado, sai como antes; e, ao excluir da rede pela função, a imagem dele sai do bucket público.
// Como aciona o robô do site (v0.19.0): POST /repos/{RADAR_GITHUB_REPO}/actions/workflows/radar-site-publicar.yml/dispatches
// com { ref: RADAR_GITHUB_RAMO }. O GitHub atrasa (ou descarta) em horas o agendamento "a cada 15 minutos", mas atende o
// acionamento manual em segundos. O workflow é fixo aqui (nada vem do pedido) e há uma pausa de 30 s entre dois acionamentos.
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
//   RADAR_GITHUB_TOKEN v0.19.0, opcional: token fino do GitHub (Fine-grained token, só o repositório radar, Actions: leitura e
//                      escrita) para acionar o robô do site na hora. Fica SÓ aqui: nunca nos segredos do GitHub, na tela ou no
//                      chat. Sem ele, as autorizações saem na próxima rodada automática do GitHub
//   RADAR_GITHUB_REPO  opcional; padrão arteconartescontabeis-design/radar
//   RADAR_GITHUB_RAMO  opcional; padrão main
// SUPABASE_URL, a chave pública (SUPABASE_PUBLISHABLE_KEYS ou SUPABASE_ANON_KEY) e a chave interna (SUPABASE_SECRET_KEYS ou
// SUPABASE_SERVICE_ROLE_KEY) o Supabase já fornece.
// =====================================================================

const VERSAO = "0.29.0";
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
const BUCKET = "radar-redes";
// v0.21.0: a arte da peça da Pauta fica no bucket privado; a Meta baixa por um link assinado que vale 10 minutos
const BUCKET_PAUTA = "radar-pauta", LINK_PAUTA_S = 600;
/** Quem chamou: o administrador logado, o robô do site (chave interna) ou, v0.21.0, a agenda do banco (chave do Vault). */
type Quem = "admin" | "robo" | "agenda";
// a Meta às vezes demora para baixar a imagem: o contêiner do Instagram é consultado por até ~40 s
const ESPERA_IG_MS = Number(env("RADAR_REDES_ESPERA_MS", "40000")), PASSO_IG_MS = Number(env("RADAR_REDES_PASSO_MS", "3000"));
// v0.21.0: cada pedido de conferir ou criar o bucket espera até 10 s (o armazenamento preso não deixa a publicação parada em "enviando")
const TEMPO_BUCKET_MS = Number(env("RADAR_REDES_BUCKET_MS", "10000"));

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
async function quemChamou(req: Request, acao = ""): Promise<string | null> {
  if (await ehRobo(req)) return null;
  const token = req.headers.get("Authorization") ?? "";
  if (!/^Bearer\s+\S+/.test(token)) throw new Erro(401, "Sessão não informada.");
  const papel = await banco(token, "POST", "rpc/radar_papel", {});
  if (papel !== "admin") {
    throw new Erro(403, acao === "acionar_robo" ? "Só o administrador aciona o robô do site." : "Só o administrador publica no Instagram e no Facebook.");
  }
  return token;
}

/** v0.21.0: a chamada vem da agenda do banco com a chave 'radar_redes_agenda' do Vault (cabeçalho x-radar-agenda)? Quem confere
 *  é o banco (radar_redes_conferir_agenda, só o papel interno executa). A recusa é sempre a mesma frase: não diz se a conferência
 *  existe, falhou ou se a chave só está errada. A chave nunca vai para mensagem nem registro. */
async function conferirAgenda(chave: string): Promise<void> {
  let ok = false;
  if (chave.length >= 32 && chave.length <= 200) {
    try { ok = (await banco(comoServico(), "POST", "rpc/radar_redes_conferir_agenda", { p_chave: chave }, 10_000)) === true; }
    catch (e) {
      if (e instanceof Erro && e.status === 503) throw e;                       // função sem a chave interna: configuração
      console.log(`radar-redes: conferência da chave da agenda falhou (${e instanceof Erro ? e.status : "sem resposta do banco"})`);
    }
  }
  if (!ok) throw new Erro(401, "Chave não confere.");
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

// ------------------------------------------------------------------ armazenamento da imagem (v0.21.0: privado da Pauta; v0.22.0: também da notícia)
/** O bucket existe (e, o da Pauta, é privado)? Se não, cria. v0.21.0: cada pedido com tempo-limite; sem resposta, a recusa diz que nada
 *  foi publicado (quem chamou grava "erro", e a publicação não fica parada em "enviando" até o Supabase encerrar a função). */
async function garantirBucket(nome: string, publico: boolean) {
  const semResposta = () => new Erro(502, "Não foi possível guardar a imagem para a Meta (o armazenamento não respondeu). Nada foi publicado.");
  let r: Response;
  try { r = await fetch(`${SUPABASE_URL}/storage/v1/bucket/${nome}`, { headers: comoServico(), signal: AbortSignal.timeout(TEMPO_BUCKET_MS) }); }
  catch { throw semResposta(); }
  const atual: any = r.ok && !publico ? await r.json().catch(() => ({})) : null;
  if (atual === null) await r.body?.cancel();
  // v0.21.0: as fotos da equipe nunca vão para um bucket público (alguém pode ter criado ou trocado o "radar-pauta" no painel)
  if (atual?.public === true) {
    throw new Erro(502, `O armazenamento "${nome}" está público: no Supabase → Storage, deixe-o privado (Edit bucket → "Public bucket" desligado).`);
  }
  if (r.ok) return;
  let c: Response;
  try {
    c = await fetch(`${SUPABASE_URL}/storage/v1/bucket`, {
      method: "POST", headers: { ...comoServico(), "Content-Type": "application/json" }, signal: AbortSignal.timeout(TEMPO_BUCKET_MS),
      body: JSON.stringify({ id: nome, name: nome, public: publico, file_size_limit: 8 * 1024 * 1024, allowed_mime_types: ["image/jpeg"] }),
    });
  } catch { throw semResposta(); }
  const d: any = await c.json().catch(() => ({}));
  // já existe (o Supabase responde 409, ou 400 com statusCode "409"): está pronto
  if (c.ok || c.status === 409 || String(d?.statusCode ?? "") === "409") return;
  throw new Erro(502, `Não foi possível criar o armazenamento das imagens (${c.status}${d?.message ? ": " + String(d.message).slice(0, 120) : ""}).`);
}

/** v0.22.0 (rodada 2): o endereço da imagem de uma notícia publicada antes desta versão, no bucket PÚBLICO "radar-redes" (só esse
 *  formato: "<conteúdo>-<canal>-<envio>.jpg"); "" se não é. A nova tentativa desse envio ainda manda esse link à Meta; ao excluir,
 *  a imagem sai do bucket. */
const PUBLICA_ANTIGA = () => `${SUPABASE_URL}/storage/v1/object/public/${BUCKET}/`;
const nomePublicoAntigo = (url: string) => {
  const nome = String(url ?? "").startsWith(PUBLICA_ANTIGA()) ? String(url).slice(PUBLICA_ANTIGA().length) : "";
  return /^\d+-(instagram|facebook)-\d+\.jpg$/.test(nome) ? nome : "";
};
/** Apaga a imagem antiga do bucket público (a Meta já tem a cópia dela). Se o armazenamento não responder, fica para o painel
 *  (LEIAME): a exclusão na rede já foi feita e registrada. */
async function apagarPublicaAntiga(url: string) {
  const nome = nomePublicoAntigo(url);
  if (!nome) return;
  try {
    const r = await fetch(`${SUPABASE_URL}/storage/v1/object/${BUCKET}/${nome}`, { method: "DELETE", headers: comoServico(), signal: AbortSignal.timeout(15_000) });
    await r.body?.cancel();
  } catch { /* fica no bucket: apague pelo painel */ }
}

/** v0.21.0: guarda a arte aprovada da peça da Pauta (v0.22.0: e a da notícia) no bucket PRIVADO, com nome aleatório e sem x-upsert
 *  (nunca sobrescreve), e
 *  devolve o endereço interno, que não abre sem a chave interna. É ele que fica no banco; a Meta recebe só o link de assinar(). */
async function guardarPrivada(dataUrl: string): Promise<string> {
  const m = /^data:image\/jpeg;base64,([A-Za-z0-9+/=]+)$/.exec(dataUrl ?? "");
  if (!m) throw new Erro(400, "A imagem da publicação não é um JPEG válido.");
  const bytes = Uint8Array.from(atob(m[1]), (ch) => ch.charCodeAt(0));
  await garantirBucket(BUCKET_PAUTA, false);
  const nome = `p-${crypto.randomUUID()}.jpg`;
  let r: Response;
  try {
    r = await fetch(`${SUPABASE_URL}/storage/v1/object/${BUCKET_PAUTA}/${nome}`, {
      method: "POST", body: bytes, headers: { ...comoServico(), "Content-Type": "image/jpeg" }, signal: AbortSignal.timeout(20_000),
    });
  } catch { throw new Erro(502, "Não foi possível guardar a imagem para a Meta (o armazenamento não respondeu). Nada foi publicado."); }
  await r.body?.cancel();
  if (!r.ok) throw new Erro(502, `Não foi possível guardar a imagem para a Meta (${r.status}).`);
  return `${SUPABASE_URL}/storage/v1/object/${BUCKET_PAUTA}/${nome}`;
}

/** v0.21.0: link assinado (10 min) para a Meta baixar a arte do bucket privado: POST /object/sign/{bucket}/{nome} com {expiresIn},
 *  que responde {signedURL: "/object/sign/…?token=…"}. Só assina o que a própria função guardou (o endereço interno "p-…"). */
async function assinar(url: string): Promise<string> {
  const base = `${SUPABASE_URL}/storage/v1/object/${BUCKET_PAUTA}/`;
  const nome = url.startsWith(base + "p-") ? url.slice(base.length) : "";
  const falhou = new Erro(502, "Não foi possível preparar o link da imagem para a Meta. Nada foi publicado.");
  if (!/^p-[\w-]+\.jpg$/.test(nome)) throw falhou;
  try {
    const r = await fetch(`${SUPABASE_URL}/storage/v1/object/sign/${BUCKET_PAUTA}/${nome}`, {
      method: "POST", headers: { ...comoServico(), "Content-Type": "application/json" },
      body: JSON.stringify({ expiresIn: LINK_PAUTA_S }), signal: AbortSignal.timeout(15_000),
    });
    const d: any = await r.json().catch(() => ({}));
    const assinado = String(d?.signedURL ?? "");
    if (r.ok && assinado.startsWith(`/object/sign/${BUCKET_PAUTA}/`)) return `${SUPABASE_URL}/storage/v1${assinado}`;
  } catch { /* o armazenamento não respondeu: a mesma recusa */ }
  throw falhou;
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

/** v0.21.0: a autorização, com peca_id (a peça da Pauta). Com o banco de antes da v0.21.0 (sem a coluna), lê de novo sem ela:
 *  a notícia continua saindo se esta função for instalada antes do SQL. */
async function lerEnvio(servico: Record<string, string>, envio: number) {
  const ler = (campos: string) => banco(servico, "GET", `radar_redes_envios?select=${campos}&id=eq.${envio}`);
  try { const [linha] = await ler("canal,situacao,junto_com_site,peca_id"); return linha ?? null; }
  catch (x) { if (!(x instanceof Erro) || !/peca_id/.test(x.message)) throw x; }
  const [linha] = await ler("canal,situacao,junto_com_site");
  return linha ? { ...linha, peca_id: null } : null;
}

async function publicar(envio: number, inicio: number, quem: Quem) {
  const servico = comoServico();
  // confere a configuração ANTES de pegar a autorização: sem a Meta configurada, ela continua aguardando
  const linha = await lerEnvio(servico, envio);
  if (!linha) throw new Erro(404, "Autorização não encontrada.");
  // v0.17.0: o robô só manda o que o administrador autorizou junto com o site ("Publicar em todos")
  if (quem === "robo" && !linha.junto_com_site) throw new Erro(403, "O robô só publica o que foi autorizado junto com o site.");
  // v0.21.0: a agenda do banco só manda a peça da Pauta (a notícia sai pela tela ou pelo robô do site, como antes)
  if (quem === "agenda" && !linha.peca_id) throw new Erro(403, "A agenda só publica peças da Pauta.");
  const cfg = configMeta(linha.canal);
  if (cfg.faltam.length) {
    throw new Erro(503, `${linha.canal === "instagram" ? "O Instagram" : "O Facebook"} ainda não está configurado: faltam os segredos ` +
      cfg.faltam.join(", ") + " (Supabase → Edge Functions → Secrets). A autorização continua guardada; publique depois.");
  }
  // v0.21.0: a peça é pega por radar_pauta_iniciar (na hora marcada, uma vez, conferindo tudo de novo; o problema vira "erro")
  const e = await banco(servico, "POST", linha.peca_id ? "rpc/radar_pauta_iniciar" : "rpc/radar_rede_iniciar", { p_envio: envio });
  if (e?.cancelado) return { situacao: "cancelado", mensagem: "O conteúdo mudou depois de autorizado: a autorização caiu. Confira e autorize de novo." };
  if (e?.erro) return { situacao: "erro", mensagem: String(e.erro) };
  // imagemUrl é o que fica no banco; paraMeta, o que a Meta baixa (na peça, o link assinado de 10 min, que nunca é gravado)
  let imagemUrl = e.imagem_url ?? "", paraMeta = "";
  try {
    // o bucket (até 2 × 10 s), o envio (até 20 s) e a assinatura (até 15 s) contam dentro dos 55 s de aindaDaTempo (passado esse
    // tempo, o pedido à Meta não sai e a recusa vira "erro"): o pior caso depois da publicação continua o de LIMITE_PUBLICAR_MS.
    // v0.22.0 (rodada 2): a notícia também vai para o bucket privado (nome aleatório, link de 10 min); só a nova tentativa de um
    // envio de antes desta versão, com o link público já gravado, manda esse link
    if (!linha.peca_id && nomePublicoAntigo(imagemUrl)) paraMeta = imagemUrl;
    else {
      if (!imagemUrl) imagemUrl = await guardarPrivada(e.imagem);
      paraMeta = await assinar(imagemUrl);
    }
    const r = e.canal === "instagram" ? await publicarInstagram(paraMeta, e.legenda, inicio) : await publicarFacebook(paraMeta, e.legenda, inicio);
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
  const [e] = await banco(comoServico(), "GET", `radar_redes_envios?select=id,canal,situacao,post_id,url,imagem_url&id=eq.${envio}`);
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
  await apagarPublicaAntiga(e.imagem_url);                 // v0.22.0 (rodada 2): a imagem de antes desta versão, no bucket público
  return { situacao: "excluido", canal: e.canal };
}

// ------------------------------------------------------------------ robô do site (v0.19.0)
// O token com Actions: escrita aciona qualquer workflow do repositório: por isso o workflow é fixo aqui e só o administrador chama.
const GITHUB_API = env("RADAR_GITHUB_API", "https://api.github.com").replace(/\/+$/, "");    // só os testes trocam
const REPO = env("RADAR_GITHUB_REPO", "arteconartescontabeis-design/radar").trim();
const RAMO = env("RADAR_GITHUB_RAMO", "main").trim();
const WORKFLOW = "radar-site-publicar.yml";                   // nunca vem do pedido
const PAUSA_ROBO_MS = 30_000;
// as mesmas consultas do passo "Há autorização pendente?" do workflow
const PENDENCIAS = [
  "radar_site_envios?select=id&situacao=in.(autorizado,enviando)&limit=1",
  "radar_redes_envios?select=id&situacao=eq.autorizado&junto_com_site=eq.true&limit=1",
  "radar_site_exclusoes?select=id&situacao=in.(pedido,excluindo)&limit=1",
];
// último acionamento, na memória desta instância da função: cliques seguidos não acionam o robô de novo
let ultimoAcionamento = 0;
type Acionamento = { acionado: boolean; motivo?: string; em?: string; mensagem: string };

/** Há algo esperando o robô do site? Se a consulta falhar, conta como pendente, como no workflow (o robô confere de novo). */
async function haPendencia(): Promise<boolean> {
  try {
    const servico = comoServico();
    const linhas = await Promise.all(PENDENCIAS.map((c) => banco(servico, "GET", c, undefined, 10_000)));
    return linhas.some((l) => !Array.isArray(l) || l.length > 0);
  } catch { return true; }
}

/** Aciona o robô do site no GitHub. Nunca lança erro: a autorização já está guardada no banco e, se não der para acionar,
 *  sai na próxima rodada automática. O token nunca aparece em mensagem nem em registro (só textos fixos). */
async function acionarRobo(): Promise<Acionamento> {
  const token = env("RADAR_GITHUB_TOKEN").trim();
  if (!token) {
    return { acionado: false, motivo: "sem_token", mensagem: "O robô do site não foi acionado na hora: falta o segredo RADAR_GITHUB_TOKEN " +
      "no Supabase (Edge Functions → Secrets). A autorização está guardada e sai na próxima rodada automática do GitHub." };
  }
  if (!(await haPendencia())) {
    return { acionado: false, motivo: "nada_pendente", mensagem: "Não há nada esperando o robô do site: ele não foi acionado." };
  }
  if (Date.now() - ultimoAcionamento < PAUSA_ROBO_MS) {
    return { acionado: true, em: new Date(ultimoAcionamento).toISOString(), mensagem: "O robô já foi acionado há instantes." };
  }
  const antes = ultimoAcionamento;
  ultimoAcionamento = Date.now();                             // reserva já: dois cliques ao mesmo tempo não acionam duas vezes
  const falhou = (motivo: string, porque: string, fim = "a autorização continua guardada e sai na próxima rodada automática"): Acionamento => {
    ultimoAcionamento = antes;                                // não acionou: o próximo clique tenta de novo
    console.log(`radar-redes: robô do site não acionado (${motivo})`);
    return { acionado: false, motivo, mensagem: `O robô do site não foi acionado na hora: ${porque}; ${fim}.` };
  };
  let r: Response;
  try { r = await dispararRobo(token); } catch { return falhou("github_fora", "o GitHub não respondeu"); }
  await r.body?.cancel().catch(() => {});                     // a resposta do GitHub não é usada (nem mostrada)
  if (r.status === 204 || r.status === 200) {
    console.log("radar-redes: robô do site acionado");
    return { acionado: true, em: new Date(ultimoAcionamento).toISOString(), mensagem: "Robô acionado: a publicação deve sair em 1 a 2 minutos." };
  }
  if (r.status === 401) {
    return falhou("token_recusado", "o GitHub recusou o token (vencido ou revogado): gere outro e troque o segredo RADAR_GITHUB_TOKEN no Supabase");
  }
  if (r.status === 403 || r.status === 404) {
    return falhou("sem_acesso", `o token não tem acesso ao repositório ${REPO} com a permissão Actions: leitura e escrita ` +
      "(ou o GitHub limitou os pedidos por um tempo)");
  }
  if (r.status === 422) {
    // v0.22.0 (rodada 2 da varredura geral): o 422 é também o do workflow DESLIGADO. Desligado pelo GitHub por inatividade (60 dias
    // sem atividade no repositório público): religa e aciona de novo, uma vez. Desligado (pelo GitHub ou à mão) e não religado: diz
    // onde religar, sem prometer a rodada automática — desligado, ele não roda sozinho
    const estado = await estadoWorkflow(token, WORKFLOW);
    if (estado === "disabled_inactivity" && await religar(token, WORKFLOW)) {
      let r2: Response | null = null;
      try { r2 = await dispararRobo(token); await r2.body?.cancel().catch(() => {}); } catch { /* cai no recado abaixo */ }
      if (r2 && (r2.status === 204 || r2.status === 200)) {
        console.log("radar-redes: robô do site religado e acionado");
        return { acionado: true, em: new Date(ultimoAcionamento).toISOString(), mensagem: "O GitHub tinha desligado o robô do site por falta de " +
          "atividade no repositório (60 dias): o Radar religou e acionou. A publicação deve sair em 1 a 2 minutos." };
      }
      return falhou("workflow_religado", "o GitHub tinha desligado o robô do site por falta de atividade no repositório (60 dias); o Radar religou, " +
        "mas o acionamento não entrou agora");
    }
    if (estado.startsWith("disabled")) {
      return falhou("workflow_desligado", `o workflow ${WORKFLOW} está desligado no GitHub` +
        (estado === "disabled_inactivity" ? " (por falta de atividade no repositório: 60 dias) e o Radar não conseguiu religar" : " (desligado à mão)") +
        ": no GitHub, Actions → “Radar — publicar no site” → Enable workflow",
        "a autorização continua guardada, mas só sai depois que ele for religado (desligado, ele não roda sozinho)");
    }
    return falhou("workflow_recusou", `o workflow ${WORKFLOW} não aceita acionamento manual no ramo ${RAMO}`);
  }
  if (r.status === 429) return falhou("limite_github", "o GitHub limitou os pedidos por um tempo");
  return falhou("erro_github", `o GitHub respondeu com erro ${r.status}`);
}

// ------------------------------------------------------------------ robôs agendados (v0.22.0, rodada 2 da varredura geral)
// No repositório PÚBLICO, o GitHub desliga sozinho os workflows agendados depois de 60 dias sem atividade ("disabled_inactivity")
// e eles só voltam com "Enable workflow", mesmo que entre commit novo depois. Parados, a coleta da manhã, o robô do site (e as redes
// "junto com o site"), os avisos (que rodam dentro da coleta) e o resumo de segunda param sem aviso nenhum. A lista é fixa aqui
// (nunca vem do pedido) e o token é o mesmo do acionamento (RADAR_GITHUB_TOKEN, Actions: leitura e escrita, só o repositório radar).
// v0.29.0: + o robô dos lembretes por e-mail (rodada de hora em hora, a reserva do acionamento pela agenda do banco)
const ROBOS_AGENDADOS = ["radar-coletar.yml", "radar-site-publicar.yml", "radar-resumo.yml", "radar-lembretes.yml"];

function pedirGithub(token: string, metodo: string, caminho: string, corpo?: unknown): Promise<Response> {
  return fetch(`${GITHUB_API}/repos/${REPO}/actions/workflows/${caminho}`, {
    method: metodo, signal: AbortSignal.timeout(10_000), body: corpo === undefined ? undefined : JSON.stringify(corpo),
    headers: { Accept: "application/vnd.github+json", Authorization: "Bearer " + token, "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "radar-artecon", ...(corpo === undefined ? {} : { "Content-Type": "application/json" }) },
  });
}
// v0.29.0: o acionamento de um workflow fixo (o robô do site ou o dos lembretes; nunca vem do pedido)
const disparar = (token: string, arquivo: string) => pedirGithub(token, "POST", `${arquivo}/dispatches`, { ref: RAMO });
const dispararRobo = (token: string) => disparar(token, WORKFLOW);

/** O estado do workflow no GitHub ("active", "disabled_inactivity", "disabled_manually"…); "" se não deu para ler */
async function estadoWorkflow(token: string, arquivo: string): Promise<string> {
  try {
    const r = await pedirGithub(token, "GET", arquivo);
    const d: any = await r.json().catch(() => ({}));
    return r.ok && typeof d?.state === "string" ? d.state : "";
  } catch { return ""; }
}

/** PUT .../enable: religa o desligado e, no ativo, não muda nada (só renova). true = o GitHub aceitou. */
async function religar(token: string, arquivo: string): Promise<boolean> {
  try { const r = await pedirGithub(token, "PUT", `${arquivo}/enable`); await r.body?.cancel().catch(() => {}); return r.status === 204 || r.ok; }
  catch { return false; }
}

/** Ação "manter_robos": cada robô agendado ativo é renovado e o desligado por inatividade, religado. O desligado à mão
 *  ("disabled_manually": o LEIAME manda desligar ao desfazer a versão) e o que não deu para ler ficam como estão. Nunca lança erro. */
async function manterRobos() {
  const token = env("RADAR_GITHUB_TOKEN").trim();
  if (!token) return { ok: false, robos: [], mensagem: "Falta o segredo RADAR_GITHUB_TOKEN no Supabase (Edge Functions → Secrets): os robôs agendados não são religados." };
  const robos: { workflow: string; estado: string; religado: boolean }[] = [];
  for (const workflow of ROBOS_AGENDADOS) {
    const antes = await estadoWorkflow(token, workflow);
    if (antes !== "active" && antes !== "disabled_inactivity") { robos.push({ workflow, estado: antes || "não lido", religado: false }); continue; }
    const ok = await religar(token, workflow);
    robos.push({ workflow, estado: ok ? "active" : antes, religado: ok && antes === "disabled_inactivity" });
  }
  console.log("radar-redes: robôs agendados — " + robos.map((r) => `${r.workflow} ${r.estado}${r.religado ? " (religado)" : ""}`).join("; "));
  return { ok: robos.every((r) => r.estado === "active"), robos };
}

// ------------------------------------------------------------------ robô dos lembretes (v0.29.0)
// A agenda do banco pede só quando o banco diz que há lembrete para mandar (radar_lembretes_acionar: o horário, "um e-mail por tipo por
// dia" e no máximo um pedido a cada 30 minutos). O workflow é fixo aqui (nunca vem do pedido) e o token é o mesmo do robô do site. Na
// memória desta instância, uma pausa de 60 s entre dois acionamentos que deram certo. Nunca lança erro; o registro é um texto fixo
// (nunca o token nem a resposta do GitHub).
const WORKFLOW_LEMBRETES = "radar-lembretes.yml";
const PAUSA_LEMBRETES_MS = 60_000;
let ultimoLembrete = 0;

async function acionarLembretes(): Promise<{ acionado: boolean; motivo?: string; religado?: boolean }> {
  const token = env("RADAR_GITHUB_TOKEN").trim();
  const falhou = (motivo: string) => {
    console.log(`radar-redes: robô dos lembretes não acionado (${motivo})`);
    return { acionado: false, motivo };
  };
  if (!token) return falhou("sem_token");
  if (Date.now() - ultimoLembrete < PAUSA_LEMBRETES_MS) return { acionado: true, motivo: "ja_acionado" };
  const antes = ultimoLembrete;
  ultimoLembrete = Date.now();                                // reserva já: dois pedidos ao mesmo tempo não acionam duas vezes
  const naoFoi = (motivo: string) => { ultimoLembrete = antes; return falhou(motivo); };
  let r: Response;
  try { r = await disparar(token, WORKFLOW_LEMBRETES); } catch { return naoFoi("github_fora"); }
  await r.body?.cancel().catch(() => {});                     // a resposta do GitHub não é usada (nem registrada)
  if (r.status === 204 || r.status === 200) {
    console.log("radar-redes: robô dos lembretes acionado");
    return { acionado: true };
  }
  if (r.status === 401) return naoFoi("token_recusado");
  if (r.status === 403 || r.status === 404) return naoFoi("sem_acesso");
  if (r.status === 422) {
    // desligado pelo GitHub por inatividade (60 dias sem atividade no repositório público): religa e aciona de novo, uma vez
    const estado = await estadoWorkflow(token, WORKFLOW_LEMBRETES);
    if (estado === "disabled_inactivity" && await religar(token, WORKFLOW_LEMBRETES)) {
      try {
        const r2 = await disparar(token, WORKFLOW_LEMBRETES);
        await r2.body?.cancel().catch(() => {});
        if (r2.status === 204 || r2.status === 200) {
          console.log("radar-redes: robô dos lembretes religado e acionado");
          return { acionado: true, religado: true };
        }
      } catch { /* cai no recado abaixo */ }
      return naoFoi("workflow_religado");
    }
    if (estado.startsWith("disabled")) return naoFoi("workflow_desligado");
    return naoFoi("workflow_recusou");
  }
  if (r.status === 429) return naoFoi("limite_github");
  return naoFoi("erro_github");
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
  // v0.22.0 (rodada 2): um armazenamento só, privado, para a notícia e a Pauta (o bucket público "radar-redes" não é mais criado)
  try {
    await garantirBucket(BUCKET_PAUTA, false);
    itens.push({ item: "Armazenamento das imagens", ok: true,
                 detalhe: `bucket privado "${BUCKET_PAUTA}" (a notícia e a Pauta; a Meta recebe um link de 10 minutos)` });
  } catch (e) { itens.push({ item: "Armazenamento das imagens", ok: false, detalhe: e instanceof Error ? e.message : "erro" }); }
  return { itens, tudo_certo: itens.every((i) => i.ok), versao: VERSAO };
}

async function tratar(req: Request): Promise<Response> {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  const inicio = Date.now();                                  // por pedido: dois pedidos ao mesmo tempo não dividem o relógio
  let quem: Quem = "admin";
  const sufixo = () => quem === "agenda" ? " (agenda)" : "";  // nos registros: só o número do envio e a situação
  try {
    if (req.method !== "POST") throw new Erro(405, "Use POST.");
    if (!SUPABASE_URL) throw new Erro(503, "A função está sem SUPABASE_URL.");
    const pedido = await req.json().catch(() => ({}));
    const acao = String(pedido?.acao ?? "");
    // v0.21.0: a agenda do banco manda a chave do Vault em x-radar-agenda (e a chave anon pública no Authorization, que o
    // "Verify JWT" exige); com o cabeçalho, só a chave vale: sem ela conferida, nada segue
    const chaveAgenda = (req.headers.get("x-radar-agenda") ?? "").trim();
    let sessao: string | null = null;
    if (chaveAgenda) {
      await conferirAgenda(chaveAgenda);
      quem = "agenda";
      // v0.22.0: e mantém os robôs; v0.29.0: e aciona o robô dos lembretes
      if (!["publicar", "agenda_teste", "manter_robos", "acionar_lembretes"].includes(acao)) throw new Erro(403, "A agenda só publica.");
    } else {
      sessao = await quemChamou(req, acao);                   // null = o robô do site (só "publicar" do que foi junto com o site)
      quem = sessao === null ? "robo" : "admin";
    }
    if (!["publicar", "excluir", "diagnostico", "acionar_robo", "agenda_teste", "manter_robos", "acionar_lembretes"].includes(acao)) {
      throw new Erro(400, "Ação desconhecida.");
    }
    if (quem === "robo" && acao !== "publicar") throw new Erro(403, "O robô só publica o que foi autorizado junto com o site.");
    if (acao === "agenda_teste") {                            // v0.21.0: o teste do sql/radar-redes-agenda.sql; não toca na Meta
      if (quem !== "agenda") throw new Erro(403, "Só a agenda do banco usa o teste da agenda.");
      return responder(200, { ok: true, versao: VERSAO });
    }
    if (acao === "diagnostico") return responder(200, await diagnostico());
    if (acao === "acionar_robo") return responder(200, await acionarRobo());     // v0.19.0: só o administrador chega aqui
    if (acao === "manter_robos") return responder(200, await manterRobos());     // v0.22.0 (rodada 2): a agenda ou o administrador
    if (acao === "acionar_lembretes") {                       // v0.29.0: só a agenda do banco
      if (quem !== "agenda") throw new Erro(403, "Só a agenda do banco aciona os lembretes.");
      return responder(200, await acionarLembretes());
    }
    const envio = Number(pedido?.envio);
    if (!Number.isSafeInteger(envio) || envio <= 0) throw new Erro(400, "Informe a autorização (envio).");
    if (acao === "excluir") {
      const x = await excluir(envio, sessao as string);
      console.log(`radar-redes: envio ${envio} → excluído`);
      return responder(200, x);
    }
    const r = await publicar(envio, inicio, quem);
    console.log(`radar-redes: envio ${envio} → ${r.situacao}${sufixo()}`);
    return responder(200, r);
  } catch (e) {
    if (e instanceof Erro) return responder(e.status, { message: e.message });
    console.error(`radar-redes: erro inesperado${sufixo()}`, e instanceof Error ? e.name : "");
    return responder(500, { message: "Erro inesperado na publicação." });
  }
}

const portaLocal = Deno.env.get("RADAR_PORTA_LOCAL");       // só para rodar/testar fora do Supabase
portaLocal ? Deno.serve({ port: Number(portaLocal), hostname: "127.0.0.1" }, tratar) : Deno.serve(tratar);
