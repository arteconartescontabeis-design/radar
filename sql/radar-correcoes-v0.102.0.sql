-- Radar v0.102.0 — correções da varredura de segurança/integridade (rodar no Supabase → SQL Editor).
-- Idempotente (create or replace + drop constraint if exists). NÃO apaga dados. Depois, republique as funções Edge
-- radar-ia e radar-meta-webhook (supabase functions deploy). O conteúdo abaixo é o MESMO já incorporado em
-- sql/radar-setup-v0.50.0.sql (a fonte dos testes); esta migração só o aplica a um banco já instalado.
--
-- (1) Fix #2 — consentimento reconferido na publicação do reel para quem está só no vídeo (não só p.pessoas):
--     helper radar_pauta_pessoas_conferir + pode_sair / publicar_agora / pode_copiar / registrar_manual.
-- (2) Fix #1 — a resposta automática a comentário não sai em dobro: a fila reivindica o item ('enviando') antes de enviar;
--     um envio preso vira 'erro' depois de 15 min (sem reenviar). Precisa do estado 'enviando' no CHECK da tabela.

begin;

-- (1) o conjunto de pessoas a reconferir — p.pessoas E, no reel, quem está só no vídeo
create or replace function public.radar_pauta_pessoas_conferir(p public.radar_pauta_pecas) returns bigint[]
language sql stable security definer set search_path = public as $$
  select coalesce(p.pessoas, '{}') || case when p.formato = 'reel' then coalesce(
           (select array_agg(x) from public.radar_videos v, unnest(coalesce(v.pessoas, '{}')) x
             where v.id = p.video_id and not x = any(coalesce(p.pessoas, '{}'))), '{}')
         else '{}'::bigint[] end;
$$;
revoke all on function public.radar_pauta_pessoas_conferir(public.radar_pauta_pecas) from public;

-- as quatro funções de publicação passam a usar o helper (reconferem o termo do conjunto completo)
create or replace function public.radar_pauta_publicar_agora(p_peca bigint, p_conferi_rede boolean) returns bigint[]
language plpgsql security definer set search_path = public as $$
declare
  p      public.radar_pauta_pecas%rowtype;
  v_hoje date := public.radar_pauta_hoje();
  r      record;
  v_id   bigint;
  v_x    text;
  v_ids  bigint[];
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR159: só o administrador publica a peça da Pauta' using errcode = '42501';
  end if;
  select * into p from public.radar_pauta_pecas where id = p_peca for update;
  if p.id is null then
    raise exception 'RADAR160: peça não encontrada' using errcode = 'P0001';
  end if;
  if p.situacao <> 'aprovada' or p.aprovado_modo is distinct from 'agendar' then
    raise exception 'RADAR164: só a peça aprovada para sair pela agenda é publicada por aqui' using errcode = 'P0001';
  end if;
  if exists (select 1 from public.radar_redes_envios e where e.peca_id = p.id and e.situacao = 'enviando') then
    raise exception 'RADAR169: a peça está sendo publicada agora: espere terminar' using errcode = 'P0001';
  end if;
  if not coalesce(p_conferi_rede, false)
     and exists (select 1 from public.radar_redes_envios e where e.peca_id = p.id and e.situacao = 'erro') then
    raise exception 'RADAR166: confira no Instagram e no Facebook que a publicação não saiu e marque “Conferi no Instagram e no Facebook: não saiu”'
      using errcode = 'P0001';
  end if;
  if p.tipo = 'agenda' and v_hoje > p.data + 1 then
    raise exception 'RADAR168: a agenda da semana ficou velha (passou a segunda-feira)' using errcode = 'P0001';
  end if;
  for r in select e.canal, e.legenda from public.radar_redes_envios e where e.peca_id = p.id and e.situacao in ('autorizado','erro') loop
    foreach v_id in array public.radar_pauta_pessoas_conferir(p) loop     -- v0.102.0: reel inclui quem está só no vídeo
      v_x := public.radar_pauta_termo_ok(v_id, p.tipo, r.canal, v_hoje);
      if v_x is not null then
        raise exception 'RADAR165: o termo de uso de imagem de uma pessoa da peça não vale hoje no % (%): confira em Pauta → Pessoas e termos',
          initcap(r.canal), v_x using errcode = 'P0001';
      end if;
    end loop;
    if public.radar_marcas_verificar(r.legenda) is not null or r.legenda ~* '\{\s*confirmar[^}]*\}' or r.legenda ~ '\{[^{}\n]{1,120}\}' then
      raise exception 'RADAR165: a legenda do % tem ponto marcado com [VERIFICAR], {confirmar} ou outro marcador entre chaves: desfaça a aprovação e corrija',
        initcap(r.canal) using errcode = 'P0001';
    end if;
  end loop;
  with u as (
    update public.radar_redes_envios
       set situacao = 'autorizado', agendado_para = now(), disparos = 0, disparado_em = null, erro = null, atualizado_em = now(),
           tentativas = 0, retentar_em = null                      -- v0.43.0: o Tentar de novo recomeça as tentativas automáticas
     where peca_id = p.id and situacao in ('autorizado','erro')
    returning id
  ) select coalesce(array_agg(u.id order by u.id), '{}') into v_ids from u;
  if cardinality(v_ids) = 0 then
    raise exception 'RADAR164: não há publicação desta peça esperando a hora (ou com erro)' using errcode = 'P0001';
  end if;
  return v_ids;
