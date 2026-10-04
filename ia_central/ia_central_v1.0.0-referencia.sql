-- =====================================================================
-- IA CENTRAL — controle de consumo da API Anthropic — v1.0.0 (27/09/2026)
-- Projeto Supabase: Departamento Pessoal (fbxelwhdiisfmnwrerbl) — schema core
--
-- O que cria (NÃO altera nenhuma tabela ou função existente):
--   core.ia_config        parâmetros (administradores, e-mails de alerta, % de aviso,
--                         limite TOTAL do mês, saldo mínimo, relatório mensal)
--   core.ia_apps          um registro por aplicativo: token, limites mensal/diário,
--                         modelos liberados e máximo de tokens por chamada
--   core.ia_precos        preço por modelo (US$ por milhão de tokens)
--   core.ia_uso           cada chamada à IA: app, usuário, modelo, tokens, custo, resultado
--   core.ia_saldo         saldo informado do Console e recargas (para o saldo estimado)
--   core.ia_notificacoes  avisos ao administrador (sem repetição)
--   core.ia_alteracoes    registro de quem alterou limites, tokens e parâmetros
--   + funções para o ia-gateway e para a tela "Consumo de IA" do Portal
--   + agenda do relatório mensal (dia 1, 08:00 de Brasília)
--
-- Rodar UMA vez no SQL Editor. Se já estiver instalado, para sem alterar nada.
-- =====================================================================
begin;

do $$
begin
  if to_regclass('core.ia_uso') is not null then
    raise exception 'IA Central já instalada (core.ia_uso existe). Nada foi alterado.';
  end if;
  if to_regnamespace('core') is null then
    raise exception 'Schema core não encontrado — rode no projeto Departamento Pessoal.';
  end if;
end $$;

create extension if not exists pgcrypto with schema extensions;

-- ---------------------------------------------------------------------
-- Tabelas
-- ---------------------------------------------------------------------
create table core.ia_config (
  id                     int primary key default 1 check (id = 1),
  admins                 text[] not null default array['cleiver@artecon.cnt.br'],
  email_alertas          text[] not null default array['cleiver@artecon.cnt.br'],
  alerta_pct             int not null default 80 check (alerta_pct between 50 and 99),
  limite_total_mensal_usd numeric(10,2) not null default 40 check (limite_total_mensal_usd > 0),
  saldo_minimo_usd       numeric(10,2) not null default 5 check (saldo_minimo_usd >= 0),
  relatorio_mensal       boolean not null default true,
  atualizado_em          timestamptz not null default now(),
  atualizado_por         text
);
insert into core.ia_config default values;

create table core.ia_apps (
  app                text primary key check (app ~ '^[a-z0-9_]{2,30}$'),
  nome               text not null,
  token_hash         text unique,
  token_criado_em    timestamptz,
  limite_mensal_usd  numeric(10,2) not null check (limite_mensal_usd >= 0),
  limite_diario_usd  numeric(10,2) check (limite_diario_usd is null or limite_diario_usd >= 0),
  modelos            text[] not null,
  max_tokens         int not null check (max_tokens between 64 and 32000),
  ativo              boolean not null default true,
  criado_em          timestamptz not null default now(),
  atualizado_em      timestamptz not null default now()
);
insert into core.ia_apps (app, nome, limite_mensal_usd, limite_diario_usd, modelos, max_tokens) values
  ('atp',        'Análise Tributária — pareceres',       20.00, 5.00, array['claude-sonnet-4-6'],                   8000),
  ('cct',        'CCT Monitor — análise sob demanda',    10.00, 3.00, array['claude-sonnet-4-6'],                   6000),
  ('financeiro', 'Financeiro — leitura de anexos',        5.00, 1.00, array['claude-haiku-4-5'],                    1024),
  ('ncm',        'NCM — refino da classificação',         5.00, 1.00, array['claude-haiku-4-5','claude-sonnet-4-6'], 1024);

