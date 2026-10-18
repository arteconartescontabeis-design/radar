// =====================================================================
// RADAR ARTECON — Edge Function "radar-copia" (v0.32.0)
//
// Cópia de segurança mensal do banco do Radar numa pasta do OneDrive do administrador (Microsoft Graph). Exporta TODAS as
// tabelas do Radar (a lista fixa TABELAS, abaixo: o teste falha se aparecer tabela nova fora dela), uma página de cada vez, pela
// função do banco radar_copias_exportar; monta um .zip (um JSON por tabela, o manifesto.json com as linhas e o sha256 de cada
// arquivo, e um LEIA-ME.txt) e grava em "radar-copia-AAAA-MM-DD-HHMM.zip" na pasta liberada. O Radar nunca apaga cópias antigas.
//
// Quem pode chamar:
//   * a agenda do banco (pg_cron, sql/radar-copia-agenda.sql: dia 1 às 04h10 de Brasília; de novo às 05h10 e no dia 2 às 04h10, só
//     se o mês ainda não tem cópia), com o cabeçalho x-radar-agenda (a chave 'radar_copia_agenda' do Vault);
//   * o administrador, pelos botões "Testar a ligação com o OneDrive" e "Fazer a cópia agora" (Configurações → Cópia de segurança
//     no OneDrive), com o token da sessão.
// A chave interna dos robôs (segredo do GitHub de um repositório público) sozinha NÃO exporta nada: a função do banco confere a
// chave da agenda (Vault) ou o administrador logado.
//
// Ações (corpo {"acao": …}):
//   copiar        → a cópia (agenda ou administrador)
//   testar        → os 8 itens do "Testar a ligação com o OneDrive" (só o administrador)
//   situacao      → configurada ou não e os NOMES dos segredos que faltam (só o administrador)
//   agenda_teste  → {ok, versao}: o teste do fim do sql/radar-copia-agenda.sql (só a agenda; não copia nada)
//
// Privacidade: o repositório é público e o banco tem dados pessoais da equipe. O arquivo da cópia vai da memória da função direto
// para o OneDrive; nunca para log, resposta, armazenamento do Supabase ou GitHub. A resposta à agenda é só {ok, versao} (o pg_net
// guarda as respostas em net._http_response); o registro (radar_copias) guarda só a situação; o log, só contagens. Chave com formato
// conhecido colada no banco (RX_SEGREDO, abaixo) sai "[mascarado]" na cópia (o banco não muda).
//
// Permissão mínima: um registro de aplicativo próprio no Entra ("Radar Artecon — cópias de segurança"), só com a permissão de
// aplicativo Files.SelectedOperations.Selected e a liberação (papel "write") só na pasta das cópias. O "testar" confere que pedir a
// raiz do OneDrive é recusado.
//
// Segredos (Supabase → Edge Functions → Secrets):
//   GRAPH_TENANT_ID        o mesmo da ITC
//   COPIA_CLIENT_ID        o ID do aplicativo (cliente) das cópias
//   COPIA_CLIENT_SECRET    o Valor do segredo do aplicativo das cópias (vence em 12 meses: quadro de vencimentos)
//   COPIA_DRIVE_ID         o drive (b!…) e
//   COPIA_PASTA_ID         a pasta liberada (os dois mostrados pelo bloco do PowerShell do LEIAME; não são segredos)
//   COPIA_MAX_MB           opcional: o limite de dados da cópia, em MB (padrão 100)
// Só nos testes (nunca no Supabase): GRAPH_LOGIN_URL, GRAPH_URL, COPIA_PUT_MAX, COPIA_PEDACO, COPIA_PAGINA, COPIA_COMPACTAR_MS e
// RADAR_PORTA_LOCAL. SUPABASE_URL, a chave pública e a chave interna o Supabase já fornece. "Verify JWT" DESLIGADO (a agenda manda só
// o x-radar-agenda; a função confere quem chama no código, como a radar-itc).
//
// Limites da Edge Function (2 s de CPU por pedido, 256 MB de memória, ~150 s): a tabela das imagens vai sem compactar (o base64 de
// JPEG e PNG quase não diminui e custa CPU), a compactação tem teto de tempo e a cópia recusa, com recado, acima de COPIA_MAX_MB de
// dados. A resposta ao administrador traz os tempos de cada etapa.
// =====================================================================

const VERSAO = "0.34.0";             // v0.34.0: + as 4 tabelas da aba Setor na cópia
const env = (nome: string, padrao = "") => Deno.env.get(nome) ?? padrao;

const SUPABASE_URL = env("SUPABASE_URL").replace(/\/+$/, "");
// a chave pública do projeto, para o apikey dos pedidos feitos com o token de quem chamou (como na radar-itc): a nova
// (sb_publishable_…, em SUPABASE_PUBLISHABLE_KEYS) antes; sem a lista nova, a anon
function chavePublica(): string {
  try {
    const k = JSON.parse(env("SUPABASE_PUBLISHABLE_KEYS") || "{}");
    const v = k?.default ?? Object.values(k ?? {}).find((x) => typeof x === "string" && x);
    if (typeof v === "string" && v.trim()) return v.trim();
  } catch { /* sem a lista nova: fica a anon */ }
  return env("SUPABASE_ANON_KEY").trim();
}
const ANON = chavePublica();
const LOGIN_URL = env("GRAPH_LOGIN_URL", "https://login.microsoftonline.com").replace(/\/+$/, "");
const GRAPH_URL = env("GRAPH_URL", "https://graph.microsoft.com/v1.0").replace(/\/+$/, "");

