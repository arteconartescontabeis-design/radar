-- =====================================================================
-- RADAR ARTECON — Plataforma de Inteligência Contábil e Tributária
-- radar-setup-v0.4.0.sql  ·  banco, coletores, telas, IA e Informativo Mensal
--
-- Serve para instalar do zero e para atualizar qualquer versão anterior (se já estiver instalada).
-- IDEMPOTENTE: pode ser executado mais de uma vez sem duplicar nem apagar
-- dados. Cada execução fica registrada em radar_instalacoes com o estado
-- ANTES e DEPOIS. A última instrução devolve a evidência da instalação.
-- Reversão: radar-reversao-v0.4.0.sql
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
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'radar_conteudos_tamanho') then
    alter table public.radar_conteudos add constraint radar_conteudos_tamanho
      check (length(corpo) <= 60000 and length(titulo) <= 300) not valid;      -- vale para o que for gravado daqui em diante
  end if;
end $$;
-- pontos que a verificação automática mandou conferir no texto gerado pela IA
alter table public.radar_conteudos add column if not exists avisos_ia jsonb not null default '[]'::jsonb;

-- registro de uso da IA (quem pediu, o quê, quanto consumiu)
create table if not exists public.radar_ia_uso (
  id              bigint generated always as identity primary key,
  usuario         uuid        references auth.users(id) on delete set null,
  acao            text        not null check (acao in ('classificar','fundamentar','gerar')),
  modelo          text        not null,
  tokens_entrada  int         not null default 0 check (tokens_entrada >= 0),
  tokens_saida    int         not null default 0 check (tokens_saida >= 0),
  assunto_id      bigint      references public.radar_assuntos(id) on delete set null,
  em              timestamptz not null default now()
);
create index if not exists radar_ia_uso_em_idx on public.radar_ia_uso (em desc);
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'radar_ia_uso_teto') then
    alter table public.radar_ia_uso add constraint radar_ia_uso_teto
      check (tokens_entrada <= 5000000 and tokens_saida <= 5000000);
  end if;
end $$;

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
alter table public.radar_publicacoes add column if not exists formato text;
alter table public.radar_publicacoes add column if not exists fundamentacao jsonb not null default '[]'::jsonb;
-- um conteúdo tem no máximo UMA publicação (republicar reaproveita a mesma)
create unique index if not exists radar_publicacoes_conteudo_uk on public.radar_publicacoes (conteudo_id);
create index if not exists radar_publicacoes_vitrine_idx on public.radar_publicacoes (status, publicar_em desc);

create table if not exists public.radar_publicacao_normas (
  publicacao_id bigint not null references public.radar_publicacoes(id) on delete cascade,
  norma_id      bigint not null references public.radar_normas(id) on delete restrict,
  primary key (publicacao_id, norma_id)
);

-- imagens dos conteúdos (reduzidas no navegador antes de enviar)
create table if not exists public.radar_imagens (
  id          bigint generated always as identity primary key,
  dados       text        not null
              check (dados ~ '^data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/]{40,}={0,2}$' and length(dados) <= 900000),
  largura     int         check (largura between 1 and 20000),
  altura      int         check (altura between 1 and 20000),
  criado_por  uuid        references auth.users(id) on delete set null,
  criado_em   timestamptz not null default now()
);
alter table public.radar_conteudos   add column if not exists imagem_id     bigint references public.radar_imagens(id) on delete set null;
alter table public.radar_conteudos   add column if not exists autor         text;
alter table public.radar_conteudos   add column if not exists fonte_credito text;
alter table public.radar_publicacoes add column if not exists imagem_id     bigint references public.radar_imagens(id) on delete restrict;
alter table public.radar_publicacoes add column if not exists autor         text;
alter table public.radar_publicacoes add column if not exists fonte_credito text;

-- configurações editáveis pelo administrador (agenda de obrigações, fale conosco, fecho, feriados)
create table if not exists public.radar_config (
  chave         text primary key,
  valor         jsonb       not null,
  atualizado_em timestamptz not null default now()
);

