-- =====================================================================
-- Radar Artecon v0.32.0 — desfaz o sql/radar-copia-agenda.sql (rodar no Supabase → SQL Editor)
--
-- Tira os três agendamentos da cópia mensal no OneDrive (radar-copia, radar-copia-de-novo e radar-copia-dia-2) e confere que não
-- sobrou nenhum. Sem a agenda, a cópia só sai pelo botão "Fazer a cópia agora" (Configurações → Cópia de segurança no OneDrive), e o
-- lembrete da cópia do mês avisa no dia 2 (desligue com "copia": false em Configurações → Lembretes por e-mail). Pode rodar mais de uma vez.
-- =====================================================================
do $$
begin
  if not exists (select 1 from pg_namespace where nspname = 'cron') then
    raise notice 'O pg_cron não está instalado: não há agenda da cópia para tirar.';
    return;
  end if;
  perform cron.unschedule(j.jobid) from cron.job j where j.jobname like 'radar-copia%';
  if exists (select 1 from cron.job where jobname like 'radar-copia%') then
    raise notice 'Sobrou agendamento da cópia no pg_cron: confira cron.job';
  else
    raise notice 'Agenda da cópia retirada.';
  end if;
end $$;

-- Fica de pé, de propósito:
--   * as extensões pg_cron e pg_net (as outras agendas também usam);
--   * a chave 'radar_copia_agenda' no Vault (rodar o sql/radar-copia-agenda.sql de novo reaproveita a mesma). Para apagar à mão:
--       delete from vault.secrets where name = 'radar_copia_agenda';
-- Para só pausar sem SQL: não há (a cópia é mensal). Para cortar o acesso ao OneDrive na hora: entra.microsoft.com → Registros de
-- aplicativo → apague "Radar Artecon — cópias de segurança". Os arquivos no OneDrive ficam (o Radar nunca apaga cópias).