end $$;

create or replace function public.radar_pauta_pode_copiar(p_peca bigint, p_lido timestamptz, p_canal text default null) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  p       public.radar_pauta_pecas%rowtype;
  v_hoje  date := public.radar_pauta_hoje();
  v_canal text;
  v_id    bigint;
  v_x     text;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR159: só o editor ou o administrador mexe na Pauta' using errcode = '42501';
  end if;
  select * into p from public.radar_pauta_pecas where id = p_peca;
  if p.id is null then
    return jsonb_build_object('motivo', 'Peça não encontrada.');
  end if;
  if p.situacao <> 'aprovada' or p.aprovado_modo is distinct from 'manual' then
    return jsonb_build_object('motivo', 'Só a peça aprovada para publicar à mão pode ser copiada ou baixada.');
  end if;
  if p_lido is distinct from p.atualizado_em then
    return jsonb_build_object('motivo', 'A peça mudou depois que a tela foi aberta: recarregue e confira.');
  end if;
  if p_canal is not null and not p_canal = any(p.aprovado_canais) then
    return jsonb_build_object('motivo', format('O %s não foi aprovado para esta peça: ela sai só no canal marcado na aprovação.',
                                               case p_canal when 'instagram' then 'Instagram' when 'facebook' then 'Facebook' else 'canal' end));
  end if;
  -- o texto copiado (a legenda do canal; sem canal, o roteiro) não leva marca nem marcador do modelo entre chaves
  v_x := case when p_canal = 'instagram' then p.legenda_instagram when p_canal = 'facebook' then p.legenda_facebook else p.roteiro end;
  if public.radar_marcas_verificar(v_x) is not null or v_x ~* '\{\s*confirmar[^}]*\}' or v_x ~ '\{[^{}\n]{1,120}\}' then
    return jsonb_build_object('motivo', 'O texto aprovado tem ponto marcado com [VERIFICAR], {confirmar} ou outro marcador entre chaves: desfaça a aprovação e corrija.');
  end if;
  foreach v_canal in array case when p_canal is null then p.aprovado_canais else array[p_canal] end loop
    foreach v_id in array public.radar_pauta_pessoas_conferir(p) loop     -- v0.102.0: reel inclui quem está só no vídeo
      v_x := public.radar_pauta_termo_ok(v_id, p.tipo, v_canal, v_hoje);
      if v_x is not null then
        return jsonb_build_object('motivo', format('O termo de uso de imagem de uma pessoa da peça não vale hoje no %s (%s): confira em Pauta → Pessoas e termos.',
                                                   initcap(v_canal), v_x));
      end if;
    end loop;
  end loop;
  return jsonb_build_object('ok', true, 'artes', to_jsonb(p.artes), 'canais', to_jsonb(p.aprovado_canais));
end $$;

