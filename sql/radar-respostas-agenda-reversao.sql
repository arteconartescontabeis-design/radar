-- =====================================================================
-- Radar Artecon v0.35.0 — desfaz o sql/radar-respostas-agenda.sql (rodar no Supabase → SQL Editor)
--
-- Tira a agenda da fila das respostas automáticas (radar-respostas-fila) e confere que não sobrou nenhuma. Sem ela, os comentários
-- dentro do limite por hora continuam respondidos na hora (pelo webhook); só os PENDENTES deixam de sair sozinhos (saem pelo botão
-- da aba Respostas, ou quando a agenda voltar — lembrando a janela de 7 dias da Meta). Pode rodar mais de uma vez.
-- Para só pausar tudo, sem SQL: aba Respostas → "Pausar todas as respostas".
-- =====================================================================
do $$
begin
  if not exists (select 1 from pg_namespace where nspname = 'cron') then
    raise notice 'O pg_cron não está instalado: não há agenda das respostas para tirar.';
    return;
  end if;
  perform cron.unschedule(j.jobid) from cron.job j where j.jobname like 'radar-respostas%';
  if exists (select 1 from cron.job where jobname like 'radar-respostas%') then
    raise notice 'Sobrou agendamento das respostas no pg_cron: confira cron.job';
  else
    raise notice 'Agenda da fila das respostas retirada.';
  end if;
end $$;

-- Ficam de pé, de propósito:
--   * as extensões pg_cron e pg_net (as outras agendas também usam);
--   * a chave 'radar_respostas' no Vault e a radar_respostas_conferir (para zerar a chave:
--     delete from vault.secrets where name = 'radar_respostas');
--   * a função radar-meta-webhook e os segredos dela (para tirar: Supabase → Edge Functions; veja a reversão da versão).
