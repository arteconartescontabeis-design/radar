// =====================================================================
// RADAR ARTECON — Edge Function "radar-video" (v0.33.0: + a capa da aba Vídeo nos links, no concluir, na prévia e no baixar)
//
// O corretor de vídeo dos reels da Pauta. A equipe grava o reel no celular, em 1 a 12 clipes, e envia pela peça; um robô (GitHub
// Actions do repositório PRIVADO radar-video, com o código do repositório público em robo/video/ por commit fixo) transcreve (Azure F0,
// pelo Speech SDK, no passo próprio do workflow), compara a fala com o roteiro, corta, limpa o som, grava a legenda e a cartela e
// confere o MP4; o administrador vê a prévia, ajusta e aprova a peça amarrada ao sha256 do vídeo; o reel aprovado é baixado e postado à
// mão (a publicação automática fica para a v0.22.1).
//
// Esta função é a única que toca no bucket PRIVADO "radar-videos" (nenhuma política de usuário: a tela não lê nem grava nele direto) e a
// única com quem o robô fala. O robô NÃO tem chave do Supabase nem da Azure aqui: tem só o token estreito do Vault 'radar_video_robo'
// (cabeçalho x-radar-video-robo, conferido pelo banco em radar_video_conferir_robo), que serve só para as ações do robô abaixo, e cada
// link que ele recebe é assinado para um caminho do pedido que está com ele (radar_video_em_curso), com prazo fixo aqui.
//
// Quem chama:
//   tela   o editor ou o administrador logado (a sessão vai ao banco: as funções radar_video_* conferem o papel e a peça);
//   robô   x-radar-video-robo (e a chave anon pública no Authorization, que o "Verify JWT" exige);
//   agenda x-radar-agenda (Vault 'radar_video_agenda', conferido em radar_video_conferir_agenda), de sql/radar-video-agenda.sql.
//   Nenhuma chave interna do Supabase (service_role, sb_secret_…) é aceita como quem chama: 403.
//
// Ações:
//   tela   envio_iniciar   {peca, partes:[{n,tipo,bytes}], fala_pessoa, fala_roteiro, cartela:[…], gancho, declaracoes:[…], duracao?} → o
//                          bucket privado e o banco, que confere tudo (radar_video_criar) ANTES de qualquer arquivo sair (o vídeo vivo da
//                          peça só sai quando os clipes chegam: radar_video_enviado); devolve {id, versao, envios:[{n, caminho,
//                          token}]}: um token de envio (2 h, um caminho só, sem upsert) por clipe, bruto/<id>/<n>, para o envio
//                          retomável (TUS) direto do navegador ao armazenamento, com o token no cabeçalho x-signature
//          envio_renovar  {id} → tokens novos só para os clipes que ainda não chegaram (a tela retoma o envio ao reabrir)
//          envio_concluido{id} → confere cada clipe no armazenamento (tamanho e tipo iguais aos declarados), põe na fila
//                          (radar_video_enviado) e aciona o robô
//          previa         {id} → links do vídeo corrigido e dos 4 quadros, 600 s (o prazo é daqui: o que vier no pedido não conta);
//                          o banco registra quem viu. v0.33.0: + o link da capa (capa, ou null), quando o editor da aba Vídeo a escolheu
//                          (quadros/<id>/<sha256 do vídeo>/capa-<sha256 da capa>.jpg: trocar só a capa monta o mesmo vídeo)
//          baixar         {peca, lido} → link de 300 s do vídeo aprovado (radar_video_para_baixar: aprovado à mão, o mesmo sha256,
//                          o termo de hoje), com o nome reel-<data>.mp4; o banco registra quem baixou. v0.33.0: + o link da capa do
//                          mesmo vídeo (capa_url, reel-<data>-capa.jpg, ou null), para postar o reel com ela
//          acionar        → aciona o robô (workflow_dispatch de radar-video.yml no repositório privado), só com pedido na fila e
//                          com pausa de 30 s; responde sempre 200 {acionado, motivo?, mensagem}
//          diagnostico    (só o administrador) → o bucket privado (corrige se estiver público), o token do GitHub e o workflow, a
//                          fila e a cota do mês. Nunca mostra valor de segredo
//   robô   pegar          → o próximo pedido (radar_video_pegar), os links de leitura dos clipes (600 s) e, se houver, da transcrição
//                          guardada (palavras.json, para montar sem transcrever de novo) e, no modo completo, o token de envio de
//                          trabalho/<id>/<t>/palavras.json. Sem pedido: {pedido: null}
//          links          {id, tentativa, ler:[caminhos], gravar:[caminhos]} → links de leitura (600 s) e tokens de envio por caminho,
//                          só os do pedido: ler bruto/<id>/<n> e trabalho/<id>/<t guardada>/palavras.json; gravar
//                          trabalho/<id>/<t>/palavras.json, corrigido/<id>/<sha256>.mp4 (só se ainda não existe: nunca se
//                          sobrescreve) e quadros/<id>/<sha256>/q1…q4.jpg (v0.33.0: e capa-<sha256 da capa>.jpg, a capa escolhida na
//                          aba Vídeo)
//          audio          {id, tentativa, segundos} → soma os segundos na cota do mês e, se o palavras.json desta rodada está no
//                          armazenamento, passa a valer (radar_video_registrar_audio)
//          parcial        {id, tentativa, relatorio} → o relatório parcial (radar_video_parcial)
//          concluir       {id, tentativa, situacao, relatorio, sha256, bytes, duracao} → confere o vídeo (tamanho e tipo) e os 4
//                          quadros no armazenamento (v0.33.0: e a capa, se o relatório diz que há) e conclui (radar_video_concluir: o
//                          banco decide de novo se precisa regravar)
//          falhar         {id, tentativa, codigo} → radar_video_falhar (o código fixo; os transitórios voltam à fila)
//                          Depois de concluir ou falhar, se ainda há pedido na fila, aciona o robô de novo (proximoDaFila): ele trata
//                          um pedido por execução, e o envio que chegou enquanto ele trabalhava não espera a reserva da agenda
//   agenda acionar        → a reserva (de 10 em 10 minutos, só com fila: o próprio cron confere antes)
//          limpar         → a limpeza diária: radar_video_limpeza diz o que sai; os arquivos saem pela API do armazenamento
//                          (apagar por SQL deixaria órfãos) e radar_video_limpo registra
//          agenda_teste   → {ok, versao}, sem tocar no armazenamento nem no GitHub (o teste do sql/radar-video-agenda.sql)
//
// Registros (Logs do Supabase): só a ação, o uuid do vídeo e um resultado fixo. Nunca link assinado, token, chave, nome, fala ou a
// mensagem do armazenamento ou do GitHub.
//
// Segredos (Supabase → Edge Functions → Secrets):
//   RADAR_VIDEO_GITHUB_TOKEN  token fino do GitHub (Fine-grained token, só o repositório radar-video, Actions: leitura e escrita).
//                             Fica SÓ aqui: nunca no GitHub, na tela ou no chat. Sem ele, a função não aciona o robô (nem a reserva
//                             da agenda, que passa por aqui, mas conta cada rodada): o pedido vira o aviso "robo_nao_pegou" na peça
//                             uns 30 a 40 minutos depois do envio, e o diagnóstico avisa. Tirar o token NÃO para o corretor: a agenda
//                             própria do workflow (2 vezes por dia útil) pega a fila sem ele — para parar, desligue o workflow
//   RADAR_VIDEO_GITHUB_REPO   opcional; padrão arteconartescontabeis-design/radar-video
//   RADAR_VIDEO_GITHUB_RAMO   opcional; padrão main
// SUPABASE_URL, a chave pública (SUPABASE_PUBLISHABLE_KEYS ou SUPABASE_ANON_KEY) e a chave interna (SUPABASE_SECRET_KEYS ou
// SUPABASE_SERVICE_ROLE_KEY) o Supabase já fornece.
// A transcrição é do robô (ajustes do dono): os segredos da Azure ficam no repositório privado, não aqui.
// =====================================================================