// Todas as tabelas do Radar, em ordem alfabética. Tabela nova no banco fora desta lista e de FORA: o teste
// test_tabelas_da_copia_sao_todas_as_do_banco falha (é preciso decidir se ela vai à cópia).
const TABELAS = [
  "radar_assunto_capturas", "radar_assuntos", "radar_auditoria", "radar_capturas", "radar_capturas_versoes", "radar_categorias",
  "radar_config", "radar_conteudos", "radar_copias", "radar_divulgacoes", "radar_evidencias", "radar_execucoes", "radar_fontes",
  "radar_ia_uso", "radar_imagens", "radar_informativo_itens", "radar_informativos", "radar_instalacoes", "radar_itc_lidos",
  "radar_lembretes", "radar_normas", "radar_pauta_pecas", "radar_perfis", "radar_pessoas", "radar_redes_envios",
  // v0.34.0: as 4 da aba Setor (dados públicos do Instagram e a configuração dos setores: vão à cópia como tudo)
  "radar_setor_coletas", "radar_setor_contas", "radar_setor_posts", "radar_setor_setores", "radar_site_envios",
  "radar_site_exclusoes", "radar_vencimentos", "radar_video_acessos", "radar_videos",
] as const;
// Tabela que não vai à cópia DE PROPÓSITO, com o motivo (hoje nenhuma: nenhuma coluna guarda chave ou senha — revisão coluna a
// coluna na v0.32.0). Tabela nova fora das duas listas: o teste test_tabelas_da_copia_sao_todas_as_do_banco falha.
const FORA: Record<string, string> = {};
// linhas por página (o PostgREST do Supabase devolve até 1000: as linhas e o marcador da página, em radar_copias_exportar): menos nas
// tabelas de linhas grandes (imagens em base64, textos)
const PAGINA: Record<string, number> = {
  radar_imagens: 20, radar_redes_envios: 10, radar_capturas: 500, radar_capturas_versoes: 500, radar_auditoria: 500,
  radar_conteudos: 200, radar_divulgacoes: 200, radar_pauta_pecas: 200, radar_videos: 200,
};
const PAGINA_PADRAO = 999;
// o base64 de JPEG e PNG: compactar custa ~57 ms de CPU por MB para ganhar ~25%
const SEM_COMPACTAR = new Set<string>(["radar_imagens"]);
const MIB = 1024 * 1024;
const inteiroDe = (nome: string, padrao: number, min: number, max: number) => {
  const v = Number(env(nome).trim() || NaN);
  return Number.isInteger(v) && v >= min && v <= max ? v : padrao;
};
const PAGINA_TETO = inteiroDe("COPIA_PAGINA", PAGINA_PADRAO, 1, PAGINA_PADRAO);          // só nos testes: páginas pequenas
const PUT_MAX = inteiroDe("COPIA_PUT_MAX", 4 * MIB, 0, 4 * MIB);                          // até 4 MiB: um PUT só
// os pedaços da sessão de envio: múltiplos de 320 KiB (327 680 bytes), como a Microsoft pede
const PEDACO = (() => {
  const v = inteiroDe("COPIA_PEDACO", 0, 327_680, 60 * MIB);
  return v && v % 327_680 === 0 ? v : 10 * 327_680;
})();
const COMPACTAR_MS = inteiroDe("COPIA_COMPACTAR_MS", 700, 0, 5000);                      // teto do tempo gasto compactando
const COMPACTAR_TABELA_MAX = 25 * MIB;
const MAX_MB = (() => { const v = Number(env("COPIA_MAX_MB").trim() || NaN); return Number.isFinite(v) && v > 0 ? v : 100; })();
// o Supabase encerra a chamada perto de 150 s (o pg_net espera 150 s): cada tabela e cada pedaço só começa se der tempo
const LIMITE_MS = 140_000;
// v0.32.0 (revisão): a cópia do administrador fala com o banco o tempo todo com o token da sessão dele. Token que vence no meio
// deixava a cópia "em andamento" (o fim também era recusado) e a tela, que renova a sessão e repete, recebia "já há uma cópia em
// andamento". Por isso a cópia só começa com o token valendo pelo menos isto: o pior caso (LIMITE_MS, o último pedido, até 60 s, e o
// fim, até 30 s). Menos que isso: 401 antes de começar (nada é registrado); a tela renova a sessão e pede de novo sozinha.
const SESSAO_MIN_MS = 240_000;
const ROLE = "Files.SelectedOperations.Selected";
// Chave com formato conhecido, no texto do JSON de cada tabela: sai "[mascarado]" na cópia (o banco não muda). São os mesmos
// formatos que o quadro de vencimentos recusa (radar_vencimento_parece_segredo; v0.32.0, revisão: antes a cópia deixava passar o
// token da Meta, a chave privada, o sb_secret_ curto e o github_pat_ ou iagw_ curto): Supabase, GitHub, IA Central, Meta, segredo de
// aplicativo do Azure, JWT e chave privada (o bloco inteiro, até o END ou até o fim do texto). Nenhum aparece no base64 de uma
// imagem: os outros têm "_", "~", "." ou "-", que o base64 não tem, e o da Meta só vale entre caracteres que não são de base64. O
// "pedaço de 40+ caracteres sem espaço" do quadro NÃO vale aqui: no JSON ele pegaria o base64, os sha256 e as próprias linhas.
const RX_SEGREDO = new RegExp([
  "sb_(?:secret|publishable)_[A-Za-z0-9_-]*", "gh[pousr]_[A-Za-z0-9]{20,}", "github_pat_[A-Za-z0-9_]*", "iagw_[A-Za-z0-9_-]*",
  "(?<![A-Za-z0-9+/])EAA[A-Za-z0-9]{30,}(?![A-Za-z0-9+/=])", "[A-Za-z0-9_-]{0,3}[0-9]Q~[A-Za-z0-9_.~-]{20,}",
  "eyJ[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}(?:\\.[A-Za-z0-9_-]*)?",
  // a chave privada, dentro de um texto do JSON: a barra invertida escapa o caractere seguinte; a aspa sem escape fecha o texto
  '-----BEGIN [A-Z0-9 ]{1,40}-----(?:[^"\\\\]|\\\\.)*?(?:-----END [A-Z0-9 ]{1,40}-----|(?="))',
].join("|"), "g");

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

/** "tipo" é o que a agenda recebe quando a cópia falha (nunca a mensagem): login, permissao, pasta, envio, tamanho, tempo, banco. */
class Erro extends Error {
  status: number;
  tipo: string;
  constructor(status: number, mensagem: string, tipo = "banco") { super(mensagem); this.status = status; this.tipo = tipo; }
}
const responder = (status: number, corpo: unknown) =>
  new Response(JSON.stringify(corpo), { status, headers: { ...CORS, "Content-Type": "application/json" } });
const espera = (ms: number) => new Promise((r) => setTimeout(r, ms));
// bytes num ArrayBuffer comum (o tipo do TextEncoder: vale nas versões do TypeScript de antes e de depois do Uint8Array<…>)
type Bytes = ReturnType<TextEncoder["encode"]>;

// ------------------------------------------------------------------ banco
/** A mensagem de um erro do banco: o texto depois do "RADAR…:" (o código RADAR364 vira 409). */
function erroDoBanco(status: number, dados: any): Erro {
  const m = String(dados?.message ?? "");
  const radar = /RADAR(\d+):\s*(.*)/s.exec(m);
  if (radar) return new Erro(radar[1] === "364" ? 409 : status === 401 ? 401 : status === 403 ? 403 : 400, radar[2]);
  return new Erro(status === 401 ? 401 : status === 403 ? 403 : 400, (m || `Erro ${status} no banco`).slice(0, 300));
}

