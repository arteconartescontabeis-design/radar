// Edge Function "portal-provisionar" — projeto radar-artecon (v1.0.0)
// Cria, reativa ou desativa o login de uma pessoa no RADAR a pedido do PORTAL ARTECON.
// Mesmo contrato das demais (Cobrança Pro / Agenda Pro): quem chama é o portal, com o token da
// sessão do projeto do DP. A função:
//   1) confirma o token no projeto do DP (/auth/v1/user);
//   2) confere no núcleo (core.is_admin) que quem pede é administrador da organização;
//   3) só então usa a chave de serviço DESTE projeto (nunca sai daqui) para mexer no Auth
//      e na tabela public.radar_perfis.
// IMPORTANTE: publicar com "Verify JWT" DESLIGADO — o token vem de outro projeto; a
// verificação é feita aqui dentro, nos passos 1 e 2.
import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const DP_URL = Deno.env.get("DP_URL") ?? "https://fbxelwhdiisfmnwrerbl.supabase.co";
const DP_CHAVE = Deno.env.get("DP_PUBLISHABLE_KEY") ?? "sb_publishable_iRqjOGU1ialauv_wHYarbw_cRzspHH6";
const ORIGENS = (Deno.env.get("ORIGENS_PERMITIDAS") ?? "https://arteconartescontabeis-design.github.io")
  .split(",").map((s) => s.trim());
const ORG_PERMITIDA = Deno.env.get("ORG_PERMITIDA") ?? "";   // opcional: id da organização Artecon no núcleo
// o portal manda "admin"/"operador"/"leitura"; o Radar tem admin/editor/leitor
const PERFIS: Record<string, string> = {
  admin: "admin", diretor: "admin", administrador: "admin",
  operador: "editor", editor: "editor",
  leitura: "leitor", leitor: "leitor",
};

function cors(origem: string | null) {
  const ok = origem && ORIGENS.includes(origem) ? origem : ORIGENS[0];
  return {
    "Access-Control-Allow-Origin": ok,
    "Access-Control-Allow-Headers": "authorization, content-type, apikey, x-client-info",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Vary": "Origin",
  };
}
function resp(corpo: unknown, status: number, h: Record<string, string>) {
  return new Response(JSON.stringify(corpo), { status, headers: { ...h, "Content-Type": "application/json" } });
}