-- Informativo Mensal: cada edição reúne a agenda de obrigações e conteúdos aprovados
create table if not exists public.radar_informativos (
  id               bigint generated always as identity primary key,
  numero           int         not null check (numero between 1 and 9999),
  ano              int         not null check (ano between 2000 and 2100),
  mes              date        not null check (extract(day from mes) = 1),      -- mês de referência da agenda
  agenda           jsonb       not null default '[]'::jsonb
                   check (jsonb_typeof(agenda) = 'array' and length(agenda::text) <= 100000),
  data_assinatura  date        not null default current_date,
  status           text        not null default 'rascunho' check (status in ('rascunho','fechado')),
  fechado_em       timestamptz,                                    -- preenchido pelo banco ao fechar
  criado_por       uuid        references auth.users(id) on delete set null,
  criado_em        timestamptz not null default now(),
  atualizado_em    timestamptz not null default now(),
  constraint radar_informativos_numero_uk unique (numero, ano)
);
create table if not exists public.radar_informativo_itens (
  informativo_id  bigint not null references public.radar_informativos(id) on delete cascade,
  conteudo_id     bigint not null references public.radar_conteudos(id) on delete restrict,
  ordem           int    not null default 100,
  primary key (informativo_id, conteudo_id)
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

-- Endereço amigável a partir de um título ("CBS: o que muda" → "cbs-o-que-muda")
create or replace function public.radar_slug(t text) returns text
language sql immutable set search_path = public as $$
  select btrim(regexp_replace(
           translate(lower(coalesce(t, '')), 'áàâãäéèêëíìîïóòôõöúùûüçñ', 'aaaaaeeeeiiiiooooouuuucn'),
           '[^a-z0-9]+', '-', 'g'), '-')
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
          coalesce(v_reg->>'id', v_reg->>'user_id', v_reg->>'slug', v_reg->>'chave', '?'),
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
    new.modelo_ia  := old.modelo_ia;
    new.avisos_ia  := old.avisos_ia;      -- nem os pontos que a verificação mandou conferir
  elsif new.gerado_por = 'humano' then
    new.modelo_ia := null;
    new.avisos_ia := '[]'::jsonb;
  end if;

  if tg_op = 'UPDATE' and old.status = 'aprovado' and new.status = 'aprovado'
     and (new.titulo is distinct from old.titulo or new.corpo is distinct from old.corpo
          or new.formato is distinct from old.formato or new.imagem_id is distinct from old.imagem_id
          or new.autor is distinct from old.autor or new.fonte_credito is distinct from old.fonte_credito) then
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
    new.fundamentacao := '[]'::jsonb;
    new.criado_por    := auth.uid();
    new.criado_em     := now();
    new.publicado_por := null;
    new.publicado_em  := null;
    new.requer_revisao := false;
    new.motivo_revisao := null;
  else
    new.criado_por := public.radar_manter_usuario(old.criado_por, new.criado_por);
    new.criado_em  := old.criado_em;
    if new.conteudo_id is distinct from old.conteudo_id and old.status <> 'publicado' then
      raise exception 'RADAR035: uma publicação não pode ser apontada para outro conteúdo'
        using errcode = 'P0001';
    end if;
  end if;

  if tg_op = 'UPDATE' and old.status = 'publicado' and new.status = 'publicado' then
    if new.conteudo_id is distinct from old.conteudo_id or new.titulo is distinct from old.titulo
       or new.corpo is distinct from old.corpo or new.slug is distinct from old.slug then
      raise exception 'RADAR034: publicação no ar não pode ter texto, endereço ou conteúdo trocados — despublique, revise e publique de novo, ou registre uma errata'
        using errcode = 'P0001';
    end if;
    new.publicado_por := public.radar_manter_usuario(old.publicado_por, new.publicado_por);
    new.publicado_em  := old.publicado_em;
    new.formato       := old.formato;
    new.fundamentacao := old.fundamentacao;
    new.imagem_id     := old.imagem_id;
    new.autor         := old.autor;
    new.fonte_credito := old.fonte_credito;
    return new;
  end if;

  -- "for share": uma edição simultânea do conteúdo espera a publicação terminar (e vice-versa)
  select * into v_conteudo from public.radar_conteudos c where c.id = new.conteudo_id for share;
  new.titulo  := coalesce(v_conteudo.titulo, '');
  new.corpo   := coalesce(v_conteudo.corpo, '');
  new.formato := v_conteudo.formato;
  new.imagem_id     := v_conteudo.imagem_id;
  new.autor         := v_conteudo.autor;
  new.fonte_credito := v_conteudo.fonte_credito;
  if tg_op = 'INSERT' then
    -- endereço: o informado (higienizado) ou gerado do título; o nº garante que não repete
    new.slug := btrim(left(public.radar_slug(coalesce(nullif(btrim(new.slug), ''), new.titulo)), 80), '-');
    if new.slug = '' then new.slug := 'publicacao'; end if;
    if exists (select 1 from public.radar_publicacoes p where p.slug = new.slug) then
      new.slug := new.slug || '-' || new.id;
      while exists (select 1 from public.radar_publicacoes p where p.slug = new.slug) loop
        new.slug := new.slug || '-' || substr(md5(random()::text), 1, 4);
      end loop;
    end if;
  else
    new.slug          := old.slug;        -- endereço não muda depois de criado
    new.fundamentacao := old.fundamentacao;
  end if;
  if new.categoria is null then
    select a.categoria into new.categoria from public.radar_assuntos a where a.id = v_conteudo.assunto_id;
  end if;

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

  -- A fundamentação que o público vê é uma fotografia das evidências conferidas
  -- em fonte oficial no momento da publicação (fica travada junto com o texto).
  select coalesce(jsonb_agg(jsonb_build_object(
           'orgao', f.orgao, 'fonte', f.nome, 'titulo', c.titulo, 'url', c.url,
           'data', c.data_publicacao, 'dispositivo', e.dispositivo, 'trecho', e.trecho_literal,
           'natureza', e.natureza,
           'norma', case when n.id is not null then n.tipo || ' nº ' || n.numero || ' — ' || n.orgao end,
           'norma_url', n.url_oficial) order by e.id), '[]'::jsonb)
    into new.fundamentacao
  from public.radar_evidencias e
  join public.radar_capturas c on c.id = e.captura_id
  join public.radar_fontes   f on f.id = c.fonte_id
  left join public.radar_normas n on n.id = e.norma_id
  where e.assunto_id = v_conteudo.assunto_id and e.trecho_conferido and f.oficial;

  new.publicado_por  := auth.uid();
  new.publicado_em   := now();
  new.requer_revisao := false;
  new.motivo_revisao := null;
  if tg_op = 'UPDATE' and new.errata is not distinct from old.errata
     and (new.titulo is distinct from old.titulo or new.corpo is distinct from old.corpo) then
    new.errata := null;       -- voltou ao ar com texto NOVO: a errata do texto antigo não o acompanha
  end if;
  return new;
end $$;

-- Depois de publicar: o assunto passa a "publicado" e as normas citadas ficam
-- vinculadas à publicação (base do acompanhamento de normas alteradas).
create or replace function public.radar_fn_publicacao_efeitos() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_assunto bigint;
begin
  select c.assunto_id into v_assunto from public.radar_conteudos c where c.id = new.conteudo_id;
  if new.status = 'publicado' and (tg_op = 'INSERT' or old.status is distinct from 'publicado') then
    update public.radar_assuntos set status = 'publicado' where id = v_assunto and status <> 'publicado';
    delete from public.radar_publicacao_normas where publicacao_id = new.id;
    insert into public.radar_publicacao_normas (publicacao_id, norma_id)
    select distinct new.id, e.norma_id
    from public.radar_evidencias e
    join public.radar_capturas c on c.id = e.captura_id
    join public.radar_fontes   f on f.id = c.fonte_id
    where e.assunto_id = v_assunto and e.norma_id is not null and e.trecho_conferido and f.oficial
    on conflict do nothing;
  elsif tg_op = 'UPDATE' and old.status = 'publicado' and new.status <> 'publicado' then
    -- saiu do ar: se nada mais do assunto está publicado, ele volta a aparecer como "em andamento"
    update public.radar_assuntos a set status = 'aprovado'
     where a.id = v_assunto and a.status = 'publicado'
       and not exists (select 1 from public.radar_publicacoes p join public.radar_conteudos c on c.id = p.conteudo_id
                       where c.assunto_id = v_assunto and p.status = 'publicado');
  end if;
  return null;
end $$;

-- Uso da IA: quem registra é sempre o próprio usuário, na hora em que acontece
create or replace function public.radar_fn_ia_uso() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  new.usuario := auth.uid();
  new.em      := now();
  return new;
end $$;

-- Registro de uso da IA: só por aqui (ninguém insere direto na tabela), com valores limitados
create or replace function public.radar_registrar_uso_ia(p_acao text, p_modelo text, p_entrada int, p_saida int, p_assunto bigint)
returns void language plpgsql security definer set search_path = public as $$
begin
  if coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR050: seu perfil não permite usar a IA' using errcode = 'P0001';
  end if;
  insert into public.radar_ia_uso (acao, modelo, tokens_entrada, tokens_saida, assunto_id)
  values (p_acao, left(coalesce(p_modelo, '?'), 80),
          least(greatest(coalesce(p_entrada, 0), 0), 5000000), least(greatest(coalesce(p_saida, 0), 0), 5000000),
          (select a.id from public.radar_assuntos a where a.id = p_assunto));
end $$;

-- Evidência proposta pela IA: só é gravada se o banco conferir o trecho no texto de uma
-- captura OFICIAL deste assunto. Devolve o id, ou NULL se não conferiu (e nada é gravado).
create or replace function public.radar_registrar_evidencia_ia(p_assunto bigint, p_captura bigint, p_trecho text, p_dispositivo text)
returns bigint language plpgsql security definer set search_path = public as $$
declare
  v_id bigint;
begin
  if coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR050: seu perfil não permite usar a IA' using errcode = 'P0001';
  end if;
  if not exists (
    select 1 from public.radar_assunto_capturas ac
    join public.radar_capturas c on c.id = ac.captura_id
    join public.radar_fontes   f on f.id = c.fonte_id
    where ac.assunto_id = p_assunto and ac.captura_id = p_captura and f.oficial
      and public.radar_trecho_confere(p_trecho, c.texto)
  ) then
    return null;
  end if;
  insert into public.radar_evidencias (assunto_id, captura_id, trecho_literal, dispositivo, natureza)
  values (p_assunto, p_captura, left(p_trecho, 2000), nullif(left(btrim(coalesce(p_dispositivo, '')), 80), ''), 'fato_oficial')
  returning id into v_id;
  return v_id;
end $$;

-- Informativo: só entra conteúdo aprovado; edição fechada não muda (reabrir é do administrador)
create or replace function public.radar_fn_informativo_item() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_inf bigint := case when tg_op = 'DELETE' then old.informativo_id else new.informativo_id end;
begin
  -- quem não é da equipe é barrado antes de qualquer conferência (a mensagem não revela nada)
  if auth.uid() is not null and coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'permission denied for table radar_informativo_itens' using errcode = '42501';
  end if;
  if tg_op = 'UPDATE' and (new.informativo_id <> old.informativo_id or new.conteudo_id <> old.conteudo_id) then
    raise exception 'RADAR064: o artigo não troca de edição nem de conteúdo; remova e inclua de novo' using errcode = 'P0001';
  end if;
  if (select i.status from public.radar_informativos i where i.id = v_inf) = 'fechado' then
    raise exception 'RADAR061: este informativo está fechado; reabra para alterar' using errcode = 'P0001';
  end if;
  if tg_op <> 'DELETE' and (select c.status from public.radar_conteudos c where c.id = new.conteudo_id) is distinct from 'aprovado' then
    raise exception 'RADAR060: só conteúdo aprovado entra no informativo' using errcode = 'P0001';
  end if;
  if tg_op = 'DELETE' then return old; end if;
  return new;
end $$;

create or replace function public.radar_fn_informativo() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if tg_op = 'INSERT' then
    new.criado_por := auth.uid();
    new.criado_em  := now();
    new.status     := 'rascunho';        -- toda edição nasce em montagem; fechar é um passo à parte
    new.fechado_em := null;
    return new;
  end if;
  new.criado_por := public.radar_manter_usuario(old.criado_por, new.criado_por);
  new.criado_em  := old.criado_em;
  new.fechado_em := case when new.status = 'fechado' then coalesce(old.fechado_em, now()) end;
  -- excluir do Supabase o usuário que criou a edição só limpa a autoria: isso não é alteração da edição
  if old.status = 'fechado' and new.status = 'fechado'
     and (to_jsonb(new) - array['criado_por','atualizado_em']) is distinct from (to_jsonb(old) - array['criado_por','atualizado_em']) then
    raise exception 'RADAR061: este informativo está fechado; reabra para alterar' using errcode = 'P0001';
  end if;
  if old.status = 'fechado' and new.status = 'rascunho' and coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR062: só o administrador reabre um informativo fechado' using errcode = 'P0001';
  end if;
  if new.status = 'fechado' and old.status <> 'fechado' then
    if exists (select 1 from public.radar_informativo_itens it join public.radar_conteudos c on c.id = it.conteudo_id
               where it.informativo_id = new.id and c.status <> 'aprovado') then
      raise exception 'RADAR063: há conteúdo que deixou de estar aprovado; revise antes de fechar' using errcode = 'P0001';
    end if;
    new.fechado_em := now();
  end if;
  return new;
end $$;

create or replace function public.radar_fn_imagem() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  new.criado_por := auth.uid();
  new.criado_em  := now();
  return new;
end $$;

-- Não deixa o Radar sem nenhum administrador ativo
create or replace function public.radar_fn_ultimo_admin() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if not (old.papel = 'admin' and old.ativo) then
    return null;
  end if;
  -- uma alteração de administrador por vez: duas simultâneas não deixam o Radar sem nenhum
  perform pg_advisory_xact_lock(hashtextextended('radar_ultimo_admin', 0));
  if old.papel = 'admin' and old.ativo
     and not exists (select 1 from public.radar_perfis p where p.papel = 'admin' and p.ativo) then
    raise exception 'RADAR042: o Radar não pode ficar sem nenhum administrador ativo — defina outro administrador antes'
      using errcode = 'P0001';
  end if;
  return null;
end $$;

-- Abre um assunto a partir de uma captura (ou a marca como ignorada). Roda com as
-- permissões de quem chama: só editor/admin consegue, pela RLS.
create or replace function public.radar_abrir_assunto(p_captura bigint, p_ignorar boolean default false)
returns bigint language plpgsql set search_path = public as $$
declare
  v_id bigint;
begin
  -- duas chamadas simultâneas para a mesma captura (clique duplo) não criam dois assuntos
  perform pg_advisory_xact_lock(hashtextextended('radar_abrir_assunto:' || coalesce(p_captura, 0), 0));
  select ac.assunto_id into v_id from public.radar_assunto_capturas ac where ac.captura_id = p_captura limit 1;
  if v_id is not null then
    return v_id;
  end if;
  insert into public.radar_assuntos (titulo, categoria, abrangencia, status, resumo)
  select c.titulo, f.categoria_padrao, f.abrangencia,
         case when p_ignorar then 'ignorado' else 'capturado' end, c.resumo_fonte
  from public.radar_capturas c join public.radar_fontes f on f.id = c.fonte_id
  where c.id = p_captura
  returning id into v_id;
  if v_id is null then
    raise exception 'RADAR041: captura não encontrada' using errcode = 'P0001';
  end if;
  insert into public.radar_assunto_capturas (assunto_id, captura_id) values (v_id, p_captura);
  return v_id;
end $$;

-- Lista de usuários do projeto para o administrador montar os perfis
create or replace function public.radar_admin_usuarios()
returns table (user_id uuid, email text, nome text, papel text, ativo boolean)
language plpgsql stable security definer set search_path = public as $$
begin
  if coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR040: apenas o administrador pode listar os usuários' using errcode = 'P0001';
  end if;
  return query
    select u.id, u.email::text, p.nome, p.papel, p.ativo
    from auth.users u left join public.radar_perfis p on p.user_id = u.id
    order by u.email;
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

drop trigger if exists radar_tg_informativo on public.radar_informativos;
create trigger radar_tg_informativo before insert or update on public.radar_informativos
  for each row execute function public.radar_fn_informativo();
drop trigger if exists radar_tg_informativos_atualizado on public.radar_informativos;
create trigger radar_tg_informativos_atualizado before update on public.radar_informativos
  for each row execute function public.radar_fn_atualizado_em();
drop trigger if exists radar_tg_informativo_item on public.radar_informativo_itens;
create trigger radar_tg_informativo_item before insert or update or delete on public.radar_informativo_itens
  for each row execute function public.radar_fn_informativo_item();
drop trigger if exists radar_tg_imagem on public.radar_imagens;
create trigger radar_tg_imagem before insert on public.radar_imagens
  for each row execute function public.radar_fn_imagem();
drop trigger if exists radar_tg_config_atualizado on public.radar_config;
create trigger radar_tg_config_atualizado before update on public.radar_config
  for each row execute function public.radar_fn_atualizado_em();

drop trigger if exists radar_tg_ia_uso on public.radar_ia_uso;
create trigger radar_tg_ia_uso before insert on public.radar_ia_uso
  for each row execute function public.radar_fn_ia_uso();

drop trigger if exists radar_tg_ultimo_admin on public.radar_perfis;
create trigger radar_tg_ultimo_admin after update or delete on public.radar_perfis
  for each row execute function public.radar_fn_ultimo_admin();

drop trigger if exists radar_tg_publicacao_efeitos on public.radar_publicacoes;
create trigger radar_tg_publicacao_efeitos after insert or update on public.radar_publicacoes
  for each row execute function public.radar_fn_publicacao_efeitos();

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
                           'radar_evidencias','radar_conteudos','radar_publicacoes',
                           'radar_informativos','radar_config'] loop
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