/** "quem" é a sessão do usuário ("Bearer …", com a chave pública) ou os cabeçalhos da chave interna (comoServico). */
function cabecalhos(quem: string | Record<string, string>): Record<string, string> {
  return typeof quem === "string" ? { apikey: ANON || quem, Authorization: quem } : quem;
}
async function banco(quem: string | Record<string, string>, metodo: string, caminho: string, corpo?: unknown): Promise<any> {
  const r = await fetch(`${SUPABASE_URL}/rest/v1/${caminho}`, {
    method: metodo,
    headers: { ...cabecalhos(quem), "Content-Type": "application/json" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
    signal: AbortSignal.timeout(30_000),
  });
  const texto = await r.text();
  let dados: any = null;
  try { dados = texto ? JSON.parse(texto) : null; } catch { dados = { message: texto }; }
  if (!r.ok) throw erroDoBanco(r.status, dados);
  return dados;
}
// a chave interna do Supabase: a nova (sb_secret_…) só vale no apikey; a antiga (JWT service_role) vai nos dois cabeçalhos
function chaveInterna(): string {
  try {
    const k = JSON.parse(env("SUPABASE_SECRET_KEYS") || "{}");
    const v = k?.default ?? Object.values(k ?? {}).find((x) => typeof x === "string" && x);
    if (typeof v === "string" && v.trim()) return v.trim();
  } catch { /* sem a lista nova: fica a antiga */ }
  return env("SUPABASE_SERVICE_ROLE_KEY").trim();
}
const ehJwt = (k: string) => /^[\w-]+\.[\w-]+\.[\w-]+$/.test(k);
/** Cabeçalhos para falar com o banco como a própria função. */
const comoServico = (): Record<string, string> => {
  const k = chaveInterna();
  if (!k) throw new Erro(503, "A função está sem a chave interna do Supabase (SUPABASE_SECRET_KEYS ou SUPABASE_SERVICE_ROLE_KEY).");
  return ehJwt(k) ? { apikey: k, Authorization: "Bearer " + k } : { apikey: k };
};

/** Quem chamou: a agenda (chave do Vault, conferida pelo banco) ou o administrador logado. "chave" vai em p_chave nas funções da
 *  cópia; "cab" é com quem a função fala com o banco (a chave interna, para a agenda; o token, para o administrador). */
type Quem = { quem: "agenda" | "admin"; chave: string; cab: string | Record<string, string> };
async function autorizar(req: Request): Promise<Quem> {
  const chave = req.headers.get("x-radar-agenda") ?? "";
  if (chave) {
    const servico = comoServico();
    const ok = await banco(servico, "POST", "rpc/radar_copia_conferir_agenda", { p_chave: chave });
    if (ok === true) return { quem: "agenda", chave, cab: servico };
    throw new Erro(401, "Chave da agenda não confere.");
  }
  const token = req.headers.get("Authorization") ?? "";
  if (!/^Bearer\s+\S+/.test(token)) throw new Erro(401, "Sessão não informada.");
  const papel = await banco(token, "POST", "rpc/radar_papel", {});
  if (papel !== "admin") throw new Erro(403, "Só o administrador mexe na cópia de segurança.");
  return { quem: "admin", chave: "", cab: token };
}

// ------------------------------------------------------------------ configuração e login na Microsoft
const SEGREDOS = ["GRAPH_TENANT_ID", "COPIA_CLIENT_ID", "COPIA_CLIENT_SECRET", "COPIA_DRIVE_ID", "COPIA_PASTA_ID"];
const FORMATOS: Record<string, RegExp> = {
  GRAPH_TENANT_ID: /^[\w.-]{3,100}$/,
  COPIA_CLIENT_ID: /^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$/,
  COPIA_DRIVE_ID: /^b![A-Za-z0-9_-]{20,200}$/,
  COPIA_PASTA_ID: /^[A-Za-z0-9!_-]{10,100}$/,
};
function configCopia() {
  const v = Object.fromEntries(SEGREDOS.map((n) => [n, env(n).trim()]));
  const faltam = SEGREDOS.filter((n) => !v[n]);
  const invalidos = Object.entries(FORMATOS).filter(([n, rx]) => v[n] && !rx.test(v[n])).map(([n]) => n);
  return { faltam, invalidos, configurada: !faltam.length && !invalidos.length, tenant: v.GRAPH_TENANT_ID, cliente: v.COPIA_CLIENT_ID,
           segredo: v.COPIA_CLIENT_SECRET, drive: v.COPIA_DRIVE_ID, pasta: v.COPIA_PASTA_ID };
}
type Config = ReturnType<typeof configCopia>;
const RECADO_CONFIG = "Passo a passo: Configurações → Cópia de segurança no OneDrive.";
function faltaConfig(c: Config): string {
  return "Cópia não configurada: " + [c.faltam.length ? "faltam " + c.faltam.join(", ") : "",
    c.invalidos.length ? "com formato inválido " + c.invalidos.join(", ") : ""].filter(Boolean).join("; ") +
    " (Supabase → Edge Functions → Secrets). " + RECADO_CONFIG;
}

async function tokenGraph(c: Config): Promise<string> {
  let r: Response;
  try {
    r = await fetch(`${LOGIN_URL}/${encodeURIComponent(c.tenant)}/oauth2/v2.0/token`, {
      method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ client_id: c.cliente, client_secret: c.segredo, grant_type: "client_credentials",
                                  scope: "https://graph.microsoft.com/.default" }),
      signal: AbortSignal.timeout(20_000),
    });
  } catch { throw new Erro(504, "Não foi possível falar com o login da Microsoft agora. Tente de novo.", "login"); }
  const d: any = await r.json().catch(() => ({}));
  if (!r.ok || !d.access_token) {
    const cod = String(d.error ?? r.status);
    // a descrição da Microsoft não traz o segredo; mesmo assim, só o código e o começo vão para a tela
    throw new Erro(503, `A Microsoft recusou o login do aplicativo das cópias (${cod}). Confira COPIA_CLIENT_ID e COPIA_CLIENT_SECRET ` +
      "(o segredo vence em 12 meses; copie a coluna Valor, não o ID do segredo). " +
      String(d.error_description ?? "").split("\n")[0].slice(0, 160), "login");
  }
  return d.access_token;
}

/** O meio de um JWT (base64url), lido sem conferir a assinatura (quem confere é a Microsoft ou o banco); null se não der. */
function cargaDoJwt(t: string): any {
  try {
    const meio = t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(meio + "=".repeat((4 - meio.length % 4) % 4)), (x) => x.charCodeAt(0))));
  } catch { return null; }
}
/** As permissões de aplicativo do token. Só o "testar" usa. */
function rolesDoToken(t: string): string[] {
  const carga = cargaDoJwt(t);
  return Array.isArray(carga?.roles) ? carga.roles.map(String) : [];
}

// ------------------------------------------------------------------ Microsoft Graph
/** O erro do Graph em português (com o código da Microsoft, nunca o conteúdo). */
function erroGraph(status: number, codigo: string): Erro {
  if (status === 401 || status === 403) {
    return new Erro(502, `O OneDrive recusou o acesso (${status} ${codigo}): confira a liberação da pasta (Parte 2 do passo a passo) e o ` +
      "consentimento do administrador no Entra.", "permissao");
  }
  if (status === 404) return new Erro(502, "Pasta não encontrada (404): confira COPIA_DRIVE_ID e COPIA_PASTA_ID.", "pasta");
  if (status === 409) return new Erro(409, "Já existe no OneDrive um arquivo com este nome: espere um minuto e faça de novo.", "envio");
  return new Erro(502, `O OneDrive não aceitou (HTTP ${status}, ${codigo}).`, "envio");
}
const codigoDe = (d: any, status: number) => String(d?.error?.code ?? status).replace(/[^\w.-]/g, "").slice(0, 60);

/** Um pedido ao Graph (o endereço inteiro, sempre no GRAPH_URL) com o token do aplicativo. 5xx e 429: até 3 vezes de novo (1, 2 e
 *  4 s; o Retry-After até 10 s), sem passar do tempo. Devolve o status, o corpo (não lança por status) e quantas vezes repetiu. */
