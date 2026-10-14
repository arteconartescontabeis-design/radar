-- =====================================================================
-- Radar Artecon v0.22.0 — agenda e chaves do corretor de vídeo dos reels (rodar no Supabase → SQL Editor, DEPOIS do
-- radar-setup-v0.22.0.sql)
--
-- Obrigatório para o corretor de vídeo (fica fora do setup, como as agendas da ITC e da Pauta). Liga o pg_cron (como na página
-- "Install pg_cron" do Supabase) e o pg_net e cria no Vault as duas chaves do corretor, com 64 caracteres aleatórios (se ainda não
-- existirem; ninguém digita):
--   * 'radar_video_robo': o token estreito do robô (repositório PRIVADO radar-video). Abra no Vault, revele e copie direto para o
--     GitHub (radar-video → Settings → Secrets and variables → Actions → segredo RADAR_VIDEO_ROBO_CHAVE), nunca pelo chat. Com ela o
--     robô fala só com a função radar-video (cabeçalho x-radar-video-robo): nenhuma chave do Supabase vai para o GitHub;
--   * 'radar_video_agenda': a desta agenda (cabeçalho x-radar-agenda), lida do Vault a cada rodada (não fica gravada em cron.job).
-- E agenda:
--   * radar-video-reserva, de 10 em 10 minutos: aciona o robô SÓ se há pedido na fila há 3 minutos ou mais (a tela já aciona na hora;
--     esta é a reserva, se o GitHub não atendeu) ou parado há mais de 20 minutos, e nunca enquanto o robô trabalha num pedido
--     (radar_video_reserva, no setup). Sem fila, nenhum pedido sai. No 3º acionamento da reserva sem o robô pegar o pedido (a chave do
--     robô ou as variáveis do repositório privado erradas, o token do GitHub vencido), o pedido vira erro "robo_nao_pegou" — um aviso
--     só, na peça — e a reserva para: nada de uma execução vermelha (e um e-mail do GitHub) a cada 10 minutos;
--   * radar-video-limpeza, todo dia às 03h37 de Brasília (06h37 UTC): apaga os arquivos e os textos nos prazos de guarda
--     (radar_video_limpeza, no setup) e guarda 7 dias do histórico do pg_cron.
-- Pode rodar de novo: as chaves existentes são mantidas e a agenda é refeita.
--
-- A radar-video fica com "Verify JWT" LIGADO: a agenda manda no Authorization a chave anon, que é pública (a mesma de radar-config.js;
-- o teste do repositório confere que são iguais e este arquivo recusa qualquer chave que não seja a anon). v0.22.0 (rodada 2): ou a
-- chave pública nova (sb_publishable_…, a de radar-config.js depois da troca), que vai só no apikey; com ela, a radar-video fica com o
-- "Verify JWT" DESLIGADO (LEIAME, "Chaves novas do Supabase").
-- Para desfazer: sql/radar-video-agenda-reversao.sql. Troque o endereço abaixo se o projeto do Supabase for outro.
-- =====================================================================
create extension if not exists pg_cron with schema pg_catalog;      -- como na página "Install pg_cron" do Supabase
grant usage on schema cron to postgres;
grant all privileges on all tables in schema cron to postgres;
create extension if not exists pg_net;                               -- já instalada no projeto (0.20.4): não muda nada

do $$
begin
  if to_regprocedure('public.radar_video_reserva()') is null then
    raise exception 'Rode antes o radar-setup-v0.22.0.sql (Supabase → SQL Editor).';
  end if;
  if not exists (select 1 from vault.secrets where name = 'radar_video_robo') then
    perform vault.create_secret(replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''), 'radar_video_robo',
                                'Token do robô do corretor de vídeo (Radar Artecon): copie para o segredo RADAR_VIDEO_ROBO_CHAVE do repositório radar-video');
  end if;
  if not exists (select 1 from vault.secrets where name = 'radar_video_agenda') then
    perform vault.create_secret(replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''), 'radar_video_agenda',
                                'Chave da agenda do corretor de vídeo (Radar Artecon)');
  end if;
end $$;

