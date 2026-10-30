-- Radar v0.57.0 — Corretor de polimento de vídeo: controle de COTA e CUSTO.
-- Espelha o padrão do corretor de vídeo (radar_video_cota / radar_video_cfg_num). Incremental idempotente
-- sobre o banco v0.50.0: create or replace / if not exists; nada é apagado; pode rodar de novo.

-- 1) Config padrão (Configurações → Polimento). Só cria se não existir; não sobrescreve o que o dono ajustar.
insert into public.radar_config (chave, valor)
select 'polimento', jsonb_build_object(
         'ligado', true,
         'limite_min_mes', 30,                 -- cota do mês em minutos (1..600; padrão 30)
         'aviso_pct', 80,                       -- avisa ao chegar nesta % da cota
         'preco_cleanvoice_usd_min', 0.0367,    -- Cleanvoice PAYG ~US$ 0,037/min (confere no faturamento)
         'preco_assemblyai_usd_min', 0.0025,    -- AssemblyAI ~US$ 0,15/h = US$ 0,0025/min
         'usd_brl', 5.34)                       -- câmbio p/ estimar o custo em R$ (o dono atualiza)
where not exists (select 1 from public.radar_config where chave = 'polimento');

-- 2) Leitor de config numérica (idêntico ao do corretor, mas na chave 'polimento').
create or replace function public.radar_polimento_cfg_num(p_chave text, p_padrao numeric, p_min numeric, p_max numeric) returns numeric
language sql stable set search_path = public as $$
  select coalesce((select case when jsonb_typeof(c.valor->p_chave) = 'number' and (c.valor->>p_chave)::numeric between p_min and p_max
                               then (c.valor->>p_chave)::numeric end
                     from public.radar_config c where c.chave = 'polimento'), p_padrao)
$$;

-- O polimento está ligado? (Configurações → Polimento → ligado; padrão sim)
create or replace function public.radar_polimento_ligado() returns boolean
language sql stable set search_path = public as $$
  select coalesce((select case when jsonb_typeof(c.valor->'ligado') = 'boolean' then (c.valor->>'ligado')::boolean end
                     from public.radar_config c where c.chave = 'polimento'), true)
$$;

-- 3) Registro de uso: uma linha por chamada de API, com os minutos processados e o custo estimado.
create table if not exists public.radar_polimento_uso (
  id         bigint generated always as identity primary key,
  peca_id    bigint references public.radar_pauta_pecas(id) on delete set null,
  provedor   text not null check (provedor in ('cleanvoice','assemblyai')),
  segundos   numeric(8,1) not null default 0 check (segundos between 0 and 36000),
  custo_usd  numeric(10,4) not null default 0 check (custo_usd >= 0),
  custo_brl  numeric(10,2) not null default 0 check (custo_brl >= 0),
  status     text not null default 'ok' check (status in ('ok','erro')),
  erro       text,
  criado_em  timestamptz not null default now()
);
create index if not exists radar_polimento_uso_mes_idx on public.radar_polimento_uso (criado_em);

-- 4) Cota do mês (de Brasília), limite e custo — como a cota do corretor.
create or replace function public.radar_polimento_segundos_mes() returns numeric
language sql stable set search_path = public as $$
  select coalesce(sum(u.segundos), 0) from public.radar_polimento_uso u
   where u.status = 'ok'
     and u.criado_em >= (date_trunc('month', now() at time zone 'America/Sao_Paulo') at time zone 'America/Sao_Paulo')
$$;
create or replace function public.radar_polimento_limite_s() returns numeric
language sql stable set search_path = public as $$
  select 60 * public.radar_polimento_cfg_num('limite_min_mes', 30, 1, 600)
$$;
create or replace function public.radar_polimento_custo_mes_brl() returns numeric
language sql stable set search_path = public as $$
  select coalesce(sum(u.custo_brl), 0) from public.radar_polimento_uso u
   where u.criado_em >= (date_trunc('month', now() at time zone 'America/Sao_Paulo') at time zone 'America/Sao_Paulo')