async function graphPedir(token: string, inicio: number, metodo: string, url: string, corpo?: BodyInit, tipo?: string):
    Promise<{ status: number; dados: any; repetiu: number }> {
  if (!url.startsWith(GRAPH_URL + "/")) throw new Erro(500, "Endereço do Graph inesperado.", "envio");
  for (let tentativa = 0; ; tentativa++) {
    let r: Response | null = null;
    try {
      r = await fetch(url, { method: metodo, headers: { Authorization: "Bearer " + token, ...(tipo ? { "Content-Type": tipo } : {}) },
                             body: corpo, signal: AbortSignal.timeout(30_000) });
    } catch { r = null; }
    if (r && r.status !== 429 && r.status < 500) {
      const texto = await r.text();
      let dados: any = null;
      try { dados = texto ? JSON.parse(texto) : null; } catch { dados = null; }
      return { status: r.status, dados, repetiu: tentativa };
    }
    const depois = Math.min(Number(r?.headers.get("Retry-After")) || 0, 10);
    await r?.body?.cancel().catch(() => {});
    const ms = depois ? depois * 1000 : 1000 * 2 ** tentativa;
    if (tentativa >= 3 || Date.now() - inicio + ms > LIMITE_MS) {
      throw r ? erroGraph(r.status, String(r.status)) : new Erro(504, "O OneDrive (Microsoft Graph) não respondeu a tempo.", "envio");
    }
    await espera(ms);
  }
}
async function graph(token: string, inicio: number, metodo: string, url: string, corpo?: BodyInit, tipo?: string): Promise<any> {
  const r = await graphPedir(token, inicio, metodo, url, corpo, tipo);
  if (r.status < 200 || r.status > 299) throw erroGraph(r.status, codigoDe(r.dados, r.status));
  return r.dados;
}

/** v0.32.0 (revisão): o arquivo já está na pasta, com o tamanho enviado? É o caso em que o OneDrive gravou e só a resposta se perdeu
 *  (5xx, 429 ou queda): a repetição (com conflictBehavior "fail") esbarra no próprio arquivo e a cópia virava falha, com o .zip
 *  inteiro na pasta. Só depois de uma repetição; devolve o item ou null. */
async function jaGravado(token: string, inicio: number, base: string, total: number): Promise<any> {
  const r = await graphPedir(token, inicio, "GET", `${base.replace(/:$/, "")}?$select=id,name,size`).catch(() => null);
  return r && r.status === 200 && Number(r.dados?.size) === total ? r.dados : null;
}

/** O endereço da sessão de envio é do OneDrive (https, *.sharepoint.com)? Ele recebe o arquivo SEM o token: endereço de fora nunca
 *  recebe nada. Só nos testes (RADAR_PORTA_LOCAL): também o http://127.0.0.1 do Graph de mentira. */
function uploadUrlConfere(u: string): boolean {
  let url: URL;
  try { url = new URL(u); } catch { return false; }
  if (url.protocol === "https:" && url.hostname.endsWith(".sharepoint.com") && !url.username && !url.password) return true;
  return Boolean(Deno.env.get("RADAR_PORTA_LOCAL")) && url.protocol === "http:" && url.hostname === "127.0.0.1";
}
async function sessaoDeEnvio(token: string, inicio: number, base: string, comportamento: "fail" | "replace"): Promise<string> {
  const d = await graph(token, inicio, "POST", `${base}/createUploadSession`,
                        JSON.stringify({ item: { "@microsoft.graph.conflictBehavior": comportamento } }), "application/json");
  const u = String(d?.uploadUrl ?? "");
  if (!uploadUrlConfere(u)) throw new Erro(502, "Endereço de envio inesperado (não é do OneDrive): nada foi enviado.", "envio");
  return u;
}

/** O pedaço [de, ate) do arquivo, lido da lista de partes (sem juntar o arquivo inteiro numa memória só). */
function fatia(partes: Bytes[], de: number, ate: number): Bytes {
  const r = new Uint8Array(ate - de);
  let pos = 0, escrito = 0;
  for (const p of partes) {
    const fim = pos + p.length;
    if (fim > de && pos < ate) {
      const a = Math.max(de, pos) - pos, b = Math.min(ate, fim) - pos;
      r.set(p.subarray(a, b), escrito);
      escrito += b - a;
    }
    pos = fim;
    if (pos >= ate) break;
  }
  return r;
}
const proximoByte = (d: any): number | null => {
  const m = /^(\d+)-/.exec(String(d?.nextExpectedRanges?.[0] ?? ""));
  return m ? Number(m[1]) : null;
};

/** Envio em pedaços pela sessão de envio (sem o Authorization). 202: o próximo pedaço; 5xx e 429: o mesmo pedaço de novo (até 3
 *  vezes); 416: pergunta à sessão de onde seguir; 404 (sessão vencida): uma sessão nova, do começo. Na falha, cancela a sessão. */
async function enviarEmPedacos(token: string, inicio: number, base: string, comportamento: "fail" | "replace", partes: Bytes[],
                               total: number, tamanhoPedaco: number): Promise<any> {
  let url = await sessaoDeEnvio(token, inicio, base, comportamento);
  let pos = 0, tentativas = 0, renovada = false, ultimoIncerto = false;
  try {
    for (;;) {
      if (Date.now() - inicio > LIMITE_MS) throw new Erro(504, "A cópia passou do tempo da função durante o envio.", "tempo");
      const fim = Math.min(pos + tamanhoPedaco, total);
      let r: Response | null = null;
      try {
        r = await fetch(url, { method: "PUT", headers: { "Content-Range": `bytes ${pos}-${fim - 1}/${total}` },
                               body: fatia(partes, pos, fim), signal: AbortSignal.timeout(60_000) });
      } catch { r = null; }
      const d: any = r ? await r.json().catch(() => null) : null;
      if (r && (r.status === 200 || r.status === 201)) return d;
      if (r && r.status === 202) { pos = proximoByte(d) ?? fim; tentativas = 0; continue; }
      if (!r || r.status >= 500 || r.status === 429) {
        if (++tentativas > 3) throw r ? erroGraph(r.status, codigoDe(d, r.status)) : new Erro(504, "O OneDrive não respondeu a tempo.", "envio");
        if (fim === total) ultimoIncerto = true;            // o último pedaço: o OneDrive pode ter fechado o arquivo sem responder
        await espera(1000 * 2 ** (tentativas - 1));
        continue;
      }
      if (ultimoIncerto) {                                  // a repetição do último pedaço recusada: o arquivo já pode estar lá
        const item = await jaGravado(token, inicio, base, total);
        if (item) return item;
      }
      if (r.status === 416) {
        const s = await fetch(url, { signal: AbortSignal.timeout(30_000) }).then((x) => x.json()).catch(() => null);
        const p = proximoByte(s);
        if (p === null) throw erroGraph(416, "range");
        pos = p;
        continue;
      }
      if (r.status === 404 && !renovada) {                  // a sessão venceu: uma nova, do começo
        renovada = true;
        url = await sessaoDeEnvio(token, inicio, base, comportamento);
        pos = 0;
        continue;
      }
      throw erroGraph(r.status, codigoDe(d, r.status));
    }
  } catch (e) {
    await fetch(url, { method: "DELETE", signal: AbortSignal.timeout(10_000) }).then((x) => x.body?.cancel()).catch(() => {});
    throw e;
  }
}

