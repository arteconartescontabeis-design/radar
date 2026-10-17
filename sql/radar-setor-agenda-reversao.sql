-- =====================================================================
-- Radar Artecon v0.34.0 — desfaz o sql/radar-setor-agenda.sql (rodar no Supabase → SQL Editor)
--
-- Tira a leitura automática da aba Setor (radar-setor-coleta) e a guarda diária dos 400 dias (radar-setor-guarda) e confere que não
-- sobrou nenhuma. Sem elas, as contas só são lidas pelo botão "Atualizar a análise" da aba Setor (e a guarda dos 400 dias roda só no
-- começo de cada leitura). Pode rodar mais de uma vez.
-- Para só pausar, sem SQL: aba Setor → Configuração → desmarque "Leitura automática toda segunda-feira".
-- =====================================================================
do $$
begin
  if not exists (select 1 from pg_namespace where nspname = 'cron') then
    raise notice 'O pg_cron não está instalado: não há leitura automática do setor para tirar.';
    return;
  end if;
  perform cron.unschedule(j.jobid) from cron.job j where j.jobname like 'radar-setor%';
  if exists (select 1 from cron.job where jobname like 'radar-setor%') then
    raise notice 'Sobrou agendamento do setor no pg_cron: confira cron.job';
  else
    raise notice 'Leitura automática do setor retirada.';
  end if;
end $$;

-- Ficam de pé, de propósito:
--   * as extensões pg_cron e pg_net (as outras agendas também usam);
--   * a chave 'radar_concorrentes' no Vault e a radar_concorrentes_conferir: são da função radar-concorrentes
--     (sql/radar-concorrentes.sql; para tirar, sql/radar-concorrentes-reversao.sql).