const VERSAO = "0.33.0";
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
const BUCKET = "radar-videos";
// prazos dos links, fixos aqui (quem chama não escolhe); cada objeto sobe com cacheControl de 60 s (a tela e o robô mandam), então a
// validade efetiva vai até o prazo + 60 s
const LINK_PREVIA_S = 600, LINK_BAIXAR_S = 300, LINK_ROBO_S = 600, CACHE_S = 60;
const TIPOS = ["video/mp4", "video/quicktime", "application/json", "image/jpeg"];
const TEMPO_ARMAZENAMENTO_MS = Number(env("RADAR_VIDEO_ARMAZENAMENTO_MS", "15000"));
const LIMITE_LIMPEZA_MS = 110_000;                                // a limpeza para antes do corte de ~150 s do Supabase
const MAX_PEDIDO = 256 * 1024;                                    // o corpo do pedido (o relatório tem até 60.000 caracteres)

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

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SHA = /^[0-9a-f]{64}$/;
// v0.33.0: o caminho da capa de um vídeo (o sha256 da capa no nome)
const capaDe = (id: string, sha: string) => new RegExp(`^quadros/${id}/${sha}/capa-[0-9a-f]{64}\\.jpg$`);
function uuid(x: unknown): string {
  const s = String(x ?? "");
  if (!UUID.test(s)) throw new Erro(400, "Informe o vídeo (id).");
  return s;
}
function inteiro(x: unknown, min: number, max: number, nome: string): number {
  const n = Number(x);
  if (!Number.isSafeInteger(n) || n < min || n > max) throw new Erro(400, `Informe ${nome}.`);
  return n;
}

// ------------------------------------------------------------------ banco
/** "quem" é a sessão do usuário ("Bearer …", com a chave pública) ou os cabeçalhos da chave interna (comoServico). A mensagem que
 *  volta é a do banco sem o código (RADARnnn: …), que é fixa e sem nome. */
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
    // v0.22.0 (varredura geral): a falha do próprio banco (500 por tempo esgotado, 503 sem conexão ou reiniciando, 504 do pool) é
    // passageira: vai como 502, que o robô repete e devolve à fila (antes virava 400, "robo_recusado", e o pedido ia a "erro" de vez).
    // As recusas das regras (RADARnnn) são sempre 4xx (P0001/23514 → 400, 42501 → 403)
    if (r.status >= 500 && !radar) throw new Erro(502, "O banco não respondeu. Tente de novo em alguns minutos.");
    throw new Erro(r.status === 401 ? 401 : r.status === 403 ? 403 : 400, radar ? radar[1].slice(0, 400) : `Erro ${r.status} no banco.`);
  }
  return dados;
}
// a chave interna do Supabase (v0.14.2): a nova (sb_secret_…) só vale no cabeçalho apikey; a antiga (JWT service_role) vai nos dois
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

/** O pedido veio com uma chave interna do Supabase (a desta função, a de qualquer projeto em sb_secret_…, ou um JWT de papel interno)?
 *  Ela fura todas as regras de acesso: aqui ninguém chama com ela. */
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

/** A sessão da tela: o editor ou o administrador (o banco diz o papel). Devolve o "Bearer …" e o papel. */
async function sessaoDaTela(req: Request): Promise<{ sessao: string; papel: string }> {
  const sessao = req.headers.get("Authorization") ?? "";
  if (!/^Bearer\s+\S+/.test(sessao)) throw new Erro(401, "Sessão não informada.");
  const papel = await banco(sessao, "POST", "rpc/radar_papel", {});
  if (papel !== "admin" && papel !== "editor") throw new Erro(403, "Só o editor ou o administrador usa o corretor de vídeo.");
  return { sessao, papel };
}

/** A chave do robô (x-radar-video-robo) ou da agenda (x-radar-agenda) confere com a do Vault? Quem confere é o banco (só o papel interno
 *  executa). A recusa é sempre a mesma frase: não diz se a conferência existe, falhou ou se a chave só está errada. A chave nunca vai para
 *  mensagem nem registro. */
