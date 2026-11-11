-- =====================================================================
-- Radar Artecon — v0.78.0: a CAPA-ARTE AUTOMÁTICA do reel (o molde aprovado pelo dono em 10/11/2026).
-- Rode no Supabase (SQL Editor). Pode rodar de novo. Supõe o sql/radar-video-assumir-v0.74.0.sql aplicado.
--
-- O que muda:
--   * radar_video_ajustes_falta aceita a chave nova "capa" ({linhas, categoria, subtitulo}): é o título da capa que o
--     robô desenha no molde (painel diagonal marinho, friso amarelo, logotipo oficial, última linha do título em
--     amarelo). O administrador pode trocá-la depois pela aba Vídeo (radar_video_ajustar), como qualquer ajuste;
--   * radar_video_criar ganha p_capa (jsonb, opcional): a tela manda o título que a IA Central escreveu no envio (ou o
--     de reserva), e ele nasce em radar_videos.ajustes.capa — o robô o recebe no pedido e desenha a capa sozinho,
--     escolhendo o quadro mais nítido quando o editor não escolheu um (capa_q).
-- Nada é apagado. Sem a tela/robô novos, o parâmetro simplesmente não é usado.
-- =====================================================================

drop function if exists public.radar_video_criar(bigint, jsonb, bigint, text, text[], boolean, text[], numeric, boolean);

create or replace function public.radar_video_ajustes_falta(p jsonb) returns text
language plpgsql immutable set search_path = public as $$
declare
  k   text;
  x   jsonb;
  pal constant jsonb := public.radar_video_paleta();
