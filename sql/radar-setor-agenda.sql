-- =====================================================================
-- Radar Artecon v0.34.0 — leitura automática da aba Setor (rodar no Supabase → SQL Editor, DEPOIS do radar-setup-v0.34.0.sql)
--
-- Toda segunda-feira, a partir das 04:00 de Brasília, o Radar lê sozinho cada conta dos setores da aba Setor uma vez, pela função
-- radar-concorrentes (só leitura na API oficial da Meta, Business Discovery: nunca publica, comenta, curte ou segue). O pg_cron chama
-- de hora em hora (aos 17 minutos), mas o pedido só sai quando o banco diz que há conta devida (radar_setor_ha_devidas: leitura
-- automática ligada, sem pausa da Meta, sem rodada em andamento); cada chamada lê até 12 contas, com pausa entre elas. Com 60 contas,
-- são umas 5 rodadas na segunda de manhã (04:17, 05:17, ...): de 60 a 70 chamadas à Meta por semana, nunca mais de 15 por hora.
-- E, uma vez por dia (03:43 de Brasília), a guarda dos 400 dias (radar-setor-guarda): apaga a publicação guardada com mais de 400 dias
-- de qualquer conta — também da pausada, da que parou de ser lida e da de setor inativo (sem chamar a função nem a Meta).
--
-- Mesma proteção das outras agendas: a chave mora no Vault, é lida na hora (nunca fica gravada em cron.job) e quem confere é o banco.
-- É a chave do sql/radar-concorrentes.sql ('radar_concorrentes', conferida por radar_concorrentes_conferir): rode aquele arquivo antes,
-- se nunca rodou. Sem chave anon neste arquivo: a radar-concorrentes fica com o "Verify JWT" DESLIGADO (ela confere a chave sozinha).
-- Pode rodar de novo: a agenda é refeita.
-- Pausa sem SQL: aba Setor → Configuração → desmarque "Leitura automática toda segunda-feira". Para desfazer:
-- sql/radar-setor-agenda-reversao.sql. Troque o endereço abaixo se o projeto do Supabase for outro.
-- =====================================================================
-- o pg_cron (com os grants da página "Install pg_cron" do Supabase) e o pg_net só entram quando a extensão ainda não existe (com ela
-- instalada, os grants de novo disparariam o gatilho da Supabase e a 2ª rodada pararia em "dependent privileges exist")
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
  if to_regprocedure('public.radar_setor_ha_devidas()') is null then
    raise exception 'Rode antes o radar-setup-v0.34.0.sql desta versão (Supabase → SQL Editor). Nada foi agendado.';
  end if;
  if to_regprocedure('public.radar_concorrentes_conferir(text)') is null
     or not exists (select 1 from vault.secrets where name = 'radar_concorrentes') then
    raise exception 'Rode antes o sql/radar-concorrentes.sql (a chave da função radar-concorrentes). Nada foi agendado.';
  end if;
end $$;

do $$
declare
  v_url constant text := 'https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-concorrentes';
begin
  perform cron.unschedule(j.jobid) from cron.job j where j.jobname like 'radar-setor%';
  -- o horário do pg_cron é UTC: 17 minutos depois de cada hora (a segunda-feira, 04:00 de Brasília, é 07:00 UTC; a 1ª rodada é 07:17).
  -- Sem conta devida, o "where" não deixa sair pedido nenhum
  perform cron.schedule('radar-setor-coleta', '17 * * * *', format($c$select net.http_post(url := %L,
      body := '{"acao": "setor_coletar"}'::jsonb,
      headers := jsonb_build_object('Content-Type', 'application/json',
                   'x-radar-chave', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_concorrentes')),
      timeout_milliseconds := 150000)
    where public.radar_setor_ha_devidas()$c$, v_url));
  -- a guarda dos 400 dias, todo dia às 06:43 UTC (03:43 de Brasília), só no banco
  perform cron.schedule('radar-setor-guarda', '43 6 * * *', 'select public.radar_setor_guardar_em(now())');
end $$;

select jobname, schedule, active from cron.job where jobname like 'radar-setor%';

-- ---------------------------------------------------------------------
-- Teste (não lê o Instagram), rodar à parte depois de instalar a radar-concorrentes desta versão. Copie as 4 linhas do select para
-- uma consulta nova SEM os "--" do começo (no SQL Editor, selecione e aperte Ctrl+/) e execute; não há nada para trocar (a chave vem
-- do Vault):
--
--   select net.http_post(url := 'https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-concorrentes',
--     body := '{"acao": "setor_teste"}'::jsonb,
--     headers := jsonb_build_object('Content-Type', 'application/json',
--                  'x-radar-chave', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_concorrentes')));
--
-- Depois de alguns segundos (esperado: 200 {"ok":true,"versao":"0.34.0"}; 401 "Chave não confere." = o sql/radar-concorrentes.sql não
-- foi rodado neste projeto; 404 = a função radar-concorrentes não está instalada; 400 "Ação desconhecida." = a função instalada é de
-- uma versão anterior: faça o Deploy do index.ts desta versão):
--
--   select status_code, content from net._http_response order by id desc limit 1;
--
-- As últimas rodadas: select status, return_message, start_time from cron.job_run_details
--   where jobid = (select jobid from cron.job where jobname = 'radar-setor-coleta') order by start_time desc limit 5;
-- A limpeza do cron.job_run_details já é feita pela radar-redes-agenda-limpeza (todos os "radar-%").
-- ---------------------------------------------------------------------
