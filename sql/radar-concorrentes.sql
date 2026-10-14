-- =====================================================================
-- Radar Artecon v0.19.1 (opcional) — chave da função radar-concorrentes (rodar UMA vez no Supabase → SQL Editor)
--
-- A função radar-concorrentes (somente leitura) lê pela API oficial da Meta os dados públicos de perfis comerciais do
-- Instagram de outros escritórios. Ela é chamada pelo banco (net.http_post, exemplo no fim) ou por um script com o
-- cabeçalho x-radar-chave: a chave fica no Vault e só a função radar_concorrentes_conferir — que só o papel interno
-- (service_role) executa — a confere. O administrador logado também pode chamar a função, sem chave.
--
-- Pode rodar de novo: a chave existente é mantida e a função de conferência é refeita.
-- Para desfazer: sql/radar-concorrentes-reversao.sql.
-- Antes: instale a função radar-concorrentes com "Verify JWT" DESLIGADO e confira o META_IG_TOKEN (veja o LEIAME).
-- =====================================================================
begin;

-- v0.23.0: o pg_net só é criado quando ainda não existe (como nas agendas: com ele instalado, o "create extension" de novo pode
-- disparar o gatilho da Supabase)
do $$
begin
  if not exists (select 1 from pg_extension where extname = 'pg_net') then
    execute 'create extension pg_net';
  end if;
end $$;

-- chave aleatória de 64 caracteres (hexadecimal), como a da agenda da ITC; só o Vault a guarda
do $$
begin
  if not exists (select 1 from vault.secrets where name = 'radar_concorrentes') then
    perform vault.create_secret(replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''), 'radar_concorrentes',
                                'Chave que chama a função radar-concorrentes (Radar Artecon)');
  end if;
end $$;

-- A função radar-concorrentes confere a chave do cabeçalho x-radar-chave por aqui. Sem o Vault (ou sem a chave), nunca confere.
create or replace function public.radar_concorrentes_conferir(p_chave text) returns boolean
language plpgsql stable security definer set search_path = public as $$
declare v_certa text;
begin
  if length(coalesce(p_chave, '')) < 32 then return false; end if;
  execute 'select decrypted_secret from vault.decrypted_secrets where name = ''radar_concorrentes'' limit 1' into v_certa;
  return v_certa is not null and length(v_certa) >= 32 and v_certa = p_chave;
exception when others then
  return false;
end $$;

revoke all on function public.radar_concorrentes_conferir(text) from public, anon, authenticated;
grant execute on function public.radar_concorrentes_conferir(text) to service_role;

commit;

-- ---------------------------------------------------------------------
-- Como chamar pelo banco (SQL Editor). O pedido sai na hora e devolve só o número dele (id):
--
--   select net.http_post(
--     url := 'https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-concorrentes',
--     headers := jsonb_build_object('Content-Type', 'application/json',
--                  'x-radar-chave', (select decrypted_secret from vault.decrypted_secrets where name = 'radar_concorrentes')),
--     body := '{"perfis": ["escritorio1", "escritorio2"], "posts": 50}'::jsonb,
--     timeout_milliseconds := 150000);
--
-- De 1 a 12 perfis por chamada e de 1 a 100 posts por perfil. Teste de conexão: body := '{"acao": "diagnostico"}'::jsonb
--
-- A resposta chega em 1 a 2 minutos (o pg_net guarda as respostas por algumas horas):
--
--   select id, status_code, timed_out, error_msg, content::jsonb as resposta
--     from net._http_response order by id desc limit 1;
--
-- Perfis com "não coube no tempo; peça de novo só esses" voltam numa nova chamada só com eles.
-- ---------------------------------------------------------------------
