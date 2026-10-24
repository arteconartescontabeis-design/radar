-- =====================================================================
-- Radar Artecon v0.46.0 — Termo de uso de imagem com ASSINATURA na tela
-- (rodar no Supabase → SQL Editor, DEPOIS do radar-setup-v0.45.0.sql; pode rodar de novo)
--
-- O "aceite" por data vira uma ASSINATURA de verdade: a pessoa desenha a assinatura (caneta/dedo/mouse),
-- informa o CPF e confirma. Guarda como PROVA, num histórico, a imagem da assinatura, o nome, o CPF, a
-- data/hora, o aparelho e o texto exato assinado. TODOS assinam (sócios inclusive: não há mais dispensa).
-- =====================================================================

-- 1) CPF na pessoa (o "atual"; o histórico guarda o CPF de cada assinatura)
alter table public.radar_pessoas add column if not exists cpf text;

-- 2) o texto e a versão do termo, editáveis pelo administrador (sem mexer no código)
insert into public.radar_config (chave, valor)
values ('termo_imagem', jsonb_build_object(
  'versao', 1,
  'texto',
  'TERMO DE AUTORIZAÇÃO DE USO DE IMAGEM, VOZ E NOME' || E'\n\n' ||
  'Eu, {NOME}, inscrito(a) no CPF {CPF}, autorizo a ARTECON ARTES CONTÁBEIS a captar, usar e divulgar a minha ' ||
  'imagem, voz e nome em fotos e vídeos produzidos para o escritório, nos canais site, Instagram e Facebook da ' ||
  'Artecon, com a finalidade de comunicação institucional e divulgação de conteúdo informativo.' || E'\n\n' ||
  'Esta autorização é gratuita e por prazo indeterminado, podendo ser revogada por mim a qualquer tempo, por ' ||
  'escrito — a revogação não atinge o conteúdo já publicado antes dela.' || E'\n\n' ||
  'Estou ciente de que os vídeos passam por um corretor automático de vídeo do sistema Radar, que confere a ' ||
  'gravação com o roteiro antes da publicação, e autorizo esse processamento.' || E'\n\n' ||
  'Li e concordo com este termo, que assino eletronicamente abaixo.'))
on conflict (chave) do nothing;

-- 3) o histórico das assinaturas (uma linha por assinatura; nunca se apaga — é prova)
create table if not exists public.radar_pessoas_termos (
  id            bigint generated always as identity primary key,
  pessoa_id     bigint not null references public.radar_pessoas(id) on delete cascade,
  assinado_em   timestamptz not null default now(),
  nome          text not null,                 -- cópia do nome no momento da assinatura
  cpf           text not null,
  termo_versao  integer not null,
  termo_texto   text not null,                 -- cópia exata do texto assinado
  canais        text[] not null,
  usos          text[] not null,
  assinatura    text not null,                 -- a imagem da assinatura (PNG em data URL)
  aparelho      text,                          -- o navegador/aparelho (user agent), para a prova
  assinado_por  uuid default auth.uid(),       -- quem estava logado quando a pessoa assinou
  revogado_em   timestamptz
);
create index if not exists radar_pessoas_termos_pessoa on public.radar_pessoas_termos(pessoa_id, assinado_em desc);