-- Preço em US$ por MILHÃO de tokens. Conferir em https://claude.com/pricing antes de mudar.
-- O modelo da chamada é comparado pelo começo do nome (ex.: claude-haiku-4-5-20251001 → claude-haiku-4-5).
create table core.ia_precos (
  prefixo        text primary key,
  entrada        numeric(10,4) not null,
  saida          numeric(10,4) not null,
  cache_escrita  numeric(10,4) not null,
  cache_leitura  numeric(10,4) not null,
  atualizado_em  timestamptz not null default now()
);
insert into core.ia_precos (prefixo, entrada, saida, cache_escrita, cache_leitura) values
  ('claude-haiku-4-5',  1.00,  5.00, 1.25, 0.10),
  ('claude-sonnet-4-6', 3.00, 15.00, 3.75, 0.30);

create table core.ia_uso (
  id             bigserial primary key,
  em             timestamptz not null default now(),
  app            text not null references core.ia_apps(app),
  usuario        text,
  modelo         text,
  entrada        int not null default 0,
  saida          int not null default 0,
  cache_escrita  int not null default 0,
  cache_leitura  int not null default 0,
  custo_usd      numeric(12,6) not null default 0,
  status         text not null check (status in ('ok','erro','bloqueado','sem_credito')),
  http           int,
  ms             int,
  detalhe        text
);
create index ia_uso_app_em on core.ia_uso (app, em);
create index ia_uso_em on core.ia_uso (em);

create table core.ia_saldo (
  id         bigserial primary key,
  em         timestamptz not null default now(),
  tipo       text not null check (tipo in ('saldo_informado','recarga')),
  valor_usd  numeric(10,2) not null check (valor_usd >= 0),
  obs        text,
  por        text
);

create table core.ia_notificacoes (
  id         bigserial primary key,
  em         timestamptz not null default now(),
  chave      text not null unique,
  nivel      text not null check (nivel in ('info','aviso','critico')),
  titulo     text not null,
  texto      text not null,
  app        text,
  lida_em    timestamptz
);

create table core.ia_alteracoes (
  id      bigserial primary key,
  em      timestamptz not null default now(),
  por     text,
  acao    text not null,
  app     text,
  antes   jsonb,
  depois  jsonb
);

-- Sem políticas: ninguém lê/grava direto. Acesso só pelas funções abaixo e pelo ia-gateway.
alter table core.ia_config       enable row level security;  alter table core.ia_config       force row level security;
alter table core.ia_apps         enable row level security;  alter table core.ia_apps         force row level security;
alter table core.ia_precos       enable row level security;  alter table core.ia_precos       force row level security;
alter table core.ia_uso          enable row level security;  alter table core.ia_uso          force row level security;
alter table core.ia_saldo        enable row level security;  alter table core.ia_saldo        force row level security;
alter table core.ia_notificacoes enable row level security;  alter table core.ia_notificacoes force row level security;
alter table core.ia_alteracoes   enable row level security;  alter table core.ia_alteracoes   force row level security;

revoke all on core.ia_config, core.ia_apps, core.ia_precos, core.ia_uso, core.ia_saldo,
              core.ia_notificacoes, core.ia_alteracoes from public, anon, authenticated;

-- ---------------------------------------------------------------------
-- Funções de apoio (internas)
-- ---------------------------------------------------------------------
create or replace function core.ia_email_atual() returns text
language sql stable set search_path = core, public as $$
  select coalesce(nullif(lower(auth.jwt()->>'email'), ''), session_user::text);
$$;

-- Administrador da IA Central = e-mail do login na lista ia_config.admins
-- (ou o dono do banco rodando no SQL Editor).
create or replace function core.ia_eh_admin() returns boolean
language sql stable security definer set search_path = core, public as $$
  select (auth.jwt() is null and session_user in ('postgres','supabase_admin'))   -- SQL Editor
      or exists (select 1 from core.ia_config c, unnest(c.admins) a
                 where lower(a) = lower(coalesce(auth.jwt()->>'email','')));
$$;

create or replace function core.ia_exigir_admin() returns void
language plpgsql stable security definer set search_path = core, public as $$
begin
  if not core.ia_eh_admin() then
    raise exception 'Apenas administradores da IA Central podem fazer isto.' using errcode = '42501';
  end if;
end $$;