create or replace function public.radar_pauta_registrar_manual(p_peca bigint, p_link_instagram text, p_link_facebook text, p_data date)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  p       public.radar_pauta_pecas%rowtype;
  v_ig    text := nullif(btrim(coalesce(p_link_instagram, '')), '');
  v_fb    text := nullif(btrim(coalesce(p_link_facebook, '')), '');
  v_canal text;
  v_id    bigint;
  v_x     text;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR159: só o editor ou o administrador mexe na Pauta' using errcode = '42501';
  end if;
  select * into p from public.radar_pauta_pecas where id = p_peca for update;
  if p.id is null then
    raise exception 'RADAR160: peça não encontrada' using errcode = 'P0001';
  end if;
  if p.situacao <> 'aprovada' or p.aprovado_modo is distinct from 'manual' then
    raise exception 'RADAR175: só a peça aprovada para publicar à mão tem registro manual' using errcode = 'P0001';
  end if;
  -- v0.22.0: o reel sai com o vídeo aprovado. O reel aprovado à mão ANTES desta versão (sem o corretor: o vídeo do Edits) continua
  -- registrando o link como na v0.21.0 — desfazer a aprovação pediria "não foi postada", o que seria falso. v0.24.0: vale a primeira
  -- instalação da v0.22.0 ou mais nova (quem foi da v0.21.0 direto para uma versão depois da v0.22.0 não tem a linha da v0.22.0)
  if p.formato = 'reel' and p.video_sha256 is null
     and p.aprovado_em >= coalesce((select min(i.executado_em) from public.radar_instalacoes i
                                    where i.versao ~ '^v0\.(2[2-9]|[3-9][0-9])\.' or i.versao ~ '^v[1-9]'), '-infinity') then
    raise exception 'RADAR317: o reel foi aprovado sem o vídeo corrigido: desfaça a aprovação, confira o vídeo e aprove de novo'
      using errcode = 'P0001';
  end if;
  if v_ig is null and v_fb is null then
    raise exception 'RADAR175: cole o link da publicação no Instagram ou no Facebook' using errcode = 'P0001';
  end if;
  if (v_ig is not null and not 'instagram' = any(p.aprovado_canais)) or (v_fb is not null and not 'facebook' = any(p.aprovado_canais)) then
    raise exception 'RADAR175: o % não foi aprovado para esta peça (ela sai só no canal marcado na aprovação)',
      case when v_ig is not null and not 'instagram' = any(p.aprovado_canais) then 'Instagram' else 'Facebook' end using errcode = 'P0001';
  end if;
  if v_ig is not null and (v_ig !~ '^https://(www\.)?instagram\.com/[!-~]+$' or length(v_ig) > 500) then
    raise exception 'RADAR175: o link do Instagram começa com https://www.instagram.com/' using errcode = 'P0001';
  end if;
  if v_fb is not null and ((v_fb !~ '^https://((www|m|web)\.)?facebook\.com/[!-~]+$' and v_fb !~ '^https://fb\.watch/[!-~]+$') or length(v_fb) > 500) then
    raise exception 'RADAR175: o link do Facebook começa com https://www.facebook.com/ (ou https://fb.watch/)' using errcode = 'P0001';
  end if;
  if p_data is null or p_data < (p.aprovado_em at time zone 'America/Sao_Paulo')::date or p_data > public.radar_pauta_hoje() then
    raise exception 'RADAR175: a data da publicação vai do dia da aprovação até hoje' using errcode = 'P0001';
  end if;
  foreach v_canal in array array_remove(array[case when v_ig is not null then 'instagram' end, case when v_fb is not null then 'facebook' end], null) loop
    foreach v_id in array public.radar_pauta_pessoas_conferir(p) loop     -- v0.102.0: reel inclui quem está só no vídeo
      v_x := public.radar_pauta_termo_ok(v_id, p.tipo, v_canal, p_data);
      if v_x is not null then
        raise exception 'RADAR175: o termo de uso de imagem de uma pessoa da peça não valia nesse dia no % (%): confira em Pauta → Pessoas e termos',
          initcap(v_canal), v_x using errcode = 'P0001';
      end if;
    end loop;
  end loop;
  perform set_config('radar.pauta', '1', true);
  update public.radar_pauta_pecas
     set link_instagram = coalesce(link_instagram, v_ig), link_facebook = coalesce(link_facebook, v_fb),
         publicado_manual_em = coalesce(publicado_manual_em, p_data), publicado_manual_por = coalesce(publicado_manual_por, auth.uid())
   where id = p.id
  returning * into p;
  perform set_config('radar.pauta', '', true);
  return jsonb_build_object('link_instagram', p.link_instagram, 'link_facebook', p.link_facebook, 'publicado_manual_em', p.publicado_manual_em);