async function conferirChave(funcao: string, chave: string): Promise<void> {
  let ok = false;
  if (chave.length >= 32 && chave.length <= 200) {
    try { ok = (await banco(comoServico(), "POST", `rpc/${funcao}`, { p_chave: chave }, 10_000)) === true; }
    catch (e) {
      if (e instanceof Erro && e.status === 503) throw e;                       // função sem a chave interna: configuração
      console.log(`radar-video: conferência da chave falhou (${e instanceof Erro ? e.status : "sem resposta do banco"})`);
    }
  }
  if (!ok) throw new Erro(401, "Chave não confere.");
}

// ------------------------------------------------------------------ armazenamento (bucket privado radar-videos)
// Toda resposta do armazenamento fica aqui: a mensagem dele nunca vai para quem chamou nem para o registro (pode citar o caminho).
async function armazenamento(metodo: string, caminho: string, corpo?: unknown): Promise<{ ok: boolean; status: number; dados: any }> {
  let r: Response;
  try {
    r = await fetch(`${SUPABASE_URL}/storage/v1/${caminho}`, {
      method: metodo, headers: { ...comoServico(), "Content-Type": "application/json" },
      body: corpo === undefined ? undefined : JSON.stringify(corpo), signal: AbortSignal.timeout(TEMPO_ARMAZENAMENTO_MS),
    });
  } catch { throw new Erro(502, "O armazenamento não respondeu. Tente de novo em alguns minutos."); }
  const dados = await r.json().catch(() => null);
  return { ok: r.ok, status: r.status, dados };
}

/** O bucket existe e é PRIVADO? Se não existe, cria privado e SEM limite de tamanho próprio: vale o limite global do projeto (Storage →
 *  Settings; no Free, 50 MB por arquivo). O armazenamento recusa o limite do bucket maior que o global (EntityTooLarge), e com ele o
 *  bucket nunca nasceria no Free. Se alguém o deixou público no painel, volta a privado (só o "public": o resto fica como está). Devolve
 *  o que fez. */
async function garantirBucket(): Promise<"ok" | "criado" | "corrigido"> {
  const g = await armazenamento("GET", `bucket/${BUCKET}`);
  if (g.ok) {
    if (g.dados?.public === false) return "ok";
    const u = await armazenamento("PUT", `bucket/${BUCKET}`, { public: false });
    if (!u.ok) {
      throw new Erro(502, `O armazenamento "${BUCKET}" está público e não foi possível deixá-lo privado (${u.status}): no Supabase → Storage, ` +
        "edite o bucket e desligue “Public bucket”.");
    }
    console.log("radar-video: o bucket estava público e voltou a privado");
    return "corrigido";
  }
  const c = await armazenamento("POST", "bucket", { id: BUCKET, name: BUCKET, public: false, allowed_mime_types: TIPOS });
  if (c.ok) return "criado";
  if (c.status === 409 || String(c.dados?.statusCode ?? "") === "409") return garantirBucket();     // criado agora por outro pedido
  throw new Erro(502, `Não foi possível criar o armazenamento dos vídeos (${c.status}). Nada foi enviado: tente de novo em alguns ` +
    "minutos; se repetir, o administrador confere em Supabase → Storage.");
}

/** Token de envio (2 h, um caminho só, sem upsert: o mesmo caminho dá "já existe") — o navegador manda por TUS com x-signature; o robô,
 *  por PUT no url. */
async function tokenDeEnvio(caminho: string): Promise<{ caminho: string; token: string; url: string }> {
  const r = await armazenamento("POST", `object/upload/sign/${BUCKET}/${caminho}`, {});
  let token = "";
  try { token = new URL(SUPABASE_URL + "/storage/v1" + String(r.dados?.url ?? "")).searchParams.get("token") ?? ""; } catch { /* sem url */ }
  if (!token && typeof r.dados?.token === "string") token = r.dados.token;
  if (!r.ok || !token) throw new Erro(502, "Não foi possível preparar o envio no armazenamento. Nada foi enviado: tente de novo.");
  return { caminho, token, url: `${SUPABASE_URL}/storage/v1/object/upload/sign/${BUCKET}/${caminho}?token=${encodeURIComponent(token)}` };
}

/** Link assinado de leitura, com o prazo daqui. baixarComo: o nome do arquivo baixado. */
async function linkDeLeitura(caminho: string, segundos: number, baixarComo = ""): Promise<string> {
  const r = await armazenamento("POST", `object/sign/${BUCKET}/${caminho}`, { expiresIn: segundos });
  const assinado = String(r.dados?.signedURL ?? r.dados?.signedUrl ?? "");
  if (!r.ok || !assinado.startsWith(`/object/sign/${BUCKET}/`)) {
    throw new Erro(502, "Não foi possível preparar o link do armazenamento (o arquivo pode ter sido apagado). Tente de novo.");
  }
  return `${SUPABASE_URL}/storage/v1${assinado}` + (baixarComo ? `&download=${encodeURIComponent(baixarComo)}` : "");
}

type Objeto = { nome: string; bytes: number; tipo: string };
/** O que há numa pasta do bucket (só o primeiro nível): os arquivos (nome, tamanho, tipo) e as subpastas. */
async function listar(pasta: string): Promise<{ arquivos: Objeto[]; pastas: string[] }> {
  const arquivos: Objeto[] = [], pastas: string[] = [];
  for (let offset = 0; offset < 10_000; offset += 1000) {
    const r = await armazenamento("POST", `object/list/${BUCKET}`, { prefix: pasta, limit: 1000, offset, sortBy: { column: "name", order: "asc" } });
    if (!r.ok || !Array.isArray(r.dados)) throw new Erro(502, "Não foi possível ler o armazenamento. Tente de novo em alguns minutos.");
    for (const o of r.dados) {
      const nome = String(o?.name ?? "");
      if (!nome || nome === ".emptyFolderPlaceholder") continue;
      if (o?.id === null || o?.id === undefined) pastas.push(nome);
      else arquivos.push({ nome, bytes: Number(o?.metadata?.size ?? -1), tipo: String(o?.metadata?.mimetype ?? "") });
    }
    if (r.dados.length < 1000) break;
  }
  return { arquivos, pastas };
}

