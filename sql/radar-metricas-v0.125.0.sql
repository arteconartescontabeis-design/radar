-- Radar Artecon — migração v0.125.0: métricas das redes e melhores horários (dashboard)
--
-- Acrescenta:
--   * radar_metricas      — uma linha por publicação (envio) com o engajamento colhido da Meta (Instagram/Facebook).
--   * radar_metricas_gravar(jsonb) — o coletor (função radar-metricas, com a chave de serviço) grava/atualiza em lote.
--   * radar_v_horarios    — a visão por canal, dia da semana e hora (média de engajamento e alcance), no fuso de Brasília.
--   * radar_horarios_resumo(text, int) — o resumo que a tela usa: os baldes por hora e os melhores horários.
--
-- Só LEITURA para a equipe (a RLS confere o papel); quem grava é o coletor, pela função. Pode rodar quantas vezes quiser.
-- O mesmo conteúdo está no sql/radar-setup-v0.50.0.sql (instalações novas já vêm com ele).

create table if not exists public.radar_metricas (
  id                bigint generated always as identity primary key,
  envio_id          bigint references public.radar_redes_envios(id) on delete set null,
  canal             text        not null check (canal in ('instagram','facebook')),
  post_id           text        not null check (length(post_id) between 1 and 100),
  publicado_em      timestamptz not null,
  coletado_em       timestamptz not null default now(),
  alcance           integer     not null default 0 check (alcance between 0 and 2000000000),
  curtidas          integer     not null default 0 check (curtidas between 0 and 2000000000),
  comentarios       integer     not null default 0 check (comentarios between 0 and 2000000000),
  salvos            integer     not null default 0 check (salvos between 0 and 2000000000),
  compartilhamentos integer     not null default 0 check (compartilhamentos between 0 and 2000000000),
  engajamento       integer     not null default 0 check (engajamento between 0 and 2000000000),
  unique (canal, post_id)
);
create index if not exists radar_metricas_publicado_idx on public.radar_metricas (publicado_em desc);

alter table public.radar_metricas enable row level security;
revoke all on public.radar_metricas from public, anon, authenticated, service_role;
grant select on public.radar_metricas to authenticated;            -- a equipe lê (a RLS confere o papel); o coletor grava pela função
drop policy if exists radar_metricas_sel on public.radar_metricas;
create policy radar_metricas_sel on public.radar_metricas for select to authenticated
  using ((select public.radar_papel()) is not null);

-- O coletor grava em lote (upsert por canal+post_id). SECURITY DEFINER; só o service_role chama (grant abaixo).
create or replace function public.radar_metricas_gravar(p jsonb) returns integer
language plpgsql security definer set search_path = public as $$
declare v_n integer := 0; x jsonb;
begin
  if coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role', '') <> 'service_role' then
    raise exception 'RADAR380: só o coletor grava métricas' using errcode = '42501';
  end if;
  if jsonb_typeof(p) is distinct from 'array' then
    raise exception 'RADAR381: envie um array de métricas' using errcode = 'P0001';
  end if;
  for x in select * from jsonb_array_elements(p) loop
    if coalesce(x->>'canal', '') not in ('instagram','facebook') or coalesce(x->>'post_id', '') = ''
       or coalesce(x->>'publicado_em', '') = '' then
      continue;                                                    -- item inválido é pulado, nunca derruba o lote
    end if;
    insert into public.radar_metricas
      (envio_id, canal, post_id, publicado_em, coletado_em, alcance, curtidas, comentarios, salvos, compartilhamentos, engajamento)
    values (
      case when jsonb_typeof(x->'envio_id') = 'number' then (x->>'envio_id')::bigint end,
      x->>'canal', left(x->>'post_id', 100), (x->>'publicado_em')::timestamptz, now(),
      least(2000000000, greatest(0, coalesce((x->>'alcance')::int, 0))),
      least(2000000000, greatest(0, coalesce((x->>'curtidas')::int, 0))),
      least(2000000000, greatest(0, coalesce((x->>'comentarios')::int, 0))),
      least(2000000000, greatest(0, coalesce((x->>'salvos')::int, 0))),
      least(2000000000, greatest(0, coalesce((x->>'compartilhamentos')::int, 0))),
      least(2000000000, greatest(0, coalesce((x->>'engajamento')::int, 0))))
    on conflict (canal, post_id) do update set
      envio_id = coalesce(excluded.envio_id, public.radar_metricas.envio_id),
      publicado_em = excluded.publicado_em, coletado_em = now(),
      alcance = excluded.alcance, curtidas = excluded.curtidas, comentarios = excluded.comentarios,
      salvos = excluded.salvos, compartilhamentos = excluded.compartilhamentos, engajamento = excluded.engajamento;
    v_n := v_n + 1;
  end loop;
  return v_n;