create or replace function core.ia_ini_mes(p timestamptz default now()) returns timestamptz
language sql stable as $$
  select date_trunc('month', p at time zone 'America/Sao_Paulo') at time zone 'America/Sao_Paulo';
$$;

create or replace function core.ia_ini_dia(p timestamptz default now()) returns timestamptz
language sql stable as $$
  select date_trunc('day', p at time zone 'America/Sao_Paulo') at time zone 'America/Sao_Paulo';
$$;

create or replace function core.ia_gasto(p_app text, p_desde timestamptz, p_ate timestamptz default null)
returns numeric language sql stable security definer set search_path = core, public as $$
  select coalesce(sum(custo_usd), 0) from core.ia_uso
   where (p_app is null or app = p_app) and em >= p_desde and (p_ate is null or em < p_ate);
$$;

-- Saldo estimado = último saldo informado + recargas depois dele − gasto registrado depois dele.
create or replace function core.ia_saldo_estimado() returns numeric
language sql stable security definer set search_path = core, public as $$
  select l.valor_usd
       + coalesce((select sum(r.valor_usd) from core.ia_saldo r where r.tipo = 'recarga' and r.em > l.em), 0)
       - coalesce((select sum(u.custo_usd) from core.ia_uso u where u.em > l.em), 0)
    from core.ia_saldo l
   where l.tipo = 'saldo_informado'
   order by l.em desc
   limit 1;
$$;

-- Cria um aviso uma única vez por chave. Devolve o aviso se for novo.
create or replace function core.ia_notificar(p_chave text, p_nivel text, p_titulo text, p_texto text, p_app text default null)
returns jsonb language plpgsql security definer set search_path = core, public as $$
declare v core.ia_notificacoes;
begin
  insert into core.ia_notificacoes (chave, nivel, titulo, texto, app)
  values (p_chave, p_nivel, p_titulo, p_texto, p_app)
  on conflict (chave) do nothing
  returning * into v;
  if v.id is null then return null; end if;
  return jsonb_build_object('nivel', v.nivel, 'titulo', v.titulo, 'texto', v.texto, 'app', v.app);
end $$;

-- ---------------------------------------------------------------------
-- Funções do ia-gateway (somente service_role)
-- ---------------------------------------------------------------------
create or replace function core.ia_checar(p_token_hash text, p_modelo text) returns jsonb
language plpgsql stable security definer set search_path = core, public as $$
declare
  a core.ia_apps; c core.ia_config;
  g_mes numeric; g_dia numeric; g_tot numeric;
begin
  select * into a from core.ia_apps where token_hash = p_token_hash;
  if not found then
    return jsonb_build_object('ok', false, 'http', 401, 'motivo', 'Token do aplicativo inválido ou substituído. Gere um novo no Portal → Consumo de IA.');
  end if;
  select * into c from core.ia_config where id = 1;
  if not a.ativo then
    return jsonb_build_object('ok', false, 'app', a.app, 'http', 403,
      'motivo', format('O uso de IA do aplicativo "%s" está desligado no Portal Artecon.', a.nome));
  end if;
  if not exists (select 1 from unnest(a.modelos) m where coalesce(p_modelo,'') like m || '%') then
    return jsonb_build_object('ok', false, 'app', a.app, 'http', 403,
      'motivo', format('O modelo "%s" não está liberado para "%s". Liberados: %s.', coalesce(p_modelo,'(vazio)'), a.nome, array_to_string(a.modelos, ', ')));
  end if;
  if not exists (select 1 from core.ia_precos p where p_modelo like p.prefixo || '%') then
    return jsonb_build_object('ok', false, 'app', a.app, 'http', 403,
      'motivo', format('O modelo "%s" não tem preço cadastrado na IA Central.', p_modelo));
  end if;

  g_mes := core.ia_gasto(a.app, core.ia_ini_mes());
  g_dia := core.ia_gasto(a.app, core.ia_ini_dia());
  g_tot := core.ia_gasto(null,  core.ia_ini_mes());

  if g_tot >= c.limite_total_mensal_usd then
    return jsonb_build_object('ok', false, 'app', a.app, 'http', 429,
      'motivo', format('Limite TOTAL de IA do mês atingido (US$ %s de US$ %s). O administrador pode ajustar no Portal → Consumo de IA.',
                       round(g_tot,2), c.limite_total_mensal_usd));
  end if;
  if g_mes >= a.limite_mensal_usd then
    return jsonb_build_object('ok', false, 'app', a.app, 'http', 429,
      'motivo', format('Limite mensal de IA de "%s" atingido (US$ %s de US$ %s). O administrador pode ajustar no Portal → Consumo de IA.',
                       a.nome, round(g_mes,2), a.limite_mensal_usd));
  end if;
  if a.limite_diario_usd is not null and g_dia >= a.limite_diario_usd then
    return jsonb_build_object('ok', false, 'app', a.app, 'http', 429,
      'motivo', format('Limite diário de IA de "%s" atingido (US$ %s de US$ %s). Libera amanhã ou o administrador pode ajustar no Portal.',
                       a.nome, round(g_dia,2), a.limite_diario_usd));
  end if;

  return jsonb_build_object('ok', true, 'app', a.app, 'nome', a.nome, 'max_tokens', a.max_tokens,
                            'gasto_mes', g_mes, 'gasto_dia', g_dia);