/** Grava o arquivo na pasta: até PUT_MAX, um PUT só; acima, a sessão de envio. Confere o tamanho que o OneDrive guardou. */
async function enviar(token: string, inicio: number, c: Config, nome: string, partes: Bytes[], total: number,
                      comportamento: "fail" | "replace" = "fail", tamanhoPedaco = PEDACO): Promise<any> {
  const base = `${GRAPH_URL}/drives/${encodeURIComponent(c.drive)}/items/${encodeURIComponent(c.pasta)}:/${encodeURIComponent(nome)}:`;
  let item: any;
  if (total <= PUT_MAX) {
    const r = await graphPedir(token, inicio, "PUT", `${base}/content?@microsoft.graph.conflictBehavior=${comportamento}`, fatia(partes, 0, total),
                               nome.endsWith(".zip") ? "application/zip" : nome.endsWith(".txt") ? "text/plain; charset=utf-8" : "application/octet-stream");
    // 409 depois de repetir: o primeiro PUT pode ter gravado (a resposta se perdeu); vale se o arquivo da pasta tem o tamanho enviado
    if (r.status === 409 && r.repetiu > 0) item = await jaGravado(token, inicio, base, total);
    if (!item) {
      if (r.status < 200 || r.status > 299) throw erroGraph(r.status, codigoDe(r.dados, r.status));
      item = r.dados;
    }
  } else {
    item = await enviarEmPedacos(token, inicio, base, comportamento, partes, total, tamanhoPedaco);
  }
  if (Number(item?.size) !== total || item?.name !== nome) {
    if (item?.id) {
      await graphPedir(token, inicio, "DELETE", `${GRAPH_URL}/drives/${encodeURIComponent(c.drive)}/items/${encodeURIComponent(String(item.id))}`)
        .catch(() => {});
    }
    throw new Erro(502, "O arquivo no OneDrive ficou com tamanho diferente do enviado: ele foi apagado e a cópia não vale.", "envio");
  }
  return item;
}

// ------------------------------------------------------------------ .zip sem biblioteca
// O gzip nativo (CompressionStream) já traz o que a entrada do zip precisa: o fluxo deflate cru (o miolo), o CRC32 e o tamanho (o
// rodapé). O que vai sem compactar (método 0) leva o CRC32 calculado aqui (tabela "slice-by-8").
const CRC_T = (() => {
  const t = new Uint32Array(256 * 8);
  for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
  for (let n = 0; n < 256; n++) for (let k = 1; k < 8; k++) t[k * 256 + n] = (t[(k - 1) * 256 + n] >>> 8) ^ t[t[(k - 1) * 256 + n] & 255];
  return t;
})();
function crc32(d: Uint8Array): number {
  const T = CRC_T;
  let c = 0xFFFFFFFF, i = 0;
  const n = d.length - (d.length % 8);
  for (; i < n; i += 8) {
    const a = (c ^ (d[i] | (d[i + 1] << 8) | (d[i + 2] << 16) | (d[i + 3] << 24))) >>> 0;
    c = T[1792 + (a & 255)] ^ T[1536 + ((a >>> 8) & 255)] ^ T[1280 + ((a >>> 16) & 255)] ^ T[1024 + (a >>> 24)] ^
        T[768 + d[i + 4]] ^ T[512 + d[i + 5]] ^ T[256 + d[i + 6]] ^ T[d[i + 7]];
  }
  for (; i < d.length; i++) c = T[(c ^ d[i]) & 255] ^ (c >>> 8);
  return (~c) >>> 0;
}
async function gzip(dados: Bytes): Promise<Bytes> {
  const s = new Blob([dados]).stream().pipeThrough(new CompressionStream("gzip"));
  return new Uint8Array(await new Response(s).arrayBuffer());
}
/** O deflate cru e o CRC32 de dentro do gzip (RFC 1952: cabeçalho de 10 bytes, os opcionais conforme FLG, o rodapé de 8). */
function deGzip(g: Bytes, tamanho: number): { deflate: Bytes; crc: number } {
  if (g.length < 18 || g[0] !== 0x1f || g[1] !== 0x8b || g[2] !== 8) throw new Erro(500, "Compactação inesperada.");
  const flg = g[3];
  let i = 10;
  if (flg & 4) i += 2 + (g[i] | (g[i + 1] << 8));
  if (flg & 8) { while (i < g.length && g[i++] !== 0); }
  if (flg & 16) { while (i < g.length && g[i++] !== 0); }
  if (flg & 2) i += 2;
  const fim = g.length - 8, dv = new DataView(g.buffer, g.byteOffset, g.byteLength);
  if (i > fim || dv.getUint32(fim + 4, true) !== tamanho % 2 ** 32) throw new Erro(500, "Compactação inesperada.");
  return { deflate: g.subarray(i, fim), crc: dv.getUint32(fim, true) };
}

type Entrada = { nome: string; metodo: 0 | 8; crc: number; tamanho: number; dados: Bytes };
/** Data e hora do DOS (as do horário de Brasília da cópia, "AAAA-MM-DDTHH:MM:SS"). */
function dos(iso: string): { data: number; hora: number } {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(iso);
  if (!m) return { data: 0x21, hora: 0 };
  const [a, me, di, h, mi, s] = m.slice(1).map(Number);
  return { data: ((a - 1980) << 9) | (me << 5) | di, hora: (h << 11) | (mi << 5) | (s >> 1) };
}
/** O .zip como lista de partes (cabeçalho local + dados de cada entrada, o diretório central e o fim), mais o total. Nomes em
 *  UTF-8 (bit 11). Sem ZIP64: recusa acima de 4 GiB ou 65 535 entradas. */
function montarZip(entradas: Entrada[], quando: string): { partes: Bytes[]; total: number } {
  const enc = new TextEncoder(), t = dos(quando), partes: Bytes[] = [], central: Bytes[] = [];
  let pos = 0;
  if (entradas.length > 65_000) throw new Erro(500, "Entradas demais para o .zip.", "tamanho");
  for (const e of entradas) {
    const nome = enc.encode(e.nome);
    const h = new Uint8Array(30 + nome.length), v = new DataView(h.buffer);
    v.setUint32(0, 0x04034b50, true); v.setUint16(4, 20, true); v.setUint16(6, 0x0800, true); v.setUint16(8, e.metodo, true);
    v.setUint16(10, t.hora, true); v.setUint16(12, t.data, true); v.setUint32(14, e.crc, true); v.setUint32(18, e.dados.length, true);
    v.setUint32(22, e.tamanho, true); v.setUint16(26, nome.length, true); v.setUint16(28, 0, true); h.set(nome, 30);
    const c = new Uint8Array(46 + nome.length), w = new DataView(c.buffer);
    w.setUint32(0, 0x02014b50, true); w.setUint16(4, 20, true); w.setUint16(6, 20, true); w.setUint16(8, 0x0800, true);
    w.setUint16(10, e.metodo, true); w.setUint16(12, t.hora, true); w.setUint16(14, t.data, true); w.setUint32(16, e.crc, true);
    w.setUint32(20, e.dados.length, true); w.setUint32(24, e.tamanho, true); w.setUint16(28, nome.length, true);
    w.setUint32(42, pos, true); c.set(nome, 46);
    partes.push(h, e.dados);
    central.push(c);
    pos += h.length + e.dados.length;
    if (pos > 0xFFFF_0000) throw new Erro(500, "A cópia passou de 4 GiB.", "tamanho");
  }
  const tamC = central.reduce((s, x) => s + x.length, 0), fim = new Uint8Array(22), f = new DataView(fim.buffer);
  f.setUint32(0, 0x06054b50, true); f.setUint16(8, entradas.length, true); f.setUint16(10, entradas.length, true);
  f.setUint32(12, tamC, true); f.setUint32(16, pos, true);
  partes.push(...central, fim);
  return { partes, total: pos + tamC + 22 };
}

