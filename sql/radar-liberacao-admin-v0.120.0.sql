-- Radar Artecon — migração v0.120.0: liberação do administrador na Pauta (publicar com ponto de publicidade/CFC ou número sem fonte).
-- Aditiva e idempotente (pode rodar de novo). O banco segue registrado como v0.50.0 (rode o radar-setup-v0.50.0.sql tem o mesmo efeito).

-- 1) a coluna de registro da liberação (motivo, por, em, pontos)
alter table public.radar_pauta_pecas add column if not exists liberacao    jsonb;

-- 2) o gatilho da peça: nasce sem liberação e limpa a liberação quando o conteúdo muda
create or replace function public.radar_fn_pauta_peca() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_funcao boolean := coalesce(current_setting('radar.pauta', true), '') = '1';
  v_mudou  boolean := false;      -- mudou o que vai ao ar
  v_novas  bigint[];              -- as pessoas acrescentadas agora
begin
  if tg_op = 'INSERT' then
    -- toda peça nasce planejada, sem aprovação, sem lâminas e sem registro (vale também para a importação)
    new.situacao := 'planejada';
    new.aprovado_por := null; new.aprovado_em := null; new.aprovado_modo := null; new.aprovado_conferencias := '{}';
    new.aprovado_canais := '{}'; new.manual_desfeita_em := null;
    new.artes := '{}'; new.arte_identificacao := null; new.link_instagram := null; new.link_facebook := null;
    new.publicado_manual_em := null; new.publicado_manual_por := null;
    new.video_id := null; new.video_sha256 := null;                                    -- v0.22.0: só a aprovação amarra o vídeo
    new.liberacao := null;                                                             -- v0.120.0: nasce sem liberação do administrador
    new.versao_publicavel := now(); new.criado_por := auth.uid(); new.criado_em := now();
    v_novas := new.pessoas;
  else
    new.criado_por := public.radar_manter_usuario(old.criado_por, new.criado_por);
    new.criado_em  := old.criado_em;
    -- v0.64.0: "data" saiu daqui — mudar o dia não é mexer no que vai ao ar (a Conferência continua valendo)
    v_mudou := new.tipo is distinct from old.tipo or new.formato is distinct from old.formato
            or new.chamada is distinct from old.chamada or new.apoio is distinct from old.apoio or new.cartoes is distinct from old.cartoes
            or new.roteiro is distinct from old.roteiro or new.legenda_instagram is distinct from old.legenda_instagram
            or new.legenda_facebook is distinct from old.legenda_facebook or new.fotos is distinct from old.fotos
            or new.pessoas is distinct from old.pessoas or new.conferidas is distinct from old.conferidas;
    if not v_funcao then
      -- o que só as funções mudam fica como estava (quem aprovou ou registrou só vira nulo se o usuário foi excluído)
      new.aprovado_por := public.radar_manter_usuario(old.aprovado_por, new.aprovado_por);
      new.aprovado_em := old.aprovado_em; new.aprovado_modo := old.aprovado_modo; new.aprovado_conferencias := old.aprovado_conferencias;
      new.aprovado_canais := old.aprovado_canais; new.manual_desfeita_em := old.manual_desfeita_em;
      new.artes := old.artes; new.arte_identificacao := old.arte_identificacao;
      new.video_id := old.video_id; new.video_sha256 := old.video_sha256;            -- v0.22.0
      new.link_instagram := old.link_instagram; new.link_facebook := old.link_facebook;
      new.publicado_manual_em := old.publicado_manual_em;
      new.publicado_manual_por := public.radar_manter_usuario(old.publicado_manual_por, new.publicado_manual_por);
      new.versao_publicavel := old.versao_publicavel;
      if old.situacao = 'aprovada' then
        -- v0.64.0: a data entra na trava por extenso (o dia da aprovada muda só por radar_pauta_mudar_data)
        if v_mudou or new.data is distinct from old.data or new.hora is distinct from old.hora or new.situacao is distinct from old.situacao then
          raise exception 'RADAR162: a peça está aprovada: para mudar, use Desfazer aprovação (o administrador pode mudar só o dia em "Mudar o dia e a hora")' using errcode = 'P0001';
        end if;
      elsif old.situacao = 'cancelada' then
        if v_mudou or new.data is distinct from old.data or new.hora is distinct from old.hora then
          raise exception 'RADAR162: a peça está cancelada: para mudar, use Reabrir' using errcode = 'P0001';
        end if;
        if new.situacao not in ('cancelada','planejada') then
          raise exception 'RADAR159: a peça cancelada só volta a planejada (Reabrir)' using errcode = 'P0001';
        end if;
      elsif new.situacao is distinct from old.situacao
            and not (new.situacao = 'cancelada' or (old.situacao = 'pronta' and new.situacao = 'em_producao')) then
        raise exception 'RADAR159: esta mudança de situação só é feita pelos botões da Pauta (Salvar e marcar como pronta, Aprovar)'
          using errcode = 'P0001';
      elsif v_mudou and new.situacao in ('planejada','pronta') then
        new.situacao := 'em_producao';            -- mexeu no que vai ao ar: vai (ou volta) para a produção
      end if;
    end if;
    if v_mudou then
      new.versao_publicavel := now();
      new.liberacao := null;                           -- v0.120.0: mudou o que vai ao ar: a liberação do administrador não vale mais
    end if;
    v_novas := array(select x from unnest(new.pessoas) x where not x = any(old.pessoas));
  end if;
  -- pessoa e foto: nada repetido; a pessoa acrescentada está cadastrada e ativa (quem já estava fica, mesmo inativa); a foto existe
  if (select count(*) <> count(distinct x) from unnest(new.pessoas) x) or (select count(*) <> count(distinct x) from unnest(new.fotos) x)
     or (select count(*) <> count(distinct x) from unnest(new.artes) x) then
    raise exception 'RADAR176: pessoa ou foto repetida na peça' using errcode = 'P0001';
  end if;
  if exists (select 1 from unnest(v_novas) x where not exists (select 1 from public.radar_pessoas pe where pe.id = x and pe.ativo)) then
    raise exception 'RADAR176: pessoa que não está cadastrada (ou não está ativa) em Pauta → Pessoas e termos' using errcode = 'P0001';
  end if;
  if (tg_op = 'INSERT' or new.fotos is distinct from old.fotos)
     and exists (select 1 from unnest(new.fotos) x where not exists (select 1 from public.radar_imagens i where i.id = x)) then
    raise exception 'RADAR176: foto que não está mais no banco: envie de novo' using errcode = 'P0001';
  end if;
  return new;