end $$;

create or replace function core.ia_registrar(
  p_app text, p_modelo text, p_usuario text,
  p_entrada int, p_saida int, p_cache_escrita int, p_cache_leitura int,
  p_status text, p_http int, p_ms int, p_detalhe text
) returns jsonb
language plpgsql security definer set search_path = core, public as $$
declare
  pr core.ia_precos; a core.ia_apps; c core.ia_config;
  v_custo numeric := 0; g_mes numeric; g_dia numeric; g_tot numeric; v_saldo numeric;
  v_mes text := to_char(now() at time zone 'America/Sao_Paulo', 'YYYY-MM');
  v_dia text := to_char(now() at time zone 'America/Sao_Paulo', 'YYYY-MM-DD');
  v_alertas jsonb := '[]'::jsonb; v_n jsonb; v_pct numeric;
begin
  select * into a from core.ia_apps where app = p_app;
  if not found then raise exception 'App % não cadastrado na IA Central', p_app; end if;
  select * into c from core.ia_config where id = 1;

  select * into pr from core.ia_precos where coalesce(p_modelo,'') like prefixo || '%'
   order by length(prefixo) desc limit 1;
  if found then
    v_custo := ( coalesce(p_entrada,0)       * pr.entrada
               + coalesce(p_saida,0)         * pr.saida
               + coalesce(p_cache_escrita,0) * pr.cache_escrita
               + coalesce(p_cache_leitura,0) * pr.cache_leitura ) / 1000000.0;
  end if;

  insert into core.ia_uso (app, usuario, modelo, entrada, saida, cache_escrita, cache_leitura, custo_usd, status, http, ms, detalhe)
  values (p_app, left(p_usuario,120), left(p_modelo,80), coalesce(p_entrada,0), coalesce(p_saida,0),
          coalesce(p_cache_escrita,0), coalesce(p_cache_leitura,0), v_custo, p_status, p_http, p_ms, left(p_detalhe,500));

  -- ---- avisos -------------------------------------------------------
  g_mes := core.ia_gasto(p_app, core.ia_ini_mes());
  g_dia := core.ia_gasto(p_app, core.ia_ini_dia());
  g_tot := core.ia_gasto(null,  core.ia_ini_mes());

  if a.limite_mensal_usd > 0 then
    v_pct := g_mes / a.limite_mensal_usd * 100;
    if v_pct >= 100 then
      v_n := core.ia_notificar('lim100:'||p_app||':'||v_mes, 'critico',
               format('IA bloqueada: %s atingiu o limite do mês', a.nome),
               format('Gasto de US$ %s no mês, limite de US$ %s. Novas chamadas do aplicativo ficam bloqueadas até o próximo mês ou até o limite ser aumentado no Portal.', round(g_mes,2), a.limite_mensal_usd), p_app);
    elsif v_pct >= c.alerta_pct then
      v_n := core.ia_notificar('limpct:'||p_app||':'||v_mes, 'aviso',
               format('%s usou %s%% do limite de IA do mês', a.nome, floor(v_pct)),
               format('Gasto de US$ %s de US$ %s no mês.', round(g_mes,2), a.limite_mensal_usd), p_app);
    else v_n := null; end if;
    if v_n is not null then v_alertas := v_alertas || v_n; end if;
  end if;

  if a.limite_diario_usd is not null and a.limite_diario_usd > 0 and g_dia >= a.limite_diario_usd then
    v_n := core.ia_notificar('limdia:'||p_app||':'||v_dia, 'aviso',
             format('%s atingiu o limite diário de IA', a.nome),
             format('Gasto de US$ %s hoje, limite diário de US$ %s. Libera amanhã.', round(g_dia,2), a.limite_diario_usd), p_app);
    if v_n is not null then v_alertas := v_alertas || v_n; end if;
  end if;

  v_pct := g_tot / c.limite_total_mensal_usd * 100;
  if v_pct >= 100 then
    v_n := core.ia_notificar('tot100:'||v_mes, 'critico', 'IA bloqueada: limite TOTAL do mês atingido',
             format('Todos os aplicativos somam US$ %s no mês, limite total de US$ %s.', round(g_tot,2), c.limite_total_mensal_usd));
  elsif v_pct >= c.alerta_pct then
    v_n := core.ia_notificar('totpct:'||v_mes, 'aviso', format('IA: %s%% do limite total do mês', floor(v_pct)),
             format('Todos os aplicativos somam US$ %s de US$ %s no mês.', round(g_tot,2), c.limite_total_mensal_usd));
  else v_n := null; end if;
  if v_n is not null then v_alertas := v_alertas || v_n; end if;

  v_saldo := core.ia_saldo_estimado();
  if v_saldo is not null and v_saldo < c.saldo_minimo_usd then
    v_n := core.ia_notificar('saldo:'||v_dia, 'aviso', 'Crédito da Anthropic acabando',
             format('Saldo estimado de US$ %s (mínimo configurado: US$ %s). Recarregue em platform.claude.com → Billing e lance a recarga no Portal.', round(v_saldo,2), c.saldo_minimo_usd));
    if v_n is not null then v_alertas := v_alertas || v_n; end if;
  end if;

  if p_status = 'sem_credito' then
    v_n := core.ia_notificar('semcredito:'||v_dia, 'critico', 'Crédito da Anthropic ESGOTADO',
             'A Anthropic recusou a chamada por falta de crédito. Todos os aplicativos com IA estão parados até a recarga em platform.claude.com → Billing.', p_app);
    if v_n is not null then v_alertas := v_alertas || v_n; end if;
  end if;

  return jsonb_build_object('custo', v_custo, 'alertas', v_alertas, 'emails', to_jsonb(c.email_alertas));
