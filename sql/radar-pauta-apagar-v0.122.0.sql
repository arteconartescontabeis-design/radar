-- Radar Artecon — migração v0.122.0: apagar peça da Pauta (só o administrador)
--
-- Acrescenta a função radar_pauta_apagar(bigint). Tira a peça do calendário de vez,
-- com os vídeos (e os clipes deles, por cascata) e os envios de rede ainda NÃO
-- publicados. A peça que já foi (ou está sendo) publicada numa rede não é apagada —
-- o histórico fica: nela, use "Cancelar a peça". Diferente de Cancelar, que mantém a
-- peça no calendário como cancelada.
--
-- Pode rodar quantas vezes quiser (create or replace). O conteúdo é o mesmo que já
-- está no sql/radar-setup-v0.50.0.sql; esta migração é só para aplicar em bases que
-- já existem, sem rodar o setup inteiro.

create or replace function public.radar_pauta_apagar(p_id bigint) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  p public.radar_pauta_pecas%rowtype;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR360: só o administrador apaga uma peça da Pauta' using errcode = '42501';
  end if;
  select * into p from public.radar_pauta_pecas where id = p_id for update;
  if p.id is null then
    raise exception 'RADAR361: peça não encontrada (atualize a página)' using errcode = 'P0001';
  end if;
  if p.publicado_manual_em is not null
     or exists (select 1 from public.radar_redes_envios e where e.peca_id = p.id and e.situacao in ('publicado','enviando')) then
    raise exception 'RADAR362: esta peça já foi (ou está sendo) publicada numa rede — para tirar do calendário sem apagar o histórico, use "Cancelar a peça"' using errcode = 'P0001';
  end if;
  update public.radar_pauta_pecas set video_id = null where id = p.id;    -- solta a referência antes de apagar o vídeo
  delete from public.radar_videos where peca_id = p.id;                    -- os clipes vão junto (on delete cascade)
  delete from public.radar_redes_envios where peca_id = p.id;              -- só sobram os não publicados (os publicados barram acima)
  delete from public.radar_pauta_pecas where id = p.id;                    -- a trilha (radar_auditoria) guarda o DELETE
  return jsonb_build_object('apagada', true, 'id', p.id, 'data', p.data, 'tipo', p.tipo);
end $$;
revoke all on function public.radar_pauta_apagar(bigint) from public, anon, authenticated, service_role;
grant execute on function public.radar_pauta_apagar(bigint) to authenticated;