end $$;

-- 3) os pontos SEM liberação (bloqueios): tudo, menos o número sem fonte
create or replace function public.radar_pauta_bloqueios(p_peca bigint, p_canais text[], p_data date) returns text[]
language sql stable set search_path = public as $$
  select coalesce(array_agg(p order by o), '{}')
    from unnest(public.radar_pauta_problemas(p_peca, p_canais, p_data)) with ordinality t(p, o)
   where p not like 'Números que não estão nas informações conferidas:%';
$$;
revoke all on function public.radar_pauta_bloqueios(bigint, text[], date) from public, anon, authenticated, service_role;

-- 4) marcar como pronta e aprovar, agora com a liberação do administrador (só admin, motivo obrigatório, registro)
drop function if exists public.radar_pauta_marcar_pronta(bigint, timestamptz);   -- v0.120.0: a assinatura ganhou p_liberacao
create or replace function public.radar_pauta_marcar_pronta(p_peca bigint, p_lido timestamptz, p_liberacao jsonb default null) returns timestamptz
language plpgsql security definer set search_path = public as $$
declare
  p      public.radar_pauta_pecas%rowtype;
  v_prob text[];
  v_em   timestamptz;
  v_lib  boolean := p_liberacao is not null and jsonb_typeof(p_liberacao) = 'object';   -- v0.120.0: liberação do administrador
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR159: só o editor ou o administrador mexe na Pauta' using errcode = '42501';
  end if;
  if v_lib and coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR171: só o administrador libera a publicação com pontos pendentes' using errcode = '42501';
  end if;
  if v_lib and length(btrim(coalesce(p_liberacao->>'motivo', ''))) < 3 then
    raise exception 'RADAR171: escreva o motivo da liberação (ao menos 3 caracteres)' using errcode = 'P0001';
  end if;
  select * into p from public.radar_pauta_pecas where id = p_peca for update;
  if p.id is null then
    raise exception 'RADAR160: peça não encontrada' using errcode = 'P0001';
  end if;
  if p_lido is distinct from p.atualizado_em then
    raise exception 'RADAR161: a peça foi alterada depois que a tela foi aberta: recarregue, confira e tente de novo' using errcode = 'P0001';
  end if;
  if p.situacao not in ('planejada','em_producao') then
    raise exception 'RADAR164: só a peça planejada ou em produção fica pronta (situação atual: %)', p.situacao using errcode = 'P0001';
  end if;
  v_prob := case when v_lib then public.radar_pauta_bloqueios(p.id, public.radar_pauta_canais(p.legenda_instagram, p.legenda_facebook), p.data)
                 else public.radar_pauta_problemas(p.id, public.radar_pauta_canais(p.legenda_instagram, p.legenda_facebook), p.data) end;
  if cardinality(v_prob) > 0 then
    raise exception 'RADAR165: há % ponto(s) a resolver: a lista aparece na tela', cardinality(v_prob) using errcode = 'P0001';
  end if;
  perform set_config('radar.pauta', '1', true);
  update public.radar_pauta_pecas
     set situacao = 'pronta',
         liberacao = case when v_lib then jsonb_build_object('motivo', btrim(p_liberacao->>'motivo'),
                            'pontos', coalesce(p_liberacao->'pontos', '[]'::jsonb), 'por', auth.uid(), 'em', now()) else liberacao end
   where id = p.id returning atualizado_em into v_em;
  perform set_config('radar.pauta', '', true);
  return v_em;