-- Fila de triagem: capturas que ainda não viraram assunto (nem foram ignoradas)
create or replace view public.radar_v_fila
with (security_invoker = true) as
select c.id, c.fonte_id, f.slug as fonte_slug, f.nome as fonte_nome, f.orgao, f.abrangencia,
       f.categoria_padrao, f.oficial, c.url, c.titulo, c.data_publicacao, c.resumo_fonte,
       c.capturado_em, c.versao, (c.texto is not null) as tem_texto, c.duplicata_de
from public.radar_capturas c
join public.radar_fontes f on f.id = c.fonte_id
where not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = c.id);

-- Assuntos com os números que a lista do dashboard mostra
create or replace view public.radar_v_assuntos
with (security_invoker = true) as
select a.*,
       (select count(*) from public.radar_evidencias e where e.assunto_id = a.id) as evidencias,
       (select count(*) from public.radar_evidencias e where e.assunto_id = a.id and e.trecho_conferido) as evidencias_conferidas,
       (select count(*) from public.radar_conteudos c where c.assunto_id = a.id) as conteudos,
       (select count(*) from public.radar_conteudos c where c.assunto_id = a.id and c.status = 'em_revisao') as em_revisao,
       (select count(*) from public.radar_publicacoes p join public.radar_conteudos c on c.id = p.conteudo_id
         where c.assunto_id = a.id and p.status = 'publicado') as publicacoes_no_ar,
       (select string_agg(distinct f.orgao, ' · ') from public.radar_assunto_capturas ac
          join public.radar_capturas c on c.id = ac.captura_id
          join public.radar_fontes f on f.id = c.fonte_id where ac.assunto_id = a.id) as orgaos
