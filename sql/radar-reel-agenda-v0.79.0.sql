-- =====================================================================
-- Radar Artecon — v0.79.0: o REEL SAI PELA AGENDA (publicação automática no Instagram e no Facebook).
-- Rode no Supabase (SQL Editor). Pode rodar de novo. Supõe o sql/radar-capa-v0.78.0.sql aplicado.
--
-- O que muda:
--   * radar_pauta_aprovar aceita o modo "agendar" na peça em formato reel (antes só à mão): o envio nasce por canal, como na
--     imagem e no carrossel, e a agenda do banco (pg_cron, sql/radar-redes-agenda.sql) publica na hora marcada. O vídeo que sai
--     é o amarrado na aprovação (video_id + video_sha256: o que o administrador viu). O Facebook só aceita reel de até 90
--     segundos: acima disso, a aprovação agendada com o Facebook marcado é recusada (RADAR318) — Instagram vai até 15 minutos;
--   * radar_pauta_pode_sair, no reel, confere o vídeo em vez da imagem: o amarrado tem de continuar pronto, com o mesmo sha256
--     e sem 'corrigido' apagado pela limpeza; no Facebook, os 90 s valem de novo. O que não puder sair vira "erro" com o motivo
--     (o aviso "Não saíram" de sempre);
--   * radar_pauta_iniciar devolve também, no reel, o caminho do vídeo aprovado (corrigido/<id>/<sha256>.mp4), o da capa
--     desenhada (quadros/<id>/<sha256>/capa-<sha256 da capa>.jpg, quando há) e a duração — a função radar-redes v0.46.0 assina
--     os caminhos (bucket privado radar-videos, link temporário) e publica: Instagram por contêiner REELS, Facebook por
--     video_reels em 3 fases. Nada fica público: a Meta baixa por link assinado e o endereço não é gravado.
-- Nada é apagado. Sem a tela/função novas, nada muda (o reel continua saindo à mão).
-- =====================================================================

