-- =====================================================================
-- Radar Artecon — v0.74.0: "ENVIAR MESMO ASSIM" (o administrador assume as pendências, com confirmação).
-- Rode no Supabase (SQL Editor). Pode rodar de novo.
--
-- O pedido (10/11/2026): poder aceitar o vídeo e enviar para a correção mesmo com pendência, desde que
-- confirmado pelo usuário. Como fica:
--   * radar_video_criar ganha p_assumir (SÓ o administrador): com ele, a pendência de TERMO das pessoas e a
--     frase igual à do boletim pago não travam o envio ao corretor. MENOR DE IDADE e pessoa não cadastrada
--     continuam impeditivos, e a APROVAÇÃO/publicação continua exigindo o termo — o assumir vale só para o
--     envio à correção;
--   * fica registrado quem assumiu e quando (radar_videos.assumido_em / assumido_por);
--   * radar_video_enviado (quando os clipes chegam) respeita o assumir gravado, com os mesmos impeditivos.
-- =====================================================================

drop function if exists public.radar_video_criar(bigint, jsonb, bigint, text, text[], boolean, text[], numeric);
alter table public.radar_videos add column if not exists assumido_em timestamptz;
alter table public.radar_videos add column if not exists assumido_por uuid references auth.users(id) on delete set null;

create or replace function public.radar_video_criar(p_peca bigint, p_partes jsonb, p_fala_pessoa bigint, p_fala_roteiro text,
                                                    p_cartela text[], p_gancho boolean, p_declaracoes text[], p_duracao numeric default null,
                                                    p_assumir boolean default false)
returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  p        public.radar_pauta_pecas%rowtype;
  v_fala   text := btrim(regexp_replace(coalesce(p_fala_roteiro, ''), '[[:space:]]+', ' ', 'g'));
  v_partes jsonb := '[]'::jsonb;
  v_parte  jsonb;
  v_n      bigint;
  v_total  numeric := 0;
  v_i      bigint;
  v_x      text;
  v_versao int;
  v_id     uuid;
  v_usado  numeric := public.radar_video_segundos_mes();
  v_limite numeric := public.radar_video_limite_s();
  v_decl   constant text[] := array['so_marcadas','sem_fundo','so_voz','fala_confere'];
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR300: só o editor ou o administrador envia a gravação do reel' using errcode = '42501';
  end if;
  -- v0.74.0: "Enviar mesmo assim" (pendências assumidas) é só do administrador, sempre confirmado na tela
  if coalesce(p_assumir, false) and coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR355: só o administrador envia com pendências (Enviar mesmo assim)' using errcode = 'P0001';
  end if;
  -- 1. a peça
  select * into p from public.radar_pauta_pecas where id = p_peca for update;
  if p.id is null then
    raise exception 'RADAR301: peça não encontrada' using errcode = 'P0001';
  end if;
  if p.formato <> 'reel' then
    raise exception 'RADAR301: o corretor de vídeo é só para a peça em formato reel' using errcode = 'P0001';
  end if;
  if p.situacao = 'aprovada' then
    raise exception 'RADAR301: a peça está aprovada: para mudar o vídeo, use Desfazer aprovação' using errcode = 'P0001';
  end if;
  if p.situacao not in ('planejada','em_producao','pronta') then
    raise exception 'RADAR301: a peça está cancelada: para gravar, use Reabrir' using errcode = 'P0001';
  end if;
  if p.publicado_manual_em is not null or exists (select 1 from public.radar_redes_envios e where e.peca_id = p.id and e.situacao = 'publicado') then
    raise exception 'RADAR301: a peça já saiu numa rede' using errcode = 'P0001';
  end if;
  -- 2. a fala para conferência
  if btrim(p.roteiro) = '' then
    raise exception 'RADAR302: cole o roteiro na peça antes de enviar a gravação' using errcode = 'P0001';
  end if;
  if length(v_fala) not between 20 and 6000 or not public.radar_video_fala_no_roteiro(v_fala, p.roteiro) then
    raise exception 'RADAR302: a fala para conferência tem de estar no roteiro da peça, palavra por palavra e na ordem (ao menos 10 palavras)'
      using errcode = 'P0001';
  end if;
  -- 3. o boletim pago: só sim ou não (o trecho não aparece); v0.74.0: o administrador pode assumir e enviar mesmo assim
  if not coalesce(p_assumir, false) and public.radar_pauta_copia_paga(array[p.roteiro, v_fala]) then
    raise exception 'RADAR303: o roteiro tem frase igual à do boletim pago (ITC): reescreva com palavras próprias antes de gravar'
      using errcode = 'P0001';
  end if;
  -- 4. as pessoas
  if cardinality(p.pessoas) = 0 then
    raise exception 'RADAR304: marque em Quem aparece a pessoa que fala no vídeo' using errcode = 'P0001';
  end if;
  if p_fala_pessoa is null or not p_fala_pessoa = any(p.pessoas) then
    raise exception 'RADAR304: quem fala tem de estar marcada em Quem aparece' using errcode = 'P0001';
  end if;
  foreach v_i in array p.pessoas loop
    v_x := public.radar_video_pessoa_falta(v_i, p.id);
    -- v0.74.0: com o assumir do administrador, a pendência de termo não trava; menor de idade e pessoa
    -- não cadastrada continuam impeditivos
    if v_x is not null and (not coalesce(p_assumir, false) or v_x = 'pessoa não cadastrada' or v_x like 'menor de idade%') then
      raise exception 'RADAR304: uma pessoa da peça não pode aparecer no vídeo (%): confira em Pauta → Pessoas e termos', v_x using errcode = 'P0001';
    end if;
  end loop;
  -- 5. a cartela
  v_x := public.radar_video_cartela_falta(p_cartela, p_fala_pessoa);
  if v_x is not null then
    raise exception 'RADAR305: %', v_x using errcode = 'P0001';
  end if;
  -- 6. os clipes, na ordem: [{n: 1…, tipo, bytes}]
  if p_partes is null or jsonb_typeof(p_partes) <> 'array' or jsonb_array_length(p_partes) not between 1 and 12 then
    raise exception 'RADAR306: envie de 1 a 12 clipes' using errcode = 'P0001';
  end if;
  for v_parte, v_n in select x, o from jsonb_array_elements(p_partes) with ordinality t(x, o) loop
    -- {n, tipo, bytes} e nada mais (cada conferência só depois da anterior: a seguinte não roda sobre o que não é objeto)
    if jsonb_typeof(v_parte) is distinct from 'object' then v_parte := '{}'::jsonb; end if;
    if (select count(*) from jsonb_object_keys(v_parte)) <> 3
       or jsonb_typeof(v_parte->'n') is distinct from 'number' or (v_parte->>'n') <> v_n::text
       or coalesce(v_parte->>'tipo', '') not in ('video/mp4','video/quicktime','video/webm')   -- v0.44.0: + a gravação do teleprompter pelo navegador
       or jsonb_typeof(v_parte->'bytes') is distinct from 'number' or (v_parte->>'bytes') !~ '^[0-9]{1,9}$' then
      raise exception 'RADAR306: o clipe nº % não confere (MP4, MOV ou a gravação do navegador, de 1 byte a 500 MB, na ordem)', v_n using errcode = 'P0001';
    end if;
    if (v_parte->>'bytes')::bigint not between 1 and 524288000 then
      raise exception 'RADAR306: o clipe nº % não confere (MP4, MOV ou a gravação do navegador, de 1 byte a 500 MB, na ordem)', v_n using errcode = 'P0001';
    end if;
    v_total := v_total + (v_parte->>'bytes')::bigint;
    v_partes := v_partes || jsonb_build_array(jsonb_build_object('n', v_n, 'tipo', v_parte->>'tipo', 'bytes', (v_parte->>'bytes')::bigint));
  end loop;
  if v_total > 524288000 then
    raise exception 'RADAR306: os clipes passam de 500 MB no total' using errcode = 'P0001';
  end if;
  if p_declaracoes is null or not (p_declaracoes @> v_decl and p_declaracoes <@ v_decl) then
    raise exception 'RADAR307: marque as quatro declarações (só as pessoas marcadas; sem tela, documento ou cliente ao fundo; só a voz; a fala para conferência é o que foi gravado)'
      using errcode = 'P0001';
  end if;
  if coalesce(p_gancho, false) and btrim(p.chamada) = '' then
    raise exception 'RADAR308: o texto do gancho é a chamada da peça: escreva a chamada ou desmarque o gancho' using errcode = 'P0001';
  end if;
  if v_usado >= v_limite then
    raise exception 'RADAR312: o limite de minutos do corretor neste mês acabou (Configurações → Corretor de vídeo)' using errcode = 'P0001';
  end if;
  if p_duracao is not null and p_duracao > 0 and v_usado + p_duracao > v_limite then
    raise exception 'RADAR312: a gravação tem cerca de % s, e o corretor só pode transcrever mais % s neste mês (Configurações → Corretor de vídeo → limite_min_mes): grave mais curto ou espere o mês que vem',
      round(p_duracao), floor(v_limite - v_usado) using errcode = 'P0001';
  end if;
  -- 7. o envio anterior que ainda esperava os arquivos é substituído por este (o vídeo vivo fica até os clipes deste chegarem)
  select coalesce(max(versao), 0) + 1 into v_versao from public.radar_videos where peca_id = p.id;
  if v_versao > 50 then
    raise exception 'RADAR301: esta peça já recebeu 50 gravações' using errcode = 'P0001';
  end if;
  update public.radar_videos set situacao = 'substituido', encerrado_em = now(), pego_em = null
   where peca_id = p.id and situacao = 'aguardando_envio';
  insert into public.radar_videos (peca_id, versao, partes, fala_pessoa, pessoas, fala_roteiro, roteiro_hash, cartela_linhas, gancho, declaracoes,
                                   enviado_por, assumido_em, assumido_por)
  values (p.id, v_versao, v_partes, p_fala_pessoa, p.pessoas, v_fala, public.radar_hash_texto(p.roteiro),
          array(select btrim(l) from unnest(p_cartela) with ordinality t(l, o) order by o),
          case when coalesce(p_gancho, false) then btrim(p.chamada) end,
          array(select d from unnest(v_decl) d), auth.uid(),
          case when coalesce(p_assumir, false) then now() end, case when coalesce(p_assumir, false) then auth.uid() end)
  returning id into v_id;
  return jsonb_build_object('id', v_id, 'versao', v_versao);
