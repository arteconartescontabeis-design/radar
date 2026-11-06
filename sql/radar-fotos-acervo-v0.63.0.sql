-- Radar v0.63.0 — Fotos da Artecon (o acervo das capas): as fotos da pasta "FOTOS ARTECON" do OneDrive
-- (triagem "1 Ambiente (sem rosto)" e "2 Socios (com rosto)"), enviadas pela tela (Configurações →
-- "Fotos da Artecon"), em dois grupos — 'ambiente' (sem rosto: as publicações normais) e 'socios'
-- (com rosto: para escolher à mão). O "Preparar com IA" com "Foto real com o título" passa a usar uma
-- foto do grupo 'ambiente' na capa (o título continua escrito por cima, como sempre); sem nenhuma foto
-- no acervo, continua buscando nos bancos de imagens (Pixabay/Pexels), como antes.
-- Incremental idempotente sobre o banco v0.50.0 (com os incrementais anteriores): create or replace /
-- if not exists; nada é apagado; pode rodar de novo. Para desfazer: sql/radar-fotos-acervo-reversao.sql.

create table if not exists public.radar_fotos_acervo (
  id         bigint generated always as identity primary key,
  grupo      text not null check (grupo in ('ambiente','socios')),
  nome       text not null default '' check (length(nome) <= 120 and nome !~ '[<>{}\\]' and nome !~ '[[:cntrl:]]'),
  imagem_id  bigint not null unique references public.radar_imagens(id) on delete restrict,
  criado_em  timestamptz not null default now(),
  criado_por uuid default auth.uid() references auth.users(id) on delete set null
);

-- Entrar no acervo (editor e administrador): a tela grava a foto em radar_imagens e chama aqui.
create or replace function public.radar_foto_acervo_gravar(p_grupo text, p_nome text, p_imagem_id bigint) returns bigint
language plpgsql security definer set search_path = public as $$
declare
  v_grupo text := trim(coalesce(p_grupo, ''));
  v_nome  text := trim(coalesce(p_nome, ''));
  v_id    bigint;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR345: só o editor ou o administrador mexe no acervo de fotos da Artecon' using errcode = 'P0001';
  end if;
  if v_grupo not in ('ambiente','socios') then
    raise exception 'RADAR346: o grupo da foto é "ambiente" (sem rosto) ou "socios" (com rosto)' using errcode = 'P0001';
  end if;
  if length(v_nome) > 120 or v_nome ~ '[<>{}\\]' or v_nome ~ '[[:cntrl:]]' then
    raise exception 'RADAR346: o nome da foto tem até 120 caracteres, sem < > { } nem \' using errcode = 'P0001';
  end if;
  if not exists (select 1 from public.radar_imagens i where i.id = p_imagem_id) then
    raise exception 'RADAR346: a imagem não está no banco: envie a foto de novo' using errcode = 'P0001';
  end if;
  -- só imagem recém-enviada: uma capa, foto de peça ou lâmina já em uso não vira foto do acervo
  if exists (select 1 from public.radar_conteudos c where c.imagem_id = p_imagem_id or c.ilustracao_id = p_imagem_id)
     or exists (select 1 from public.radar_pauta_pecas p where p_imagem_id = any(p.fotos) or p_imagem_id = any(p.artes))
     or exists (select 1 from public.radar_redes_envios e where p_imagem_id = any(e.artes)) then
    raise exception 'RADAR346: esta imagem já é usada por uma publicação ou peça: envie a foto de novo' using errcode = 'P0001';
  end if;
  if (select count(*) from public.radar_fotos_acervo) >= 300 then
    raise exception 'RADAR347: o acervo está cheio (300 fotos): tire as que não usa mais' using errcode = 'P0001';
  end if;
  insert into public.radar_fotos_acervo (grupo, nome, imagem_id)
  values (v_grupo, v_nome, p_imagem_id) returning id into v_id;
  return v_id;
end $$;