/** Todos os arquivos de uma pasta e das subpastas (até 2 níveis: trabalho/<id>/<t>/, quadros/<id>/<sha>/). */
async function arquivosDe(pasta: string, nivel = 0): Promise<string[]> {
  const { arquivos, pastas } = await listar(pasta);
  const todos = arquivos.map((a) => `${pasta}/${a.nome}`);
  if (nivel < 2) for (const p of pastas) todos.push(...await arquivosDe(`${pasta}/${p}`, nivel + 1));
  return todos;
}

/** Apaga pela API do armazenamento (DELETE /object/{bucket} com os nomes; o que já não existe não é erro). */
async function apagar(caminhos: string[]): Promise<void> {
  for (let i = 0; i < caminhos.length; i += 100) {
    const r = await armazenamento("DELETE", `object/${BUCKET}`, { prefixes: caminhos.slice(i, i + 100) });
    if (!r.ok) throw new Erro(502, "O armazenamento não apagou os arquivos. A limpeza tenta de novo amanhã.");
  }
}

// ------------------------------------------------------------------ robô no GitHub
// O token com Actions: escrita aciona qualquer workflow do repositório: o workflow e o ramo são fixos aqui (nada vem do pedido).
const GITHUB_API = env("RADAR_GITHUB_API", "https://api.github.com").replace(/\/+$/, "");    // só os testes trocam
const REPO = env("RADAR_VIDEO_GITHUB_REPO", "arteconartescontabeis-design/radar-video").trim();
const RAMO = env("RADAR_VIDEO_GITHUB_RAMO", "main").trim();
const WORKFLOW = "radar-video.yml";
const PAUSA_ROBO_MS = 30_000;
let ultimoAcionamento = 0;                                   // nesta instância: cliques seguidos não acionam o robô de novo
type Acionamento = { acionado: boolean; motivo?: string; em?: string; mensagem: string };
const cabecalhosGithub = (token: string) => ({ Accept: "application/vnd.github+json", Authorization: "Bearer " + token,
  "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "radar-artecon" });

/** Há pedido para o robô? Se a consulta falhar, conta como pendente (o robô confere de novo ao pegar). */
async function haFila(): Promise<boolean> {
  try { return (await banco(comoServico(), "POST", "rpc/radar_video_ha_fila", { p_minutos: 0 }, 10_000)) === true; }
  catch { return true; }
}

/** Aciona o robô no repositório privado. Nunca lança erro: o pedido já está na fila e sai na reserva da agenda. semPausa: o robô
 *  acabou de terminar um pedido (proximoDaFila), e a pausa de 30 s — que evita dois acionamentos para o mesmo envio — não vale. */
async function acionarRobo(semPausa = false): Promise<Acionamento> {
  const token = env("RADAR_VIDEO_GITHUB_TOKEN").trim();
  if (!token) {
    return { acionado: false, motivo: "sem_token", mensagem: "O robô do corretor não foi acionado: falta o segredo RADAR_VIDEO_GITHUB_TOKEN no " +
      "Supabase (Edge Functions → Secrets). O vídeo continua na fila." };
  }
  if (!(await haFila())) return { acionado: false, motivo: "nada_na_fila", mensagem: "Não há vídeo na fila: o robô não foi acionado." };
  if (!semPausa && Date.now() - ultimoAcionamento < PAUSA_ROBO_MS) {
    return { acionado: true, em: new Date(ultimoAcionamento).toISOString(), mensagem: "O robô já foi acionado há instantes." };
  }
  const antes = ultimoAcionamento;
  ultimoAcionamento = Date.now();                             // reserva já: dois cliques ao mesmo tempo não acionam duas vezes
  const falhou = (motivo: string, porque: string): Acionamento => {
    ultimoAcionamento = antes;
    console.log(`radar-video: robô não acionado (${motivo})`);
    return { acionado: false, motivo, mensagem: `O robô do corretor não foi acionado agora: ${porque}; o vídeo continua na fila e a reserva ` +
      "da agenda tenta de novo em até 10 minutos." };
  };
  let r: Response;
  try {
    r = await fetch(`${GITHUB_API}/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
      method: "POST", headers: { ...cabecalhosGithub(token), "Content-Type": "application/json" },
      body: JSON.stringify({ ref: RAMO }), signal: AbortSignal.timeout(10_000),
    });
  } catch { return falhou("github_fora", "o GitHub não respondeu"); }
  await r.body?.cancel().catch(() => {});                     // a resposta do GitHub não é usada (nem mostrada)
  if (r.status === 204 || r.status === 200) {
    console.log("radar-video: robô acionado");
    return { acionado: true, em: new Date(ultimoAcionamento).toISOString(), mensagem: "Robô acionado: o vídeo corrigido deve ficar pronto em alguns minutos." };
  }
  if (r.status === 401) return falhou("token_recusado", "o GitHub recusou o token (vencido ou revogado): gere outro e troque o RADAR_VIDEO_GITHUB_TOKEN");
  if (r.status === 403 || r.status === 404) {
    return falhou("sem_acesso", `o token não tem acesso ao repositório ${REPO} com a permissão Actions: leitura e escrita (ou o GitHub limitou os pedidos)`);
  }
  if (r.status === 422) return falhou("workflow_recusou", `o workflow ${WORKFLOW} não aceita acionamento manual no ramo ${RAMO}`);
  if (r.status === 429) return falhou("limite_github", "o GitHub limitou os pedidos por um tempo");
  return falhou("erro_github", `o GitHub respondeu com erro ${r.status}`);
}

/** O robô trata UM pedido por execução e não olha a fila de novo antes de sair. Ao concluir ou falhar, se ainda há pedido na fila — o
 *  envio que chegou enquanto ele trabalhava (a tela recebeu "o robô já foi acionado há instantes") ou o mesmo pedido de volta à fila
 *  (falha transitória) —, aciona de novo, sem esperar a reserva da agenda (que só age 3 minutos depois e nunca com o robô trabalhando).
 *  A execução a mais, se a fila esvaziar antes, gasta cerca de 1 minuto e sai sem pedido. Nunca lança: a resposta ao robô não depende
 *  disto. */
async function proximoDaFila(): Promise<void> {
  try { await acionarRobo(true); } catch { /* a reserva da agenda aciona */ }
}

// ------------------------------------------------------------------ tela
async function envioIniciar(sessao: string, p: any) {
  const partes = Array.isArray(p?.partes) ? p.partes : [];
  // o armazenamento antes do registro: se ele falha, nada fica registrado (nem gasta uma das 50 gravações da peça)
  await garantirBucket();
  // a duração que o navegador leu dos clipes (quando leu): o banco confere se cabe no que sobra da cota do mês antes de qualquer envio
  const duracao = Number(p?.duracao);
  const r = await banco(sessao, "POST", "rpc/radar_video_criar", {
    p_peca: p?.peca ?? null, p_partes: partes, p_fala_pessoa: p?.fala_pessoa ?? null, p_fala_roteiro: p?.fala_roteiro ?? null,
    p_cartela: Array.isArray(p?.cartela) ? p.cartela : null, p_gancho: p?.gancho === true, p_declaracoes: Array.isArray(p?.declaracoes) ? p.declaracoes : null,
    p_duracao: p?.duracao !== null && p?.duracao !== undefined && Number.isFinite(duracao) && duracao > 0 && duracao <= 3600 ? duracao : null,
  });
  const id = uuid(r?.id);                                    // o banco conferiu os clipes: de 1 a 12, na ordem
  const envios = [];
  for (let n = 1; n <= partes.length; n++) {
    const { caminho, token } = await tokenDeEnvio(`bruto/${id}/${n}`);
    envios.push({ n, caminho, token });
  }
  return { id, versao: r.versao, bucket: BUCKET, cache_s: CACHE_S, envios };
}

/** O envio que espera os clipes (radar_video_para_envio: só quem começou, ou o administrador) e o que já chegou ao armazenamento. */
async function clipesDoEnvio(sessao: string, id: string) {
  const e = await banco(sessao, "POST", "rpc/radar_video_para_envio", { p_id: id });
  const { arquivos } = await listar(`bruto/${id}`);
  return { partes: (Array.isArray(e?.partes) ? e.partes : []) as { n: number; tipo: string; bytes: number }[],
           chegou: new Map(arquivos.map((a) => [a.nome, a])) };
}

async function envioRenovar(sessao: string, id: string) {
  const { partes, chegou } = await clipesDoEnvio(sessao, id);
  const envios = [];
  for (const p of partes) {
    if (chegou.has(String(p.n))) continue;
    const { caminho, token } = await tokenDeEnvio(`bruto/${id}/${p.n}`);
    envios.push({ n: p.n, caminho, token });
  }
  return { id, bucket: BUCKET, cache_s: CACHE_S, envios, prontos: partes.filter((p) => chegou.has(String(p.n))).map((p) => p.n) };
}

async function envioConcluido(sessao: string, id: string) {
  const { partes, chegou } = await clipesDoEnvio(sessao, id);
  const faltam = partes.filter((p) => !chegou.has(String(p.n))).map((p) => p.n);
  if (faltam.length) throw new Erro(409, `Ainda faltam clipes no armazenamento (nº ${faltam.join(", ")}): retome o envio.`);
  const diferentes = partes.filter((p) => { const a = chegou.get(String(p.n))!; return a.bytes !== p.bytes || a.tipo !== p.tipo; }).map((p) => p.n);
  if (diferentes.length) {
    throw new Erro(409, `Os clipes nº ${diferentes.join(", ")} chegaram diferentes do que a tela declarou (tamanho ou tipo): envie a gravação de novo.`);
  }
  await banco(sessao, "POST", "rpc/radar_video_enviado", { p_id: id });
  return { id, situacao: "na_fila", robo: await acionarRobo() };
}

async function previa(sessao: string, id: string) {
  const r = await banco(sessao, "POST", "rpc/radar_video_para_previa", { p_id: id });
  const sha = String(r?.sha256 ?? "");
  const quadros = Array.isArray(r?.quadros) ? r.quadros.map(String) : [];
  if (!SHA.test(sha) || r?.video !== `corrigido/${id}/${sha}.mp4` || quadros.length !== 4
      || quadros.some((q: string, i: number) => q !== `quadros/${id}/${sha}/q${i + 1}.jpg`)
      || (r?.capa !== undefined && r?.capa !== null && !capaDe(id, sha).test(String(r.capa)))) {
    throw new Erro(502, "O banco devolveu um caminho fora do esperado.");
  }
  return { video: await linkDeLeitura(r.video, LINK_PREVIA_S), quadros: await Promise.all(quadros.map((q: string) => linkDeLeitura(q, LINK_PREVIA_S))),
           capa: r?.capa ? await linkDeLeitura(r.capa, LINK_PREVIA_S) : null, sha256: sha, expira_s: LINK_PREVIA_S };
}

async function baixar(sessao: string, peca: number, lido: string) {
  const r = await banco(sessao, "POST", "rpc/radar_video_para_baixar", { p_peca: peca, p_lido: lido });
  if (r?.motivo) throw new Erro(409, String(r.motivo));
  const caminho = String(r?.caminho ?? ""), data = String(r?.data ?? "");
  const m = /^corrigido\/([0-9a-f-]{36})\/([0-9a-f]{64})\.mp4$/.exec(caminho);
  // v0.33.0: a capa é a do mesmo vídeo aprovado (o mesmo id e o mesmo sha256)
  if (!m || !/^\d{4}-\d{2}-\d{2}$/.test(data) || (r?.capa !== undefined && r?.capa !== null && !capaDe(m[1], m[2]).test(String(r.capa)))) {
    throw new Erro(502, "O banco devolveu um caminho fora do esperado.");
  }
  return { url: await linkDeLeitura(caminho, LINK_BAIXAR_S, `reel-${data}.mp4`),
           capa_url: r?.capa ? await linkDeLeitura(r.capa, LINK_BAIXAR_S, `reel-${data}-capa.jpg`) : null, expira_s: LINK_BAIXAR_S };
}

async function diagnostico(sessao: string) {
  const itens: { item: string; ok: boolean; detalhe: string }[] = [];
  const falha = (e: unknown) => e instanceof Erro ? e.message : "erro inesperado";
  try {
    const b = await garantirBucket();
    itens.push({ item: "Armazenamento dos vídeos", ok: true, detalhe: `bucket privado "${BUCKET}"` +
      (b === "criado" ? " (criado agora)" : b === "corrigido" ? " (estava público: voltou a privado)" : "") });
  } catch (e) { itens.push({ item: "Armazenamento dos vídeos", ok: false, detalhe: falha(e) }); }
  const token = env("RADAR_VIDEO_GITHUB_TOKEN").trim();
  itens.push({ item: "Token do GitHub", ok: !!token, detalhe: token ? "RADAR_VIDEO_GITHUB_TOKEN cadastrado"
    : "Falta o segredo RADAR_VIDEO_GITHUB_TOKEN (Supabase → Edge Functions → Secrets): sem ele, nada aciona o robô" });
  if (token) {
    let detalhe = "", ok = false;
    try {
      const r = await fetch(`${GITHUB_API}/repos/${REPO}/actions/workflows/${WORKFLOW}`, { headers: cabecalhosGithub(token), signal: AbortSignal.timeout(10_000) });
      const d: any = await r.json().catch(() => ({}));
      ok = r.ok && d?.state === "active";
      detalhe = r.ok ? `${WORKFLOW} em ${REPO}: ${d?.state === "active" ? "ativo" : "desativado (Actions → o workflow → Enable workflow)"}`
        : r.status === 401 ? "o GitHub recusou o token (vencido ou revogado)"
        : r.status === 404 || r.status === 403 ? `o token não alcança ${WORKFLOW} em ${REPO} (o workflow não foi copiado, ou falta a permissão Actions)`
        : `o GitHub respondeu com erro ${r.status}`;
    } catch { detalhe = "o GitHub não respondeu"; }
    itens.push({ item: "Workflow do robô", ok, detalhe });
  }
  try {
    const f = await banco(sessao, "POST", "rpc/radar_video_resumo", {});
    const espera = Number(f?.espera_s ?? 0), usados = Number(f?.segundos_mes ?? 0), limite = Number(f?.limite_s ?? 0);
    itens.push({ item: "Fila do corretor", ok: !(Number(f?.na_fila) > 0 && espera > 1800), detalhe: `${Number(f?.na_fila ?? 0)} na fila` +
      (Number(f?.na_fila) > 0 ? ` (o mais antigo há ${Math.round(espera / 60)} min)` : "") + `, ${Number(f?.processando ?? 0)} com o robô` });
    itens.push({ item: "Transcrição no mês", ok: usados < limite, detalhe: `${(usados / 60).toFixed(1)} de ${Math.round(limite / 60)} minutos ` +
      "(Configurações → Corretor de vídeo → limite_min_mes; o F0 da Azure, 300 minutos por mês, é dividido com a Agenda, que se reserva 270)" });
  } catch (e) { itens.push({ item: "Fila do corretor", ok: false, detalhe: falha(e) }); }
  return { itens, tudo_certo: itens.every((i) => i.ok), versao: VERSAO };
}

// ------------------------------------------------------------------ robô
async function pegar(servico: Record<string, string>) {
  const p = await banco(servico, "POST", "rpc/radar_video_pegar", {});
  if (!p) return { pedido: null };
  const id = uuid(p.id), t = inteiro(p.tentativa, 1, 200, "a tentativa");
  try {
    const partes = [];
    for (const x of Array.isArray(p.partes) ? p.partes : []) {
      const n = inteiro(x?.n, 1, 12, "o clipe");
      partes.push({ n, tipo: x.tipo, bytes: x.bytes, url: await linkDeLeitura(`bruto/${id}/${n}`, LINK_ROBO_S) });
    }
    const guardada = p.palavras_tentativa ? inteiro(p.palavras_tentativa, 1, 200, "a transcrição") : 0;
    return { pedido: p, links: { partes, palavras: guardada ? await linkDeLeitura(`trabalho/${id}/${guardada}/palavras.json`, LINK_ROBO_S) : null },
             envio_palavras: p.modo === "completo" ? await tokenDeEnvio(`trabalho/${id}/${t}/palavras.json`) : null,
             expira_s: LINK_ROBO_S, cache_s: CACHE_S };
  } catch (e) {
    // sem os links o robô não faz nada: o pedido volta à fila (o armazenamento é transitório) em vez de esperar 20 minutos parado
    await banco(servico, "POST", "rpc/radar_video_falhar", { p_id: id, p_tentativa: t, p_codigo: "storage" }).catch(() => {});
    throw e;
  }
}

/** Links por caminho, só os do pedido que está com o robô nesta rodada. */
async function links(servico: Record<string, string>, id: string, t: number, ler: unknown, gravar: unknown) {
  const c = await banco(servico, "POST", "rpc/radar_video_em_curso", { p_id: id, p_tentativa: t });
  const lista = (x: unknown, max: number) => {
    if (x === undefined || x === null) return [] as string[];
    if (!Array.isArray(x) || x.length > max || x.some((v) => typeof v !== "string")) throw new Erro(400, "Caminhos fora do formato.");
    return [...new Set(x as string[])];
  };
  const paraLer = lista(ler, 13), paraGravar = lista(gravar, 6);
  const guardada = Number(c?.palavras_tentativa ?? 0), nPartes = Number(c?.partes ?? 0);
  const podeLer = (k: string) => {
    const m = new RegExp(`^bruto/${id}/(\\d{1,2})$`).exec(k);
    return (m !== null && Number(m[1]) >= 1 && Number(m[1]) <= nPartes && String(Number(m[1])) === m[1])
      || (guardada > 0 && k === `trabalho/${id}/${guardada}/palavras.json`);
  };
  const podeGravar = (k: string) => k === `trabalho/${id}/${t}/palavras.json` || new RegExp(`^corrigido/${id}/[0-9a-f]{64}\\.mp4$`).test(k)
    || new RegExp(`^quadros/${id}/[0-9a-f]{64}/(q[1-4]|capa-[0-9a-f]{64})\\.jpg$`).test(k);   // v0.33.0: + a capa (vídeo + 4 quadros + capa = 6)
  const recusados = [...paraLer.filter((k) => !podeLer(k)), ...paraGravar.filter((k) => !podeGravar(k))];
  if (recusados.length) throw new Erro(403, `${recusados.length} caminho(s) fora do pedido.`);
  // o vídeo corrigido nunca se sobrescreve: o caminho tem o sha256, e o que já existe não ganha token
  if (paraGravar.some((k) => k.startsWith("corrigido/"))) {
    const { arquivos } = await listar(`corrigido/${id}`);
    if (paraGravar.some((k) => arquivos.some((a) => k === `corrigido/${id}/${a.nome}`))) {
      throw new Erro(409, "O vídeo corrigido com este sha256 já está no armazenamento: o caminho nunca se sobrescreve.");
    }
  }
  const respostaLer: Record<string, string> = {}, respostaGravar: Record<string, { url: string; token: string }> = {};
  for (const k of paraLer) respostaLer[k] = await linkDeLeitura(k, LINK_ROBO_S);
  for (const k of paraGravar) { const e = await tokenDeEnvio(k); respostaGravar[k] = { url: e.url, token: e.token }; }
  return { ler: respostaLer, gravar: respostaGravar, expira_s: LINK_ROBO_S, cache_s: CACHE_S };
}

async function audio(servico: Record<string, string>, id: string, t: number, segundos: unknown) {
  const s = Number(segundos);
  if (!Number.isFinite(s) || s < 0 || s > 300) throw new Erro(400, "Informe os segundos de áudio transcritos (de 0 a 300).");
  await banco(servico, "POST", "rpc/radar_video_em_curso", { p_id: id, p_tentativa: t });
  const { arquivos } = await listar(`trabalho/${id}/${t}`);
  const pal = arquivos.find((a) => a.nome === "palavras.json");
  const guardou = !!pal && pal.bytes > 0 && pal.bytes <= 5 * 1024 * 1024 && pal.tipo.startsWith("application/json");
  const r = await banco(servico, "POST", "rpc/radar_video_registrar_audio", { p_id: id, p_tentativa: t, p_segundos: s, p_palavras: guardou });
  return { palavras_guardadas: guardou, restante_s: r?.restante_s ?? null };
}

async function concluir(servico: Record<string, string>, id: string, t: number, p: any) {
  const sha = String(p?.sha256 ?? ""), bytes = Number(p?.bytes);
  if (!SHA.test(sha) || !Number.isSafeInteger(bytes) || bytes < 1) throw new Erro(400, "Informe o sha256 e o tamanho do vídeo corrigido.");
  await banco(servico, "POST", "rpc/radar_video_em_curso", { p_id: id, p_tentativa: t });
  const video = (await listar(`corrigido/${id}`)).arquivos.find((a) => a.nome === `${sha}.mp4`);
  if (!video || video.bytes !== bytes || video.tipo !== "video/mp4") {
    throw new Erro(409, "O vídeo corrigido não está no armazenamento com o tamanho e o tipo informados: suba de novo.");
  }
  const quadros = (await listar(`quadros/${id}/${sha}`)).arquivos;
  const faltam = [1, 2, 3, 4].filter((k) => !quadros.some((a) => a.nome === `q${k}.jpg` && a.tipo === "image/jpeg" && a.bytes > 0 && a.bytes <= 5 * 1024 * 1024));
  if (faltam.length) throw new Erro(409, `Faltam quadros no armazenamento (q${faltam.join(", q")}): suba de novo.`);
  // v0.33.0: a capa escolhida na aba Vídeo, ao lado dos quadros (o mesmo sha256), com o sha256 DELA no nome: a capa de antes do mesmo
  // vídeo (trocar só a capa monta o mesmo vídeo) não passa pela nova
  if (p?.relatorio?.capa) {
    const capa = String(p.relatorio.capa?.sha256 ?? "");
    if (!SHA.test(capa)) throw new Erro(400, "Informe o sha256 da capa.");
    if (!quadros.some((a) => a.nome === `capa-${capa}.jpg` && a.tipo === "image/jpeg" && a.bytes > 0 && a.bytes <= 5 * 1024 * 1024)) {
      throw new Erro(409, "Falta a capa no armazenamento: suba de novo.");
    }
  }
  return await banco(servico, "POST", "rpc/radar_video_concluir", {
    p_id: id, p_tentativa: t, p_situacao: p?.situacao ?? null, p_relatorio: p?.relatorio ?? null, p_sha256: sha, p_bytes: bytes,
    p_duracao: Number(p?.duracao),
  });
}

// ------------------------------------------------------------------ agenda: limpeza
async function limpar(servico: Record<string, string>, inicio: number) {
  const r = await banco(servico, "POST", "rpc/radar_video_limpeza", {});
  let videos = 0, arquivos = 0, falhas = 0, adiados = 0;
  for (const item of Array.isArray(r?.itens) ? r.itens : []) {
    if (Date.now() - inicio > LIMITE_LIMPEZA_MS) { adiados++; continue; }      // o resto fica para amanhã (a limpeza devolve de novo)
    try {
      const id = uuid(item?.id), manter = String(item?.manter ?? "");
      const grupos = (Array.isArray(item?.apagar) ? item.apagar : []).filter((g: unknown) =>
        ["bruto", "trabalho", "corrigido"].includes(String(g)) || (g === "antigos" && SHA.test(manter))) as string[];
      if (!grupos.length) continue;
      const caminhos: string[] = [];
      for (const g of grupos) {
        if (g === "bruto" || g === "trabalho") caminhos.push(...await arquivosDe(`${g}/${id}`));
        if (g === "corrigido") caminhos.push(...await arquivosDe(`corrigido/${id}`), ...await arquivosDe(`quadros/${id}`));
        if (g === "antigos") {                                  // as versões antigas: tudo menos o sha256 atual
          caminhos.push(...(await arquivosDe(`corrigido/${id}`)).filter((k) => k !== `corrigido/${id}/${manter}.mp4`),
                        ...(await arquivosDe(`quadros/${id}`)).filter((k) => !k.startsWith(`quadros/${id}/${manter}/`)));
        }
      }
      const unicos = [...new Set(caminhos)];
      await apagar(unicos);
      await banco(servico, "POST", "rpc/radar_video_limpo", { p_id: id, p_grupos: grupos });
      videos++;
      arquivos += unicos.length;
    } catch { falhas++; }
  }
  console.log(`radar-video: limpeza → ${videos} vídeo(s), ${arquivos} arquivo(s), ${Number(r?.textos ?? 0)} texto(s)` +
    (falhas ? `, ${falhas} falha(s)` : "") + (adiados ? `, ${adiados} para amanhã` : ""));
  return { videos, arquivos, textos: Number(r?.textos ?? 0), falhas, adiados };
}

// ------------------------------------------------------------------ pedido
const ACOES_TELA = ["envio_iniciar", "envio_renovar", "envio_concluido", "previa", "baixar", "acionar", "diagnostico"];
const ACOES_ROBO = ["pegar", "links", "audio", "parcial", "concluir", "falhar"];
const ACOES_AGENDA = ["acionar", "limpar", "agenda_teste"];

async function tratar(req: Request): Promise<Response> {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  const inicio = Date.now();
  let acao = "", quem = "tela", id = "";
  const registro = (fim: string) => console.log(`radar-video: ${acao || "?"}${id ? " " + id : ""} → ${fim}${quem !== "tela" ? ` (${quem})` : ""}`);
  try {
    if (req.method !== "POST") throw new Erro(405, "Use POST.");
    if (!SUPABASE_URL) throw new Erro(503, "A função está sem SUPABASE_URL.");
    if (ehChaveInterna(req)) throw new Erro(403, "A chave interna do Supabase não chama o corretor de vídeo.");
    const texto = await req.text();
    if (texto.length > MAX_PEDIDO) throw new Erro(413, "Pedido grande demais.");
    let pedido: any = {};
    try { pedido = texto ? JSON.parse(texto) : {}; } catch { throw new Erro(400, "Pedido fora do formato (JSON)."); }
    const bruta = String(pedido?.acao ?? "");
    acao = /^[a-z_]{1,40}$/.test(bruta) ? bruta : "";                // só o nome da ação vai ao registro
    const chaveRobo = (req.headers.get("x-radar-video-robo") ?? "").trim(), chaveAgenda = (req.headers.get("x-radar-agenda") ?? "").trim();
    let sessao = "", papel = "";
    if (chaveRobo || chaveAgenda) {
      quem = chaveRobo ? "robo" : "agenda";
      if (chaveRobo && chaveAgenda) throw new Erro(401, "Chave não confere.");
      await conferirChave(chaveRobo ? "radar_video_conferir_robo" : "radar_video_conferir_agenda", chaveRobo || chaveAgenda);
      if (!(chaveRobo ? ACOES_ROBO : ACOES_AGENDA).includes(acao)) {
        throw new Erro(403, chaveRobo ? "O robô só pega o pedido, pede links e entrega o resultado." : "A agenda só aciona o robô e faz a limpeza.");
      }
    } else {
      ({ sessao, papel } = await sessaoDaTela(req));
      if (!ACOES_TELA.includes(acao)) {
        throw new Erro([...ACOES_ROBO, ...ACOES_AGENDA].includes(acao) ? 403 : 400,
          [...ACOES_ROBO, ...ACOES_AGENDA].includes(acao) ? "Esta ação é só do robô ou da agenda." : "Ação desconhecida.");
      }
    }
    const servico = quem === "tela" ? {} : comoServico();
    const precisaId = ["envio_renovar", "envio_concluido", "previa", ...ACOES_ROBO.filter((a) => a !== "pegar")];
    if (precisaId.includes(acao)) id = uuid(pedido?.id);
    const t = quem === "robo" && acao !== "pegar" ? inteiro(pedido?.tentativa, 1, 200, "a tentativa") : 0;
    let r: any;
    switch (acao) {
      case "envio_iniciar": r = await envioIniciar(sessao, pedido); id = r.id; break;
      case "envio_renovar": r = await envioRenovar(sessao, id); break;
      case "envio_concluido": r = await envioConcluido(sessao, id); break;
      case "previa": r = await previa(sessao, id); break;
      case "baixar": r = await baixar(sessao, inteiro(pedido?.peca, 1, Number.MAX_SAFE_INTEGER, "a peça"), String(pedido?.lido ?? "")); break;
      case "acionar": r = await acionarRobo(); break;
      case "diagnostico":
        if (papel !== "admin") throw new Erro(403, "Só o administrador vê o diagnóstico do corretor de vídeo.");
        r = await diagnostico(sessao); break;
      case "pegar": r = await pegar(servico); id = r.pedido?.id ?? ""; break;
      case "links": r = await links(servico, id, t, pedido?.ler, pedido?.gravar); break;
      case "audio": r = await audio(servico, id, t, pedido?.segundos); break;
      case "parcial": r = await banco(servico, "POST", "rpc/radar_video_parcial", { p_id: id, p_tentativa: t, p_relatorio: pedido?.relatorio ?? null }); break;
      case "concluir": r = await concluir(servico, id, t, pedido); await proximoDaFila(); break;
      case "falhar":
        r = await banco(servico, "POST", "rpc/radar_video_falhar", { p_id: id, p_tentativa: t, p_codigo: String(pedido?.codigo ?? "").slice(0, 40) });
        await proximoDaFila();
        break;
      case "limpar": r = await limpar(servico, inicio); break;
      case "agenda_teste": r = { ok: true, versao: VERSAO }; break;
    }
    registro(acao === "pegar" && !id ? "sem pedido" : r?.situacao ? String(r.situacao) : "ok");
    return responder(200, r ?? { ok: true });
  } catch (e) {
    if (e instanceof Erro) { registro(`recusado (${e.status})`); return responder(e.status, { message: e.message }); }
    console.error(`radar-video: ${acao || "?"} → erro inesperado`, e instanceof Error ? e.name : "");
    return responder(500, { message: "Erro inesperado no corretor de vídeo." });
  }
}

const portaLocal = Deno.env.get("RADAR_PORTA_LOCAL");       // só para rodar/testar fora do Supabase
portaLocal ? Deno.serve({ port: Number(portaLocal), hostname: "127.0.0.1" }, tratar) : Deno.serve(tratar);