const hex = (b: ArrayBuffer) => Array.from(new Uint8Array(b), (x) => x.toString(16).padStart(2, "0")).join("");
const sha256 = async (d: Bytes) => hex(await crypto.subtle.digest("SHA-256", d));

// ------------------------------------------------------------------ exportação
const ABRE = 0x5b, FECHA = 0x5d, VIRGULA = 0x2c, ASPAS = 0x22;
/** Quantos elementos vieram, pelo Content-Range do PostgREST ("0-9/*" = 10; "*\/*" = nenhum). null: sem o cabeçalho. */
function linhasDaFaixa(cr: string | null): number | null {
  if (!cr) return null;
  const m = /^(\d+)-(\d+)\//.exec(cr.trim());
  if (m) return Number(m[2]) - Number(m[1]) + 1;
  return /^\*\//.test(cr.trim()) ? 0 : null;
}
const ehHex = (b: number) => (b >= 0x30 && b <= 0x39) || (b >= 0x61 && b <= 0x66);
const ehSeparador = (b: number) => b === VIRGULA || b === 0x20 || b === 0x0a || b === 0x0d || b === 0x09;
/** O marcador do fim da página (radar_copias_exportar): o último elemento, um texto JSON só com hexadecimal (a chave primária da
 *  última linha). Devolve o marcador e onde terminam as linhas (logo depois do "}" da última); null se o último elemento não é o
 *  marcador (a página foi cortada). Lê só o fim do corpo: hexadecimal não tem aspas, e o JSON das linhas não precisa ser lido. */
function marcadorDaPagina(corpo: Bytes): { depois: string; fimLinhas: number } | null {
  let i = corpo.length - 1;
  if (corpo[i] !== FECHA) return null;
  do i--; while (i > 0 && ehSeparador(corpo[i]));
  if (corpo[i] !== ASPAS) return null;
  const fimHex = i;
  do i--; while (i > 0 && ehHex(corpo[i]));
  if (corpo[i] !== ASPAS || fimHex - i < 3) return null;
  const depois = new TextDecoder().decode(corpo.subarray(i + 1, fimHex));
  do i--; while (i > 0 && ehSeparador(corpo[i]));
  return corpo[i] === 0x7d ? { depois, fimLinhas: i + 1 } : null;      // "}": o fim da última linha
}
/** Uma tabela inteira como um JSON só ("[…]"), página por página, na ordem da chave primária (radar_copias_exportar, no banco, que
 *  confere a chave da agenda ou o administrador). Cada página começa depois da chave da última linha da anterior (o marcador): uma
 *  linha apagada no meio da cópia não faz outra pular a fronteira (v0.32.0, revisão). O corpo de cada página é juntado em bytes,
 *  sem ler o JSON. */
async function exportarTabela(q: Quem, t: string, inicio: number): Promise<{ json: Bytes; linhas: number }> {
  const tamanho = Math.min(PAGINA[t] ?? PAGINA_PADRAO, PAGINA_TETO);
  const pedacos: Bytes[] = [];
  let linhas = 0, depois = "";
  for (;;) {
    if (Date.now() - inicio > LIMITE_MS) throw new Erro(504, "A cópia passou do tempo da função ao ler o banco.", "tempo");
    const r = await fetch(`${SUPABASE_URL}/rest/v1/rpc/radar_copias_exportar`, {
      method: "POST",
      headers: { ...cabecalhos(q.cab), "Content-Type": "application/json", "Accept-Encoding": "identity" },
      body: JSON.stringify({ p_chave: q.chave, p_tabela: t, p_depois: depois, p_tamanho: tamanho }),
      signal: AbortSignal.timeout(60_000),
    });
    const corpo = new Uint8Array(await r.arrayBuffer());
    if (!r.ok) {
      let dados: any = null;
      try { dados = JSON.parse(new TextDecoder().decode(corpo)); } catch { dados = null; }
      throw erroDoBanco(r.status, dados);
    }
    if (corpo[0] !== ABRE || corpo[corpo.length - 1] !== FECHA) throw new Erro(502, `Resposta inesperada do banco na tabela ${t}.`);
    let n = linhasDaFaixa(r.headers.get("Content-Range"));
    if (n === null) n = (JSON.parse(new TextDecoder().decode(corpo)) as unknown[]).length;      // reserva: sem o Content-Range
    if (n === 0) break;                                                                       // "[]": a tabela acabou
    const m = marcadorDaPagina(corpo);
    // sem o marcador no fim (a página veio cortada) ou sem avançar: a cópia não vale (nunca uma tabela pela metade)
    if (!m || m.depois === depois || n - 1 > tamanho) throw new Erro(502, `Resposta inesperada do banco na tabela ${t}.`);
    n -= 1;                                                                                   // o marcador não é linha
    pedacos.push(corpo.subarray(1, m.fimLinhas));
    linhas += n;
    if (n < tamanho) break;
    depois = m.depois;
  }
  const total = 2 + pedacos.reduce((s, x) => s + x.length, 0) + Math.max(pedacos.length - 1, 0);
  const json = new Uint8Array(total);
  let pos = 0;
  json[pos++] = ABRE;
  pedacos.forEach((x, i) => { if (i) json[pos++] = VIRGULA; json.set(x, pos); pos += x.length; });
  json[pos] = FECHA;
  return { json, linhas };
}

const LEIA_ME = (gerado: string, arquivo: string) => [
  "Cópia de segurança do Radar Artecon",
  "===================================",
  "",
  `Arquivo: ${arquivo}`,
  `Feita em: ${gerado.slice(8, 10)}/${gerado.slice(5, 7)}/${gerado.slice(0, 4)} às ${gerado.slice(11, 16)} (horário de Brasília).`,
  "",
  "É a cópia do banco do Radar: todas as tabelas, cada uma num arquivo .json dentro da pasta \"tabelas\".",
  "",
  "Como abrir: clique duas vezes no .zip. Os arquivos .json abrem no Bloco de Notas ou no navegador.",
  "O manifesto.json diz quantas linhas tem cada tabela e o sha256 de cada arquivo (serve para conferir que nada mudou).",
  "",
  "Não entram: os arquivos do armazenamento (vídeos e lâminas da Pauta), os logins e as senhas (Supabase Auth) e os segredos",
  "(Vault e Edge Functions). Chave com formato conhecido (Supabase, GitHub, IA Central, Meta, segredo de aplicativo do Azure, JWT,",
  "chave privada) que estivesse colada num texto do banco aparece como [mascarado].",
  "",
  "Guarde: o Radar não apaga cópias antigas. A cópia tem dados pessoais da equipe (nomes, termos, fotos): não compartilhe.",
  "",
].join("\r\n");