from public.radar_assuntos a;

-- Consumo da IA no mês corrente (uma linha)
create or replace view public.radar_v_ia_mes
with (security_invoker = true) as
select count(*)::int as chamadas,
       coalesce(sum(tokens_entrada::bigint), 0)::bigint as tokens_entrada,
       coalesce(sum(tokens_saida::bigint), 0)::bigint as tokens_saida,
       coalesce(sum(tokens_entrada::bigint + tokens_saida::bigint), 0)::bigint as tokens
from public.radar_ia_uso
where em >= date_trunc('month', now());

-- Números do painel do dia (uma linha). É recriada: assim colunas novas entram em qualquer atualização.
drop view if exists public.radar_v_painel;
create view public.radar_v_painel
with (security_invoker = true) as
select (select count(*) from public.radar_v_saude_fontes where ativo) as fontes_ativas,
       (select count(*) from public.radar_v_saude_fontes where saude = 'ok') as fontes_ok,
       (select count(*) from public.radar_capturas where capturado_em > now() - interval '24 hours') as capturas_24h,
       (select count(*) from public.radar_v_fila) as na_fila,
       (select count(*) from public.radar_assuntos
         where relevancia = 'alta' and status not in ('publicado','ignorado','arquivado')) as alta_relevancia,
       (select count(*) from public.radar_assuntos
         where situacao_confirmacao = 'em_verificacao' and status not in ('publicado','ignorado','arquivado')) as em_verificacao,
       (select count(*) from public.radar_conteudos where status = 'em_revisao') as aguardando_aprovacao,
       (select count(*) from public.radar_publicacoes where status = 'publicado' and publicar_em <= now()) as no_ar,
       (select count(*) from public.radar_publicacoes where status = 'publicado' and requer_revisao) as requer_revisao,
       (select count(*) from public.radar_publicacoes where status = 'publicado' and publicar_em > now()) as agendadas;

