-- =====================================================================
-- Radar Artecon v0.12.0 — agenda da leitura do boletim da ITC (rodar UMA vez no Supabase → SQL Editor)
--
-- Liga as extensões pg_cron e pg_net, cria no Vault a chave que só a agenda conhece e agenda a função
-- radar-itc 1 vez por dia, às 02h55 de Brasília (05h55 UTC). Se nessa leitura ficar boletim para depois (o Supabase
-- limita cada chamada a ~150 s), ela se completa às 03h10 e às 03h25 — só nesse caso. Pode rodar de novo:
-- a chave existente é mantida e a agenda é refeita.
--
-- Antes: instale a função radar-itc e cadastre os segredos do Microsoft Graph (veja o LEIAME).
-- Troque o endereço abaixo se o projeto do Supabase for outro.
-- =====================================================================
create extension if not exists pg_cron;
create extension if not exists pg_net;

do $$
begin
  if not exists (select 1 from vault.secrets where name = 'radar_itc_agenda') then
    perform vault.create_secret(replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''), 'radar_itc_agenda',
                                'Chave da agenda que chama a função radar-itc (Radar Artecon)');
  end if;
end $$;

do $$
declare
  v_url text := 'https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-itc';
  v_cmd text;
begin
  perform cron.unschedule(j.jobid) from cron.job j where j.jobname like 'radar-itc%';
  v_cmd := format($c$select net.http_post(url := %L,
      headers := jsonb_build_object('Content-Type', 'application/json',
                   'x-radar-agenda', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_itc_agenda')),
      body := '{"acao": "ler"}'::jsonb, timeout_milliseconds := 150000)$c$, v_url);
  perform cron.schedule('radar-itc', '55 5 * * *', v_cmd);                               -- 02h55 de Brasília
  -- complemento: só chama se a leitura anterior deixou boletim para depois
  perform cron.schedule('radar-itc-completa', '10,25 6 * * *', v_cmd ||
    $c$ where exists (select 1 from public.radar_fontes where slug = 'itc-email' and ultimo_erro like '%ficaram para a próxima leitura%')$c$);
end $$;

select jobname, schedule, active from cron.job where jobname like 'radar-itc%';