-- Aprovação (só o administrador). Confere de novo tudo (radar_pauta_problemas, com o dia da peça), as caixas de conferência, as
-- lâminas desenhadas na tela dele e guardadas agora em radar_imagens (o que se aprova é o que ele viu) e a hora. Modo "agendar"
-- (imagem única, carrossel e, v0.79.0, o reel): um envio por canal, que a agenda do banco publica na hora marcada. Modo "manual":
-- não cria envio; libera baixar e copiar, só nos canais aprovados (aprovado_canais).
-- v0.22.0: no reel, p_video_sha256 é o hash do vídeo corrigido que a tela mostrou: tem de ser o do vídeo pronto, e a peça fica amarrada
-- a ele (video_id, video_sha256); pede a caixa "video" e, se alguma pessoa marcada quer ver a peça antes (termo), a caixa "viu".
-- v0.79.0: o reel também sai pela agenda; no Facebook, só até 90 segundos (RADAR318).
create or replace function public.radar_pauta_aprovar(p_peca bigint, p_lido timestamptz, p_canais text[], p_modo text, p_artes bigint[],
                                                      p_arte_identificacao text, p_conferencias text[], p_video_sha256 text default null)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  v_vid    public.radar_videos%rowtype;
  p        public.radar_pauta_pecas%rowtype;
  v_canais text[];
  v_conf   text[] := coalesce(p_conferencias, '{}');
  v_artes  bigint[] := coalesce(p_artes, '{}');
  v_prob   text[];
  v_qtd    int;
  v_janela int := public.radar_pauta_janela();
  v_quando timestamptz;
  v_img    text;
  v_canal  text;
  v_id     bigint;
  v_ids    jsonb := '{}'::jsonb;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR159: só o administrador aprova a peça da Pauta' using errcode = '42501';
  end if;
  select * into p from public.radar_pauta_pecas where id = p_peca for update;
  if p.id is null then
    raise exception 'RADAR160: peça não encontrada' using errcode = 'P0001';
  end if;
  if p_lido is distinct from p.atualizado_em then
    raise exception 'RADAR161: a peça foi alterada depois que a tela foi aberta: recarregue, confira e aprove de novo' using errcode = 'P0001';
  end if;
  if p.situacao <> 'pronta' then
    raise exception 'RADAR164: só a peça pronta é aprovada (situação atual: %)', p.situacao using errcode = 'P0001';
  end if;
  if p_modo is null or p_modo not in ('agendar','manual') then
    raise exception 'RADAR164: escolha entre agendar e publicar à mão' using errcode = 'P0001';
  end if;
  -- v0.42.0: o carrossel (e o carrossel de fotos) também sai pela agenda; v0.79.0: o reel também
  if p_modo = 'agendar' and p.formato not in ('imagem','foto','carrossel','carrossel_fotos','reel') then
    raise exception 'RADAR164: este formato sai à mão (escolha “Vou publicar à mão”)' using errcode = 'P0001';
  end if;
  select coalesce(array_agg(distinct c), '{}') into v_canais from unnest(coalesce(p_canais, '{}')) c;
  v_prob := public.radar_pauta_problemas(p.id, v_canais, p.data);
  if cardinality(v_prob) > 0 then
    raise exception 'RADAR165: há % ponto(s) a resolver: a lista aparece na tela', cardinality(v_prob) using errcode = 'P0001';
  end if;
  -- as caixas que o administrador marca na tela (o que está na foto só ele sabe). A das pessoas vale para toda peça: o nome de
  -- alguém escrito de um jeito que a lista não reconhece (em minúsculas, com erro de digitação) só o olho de quem aprova pega
  if not 'pessoas' = any(v_conf) then
    raise exception 'RADAR166: marque “Conferi: nas fotos e nos textos só aparecem as pessoas marcadas”' using errcode = 'P0001';
  end if;
  if p.tipo = 'agenda' and not 'datas' = any(v_conf) then
    raise exception 'RADAR166: marque “Conferi as datas da agenda”' using errcode = 'P0001';
  end if;
  if not 'rede' = any(v_conf)
     and exists (select 1 from public.radar_redes_envios e where e.peca_id = p.id and e.canal = any(v_canais)
                  and e.situacao = 'cancelado' and e.enviado_em is not null and e.post_id is null) then
    raise exception 'RADAR166: uma publicação desta peça foi cancelada no meio do envio: confira no Instagram e no Facebook que ela não saiu e marque “Conferi no Instagram e no Facebook: não saiu”'
      using errcode = 'P0001';
  end if;
  -- a aprovação à mão foi desfeita: a peça pode ter sido postada sem o link registrado (o administrador confere antes de aprovar de novo)
  if not 'rede' = any(v_conf) and p.manual_desfeita_em is not null then
    raise exception 'RADAR166: esta peça já foi aprovada para publicar à mão: confira no Instagram e no Facebook que ela não foi postada e marque “Conferi no Instagram e no Facebook: não saiu”'
      using errcode = 'P0001';
  end if;
  -- v0.22.0: o reel sai com o vídeo que o administrador viu (o pronto, pelo hash) e as caixas do vídeo
  if p.formato = 'reel' then
    select * into v_vid from public.radar_videos
     where peca_id = p.id and situacao in ('na_fila','processando','pronto','regravar','erro') for update;
    if v_vid.id is null or v_vid.situacao <> 'pronto' or v_vid.sha256 is null or p_video_sha256 is distinct from v_vid.sha256
       or 'corrigido' = any(v_vid.arquivos_apagados) then
      raise exception 'RADAR313: o vídeo da aprovação não é o vídeo corrigido pronto desta peça: recarregue a prévia, confira e aprove de novo'
        using errcode = 'P0001';
    end if;
    if not 'video' = any(v_conf) then
      raise exception 'RADAR314: marque “Conferi o vídeo: só aparecem as pessoas marcadas; sem tela, documento ou cliente ao fundo; só a voz”'
        using errcode = 'P0001';
    end if;
    if not 'viu' = any(v_conf) and exists (select 1 from public.radar_pessoas pe where pe.id = any(p.pessoas || v_vid.pessoas) and pe.quer_ver_peca) then
      raise exception 'RADAR314: uma pessoa da peça pediu, no termo, para ver a peça antes: mostre o vídeo final e marque “A pessoa viu o vídeo final”'
        using errcode = 'P0001';
    end if;
    -- v0.79.0: o Facebook só aceita reel de 3 a 90 segundos; o Instagram vai até 15 minutos (o teto do corretor)
    if p_modo = 'agendar' and 'facebook' = any(v_canais) and coalesce(v_vid.duracao_final, 0) > 90 then
      raise exception 'RADAR318: o Facebook só aceita reel de até 90 segundos (este tem % s): desmarque o Facebook (o Instagram aceita até 15 minutos) ou escolha publicar à mão',
        round(coalesce(v_vid.duracao_final, 0)) using errcode = 'P0001';
    end if;
  end if;
  -- as lâminas: uma por imagem ou foto, capa + uma por cartão no carrossel, uma por foto no carrossel de fotos, nenhuma no reel;
  -- JPEG 1080×1350 enviado agora (há até 2 horas) por quem aprova; a identificação desenhada nelas é a das Configurações
  v_qtd := case p.formato when 'imagem' then 1 when 'foto' then 1 when 'carrossel' then 1 + jsonb_array_length(p.cartoes)
                          when 'carrossel_fotos' then cardinality(p.fotos) else 0 end;
  if cardinality(v_artes) <> v_qtd or (select count(distinct a) from unnest(v_artes) a) <> v_qtd
     or exists (select 1 from unnest(v_artes) a
                 where not exists (select 1 from public.radar_imagens i
                                    where i.id = a and i.dados like 'data:image/jpeg;base64,%' and i.largura = 1080 and i.altura = 1350
                                      and i.criado_por = auth.uid() and i.criado_em > now() - interval '2 hours'))
     or public.radar_pauta_identificacao_falta(p_arte_identificacao) is not null then
    raise exception 'RADAR163: as lâminas da aprovação não conferem (quantidade, JPEG 1080×1350 enviado agora por você, identificação legal das Configurações): desenhe e aprove de novo'
      using errcode = 'P0001';
  end if;
  if p_modo = 'agendar' then
    if p.tipo = 'agenda' and public.radar_pauta_hoje() > p.data + 1 then
      raise exception 'RADAR168: a agenda da semana ficou velha (passou a segunda-feira)' using errcode = 'P0001';
    end if;
    v_quando := (p.data + p.hora) at time zone 'America/Sao_Paulo';
    if v_quando < now() - make_interval(hours => v_janela) then
      raise exception 'RADAR167: a hora marcada (% de Brasília) passou há mais de % horas: mude a hora', to_char(p.data + p.hora, 'DD/MM/YYYY HH24:MI'), v_janela
        using errcode = 'P0001';
    end if;
    if v_quando < now() then
      v_quando := now();                                    -- passou há pouco: sai na próxima rodada da agenda
    end if;
    if v_quando > now() + interval '120 days' then
      raise exception 'RADAR167: a hora marcada fica a mais de 120 dias: aprove mais perto do dia' using errcode = 'P0001';
    end if;
  end if;
  perform set_config('radar.pauta', '1', true);
  update public.radar_pauta_pecas
     set situacao = 'aprovada', aprovado_por = auth.uid(), aprovado_em = now(), aprovado_modo = p_modo,
         aprovado_conferencias = array(select distinct c from unnest(v_conf) c where c in ('pessoas','datas','rede','video','viu') order by c),
         aprovado_canais = array_remove(array[case when 'instagram' = any(v_canais) then 'instagram' end,      -- na ordem da tela
                                              case when 'facebook' = any(v_canais) then 'facebook' end], null),
         manual_desfeita_em = null,
         artes = v_artes, arte_identificacao = left(btrim(p_arte_identificacao), 300),
         video_id = v_vid.id, video_sha256 = v_vid.sha256                         -- v0.22.0: nulos fora do reel
   where id = p.id;
  perform set_config('radar.pauta', '', true);
  if p_modo = 'agendar' then
    -- v0.42.0: no carrossel, o envio leva as lâminas por referência (artes; a lâmina aprovada não muda e a faxina não a apaga);
    -- na imagem única, a cópia da lâmina, como antes; v0.79.0: no reel, nada aqui (o vídeo sai pela amarra da peça: video_id + video_sha256)
    if p.formato in ('carrossel','carrossel_fotos','reel') then
      v_img := null;
    else
      select i.dados into v_img from public.radar_imagens i where i.id = v_artes[1];
    end if;
    foreach v_canal in array v_canais loop
      begin
        insert into public.radar_redes_envios (peca_id, canal, legenda, imagem, artes, conteudo_lido_em, situacao, autorizado_por, agendado_para)
        values (p.id, v_canal, btrim(case v_canal when 'instagram' then p.legenda_instagram else p.legenda_facebook end), v_img,
                case when p.formato in ('carrossel','carrossel_fotos') then v_artes else '{}' end,
                p.versao_publicavel, 'autorizado', auth.uid(), v_quando)
        returning id into v_id;
      exception when unique_violation then
        raise exception 'RADAR170: já há publicação aberta (ou feita) desta peça no %', initcap(v_canal) using errcode = 'P0001';
      end;
      v_ids := v_ids || jsonb_build_object(v_canal, v_id);
    end loop;
  end if;
  return jsonb_build_object('agendado_para', v_quando, 'envios', v_ids);