type Resultado = { arquivo: string; bytes: number; bytes_brutos: number; linhas: number; tabelas: number; sha256: string;
                   mascarados: Record<string, number>; tempos: Record<string, number> };

async function copiar(q: Quem, c: Config, inicio: number): Promise<Resultado> {
  const comeco = await banco(q.cab, "POST", "rpc/radar_copias_comecar", { p_chave: q.chave });
  const id = Number(comeco?.id), arquivo = String(comeco?.arquivo ?? ""), gerado = String(comeco?.gerado_em ?? "");
  let brutos = 0, linhas = 0, tabelas = 0;
  const terminar = (ok: boolean, extra: Record<string, unknown>) =>
    banco(q.cab, "POST", "rpc/radar_copias_terminar", { p_chave: q.chave, p_id: id, p_ok: ok, p_bytes: null, p_bytes_brutos: brutos,
      p_linhas: linhas, p_tabelas: tabelas, p_sha256: null, p_erro: null, ...extra });
  try {
    const token = await tokenGraph(c);
    const enc = new TextEncoder(), dec = new TextDecoder();
    const entradas: Entrada[] = [], manifesto: Record<string, unknown>[] = [], mascarados: Record<string, number> = {};
    const tempos = { exportar_ms: 0, compactar_ms: 0, enviar_ms: 0 };
    for (const t of TABELAS) {
      if (t in FORA) continue;
      let marca = Date.now();
      let { json, linhas: n } = await exportarTabela(q, t, inicio);
      if (t !== "radar_imagens") {
        let achou = 0;
        const texto = dec.decode(json);
        const limpo = texto.replace(RX_SEGREDO, () => { achou++; return "[mascarado]"; });
        if (achou) { mascarados[t] = achou; json = enc.encode(limpo); }
      }
      brutos += json.length;
      linhas += n;
      tabelas++;
      tempos.exportar_ms += Date.now() - marca;
      if (brutos > MAX_MB * MIB) {
        throw new Erro(413, `O banco passou de ${MAX_MB} MB de dados: a cópia automática precisa ser dividida (avise o suporte). Nada foi enviado.`,
                       "tamanho");
      }
      marca = Date.now();
      const resumo = await sha256(json);
      const nome = `tabelas/${t}.json`;
      let entrada: Entrada;
      if (!SEM_COMPACTAR.has(t) && json.length <= COMPACTAR_TABELA_MAX && tempos.compactar_ms < COMPACTAR_MS) {
        const g = deGzip(await gzip(json), json.length);
        entrada = { nome, metodo: 8, crc: g.crc, tamanho: json.length, dados: g.deflate };
      } else {
        entrada = { nome, metodo: 0, crc: crc32(json), tamanho: json.length, dados: json };
      }
      tempos.compactar_ms += Date.now() - marca;
      entradas.push(entrada);
      manifesto.push({ tabela: t, arquivo: nome, linhas: n, bytes: json.length, sha256: resumo, compactado: entrada.metodo === 8 });
    }
    const man = enc.encode(JSON.stringify({
      radar: "Radar Artecon", arquivo, gerado_em: gerado, origem: q.quem, versao_funcao: VERSAO, versao_banco: comeco?.banco ?? null,
      tabelas: manifesto, linhas, bytes_brutos: brutos, ...(Object.keys(mascarados).length ? { mascarados } : {}),
      nao_inclui: ["os arquivos do armazenamento (vídeos e lâminas da Pauta)", "os logins e as senhas (Supabase Auth)",
                   "os segredos (Vault e Edge Functions)"],
    }, null, 2) + "\n");
    const leia = enc.encode(LEIA_ME(gerado, arquivo));
    const fixo = async (nome: string, d: Bytes): Promise<Entrada> => {
      const g = deGzip(await gzip(d), d.length);
      return { nome, metodo: 8, crc: g.crc, tamanho: d.length, dados: g.deflate };
    };
    const zip = montarZip([await fixo("LEIA-ME.txt", leia), await fixo("manifesto.json", man), ...entradas], gerado);
    const resumo = await sha256(man);
    const marca = Date.now();
    await enviar(token, inicio, c, arquivo, zip.partes, zip.total);
    tempos.enviar_ms = Date.now() - marca;
    await terminar(true, { p_bytes: zip.total, p_sha256: resumo });
    return { arquivo, bytes: zip.total, bytes_brutos: brutos, linhas, tabelas, sha256: resumo, mascarados, tempos };
  } catch (e) {
    const msg = e instanceof Erro ? e.message : "Erro inesperado na cópia.";
    await terminar(false, { p_erro: msg }).catch(() => {});
    throw e instanceof Erro ? e : new Erro(500, msg, "envio");
  }
}