begin
  if p is null or jsonb_typeof(p) <> 'object' or length(p::text) > 20000 then return 'os ajustes vão num objeto de até 20.000 caracteres'; end if;
  if exists (select 1 from jsonb_object_keys(p) c
              where c not in ('manter','transcricao_errou','aceitas','legenda','estilo','sem_gancho',
                              'cortar','inicio_q','fim_q','capa_q','legenda_tamanho','legenda_posicao','legenda_cor','cartela_extra','capa')) then
    return 'ajuste desconhecido';
  end if;
  -- (cada conferência só depois da forma: jsonb_array_elements e jsonb_each não rodam sobre o que não é lista nem objeto)
  -- v0.40.0: aceitas — as divergências aceitas ("quis dizer o mesmo"), a mesma forma de transcricao_errou
  foreach k in array array['manter','transcricao_errou','aceitas'] loop
    continue when not p ? k;
    x := p->k;
    if jsonb_typeof(x) <> 'array' or jsonb_array_length(x) > 200
       or exists (select 1 from jsonb_array_elements(x) y
                   where jsonb_typeof(y) <> 'string'
                      or (y #>> '{}') !~ case k when 'manter' then '^[0-9]{1,2}:[0-9]{1,6}b{0,3}$' else '^[0-9a-f]{16}$' end) then
      return k || case k when 'manter' then ': uma lista de até 200 chaves de corte do relatório ("clipe:quadro")'
                         else ': uma lista de até 200 códigos de divergência do relatório' end;
    end if;
  end loop;
  if p ? 'legenda' then
    x := p->'legenda';
    if jsonb_typeof(x) = 'array' then                   -- cada item [chave, texto] (o case confere a forma antes do resto)
      if jsonb_array_length(x) > 200
         or exists (select 1 from jsonb_array_elements(x) y
                     where case when jsonb_typeof(y) <> 'array' then true
                                when jsonb_array_length(y) <> 2 then true
                                when jsonb_typeof(y->0) <> 'string' or jsonb_typeof(y->1) <> 'string' then true
                                else (y->>0) !~ '^[0-9]{1,4}(:[0-9]{1,3})?$' or length(btrim(y->>1)) not between 1 and 120
                                     or (y->>1) ~ '[{}\\<>[:cntrl:]]' end) then
        return 'legenda: até 200 blocos ("u" ou "u:n"), cada um com um texto de 1 a 120 caracteres, sem { } \ < > nem caractere de controle';
      end if;
    elsif jsonb_typeof(x) <> 'object' then
      return 'legenda: até 200 blocos ("u" ou "u:n"), cada um com um texto de 1 a 120 caracteres, sem { } \ < > nem caractere de controle';
    elsif (select count(*) from jsonb_object_keys(x)) > 200
       or exists (select 1 from jsonb_each(x) w
                   where w.key !~ '^[0-9]{1,4}(:[0-9]{1,3})?$' or jsonb_typeof(w.value) <> 'string'
                      or length(btrim(w.value #>> '{}')) not between 1 and 120 or (w.value #>> '{}') ~ '[{}\\<>[:cntrl:]]') then
      return 'legenda: até 200 blocos ("u" ou "u:n"), cada um com um texto de 1 a 120 caracteres, sem { } \ < > nem caractere de controle';
    end if;
  end if;
  if p ? 'estilo' and (jsonb_typeof(p->'estilo') <> 'string' or p->>'estilo' not in ('normal','compacta')) then
    return 'estilo: normal ou compacta';
  end if;
  if p ? 'sem_gancho' and jsonb_typeof(p->'sem_gancho') <> 'boolean' then return 'sem_gancho: sim ou não'; end if;
  -- v0.33.0: o editor da aba Vídeo
  if p ? 'cortar' then
    x := p->'cortar';
    if jsonb_typeof(x) <> 'array' or jsonb_array_length(x) > 30
       or exists (select 1 from jsonb_array_elements(x) y
                   where case when jsonb_typeof(y) <> 'array' then true
                              when jsonb_array_length(y) <> 2 then true
                              when jsonb_typeof(y->0) <> 'number' or jsonb_typeof(y->1) <> 'number' then true
                              when (y->>0) !~ '^[0-9]{1,4}$' or (y->>1) !~ '^[0-9]{1,4}$' then true
                              else (y->>1)::int > 29000 or (y->>1)::int - (y->>0)::int < 3 end) then
      return 'cortar: até 30 trechos [começo, fim] em quadros (inteiros de 0 a 29000, cada um com 3 quadros ou mais)';
    end if;
  end if;
  foreach k in array array['inicio_q','fim_q','capa_q'] loop
    continue when not p ? k;
    if jsonb_typeof(p->k) <> 'number' or (p->>k) !~ '^[0-9]{1,5}$' or (p->>k)::int > 29000 then
      return k || ': um quadro do vídeo (inteiro de 0 a 29000)';
    end if;
  end loop;
  if p ? 'legenda_tamanho' and (jsonb_typeof(p->'legenda_tamanho') <> 'string'
       or not exists (select 1 from jsonb_array_elements(pal->'tamanhos') t where t->>'chave' = p->>'legenda_tamanho')) then
    return 'tamanho da legenda: pequena, média ou grande';
  end if;
  if p ? 'legenda_posicao' and (jsonb_typeof(p->'legenda_posicao') <> 'string'
       or not exists (select 1 from jsonb_array_elements(pal->'posicoes') t where t->>'chave' = p->>'legenda_posicao')) then
    return 'posição da legenda: em cima, no meio ou embaixo';
  end if;
  if p ? 'legenda_cor' and (jsonb_typeof(p->'legenda_cor') <> 'string'
       or not exists (select 1 from jsonb_array_elements(pal->'cores') t where t->>'chave' = p->>'legenda_cor')) then
    return 'cor da legenda fora da paleta da Artecon';
  end if;
  if p ? 'cartela_extra' and (jsonb_typeof(p->'cartela_extra') <> 'string' or length(p->>'cartela_extra') > 120
                              or (p->>'cartela_extra') ~ '[{}\\<>[:cntrl:]]') then
    return 'texto extra da cartela: até 120 caracteres, sem { } \ < > nem quebra de linha';
  end if;
  -- v0.46.0 do corretor: a CAPA-ARTE automática ({linhas, categoria, subtitulo}), escrita no envio (radar_video_criar)
  -- e editável pelo administrador; o robô desenha o molde com ela
  if p ? 'capa' then
    x := p->'capa';
    if jsonb_typeof(x) = 'null' then
      null;                                            -- "capa": null tira a capa-arte (o ajustar mescla; sem a marca, a de antes ficaria)
    elsif jsonb_typeof(x) <> 'object'
       or exists (select 1 from jsonb_object_keys(x) c where c not in ('linhas','categoria','subtitulo'))
       or jsonb_typeof(x->'linhas') <> 'array' or jsonb_array_length(x->'linhas') not between 1 and 3
       or exists (select 1 from jsonb_array_elements(x->'linhas') y
                   where jsonb_typeof(y) <> 'string' or length(btrim(y #>> '{}')) not between 1 and 18
                      or (y #>> '{}') ~ '[{}\\[:cntrl:]]')
       or (x ? 'categoria' and (jsonb_typeof(x->'categoria') <> 'string' or length(x->>'categoria') > 24
                                or (x->>'categoria') ~ '[{}\\[:cntrl:]]'))
       or (x ? 'subtitulo' and (jsonb_typeof(x->'subtitulo') <> 'string' or length(x->>'subtitulo') > 48
                                or (x->>'subtitulo') ~ '[{}\\[:cntrl:]]')) then
      return 'capa: linhas (1 a 3, cada uma de 1 a 18 caracteres), categoria (até 24) e subtitulo (até 48), sem { } \ nem caractere de controle';
    end if;
  end if;
  return null;
end $$;

create or replace function public.radar_video_criar(p_peca bigint, p_partes jsonb, p_fala_pessoa bigint, p_fala_roteiro text,
                                                    p_cartela text[], p_gancho boolean, p_declaracoes text[], p_duracao numeric default null,
                                                    p_assumir boolean default false,
                                                    p_capa jsonb default null)
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
  -- v0.78.0: a CAPA-ARTE automática (as linhas do título, a categoria e o subtítulo que o robô desenha no molde)
  if p_capa is not null then
    v_x := public.radar_video_ajustes_falta(jsonb_build_object('capa', p_capa));
    if v_x is not null then
      raise exception 'RADAR356: %', v_x using errcode = 'P0001';
    end if;
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
                                   enviado_por, assumido_em, assumido_por, ajustes)
  values (p.id, v_versao, v_partes, p_fala_pessoa, p.pessoas, v_fala, public.radar_hash_texto(p.roteiro),
          array(select btrim(l) from unnest(p_cartela) with ordinality t(l, o) order by o),
          case when coalesce(p_gancho, false) then btrim(p.chamada) end,
          array(select d from unnest(v_decl) d), auth.uid(),
          case when coalesce(p_assumir, false) then now() end, case when coalesce(p_assumir, false) then auth.uid() end,
          coalesce(jsonb_strip_nulls(jsonb_build_object('capa', p_capa)), '{}'::jsonb))
  returning id into v_id;
  return jsonb_build_object('id', v_id, 'versao', v_versao);
end $$;

revoke all on function public.radar_video_criar(bigint, jsonb, bigint, text, text[], boolean, text[], numeric, boolean, jsonb) from public, anon;
grant execute on function public.radar_video_criar(bigint, jsonb, bigint, text, text[], boolean, text[], numeric, boolean, jsonb) to authenticated;

select 'v0.78.0 aplicada: capa-arte automática (p_capa + ajustes.capa)' as resultado;