-- 4) a função que GRAVA a assinatura (só o administrador; confere CPF e assinatura; grava o histórico e o "atual")
create or replace function public.radar_pessoa_assinar_termo(
  p_pessoa bigint, p_cpf text, p_assinatura text, p_aparelho text default null) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_pessoa public.radar_pessoas%rowtype;
  v_cfg    jsonb;
  v_cpf    text := regexp_replace(coalesce(p_cpf, ''), '\D', '', 'g');   -- só os dígitos
  v_canais text[] := array['instagram','facebook'];       -- os canais que a conferência da Pauta usa (o texto do termo cobre também o site)
  v_usos   text[] := array['equipe','orientacao','datas','captacao'];
  v_hist   bigint;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR190: só o administrador registra a assinatura do termo.' using errcode = 'P0001';
  end if;
  select * into v_pessoa from public.radar_pessoas where id = p_pessoa;
  if v_pessoa.id is null then raise exception 'RADAR190: pessoa não encontrada.' using errcode = 'P0001'; end if;
  if length(v_cpf) <> 11 then raise exception 'RADAR190: CPF inválido (precisa de 11 dígitos).' using errcode = 'P0001'; end if;
  -- a assinatura é uma imagem PNG em data URL, com tamanho razoável (evita abuso)
  if p_assinatura is null or p_assinatura !~ '^data:image/(png|jpeg);base64,[A-Za-z0-9+/=]+$'
     or length(p_assinatura) < 400 or length(p_assinatura) > 400000 then
    raise exception 'RADAR190: assinatura ausente ou inválida (assine no quadro antes de confirmar).' using errcode = 'P0001';
  end if;
  select valor into v_cfg from public.radar_config where chave = 'termo_imagem';
  if v_cfg is null then raise exception 'RADAR190: o texto do termo não está configurado.' using errcode = 'P0001'; end if;

  insert into public.radar_pessoas_termos (pessoa_id, nome, cpf, termo_versao, termo_texto, canais, usos, assinatura, aparelho)
  values (p_pessoa, coalesce(v_pessoa.nome, v_pessoa.nome_na_peca, ''), v_cpf,
          coalesce((v_cfg->>'versao')::int, 1), coalesce(v_cfg->>'texto', ''), v_canais, v_usos,
          p_assinatura, left(coalesce(p_aparelho, ''), 400))
  returning id into v_hist;

  update public.radar_pessoas set
    cpf = v_cpf,
    termo_assinado_em = current_date,
    termo_corretor_em = current_date,          -- o termo único cobre também o corretor de vídeo
    termo_canais = v_canais,
    termo_usos = v_usos,
    termo_valido_ate = null,
    termo_revogado_em = null,
    atualizado_em = now()
  where id = p_pessoa;

  return jsonb_build_object('ok', true, 'historico', v_hist, 'assinado_em', current_date);
end $$;

-- 5) revogar o termo (só o administrador): marca a revogação, na pessoa e na última assinatura
create or replace function public.radar_pessoa_revogar_termo(p_pessoa bigint) returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR190: só o administrador revoga o termo.' using errcode = 'P0001';
  end if;
  update public.radar_pessoas set termo_revogado_em = current_date, atualizado_em = now() where id = p_pessoa;
  update public.radar_pessoas_termos set revogado_em = now()
   where pessoa_id = p_pessoa and revogado_em is null;
  return jsonb_build_object('ok', true);
end $$;

-- 6) agora TODOS precisam do termo assinado (sócio não é mais dispensado): a única mudança na conferência
create or replace function public.radar_pauta_termo_ok(p_pessoa bigint, p_tipo text, p_canal text, p_data date) returns text
language plpgsql stable set search_path = public as $$
declare
  v     public.radar_pessoas%rowtype;
  v_uso text := case when p_tipo in ('quem_cuida','bastidor') then 'equipe'
                     when p_tipo in ('reel','educativo','agenda','noticia') then 'orientacao'
                     when p_tipo = 'data_equipe' then 'datas'
                     when p_tipo = 'captacao' then 'captacao' end;
begin
  select * into v from public.radar_pessoas where id = p_pessoa;
  if v.id is null then return 'pessoa não cadastrada'; end if;
  if not v.ativo then return 'pessoa inativa'; end if;
  -- v0.46.0: todos assinam (inclusive sócios): a dispensa por "socio" foi removida
  if v.termo_assinado_em is null then return 'sem termo assinado'; end if;
  if p_data is null or v.termo_assinado_em > p_data then return 'termo assinado depois desta data'; end if;
  if v.termo_revogado_em is not null and v.termo_revogado_em <= p_data then return 'termo revogado'; end if;
  if v.termo_valido_ate is not null and v.termo_valido_ate < p_data then return 'termo vencido'; end if;
  if p_canal is null or not p_canal = any(v.termo_canais) then return 'canal não autorizado no termo'; end if;
  if v_uso is null or not v_uso = any(v.termo_usos) then return 'finalidade não autorizada no termo'; end if;
  return null;
end $$;