-- ---------------------------------------------------------------------
-- 5. RLS
-- ---------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['radar_instalacoes','radar_perfis','radar_categorias','radar_fontes',
      'radar_execucoes','radar_capturas','radar_capturas_versoes','radar_normas','radar_assuntos',
      'radar_assunto_capturas','radar_evidencias','radar_conteudos','radar_publicacoes',
      'radar_publicacao_normas','radar_auditoria','radar_ia_uso','radar_imagens','radar_config',
      'radar_informativos','radar_informativo_itens'] loop
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
grant select (id, slug, titulo, corpo, formato, categoria, publicar_em, errata, fundamentacao, atualizado_em,
              imagem_id, autor, fonte_credito, status)      -- "status" só para a regra das imagens: o público só vê linhas no ar
  on public.radar_publicacoes to anon;
grant select (id, dados, largura, altura) on public.radar_imagens to anon;
-- imagem não se altera depois de enviada (troca-se por outra)
revoke update on public.radar_imagens from authenticated;

revoke all on public.radar_v_saude_fontes, public.radar_v_fila, public.radar_v_assuntos, public.radar_v_painel, public.radar_v_ia_mes
  from public, anon, authenticated, service_role;
grant select on public.radar_v_saude_fontes, public.radar_v_fila, public.radar_v_assuntos, public.radar_v_painel, public.radar_v_ia_mes
  to authenticated, service_role;