end $$;

create or replace function core.ia_cron_ok(p_segredo text) returns boolean
language sql stable security definer set search_path = core, public as $$
  select coalesce(p_segredo,'') <> ''
     and exists (select 1 from vault.decrypted_secrets where name = 'IA_CRON_SECRET' and decrypted_secret = p_segredo);
$$;

-- Resumo completo de um mês (usado pelo Portal e pelo relatório mensal).
create or replace function core.ia_resumo_interno(p_mes date default null) returns jsonb
language plpgsql stable security definer set search_path = core, public as $$
declare
  v_ref  date := date_trunc('month', coalesce(p_mes, (now() at time zone 'America/Sao_Paulo')::date))::date;
  v_ini  timestamptz := v_ref::timestamp at time zone 'America/Sao_Paulo';
  v_fim  timestamptz := (v_ref + interval '1 month')::timestamp at time zone 'America/Sao_Paulo';
  v_ant  timestamptz := (v_ref - interval '1 month')::timestamp at time zone 'America/Sao_Paulo';
  v_hoje timestamptz := core.ia_ini_dia();
  c core.ia_config; v_ultimo core.ia_saldo;
begin
  select * into c from core.ia_config where id = 1;
  select * into v_ultimo from core.ia_saldo where tipo = 'saldo_informado' order by em desc limit 1;

  return jsonb_build_object(
    'mes', to_char(v_ref, 'YYYY-MM'),
    'gerado_em', now(),
    'config', jsonb_build_object('admins', c.admins, 'email_alertas', c.email_alertas, 'alerta_pct', c.alerta_pct,
                                 'limite_total_mensal_usd', c.limite_total_mensal_usd, 'saldo_minimo_usd', c.saldo_minimo_usd,
                                 'relatorio_mensal', c.relatorio_mensal),
    'total_mes',      core.ia_gasto(null, v_ini, v_fim),
    'total_hoje',     core.ia_gasto(null, v_hoje),
    'total_mes_anterior', core.ia_gasto(null, v_ant, v_ini),
    'saldo', jsonb_build_object('estimado', core.ia_saldo_estimado(),
                                'informado_em', v_ultimo.em, 'informado_usd', v_ultimo.valor_usd,
                                'recargas_depois', coalesce((select sum(valor_usd) from core.ia_saldo r where r.tipo='recarga' and r.em > v_ultimo.em), 0)),
    'apps', coalesce((
      select jsonb_agg(jsonb_build_object(
               'app', a.app, 'nome', a.nome, 'ativo', a.ativo, 'modelos', a.modelos, 'max_tokens', a.max_tokens,
               'limite_mensal_usd', a.limite_mensal_usd, 'limite_diario_usd', a.limite_diario_usd,
               'tem_token', a.token_hash is not null, 'token_criado_em', a.token_criado_em,
               'gasto_mes',  core.ia_gasto(a.app, v_ini, v_fim),
               'gasto_hoje', core.ia_gasto(a.app, v_hoje),
               'chamadas_mes',  (select count(*) from core.ia_uso u where u.app = a.app and u.em >= v_ini and u.em < v_fim and u.status = 'ok'),
               'bloqueios_mes', (select count(*) from core.ia_uso u where u.app = a.app and u.em >= v_ini and u.em < v_fim and u.status = 'bloqueado'),
               'erros_mes',     (select count(*) from core.ia_uso u where u.app = a.app and u.em >= v_ini and u.em < v_fim and u.status in ('erro','sem_credito')),
               'ultimo_uso',    (select max(u.em) from core.ia_uso u where u.app = a.app)
             ) order by a.nome)
        from core.ia_apps a), '[]'::jsonb),
    'diario', coalesce((
      select jsonb_agg(jsonb_build_object('dia', d.dia, 'app', d.app, 'custo', d.custo, 'chamadas', d.chamadas) order by d.dia, d.app)
        from (select (u.em at time zone 'America/Sao_Paulo')::date as dia, u.app,
                     sum(u.custo_usd) as custo, count(*) filter (where u.status = 'ok') as chamadas
                from core.ia_uso u where u.em >= v_ini and u.em < v_fim
               group by 1, 2) d), '[]'::jsonb),
    'modelos', coalesce((
      select jsonb_agg(jsonb_build_object('modelo', m.modelo, 'custo', m.custo, 'chamadas', m.chamadas) order by m.custo desc)
        from (select u.modelo, sum(u.custo_usd) as custo, count(*) as chamadas
                from core.ia_uso u where u.em >= v_ini and u.em < v_fim and u.status = 'ok'
               group by 1) m), '[]'::jsonb),
    'ultimas', coalesce((
      select jsonb_agg(to_jsonb(x) order by x.em desc)
        from (select u.em, u.app, u.usuario, u.modelo, u.entrada, u.saida, u.custo_usd, u.status, u.http, u.detalhe
                from core.ia_uso u order by u.em desc limit 30) x), '[]'::jsonb),
    'notificacoes', coalesce((
      select jsonb_agg(to_jsonb(n) order by n.em desc)
        from (select id, em, nivel, titulo, texto, app, lida_em from core.ia_notificacoes order by em desc limit 20) n), '[]'::jsonb),
    'nao_lidas', (select count(*) from core.ia_notificacoes where lida_em is null)
  );