// ------------------------------------------------------------------ testar (só o administrador)
type Item = { item: string; ok: boolean; detalhe: string };
async function testar(c: Config, inicio: number) {
  const itens: Item[] = [];
  const fim = () => ({ itens, tudo_certo: itens.length === 8 && itens.every((i) => i.ok), configurada: c.configurada, versao: VERSAO });
  const msg = (e: unknown) => e instanceof Error ? e.message : "erro";
  itens.push({ item: "Função radar-copia instalada", ok: true, detalhe: "versão " + VERSAO });
  itens.push({ item: "Segredos da cópia", ok: c.configurada, detalhe: c.configurada ? "configurados (COPIA_CLIENT_ID, COPIA_CLIENT_SECRET, " +
    "COPIA_DRIVE_ID, COPIA_PASTA_ID e o GRAPH_TENANT_ID da ITC)" : faltaConfig(c) });
  if (!c.configurada) return fim();
  let token: string;
  try {
    token = await tokenGraph(c);
    itens.push({ item: "Login na Microsoft (aplicativo das cópias)", ok: true, detalhe: "o aplicativo entrou" });
  } catch (e) {
    itens.push({ item: "Login na Microsoft (aplicativo das cópias)", ok: false, detalhe: msg(e) });
    return fim();
  }
  const roles = rolesDoToken(token), mais = roles.filter((r) => r !== ROLE);
  itens.push({ item: "Permissão do aplicativo", ok: roles.includes(ROLE) && !mais.length,
    detalhe: mais.length ? `permissão a mais: ${mais.join(", ")} — tire em Entra → Permissões de API (o Radar só precisa de ${ROLE})`
      // v0.32.0 (revisão): o token do aplicativo só traz as permissões de aplicativo; a delegada (o User.Read que o Entra põe em todo
      // registro novo) não aparece aqui, e o "Conceder consentimento" a concede junto: o passo a passo manda tirá-la antes
      : roles.includes(ROLE) ? `só ${ROLE} (a pasta liberada). As permissões delegadas (como User.Read) não aparecem neste teste: ` +
        `no Entra, em Permissões de API, a lista deve ter só ${ROLE}`
      : "falta o consentimento do administrador (Entra → Permissões de API → Conceder consentimento do administrador)" });
  const drive = encodeURIComponent(c.drive), pasta = encodeURIComponent(c.pasta);
  let pastaOk = false;
  try {
    const d = await graph(token, inicio, "GET", `${GRAPH_URL}/drives/${drive}/items/${pasta}?$select=id,name,folder`);
    pastaOk = Boolean(d?.folder);
    itens.push({ item: "Pasta liberada", ok: pastaOk, detalhe: pastaOk ? `“${String(d?.name ?? "").slice(0, 120)}”` : "o item não é uma pasta: confira COPIA_PASTA_ID" });
  } catch (e) { itens.push({ item: "Pasta liberada", ok: false, detalhe: msg(e) }); }
  try {
    const r = await graphPedir(token, inicio, "GET", `${GRAPH_URL}/drives/${drive}/root?$select=id`);
    const fora = r.status === 403 || r.status === 404;
    itens.push({ item: "O resto do OneDrive fica fora do alcance", ok: fora,
      detalhe: fora ? `como esperado: o aplicativo só enxerga a pasta (a raiz do OneDrive respondeu ${r.status})`
        : r.status >= 200 && r.status <= 299 ? "o aplicativo enxerga o OneDrive inteiro: a permissão está larga demais"
        : `resposta inesperada da raiz do OneDrive (HTTP ${r.status}, ${codigoDe(r.dados, r.status)})` });
  } catch (e) { itens.push({ item: "O resto do OneDrive fica fora do alcance", ok: false, detalhe: msg(e) }); }
  const semPasta = "não testado: primeiro a pasta precisa estar liberada (item “Pasta liberada”, acima)";
  if (!pastaOk) {
    itens.push({ item: "Gravar um arquivo pequeno", ok: false, detalhe: semPasta },
               { item: "Gravar em pedaços (arquivo grande)", ok: false, detalhe: semPasta });
    return fim();
  }
  try {
    const agora = new Date(Date.now() - 3 * 3600_000).toISOString();
    const texto = new TextEncoder().encode(`Teste do Radar em ${agora.slice(8, 10)}/${agora.slice(5, 7)}/${agora.slice(0, 4)} ${agora.slice(11, 16)}\r\n`);
    await enviar(token, inicio, c, "radar-teste-conexao.txt", [texto], texto.length, "replace");
    itens.push({ item: "Gravar um arquivo pequeno", ok: true, detalhe: `radar-teste-conexao.txt gravado (${texto.length} bytes, conferido)` });
  } catch (e) { itens.push({ item: "Gravar um arquivo pequeno", ok: false, detalhe: msg(e) }); }
  try {
    const grande = new Uint8Array(409_600);                      // 2 pedaços: 327 680 + 81 920 bytes
    await enviarEmPedacos(token, inicio, `${GRAPH_URL}/drives/${drive}/items/${pasta}:/radar-teste-pedacos.bin:`, "replace", [grande],
                          grande.length, 327_680)
      .then((item) => {
        if (Number(item?.size) !== grande.length) throw new Erro(502, "o OneDrive guardou um tamanho diferente do enviado", "envio");
      });
    itens.push({ item: "Gravar em pedaços (arquivo grande)", ok: true, detalhe: "radar-teste-pedacos.bin gravado em 2 pedaços (409.600 bytes, conferido)" });
  } catch (e) { itens.push({ item: "Gravar em pedaços (arquivo grande)", ok: false, detalhe: msg(e) }); }
  return fim();
}

// ------------------------------------------------------------------ o pedido
async function tratar(req: Request): Promise<Response> {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  const inicio = Date.now();
  let quem: Quem | null = null;
  try {
    if (req.method !== "POST") throw new Erro(405, "Use POST.");
    if (!SUPABASE_URL) throw new Erro(503, "A função está sem SUPABASE_URL.");
    quem = await autorizar(req);
    const pedido = await req.json().catch(() => ({}));
    const acao = String(pedido?.acao ?? "");
    const c = configCopia();
    if (acao === "agenda_teste") {
      if (quem.quem !== "agenda") throw new Erro(403, "Só a agenda usa esta ação.");
      return responder(200, { ok: true, versao: VERSAO });
    }
    if (acao === "situacao" || acao === "testar") {
      if (quem.quem !== "admin") throw new Erro(403, "Só o administrador usa esta ação.");
      if (acao === "situacao") return responder(200, { versao: VERSAO, configurada: c.configurada, faltam: c.faltam, invalidos: c.invalidos });
      return responder(200, await testar(c, inicio));
    }
    if (acao !== "copiar") throw new Erro(400, "Ação desconhecida.");
    // sem os segredos: nada é registrado e a Microsoft não é chamada (o lembrete da cópia nunca dispara para quem não configurou)
    if (!c.configurada) return responder(200, { ok: false, configurada: false, versao: VERSAO, mensagem: faltaConfig(c) });
    if (quem.quem === "admin") {             // o token já foi conferido pelo banco (radar_papel): aqui, só quanto tempo ele ainda vale
      const exp = cargaDoJwt(String(quem.cab).replace(/^Bearer\s+/, ""))?.exp;
      if (typeof exp === "number" && exp * 1000 - Date.now() < SESSAO_MIN_MS) {
        throw new Erro(401, "A sua sessão está perto de vencer e a cópia não começou: recarregue a página (ou entre de novo) e clique outra " +
          "vez em “Fazer a cópia agora”.");
      }
    }
    try {
      const r = await copiar(quem, c, inicio);
      console.log(`radar-copia (${quem.quem}): ok, ${r.tabelas} tabelas, ${r.linhas} linhas, ${(r.bytes / MIB).toFixed(1)} MB, ${Date.now() - inicio} ms`);
      if (quem.quem === "agenda") return responder(200, { ok: true, versao: VERSAO });
      return responder(200, { ok: true, arquivo: r.arquivo, bytes: r.bytes, bytes_brutos: r.bytes_brutos, linhas: r.linhas, tabelas: r.tabelas,
                              mascarados: r.mascarados, tempos: r.tempos, versao: VERSAO });
    } catch (e) {
      const tipo = e instanceof Erro ? e.tipo : "envio";
      console.log(`radar-copia (${quem.quem}): falhou (${tipo}), ${Date.now() - inicio} ms`);
      if (quem.quem === "agenda") return responder(200, { ok: false, versao: VERSAO, erro: tipo });
      throw e;
    }
  } catch (e) {
    if (e instanceof Erro) return responder(e.status, { message: e.message });
    console.error("radar-copia: erro inesperado", e instanceof Error ? e.name : "");
    return responder(500, { message: "Erro inesperado na cópia de segurança." });
  }
}

const portaLocal = Deno.env.get("RADAR_PORTA_LOCAL");       // só para rodar/testar fora do Supabase
portaLocal ? Deno.serve({ port: Number(portaLocal), hostname: "127.0.0.1" }, tratar) : Deno.serve(tratar);