-- uso da IA: só se consulta; quem grava é a função radar_registrar_uso_ia
revoke insert, update, delete on public.radar_ia_uso from authenticated;

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
grant execute on function public.radar_abrir_assunto(bigint, boolean) to authenticated;
grant execute on function public.radar_admin_usuarios() to authenticated;
grant execute on function public.radar_registrar_uso_ia(text, text, int, int, bigint) to authenticated;
grant execute on function public.radar_registrar_evidencia_ia(bigint, bigint, text, text) to authenticated;

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
                           'radar_evidencias','radar_conteudos','radar_publicacao_normas',
                           'radar_imagens','radar_informativos','radar_informativo_itens'] loop
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

-- artigos do informativo: quem monta a edição também remove (edição fechada é barrada pelo gatilho)
drop policy if exists radar_informativo_itens_del on public.radar_informativo_itens;
create policy radar_informativo_itens_del on public.radar_informativo_itens for delete to authenticated
  using ((select public.radar_papel()) in ('admin','editor'));

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

-- imagens: o público só baixa as que pertencem a publicação no ar
drop policy if exists radar_imagens_vitrine on public.radar_imagens;
create policy radar_imagens_vitrine on public.radar_imagens for select to anon
  using (exists (select 1 from public.radar_publicacoes p      -- o visitante só enxerga publicações no ar (política da vitrine)
                 where p.imagem_id = radar_imagens.id and p.status = 'publicado' and p.publicar_em <= now()));