end $$;

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
  foreach v_id in array public.radar_pauta_pessoas_conferir(p) loop       -- v0.102.0: reel inclui quem está só no vídeo
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

-- (2) o estado 'enviando' (reivindicado antes de sair na Meta) no CHECK de radar_respostas_registro
alter table public.radar_respostas_registro drop constraint if exists radar_respostas_registro_situacao_check;
alter table public.radar_respostas_registro
  add constraint radar_respostas_registro_situacao_check
  check (situacao in ('enviado','pendente','enviando','erro','descartado'));

-- a fila reivindica os escolhidos e recupera o que ficou preso
create or replace function public.radar_respostas_pendentes(p_max int) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_fila jsonb;
begin
  update public.radar_respostas_registro
     set situacao = 'erro', erro = 'A janela de 7 dias da Meta venceu: este comentário não pode mais ser respondido.'
   where situacao = 'pendente' and criado_em <= now() - interval '7 days';
  -- v0.102.0: um envio reivindicado que ficou preso em 'enviando' (a função de envio caiu entre reivindicar e gravar o resultado)
  -- vira 'erro' em vez de voltar à fila — responder comentário NÃO é idempotente na Meta, então NÃO se reenvia: o administrador
  -- confere na rede (mesmo padrão de radar_redes_envios 'enviando' preso). enviado_em marca a hora da reivindicação.
  update public.radar_respostas_registro
     set situacao = 'erro', erro = 'O envio ficou preso: a resposta pode ou não ter saído — confira o comentário na rede antes de tentar de novo.'
   where situacao = 'enviando' and enviado_em <= now() - interval '15 minutes';
  if not (public.radar_respostas_cfg()->>'ligado')::boolean then
    return '[]'::jsonb;
  end if;
  -- v0.102.0: a fila REIVINDICA os escolhidos (pendente → enviando, enviado_em = agora) na mesma consulta que os devolve, para que
  -- uma resposta que já saiu na Meta nunca volte à fila se a gravação do resultado falhar logo depois (antes era só um SELECT de
  -- 'pendente', e um 5xx/timeout do banco após o envio reenviava a resposta pública). O 'enviando' também conta no limite por hora.
  -- o CTE que modifica dados (reivindicados) tem de ficar no TOPO de um SELECT (não dentro de um coalesce/subconsulta)
  with elegiveis as (
    select r.id, row_number() over (partition by g.id order by r.criado_em) as n,
           g.limite_hora - (select count(*) from public.radar_respostas_registro e
                            where e.gatilho_id = g.id
                              and ((e.situacao = 'enviado' and e.enviado_em > now() - interval '1 hour') or e.situacao = 'enviando')) as folga
      from public.radar_respostas_registro r
      join public.radar_respostas_gatilhos g on g.id = r.gatilho_id and g.ativo
     where r.situacao = 'pendente'
  ),
  escolhidos as (
    select id from elegiveis where n <= folga order by id limit least(greatest(coalesce(p_max, 25), 1), 100)
  ),
  reivindicados as (
    update public.radar_respostas_registro r set situacao = 'enviando', enviado_em = now()
     where r.id in (select id from escolhidos)
    returning r.id, r.rede, r.comentario_id, r.gatilho_id
  )
  select coalesce(jsonb_agg(jsonb_build_object('registro', r.id, 'rede', r.rede, 'comentario_id', r.comentario_id,
                                      'resposta_publica', g.resposta_publica, 'mensagem_privada', g.mensagem_privada,
                                      'link', g.link_material) order by r.id), '[]'::jsonb)
    into v_fila
    from reivindicados r join public.radar_respostas_gatilhos g on g.id = r.gatilho_id;
  return v_fila;
end $$;

commit;
