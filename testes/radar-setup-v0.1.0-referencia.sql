-- =====================================================================
-- RADAR ARTECON — Plataforma de Inteligência Contábil e Tributária
-- radar-setup-v0.1.0.sql  ·  Bloco 1 (banco + coletores)
--
-- IDEMPOTENTE: pode ser executado mais de uma vez sem duplicar nem apagar
-- dados. Cada execução fica registrada em radar_instalacoes com o estado
-- ANTES e DEPOIS. A última instrução devolve a evidência da instalação.
-- Reversão: radar-reversao-v0.1.0.sql
-- =====================================================================

begin;

-- ---------------------------------------------------------------------
-- 0. ESTADO ANTES (guardado em tabela temporária até o fim do script)
-- ---------------------------------------------------------------------
create temp table _radar_antes on commit drop as
select coalesce(jsonb_agg(jsonb_build_object('tabela', c.relname, 'rls', c.relrowsecurity)
                          order by c.relname), '[]'::jsonb) as objetos
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'radar\_%';

-- ---------------------------------------------------------------------
-- 1. TABELAS
-- ---------------------------------------------------------------------
create table if not exists public.radar_instalacoes (
  id            bigint generated always as identity primary key,
  versao        text        not null,
  executado_em  timestamptz not null default now(),
  antes         jsonb       not null,
  depois        jsonb
);

create table if not exists public.radar_perfis (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  nome       text        not null,
  papel      text        not null default 'leitor'
             check (papel in ('admin','editor','leitor')),
  ativo      boolean     not null default true,
  criado_em  timestamptz not null default now()
);

create table if not exists public.radar_categorias (
  slug   text primary key,
  nome   text not null,
  ordem  int  not null default 100
);

create table if not exists public.radar_fontes (
  id                   bigint generated always as identity primary key,
  slug                 text        not null unique,
  nome                 text        not null,
  orgao                text        not null,
  abrangencia          text        not null default 'federal'
                       check (abrangencia in ('federal','estadual_sc','municipal','geral')),
  oficial              boolean     not null default true,
  tipo_coletor         text        not null
                       check (tipo_coletor in ('rss','html_links','normas_rfb')),
  url                  text        not null,
  config               jsonb       not null default '{}'::jsonb,
  categoria_padrao     text        references public.radar_categorias(slug),
  frequencia_horas     int         not null default 6 check (frequencia_horas between 1 and 168),
  ativo                boolean     not null default true,
  validada             boolean     not null default false,
  ultimo_sucesso_em    timestamptz,
  ultima_falha_em      timestamptz,
  ultimo_erro          text,
  falhas_consecutivas  int         not null default 0,
  criado_em            timestamptz not null default now(),
  atualizado_em        timestamptz not null default now()
);

create table if not exists public.radar_execucoes (
  id                 bigint generated always as identity primary key,
  fonte_id           bigint      not null references public.radar_fontes(id) on delete cascade,
  iniciado_em        timestamptz not null default now(),
  finalizado_em      timestamptz,
  status             text        not null default 'em_andamento'
                     check (status in ('em_andamento','ok','parcial','vazio_suspeito','falha')),
  itens_encontrados  int         not null default 0,
  itens_novos        int         not null default 0,
  itens_atualizados  int         not null default 0,
  itens_sem_texto    int         not null default 0,
  itens_com_erro     int         not null default 0,
  http_status        int,
  erro               text,
  versao_robo        text
);
create index if not exists radar_execucoes_fonte_idx on public.radar_execucoes (fonte_id, iniciado_em desc);

create table if not exists public.radar_capturas (
  id               bigint generated always as identity primary key,
  fonte_id         bigint      not null references public.radar_fontes(id) on delete restrict,
  url              text        not null,
  titulo           text        not null,
  data_publicacao  date,
  resumo_fonte     text,
  texto            text,
  hash_conteudo    text,
  hash_titulo      text        not null,
  duplicata_de     bigint      references public.radar_capturas(id) on delete set null,
  metadados        jsonb       not null default '{}'::jsonb,
  versao           int         not null default 1,
  capturado_em     timestamptz not null default now(),
  verificado_em    timestamptz not null default now(),
  atualizado_em    timestamptz,
  constraint radar_capturas_fonte_url_uk unique (fonte_id, url)
);
create index if not exists radar_capturas_hash_titulo_idx on public.radar_capturas (hash_titulo);
create index if not exists radar_capturas_hash_conteudo_idx on public.radar_capturas (hash_conteudo);
create index if not exists radar_capturas_data_idx on public.radar_capturas (capturado_em desc);

create table if not exists public.radar_capturas_versoes (
  id             bigint generated always as identity primary key,
  captura_id     bigint      not null references public.radar_capturas(id) on delete cascade,
  versao         int         not null,
  titulo         text        not null,
  texto          text,
  hash_conteudo  text,
  registrado_em  timestamptz not null default now(),
  constraint radar_capturas_versoes_uk unique (captura_id, versao)
);

create table if not exists public.radar_normas (
  id           bigint generated always as identity primary key,
  tipo         text        not null,
  numero       text        not null,
  data_norma   date,
  orgao        text        not null,
  ementa       text,
  url_oficial  text,
  situacao     text        not null default 'vigente'
               check (situacao in ('vigente','alterada','revogada','nao_verificada')),
  criado_em    timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  constraint radar_normas_uk unique (tipo, numero, orgao)
);