do $$
declare
  v_url  constant text := 'https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-video';
  -- a MESMA chave pública de radar-config.js (SUPABASE_ANON_KEY); o teste confere que são iguais
  v_anon constant text := 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpoeGxzdnp2cXZ1Znloa2pubWVxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTA5NjA0NzgsImV4cCI6MjEwNjUzNjQ3OH0.CbzVS3-ig73XOMyvbDaeII8Q4V2m1MjR6wIP62cl2eI';
  v_p text := split_part(v_anon, '.', 2);
  -- v0.22.0 (rodada 2 da varredura geral): a chave pública nova (sb_publishable_…; o Supabase desliga a anon antiga até o fim de
  -- 2026) vai só no apikey: no Authorization o Supabase a recusa (não é JWT), e a função fica com o "Verify JWT" desligado (LEIAME,
  -- "Chaves novas do Supabase"). A anon antiga (JWT) continua no Authorization
  v_nova constant boolean := v_anon ~ '^sb_publishable_[A-Za-z0-9_-]{16,200}$';
  v_cab_nome  constant text := case when v_nova then 'apikey' else 'Authorization' end;
  v_cab_valor constant text := case when v_nova then v_anon else 'Bearer ' || v_anon end;
  v_pedido text;
begin
  -- nunca a chave secreta: só um JWT com "role": "anon" ou a pública nova
  v_p := rpad(translate(v_p, '-_', '+/'), ((length(v_p) + 3) / 4) * 4, '=');
  if not v_nova and (v_anon like 'sb_secret_%' or v_anon !~ '^eyJ'
     or coalesce(convert_from(decode(v_p, 'base64'), 'UTF8')::jsonb ->> 'role', '') <> 'anon') then
    raise exception 'A chave escrita neste arquivo não é a chave anon (pública). Nada foi agendado.';
  end if;
  -- o pedido à radar-video, com a chave da agenda lida do Vault na hora (%s = a ação)
  v_pedido := format($c$select net.http_post(url := %L,
      body := jsonb_build_object('acao', %%L),
      headers := jsonb_build_object('Content-Type', 'application/json', %L, %L,
                   'x-radar-agenda', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_video_agenda')),
      timeout_milliseconds := 150000)$c$, v_url, v_cab_nome, v_cab_valor);
  perform cron.unschedule(j.jobid) from cron.job j where j.jobname like 'radar-video-%';
  -- a reserva: só com pedido esperando, com o limite de 3 acionamentos por pedido (radar_video_reserva confere e conta no banco;
  -- nenhuma linha = nenhum pedido)
  perform cron.schedule('radar-video-reserva', '*/10 * * * *', format(v_pedido, 'acionar') || ' where public.radar_video_reserva()');
  -- a limpeza diária; no mesmo comando (um só, como os outros), o histórico do pg_cron, que não é limpo sozinho: guarda 7 dias, como a
  -- agenda da Pauta
  perform cron.schedule('radar-video-limpeza', '37 6 * * *', $c$with historico as (delete from cron.job_run_details
         where end_time < now() - interval '7 days' and jobid in (select jobid from cron.job where jobname like 'radar-%') returning 1)
    $c$ || format(v_pedido, 'limpar'));
end $$;

select jobname, schedule, active from cron.job where jobname like 'radar-video-%';

-- ---------------------------------------------------------------------
-- Teste (não aciona o robô nem apaga nada), rodar à parte depois de instalar a função radar-video. Copie as 5 linhas do select para
-- uma consulta nova SEM os "--" do começo (no SQL Editor, selecione e aperte Ctrl+/) e execute; não há nada para trocar: a chave anon
-- vem do próprio agendamento acima (cron.job) e a da agenda, do Vault.
--
--   select net.http_post(url := 'https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-video',
--     body := '{"acao":"agenda_teste"}'::jsonb,
--     headers := (select jsonb_build_object('Content-Type', 'application/json', 'x-radar-agenda', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_video_agenda'))
--       || case when j.c ~ 'Bearer ' then jsonb_build_object('Authorization', substring(j.c from '(Bearer [^'']+)')) else jsonb_build_object('apikey', substring(j.c from '(sb_publishable_[A-Za-z0-9_-]+)')) end
--       from (select command as c from cron.job where jobname = 'radar-video-reserva') j));
--
-- Depois de alguns segundos (esperado: 200 {"ok":true,"versao":"0.22.0"}; 401 "Invalid JWT" = a chave anon do agendamento não é a
-- deste projeto: troque em v_anon e rode este arquivo de novo; com a chave nova, sb_publishable_…, 401 = a função ainda está com o
-- "Verify JWT" ligado):
--
--   select status_code, content from net._http_response order by id desc limit 1;
--
-- As últimas rodadas: select j.jobname, d.status, d.return_message, d.start_time from cron.job_run_details d
--   join cron.job j on j.jobid = d.jobid where j.jobname like 'radar-video-%' order by d.start_time desc limit 5;
-- ---------------------------------------------------------------------
