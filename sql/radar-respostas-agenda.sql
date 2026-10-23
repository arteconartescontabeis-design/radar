-- =====================================================================
-- Radar Artecon v0.35.0 — a fila do Módulo Respostas Automáticas (rodar no Supabase → SQL Editor, DEPOIS do radar-setup-v0.35.0.sql)
--
-- O comentário que passa do limite por hora do gatilho fica PENDENTE. Esta agenda olha a fila a cada 5 minutos e, SÓ quando há o
-- que mandar (radar_respostas_ha_pendentes: pendente de gatilho ativo, com o interruptor geral ligado), chama a função
-- radar-meta-webhook (ação "pendentes"), que envia dentro da folga do limite. Sem pendente, nenhum pedido sai.
--
-- Mesma proteção das outras agendas: a chave mora no Vault ('radar_respostas', criada aqui na primeira rodada), é lida na hora
-- (nunca fica gravada em cron.job) e quem confere é o banco (radar_respostas_conferir, que só a chave interna executa). Sem chave
-- anon neste arquivo: a radar-meta-webhook fica com o "Verify JWT" DESLIGADO (a Meta não manda JWT; a função confere a assinatura
-- da Meta e a chave sozinha).
-- Pode rodar de novo: a agenda é refeita e a chave do Vault não muda.
-- Pausa sem SQL: aba Respostas → interruptor "Pausar todas as respostas". Para desfazer: sql/radar-respostas-agenda-reversao.sql.
-- Troque o endereço abaixo se o projeto do Supabase for outro.
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
  if to_regprocedure('public.radar_respostas_ha_pendentes()') is null then
    raise exception 'Rode antes o radar-setup-v0.35.0.sql desta versão (Supabase → SQL Editor). Nada foi agendado.';
  end if;
end $$;

-- a chave da agenda, no Vault (só na primeira rodada; para zerar: delete from vault.secrets where name = 'radar_respostas')
do $$
begin
  if not exists (select 1 from vault.secrets where name = 'radar_respostas') then
    perform vault.create_secret(replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''), 'radar_respostas',
                                'Chave da agenda do Módulo Respostas Automáticas (Radar Artecon)');
  end if;
end $$;

-- quem confere a chave é o banco; só a chave interna (a função radar-meta-webhook) executa
create or replace function public.radar_respostas_conferir(p_chave text) returns boolean
language plpgsql stable security definer set search_path = public as $$
declare v_certa text;
begin
  if length(coalesce(p_chave, '')) < 32 then return false; end if;
  execute 'select decrypted_secret from vault.decrypted_secrets where name = ''radar_respostas'' limit 1' into v_certa;
  return v_certa is not null and length(v_certa) >= 32 and v_certa = p_chave;
exception when others then
  return false;
end $$;
do $$
begin
  execute 'revoke all on function public.radar_respostas_conferir(text) from public, anon, authenticated';
  execute 'grant execute on function public.radar_respostas_conferir(text) to service_role';
end $$;

do $$
declare
  v_url constant text := 'https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-meta-webhook';
begin
  perform cron.unschedule(j.jobid) from cron.job j where j.jobname like 'radar-respostas%';
  -- a cada 5 minutos; sem pendente com folga, o "where" não deixa sair pedido nenhum
  perform cron.schedule('radar-respostas-fila', '*/5 * * * *', format($c$select net.http_post(url := %L,
      body := '{"acao": "pendentes"}'::jsonb,
      headers := jsonb_build_object('Content-Type', 'application/json',
                   'x-radar-chave', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_respostas')),
      timeout_milliseconds := 150000)
    where public.radar_respostas_ha_pendentes()$c$, v_url));
end $$;

select jobname, schedule, active from cron.job where jobname like 'radar-respostas%';

-- ---------------------------------------------------------------------
-- Teste (não toca na Meta), rodar à parte depois do Deploy da radar-meta-webhook. Copie as 4 linhas do select para uma consulta
-- nova SEM os "--" do começo (no SQL Editor, selecione e aperte Ctrl+/) e execute; não há nada para trocar (a chave vem do Vault):
--
--   select net.http_post(url := 'https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-meta-webhook',
--     body := '{"acao": "agenda_teste"}'::jsonb,
--     headers := jsonb_build_object('Content-Type', 'application/json',
--                  'x-radar-chave', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_respostas')));
--
-- Depois de alguns segundos (esperado: 200 {"ok":true,"versao":"0.35.1"}; 401 "Chave não confere." = este arquivo não foi rodado
-- neste projeto; 404 = a função radar-meta-webhook não está instalada: faça o Deploy do index.ts desta versão):
--
--   select status_code, content from net._http_response order by id desc limit 1;
--
-- As últimas rodadas: select status, return_message, start_time from cron.job_run_details
--   where jobid = (select jobid from cron.job where jobname = 'radar-respostas-fila') order by start_time desc limit 5;
-- A limpeza do cron.job_run_details já é feita pela radar-redes-agenda-limpeza (todos os "radar-%").
-- ---------------------------------------------------------------------
