-- =====================================================================
-- Radar Artecon — desfaz a v0.72.0 (a foto da notícia e o rodízio do acervo).
-- Rode no Supabase (SQL Editor). As capas já desenhadas não mudam; só sai a "memória"
-- de qual foto pertence a cada notícia e o controle de uso do rodízio.
-- =====================================================================

drop function if exists public.radar_assunto_foto(bigint);
drop function if exists public.radar_assunto_foto_gravar(bigint, bigint);

-- a limpeza de imagens volta como na v0.63.0 (sem poupar a foto da notícia)
create or replace function public.radar_fn_imagem_sem_uso() returns trigger
language plpgsql security definer set search_path = public as $$
begin
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
  delete from public.radar_imagens i
   where i.criado_em < now() - make_interval(hours => least(greatest(coalesce(p_horas, 24), 1), 8760))
     and not exists (select 1 from public.radar_conteudos c where c.imagem_id = i.id or c.ilustracao_id = i.id)
     and not exists (select 1 from public.radar_pauta_pecas p where i.id = any(p.fotos) or i.id = any(p.artes))
     and not exists (select 1 from public.radar_redes_envios e where i.id = any(e.artes))
     and not exists (select 1 from public.radar_fotos_acervo a where a.imagem_id = i.id);
  get diagnostics v_n = row_count;
  return v_n;
end $$;

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

alter table public.radar_assuntos drop column if exists foto_imagem_id;
alter table public.radar_fotos_acervo drop column if exists usada_em;

select 'v0.72.0 desfeita' as resultado;