-- configurações: a equipe lê; o administrador altera
drop policy if exists radar_config_sel on public.radar_config;
create policy radar_config_sel on public.radar_config for select to authenticated
  using ((select public.radar_papel()) is not null);
drop policy if exists radar_config_adm on public.radar_config;
create policy radar_config_adm on public.radar_config for all to authenticated
  using ((select public.radar_papel()) = 'admin') with check ((select public.radar_papel()) = 'admin');

-- uso da IA: a equipe lê; a gravação é só pela função radar_registrar_uso_ia
drop policy if exists radar_ia_uso_sel on public.radar_ia_uso;
create policy radar_ia_uso_sel on public.radar_ia_uso for select to authenticated
  using ((select public.radar_papel()) is not null);
drop policy if exists radar_ia_uso_ins on public.radar_ia_uso;

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
  ('rfb-noticias', 'Receita Federal — Notícias', 'Receita Federal do Brasil', 'federal', 'html_links', 'https://www.gov.br/receitafederal/pt-br/assuntos/noticias/ultimas-noticias', '{"janela_dias": 30, "padrao_url": "/receitafederal/pt-br/assuntos/noticias/\\d{4}/[a-z]+/[^/?#]+$", "seletor_texto": "[property=''rnews:articleBody''], #parent-fieldname-text, #content-core, article, main"}'::jsonb, 'federal', 6),
  ('pgfn-noticias', 'PGFN — Notícias', 'Procuradoria-Geral da Fazenda Nacional', 'federal', 'html_links', 'https://www.gov.br/pgfn/pt-br/assuntos/noticias', '{"janela_dias": 30, "padrao_url": "/pgfn/pt-br/assuntos/noticias/\\d{4}/[^/?#]+$", "seletor_texto": "[property=''rnews:articleBody''], #parent-fieldname-text, #content-core, article, main"}'::jsonb, 'pgfn', 6),
  ('simples-noticias', 'Simples Nacional — Notícias', 'Comitê Gestor do Simples Nacional', 'federal', 'html_links', 'https://www8.receita.fazenda.gov.br/SimplesNacional/Noticias/TodasNoticias.aspx', '{"janela_dias": 60, "padrao_url": "NoticiaCompleta\\.aspx\\?id=[0-9a-fA-F-]{36}", "seletor_texto": "#conteudo, .conteudo, form, body"}'::jsonb, 'simples-nacional', 12),
  ('rfb-normas', 'Receita Federal — Atos normativos (Normas)', 'Receita Federal do Brasil', 'federal', 'normas_rfb', 'http://normas.receita.fazenda.gov.br/sijut2consulta/consulta.action?tipoData=2&dt_inicio={inicio}&dt_fim={fim}&optOrdem=Publicacao_DESC&p={p}', '{"janela_dias": 10, "paginas_max": 6, "itens_por_pagina": 100, "max_itens": 300, "excluir_orgao": "^(SRRF|DRF|ALF|IRF|DERAT|DEFIS|DELEX|DECEX|DEMAC|DRJ|ARF|DISIT)", "sem_pagina_de_texto": true, "diagnostico_urls": ["http://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=153881", "https://normasinternet2.receita.fazenda.gov.br/"]}'::jsonb, 'federal', 6),
  ('sefsc-legislacao', 'SEF/SC — Últimas legislações', 'Secretaria de Estado da Fazenda de Santa Catarina', 'estadual_sc', 'html_links', 'https://www.sef.sc.gov.br/', '{"janela_dias": 30, "padrao_url": "legislacao\\.sef\\.sc\\.gov\\.br/html/.+\\.html?$", "titulo_do_contexto": true, "seletor_texto": "body"}'::jsonb, 'santa-catarina', 12),
  ('cgibs-noticias', 'Comitê Gestor do IBS — Notícias', 'Comitê Gestor do IBS', 'federal', 'html_links', 'https://www.cgibs.gov.br/', '{"janela_dias": 30, "padrao_url": "^https://www\\.cgibs\\.gov\\.br/[a-z0-9]+(-[a-z0-9]+){4,}$", "data_do_texto": true, "seletor_texto": "article, main, #content, body"}'::jsonb, 'reforma-tributaria', 12)
) as v (slug, nome, orgao, abrangencia, tipo_coletor, url, config, categoria_padrao, frequencia_horas)
-- só na PRIMEIRA instalação: fonte que você apagar depois não volta sozinha
where not exists (select 1 from public.radar_instalacoes)
on conflict (slug) do nothing;


