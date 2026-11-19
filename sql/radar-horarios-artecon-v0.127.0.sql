-- Radar Artecon — migração v0.127.0: melhores horários da Artecon (dashboard)
--
-- radar_horarios_artecon(p_dias) lê as publicações da CONTA PRÓPRIA da Artecon já coletadas pela aba Setor
-- (radar_setor_posts, via Business Discovery da Meta) e devolve, por dia da semana e hora (fuso de Brasília),
-- o engajamento médio ((curtidas + comentários) ÷ seguidores) e as interações médias — além dos melhores horários.
-- Só leitura, para a equipe. Não precisa de coletor novo nem cron: reaproveita a coleta semanal do Setor.
-- Pode rodar quantas vezes quiser (create or replace). O mesmo conteúdo está no sql/radar-setup-v0.50.0.sql.

create or replace function public.radar_horarios_artecon(p_dias int default 180) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  v_dias int := greatest(14, least(400, coalesce(p_dias, 180)));
  v_res  jsonb;
begin
  if coalesce(public.radar_papel(), '') = '' then
    raise exception 'RADAR383: seu perfil não vê o painel de horários' using errcode = '42501';
  end if;
  with base as (
    select extract(dow  from p.publicado_em at time zone 'America/Sao_Paulo')::int as dia_semana,  -- 0 = domingo
           extract(hour from p.publicado_em at time zone 'America/Sao_Paulo')::int as hora,
           p.formato,
           (coalesce(p.curtidas, 0) + coalesce(p.comentarios, 0))::numeric / nullif(p.seguidores, 0) as engajamento,
           (coalesce(p.curtidas, 0) + coalesce(p.comentarios, 0))                                    as interacoes
      from public.radar_setor_posts p
      join public.radar_setor_contas c on c.id = p.conta_id
     where c.propria                                           -- só a conta da Artecon
       and p.curtidas is not null                              -- curtidas ocultas pelo dono ficam de fora
       and p.publicado_em >= now() - make_interval(days => v_dias)
  ),
  baldes as (
    select dia_semana, hora, count(*)::int as posts,
           round(avg(engajamento)::numeric, 4) as engajamento_medio,
           round(avg(interacoes)::numeric, 1)  as interacoes_media
      from base group by 1, 2
  )
  select jsonb_build_object(
    'total_posts', (select count(*) from base),
    'dias', v_dias,
    'por_hora', coalesce((select jsonb_agg(jsonb_build_object(
        'dia_semana', dia_semana, 'hora', hora, 'posts', posts,
        'engajamento_medio', engajamento_medio, 'interacoes_media', interacoes_media) order by dia_semana, hora) from baldes), '[]'::jsonb),
    'melhores', coalesce((select jsonb_agg(jsonb_build_object(
        'dia_semana', dia_semana, 'hora', hora, 'posts', posts, 'engajamento_medio', engajamento_medio) order by engajamento_medio desc, posts desc)
        from (select * from baldes where posts >= 2 order by engajamento_medio desc, posts desc limit 10) t), '[]'::jsonb),
    'por_formato', coalesce((select jsonb_agg(jsonb_build_object(
        'formato', formato, 'posts', posts, 'engajamento_medio', eng) order by eng desc nulls last)
        from (select formato, count(*)::int as posts, round(avg(engajamento)::numeric, 4) as eng from base group by formato) g), '[]'::jsonb)
  ) into v_res;
  return v_res;
end $$;
revoke all on function public.radar_horarios_artecon(int) from public, anon, authenticated, service_role;
grant execute on function public.radar_horarios_artecon(int) to authenticated;