end $$;

-- Conferência curta, logo antes de disparar e de novo no início do envio: devolve o primeiro motivo para a peça NÃO sair (ou
-- NULL). Sem nome de pessoa: o texto vai para radar_redes_envios.erro.
-- v0.79.0: no reel, o que se confere é o vídeo amarrado na aprovação (não a imagem): pronto, com o mesmo sha256 e com o arquivo
-- corrigido ainda guardado; no Facebook, o limite de 90 segundos vale de novo.
create or replace function public.radar_pauta_pode_sair(p_envio bigint) returns text
language plpgsql stable security definer set search_path = public as $$
declare
  e        public.radar_redes_envios%rowtype;
  p        public.radar_pauta_pecas%rowtype;
  v        public.radar_videos%rowtype;
  v_hoje   date := public.radar_pauta_hoje();
  v_janela int := public.radar_pauta_janela();
  v_id     bigint;
  v_x      text;
begin
  select * into e from public.radar_redes_envios where id = p_envio;
  select * into p from public.radar_pauta_pecas where id = e.peca_id;
  if p.id is null then
    return 'A publicação não é de uma peça da Pauta.';
  end if;
  if p.situacao <> 'aprovada' or p.aprovado_modo is distinct from 'agendar' then
    return 'A peça não está aprovada para sair pela agenda.';
  end if;
  if p.versao_publicavel is distinct from e.conteudo_lido_em then
    return 'A peça mudou depois de aprovada: confira e aprove de novo.';
  end if;
  if now() > e.agendado_para + make_interval(hours => v_janela) then
    return format('Passaram mais de %s horas da hora marcada: a publicação não sai atrasada sozinha. Use Publicar agora ou desfaça a aprovação.', v_janela);
  end if;
  if p.tipo = 'agenda' and v_hoje > p.data + 1 then
    return 'A agenda da semana ficou velha (passou a segunda-feira).';
  end if;
  foreach v_id in array p.pessoas loop
    v_x := public.radar_pauta_termo_ok(v_id, p.tipo, e.canal, v_hoje);
    if v_x is not null then
      return format('O termo de uso de imagem de uma pessoa da peça não vale em %s (%s): confira em Pauta → Pessoas e termos.', to_char(v_hoje, 'DD/MM/YYYY'), v_x);
    end if;
  end loop;
  if public.radar_marcas_verificar(e.legenda) is not null or e.legenda ~* '\{\s*confirmar[^}]*\}' or e.legenda ~ '\{[^{}\n]{1,120}\}' then
    return 'A legenda tem ponto marcado com [VERIFICAR], {confirmar} ou outro marcador entre chaves: desfaça a aprovação e corrija.';
  end if;
  -- v0.79.0: o reel sai com o vídeo amarrado na aprovação (não há imagem)
  if p.formato = 'reel' then
    select * into v from public.radar_videos where id = p.video_id;
    if v.id is null or v.sha256 is null or v.sha256 is distinct from p.video_sha256 or v.situacao <> 'pronto'
       or 'corrigido' = any(v.arquivos_apagados) then
      return 'O vídeo aprovado do reel não está mais disponível (foi substituído ou apagado): desfaça a aprovação, confira e aprove de novo.';
    end if;
    if e.canal = 'facebook' and coalesce(v.duracao_final, 0) > 90 then
      return 'O Facebook só aceita reel de até 90 segundos: desfaça a aprovação e publique à mão no Facebook (ou só no Instagram).';
    end if;
  -- v0.42.0: no carrossel, as imagens do post são as lâminas (artes)
  elsif cardinality(e.artes) > 0 then
    if exists (select 1 from unnest(e.artes) a
                where not exists (select 1 from public.radar_imagens i where i.id = a and i.dados like 'data:image/jpeg;base64,%')) then
      return 'As lâminas da publicação se perderam: desfaça a aprovação e aprove de novo.';
    end if;
  elsif e.imagem is null and e.imagem_url is null then
    return 'A imagem da publicação se perdeu: desfaça a aprovação e aprove de novo.';
  end if;
  return null;