end $$;
revoke all on function public.radar_metricas_gravar(jsonb) from public, anon, authenticated, service_role;
grant execute on function public.radar_metricas_gravar(jsonb) to service_role;

-- A visão por canal, dia da semana (0=domingo) e hora, no fuso de Brasília: média de engajamento e de alcance e nº de posts.
drop view if exists public.radar_v_horarios;
create view public.radar_v_horarios
with (security_invoker = true) as
select m.canal,
       extract(dow  from m.publicado_em at time zone 'America/Sao_Paulo')::int as dia_semana,
       extract(hour from m.publicado_em at time zone 'America/Sao_Paulo')::int as hora,
       count(*)::int                        as posts,
       round(avg(m.engajamento))::int       as engajamento_medio,
       round(avg(m.alcance))::int           as alcance_medio
  from public.radar_metricas m
 group by 1, 2, 3;
revoke all on public.radar_v_horarios from public, anon, authenticated, service_role;   -- o Supabase concede tudo por padrão às views novas
grant select on public.radar_v_horarios to authenticated;

-- O resumo que a tela usa: os baldes por hora (para os gráficos) e os melhores horários (ordenados por engajamento médio,
-- com ao menos 2 posts no balde para não premiar o acaso). p_canal nulo = os dois canais somados; p_dias = janela recente.
create or replace function public.radar_horarios_resumo(p_canal text default null, p_dias int default 90) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  v_dias int := greatest(7, least(730, coalesce(p_dias, 90)));
  v_canal text := case when p_canal in ('instagram','facebook') then p_canal end;
  v_res jsonb;
begin
  if coalesce(public.radar_papel(), '') = '' then
    raise exception 'RADAR382: seu perfil não vê o painel de horários' using errcode = '42501';
  end if;
  with base as (
    select extract(dow  from m.publicado_em at time zone 'America/Sao_Paulo')::int as dia_semana,
           extract(hour from m.publicado_em at time zone 'America/Sao_Paulo')::int as hora,
           m.engajamento, m.alcance
      from public.radar_metricas m
     where m.publicado_em >= now() - make_interval(days => v_dias)
       and (v_canal is null or m.canal = v_canal)
  ),
  baldes as (
    select dia_semana, hora, count(*)::int as posts,
           round(avg(engajamento))::int as engajamento_medio, round(avg(alcance))::int as alcance_medio
      from base group by 1, 2
  )
  select jsonb_build_object(
    'total_posts', (select count(*) from base),
    'dias', v_dias,
    'canal', coalesce(v_canal, 'ambos'),
    'por_hora', coalesce((select jsonb_agg(jsonb_build_object(
        'dia_semana', dia_semana, 'hora', hora, 'posts', posts,
        'engajamento_medio', engajamento_medio, 'alcance_medio', alcance_medio) order by dia_semana, hora) from baldes), '[]'::jsonb),
    'melhores', coalesce((select jsonb_agg(jsonb_build_object(
        'dia_semana', dia_semana, 'hora', hora, 'posts', posts, 'engajamento_medio', engajamento_medio) order by engajamento_medio desc, posts desc)
        from (select * from baldes where posts >= 2 order by engajamento_medio desc, posts desc limit 8) t), '[]'::jsonb)
  ) into v_res;
  return v_res;
end $$;
revoke all on function public.radar_horarios_resumo(text, int) from public, anon, authenticated, service_role;
grant execute on function public.radar_horarios_resumo(text, int) to authenticated;
