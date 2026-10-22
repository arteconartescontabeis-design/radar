-- =====================================================================
-- Radar Artecon v0.21.0 — agenda que publica a Pauta aprovada (rodar no Supabase → SQL Editor, DEPOIS do radar-setup-v0.21.0.sql)
--
-- Obrigatório para a publicação automática da Pauta (fica fora do setup, como a agenda da ITC). Liga o pg_cron (como na página
-- "Install pg_cron" do Supabase) e o pg_net, cria no Vault a chave que só a agenda conhece ('radar_redes_agenda') e agenda, de 5
-- em 5 minutos, a chamada da função radar-redes para cada peça aprovada cuja hora chegou. Quem decide o que sai é o banco
-- (radar_agenda_vencidas e radar_pauta_pode_sair, no setup); o cron só chama. Sem nada vencido, nenhum pedido sai.
-- v0.22.0 (rodada 2 da varredura geral): e, uma vez por dia (radar-redes-agenda-robos), pede à radar-redes ("manter_robos") que
-- religue os robôs agendados do GitHub (coleta, robô do site, resumo) que o GitHub desliga sozinho no repositório PÚBLICO depois de
-- 60 dias sem atividade (o GitHub não desliga o pg_cron). Precisa do segredo RADAR_GITHUB_TOKEN na radar-redes (o mesmo do
-- acionamento do robô do site); o desligado à mão fica desligado.
-- v0.29.0: e, de 15 em 15 minutos (radar-redes-agenda-lembretes), os lembretes por e-mail antes do dia. Quem decide é o banco
-- (radar_lembretes_acionar, do radar-setup-v0.29.0.sql: Configurações → Lembretes por e-mail, o horário e "no máximo um e-mail por tipo
-- por dia"); só quando há lembrete para mandar, pede à radar-redes ("acionar_lembretes") que acione o robô dos lembretes no GitHub
-- (workflow radar-lembretes.yml), com o mesmo segredo RADAR_GITHUB_TOKEN. Nada a lembrar = nenhum pedido. Desligar sem SQL:
-- Configurações → Lembretes por e-mail → "ligado": false.
-- Pode rodar de novo: a chave existente é mantida e a agenda é refeita (v0.23.0: também no Supabase, com as extensões já ligadas).
--
-- A radar-redes continua com "Verify JWT" LIGADO: a agenda manda no Authorization a chave anon, que é pública (a mesma de
-- radar-config.js; o teste do repositório confere que são iguais e este arquivo recusa qualquer chave que não seja a anon).
-- v0.22.0 (rodada 2): ou a chave pública nova (sb_publishable_…, a de radar-config.js depois da troca), que vai só no apikey; com
-- ela, a radar-redes fica com o "Verify JWT" DESLIGADO (LEIAME, "Chaves novas do Supabase").
-- v0.45.0: e, de 5 em 5 minutos (radar-redes-agenda-site), a publicação no SITE com hora marcada. Quem decide é o banco
-- (radar_site_agendada_devida, do radar-setup-v0.45.0.sql); só quando uma hora vence, pede à radar-redes ("acionar_site") que
-- acione o robô do site no GitHub, como o botão da tela. Nada vencido = nenhum pedido.
-- Pausa sem SQL: Configurações → Pauta → "agenda_ligada": false. Para desfazer: sql/radar-redes-agenda-reversao.sql.
-- Troque o endereço abaixo se o projeto do Supabase for outro.
-- =====================================================================
-- v0.23.0: o pg_cron (com os grants da página "Install pg_cron" do Supabase) e o pg_net só entram quando a extensão ainda não
-- existe. Com ela instalada, o "create extension" e os grants de novo disparavam o gatilho da Supabase (grant_pg_cron_access) e a
-- 2ª rodada parava em "ERROR: dependent privileges exist", antes de refazer a agenda.
do $$
begin
  if not exists (select 1 from pg_extension where extname = 'pg_cron') then
    execute 'create extension pg_cron with schema pg_catalog';       -- como na página "Install pg_cron" do Supabase
    execute 'grant usage on schema cron to postgres';
    execute 'grant all privileges on all tables in schema cron to postgres';
  end if;
  if not exists (select 1 from pg_extension where extname = 'pg_net') then
    execute 'create extension pg_net';                                -- já instalada no projeto (0.20.4): não muda nada
  end if;
end $$;

do $$
begin
  -- v0.29.0: e os lembretes (radar_lembretes_acionar); v0.45.0: e a hora marcada do site (radar_site_agendada_devida):
  -- o setup desta versão vem antes
  if to_regprocedure('public.radar_agenda_vencidas(integer)') is null or to_regprocedure('public.radar_lembretes_acionar()') is null
     or to_regprocedure('public.radar_site_agendada_devida()') is null then
    raise exception 'Rode antes o radar-setup-v0.45.0.sql (Supabase → SQL Editor).';
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
  -- v0.22.0 (rodada 2 da varredura geral): a chave pública nova (sb_publishable_…; o Supabase desliga a anon antiga até o fim de
  -- 2026) vai só no apikey: no Authorization o Supabase a recusa (não é JWT), e a função fica com o "Verify JWT" desligado (LEIAME,
  -- "Chaves novas do Supabase"). A anon antiga (JWT) continua no Authorization
  v_nova constant boolean := v_anon ~ '^sb_publishable_[A-Za-z0-9_-]{16,200}$';
  v_cab_nome  constant text := case when v_nova then 'apikey' else 'Authorization' end;
  v_cab_valor constant text := case when v_nova then v_anon else 'Bearer ' || v_anon end;
  v_cmd text;
begin
  -- nunca a chave secreta: só um JWT com "role": "anon" ou a pública nova
  v_p := rpad(translate(v_p, '-_', '+/'), ((length(v_p) + 3) / 4) * 4, '=');
  if not v_nova and (v_anon like 'sb_secret_%' or v_anon !~ '^eyJ'
     or coalesce(convert_from(decode(v_p, 'base64'), 'UTF8')::jsonb ->> 'role', '') <> 'anon') then
    raise exception 'A chave escrita neste arquivo não é a chave anon (pública). Nada foi agendado.';
  end if;
  -- a chave da agenda é lida do Vault na hora (como radar-itc-agenda.sql): não fica gravada em cron.job.
  -- radar_agenda_vencidas marca a tentativa e devolve só o que venceu (nenhuma linha = nenhum pedido)
  v_cmd := format($c$select net.http_post(url := %L,
      body := jsonb_build_object('acao', 'publicar', 'envio', v.id),
      headers := jsonb_build_object('Content-Type', 'application/json', %L, %L,
                   'x-radar-agenda', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_redes_agenda')),
      timeout_milliseconds := 150000)
    from public.radar_agenda_vencidas(2) as v(id)$c$, v_url, v_cab_nome, v_cab_valor);
  perform cron.unschedule(j.jobid) from cron.job j where j.jobname like 'radar-redes-agenda%';
  perform cron.schedule('radar-redes-agenda', '*/5 * * * *', v_cmd);          -- 09:30 cai numa rodada
  -- v0.22.0 (rodada 2): os robôs agendados do GitHub, uma vez por dia (05:13 de Brasília), com a mesma chave da agenda
  perform cron.schedule('radar-redes-agenda-robos', '13 8 * * *', format($c$select net.http_post(url := %L,
      body := '{"acao": "manter_robos"}'::jsonb,
      headers := jsonb_build_object('Content-Type', 'application/json', %L, %L,
                   'x-radar-agenda', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_redes_agenda')),
      timeout_milliseconds := 60000)$c$, v_url, v_cab_nome, v_cab_valor));
  -- v0.29.0: os lembretes por e-mail. O banco confere (radar_lembretes_acionar: Configurações → Lembretes por e-mail, o horário, "um por
  -- tipo por dia" e no máximo um pedido a cada 30 minutos); só então pede à radar-redes que acione o robô dos lembretes no GitHub
  -- (radar-lembretes.yml). Nada a lembrar = nenhum pedido
  perform cron.schedule('radar-redes-agenda-lembretes', '*/15 * * * *', format($c$select net.http_post(url := %L,
      body := '{"acao": "acionar_lembretes"}'::jsonb,
      headers := jsonb_build_object('Content-Type', 'application/json', %L, %L,
                   'x-radar-agenda', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_redes_agenda')),
      timeout_milliseconds := 60000) where public.radar_lembretes_acionar()$c$, v_url, v_cab_nome, v_cab_valor));
  -- v0.45.0: a publicação no SITE com hora marcada. O banco confere (radar_site_agendada_devida: envio autorizado com a hora
  -- vencida, avisado até 3 vezes, de 10 em 10 minutos); só então pede à radar-redes que acione o robô do site no GitHub
  -- (acionar_site, o mesmo acionamento do botão da tela). Nada vencido = nenhum pedido; sem o segredo RADAR_GITHUB_TOKEN, a
  -- rodada automática do robô (minutos 7, 22, 37 e 52) é a reserva
  perform cron.schedule('radar-redes-agenda-site', '*/5 * * * *', format($c$select net.http_post(url := %L,
      body := '{"acao": "acionar_site"}'::jsonb,
      headers := jsonb_build_object('Content-Type', 'application/json', %L, %L,
                   'x-radar-agenda', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_redes_agenda')),
      timeout_milliseconds := 60000) where public.radar_site_agendada_devida()$c$, v_url, v_cab_nome, v_cab_valor));
  -- cron.job_run_details não é limpo sozinho (a página do Supabase não fala disso): guarda 7 dias
  perform cron.schedule('radar-redes-agenda-limpeza', '41 6 * * *',
    $c$delete from cron.job_run_details where end_time < now() - interval '7 days'
         and jobid in (select jobid from cron.job where jobname like 'radar-%')$c$);
end $$;

select jobname, schedule, active from cron.job where jobname like 'radar-redes-agenda%';

-- ---------------------------------------------------------------------
-- Teste (não publica nada), rodar à parte depois de instalar a radar-redes v0.21.0. Copie as 5 linhas do select para uma consulta
-- nova SEM os "--" do começo (no SQL Editor, selecione e aperte Ctrl+/) e execute; não há nada para trocar: a chave anon vem do
-- próprio agendamento acima (cron.job) e a da agenda, do Vault.
--
--   select net.http_post(url := 'https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-redes',
--     body := '{"acao":"agenda_teste"}'::jsonb,
--     headers := (select jsonb_build_object('Content-Type', 'application/json', 'x-radar-agenda', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_redes_agenda'))
--       || case when j.c ~ 'Bearer ' then jsonb_build_object('Authorization', substring(j.c from '(Bearer [^'']+)')) else jsonb_build_object('apikey', substring(j.c from '(sb_publishable_[A-Za-z0-9_-]+)')) end
--       from (select command as c from cron.job where jobname = 'radar-redes-agenda') j));
--
-- Depois de alguns segundos (esperado: 200 {"ok":true,"versao":"0.29.0"}; 401 "Invalid JWT" = a chave anon do agendamento não é a
-- deste projeto: troque em v_anon e rode este arquivo de novo; com a chave nova, sb_publishable_…, 401 = a função ainda está com o
-- "Verify JWT" ligado):
--
--   select status_code, content from net._http_response order by id desc limit 1;
--
-- As últimas rodadas da agenda: select status, return_message, start_time from cron.job_run_details
--   where jobid = (select jobid from cron.job where jobname = 'radar-redes-agenda') order by start_time desc limit 5;
-- ---------------------------------------------------------------------