create table if not exists public.radar_assuntos (
  id                    bigint generated always as identity primary key,
  titulo                text        not null,
  categoria             text        references public.radar_categorias(slug),
  subcategoria          text,
  abrangencia           text        not null default 'federal'
                        check (abrangencia in ('federal','estadual_sc','municipal','geral')),
  relevancia            text        not null default 'media'
                        check (relevancia in ('alta','media','baixa')),
  situacao_confirmacao  text        not null default 'em_verificacao'
                        check (situacao_confirmacao in ('confirmado_oficialmente',
                               'confirmado_fontes_confiaveis','em_verificacao',
                               'nao_confirmado','divergencia_identificada')),
  status                text        not null default 'capturado'
                        check (status in ('capturado','classificado','analisado','selecionado',
                               'conteudo_gerado','revisao','aprovado','publicado',
                               'ignorado','arquivado')),
  resumo                text,
  publico_afetado       text,
  responsavel           uuid        references auth.users(id) on delete set null,
  criado_em             timestamptz not null default now(),
  atualizado_em         timestamptz not null default now()
);
create index if not exists radar_assuntos_status_idx on public.radar_assuntos (status, relevancia);

create table if not exists public.radar_assunto_capturas (
  assunto_id  bigint not null references public.radar_assuntos(id) on delete cascade,
  captura_id  bigint not null references public.radar_capturas(id) on delete restrict,
  primary key (assunto_id, captura_id)
);

create table if not exists public.radar_evidencias (
  id               bigint generated always as identity primary key,
  assunto_id       bigint      not null references public.radar_assuntos(id) on delete cascade,
  captura_id       bigint      not null references public.radar_capturas(id) on delete restrict,
  norma_id         bigint      references public.radar_normas(id) on delete set null,
  dispositivo      text,
  trecho_literal   text        not null,
  natureza         text        not null default 'fato_oficial'
                   check (natureza in ('fato_oficial','interpretacao_tecnica','hipotese')),
  trecho_conferido boolean     not null default false,
  conferido_em     timestamptz,
  versao_captura   int,
  criado_em        timestamptz not null default now()
);
create index if not exists radar_evidencias_assunto_idx on public.radar_evidencias (assunto_id);
create index if not exists radar_evidencias_captura_idx on public.radar_evidencias (captura_id);

create table if not exists public.radar_conteudos (
  id            bigint generated always as identity primary key,
  assunto_id    bigint      not null references public.radar_assuntos(id) on delete cascade,
  formato       text        not null check (formato in ('flash','informativo','artigo')),
  titulo        text        not null,
  corpo         text        not null,
  gerado_por    text        not null default 'ia' check (gerado_por in ('ia','humano')),
  modelo_ia     text,
  status        text        not null default 'rascunho'
                check (status in ('rascunho','em_revisao','aprovado','rejeitado')),
  aprovado_por  uuid        references auth.users(id) on delete set null,
  aprovado_em   timestamptz,
  criado_em     timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);
create index if not exists radar_conteudos_assunto_idx on public.radar_conteudos (assunto_id);

create table if not exists public.radar_publicacoes (
  id            bigint generated always as identity primary key,
  conteudo_id   bigint      not null references public.radar_conteudos(id) on delete restrict,
  slug          text        not null unique,
  titulo        text        not null default '',   -- sempre copiado do conteúdo aprovado
  corpo         text        not null default '',   -- idem (texto; a vitrine é que formata)
  categoria     text        references public.radar_categorias(slug),
  status        text        not null default 'rascunho'
                check (status in ('rascunho','publicado','despublicado')),
  publicar_em   timestamptz not null default now(),
  errata        text,
  requer_revisao boolean    not null default false,
  motivo_revisao text,
  criado_por    uuid        references auth.users(id) on delete set null,
  publicado_por uuid        references auth.users(id) on delete set null,
  publicado_em  timestamptz,
  criado_em     timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);
create index if not exists radar_publicacoes_vitrine_idx on public.radar_publicacoes (status, publicar_em desc);

create table if not exists public.radar_publicacao_normas (
  publicacao_id bigint not null references public.radar_publicacoes(id) on delete cascade,
  norma_id      bigint not null references public.radar_normas(id) on delete restrict,
  primary key (publicacao_id, norma_id)
);

create table if not exists public.radar_auditoria (
  id           bigint generated always as identity primary key,
  tabela       text        not null,
  registro_id  text        not null,
  acao         text        not null,
  usuario      uuid,
  antes        jsonb,
  depois       jsonb,
  em           timestamptz not null default now()
);
create index if not exists radar_auditoria_registro_idx on public.radar_auditoria (tabela, registro_id, em desc);

-- ---------------------------------------------------------------------
-- 2. FUNÇÕES
-- ---------------------------------------------------------------------

-- Papel do usuário logado (security definer: evita recursão de RLS em radar_perfis)
create or replace function public.radar_papel() returns text
language sql stable security definer set search_path = public as $$
  select p.papel from public.radar_perfis p
  where p.user_id = auth.uid() and p.ativo
$$;