end $$;

drop function if exists public.radar_pauta_aprovar(bigint, timestamptz, text[], text, bigint[], text, text[]);
drop function if exists public.radar_pauta_aprovar(bigint, timestamptz, text[], text, bigint[], text, text[], text);
create or replace function public.radar_pauta_aprovar(p_peca bigint, p_lido timestamptz, p_canais text[], p_modo text, p_artes bigint[],
                                                      p_arte_identificacao text, p_conferencias text[], p_video_sha256 text default null,
                                                      p_liberacao jsonb default null)
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
  v_lib    boolean := p_liberacao is not null and jsonb_typeof(p_liberacao) = 'object';   -- v0.120.0: liberação do administrador
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR159: só o administrador aprova a peça da Pauta' using errcode = '42501';
  end if;
  if v_lib and length(btrim(coalesce(p_liberacao->>'motivo', ''))) < 3 then
    raise exception 'RADAR171: escreva o motivo da liberação (ao menos 3 caracteres)' using errcode = 'P0001';
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
  -- v0.42.0: o carrossel (e o carrossel de fotos) também sai pela agenda; v0.79.0: o reel também (a função radar-redes v0.46.0
  -- publica o vídeo aprovado na Meta: contêiner REELS no Instagram, video_reels no Facebook)
  if p_modo = 'agendar' and p.formato not in ('imagem','foto','carrossel','carrossel_fotos','reel') then
    raise exception 'RADAR164: este formato sai à mão (escolha “Vou publicar à mão”)' using errcode = 'P0001';
  end if;
  select coalesce(array_agg(distinct c), '{}') into v_canais from unnest(coalesce(p_canais, '{}')) c;
  v_prob := case when v_lib then public.radar_pauta_bloqueios(p.id, v_canais, p.data) else public.radar_pauta_problemas(p.id, v_canais, p.data) end;
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
    -- v0.79.0: o Facebook só aceita reel de 3 a 90 segundos; o Instagram vai até 15 minutos — e os 15 minutos já são
    -- travados antes (radar_video_pendencia: o vídeo acima de 900 s nem fica pronto, e radar_pauta_problemas reconfere aqui)
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
         liberacao = case when v_lib then jsonb_build_object('motivo', btrim(p_liberacao->>'motivo'),
                            'pontos', coalesce(p_liberacao->'pontos', '[]'::jsonb), 'por', auth.uid(), 'em', now()) else liberacao end,
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

-- 5) grants das novas assinaturas
grant execute on function public.radar_pauta_marcar_pronta(bigint, timestamptz, jsonb) to authenticated;   -- v0.120.0: + a liberação do administrador
grant execute on function public.radar_pauta_aprovar(bigint, timestamptz, text[], text, bigint[], text, text[], text, jsonb) to authenticated;   -- v0.22.0: + o vídeo; v0.120.0: + a liberação
