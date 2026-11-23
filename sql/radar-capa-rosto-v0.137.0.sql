-- Radar Artecon — v0.137.0: escolher a capa automática das publicações — Ambiente (sem rosto), Sócios (com rosto) ou as duas.
--
-- Acrescenta a configuração "capa" ({"rosto": "sem"|"com"|"ambos"}) e faz a função radar_assunto_foto (o rodízio da capa
-- automática) ler essa escolha. O administrador troca em Configurações → "Fotos da Artecon". Nada é apagado; pode rodar de novo.
-- Padrão "sem" = Ambiente (como era até aqui). "com" = Sócios (com rosto). "ambos" = os dois grupos no rodízio.
-- Não mexe em tabela nem em outra função. O mesmo conteúdo está no sql/radar-setup-v0.50.0.sql.

insert into public.radar_config (chave, valor)
select 'capa', '{"rosto": "sem"}'::jsonb
where not exists (select 1 from public.radar_config where chave = 'capa');

create or replace function public.radar_assunto_foto(p_assunto bigint) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_img  bigint;
  v_foto record;
  -- v0.137.0: a capa automática usa o grupo escolhido em Configurações → "Fotos da Artecon" (radar_config.capa.rosto):
  -- 'sem' = Ambiente (padrão), 'com' = Sócios (com rosto), 'ambos' = os dois no rodízio.
  v_rosto text := coalesce((select c.valor->>'rosto' from public.radar_config c where c.chave = 'capa'), 'sem');
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
  select a.id, a.imagem_id, a.nome into v_foto
    from public.radar_fotos_acervo a
   where a.grupo = any(case v_rosto when 'com'   then array['socios']
                                    when 'ambos' then array['ambiente','socios']
                                    else array['ambiente'] end)
     and exists (select 1 from public.radar_imagens i where i.id = a.imagem_id)
   order by a.usada_em asc nulls first, random()
   limit 1;
  if v_foto.id is null then
    return jsonb_build_object('imagem_id', null, 'nova', false);
  end if;
  update public.radar_fotos_acervo set usada_em = now() where id = v_foto.id;
  update public.radar_assuntos set foto_imagem_id = v_foto.imagem_id where id = p_assunto;
  return jsonb_build_object('imagem_id', v_foto.imagem_id, 'nova', true, 'nome', v_foto.nome);
end $$;