-- Configurações iniciais (só na PRIMEIRA vez em que cada chave não existe; depois valem as suas)
insert into public.radar_config (chave, valor) values
  ('obrigacoes', '[{"nome": "Salário dos Colaboradores (Empregados)", "regra": "quinto_dia_util"}, {"nome": "Salários - Trabalhador Doméstico", "regra": "dia", "dia": 7, "ajuste": "antecipa"}, {"nome": "ICMS", "regra": "dia", "dia": 10, "ajuste": "posterga"}, {"nome": "ICMS Substituição Tributária", "regra": "dia", "dia": 10, "ajuste": "posterga"}, {"nome": "Carnê INSS Individual", "regra": "dia", "dia": 15, "ajuste": "posterga"}, {"nome": "FGTS - Fundo de Garantia Por Tempo de Serviço", "regra": "dia", "dia": 20, "ajuste": "antecipa"}, {"nome": "GPS (Empresa)", "regra": "dia", "dia": 20, "ajuste": "antecipa"}, {"nome": "IRRF (Rendimento Serviço Prestado Cód. 1708)", "regra": "dia", "dia": 20, "ajuste": "antecipa"}, {"nome": "IRRF (Rendimento de Trabalhador Cód. 0561)", "regra": "dia", "dia": 20, "ajuste": "antecipa"}, {"nome": "Simples Doméstico", "regra": "dia", "dia": 20, "ajuste": "posterga"}, {"nome": "Simples Nacional", "regra": "dia", "dia": 20, "ajuste": "posterga"}, {"nome": "Honorário contábil", "regra": "dia", "dia": 20, "ajuste": "posterga"}, {"nome": "PIS", "regra": "dia", "dia": 25, "ajuste": "antecipa"}, {"nome": "COFINS", "regra": "dia", "dia": 25, "ajuste": "antecipa"}, {"nome": "IPI", "regra": "dia", "dia": 25, "ajuste": "antecipa"}, {"nome": "CSLL - Contribuição Social sobre o Lucro Líquido", "regra": "ultimo_dia_util"}, {"nome": "IRPJ - Imposto de Renda Pessoa Jurídica", "regra": "ultimo_dia_util"}, {"nome": "Imposto de Renda Pessoa Física (Cód. 0190)", "regra": "ultimo_dia_util"}, {"nome": "INSS - Parcelamento p/ Ingresso no Simples Nacional", "regra": "ultimo_dia_util"}, {"nome": "Parcelamentos Federais e Parcelamento Especial", "regra": "ultimo_dia_util"}, {"nome": "PERT – Programa Esp. Regularização Tributária", "regra": "ultimo_dia_util"}, {"nome": "Parcelamento Especial - Simples Nacional", "regra": "ultimo_dia_util"}]'::jsonb),
  ('feriados_extras', '[]'::jsonb),
  ('fale_conosco', '{"setores": [{"nome": "Geral", "rotulo": "Atendimento Geral", "telefones": ["48-3242-0530"], "emails": ["artecon@artecon.cnt.br"], "equipe": []}, {"nome": "Setor Contábil", "rotulo": "Setor Contábil", "telefones": [], "emails": ["dc@artecon.cnt.br"], "equipe": []}, {"nome": "Setor Fiscal", "rotulo": "Setor Fiscal", "telefones": [], "emails": ["df@artecon.cnt.br"], "equipe": []}, {"nome": "Departamento Pessoal", "rotulo": "Departamento Pessoal", "telefones": [], "emails": ["rh@artecon.cnt.br"], "equipe": []}, {"nome": "Setor Institucional", "rotulo": "Setor Institucional", "telefones": [], "emails": ["societario@artecon.cnt.br"], "equipe": []}], "observacao": ""}'::jsonb),
  ('assinatura', '{"local": "Palhoça, SC", "empresa": "Artecon Artes Contábeis ME", "responsavel": "Cleiver Gonçalves"}'::jsonb)
on conflict (chave) do nothing;

-- ---------------------------------------------------------------------
-- 7. REGISTRO DA INSTALAÇÃO E EVIDÊNCIA
-- ---------------------------------------------------------------------
insert into public.radar_instalacoes (versao, antes, depois)
select 'v0.4.0', a.objetos,
       (select jsonb_agg(jsonb_build_object('tabela', c.relname, 'rls', c.relrowsecurity) order by c.relname)
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'radar\_%')
from _radar_antes a;

commit;

-- EVIDÊNCIA: exporte este resultado em CSV e guarde/envie para conferência.
-- Esperado: 20 tabelas, todas com rls = true; 6 fontes; 8 categorias.
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
