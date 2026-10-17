-- =====================================================================
-- Radar Artecon v0.21.0 — desfaz o sql/radar-redes-agenda.sql (rodar no Supabase → SQL Editor)
--
-- Tira os agendamentos da Pauta (radar-redes-agenda, radar-redes-agenda-limpeza, v0.22.0, radar-redes-agenda-robos e, v0.29.0,
-- radar-redes-agenda-lembretes) e confere que não sobrou nenhum. Sem a agenda, a peça aprovada para agendar espera: sai só pelo
-- "Publicar agora" da Pauta; os robôs agendados do GitHub que ele desligar por inatividade só voltam com "Enable workflow"; e os
-- lembretes por e-mail saem só pela rodada de hora em hora do próprio workflow (radar-lembretes.yml), quando o GitHub roda. Pode rodar
-- mais de uma vez.
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