-- 7) a view: ninguém é mais "dispensado" (todos assinam)
create or replace view public.radar_v_pauta_pessoas
with (security_invoker = true) as
select p.id as peca_id, p.data, pe.id as pessoa_id, pe.nome_na_peca,
       public.radar_pauta_termo_ok(pe.id, p.tipo, 'instagram', p.data) as motivo_instagram,
       public.radar_pauta_termo_ok(pe.id, p.tipo, 'facebook',  p.data) as motivo_facebook,
       false as termos_dispensados                     -- v0.46.0: todos assinam
from public.radar_pauta_pecas p
cross join lateral unnest(p.pessoas) as u(pessoa_id)
join public.radar_pessoas pe on pe.id = u.pessoa_id;

-- 7b) o CPF também fica FORA da trilha de auditoria (como o nome, o nome na peça, o CRC e a área): a prova completa (com o CPF e a
--     imagem da assinatura) fica em radar_pessoas_termos, que não é auditada. A trilha de radar_pessoas segue sem dado pessoal.
create or replace function public.radar_fn_auditar() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_reg jsonb;
  v_tira text[] := case tg_table_name
                     when 'radar_redes_envios' then array['imagem']
                     when 'radar_pauta_pecas'  then array['ia','assunto','objetivo','observacao','quem_aparece']
                     when 'radar_pessoas'      then array['nome','nome_na_peca','crc','area','cpf']   -- v0.46.0: + cpf
                     when 'radar_videos'       then array['relatorio','fala_roteiro','ajustes','cartela_linhas']
                     else array[]::text[] end;
begin
  if tg_op = 'DELETE' then v_reg := to_jsonb(old); else v_reg := to_jsonb(new); end if;
  if tg_op = 'UPDATE'
     and (to_jsonb(old) - array['ultimo_sucesso_em','ultima_falha_em','ultimo_erro','falhas_consecutivas','atualizado_em'])
       = (to_jsonb(new) - array['ultimo_sucesso_em','ultima_falha_em','ultimo_erro','falhas_consecutivas','atualizado_em']) then
    return new;
  end if;
  if tg_op = 'UPDATE' and tg_table_name in ('radar_redes_envios','radar_pauta_pecas','radar_pessoas','radar_videos')
     and (to_jsonb(old) - v_tira - array['atualizado_em','disparos','disparado_em','pego_em','tentativas','rodada','palavras_tentativa','fila_em','reservas','retentar_em'])
       = (to_jsonb(new) - v_tira - array['atualizado_em','disparos','disparado_em','pego_em','tentativas','rodada','palavras_tentativa','fila_em','reservas','retentar_em']) then
    return new;
  end if;
  insert into public.radar_auditoria (tabela, registro_id, acao, usuario, antes, depois)
  values (tg_table_name,
          coalesce(v_reg->>'id', v_reg->>'user_id', v_reg->>'slug', v_reg->>'chave', '?'),
          tg_op, auth.uid(),
          case when tg_op <> 'INSERT' then to_jsonb(old) - v_tira end,
          case when tg_op <> 'DELETE' then to_jsonb(new) - v_tira end);
  if tg_op = 'DELETE' then return old; end if;
  return new;
end $$;

-- 8) RLS e privilégios da tabela nova e das funções
alter table public.radar_pessoas_termos enable row level security;
revoke all on public.radar_pessoas_termos from public, anon, authenticated, service_role;
grant select on public.radar_pessoas_termos to authenticated;      -- quem decide é a RLS; gravar só pela função
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='radar_pessoas_termos' and policyname='termos_admin_le') then
    create policy termos_admin_le on public.radar_pessoas_termos for select to authenticated
      using (public.radar_papel() = 'admin');
  end if;
end $$;
revoke all on function public.radar_pessoa_assinar_termo(bigint, text, text, text) from public, anon;
grant execute on function public.radar_pessoa_assinar_termo(bigint, text, text, text) to authenticated;
revoke all on function public.radar_pessoa_revogar_termo(bigint) from public, anon;
grant execute on function public.radar_pessoa_revogar_termo(bigint) to authenticated;

select 'v0.46.0 termo com assinatura — aplicado' as resultado;
