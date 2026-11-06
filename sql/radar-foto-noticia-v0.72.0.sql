-- =====================================================================
-- Radar Artecon — v0.72.0: a FOTO DA NOTÍCIA (uma só, presa ao assunto) e o RODÍZIO do acervo.
-- Rode no Supabase (SQL Editor). Pode rodar de novo: só cria o que falta e reescreve as funções.
--
-- O pedido (06/11/2026): a imagem de uma notícia é obrigatoriamente a MESMA em todas as publicações
-- dela — inclusive quando a IA prepara de novo (hoje cada preparo sorteia OUTRA foto do acervo).
-- E o sorteio automático só pode repetir uma foto quando TODAS já foram usadas; a escolha manual
-- vale sempre e fica, mesmo que a foto já tenha sido usada em outra notícia.
--
-- O que entra:
--   * radar_fotos_acervo.usada_em — quando a foto foi usada pela última vez (o rodízio);
--   * radar_assuntos.foto_imagem_id — a foto-base presa à notícia (referência a radar_imagens);
--   * radar_assunto_foto(p_assunto) — devolve a foto da notícia; sem uma, sorteia do acervo
--     (grupo "ambiente": nunca usadas primeiro, ao acaso; todas usadas: a usada há mais tempo),
--     marca o uso e prende ao assunto; acervo vazio devolve imagem_id nulo (a tela busca nos bancos);
--   * radar_assunto_foto_gravar(p_assunto, p_imagem) — a escolha manual (ou do banco de imagens)
--     vira a foto da notícia; se a imagem é do acervo, o uso é marcado;
--   * a limpeza de imagens (radar_fn_imagem_sem_uso, radar_limpar_imagens_sem_uso e
--     radar_foto_acervo_apagar) passa a POUPAR a foto presa a um assunto.
-- =====================================================================

alter table public.radar_fotos_acervo add column if not exists usada_em timestamptz;
alter table public.radar_assuntos add column if not exists foto_imagem_id bigint references public.radar_imagens(id) on delete set null;

-- A foto da notícia: a presa ao assunto; sem uma, o rodízio do acervo (só repete quando todas já foram usadas)
create or replace function public.radar_assunto_foto(p_assunto bigint) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_img  bigint;
  v_foto record;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR353: só o editor ou o administrador prepara a imagem da notícia' using errcode = 'P0001';
  end if;
  select foto_imagem_id into v_img from public.radar_assuntos where id = p_assunto for update;
  if not found then
    raise exception 'RADAR353: assunto não encontrado (atualize a página)' using errcode = 'P0001';
  end if;
  -- a notícia já tem a sua foto: é ela, sempre (a mesma em todas as publicações e em todo preparo novo)
  if v_img is not null and exists (select 1 from public.radar_imagens i where i.id = v_img) then
    return jsonb_build_object('imagem_id', v_img, 'nova', false);
  end if;
  -- o rodízio: entre as fotos de AMBIENTE nunca usadas, uma ao acaso; todas usadas, a usada há mais tempo
  select a.id, a.imagem_id, a.nome into v_foto
    from public.radar_fotos_acervo a
   where a.grupo = 'ambiente' and exists (select 1 from public.radar_imagens i where i.id = a.imagem_id)
   order by a.usada_em asc nulls first, random()
   limit 1;
  if v_foto.id is null then
    return jsonb_build_object('imagem_id', null, 'nova', false);   -- acervo vazio: a tela busca no banco de imagens
  end if;
  update public.radar_fotos_acervo set usada_em = now() where id = v_foto.id;
  update public.radar_assuntos set foto_imagem_id = v_foto.imagem_id where id = p_assunto;
  return jsonb_build_object('imagem_id', v_foto.imagem_id, 'nova', true, 'nome', v_foto.nome);
end $$;

