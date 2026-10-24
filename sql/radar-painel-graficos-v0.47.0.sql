-- =====================================================================
-- Radar Artecon v0.47.0 — Painel com gráficos (dados)
-- (rodar no Supabase → SQL Editor, DEPOIS do radar-setup-v0.46.0.sql; pode rodar de novo)
--
-- Uma função só devolve, em JSON, o que os gráficos novos do Painel precisam e que ainda não existia:
--   • notícias (capturas) por FONTE, nos três períodos (dia, semana, mês);
--   • publicações por CANAL (site, Instagram, Facebook), semana a semana, nas últimas 6 semanas;
--   • a COMPARAÇÃO com os outros escritórios (ritmo de publicações: a conta própria × a média das demais
--     contas do Setor), nas últimas 6 semanas — só quando a aba Setor tem a conta própria e ao menos uma outra;
--     senão vem nula (o Painel mostra "configure a aba Setor").
-- O cronograma (o que falta por período), a cota do corretor de vídeo e os números de cabeçalho o Painel já
-- tira do que existe (a projeção v0.41.0, radar_video_cota e radar_v_painel). Esta função só LÊ; nada grava.
-- =====================================================================

create or replace function public.radar_painel_graficos(p_hoje date default null) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  v_hoje date := coalesce(p_hoje, public.radar_pauta_hoje());
  v_seg  date := date_trunc('week', v_hoje::timestamp)::date;                               -- segunda desta semana
  v_mes  date := date_trunc('month', v_hoje::timestamp)::date;
  v_mesf date := (date_trunc('month', v_hoje::timestamp) + interval '1 month - 1 day')::date;
  v_w0   date := date_trunc('week', v_hoje::timestamp)::date - 35;                           -- segunda de 5 semanas atrás (6 no total)
  v_fontes jsonb;
  v_canais jsonb;
  v_comp   jsonb;
begin
  if auth.uid() is null or public.radar_papel() is null then
    raise exception 'RADAR320: entre no Radar para ver o Painel.' using errcode = '42501';
  end if;

  -- 1) notícias (capturas, sem as duplicatas) por fonte, em cada período
  with cap as (
    select coalesce(f.nome, '(sem fonte)') as fonte, (c.capturado_em at time zone 'America/Sao_Paulo')::date as d
      from public.radar_capturas c left join public.radar_fontes f on f.id = c.fonte_id
     where c.duplicata_de is null
  ),
  por as (
    select periodo, fonte, count(*) as n from (
      select fonte, 'dia'    as periodo from cap where d = v_hoje
      union all select fonte, 'semana' from cap where d between v_seg and v_seg + 6
      union all select fonte, 'mes'    from cap where d between v_mes and v_mesf
    ) t group by periodo, fonte
  )
  select jsonb_object_agg(periodo, lst) into v_fontes from (
    select periodo, jsonb_agg(jsonb_build_object('fonte', fonte, 'n', n) order by n desc, fonte) as lst
      from por group by periodo
  ) q;

  -- 2) publicações por canal, semana a semana (6 semanas)
  with semanas as (select generate_series(v_w0, v_seg, interval '7 days')::date as ini),
  ig as (select date_trunc('week', (publicado_em at time zone 'America/Sao_Paulo'))::date as s, count(*) n
           from public.radar_redes_envios where canal = 'instagram' and publicado_em is not null group by 1),
  fb as (select date_trunc('week', (publicado_em at time zone 'America/Sao_Paulo'))::date as s, count(*) n
           from public.radar_redes_envios where canal = 'facebook'  and publicado_em is not null group by 1),
  st as (select date_trunc('week', publicado_em::timestamp)::date as s, count(*) n
           from public.radar_divulgacoes where publicado_em is not null group by 1)
  select jsonb_agg(jsonb_build_object('ini', s.ini, 'site', coalesce(st.n, 0),
           'instagram', coalesce(ig.n, 0), 'facebook', coalesce(fb.n, 0)) order by s.ini)
    into v_canais
    from semanas s left join ig on ig.s = s.ini left join fb on fb.s = s.ini left join st on st.s = s.ini;

  -- 3) comparação: a conta própria × a média das outras contas do Setor (ritmo de publicações), 6 semanas
  if exists (select 1 from public.radar_setor_contas where tipo = 'conta' and propria)
     and exists (select 1 from public.radar_setor_contas where tipo = 'conta' and not propria and ativa) then
    with semanas as (select generate_series(v_w0, v_seg, interval '7 days')::date as ini),
    posts as (
      select c.propria, date_trunc('week', (p.publicado_em at time zone 'America/Sao_Paulo'))::date as s
        from public.radar_setor_posts p join public.radar_setor_contas c on c.id = p.conta_id
       where c.tipo = 'conta' and p.publicado_em is not null
    ),
    art as (select s, count(*) n from posts where propria group by s),
    out1 as (select s, count(*)::numeric
               / nullif((select count(*) from public.radar_setor_contas where tipo = 'conta' and not propria and ativa), 0) as media
               from posts where not propria group by s)
    select jsonb_agg(jsonb_build_object('ini', s.ini, 'artecon', coalesce(art.n, 0),
             'media', round(coalesce(out1.media, 0), 1)) order by s.ini)
      into v_comp
      from semanas s left join art on art.s = s.ini left join out1 on out1.s = s.ini;
  end if;

  return jsonb_build_object('hoje', v_hoje, 'fontes', coalesce(v_fontes, '{}'::jsonb),
                            'canais', coalesce(v_canais, '[]'::jsonb), 'comparacao', v_comp);
end $$;

revoke all on function public.radar_painel_graficos(date) from public, anon;
grant execute on function public.radar_painel_graficos(date) to authenticated;

select 'v0.47.0 painel com gráficos (dados) — aplicado' as resultado;
