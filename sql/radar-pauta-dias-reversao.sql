-- Radar v0.64.0 — REVERSÃO de "dias de semana e mais de uma peça por dia" (sql/radar-pauta-dias-v0.64.0.sql).
-- ATENÇÃO: a trava "uma peça por dia" só volta se cada dia tiver no máximo uma peça — antes de rodar,
-- mude ou cancele as peças repetidas do mesmo dia (o select abaixo lista os dias com mais de uma).
--   select data, count(*) from radar_pauta_pecas group by data having count(*) > 1 order by data;

drop function if exists public.radar_pauta_mudar_data(bigint, date, time);
drop index if exists public.radar_pauta_pecas_data_idx;
alter table public.radar_pauta_pecas add constraint radar_pauta_pecas_data_key unique (data);

-- o gatilho volta ao texto da v0.50.0 (a data volta a v_mudou)
create or replace function public.radar_fn_pauta_peca() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_funcao boolean := coalesce(current_setting('radar.pauta', true), '') = '1';
  v_mudou  boolean := false;      -- mudou o que vai ao ar
  v_novas  bigint[];              -- as pessoas acrescentadas agora
begin
  if tg_op = 'INSERT' then
    new.situacao := 'planejada';
    new.aprovado_por := null; new.aprovado_em := null; new.aprovado_modo := null; new.aprovado_conferencias := '{}';
    new.aprovado_canais := '{}'; new.manual_desfeita_em := null;
    new.artes := '{}'; new.arte_identificacao := null; new.link_instagram := null; new.link_facebook := null;
    new.publicado_manual_em := null; new.publicado_manual_por := null;
    new.video_id := null; new.video_sha256 := null;
    new.versao_publicavel := now(); new.criado_por := auth.uid(); new.criado_em := now();
    v_novas := new.pessoas;
  else
    new.criado_por := public.radar_manter_usuario(old.criado_por, new.criado_por);
    new.criado_em  := old.criado_em;
    v_mudou := new.data is distinct from old.data or new.tipo is distinct from old.tipo or new.formato is distinct from old.formato
            or new.chamada is distinct from old.chamada or new.apoio is distinct from old.apoio or new.cartoes is distinct from old.cartoes
            or new.roteiro is distinct from old.roteiro or new.legenda_instagram is distinct from old.legenda_instagram
            or new.legenda_facebook is distinct from old.legenda_facebook or new.fotos is distinct from old.fotos
            or new.pessoas is distinct from old.pessoas or new.conferidas is distinct from old.conferidas;
    if not v_funcao then
      new.aprovado_por := public.radar_manter_usuario(old.aprovado_por, new.aprovado_por);
      new.aprovado_em := old.aprovado_em; new.aprovado_modo := old.aprovado_modo; new.aprovado_conferencias := old.aprovado_conferencias;
      new.aprovado_canais := old.aprovado_canais; new.manual_desfeita_em := old.manual_desfeita_em;
      new.artes := old.artes; new.arte_identificacao := old.arte_identificacao;
      new.video_id := old.video_id; new.video_sha256 := old.video_sha256;
      new.link_instagram := old.link_instagram; new.link_facebook := old.link_facebook;
      new.publicado_manual_em := old.publicado_manual_em;
      new.publicado_manual_por := public.radar_manter_usuario(old.publicado_manual_por, new.publicado_manual_por);
      new.versao_publicavel := old.versao_publicavel;
      if old.situacao = 'aprovada' then
        if v_mudou or new.hora is distinct from old.hora or new.situacao is distinct from old.situacao then
          raise exception 'RADAR162: a peça está aprovada: para mudar, use Desfazer aprovação' using errcode = 'P0001';
        end if;
      elsif old.situacao = 'cancelada' then
        if v_mudou or new.hora is distinct from old.hora then
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
        new.situacao := 'em_producao';
      end if;
    end if;
    if v_mudou then
      new.versao_publicavel := now();
    end if;
    v_novas := array(select x from unnest(new.pessoas) x where not x = any(old.pessoas));
  end if;
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

-- a importação e a "+ Nova peça" voltam ao texto da v0.50.0 (uma peça por dia)
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
  v_hora := public.radar_pauta_hora_padrao();
  for x, i in select t.e, t.o from jsonb_array_elements(p_linhas) with ordinality t(e, o) loop
    v_n := case when jsonb_typeof(x->'linha') = 'number' and (x->>'linha') ~ '^[0-9]{1,6}$' then (x->>'linha')::bigint else i end;
    v_campo := public.radar_pauta_linha_invalida(x);
    if v_campo is not null then
      raise exception 'RADAR173: linha %: % inválido', v_n, v_campo using errcode = 'P0001';
    end if;
    if (x->>'data')::date = any(v_datas) then
      raise exception 'RADAR173: linha %: data repetida no arquivo', v_n using errcode = 'P0001';
    end if;
    v_datas := v_datas || (x->>'data')::date;
  end loop;
  perform pg_advisory_xact_lock(hashtext('radar_pauta_importar'));
  perform set_config('radar.pauta', '1', true);
  for x in select t.e from jsonb_array_elements(p_linhas) t(e) loop
    select * into p from public.radar_pauta_pecas where data = (x->>'data')::date for update;
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

create or replace function public.radar_pauta_criar(p_peca jsonb) returns bigint
language plpgsql security definer set search_path = public as $$
declare
  v_campo text;
  v_data  date;
  v_id    bigint;
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
  perform pg_advisory_xact_lock(hashtext('radar_pauta_importar'));
  if exists (select 1 from public.radar_pauta_pecas where data = v_data) then
    raise exception 'RADAR193: já existe uma peça em %: é uma peça por dia (abra a peça desse dia; se ela estiver cancelada, use Reabrir)',
      to_char(v_data, 'DD/MM/YYYY') using errcode = 'P0001';
  end if;
  begin
    insert into public.radar_pauta_pecas (data, hora, tipo, formato, assunto, quem_aparece, objetivo, observacao)
    values (v_data, public.radar_pauta_hora_padrao(), p_peca->>'tipo', p_peca->>'formato', v_assunto,
            btrim(coalesce(p_peca->>'quem_aparece', ''), E' \t\r\n'), btrim(coalesce(p_peca->>'objetivo', ''), E' \t\r\n'),
            btrim(coalesce(p_peca->>'observacao', ''), E' \t\r\n'))
    returning id into v_id;
  exception when unique_violation then
    raise exception 'RADAR193: já existe uma peça em %: é uma peça por dia (recarregue a página)', to_char(v_data, 'DD/MM/YYYY')
      using errcode = 'P0001';
  end;
  return v_id;
end $$;
