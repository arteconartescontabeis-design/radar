-- =====================================================================
-- Radar Artecon v0.21.0 — desfaz o sql/radar-redes-agenda.sql (rodar no Supabase → SQL Editor)
--
-- Tira os dois agendamentos da Pauta (radar-redes-agenda e radar-redes-agenda-limpeza) e confere que não sobrou nenhum. Sem a
-- agenda, a peça aprovada para agendar espera: sai só pelo "Publicar agora" da Pauta. Pode rodar mais de uma vez.
-- Para só pausar, sem SQL: Configurações → Pauta → "agenda_ligada": false.
-- =====================================================================
do $$
begin
  if not exists (select 1 from pg_namespace where nspname = 'cron') then
    raise notice 'O pg_cron não está instalado: não há agenda da Pauta para tirar.';
    return;
  end if;
  perform cron.unschedule(j.jobid) from cron.job j where j.jobname like 'radar-redes-agenda%';
  if exists (select 1 from cron.job where jobname like 'radar-redes-agenda%') then
    raise notice 'Sobrou agendamento da Pauta no pg_cron: confira cron.job';
  else
    raise notice 'Agenda da Pauta retirada.';
  end if;
end $$;

-- Ficam de pé, de propósito:
--   * as extensões pg_cron e pg_net (a agenda da ITC, sql/radar-itc-agenda.sql, também usa);
--   * o segredo 'radar_redes_agenda' no Vault (rodar o sql/radar-redes-agenda.sql de novo reaproveita a mesma chave).
-- Para apagar o segredo à mão:
--   delete from vault.secrets where name = 'radar_redes_agenda';