end $$;

-- ---------------------------------------------------------------------
-- Funções do Portal (usuário logado; só administradores da IA Central)
-- ---------------------------------------------------------------------
create or replace function core.ia_painel(p_mes date default null) returns jsonb
language plpgsql stable security definer set search_path = core, public as $$
begin
  perform core.ia_exigir_admin();
  return core.ia_resumo_interno(p_mes);
end $$;

create or replace function core.ia_salvar_app(p_app text, p_limite_mensal numeric, p_limite_diario numeric,
                                              p_ativo boolean, p_max_tokens int default null)
returns jsonb language plpgsql security definer set search_path = core, public as $$
declare v_antes core.ia_apps; v_depois core.ia_apps;
begin
  perform core.ia_exigir_admin();
  select * into v_antes from core.ia_apps where app = p_app for update;
  if not found then raise exception 'Aplicativo % não encontrado.', p_app; end if;
  if p_limite_mensal is null or p_limite_mensal < 0 then raise exception 'Limite mensal inválido.'; end if;
  if p_limite_diario is not null and p_limite_diario < 0 then raise exception 'Limite diário inválido.'; end if;
  update core.ia_apps set
    limite_mensal_usd = p_limite_mensal,
    limite_diario_usd = p_limite_diario,
    ativo             = coalesce(p_ativo, ativo),
    max_tokens        = coalesce(p_max_tokens, max_tokens),
    atualizado_em     = now()
  where app = p_app returning * into v_depois;
  insert into core.ia_alteracoes (por, acao, app, antes, depois)
  values (core.ia_email_atual(), 'salvar_app', p_app,
          to_jsonb(v_antes) - 'token_hash', to_jsonb(v_depois) - 'token_hash');
  return to_jsonb(v_depois) - 'token_hash';