-- A escolha manual (acervo, banco de imagens ou foto própria) vira a foto da notícia — vale mesmo que a
-- foto já tenha sido usada em outra notícia, e fica presa dali em diante
create or replace function public.radar_assunto_foto_gravar(p_assunto bigint, p_imagem bigint) returns void
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR354: só o editor ou o administrador escolhe a imagem da notícia' using errcode = 'P0001';
  end if;
  if not exists (select 1 from public.radar_imagens i where i.id = p_imagem) then
    raise exception 'RADAR354: a imagem não está no banco: envie a foto de novo' using errcode = 'P0001';
  end if;
  update public.radar_assuntos set foto_imagem_id = p_imagem where id = p_assunto;
  if not found then
    raise exception 'RADAR354: assunto não encontrado (atualize a página)' using errcode = 'P0001';
  end if;
  update public.radar_fotos_acervo set usada_em = now() where imagem_id = p_imagem;   -- se é do acervo, conta o uso
end $$;

-- A limpeza de imagens poupa a foto presa a um assunto (além do que já poupava)
create or replace function public.radar_fn_imagem_sem_uso() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  -- v0.16.0: vale também para a ilustração guardada (ilustracao_id)
  -- v0.21.0: a foto ou a lâmina aprovada de uma peça da Pauta nunca é apagada por aqui
  -- v0.42.0: nem a lâmina de uma publicação nas redes (radar_redes_envios.artes: o carrossel da notícia)
  -- v0.63.0: nem a foto do acervo da Artecon (radar_fotos_acervo)
  -- v0.72.0: nem a FOTO DA NOTÍCIA (radar_assuntos.foto_imagem_id: a foto-base presa ao assunto)
  delete from public.radar_imagens i
   where i.id in (old.imagem_id, old.ilustracao_id)
     and (tg_op = 'DELETE' or (i.id is distinct from new.imagem_id and i.id is distinct from new.ilustracao_id))
     and not exists (select 1 from public.radar_conteudos c where c.imagem_id = i.id or c.ilustracao_id = i.id)
     and not exists (select 1 from public.radar_pauta_pecas p where i.id = any(p.fotos) or i.id = any(p.artes))
     and not exists (select 1 from public.radar_redes_envios e where i.id = any(e.artes))
     and not exists (select 1 from public.radar_fotos_acervo a where a.imagem_id = i.id)
     and not exists (select 1 from public.radar_assuntos s where s.foto_imagem_id = i.id);
  return null;
end $$;

create or replace function public.radar_limpar_imagens_sem_uso(p_horas int default 24) returns int
language plpgsql security definer set search_path = public as $$
declare v_n int;
begin
  -- v0.72.0: + a foto da notícia (radar_assuntos.foto_imagem_id) entre as poupadas
  delete from public.radar_imagens i
   where i.criado_em < now() - make_interval(hours => least(greatest(coalesce(p_horas, 24), 1), 8760))
     and not exists (select 1 from public.radar_conteudos c where c.imagem_id = i.id or c.ilustracao_id = i.id)
     and not exists (select 1 from public.radar_pauta_pecas p where i.id = any(p.fotos) or i.id = any(p.artes))
     and not exists (select 1 from public.radar_redes_envios e where i.id = any(e.artes))
     and not exists (select 1 from public.radar_fotos_acervo a where a.imagem_id = i.id)
     and not exists (select 1 from public.radar_assuntos s where s.foto_imagem_id = i.id);
  get diagnostics v_n = row_count;
  return v_n;
end $$;

-- Tirar do acervo (só o administrador): a linha sai e a imagem, se nada mais a usa, sai junto.
-- v0.72.0: a imagem presa a um assunto (foto da notícia) NÃO sai — a notícia continua com a foto dela.
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
     and not exists (select 1 from public.radar_redes_envios e where i.id = any(e.artes))
     and not exists (select 1 from public.radar_assuntos s where s.foto_imagem_id = i.id);
end $$;

-- Segurança: como as demais funções expostas — nada ao anon/público; executam conferindo o papel
revoke all on function public.radar_assunto_foto(bigint) from public, anon, authenticated, service_role;
revoke all on function public.radar_assunto_foto_gravar(bigint, bigint) from public, anon, authenticated, service_role;
grant execute on function public.radar_assunto_foto(bigint) to authenticated;
grant execute on function public.radar_assunto_foto_gravar(bigint, bigint) to authenticated;

select 'v0.72.0 aplicada: foto da notícia + rodízio do acervo' as resultado;
