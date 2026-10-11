-- =====================================================================
-- Radar Artecon v0.19.1 — desfaz o sql/radar-concorrentes.sql (rodar no Supabase → SQL Editor)
--
-- Apaga só a função que confere a chave. Sem ela, toda chamada à função radar-concorrentes com o cabeçalho
-- x-radar-chave é recusada (401); o administrador logado continua podendo chamar.
-- Pode rodar mais de uma vez.
-- =====================================================================
begin;

drop function if exists public.radar_concorrentes_conferir(text);

commit;

-- Ficam de pé, de propósito:
--   * a extensão pg_net (a agenda da ITC, sql/radar-itc-agenda.sql, também usa);
--   * o segredo 'radar_concorrentes' no Vault (rodar o sql/radar-concorrentes.sql de novo reaproveita a mesma chave).
-- Para apagar o segredo à mão:
--   delete from vault.secrets where name = 'radar_concorrentes';
-- Para tirar a função do ar: Supabase → Edge Functions → radar-concorrentes → Delete function.
