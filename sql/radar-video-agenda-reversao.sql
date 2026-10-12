-- =====================================================================
-- Radar Artecon v0.22.0 — desfaz o sql/radar-video-agenda.sql (rodar no Supabase → SQL Editor)
--
-- Tira os dois agendamentos do corretor de vídeo (radar-video-reserva e radar-video-limpeza) e confere que não sobrou nenhum. Sem a
-- agenda, o robô é acionado só pela tela (no fim do envio e depois de um ajuste) e os arquivos não são apagados nos prazos de guarda
-- até a agenda voltar. Pode rodar mais de uma vez.
-- =====================================================================
do $$
begin
  if not exists (select 1 from pg_namespace where nspname = 'cron') then
    raise notice 'O pg_cron não está instalado: não há agenda do corretor de vídeo para tirar.';
    return;
  end if;
  perform cron.unschedule(j.jobid) from cron.job j where j.jobname like 'radar-video-%';
  if exists (select 1 from cron.job where jobname like 'radar-video-%') then
    raise notice 'Sobrou agendamento do corretor de vídeo no pg_cron: confira cron.job';
  else
    raise notice 'Agenda do corretor de vídeo retirada.';
  end if;
end $$;

-- Ficam de pé, de propósito:
--   * as extensões pg_cron e pg_net (as agendas da ITC e da Pauta também usam);
--   * os segredos 'radar_video_robo' e 'radar_video_agenda' no Vault (rodar o sql/radar-video-agenda.sql de novo reaproveita os mesmos;
--     a do robô é a do segredo RADAR_VIDEO_ROBO_CHAVE do repositório radar-video).
-- Para apagar à mão (o robô deixa de falar com a radar-video até um segredo novo ser copiado para o GitHub):
--   delete from vault.secrets where name in ('radar_video_robo', 'radar_video_agenda');