end $$;

create or replace function core.ia_salvar_config(p_alerta_pct int, p_limite_total numeric, p_saldo_minimo numeric,
                                                 p_email_alertas text[], p_relatorio boolean)
returns jsonb language plpgsql security definer set search_path = core, public as $$
declare v_antes core.ia_config; v_depois core.ia_config;
begin
  perform core.ia_exigir_admin();
  select * into v_antes from core.ia_config where id = 1 for update;
  if p_email_alertas is null or cardinality(p_email_alertas) = 0 then
    raise exception 'Informe pelo menos um e-mail para os alertas.';
  end if;
  update core.ia_config set
    alerta_pct = coalesce(p_alerta_pct, alerta_pct),
    limite_total_mensal_usd = coalesce(p_limite_total, limite_total_mensal_usd),
    saldo_minimo_usd = coalesce(p_saldo_minimo, saldo_minimo_usd),
    email_alertas = p_email_alertas,
    relatorio_mensal = coalesce(p_relatorio, relatorio_mensal),
    atualizado_em = now(), atualizado_por = core.ia_email_atual()
  where id = 1 returning * into v_depois;
  insert into core.ia_alteracoes (por, acao, antes, depois)
  values (core.ia_email_atual(), 'salvar_config', to_jsonb(v_antes), to_jsonb(v_depois));
  return to_jsonb(v_depois);
end $$;

-- Gera (ou troca) o token de um aplicativo. O token aparece UMA vez; o banco guarda só o hash.
create or replace function core.ia_gerar_token(p_app text) returns text
language plpgsql security definer set search_path = core, public as $$
declare v_token text;
begin
  perform core.ia_exigir_admin();
  if not exists (select 1 from core.ia_apps where app = p_app) then
    raise exception 'Aplicativo % não encontrado.', p_app;
  end if;
  v_token := 'iagw_' || p_app || '_' || encode(extensions.gen_random_bytes(24), 'hex');
  update core.ia_apps
     set token_hash = encode(extensions.digest(v_token, 'sha256'), 'hex'),
         token_criado_em = now(), atualizado_em = now()
   where app = p_app;
  insert into core.ia_alteracoes (por, acao, app) values (core.ia_email_atual(), 'gerar_token', p_app);
  return v_token;
end $$;