Deno.serve(async (req) => {
  const h = cors(req.headers.get("Origin"));
  if (req.method === "OPTIONS") return new Response("ok", { headers: h });
  if (req.method !== "POST") return resp({ ok: false, erro: "use POST" }, 405, h);

  try {
    const token = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");
    if (!token) return resp({ ok: false, erro: "sem sessão do portal" }, 401, h);
    const corpo = await req.json().catch(() => ({}));
    const acao = String(corpo.acao ?? "");
    const org = String(corpo.org ?? "");
    if (!org) return resp({ ok: false, erro: "organização não informada" }, 400, h);
    if (ORG_PERMITIDA && org !== ORG_PERMITIDA) return resp({ ok: false, erro: "organização sem acesso a este aplicativo" }, 403, h);

    // 1) quem está chamando (sessão do portal, projeto do DP)
    const rU = await fetch(`${DP_URL}/auth/v1/user`, { headers: { apikey: DP_CHAVE, Authorization: `Bearer ${token}` } });
    if (!rU.ok) return resp({ ok: false, erro: "sessão do portal inválida ou expirada" }, 401, h);
    const executor = await rU.json();

    // 2) é administrador da organização no núcleo?
    const rA = await fetch(`${DP_URL}/rest/v1/rpc/is_admin`, {
      method: "POST",
      headers: { apikey: DP_CHAVE, Authorization: `Bearer ${token}`, "Content-Type": "application/json", "Content-Profile": "core", "Accept-Profile": "core" },
      body: JSON.stringify({ p_org: org }),
    });
    let ehAdmin = rA.ok ? await rA.json() : null;
    if (ehAdmin === null) {   // sem permissão de executar a função: confere o vínculo (a RLS do núcleo deixa ler o próprio)
      const rM = await fetch(`${DP_URL}/rest/v1/memberships?select=papel,situacao&org_id=eq.${encodeURIComponent(org)}&user_id=eq.${encodeURIComponent(executor.id)}`,
        { headers: { apikey: DP_CHAVE, Authorization: `Bearer ${token}`, "Accept-Profile": "core" } });
      const m = rM.ok ? await rM.json() : [];
      ehAdmin = Array.isArray(m) && m.some((x: any) => x.situacao === "ativo" && ["admin", "superadmin"].includes(x.papel));
    }
    if (ehAdmin !== true) return resp({ ok: false, erro: "apenas administradores do portal podem gerir contas" }, 403, h);

    const adm = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
      auth: { persistSession: false, autoRefreshToken: false },
    });

    // usuários do Auth deste projeto (poucos — lista completa, paginada)
    const todos: any[] = [];
    for (let p = 1; p <= 20; p++) {
      const { data, error } = await adm.auth.admin.listUsers({ page: p, perPage: 1000 });
      if (error) throw error;
      todos.push(...data.users);
      if (data.users.length < 1000) break;
    }
    const porEmail = (e: string) => todos.find((u) => (u.email ?? "").toLowerCase() === e.toLowerCase());
    const log = (m: string) => console.log(`[portal-provisionar] ${executor.email} → ${m}`);

    // ----- lista: situação das contas (para a tela Acessos do portal)
    if (acao === "lista") {
      const { data: perfis, error } = await adm.from("radar_perfis").select("user_id, papel, nome");
      if (error) throw error;
      const contas = todos.map((u) => {
        const v = (perfis ?? []).find((x) => x.user_id === u.id);
        return { email: (u.email ?? "").toLowerCase(), perfil: v?.papel ?? null, ativo: !!v && !u.banned_until,
          trocar_senha: !!u.user_metadata?.trocar_senha };
      });
      return resp({ ok: true, contas }, 200, h);
    }

    const email = String(corpo.email ?? "").trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return resp({ ok: false, erro: "e-mail inválido" }, 400, h);

    // ----- criar / reativar
    if (acao === "criar") {
      const perfil = PERFIS[String(corpo.perfil ?? "editor")];
      if (!perfil) return resp({ ok: false, erro: "o Radar tem os perfis Administrador, Editor e Leitor" }, 400, h);
      const senha = corpo.senha ? String(corpo.senha) : "";
      if (senha && senha.length < 8) return resp({ ok: false, erro: "a senha provisória precisa de pelo menos 8 caracteres" }, 400, h);
      const nome = String(corpo.nome ?? "").trim();

      let u = porEmail(email), criado = false;
      if (!u) {
        if (!senha) return resp({ ok: false, erro: "informe a senha provisória para criar a conta" }, 400, h);
        const { data, error } = await adm.auth.admin.createUser({ email, password: senha, email_confirm: true,
          user_metadata: { nome, trocar_senha: true, criado_pelo_portal: executor.email } });
        if (error) throw error;
        u = data.user; criado = true;
      } else {
        const upd: Record<string, unknown> = { ban_duration: "none" };
        if (senha) { upd.password = senha; upd.user_metadata = { ...(u.user_metadata ?? {}), nome: nome || u.user_metadata?.nome, trocar_senha: true }; }
        const { error } = await adm.auth.admin.updateUserById(u.id, upd);
        if (error) throw error;
      }
      // perfil do Radar (public.radar_perfis): um por usuário
      const { data: ja, error: e1 } = await adm.from("radar_perfis").select("user_id").eq("user_id", u!.id).maybeSingle();
      if (e1) throw e1;
      const { error: e2 } = ja
        ? await adm.from("radar_perfis").update({ papel: perfil, ...(nome ? { nome } : {}) }).eq("user_id", u!.id)
        : await adm.from("radar_perfis").insert({ user_id: u!.id, nome: nome || email, papel: perfil });
      if (e2) throw e2;
      log(`${criado ? "criou" : "reativou"} ${email} (${perfil})${senha && !criado ? " com nova senha provisória" : ""}`);
      return resp({ ok: true, criado, perfil, senha_definida: !!senha }, 200, h);
    }

    // ----- desativar (bloqueia o login e remove o perfil: sem perfil, a RLS não libera nada)
    if (acao === "desativar") {
      const u = porEmail(email);
      if (!u) return resp({ ok: true, aviso: "não havia conta no Radar" }, 200, h);
      const { error: e1 } = await adm.from("radar_perfis").delete().eq("user_id", u.id);
      if (e1) throw e1;
      const { error: e2 } = await adm.auth.admin.updateUserById(u.id, { ban_duration: "876000h" });
      if (e2) throw e2;
      log(`desativou ${email}`);
      return resp({ ok: true }, 200, h);
    }

    return resp({ ok: false, erro: "ação desconhecida" }, 400, h);
  } catch (e) {
    console.error("[portal-provisionar]", e);
    return resp({ ok: false, erro: String((e as Error)?.message ?? e) }, 500, h);
  }
});