end $$;

-- A função radar-redes pega o envio da peça para publicar: uma vez só (autorizado → enviando, com a peça e o envio
-- travados, nessa ordem), na hora marcada, e conferindo tudo de novo. O problema vira "erro" (contado e avisado), nunca
-- "cancelado" calado. Qualquer exceção aqui desfaz tudo: nada foi ao armazenamento nem à Meta (o envio da imagem vem depois).
-- v0.79.0: no reel, devolve também o caminho do vídeo aprovado no bucket radar-videos (corrigido/<id>/<sha256>.mp4), o da capa
-- desenhada (quando há) e a duração; a função radar-redes assina os caminhos e publica (contêiner REELS / video_reels).
create or replace function public.radar_pauta_iniciar(p_envio bigint) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_peca    bigint;
  p         public.radar_pauta_pecas%rowtype;
  v         public.radar_videos%rowtype;
  e         public.radar_redes_envios%rowtype;
  v_imagens jsonb;
  v_video   text;
  v_capa    text;
  v_motivo  text;
begin
  select peca_id into v_peca from public.radar_redes_envios where id = p_envio;     -- sem trava: a ordem é peça, depois envio
  if v_peca is null then
    raise exception 'RADAR138: esta autorização não está aguardando envio (já saiu, foi cancelada ou está saindo)' using errcode = 'P0001';
  end if;
  select * into p from public.radar_pauta_pecas where id = v_peca for update;
  select * into e from public.radar_redes_envios where id = p_envio for update;
  if e.situacao is distinct from 'autorizado' then          -- "erro" só volta por radar_pauta_publicar_agora (do administrador)
    raise exception 'RADAR138: esta autorização não está aguardando envio (já saiu, foi cancelada ou está saindo)' using errcode = 'P0001';
  end if;
  if e.agendado_para > now() then
    raise exception 'RADAR172: ainda não é a hora: agendada para % (Brasília)', to_char(e.agendado_para at time zone 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI')
      using errcode = 'P0001';
  end if;
  v_motivo := public.radar_pauta_pode_sair(p_envio);
  if v_motivo is not null then
    update public.radar_redes_envios set situacao = 'erro', erro = left(v_motivo, 1000), atualizado_em = now() where id = p_envio;
    return jsonb_build_object('erro', v_motivo);
  end if;
  -- v0.42.0: no carrossel, as lâminas aprovadas (artes), na ordem do post (pode_sair, acima, já conferiu que estão todas)
  if cardinality(e.artes) > 0 then
    select jsonb_agg(i.dados order by a.ord) into v_imagens
      from unnest(e.artes) with ordinality a(id, ord)
      join public.radar_imagens i on i.id = a.id;
  end if;
  -- v0.79.0: o reel — o vídeo amarrado na aprovação (pode_sair, acima, conferiu que ele continua pronto e guardado) e a capa
  if p.formato = 'reel' then
    select * into v from public.radar_videos where id = p.video_id;
    v_video := format('corrigido/%s/%s.mp4', v.id, v.sha256);
    if (v.relatorio->'capa'->>'sha256') ~ '^[0-9a-f]{64}$' then
      v_capa := format('quadros/%s/%s/capa-%s.jpg', v.id, v.sha256, v.relatorio->'capa'->>'sha256');
    end if;
  end if;
  update public.radar_redes_envios set situacao = 'enviando', enviado_em = now(), erro = null, retentar_em = null, atualizado_em = now()
   where id = p_envio;                                             -- v0.43.0: a nova tentativa marcada é esta (a marca sai)
  return jsonb_build_object('id', e.id, 'canal', e.canal, 'conteudo_id', null, 'peca_id', e.peca_id, 'legenda', e.legenda,
                            'imagem', e.imagem, 'imagem_url', e.imagem_url,
                            'imagens', v_imagens, 'imagens_urls', case when cardinality(e.imagens_urls) > 0 then to_jsonb(e.imagens_urls) end,
                            'video_caminho', v_video, 'video_capa', v_capa,
                            'video_duracao', case when p.formato = 'reel' then v.duracao_final end);
end $$;

select 'v0.79.0 aplicada: o reel sai pela agenda (aprovar/pode_sair/iniciar)' as resultado;
