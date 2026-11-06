-- Radar v0.64.0 — Pauta em dias de semana e mais de uma peça por dia (rodar no Supabase → SQL Editor).
--
-- (1) A Pauta deixa de exigir UMA peça por dia: a trava única da data sai (fica um índice comum) — dá para
--     ter duas ou mais peças no mesmo dia (ex.: publicar o vídeo do dia 2 junto com o do dia 1).
-- (2) Mudar O DIA de uma peça deixa de ser "mexer no que vai ao ar": a peça pronta continua pronta
--     (o conteúdo não mudou — só a data). A peça APROVADA e a CANCELADA continuam travadas no caminho
--     comum (Desfazer aprovação / Reabrir), como antes.
-- (3) Função nova radar_pauta_mudar_data (só o administrador): muda o dia (e a hora) de uma peça SEM
--     derrubar a situação — inclusive da aprovada com publicação agendada (a agenda muda junto).
-- (4) radar_pauta_importar: com mais de uma peça no mesmo dia, a importação casa com a MAIS ANTIGA do dia
--     (a do calendário); as demais ficam como estão.
-- Incremental idempotente sobre o banco v0.50.0 (com os incrementais anteriores): nada é apagado; pode
-- rodar de novo. Para desfazer: sql/radar-pauta-dias-reversao.sql (exige antes voltar a uma peça por dia).

alter table public.radar_pauta_pecas drop constraint if exists radar_pauta_pecas_data_key;
create index if not exists radar_pauta_pecas_data_idx on public.radar_pauta_pecas (data);

-- O gatilho da peça: "data" sai de v_mudou (mudar o dia não muda o que vai ao ar nem derruba a Conferência);
-- a aprovada e a cancelada ganham a trava da data por extenso (só as funções mudam — radar_pauta_mudar_data).
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

-- Mudar o dia (e a hora) de uma peça SEM mexer na situação (só o administrador). A aprovada com publicação
-- agendada tem a agenda remarcada junto; a cancelada pede Reabrir antes. O dia novo não fica no passado.
create or replace function public.radar_pauta_mudar_data(p_id bigint, p_data date, p_hora time default null) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  p        public.radar_pauta_pecas%rowtype;
  v_hora   time;
  v_quando timestamptz;
  v_envios int := 0;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR350: só o administrador muda o dia de uma peça' using errcode = 'P0001';
  end if;
  select * into p from public.radar_pauta_pecas where id = p_id for update;
  if p.id is null then
    raise exception 'RADAR351: peça não encontrada (atualize a página)' using errcode = 'P0001';
  end if;
  if p.situacao = 'cancelada' then
    raise exception 'RADAR351: a peça está cancelada: use Reabrir antes de mudar o dia' using errcode = 'P0001';
  end if;
  if p_data is null or p_data < (now() at time zone 'America/Sao_Paulo')::date then
    raise exception 'RADAR352: o dia novo não pode ficar no passado' using errcode = 'P0001';
  end if;
  v_hora   := coalesce(p_hora, p.hora);
  v_quando := (p_data + v_hora) at time zone 'America/Sao_Paulo';
  if p.situacao = 'aprovada' and v_quando <= now()
     and exists (select 1 from public.radar_redes_envios e
                  where e.peca_id = p.id and e.situacao = 'autorizado' and e.agendado_para is not null and e.enviado_em is null) then
    raise exception 'RADAR352: a hora nova da publicação agendada já passou: escolha um dia e uma hora à frente' using errcode = 'P0001';
  end if;
  perform set_config('radar.pauta', '1', true);            -- mudar o dia não derruba a situação nem a aprovação
  update public.radar_pauta_pecas set data = p_data, hora = v_hora where id = p.id;
  update public.radar_redes_envios e set agendado_para = v_quando
   where e.peca_id = p.id and e.situacao = 'autorizado' and e.agendado_para is not null and e.enviado_em is null;
  get diagnostics v_envios = row_count;
  return jsonb_build_object('data', p_data, 'hora', v_hora, 'agendados_remarcados', v_envios);
end $$;
revoke all on function public.radar_pauta_mudar_data(bigint, date, time) from public, anon, authenticated, service_role;
grant execute on function public.radar_pauta_mudar_data(bigint, date, time) to authenticated;