create or replace function core.ia_lancar_saldo(p_tipo text, p_valor numeric, p_obs text default null)
returns jsonb language plpgsql security definer set search_path = core, public as $$
declare v core.ia_saldo;
begin
  perform core.ia_exigir_admin();
  insert into core.ia_saldo (tipo, valor_usd, obs, por)
  values (p_tipo, p_valor, p_obs, core.ia_email_atual()) returning * into v;
  insert into core.ia_alteracoes (por, acao, depois) values (core.ia_email_atual(), 'lancar_saldo', to_jsonb(v));
  return jsonb_build_object('lancamento', to_jsonb(v), 'saldo_estimado', core.ia_saldo_estimado());
end $$;

create or replace function core.ia_marcar_lidas() returns int
language plpgsql security definer set search_path = core, public as $$
declare n int;
begin
  perform core.ia_exigir_admin();
  update core.ia_notificacoes set lida_em = now() where lida_em is null;
  get diagnostics n = row_count;
  return n;
end $$;

-- ---------------------------------------------------------------------
-- Permissões das funções
-- ---------------------------------------------------------------------
revoke all on function core.ia_email_atual(), core.ia_eh_admin(), core.ia_exigir_admin(),
  core.ia_ini_mes(timestamptz), core.ia_ini_dia(timestamptz), core.ia_gasto(text, timestamptz, timestamptz),
  core.ia_saldo_estimado(), core.ia_notificar(text, text, text, text, text),
  core.ia_checar(text, text), core.ia_registrar(text, text, text, int, int, int, int, text, int, int, text),
  core.ia_cron_ok(text), core.ia_resumo_interno(date),
  core.ia_painel(date), core.ia_salvar_app(text, numeric, numeric, boolean, int),
  core.ia_salvar_config(int, numeric, numeric, text[], boolean), core.ia_gerar_token(text),
  core.ia_lancar_saldo(text, numeric, text), core.ia_marcar_lidas()
  from public, anon, authenticated;

-- ia-gateway (chave de serviço)
grant execute on function core.ia_checar(text, text),
  core.ia_registrar(text, text, text, int, int, int, int, text, int, int, text),
  core.ia_cron_ok(text), core.ia_resumo_interno(date),
  core.ia_notificar(text, text, text, text, text), core.ia_eh_admin()
  to service_role;

-- Portal (usuário logado; cada função confere se é administrador)
grant execute on function core.ia_eh_admin(), core.ia_painel(date),
  core.ia_salvar_app(text, numeric, numeric, boolean, int),
  core.ia_salvar_config(int, numeric, numeric, text[], boolean), core.ia_gerar_token(text),
  core.ia_lancar_saldo(text, numeric, text), core.ia_marcar_lidas()
  to authenticated;

grant usage on schema core to service_role, authenticated;

-- ---------------------------------------------------------------------
-- Segredo do relatório mensal (no Vault) + agenda: dia 1, 11:00 UTC = 08:00 de Brasília
-- ---------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from vault.secrets where name = 'IA_CRON_SECRET') then
    perform vault.create_secret(encode(extensions.gen_random_bytes(24), 'hex'), 'IA_CRON_SECRET',
                                'IA Central: autoriza o pg_cron a pedir o relatório mensal ao ia-gateway');
  end if;
end $$;

select cron.schedule(
  'ia-relatorio-mensal',
  '0 11 1 * *',
  $cron$
    select net.http_post(
      url     := 'https://fbxelwhdiisfmnwrerbl.supabase.co/functions/v1/ia-gateway?acao=relatorio',
      headers := jsonb_build_object(
                   'Content-Type', 'application/json',
                   'x-cron-secret', (select decrypted_secret from vault.decrypted_secrets where name = 'IA_CRON_SECRET')),
      body    := '{}'::jsonb
    )
    where (select relatorio_mensal from core.ia_config where id = 1);
  $cron$
);

commit;

-- ---------------------------------------------------------------------
-- Conferência (rode depois do commit): deve mostrar 7 tabelas e 4 aplicativos
-- ---------------------------------------------------------------------
-- select count(*) as tabelas from information_schema.tables where table_schema='core' and table_name like 'ia\_%';
-- select app, nome, limite_mensal_usd, limite_diario_usd, modelos, max_tokens, token_hash is not null as tem_token from core.ia_apps order by app;
-- select jobname, schedule from cron.job where jobname = 'ia-relatorio-mensal';