-- Tirar do acervo (só o administrador): a linha sai e a imagem, se nada mais a usa, sai junto.
create or replace function public.radar_foto_acervo_apagar(p_id bigint) returns void
language plpgsql security definer set search_path = public as $$
declare v_imagem bigint;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR348: só o administrador tira uma foto do acervo' using errcode = 'P0001';
  end if;
  delete from public.radar_fotos_acervo where id = p_id returning imagem_id into v_imagem;
  if not found then
    raise exception 'RADAR348: foto não encontrada no acervo (atualize a página)' using errcode = 'P0001';
  end if;
  delete from public.radar_imagens i
   where i.id = v_imagem
     and not exists (select 1 from public.radar_conteudos c where c.imagem_id = i.id or c.ilustracao_id = i.id)
     and not exists (select 1 from public.radar_pauta_pecas p where i.id = any(p.fotos) or i.id = any(p.artes))
     and not exists (select 1 from public.radar_redes_envios e where i.id = any(e.artes));
end $$;

-- A imagem que fica sem uso continua sendo apagada — mas a foto do acervo é poupada (sem isto, a chave
-- estrangeira do acervo faria a limpeza falhar, ou a foto sumiria na faxina diária do robô).
create or replace function public.radar_fn_imagem_sem_uso() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  -- v0.16.0: vale também para a ilustração guardada (ilustracao_id)
  -- v0.21.0: a foto ou a lâmina aprovada de uma peça da Pauta nunca é apagada por aqui
  -- v0.42.0: nem a lâmina de uma publicação nas redes (radar_redes_envios.artes: o carrossel da notícia)
  -- v0.63.0: nem a foto do acervo da Artecon (radar_fotos_acervo)
  delete from public.radar_imagens i
   where i.id in (old.imagem_id, old.ilustracao_id)
     and (tg_op = 'DELETE' or (i.id is distinct from new.imagem_id and i.id is distinct from new.ilustracao_id))
     and not exists (select 1 from public.radar_conteudos c where c.imagem_id = i.id or c.ilustracao_id = i.id)
     and not exists (select 1 from public.radar_pauta_pecas p where i.id = any(p.fotos) or i.id = any(p.artes))
     and not exists (select 1 from public.radar_redes_envios e where i.id = any(e.artes))
     and not exists (select 1 from public.radar_fotos_acervo a where a.imagem_id = i.id);
  return null;
end $$;

create or replace function public.radar_limpar_imagens_sem_uso(p_horas int default 24) returns int
language plpgsql security definer set search_path = public as $$
declare v_n int;
begin
  -- v0.21.0: as fotos e as lâminas aprovadas das peças da Pauta também ficam (sem isso, sumiriam um dia depois de enviadas)
  -- v0.42.0: e as lâminas das publicações nas redes (radar_redes_envios.artes: o carrossel da notícia)
  -- v0.63.0: e as fotos do acervo da Artecon (radar_fotos_acervo)
  delete from public.radar_imagens i
   where i.criado_em < now() - make_interval(hours => least(greatest(coalesce(p_horas, 24), 1), 8760))
     and not exists (select 1 from public.radar_conteudos c where c.imagem_id = i.id or c.ilustracao_id = i.id)
     and not exists (select 1 from public.radar_pauta_pecas p where i.id = any(p.fotos) or i.id = any(p.artes))
     and not exists (select 1 from public.radar_redes_envios e where i.id = any(e.artes))
     and not exists (select 1 from public.radar_fotos_acervo a where a.imagem_id = i.id);
  get diagnostics v_n = row_count;
  return v_n;
end $$;

-- Segurança: como as demais tabelas do Radar — nada ao anon/público; a leitura é do editor e do
-- administrador (RLS; o acervo serve a quem prepara conteúdo); a escrita é só pelas funções.
alter table public.radar_fotos_acervo enable row level security;
revoke all on public.radar_fotos_acervo from public, anon, authenticated, service_role;
revoke all on sequence public.radar_fotos_acervo_id_seq from public, anon, authenticated, service_role;
drop policy if exists radar_fotos_acervo_sel on public.radar_fotos_acervo;
create policy radar_fotos_acervo_sel on public.radar_fotos_acervo for select
  using (coalesce(public.radar_papel(), '') in ('admin','editor'));
revoke all on function public.radar_foto_acervo_gravar(text, text, bigint) from public, anon, authenticated, service_role;
revoke all on function public.radar_foto_acervo_apagar(bigint) from public, anon, authenticated, service_role;
grant select on public.radar_fotos_acervo to authenticated;
grant execute on function public.radar_foto_acervo_gravar(text, text, bigint) to authenticated;
grant execute on function public.radar_foto_acervo_apagar(bigint) to authenticated;