-- A importação do calendário: com mais de uma peça no mesmo dia, casa com a MAIS ANTIGA (a do calendário);
-- as outras peças do dia ficam como estão.
create or replace function public.radar_pauta_importar(p_linhas jsonb) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_hora  time;
  x       jsonb;
  i       bigint;
  v_n     bigint;
  v_campo text;
  v_datas date[] := '{}';
  p       public.radar_pauta_pecas%rowtype;
  v_novas int := 0; v_alteradas int := 0; v_iguais int := 0; v_mantidas int := 0;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR159: só o editor ou o administrador mexe na Pauta' using errcode = '42501';
  end if;
  if jsonb_typeof(p_linhas) is distinct from 'array' or jsonb_array_length(p_linhas) not between 1 and 400 then
    raise exception 'RADAR173: envie de 1 a 400 linhas do calendário' using errcode = 'P0001';
  end if;
  v_hora := public.radar_pauta_hora_padrao();                       -- v0.28.0: a mesma hora da "+ Nova peça"
  for x, i in select t.e, t.o from jsonb_array_elements(p_linhas) with ordinality t(e, o) loop
    v_n := case when jsonb_typeof(x->'linha') = 'number' and (x->>'linha') ~ '^[0-9]{1,6}$' then (x->>'linha')::bigint else i end;
    v_campo := public.radar_pauta_linha_invalida(x);            -- v0.28.0: a mesma conferência da "+ Nova peça"
    if v_campo is not null then
      raise exception 'RADAR173: linha %: % inválido', v_n, v_campo using errcode = 'P0001';
    end if;
    if (x->>'data')::date = any(v_datas) then
      raise exception 'RADAR173: linha %: data repetida no arquivo', v_n using errcode = 'P0001';
    end if;
    v_datas := v_datas || (x->>'data')::date;
  end loop;
  perform pg_advisory_xact_lock(hashtext('radar_pauta_importar'));           -- uma importação por vez
  perform set_config('radar.pauta', '1', true);    -- a importação não leva a peça planejada para a produção
  for x in select t.e from jsonb_array_elements(p_linhas) t(e) loop
    -- v0.64.0: com mais de uma peça no dia, a do calendário é a mais antiga (menor id)
    select * into p from public.radar_pauta_pecas where data = (x->>'data')::date order by id limit 1 for update;
    if p.id is null then
      insert into public.radar_pauta_pecas (data, hora, tipo, formato, assunto, quem_aparece, objetivo, observacao)
      values ((x->>'data')::date, v_hora, x->>'tipo', x->>'formato', btrim(coalesce(x->>'assunto', '')), btrim(coalesce(x->>'quem_aparece', '')),
              btrim(coalesce(x->>'objetivo', '')), btrim(coalesce(x->>'observacao', '')));
      v_novas := v_novas + 1;
    elsif p.situacao <> 'planejada' then
      v_mantidas := v_mantidas + 1;
    elsif (p.tipo, p.formato, p.assunto, p.quem_aparece, p.objetivo, p.observacao)
          is not distinct from (x->>'tipo', x->>'formato', btrim(coalesce(x->>'assunto', '')), btrim(coalesce(x->>'quem_aparece', '')),
                                btrim(coalesce(x->>'objetivo', '')), btrim(coalesce(x->>'observacao', ''))) then
      v_iguais := v_iguais + 1;
    else
      update public.radar_pauta_pecas
         set tipo = x->>'tipo', formato = x->>'formato', assunto = btrim(coalesce(x->>'assunto', '')),
             quem_aparece = btrim(coalesce(x->>'quem_aparece', '')), objetivo = btrim(coalesce(x->>'objetivo', '')),
             observacao = btrim(coalesce(x->>'observacao', ''))
       where id = p.id;
      v_alteradas := v_alteradas + 1;
    end if;
  end loop;
  perform set_config('radar.pauta', '', true);
  return jsonb_build_object('novas', v_novas, 'alteradas', v_alteradas, 'iguais', v_iguais, 'mantidas', v_mantidas);
end $$;

-- "+ Nova peça": o dia pode já ter peça (v0.64.0) — a trava "uma peça por dia" saiu.
create or replace function public.radar_pauta_criar(p_peca jsonb) returns bigint
language plpgsql security definer set search_path = public as $$
declare
  v_campo text;
  v_data  date;
  v_id    bigint;
  -- os textos sem os espaços e as quebras de linha das pontas
  v_assunto  text := btrim(coalesce(p_peca->>'assunto', ''), E' \t\r\n');
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR191: só o administrador cria peça nova na Pauta' using errcode = '42501';
  end if;
  if jsonb_typeof(p_peca) is distinct from 'object' then
    raise exception 'RADAR192: envie o dia, o tipo, o formato e o assunto da peça nova' using errcode = 'P0001';
  end if;
  v_campo := public.radar_pauta_linha_invalida(p_peca);
  if v_campo is not null then
    raise exception 'RADAR192: confira o campo “%” da peça nova',
      case v_campo when 'data' then 'dia' when 'quem_aparece' then 'quem aparece' when 'observacao' then 'observação' else v_campo end
      using errcode = 'P0001';
  end if;
  if v_assunto = '' then
    raise exception 'RADAR192: escreva o assunto da peça nova' using errcode = 'P0001';
  end if;
  v_data := (p_peca->>'data')::date;
  if v_data < public.radar_pauta_hoje() then
    raise exception 'RADAR192: esse dia já passou: a peça nova é de hoje em diante (horário de Brasília)' using errcode = 'P0001';
  end if;
  perform pg_advisory_xact_lock(hashtext('radar_pauta_importar'));          -- não cruza com uma importação em andamento
  insert into public.radar_pauta_pecas (data, hora, tipo, formato, assunto, quem_aparece, objetivo, observacao)
  values (v_data, public.radar_pauta_hora_padrao(), p_peca->>'tipo', p_peca->>'formato', v_assunto,
          btrim(coalesce(p_peca->>'quem_aparece', ''), E' \t\r\n'), btrim(coalesce(p_peca->>'objetivo', ''), E' \t\r\n'),
          btrim(coalesce(p_peca->>'observacao', ''), E' \t\r\n'))
  returning id into v_id;
  return v_id;
end $$;