end $$;

create or replace function public.radar_video_enviado(p_id uuid) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_peca bigint;
  p      public.radar_pauta_pecas%rowtype;
  v      public.radar_videos%rowtype;
  v_x    text;
  v_i    bigint;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR300: só o editor ou o administrador envia a gravação do reel' using errcode = '42501';
  end if;
  select peca_id into v_peca from public.radar_videos where id = p_id;          -- sem trava: a ordem é peça, depois vídeo
  select * into p from public.radar_pauta_pecas where id = v_peca for update;
  select * into v from public.radar_videos where id = p_id for update;
  if v.id is null or v.situacao <> 'aguardando_envio' then
    raise exception 'RADAR309: este envio não está esperando os arquivos (já foi para a fila, foi substituído ou descartado)' using errcode = 'P0001';
  end if;
  if v.enviado_por is distinct from auth.uid() and public.radar_papel() <> 'admin' then
    raise exception 'RADAR309: só quem começou o envio (ou o administrador) conclui o envio' using errcode = 'P0001';
  end if;
  if p.situacao = 'aprovada' then
    raise exception 'RADAR301: a peça foi aprovada durante o envio: para mudar o vídeo, use Desfazer aprovação' using errcode = 'P0001';
  end if;
  if p.situacao not in ('planejada','em_producao','pronta') then
    raise exception 'RADAR301: a peça está cancelada: para gravar, use Reabrir' using errcode = 'P0001';
  end if;
  if p.publicado_manual_em is not null or exists (select 1 from public.radar_redes_envios e where e.peca_id = p.id and e.situacao = 'publicado') then
    raise exception 'RADAR301: a peça já saiu numa rede' using errcode = 'P0001';
  end if;
  -- quem pode estar no vídeo: as marcadas no envio e as marcadas agora, quando os clipes chegaram
  v.pessoas := array(select distinct x from unnest(v.pessoas || p.pessoas) x order by x);
  -- v0.74.0: o envio assumido pelo administrador não volta a travar pelo termo quando os clipes chegam;
  -- menor de idade e pessoa não cadastrada continuam impeditivos
  if v.assumido_em is null then
    v_x := public.radar_video_pessoas_falta(p.id, v.fala_pessoa, v.pessoas);
    if v_x is not null then
      raise exception 'RADAR304: %', v_x using errcode = 'P0001';
    end if;
  else
    foreach v_i in array v.pessoas loop
      v_x := public.radar_video_pessoa_falta(v_i, p.id);
      if v_x = 'pessoa não cadastrada' or v_x like 'menor de idade%' then
        raise exception 'RADAR304: %', v_x using errcode = 'P0001';
      end if;
    end loop;
  end if;
  update public.radar_videos set situacao = 'substituido', encerrado_em = now(), pego_em = null
   where peca_id = p.id and id <> v.id and situacao in ('na_fila','processando','pronto','regravar','erro');
  update public.radar_videos set situacao = 'na_fila', enviado_em = now(), fila_em = now(), reservas = 0, pessoas = v.pessoas where id = v.id;
  return jsonb_build_object('id', v.id, 'situacao', 'na_fila');
end $$;

revoke all on function public.radar_video_criar(bigint, jsonb, bigint, text, text[], boolean, text[], numeric, boolean) from public, anon;
grant execute on function public.radar_video_criar(bigint, jsonb, bigint, text, text[], boolean, text[], numeric, boolean) to authenticated;

select 'v0.74.0 aplicada: enviar mesmo assim (assumir do administrador)' as resultado;