-- Normalização usada na conferência de trechos: minúsculas, aspas e traços
-- tipográficos igualados, espaços (inclusive o "não separável") colapsados.
create or replace function public.radar_normalizar(t text) returns text
language sql immutable set search_path = public as $$
  select btrim(regexp_replace(
           lower(translate(coalesce(t, ''),
                           chr(160) || chr(8220) || chr(8221) || chr(8216) || chr(8217) || chr(8211) || chr(8212),
                           ' ' || '"' || '"' || '''' || '''' || '-' || '-')),
           '\s+', ' ', 'g'))
$$;

-- O trecho citado existe, literalmente, no texto guardado da captura?
create or replace function public.radar_trecho_confere(p_trecho text, p_texto text) returns boolean
language sql immutable set search_path = public as $$
  select length(public.radar_normalizar(p_trecho)) >= 20
     -- pontuação e espaços não provam nada: exige ao menos 15 letras/algarismos
     and length(regexp_replace(public.radar_normalizar(p_trecho), '[^[:alnum:]]', '', 'g')) >= 15
     and position(public.radar_normalizar(p_trecho) in public.radar_normalizar(p_texto)) > 0
$$;

-- Hash oficial do texto: calculado pelo banco (o robô não é a autoridade)
create or replace function public.radar_hash_texto(t text) returns text
language sql immutable set search_path = public as $$
  select case when t is null then null else
    encode(sha256(convert_to(btrim(regexp_replace(replace(t, chr(160), ' '), '\s+', ' ', 'g')), 'UTF8')), 'hex') end
$$;

create or replace function public.radar_fn_atualizado_em() returns trigger
language plpgsql set search_path = public as $$
begin
  new.atualizado_em := now();
  return new;
end $$;

-- Trilha de auditoria (somente acréscimo)
create or replace function public.radar_fn_auditar() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_reg jsonb;
begin
  if tg_op = 'DELETE' then v_reg := to_jsonb(old); else v_reg := to_jsonb(new); end if;
  -- atualização que só mexe nos campos de saúde/relógio (feita pelo próprio banco
  -- a cada execução do robô) não é decisão de ninguém: não entra na trilha
  if tg_op = 'UPDATE'
     and (to_jsonb(old) - array['ultimo_sucesso_em','ultima_falha_em','ultimo_erro','falhas_consecutivas','atualizado_em'])
       = (to_jsonb(new) - array['ultimo_sucesso_em','ultima_falha_em','ultimo_erro','falhas_consecutivas','atualizado_em']) then
    return new;
  end if;
  insert into public.radar_auditoria (tabela, registro_id, acao, usuario, antes, depois)
  values (tg_table_name,
          coalesce(v_reg->>'id', v_reg->>'user_id', v_reg->>'slug', '?'),
          tg_op, auth.uid(),
          case when tg_op <> 'INSERT' then to_jsonb(old) end,
          case when tg_op <> 'DELETE' then to_jsonb(new) end);
  if tg_op = 'DELETE' then return old; end if;
  return new;
end $$;

create or replace function public.radar_fn_auditoria_imutavel() returns trigger
language plpgsql set search_path = public as $$
begin
  raise exception 'RADAR010: a trilha de auditoria não pode ser alterada nem apagada'
    using errcode = 'P0001';
end $$;

-- Versão anterior da captura é preservada sempre que o conteúdo muda
create or replace function public.radar_fn_captura_versionar() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  new.hash_conteudo := public.radar_hash_texto(new.texto);
  if tg_op = 'INSERT' then
    new.versao := 1;
    return new;
  end if;
  if new.fonte_id is distinct from old.fonte_id then
    raise exception 'RADAR011: uma captura não pode ser transferida para outra fonte'
      using errcode = 'P0001';
  end if;
  new.versao := old.versao;      -- o número da versão é controlado só por este gatilho
  if new.hash_conteudo is distinct from old.hash_conteudo and old.hash_conteudo is not null then
    insert into public.radar_capturas_versoes (captura_id, versao, titulo, texto, hash_conteudo)
    values (old.id, old.versao, old.titulo, old.texto, old.hash_conteudo)
    on conflict (captura_id, versao) do nothing;
    new.versao := old.versao + 1;
    new.atualizado_em := now();
  end if;
  return new;
end $$;

-- Se o texto oficial mudou, as evidências que dependem dele são reconferidas
create or replace function public.radar_fn_captura_reconferir() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.hash_conteudo is distinct from old.hash_conteudo then
    update public.radar_evidencias set conferido_em = null where captura_id = new.id;
  end if;
  return null;
end $$;

-- A conferência do trecho é SEMPRE calculada pelo banco; ninguém marca à mão
create or replace function public.radar_fn_evidencia_conferir() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_texto  text;
  v_versao int;
begin
  if tg_op = 'UPDATE' and new.assunto_id is distinct from old.assunto_id then
    raise exception 'RADAR022: uma evidência não pode ser transferida para outro assunto'
      using errcode = 'P0001';
  end if;
  select c.texto, c.versao into v_texto, v_versao
  from public.radar_capturas c where c.id = new.captura_id;
  new.trecho_conferido := coalesce(public.radar_trecho_confere(new.trecho_literal, v_texto), false);
  new.conferido_em     := now();
  new.versao_captura   := v_versao;
  insert into public.radar_assunto_capturas (assunto_id, captura_id)
  values (new.assunto_id, new.captura_id) on conflict do nothing;
  return new;
end $$;

-- Campo de autoria não pode ser trocado; a única mudança aceita é virar nulo
-- quando o usuário deixa de existir (ação "on delete set null" da chave estrangeira).
create or replace function public.radar_manter_usuario(p_antigo uuid, p_novo uuid) returns uuid
language sql stable security definer set search_path = public as $$
  select case when p_novo is null and p_antigo is not null
                   and not exists (select 1 from auth.users u where u.id = p_antigo)
              then null else p_antigo end
$$;

-- Aprovação: só pessoa (admin/editor); texto alterado depois de aprovado volta para revisão
create or replace function public.radar_fn_conteudo_aprovacao() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if tg_op = 'UPDATE' and new.assunto_id is distinct from old.assunto_id then
    raise exception 'RADAR021: um conteúdo não pode ser transferido para outro assunto'
      using errcode = 'P0001';
  end if;

  if tg_op = 'UPDATE' then
    new.gerado_por := old.gerado_por;     -- a origem do texto não se reescreve
  end if;

  if tg_op = 'UPDATE' and old.status = 'aprovado' and new.status = 'aprovado'
     and (new.titulo is distinct from old.titulo or new.corpo is distinct from old.corpo
          or new.formato is distinct from old.formato) then
    new.status := 'em_revisao';
  end if;

  if new.status = 'aprovado' and (tg_op = 'INSERT' or old.status is distinct from 'aprovado') then
    if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
      raise exception 'RADAR020: a aprovação exige um usuário com perfil de editor ou administrador (o robô e a IA não aprovam)'
        using errcode = 'P0001';
    end if;
    new.aprovado_por := auth.uid();
    new.aprovado_em  := now();
  elsif new.status <> 'aprovado' then
    new.aprovado_por := null;
    new.aprovado_em  := null;
  else
    -- continua aprovado: quem/quando não mudam (só vira nulo se o usuário foi excluído)
    new.aprovado_por := public.radar_manter_usuario(old.aprovado_por, new.aprovado_por);
    new.aprovado_em  := old.aprovado_em;
  end if;
  return new;
end $$;

-- Pré-requisitos de publicação de um assunto. Devolve NULL se está tudo certo,
-- ou o motivo (texto) do que falta.
create or replace function public.radar_pendencia_assunto(p_assunto bigint) returns text
language plpgsql stable security definer set search_path = public as $$
declare
  v_situacao text;
begin
  select a.situacao_confirmacao into v_situacao from public.radar_assuntos a where a.id = p_assunto;
  if v_situacao is distinct from 'confirmado_oficialmente' then
    return format('RADAR031: o assunto não está CONFIRMADO OFICIALMENTE (situação atual: %s)',
                  coalesce(v_situacao, 'inexistente'));
  end if;
  if not exists (
    select 1
    from public.radar_evidencias e
    join public.radar_capturas c on c.id = e.captura_id
    join public.radar_fontes   f on f.id = c.fonte_id
    where e.assunto_id = p_assunto and e.trecho_conferido and f.oficial
  ) then
    return 'RADAR032: FUNDAMENTAÇÃO NÃO CONFIRMADA — necessária análise técnica (nenhum trecho conferido em fonte oficial)';
  end if;
  return null;
end $$;

-- Portão de publicação.
--  * título e corpo NUNCA vêm de quem grava: são copiados do conteúdo;
--  * publicar exige pessoa (editor/admin), conteúdo aprovado, assunto confirmado
--    oficialmente e ao menos uma evidência conferida em fonte oficial;
--  * depois de publicado, o texto, o endereço e o vínculo ficam travados
--    (para corrigir: despublicar, revisar o conteúdo e publicar de novo; ou errata).
create or replace function public.radar_fn_publicacao_portao() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_conteudo  public.radar_conteudos%rowtype;
  v_pendencia text;
begin
  if tg_op = 'INSERT' then
    new.criado_por    := auth.uid();
    new.criado_em     := now();
    new.publicado_por := null;
    new.publicado_em  := null;
    new.requer_revisao := false;
    new.motivo_revisao := null;
  else
    new.criado_por := public.radar_manter_usuario(old.criado_por, new.criado_por);
    new.criado_em  := old.criado_em;
  end if;

  if tg_op = 'UPDATE' and old.status = 'publicado' and new.status = 'publicado' then
    if new.conteudo_id is distinct from old.conteudo_id or new.titulo is distinct from old.titulo
       or new.corpo is distinct from old.corpo or new.slug is distinct from old.slug then
      raise exception 'RADAR034: publicação no ar não pode ter texto, endereço ou conteúdo trocados — despublique, revise e publique de novo, ou registre uma errata'
        using errcode = 'P0001';
    end if;
    new.publicado_por := public.radar_manter_usuario(old.publicado_por, new.publicado_por);
    new.publicado_em  := old.publicado_em;
    return new;
  end if;

  -- "for share": uma edição simultânea do conteúdo espera a publicação terminar (e vice-versa)
  select * into v_conteudo from public.radar_conteudos c where c.id = new.conteudo_id for share;
  new.titulo := coalesce(v_conteudo.titulo, '');
  new.corpo  := coalesce(v_conteudo.corpo, '');

  if new.status <> 'publicado' then
    if tg_op = 'UPDATE' then
      new.publicado_por := public.radar_manter_usuario(old.publicado_por, new.publicado_por);
      new.publicado_em  := old.publicado_em;
    end if;
    return new;
  end if;

  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR033: a publicação exige um usuário com perfil de editor ou administrador (o robô e a IA não publicam)'
      using errcode = 'P0001';
  end if;
  if v_conteudo.status is distinct from 'aprovado' then
    raise exception 'RADAR030: só é possível publicar conteúdo aprovado (situação atual: %)',
      coalesce(v_conteudo.status, 'inexistente') using errcode = 'P0001';
  end if;
  v_pendencia := public.radar_pendencia_assunto(v_conteudo.assunto_id);
  if v_pendencia is not null then
    raise exception '%', v_pendencia using errcode = 'P0001';
  end if;

  new.publicado_por  := auth.uid();
  new.publicado_em   := now();
  new.requer_revisao := false;
  new.motivo_revisao := null;
  return new;
end $$;

-- Se um pré-requisito cai DEPOIS da publicação (conteúdo volta para revisão,
-- assunto deixa de estar confirmado, evidência deixa de conferir, fonte deixa
-- de ser oficial), a publicação é sinalizada para revisão. A retirada do ar é
-- decisão humana — o sistema avisa, não despublica sozinho.
create or replace function public.radar_sinalizar_assunto(p_assunto bigint) returns void
language plpgsql security definer set search_path = public as $$
declare
  v_pendencia text := public.radar_pendencia_assunto(p_assunto);
begin
  update public.radar_publicacoes p
     set requer_revisao = true,
         motivo_revisao = coalesce(v_pendencia, 'o conteúdo publicado voltou para revisão ou foi rejeitado')
    from public.radar_conteudos c
   where c.id = p.conteudo_id and c.assunto_id = p_assunto and p.status = 'publicado'
     and (v_pendencia is not null or c.status <> 'aprovado')
     and (p.requer_revisao is not true
          or p.motivo_revisao is distinct from coalesce(v_pendencia, 'o conteúdo publicado voltou para revisão ou foi rejeitado'));
end $$;

create or replace function public.radar_fn_sinalizar() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  r record;
begin
  if tg_table_name = 'radar_fontes' then
    if new.oficial is distinct from old.oficial then
      for r in select distinct e.assunto_id from public.radar_evidencias e
               join public.radar_capturas c on c.id = e.captura_id where c.fonte_id = new.id loop
        perform public.radar_sinalizar_assunto(r.assunto_id);
      end loop;
    end if;
  elsif tg_table_name = 'radar_assuntos' then
    perform public.radar_sinalizar_assunto(new.id);
  elsif tg_op = 'DELETE' then
    perform public.radar_sinalizar_assunto(old.assunto_id);
  else
    perform public.radar_sinalizar_assunto(new.assunto_id);
  end if;
  return null;
end $$;

-- Saúde da fonte é atualizada pelo próprio banco ao fechar cada execução
create or replace function public.radar_fn_execucao_saude() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.status = 'em_andamento' then return null; end if;
  if tg_op = 'UPDATE' and old.status = new.status then return null; end if;

  if new.status = 'ok' then
    update public.radar_fontes
       set ultimo_sucesso_em = coalesce(new.finalizado_em, now()),
           falhas_consecutivas = 0, ultimo_erro = null
     where id = new.fonte_id;
  else
    update public.radar_fontes
       set ultima_falha_em = coalesce(new.finalizado_em, now()),
           falhas_consecutivas = falhas_consecutivas + 1,
           ultimo_erro = left(coalesce(new.erro, new.status), 500)
     where id = new.fonte_id;
  end if;
  return null;
end $$;

-- ---------------------------------------------------------------------
-- 3. GATILHOS
-- ---------------------------------------------------------------------
drop trigger if exists radar_tg_fontes_atualizado on public.radar_fontes;
create trigger radar_tg_fontes_atualizado before update on public.radar_fontes
  for each row execute function public.radar_fn_atualizado_em();

drop trigger if exists radar_tg_assuntos_atualizado on public.radar_assuntos;
create trigger radar_tg_assuntos_atualizado before update on public.radar_assuntos
  for each row execute function public.radar_fn_atualizado_em();

drop trigger if exists radar_tg_conteudos_atualizado on public.radar_conteudos;
create trigger radar_tg_conteudos_atualizado before update on public.radar_conteudos
  for each row execute function public.radar_fn_atualizado_em();

drop trigger if exists radar_tg_publicacoes_atualizado on public.radar_publicacoes;
create trigger radar_tg_publicacoes_atualizado before update on public.radar_publicacoes
  for each row execute function public.radar_fn_atualizado_em();

drop trigger if exists radar_tg_normas_atualizado on public.radar_normas;
create trigger radar_tg_normas_atualizado before update on public.radar_normas
  for each row execute function public.radar_fn_atualizado_em();

drop trigger if exists radar_tg_captura_versionar on public.radar_capturas;
create trigger radar_tg_captura_versionar before insert or update on public.radar_capturas
  for each row execute function public.radar_fn_captura_versionar();

drop trigger if exists radar_tg_captura_reconferir on public.radar_capturas;
create trigger radar_tg_captura_reconferir after update on public.radar_capturas
  for each row execute function public.radar_fn_captura_reconferir();

drop trigger if exists radar_tg_evidencia_conferir on public.radar_evidencias;
create trigger radar_tg_evidencia_conferir before insert or update on public.radar_evidencias
  for each row execute function public.radar_fn_evidencia_conferir();

drop trigger if exists radar_tg_conteudo_aprovacao on public.radar_conteudos;
create trigger radar_tg_conteudo_aprovacao before insert or update on public.radar_conteudos
  for each row execute function public.radar_fn_conteudo_aprovacao();

drop trigger if exists radar_tg_publicacao_portao on public.radar_publicacoes;
create trigger radar_tg_publicacao_portao before insert or update on public.radar_publicacoes
  for each row execute function public.radar_fn_publicacao_portao();

drop trigger if exists radar_tg_sinalizar on public.radar_assuntos;
create trigger radar_tg_sinalizar after update on public.radar_assuntos
  for each row execute function public.radar_fn_sinalizar();
drop trigger if exists radar_tg_sinalizar on public.radar_conteudos;
create trigger radar_tg_sinalizar after update on public.radar_conteudos
  for each row execute function public.radar_fn_sinalizar();
drop trigger if exists radar_tg_sinalizar on public.radar_evidencias;
create trigger radar_tg_sinalizar after update or delete on public.radar_evidencias
  for each row execute function public.radar_fn_sinalizar();
drop trigger if exists radar_tg_sinalizar on public.radar_fontes;
create trigger radar_tg_sinalizar after update of oficial on public.radar_fontes
  for each row execute function public.radar_fn_sinalizar();

drop trigger if exists radar_tg_execucao_saude on public.radar_execucoes;
create trigger radar_tg_execucao_saude after insert or update on public.radar_execucoes
  for each row execute function public.radar_fn_execucao_saude();

drop trigger if exists radar_tg_auditoria_imutavel on public.radar_auditoria;
create trigger radar_tg_auditoria_imutavel before update or delete on public.radar_auditoria
  for each row execute function public.radar_fn_auditoria_imutavel();

drop trigger if exists radar_tg_auditoria_sem_truncate on public.radar_auditoria;
create trigger radar_tg_auditoria_sem_truncate before truncate on public.radar_auditoria
  for each statement execute function public.radar_fn_auditoria_imutavel();

do $$
declare t text;
begin
  foreach t in array array['radar_perfis','radar_fontes','radar_normas','radar_assuntos',
                           'radar_evidencias','radar_conteudos','radar_publicacoes'] loop
    execute format('drop trigger if exists radar_tg_auditar on public.%I', t);
    execute format('create trigger radar_tg_auditar after insert or update or delete on public.%I
                    for each row execute function public.radar_fn_auditar()', t);
  end loop;
end $$;

-- ---------------------------------------------------------------------
-- 4. VISÃO DE SAÚDE DAS FONTES
-- ---------------------------------------------------------------------
create or replace view public.radar_v_saude_fontes
with (security_invoker = true) as
select f.id, f.slug, f.nome, f.orgao, f.ativo, f.validada, f.frequencia_horas,
       f.ultimo_sucesso_em, f.ultima_falha_em, f.falhas_consecutivas, f.ultimo_erro,
       case
         when not f.ativo then 'inativa'
         when f.ultimo_sucesso_em is null and f.ultima_falha_em is null then 'nunca_executou'
         when f.ultimo_sucesso_em is null then 'nunca_funcionou'
         when f.falhas_consecutivas >= 3 then 'falhando'
         when f.ultimo_sucesso_em < now() - make_interval(hours => f.frequencia_horas * 3) then 'atrasada'
         when f.falhas_consecutivas > 0 then 'instavel'
         else 'ok'
       end as saude
from public.radar_fontes f;

-- ---------------------------------------------------------------------
-- 5. RLS
-- ---------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['radar_instalacoes','radar_perfis','radar_categorias','radar_fontes',
      'radar_execucoes','radar_capturas','radar_capturas_versoes','radar_normas','radar_assuntos',
      'radar_assunto_capturas','radar_evidencias','radar_conteudos','radar_publicacoes',
      'radar_publicacao_normas','radar_auditoria'] loop
    execute format('alter table public.%I enable row level security', t);
    -- parte do zero: o Supabase concede tudo a esses papéis por padrão
    execute format('revoke all on public.%I from public, anon, authenticated, service_role', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);  -- quem decide é a RLS
    execute format('grant select on public.%I to service_role', t);
  end loop;
end $$;

-- service_role (robô e, no Bloco 2, a função de IA): só o que precisa gravar.
-- NÃO grava auditoria, publicações, perfis, fontes, versões nem apaga nada.
grant insert, update on public.radar_execucoes, public.radar_capturas to service_role;
grant insert, update on public.radar_assuntos, public.radar_assunto_capturas, public.radar_evidencias,
                        public.radar_conteudos, public.radar_normas to service_role;

-- público: categorias e as colunas de vitrine das publicações (nada de uso interno)
grant select on public.radar_categorias to anon;
grant select (id, slug, titulo, corpo, categoria, publicar_em, errata, atualizado_em)
  on public.radar_publicacoes to anon;

revoke all on public.radar_v_saude_fontes from public, anon, authenticated, service_role;
grant select on public.radar_v_saude_fontes to authenticated, service_role;

-- sequências das colunas identity: ninguém precisa de acesso direto
do $$
declare q record;
begin
  for q in select c.oid::regclass as nome from pg_class c join pg_namespace n on n.oid = c.relnamespace
           where n.nspname = 'public' and c.relkind = 'S' and c.relname like 'radar\_%' loop
    execute format('revoke all on sequence %s from public, anon, authenticated, service_role', q.nome);
  end loop;
end $$;

-- funções: nada exposto como RPC ao público
do $$
declare f record;
begin
  for f in select p.oid::regprocedure as assinatura from pg_proc p join pg_namespace n on n.oid = p.pronamespace
           where n.nspname = 'public' and p.proname like 'radar\_%' loop
    execute format('revoke all on function %s from public, anon, authenticated, service_role', f.assinatura);
  end loop;
end $$;
grant execute on function public.radar_papel() to authenticated, service_role;

-- perfis
drop policy if exists radar_perfis_sel on public.radar_perfis;
create policy radar_perfis_sel on public.radar_perfis for select to authenticated
  using (user_id = auth.uid() or (select public.radar_papel()) = 'admin');
drop policy if exists radar_perfis_adm on public.radar_perfis;
create policy radar_perfis_adm on public.radar_perfis for all to authenticated
  using ((select public.radar_papel()) = 'admin') with check ((select public.radar_papel()) = 'admin');

-- categorias (leitura pública; escrita do admin)
drop policy if exists radar_categorias_sel on public.radar_categorias;
create policy radar_categorias_sel on public.radar_categorias for select to anon, authenticated
  using (true);
drop policy if exists radar_categorias_adm on public.radar_categorias;
create policy radar_categorias_adm on public.radar_categorias for all to authenticated
  using ((select public.radar_papel()) = 'admin') with check ((select public.radar_papel()) = 'admin');

-- fontes (equipe lê; admin escreve)
drop policy if exists radar_fontes_sel on public.radar_fontes;
create policy radar_fontes_sel on public.radar_fontes for select to authenticated
  using ((select public.radar_papel()) is not null);
drop policy if exists radar_fontes_adm on public.radar_fontes;
create policy radar_fontes_adm on public.radar_fontes for all to authenticated
  using ((select public.radar_papel()) = 'admin') with check ((select public.radar_papel()) = 'admin');

-- tabelas que só o robô (service_role) grava: equipe apenas lê
do $$
declare t text;
begin
  foreach t in array array['radar_execucoes','radar_capturas','radar_capturas_versoes'] loop
    execute format('drop policy if exists %I on public.%I', t || '_sel', t);
    execute format('create policy %I on public.%I for select to authenticated
                    using ((select public.radar_papel()) is not null)', t || '_sel', t);
  end loop;
end $$;

-- tabelas editoriais: equipe lê; editor/admin grava; só admin apaga
do $$
declare t text;
begin
  foreach t in array array['radar_normas','radar_assuntos','radar_assunto_capturas',
                           'radar_evidencias','radar_conteudos','radar_publicacao_normas'] loop
    execute format('drop policy if exists %I on public.%I', t || '_sel', t);
    execute format('create policy %I on public.%I for select to authenticated
                    using ((select public.radar_papel()) is not null)', t || '_sel', t);
    execute format('drop policy if exists %I on public.%I', t || '_ins', t);
    execute format('create policy %I on public.%I for insert to authenticated
                    with check ((select public.radar_papel()) in (''admin'',''editor''))', t || '_ins', t);
    execute format('drop policy if exists %I on public.%I', t || '_upd', t);
    execute format('create policy %I on public.%I for update to authenticated
                    using ((select public.radar_papel()) in (''admin'',''editor''))
                    with check ((select public.radar_papel()) in (''admin'',''editor''))', t || '_upd', t);
    execute format('drop policy if exists %I on public.%I', t || '_del', t);
    execute format('create policy %I on public.%I for delete to authenticated
                    using ((select public.radar_papel()) = ''admin'')', t || '_del', t);
  end loop;
end $$;

-- publicações: o público só enxerga o que está publicado e com data vencida
drop policy if exists radar_publicacoes_vitrine on public.radar_publicacoes;
create policy radar_publicacoes_vitrine on public.radar_publicacoes for select to anon
  using (status = 'publicado' and publicar_em <= now());
drop policy if exists radar_publicacoes_sel on public.radar_publicacoes;
create policy radar_publicacoes_sel on public.radar_publicacoes for select to authenticated
  using ((select public.radar_papel()) is not null);
drop policy if exists radar_publicacoes_ins on public.radar_publicacoes;
create policy radar_publicacoes_ins on public.radar_publicacoes for insert to authenticated
  with check ((select public.radar_papel()) in ('admin','editor'));
drop policy if exists radar_publicacoes_upd on public.radar_publicacoes;
create policy radar_publicacoes_upd on public.radar_publicacoes for update to authenticated
  using ((select public.radar_papel()) in ('admin','editor'))
  with check ((select public.radar_papel()) in ('admin','editor'));
drop policy if exists radar_publicacoes_del on public.radar_publicacoes;
create policy radar_publicacoes_del on public.radar_publicacoes for delete to authenticated
  using ((select public.radar_papel()) = 'admin');

-- auditoria e instalações: só admin lê; ninguém grava pela API
drop policy if exists radar_auditoria_sel on public.radar_auditoria;
create policy radar_auditoria_sel on public.radar_auditoria for select to authenticated
  using ((select public.radar_papel()) = 'admin');
drop policy if exists radar_instalacoes_sel on public.radar_instalacoes;
create policy radar_instalacoes_sel on public.radar_instalacoes for select to authenticated
  using ((select public.radar_papel()) = 'admin');

-- ---------------------------------------------------------------------
-- 6. DADOS INICIAIS (não sobrescrevem o que já foi ajustado)
-- ---------------------------------------------------------------------
-- só na PRIMEIRA instalação: o que você apagar depois não volta sozinho
insert into public.radar_categorias (slug, nome, ordem)
select v.* from (values
  ('reforma-tributaria', 'Reforma Tributária', 10),
  ('simples-nacional',   'Simples Nacional',   20),
  ('federal',            'Federal',            30),
  ('santa-catarina',     'Santa Catarina',     40),
  ('trabalhista',        'Trabalhista',        50),
  ('contabilidade',      'Contabilidade',      60),
  ('pgfn',               'PGFN',               70),
  ('informativos',       'Informativos',       80)
) as v (slug, nome, ordem)
where not exists (select 1 from public.radar_instalacoes)
on conflict (slug) do nothing;

-- Fontes oficiais do MVP (espelho de robo/radar_fontes.json). Entram como
-- validada = false até o diagnóstico confirmar cada uma no ambiente real.
insert into public.radar_fontes (slug, nome, orgao, abrangencia, tipo_coletor, url, config, categoria_padrao, frequencia_horas)
select v.* from (values
  ('rfb-noticias', 'Receita Federal — Notícias', 'Receita Federal do Brasil', 'federal', 'rss', 'https://www.gov.br/receitafederal/pt-br/assuntos/noticias/RSS', '{"janela_dias": 30, "excluir_url": "(/view$|\\.(png|jpe?g|gif|pdf)(/view)?$)", "seletor_texto": "#content-core, #parent-fieldname-text, article, main"}'::jsonb, 'federal', 6),
  ('pgfn-noticias', 'PGFN — Notícias', 'Procuradoria-Geral da Fazenda Nacional', 'federal', 'html_links', 'https://www.gov.br/pgfn/pt-br/assuntos/noticias', '{"janela_dias": 30, "padrao_url": "/pgfn/pt-br/assuntos/noticias/\\d{4}/[^/?#]+$", "seletor_texto": "#content-core, #parent-fieldname-text, article, main"}'::jsonb, 'pgfn', 6),
  ('simples-noticias', 'Simples Nacional — Notícias', 'Comitê Gestor do Simples Nacional', 'federal', 'html_links', 'https://www8.receita.fazenda.gov.br/SimplesNacional/Noticias/TodasNoticias.aspx', '{"janela_dias": 60, "padrao_url": "NoticiaCompleta\\.aspx\\?id=[0-9a-fA-F-]{36}", "seletor_texto": "#conteudo, .conteudo, form, body"}'::jsonb, 'simples-nacional', 12),
  ('rfb-normas', 'Receita Federal — Atos normativos (Normas)', 'Receita Federal do Brasil', 'federal', 'normas_rfb', 'http://normas.receita.fazenda.gov.br/sijut2consulta/consulta.action', '{"janela_dias": 15, "excluir_orgao": "^(SRRF|DRF|ALF|IRF|DERAT|DEFIS|DELEX|DECEX|DEMAC|DRJ|ARF)", "url_texto": "http://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto={id}", "seletor_texto": "#divTexto, .divTexto, body"}'::jsonb, 'federal', 6),
  ('sefsc-legislacao', 'SEF/SC — Últimas legislações', 'Secretaria de Estado da Fazenda de Santa Catarina', 'estadual_sc', 'html_links', 'https://www.sef.sc.gov.br/', '{"janela_dias": 30, "padrao_url": "legislacao\\.sef\\.sc\\.gov\\.br/html/.+\\.html?$", "titulo_do_contexto": true, "seletor_texto": "body"}'::jsonb, 'santa-catarina', 12),
  ('cgibs-noticias', 'Comitê Gestor do IBS — Notícias', 'Comitê Gestor do IBS', 'federal', 'html_links', 'https://www.cgibs.gov.br/', '{"janela_dias": 30, "padrao_url": "^https://www\\.cgibs\\.gov\\.br/[a-z0-9]+(-[a-z0-9]+){4,}$", "exigir_data": false, "seletor_texto": "article, main, #content, body"}'::jsonb, 'reforma-tributaria', 12)
) as v (slug, nome, orgao, abrangencia, tipo_coletor, url, config, categoria_padrao, frequencia_horas)
-- só na PRIMEIRA instalação: fonte que você apagar depois não volta sozinha
where not exists (select 1 from public.radar_instalacoes)
on conflict (slug) do nothing;

-- ---------------------------------------------------------------------
-- 7. REGISTRO DA INSTALAÇÃO E EVIDÊNCIA
-- ---------------------------------------------------------------------
insert into public.radar_instalacoes (versao, antes, depois)
select 'v0.1.0', a.objetos,
       (select jsonb_agg(jsonb_build_object('tabela', c.relname, 'rls', c.relrowsecurity) order by c.relname)
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'radar\_%')
from _radar_antes a;

commit;

-- EVIDÊNCIA: exporte este resultado em CSV e guarde/envie para conferência.
-- Esperado: 15 tabelas, todas com rls = true; 6 fontes; 8 categorias.
select 'tabela' as item, c.relname as nome, c.relrowsecurity::text as rls,
       (select count(*) from pg_policies p where p.schemaname = 'public' and p.tablename = c.relname)::text as politicas,
       (select count(*) from pg_trigger g where g.tgrelid = c.oid and not g.tgisinternal)::text as gatilhos
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'radar\_%'
union all
select 'fontes', count(*)::text, null, null, null from public.radar_fontes
union all
select 'categorias', count(*)::text, null, null, null from public.radar_categorias
union all
select 'instalacoes', count(*)::text, max(versao), null, null from public.radar_instalacoes
order by 1, 2;
