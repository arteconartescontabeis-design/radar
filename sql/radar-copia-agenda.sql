-- =====================================================================
-- Radar Artecon v0.32.0 — agenda da cópia mensal do banco no OneDrive (rodar no Supabase → SQL Editor, DEPOIS do
-- radar-setup-v0.32.0.sql)
--
-- Liga o pg_cron e o pg_net (só se faltarem), cria no Vault a chave que só a agenda conhece ('radar_copia_agenda', 64 caracteres
-- aleatórios, se ainda não existir; ninguém digita) e agenda a função radar-copia:
--   * radar-copia: dia 1 de cada mês, às 04h10 de Brasília (07h10 UTC);
--   * radar-copia-de-novo (05h10 do dia 1) e radar-copia-dia-2 (04h10 do dia 2): só se o mês ainda não tem cópia OK nem uma em
--     andamento (radar_copias_falta_mes, no setup). O dia 1 também confere: a cópia feita à mão na madrugada do dia 1 vale pelo mês.
-- A chave da agenda é lida do Vault a cada rodada (não fica gravada em cron.job). A radar-copia fica com "Verify JWT" DESLIGADO
-- (confere a chave no código, como a radar-itc). Sem a chave do Vault, a cópia nunca sai pela agenda. Pode rodar de novo: a chave
-- existente é mantida e a agenda é refeita. O histórico do pg_cron destes agendamentos é limpo pela radar-redes-agenda-limpeza.
-- Antes: a função radar-copia instalada e os segredos COPIA_* no Supabase (LEIAME). Para desfazer: sql/radar-copia-agenda-reversao.sql.
-- Troque o endereço abaixo se o projeto do Supabase for outro.
-- =====================================================================
-- as extensões só entram quando ainda não existem (com elas instaladas, o "create extension" e os grants de novo disparavam o gatilho
-- da Supabase, grant_pg_cron_access, e a 2ª rodada parava em "ERROR: dependent privileges exist")
do $$
begin
  if not exists (select 1 from pg_extension where extname = 'pg_cron') then
    execute 'create extension pg_cron with schema pg_catalog';       -- como na página "Install pg_cron" do Supabase
    execute 'grant usage on schema cron to postgres';
    execute 'grant all privileges on all tables in schema cron to postgres';
  end if;
  if not exists (select 1 from pg_extension where extname = 'pg_net') then
    execute 'create extension pg_net';
  end if;
end $$;

do $$
begin
  if to_regprocedure('public.radar_copias_falta_mes()') is null then
    raise exception 'Rode antes o radar-setup-v0.32.0.sql (Supabase → SQL Editor).';
  end if;
  if not exists (select 1 from vault.secrets where name = 'radar_copia_agenda') then
    perform vault.create_secret(replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''), 'radar_copia_agenda',
                                'Chave da agenda que chama a função radar-copia (Radar Artecon)');
  end if;
end $$;

do $$
declare
  v_url constant text := 'https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-copia';
  v_cmd text;
begin
  perform cron.unschedule(j.jobid) from cron.job j where j.jobname like 'radar-copia%';
  -- o pedido à radar-copia, com a chave da agenda lida do Vault na hora; nenhuma linha (o mês já tem cópia) = nenhum pedido
  v_cmd := format($c$select net.http_post(url := %L, body := '{"acao": "copiar"}'::jsonb,
      headers := jsonb_build_object('Content-Type', 'application/json',
                   'x-radar-agenda', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_copia_agenda')),
      timeout_milliseconds := 150000) where public.radar_copias_falta_mes()$c$, v_url);
  perform cron.schedule('radar-copia', '10 7 1 * *', v_cmd);              -- dia 1, 04h10 de Brasília
  perform cron.schedule('radar-copia-de-novo', '10 8 1 * *', v_cmd);      -- dia 1, 05h10, só sem cópia OK no mês
  perform cron.schedule('radar-copia-dia-2', '10 7 2 * *', v_cmd);        -- dia 2, 04h10, idem
end $$;

select jobname, schedule, active from cron.job where jobname like 'radar-copia%' order by jobname;

-- ---------------------------------------------------------------------
-- Teste (não copia nada), rodar à parte depois de instalar a função radar-copia. Copie as 3 linhas do select para uma consulta nova
-- SEM os "--" do começo (no SQL Editor, selecione e aperte Ctrl+/) e execute; não há nada para trocar.
--
--   select net.http_post(url := 'https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-copia',
--     body := '{"acao":"agenda_teste"}'::jsonb,
--     headers := jsonb_build_object('Content-Type', 'application/json', 'x-radar-agenda', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_copia_agenda')));
--
-- Depois de alguns segundos (esperado: 200 {"ok":true,"versao":"0.32.0"}; 401 = a função está com o "Verify JWT" ligado, ou a chave não
-- confere):
--
--   select status_code, content from net._http_response order by id desc limit 1;
--
-- As últimas rodadas: select j.jobname, d.status, d.return_message, d.start_time from cron.job_run_details d
--   join cron.job j on j.jobid = d.jobid where j.jobname like 'radar-copia%' order by d.start_time desc limit 5;
-- ---------------------------------------------------------------------