$$;

-- 5) A cota para a tela (só editor/admin): ligado, segundos usados, limite e custo do mês em R$.
create or replace function public.radar_polimento_cota() returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR310: só o editor ou o administrador usa o polimento' using errcode = '42501';
  end if;
  return jsonb_build_object(
    'ligado',        public.radar_polimento_ligado(),
    'segundos_mes',  public.radar_polimento_segundos_mes(),
    'limite_s',      public.radar_polimento_limite_s(),
    'custo_mes_brl', public.radar_polimento_custo_mes_brl(),
    'aviso_pct',     public.radar_polimento_cfg_num('aviso_pct', 80, 50, 100));
end $$;

-- 6) Registrar o uso (chamado pela Edge Function radar-polir, como service_role, depois de cada API). Calcula o
-- custo pelo preço por minuto da config. Não trava aqui — a trava de cota é conferida ANTES de chamar a API.
create or replace function public.radar_polimento_registrar(p_peca bigint, p_provedor text, p_segundos numeric,
                                                            p_status text default 'ok', p_erro text default null) returns bigint
language plpgsql security definer set search_path = public as $$
declare
  v_preco numeric := case p_provedor
                       when 'cleanvoice' then public.radar_polimento_cfg_num('preco_cleanvoice_usd_min', 0.0367, 0, 10)
                       when 'assemblyai' then public.radar_polimento_cfg_num('preco_assemblyai_usd_min', 0.0025, 0, 10)
                       else 0 end;
  v_usd numeric := round((coalesce(p_segundos, 0) / 60.0) * v_preco, 4);
  v_brl numeric := round(v_usd * public.radar_polimento_cfg_num('usd_brl', 5.34, 1, 20), 2);
  v_id  bigint;
begin
  if p_provedor not in ('cleanvoice','assemblyai') then
    raise exception 'RADAR311: provedor de polimento inválido (%).', p_provedor using errcode = '22023';
  end if;
  insert into public.radar_polimento_uso (peca_id, provedor, segundos, custo_usd, custo_brl, status, erro)
  values (p_peca, p_provedor, coalesce(p_segundos, 0), v_usd, v_brl, coalesce(p_status, 'ok'), left(p_erro, 500))
  returning id into v_id;
  return v_id;
end $$;

-- 7) Segurança: como as demais tabelas do Radar, nada fica exposto ao anon/público. A leitura é só do editor/admin (RLS) e o registro é
-- feito pela função (service_role). A tabela e a SEQUÊNCIA da identity são revogadas; a tela lê a cota como o usuário logado.
alter table public.radar_polimento_uso enable row level security;
revoke all on public.radar_polimento_uso from public, anon, authenticated, service_role;
revoke all on sequence public.radar_polimento_uso_id_seq from public, anon, authenticated, service_role;
drop policy if exists radar_polimento_uso_sel on public.radar_polimento_uso;
create policy radar_polimento_uso_sel on public.radar_polimento_uso for select
  using (coalesce(public.radar_papel(), '') in ('admin','editor'));

revoke all on function public.radar_polimento_cfg_num(text, numeric, numeric, numeric) from public, anon, authenticated, service_role;
revoke all on function public.radar_polimento_ligado() from public, anon, authenticated, service_role;
revoke all on function public.radar_polimento_segundos_mes() from public, anon, authenticated, service_role;
revoke all on function public.radar_polimento_limite_s() from public, anon, authenticated, service_role;
revoke all on function public.radar_polimento_custo_mes_brl() from public, anon, authenticated, service_role;
revoke all on function public.radar_polimento_cota() from public, anon, authenticated, service_role;
revoke all on function public.radar_polimento_registrar(bigint, text, numeric, text, text) from public, anon, authenticated, service_role;
grant select on public.radar_polimento_uso to authenticated;
grant execute on function public.radar_polimento_cota() to authenticated;
grant execute on function public.radar_polimento_registrar(bigint, text, numeric, text, text) to service_role;
