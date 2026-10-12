-- =====================================================================
-- Radar Artecon v0.21.0 — agenda que publica a Pauta aprovada (rodar no Supabase → SQL Editor, DEPOIS do radar-setup-v0.21.0.sql)
--
-- Obrigatório para a publicação automática da Pauta (fica fora do setup, como a agenda da ITC). Liga o pg_cron (como na página
-- "Install pg_cron" do Supabase) e o pg_net, cria no Vault a chave que só a agenda conhece ('radar_redes_agenda') e agenda, de 5
-- em 5 minutos, a chamada da função radar-redes para cada peça aprovada cuja hora chegou. Quem decide o que sai é o banco
-- (radar_agenda_vencidas e radar_pauta_pode_sair, no setup); o cron só chama. Sem nada vencido, nenhum pedido sai.
-- Pode rodar de novo: a chave existente é mantida e a agenda é refeita.
--
-- A radar-redes continua com "Verify JWT" LIGADO: a agenda manda no Authorization a chave anon, que é pública (a mesma de
-- radar-config.js; o teste do repositório confere que são iguais e este arquivo recusa qualquer chave que não seja a anon).
-- Pausa sem SQL: Configurações → Pauta → "agenda_ligada": false. Para desfazer: sql/radar-redes-agenda-reversao.sql.
-- Troque o endereço abaixo se o projeto do Supabase for outro.
-- =====================================================================
create extension if not exists pg_cron with schema pg_catalog;      -- como na página "Install pg_cron" do Supabase
grant usage on schema cron to postgres;
grant all privileges on all tables in schema cron to postgres;
create extension if not exists pg_net;                               -- já instalada no projeto (0.20.4): não muda nada

do $$
begin
  if to_regprocedure('public.radar_agenda_vencidas(integer)') is null then
    raise exception 'Rode antes o radar-setup-v0.21.0.sql (Supabase → SQL Editor).';
  end if;
  if not exists (select 1 from vault.secrets where name = 'radar_redes_agenda') then
    perform vault.create_secret(replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''), 'radar_redes_agenda',
                                'Chave da agenda que publica a Pauta aprovada (Radar Artecon)');
  end if;
end $$;

do $$
declare
  v_url  constant text := 'https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-redes';
  -- a MESMA chave pública de radar-config.js (SUPABASE_ANON_KEY); o teste confere que são iguais
  v_anon constant text := 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpoeGxzdnp2cXZ1Znloa2pubWVxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTA5NjA0NzgsImV4cCI6MjEwNjUzNjQ3OH0.CbzVS3-ig73XOMyvbDaeII8Q4V2m1MjR6wIP62cl2eI';
  v_p text := split_part(v_anon, '.', 2);
  v_cmd text;
begin
  -- nunca a chave secreta: só um JWT com "role": "anon"
  v_p := rpad(translate(v_p, '-_', '+/'), ((length(v_p) + 3) / 4) * 4, '=');
  if v_anon like 'sb_secret_%' or v_anon !~ '^eyJ'
     or coalesce(convert_from(decode(v_p, 'base64'), 'UTF8')::jsonb ->> 'role', '') <> 'anon' then
    raise exception 'A chave escrita neste arquivo não é a chave anon (pública). Nada foi agendado.';
  end if;
  -- a chave da agenda é lida do Vault na hora (como radar-itc-agenda.sql): não fica gravada em cron.job.
  -- radar_agenda_vencidas marca a tentativa e devolve só o que venceu (nenhuma linha = nenhum pedido)
  v_cmd := format($c$select net.http_post(url := %L,
      body := jsonb_build_object('acao', 'publicar', 'envio', v.id),
      headers := jsonb_build_object('Content-Type', 'application/json', 'Authorization', %L,
                   'x-radar-agenda', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_redes_agenda')),
      timeout_milliseconds := 150000)
    from public.radar_agenda_vencidas(2) as v(id)$c$, v_url, 'Bearer ' || v_anon);
  perform cron.unschedule(j.jobid) from cron.job j where j.jobname like 'radar-redes-agenda%';
  perform cron.schedule('radar-redes-agenda', '*/5 * * * *', v_cmd);          -- 09:30 cai numa rodada
  -- cron.job_run_details não é limpo sozinho (a página do Supabase não fala disso): guarda 7 dias
  perform cron.schedule('radar-redes-agenda-limpeza', '41 6 * * *',
    $c$delete from cron.job_run_details where end_time < now() - interval '7 days'
         and jobid in (select jobid from cron.job where jobname like 'radar-%')$c$);
end $$;

select jobname, schedule, active from cron.job where jobname like 'radar-redes-agenda%';

-- ---------------------------------------------------------------------
-- Teste (não publica nada), rodar à parte depois de instalar a radar-redes v0.21.0:
--
--   select net.http_post(url := 'https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-redes',
--     body := '{"acao":"agenda_teste"}'::jsonb,
--     headers := jsonb_build_object('Content-Type','application/json','Authorization','Bearer <a chave anon acima>',
--       'x-radar-agenda', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_redes_agenda')));
--
-- Depois de alguns segundos (esperado: 200 {"ok":true,...}):
--
--   select status_code, content from net._http_response order by id desc limit 1;
--
-- As últimas rodadas da agenda: select status, return_message, start_time from cron.job_run_details
--   where jobid = (select jobid from cron.job where jobname = 'radar-redes-agenda') order by start_time desc limit 5;
-- ---------------------------------------------------------------------
