-- =====================================================================
-- RADAR ARTECON — Plataforma de Inteligência Contábil e Tributária
-- radar-setup-v0.11.1.sql  ·  banco, coletores, telas, IA e Informativo Mensal
--
-- Serve para instalar do zero e para atualizar qualquer versão anterior (se já estiver instalada).
-- IDEMPOTENTE: pode ser executado mais de uma vez sem duplicar nem apagar
-- dados. Cada execução fica registrada em radar_instalacoes com o estado
-- ANTES e DEPOIS. A última instrução devolve a evidência da instalação.
-- Reversão: radar-reversao-v0.11.1.sql
-- =====================================================================

begin;

-- ---------------------------------------------------------------------
-- 0. ESTADO ANTES — gravado já no início, em radar_instalacoes, com "depois" vazio;
--    o fim do script preenche o "depois". Não depende de tabela temporária nem de o
--    editor manter a transação: funciona também se cada instrução for confirmada à parte.
--    Linha com "depois" vazio = execução que não chegou ao fim.
-- ---------------------------------------------------------------------
do $$
declare v_antes jsonb;
begin
  select coalesce(jsonb_agg(jsonb_build_object('tabela', c.relname, 'rls', c.relrowsecurity) order by c.relname), '[]'::jsonb)
    into v_antes
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'radar\_%';

  create table if not exists public.radar_instalacoes (
    id            bigint generated always as identity primary key,
    versao        text        not null,
    executado_em  timestamptz not null default now(),
    antes         jsonb       not null,
    depois        jsonb
  );
  insert into public.radar_instalacoes (versao, antes) values ('v0.11.1', v_antes);
end $$;

-- ---------------------------------------------------------------------
-- 1. TABELAS
-- ---------------------------------------------------------------------

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
                       check (tipo_coletor in ('rss','html_links','normas_rfb','inlabs')),
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
-- v0.6.0: relevância calculada pelo banco a partir das regras de radar_config.relevancia
alter table public.radar_capturas add column if not exists relevancia         text not null default 'media';
alter table public.radar_capturas add column if not exists relevancia_pontos  int  not null default 0;
alter table public.radar_capturas add column if not exists relevancia_motivos jsonb not null default '[]'::jsonb;
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'radar_capturas_relevancia_ck') then
    alter table public.radar_capturas add constraint radar_capturas_relevancia_ck check (relevancia in ('alta','media','baixa'));
  end if;
end $$;
create index if not exists radar_capturas_relevancia_idx on public.radar_capturas (relevancia);
-- v0.7.0: avaliação da IA feita pelo robô depois de cada coleta (o que está "em alta" para os clientes do escritório)
alter table public.radar_capturas add column if not exists ia_nota        smallint;
alter table public.radar_capturas add column if not exists ia_motivo      text;
alter table public.radar_capturas add column if not exists ia_tema        text;
alter table public.radar_capturas add column if not exists ia_avaliado_em timestamptz;
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'radar_capturas_ia_nota_ck') then
    alter table public.radar_capturas add constraint radar_capturas_ia_nota_ck check (ia_nota is null or ia_nota between 0 and 10);
  end if;
end $$;
create index if not exists radar_capturas_duplicata_idx on public.radar_capturas (duplicata_de) where duplicata_de is not null;

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
-- v0.7.0: marca a captura que a IA juntou sozinha como repetição (para a pessoa poder desfazer)
alter table public.radar_assunto_capturas add column if not exists juntada_pela_ia_em timestamptz;

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
  acao            text        not null constraint radar_ia_uso_acao_check check (acao in ('classificar','fundamentar','gerar','ilustrar')),
  modelo          text        not null,
  tokens_entrada  int         not null default 0 check (tokens_entrada >= 0),
  tokens_saida    int         not null default 0 check (tokens_saida >= 0),
  assunto_id      bigint      references public.radar_assuntos(id) on delete set null,
  em              timestamptz not null default now()
);
create index if not exists radar_ia_uso_em_idx on public.radar_ia_uso (em desc);
-- v0.6.0: a ilustração de capa por IA também é registrada no consumo
alter table public.radar_ia_uso drop constraint if exists radar_ia_uso_acao_check;
alter table public.radar_ia_uso add constraint radar_ia_uso_acao_check check (acao in ('classificar','fundamentar','gerar','ilustrar'));
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'radar_ia_uso_teto') then
    alter table public.radar_ia_uso add constraint radar_ia_uso_teto
      check (tokens_entrada <= 5000000 and tokens_saida <= 5000000);
  end if;
end $$;

-- v0.8.0: a antiga publicação dentro do próprio Radar (radar_publicacoes, com a vitrine e a sinalização de revisão)
-- saiu. A publicação é feita no site da Artecon e registrada em radar_divulgacoes. As tabelas só são apagadas
-- se estiverem vazias; uma instalação antiga que tenha publicações guardadas mantém as tabelas como arquivo.
do $$
begin
  if to_regclass('public.radar_publicacoes') is not null then
    if exists (select 1 from public.radar_publicacoes) then
      raise notice 'radar_publicacoes tem registros antigos: a tabela fica guardada como arquivo (sem uso pelo Radar)';
      -- arquivo só de leitura: sem as regras antigas, ninguém grava nele; e ele não prende imagens nem normas
      alter table public.radar_publicacoes drop constraint if exists radar_publicacoes_imagem_id_fkey;
      alter table public.radar_publicacao_normas drop constraint if exists radar_publicacao_normas_norma_id_fkey;
      drop policy if exists radar_publicacoes_ins on public.radar_publicacoes;
      drop policy if exists radar_publicacoes_upd on public.radar_publicacoes;
      drop policy if exists radar_publicacoes_del on public.radar_publicacoes;
      revoke insert, update, delete on public.radar_publicacoes, public.radar_publicacao_normas from authenticated, service_role, anon;
      execute 'drop policy if exists radar_publicacao_normas_ins on public.radar_publicacao_normas';
      execute 'drop policy if exists radar_publicacao_normas_upd on public.radar_publicacao_normas';
      execute 'drop policy if exists radar_publicacao_normas_del on public.radar_publicacao_normas';
    else
      drop table if exists public.radar_publicacao_normas cascade;
      drop table public.radar_publicacoes cascade;
    end if;
  end if;
end $$;
drop function if exists public.radar_fn_publicacao_portao() cascade;
drop function if exists public.radar_fn_publicacao_efeitos() cascade;
drop function if exists public.radar_fn_sinalizar() cascade;
drop function if exists public.radar_sinalizar_assunto(bigint) cascade;

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
-- conteúdo que não vai ao site (ex.: só para o Informativo Mensal): sai da fila "aprovados a publicar"
alter table public.radar_conteudos   add column if not exists fora_do_site  boolean not null default false;

-- Registro do que foi publicado no site da Artecon (v0.5.0): a publicação é feita no site;
-- aqui fica a data, o link e a cópia do texto aprovado que saiu.
create table if not exists public.radar_divulgacoes (
  id              bigint generated always as identity primary key,
  conteudo_id     bigint      not null references public.radar_conteudos(id) on delete restrict,
  url             text        not null          -- só caracteres visíveis comuns: nada de espaço, controle ou sinais que enganem a leitura
                  check (url ~ '^https?://[!-~]+$' and url !~ '[<>"''`]' and length(url) <= 500),
  publicado_em    date        not null default current_date,
  conteudo_lido_em timestamptz,                  -- "atualizado_em" do conteúdo que estava na tela de quem registrou
  observacao      text        check (length(observacao) <= 500),
  titulo          text        not null default '',      -- cópia do título e do texto aprovados no momento do registro
  corpo           text        not null default '',
  registrado_por  uuid        references auth.users(id) on delete set null,
  registrado_em   timestamptz not null default now()
);
create index if not exists radar_divulgacoes_conteudo_idx on public.radar_divulgacoes (conteudo_id);
-- fotografia das evidências conferidas em fonte oficial no momento do registro
alter table public.radar_divulgacoes add column if not exists fundamentacao jsonb not null default '[]'::jsonb;
alter table public.radar_divulgacoes add column if not exists conteudo_lido_em timestamptz;

-- v0.10.0: títulos alternativos sugeridos pela IA (a pessoa escolhe com um clique na tela do assunto)
alter table public.radar_conteudos add column if not exists titulos_sugeridos jsonb not null default '[]'::jsonb;

-- v0.10.0: autorização de publicação no site da Artecon. O administrador autoriza na tela do assunto; o robô
-- (workflow "Radar — publicar no site") cadastra a notícia no painel do site — que publica na hora — e registra o
-- link em radar_divulgacoes. Nada vai ao ar sem esta autorização. O robô nunca envia duas vezes a mesma autorização:
-- passa para "enviando" antes de enviar e, se cair no meio, só confere no site se a notícia saiu.
create table if not exists public.radar_site_envios (
  id               bigint generated always as identity primary key,
  conteudo_id      bigint      not null references public.radar_conteudos(id) on delete restrict,
  categoria        text        not null check (length(categoria) between 2 and 80),
  conteudo_lido_em timestamptz not null,          -- versão do texto que foi vista e autorizada
  situacao         text        not null default 'autorizado'
                   check (situacao in ('autorizado','enviando','publicado','erro','cancelado')),
  autorizado_por   uuid        references auth.users(id) on delete set null,
  autorizado_em    timestamptz not null default now(),
  cancelado_por    uuid        references auth.users(id) on delete set null,
  cancelado_em     timestamptz,
  enviado_em       timestamptz,
  url              text        check (url is null or (url ~ '^https?://[!-~]+$' and length(url) <= 500)),
  erro             text        check (length(erro) <= 1000),
  atualizado_em    timestamptz not null default now()
);
create index if not exists radar_site_envios_conteudo_idx on public.radar_site_envios (conteudo_id);
-- uma autorização em aberto por conteúdo
create unique index if not exists radar_site_envios_aberto_uk on public.radar_site_envios (conteudo_id)
  where situacao in ('autorizado','enviando');

-- v0.8.0: o Diário Oficial da União pelo INLABS é um tipo de leitura a mais
alter table public.radar_fontes drop constraint if exists radar_fontes_tipo_coletor_check;
alter table public.radar_fontes add constraint radar_fontes_tipo_coletor_check
  check (tipo_coletor in ('rss','html_links','normas_rfb','inlabs'));
-- (o formato do cadastro de fontes é conferido pelo gatilho radar_fn_fonte_formato, mais abaixo)
alter table public.radar_fontes drop constraint if exists radar_fontes_formato;

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
  -- marcar ou desmarcar "não vai ao site" não é alteração do texto: a data do conteúdo não muda
  if tg_table_name = 'radar_conteudos' and (to_jsonb(new) - 'fora_do_site') = (to_jsonb(old) - 'fora_do_site') then
    new.atualizado_em := old.atualizado_em;
    return new;
  end if;
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
  -- captura incluída pela equipe e depois lida pelo robô: o texto atual passa a ser o do robô,
  -- mas fica guardado que o endereço entrou manualmente (quem, quando e se o texto era igual)
  if coalesce(old.metadados->>'manual', '') = 'true' and coalesce(new.metadados->>'manual', '') <> 'true' then
    new.metadados := new.metadados || jsonb_build_object('origem_manual', jsonb_build_object(
      'por', old.metadados->'incluido_por', 'em', old.metadados->'incluido_em', 'versao', old.versao,
      'texto_igual', new.hash_conteudo is not distinct from old.hash_conteudo));
  elsif old.metadados ? 'origem_manual' and not (new.metadados ? 'origem_manual') then
    new.metadados := new.metadados || jsonb_build_object('origem_manual', old.metadados->'origem_manual');
  end if;
  if new.hash_conteudo is distinct from old.hash_conteudo and old.hash_conteudo is not null then
    insert into public.radar_capturas_versoes (captura_id, versao, titulo, texto, hash_conteudo)
    values (old.id, old.versao, old.titulo, old.texto, old.hash_conteudo)
    on conflict (captura_id, versao) do nothing;
    new.versao := old.versao + 1;
    new.atualizado_em := now();
  end if;
  return new;
end $$;

-- ---------------------------------------------------------------- relevância das capturas (v0.6.0)
-- Texto para comparação de palavras: minúsculas e sem acento ("Prorrogação" = "prorrogacao")
create or replace function public.radar_sem_acento(t text) returns text
language sql immutable set search_path = public as $$
  select translate(lower(coalesce(t, '')), 'áàâãäéèêëíìîïóòôõöúùûüçñ', 'aaaaaeeeeiiiiooooouuuucn');
$$;

-- Pontua um item pelas regras de radar_config.relevancia: {"limite_alta", "limite_media", "termos": [{"termo","pontos"}]}.
-- Cada termo conta uma vez: o dobro dos pontos se está no título; os pontos se está só no resumo ou no começo do texto.
-- Só casa palavra inteira ("MEI" não casa com "meio"). Devolve nível, pontos e os termos que pesaram.
-- v0.7.1: termo que começa ou termina com pontuação ("S.A.", "Ltda.") é aceito; a exigência de palavra inteira
-- vale só no lado que é letra ou número ("S.A." casa com "Petrobras S.A." e "S.A.," mas não com "SS.A.").
create or replace function public.radar_avaliar_relevancia(p_titulo text, p_resumo text, p_texto text)
returns table (nivel text, pontos int, motivos jsonb)
language plpgsql stable security definer set search_path = public as $$
declare
  v_conf   jsonb;
  v_titulo text := public.radar_sem_acento(p_titulo);
  v_corpo  text := public.radar_sem_acento(coalesce(p_resumo, '') || ' ' || left(coalesce(p_texto, ''), 3000));
  v_t      record;
  v_re     text;
  v_pts    int := 0;
  v_mot    jsonb := '[]'::jsonb;
  v_alta   int;
  v_media  int;
  v_norm   text;
begin
  select c.valor into v_conf from public.radar_config c where c.chave = 'relevancia';
  if v_conf is null or jsonb_typeof(v_conf->'termos') is distinct from 'array' then
    return query select 'media'::text, 0, '[]'::jsonb;        -- sem regras: nada é escondido
    return;
  end if;
  -- números absurdos na configuração são contidos aqui: nada do que está nas regras pode travar a coleta
  v_alta  := case when jsonb_typeof(v_conf->'limite_alta')  = 'number' then least(greatest((v_conf->>'limite_alta')::numeric,  -100000), 100000)::int else 8 end;
  v_media := case when jsonb_typeof(v_conf->'limite_media') = 'number' then least(greatest((v_conf->>'limite_media')::numeric, -100000), 100000)::int else 3 end;
  for v_t in
    select btrim(x->>'termo') as termo, least(greatest((x->>'pontos')::numeric, -1000), 1000)::int as pts
    from jsonb_array_elements(v_conf->'termos') x
    where jsonb_typeof(x) = 'object' and jsonb_typeof(x->'pontos') = 'number' and length(btrim(coalesce(x->>'termo', ''))) between 2 and 80
  loop
    v_norm := public.radar_sem_acento(v_t.termo);
    continue when strpos(v_titulo, v_norm) = 0 and strpos(v_corpo, v_norm) = 0;      -- atalho: a maioria dos termos não aparece
    v_re := case when v_norm ~ '^[[:alnum:]]' then '\m' else '' end
         || regexp_replace(v_norm, '([^[:alnum:][:space:]])', '\\\1', 'g')
         || case when v_norm ~ '[[:alnum:]]$' then '\M' else '' end;
    if v_titulo ~ v_re then
      v_pts := v_pts + 2 * v_t.pts;
      v_mot := v_mot || jsonb_build_object('termo', v_t.termo, 'pontos', 2 * v_t.pts);
    elsif v_corpo ~ v_re then
      v_pts := v_pts + v_t.pts;
      v_mot := v_mot || jsonb_build_object('termo', v_t.termo, 'pontos', v_t.pts);
    end if;
  end loop;
  return query select case when v_pts >= v_alta then 'alta' when v_pts >= v_media then 'media' else 'baixa' end, v_pts, v_mot;
exception when others then
  -- qualquer erro no cálculo vira "média": a captura entra e aparece na triagem
  return query select 'media'::text, 0, '[]'::jsonb;
end $$;

-- v0.8.0: nota alta da IA tira a captura de "baixa". A lista de palavras não cobre tudo: notícia importante
-- escrita sem nenhum termo da lista ficava escondida. Com nota da IA a partir de radar_config.relevancia.nota_promove
-- (padrão 8), "baixa" vira "média" e o motivo fica anotado. Nunca passa de "média" (a IA não decide sozinha).
-- Só vale para a captura que ficou baixa por FALTA de palavras: a que tem qualquer termo negativo da lista
-- (apreensão, concurso, leilão...) continua baixa, mesmo com termos positivos — essa exclusão é do escritório.
-- v0.9.0: e o contrário. Captura "alta" pelas palavras da lista (muitas vezes só genéricas: decreto, portaria, prazo...)
-- com nota da IA até radar_config.relevancia.nota_rebaixa (padrão 3; -1 desliga) desce para "média": continua na fila,
-- mas sai do topo.
-- Sem nota da IA (ainda não avaliada), nada muda.
drop function if exists public.radar_relevancia_com_ia(text, jsonb, smallint);
create or replace function public.radar_relevancia_com_ia(p_nivel text, p_pontos int, p_motivos jsonb, p_nota smallint)
returns table (nivel text, motivos jsonb)
language sql stable security definer set search_path = public as $$
  select case when l.promove then 'media' when l.rebaixa then 'media' else p_nivel end,
         case when l.promove
              then coalesce(p_motivos, '[]'::jsonb) || jsonb_build_object('termo', 'nota da IA ' || p_nota, 'pontos', 0)
              when l.rebaixa
              then coalesce(p_motivos, '[]'::jsonb) || jsonb_build_object('termo', 'nota da IA ' || p_nota || ' (rebaixada)', 'pontos', 0)
              else p_motivos end
    from (select p_nivel = 'baixa' and x.sem_negativo and p_nota >= x.limite as promove,
                 p_nivel = 'alta' and p_nota <= x.rebaixa as rebaixa
            from (select coalesce((select case when jsonb_typeof(c.valor->'nota_promove') = 'number'
                                               then least(greatest((c.valor->>'nota_promove')::numeric, 0), 11) end
                                     from public.radar_config c where c.chave = 'relevancia'), 8) as limite,
                         coalesce((select case when jsonb_typeof(c.valor->'nota_rebaixa') = 'number'
                                               then least(greatest((c.valor->>'nota_rebaixa')::numeric, -1), 10) end
                                     from public.radar_config c where c.chave = 'relevancia'), 3) as rebaixa,
                         p_pontos >= 0 and not exists (select 1 from jsonb_array_elements(case when jsonb_typeof(p_motivos) = 'array'
                                                                                         then p_motivos else '[]'::jsonb end) m
                                                       where jsonb_typeof(m->'pontos') = 'number' and (m->>'pontos')::numeric < 0) as sem_negativo) x) l;
$$;

-- v0.11.0: notícia com mais de radar_config.relevancia.dias_baixa dias (padrão 5; 0 desliga) vira "baixa" — conta a data da
-- notícia (ou, sem ela, a da captura), no dia de Brasília. O motivo fica anotado com "idade": true, e a limpeza da fila
-- (radar_arquivar_fila) não arquiva por esse motivo: a notícia velha mas relevante continua em "Baixa relevância".
create or replace function public.radar_relevancia_idade(p_nivel text, p_motivos jsonb, p_data date, p_capturado timestamptz)
returns table (nivel text, motivos jsonb)
language sql stable security definer set search_path = public as $$
  select case when x.velha then 'baixa' else p_nivel end,
         case when x.velha
              then coalesce(p_motivos, '[]'::jsonb) || jsonb_build_object('termo', 'notícia com mais de ' || x.dias || ' dias', 'pontos', 0, 'idade', true, 'antes', p_nivel)
              else p_motivos end
    from (select d.dias, d.dias > 0 and p_nivel is distinct from 'baixa'
                 and coalesce(p_data, (coalesce(p_capturado, now()) at time zone 'America/Sao_Paulo')::date)
                     < (now() at time zone 'America/Sao_Paulo')::date - d.dias as velha
            from (select coalesce((select case when jsonb_typeof(c.valor->'dias_baixa') = 'number'
                                               then least(greatest((c.valor->>'dias_baixa')::numeric, 0), 365)::int end
                                     from public.radar_config c where c.chave = 'relevancia'), 5) as dias) d) x;
$$;

create or replace function public.radar_fn_captura_relevancia() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if tg_op = 'UPDATE' and new.titulo is distinct from old.titulo then
    new.ia_avaliado_em := null;          -- v0.7.0: título mudou, o robô pede a nota da IA de novo na próxima coleta
  end if;
  if coalesce(current_setting('radar.reavaliando', true), '') = '1' then
    return new;                          -- reavaliação geral em curso (radar_reavaliar_capturas)
  end if;
  if tg_op = 'UPDATE' and new.titulo is not distinct from old.titulo and new.resumo_fonte is not distinct from old.resumo_fonte
     and new.texto is not distinct from old.texto and new.ia_nota is not distinct from old.ia_nota
     and new.data_publicacao is not distinct from old.data_publicacao then
    new.relevancia := old.relevancia; new.relevancia_pontos := old.relevancia_pontos; new.relevancia_motivos := old.relevancia_motivos;
    return new;                          -- ninguém marca relevância à mão: só muda quando o item, a nota da IA ou as regras mudam
  end if;
  select r.nivel, r.pontos, r.motivos into new.relevancia, new.relevancia_pontos, new.relevancia_motivos
    from public.radar_avaliar_relevancia(new.titulo, new.resumo_fonte, new.texto) r;
  select x.nivel, x.motivos into new.relevancia, new.relevancia_motivos
    from public.radar_relevancia_com_ia(new.relevancia, new.relevancia_pontos, new.relevancia_motivos, new.ia_nota) x;
  if tg_op = 'INSERT' or not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = new.id) then
    select y.nivel, y.motivos into new.relevancia, new.relevancia_motivos      -- a que já virou assunto não envelhece
      from public.radar_relevancia_idade(new.relevancia, new.relevancia_motivos, new.data_publicacao, new.capturado_em) y;
  end if;
  return new;
end $$;

-- Regras alteradas em Configurações: as capturas que ainda estão na fila de triagem são reavaliadas na hora
-- (as que já viraram assunto não voltam para a fila; reavaliá-las só gastaria tempo)
create or replace function public.radar_reavaliar_capturas() returns int
language plpgsql security definer set search_path = public as $$
declare v_n int;
begin
  perform set_config('radar.reavaliando', '1', true);        -- só nesta transação: deixa o gatilho aceitar o valor recalculado
  update public.radar_capturas c
     set relevancia = y.nivel, relevancia_pontos = r.pontos, relevancia_motivos = y.motivos
    from public.radar_capturas k cross join lateral public.radar_avaliar_relevancia(k.titulo, k.resumo_fonte, k.texto) r
         cross join lateral public.radar_relevancia_com_ia(r.nivel, r.pontos, r.motivos, k.ia_nota) x
         cross join lateral public.radar_relevancia_idade(x.nivel, x.motivos, k.data_publicacao, k.capturado_em) y
   where k.id = c.id
     and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = k.id)
     and (c.relevancia, c.relevancia_pontos, c.relevancia_motivos) is distinct from (y.nivel, r.pontos, y.motivos);
  get diagnostics v_n = row_count;
  perform set_config('radar.reavaliando', '', true);
  return v_n;
end $$;

create or replace function public.radar_fn_config_relevancia() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if coalesce(new.chave, old.chave) = 'relevancia' then
    perform public.radar_reavaliar_capturas();
  end if;
  return null;
end $$;

-- Imagem trocada ou conteúdo apagado: a imagem que ninguém mais usa é removida (v0.6.0 — todo conteúdo nasce com capa,
-- e cada capa refeita deixaria uma imagem sem uso no banco)
create or replace function public.radar_fn_imagem_sem_uso() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if old.imagem_id is not null and (tg_op = 'DELETE' or new.imagem_id is distinct from old.imagem_id) then
    delete from public.radar_imagens i
     where i.id = old.imagem_id
       and not exists (select 1 from public.radar_conteudos c where c.imagem_id = i.id);
  end if;
  return null;
end $$;
drop trigger if exists radar_tg_imagem_sem_uso on public.radar_conteudos;
create trigger radar_tg_imagem_sem_uso after update of imagem_id or delete on public.radar_conteudos
  for each row execute function public.radar_fn_imagem_sem_uso();

-- v0.7.1: imagem que ficou sem uso por outro caminho (envio que falhou entre gravar a imagem e ligá-la ao conteúdo,
-- capas trocadas antes da v0.6.0) é apagada pelo robô ao fim de cada coleta. Só as com mais de p_horas (padrão 24):
-- uma imagem acabada de enviar, que a tela ainda vai ligar ao conteúdo, não é tocada. Devolve quantas apagou.
create or replace function public.radar_limpar_imagens_sem_uso(p_horas int default 24) returns int
language plpgsql security definer set search_path = public as $$
declare v_n int;
begin
  delete from public.radar_imagens i
   where i.criado_em < now() - make_interval(hours => least(greatest(coalesce(p_horas, 24), 1), 8760))
     and not exists (select 1 from public.radar_conteudos c where c.imagem_id = i.id);
  get diagnostics v_n = row_count;
  return v_n;
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
    -- v0.11.0: o texto para análise (escrito pela IA a partir de fonte não oficial) é só para estudo: não se aprova
    if coalesce(new.avisos_ia->>0, '') like 'TEXTO PARA ANÁLISE%' then
      raise exception 'RADAR023: texto para análise (escrito a partir de fonte não oficial) não pode ser aprovado; inclua o texto oficial e gere ou escreva um conteúdo novo'
        using errcode = 'P0001';
    end if;
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

-- Cadastro de fontes pela tela: formato mínimo. Só é conferido quando o cadastro muda — a atualização
-- de saúde feita pelo robô a cada execução nunca é barrada por causa de um cadastro antigo.
create or replace function public.radar_fn_fonte_formato() returns trigger
language plpgsql set search_path = public as $$
begin
  if tg_op = 'UPDATE' and new.url = old.url and new.nome = old.nome and new.orgao = old.orgao
     and new.slug = old.slug and new.config = old.config then
    return new;
  end if;
  if new.url !~ '^https?://[!-~]+$' or length(new.url) > 1000 then
    raise exception 'RADAR090: o endereço da fonte precisa ser completo, começando com https:// e sem espaços' using errcode = '23514';
  end if;
  if jsonb_typeof(new.config) is distinct from 'object' or length(new.config::text) > 20000 then
    raise exception 'RADAR091: as opções de leitura da fonte precisam ser um objeto JSON de tamanho razoável' using errcode = '23514';
  end if;
  if length(btrim(new.nome)) not between 3 and 200 or length(btrim(new.orgao)) not between 2 and 200 then
    raise exception 'RADAR092: informe o nome (3 a 200 caracteres) e o órgão (2 a 200) da fonte' using errcode = '23514';
  end if;
  if new.slug !~ '^[a-z0-9]+(-[a-z0-9]+)*$' or length(new.slug) > 80 then
    raise exception 'RADAR093: identificador da fonte inválido' using errcode = '23514';
  end if;
  return new;
end $$;

-- Endereço em forma única para comparar: sem âncora, sem parâmetros de rastreio e sem barra no fim
create or replace function public.radar_url_base(p_url text) returns text
language sql immutable set search_path = public as $$
  select regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(btrim(coalesce(p_url, '')),
           '#.*$', ''), '([?&])(utm_[a-z_]+|fbclid|gclid)=[^&]*', '\1', 'gi'), '([?&])&+', '\1', 'g'), '[?&]+$', ''), '(.)/+$', '\1');
$$;

-- Fotografia das evidências conferidas em fonte oficial de um assunto (o que fundamenta a divulgação)
create or replace function public.radar_fundamentacao(p_assunto bigint) returns jsonb
language sql stable security definer set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
           'orgao', f.orgao, 'fonte', f.nome, 'titulo', c.titulo, 'url', c.url,
           'data', c.data_publicacao, 'dispositivo', e.dispositivo, 'trecho', e.trecho_literal,
           'natureza', e.natureza, 'manual', coalesce(c.metadados->>'manual', '') = 'true',
           'norma', case when n.id is not null then n.tipo || ' nº ' || n.numero || ' — ' || n.orgao end,
           'norma_url', n.url_oficial) order by e.id), '[]'::jsonb)
  from public.radar_evidencias e
  join public.radar_capturas c on c.id = e.captura_id
  join public.radar_fontes   f on f.id = c.fonte_id
  left join public.radar_normas n on n.id = e.norma_id
  where e.assunto_id = p_assunto and e.trecho_conferido and f.oficial;
$$;

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

-- Registro de publicação no site. Mesmas exigências da antiga publicação: conteúdo aprovado, assunto
-- confirmado oficialmente e ao menos um trecho conferido em fonte oficial. Guarda a cópia do texto e
-- da fundamentação; o que saiu não se reescreve.
create or replace function public.radar_fn_divulgacao() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_c public.radar_conteudos%rowtype;
  v_pendencia text;
begin
  if auth.uid() is not null and coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'permission denied for table radar_divulgacoes' using errcode = '42501';
  end if;
  if tg_op = 'INSERT' then
    select * into v_c from public.radar_conteudos c where c.id = new.conteudo_id;
    if v_c.status is distinct from 'aprovado' then
      raise exception 'RADAR070: só conteúdo aprovado pode ser registrado como publicado no site' using errcode = 'P0001';
    end if;
    -- a cópia guardada tem de ser do texto que a pessoa viu (e copiou para o site), não de uma versão mais nova
    if new.conteudo_lido_em is not null and new.conteudo_lido_em <> v_c.atualizado_em then
      raise exception 'RADAR071: o conteúdo foi alterado depois que esta tela foi aberta; recarregue, confira o texto e registre de novo'
        using errcode = 'P0001';
    end if;
    new.conteudo_lido_em := v_c.atualizado_em;
    v_pendencia := public.radar_pendencia_assunto(v_c.assunto_id);
    if v_pendencia is not null then
      raise exception '%', v_pendencia using errcode = 'P0001';
    end if;
    new.fundamentacao := public.radar_fundamentacao(v_c.assunto_id);
    new.titulo         := v_c.titulo;
    new.corpo          := v_c.corpo;
    new.registrado_por := auth.uid();
    new.registrado_em  := now();
    if new.publicado_em < date '2000-01-01' or new.publicado_em > current_date + 1 then
      raise exception 'RADAR072: a data da publicação no site não pode estar no futuro' using errcode = 'P0001';
    end if;
    return new;
  end if;
  -- depois de registrado, só o link, a data e a observação podem ser corrigidos
  new.conteudo_id    := old.conteudo_id;
  new.titulo         := old.titulo;
  new.corpo          := old.corpo;
  new.registrado_por := public.radar_manter_usuario(old.registrado_por, new.registrado_por);
  new.registrado_em  := old.registrado_em;
  new.conteudo_lido_em := old.conteudo_lido_em;
  new.fundamentacao    := old.fundamentacao;
  if new.publicado_em < date '2000-01-01' or new.publicado_em > current_date + 1 then
    raise exception 'RADAR072: a data da publicação no site não pode estar no futuro' using errcode = 'P0001';
  end if;
  return new;
end $$;

-- v0.10.0: o administrador autoriza a publicação no site. Valem as mesmas exigências do registro (conteúdo aprovado,
-- assunto confirmado oficialmente, trecho conferido em fonte oficial) e o texto tem de ser o que estava na tela.
create or replace function public.radar_autorizar_site(p_conteudo bigint, p_categoria text, p_lido timestamptz)
returns bigint language plpgsql security definer set search_path = public as $$
declare
  v_c public.radar_conteudos%rowtype;
  v_pendencia text;
  v_id bigint;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR110: só o administrador autoriza a publicação no site' using errcode = '42501';
  end if;
  select * into v_c from public.radar_conteudos c where c.id = p_conteudo for update;
  if v_c.id is null then
    raise exception 'RADAR111: conteúdo não encontrado' using errcode = 'P0001';
  end if;
  if v_c.status is distinct from 'aprovado' then
    raise exception 'RADAR112: só conteúdo aprovado pode ser publicado no site' using errcode = 'P0001';
  end if;
  if coalesce(v_c.avisos_ia->>0, '') like 'TEXTO PARA ANÁLISE%' then
    raise exception 'RADAR119: texto para análise não vai ao site' using errcode = 'P0001';
  end if;
  if v_c.fora_do_site then
    raise exception 'RADAR113: este conteúdo está marcado como "não vai ao site"' using errcode = 'P0001';
  end if;
  if p_lido is distinct from v_c.atualizado_em then
    raise exception 'RADAR114: o conteúdo foi alterado depois que esta tela foi aberta; recarregue, confira e autorize de novo' using errcode = 'P0001';
  end if;
  if length(btrim(coalesce(p_categoria, ''))) not between 2 and 80 then
    raise exception 'RADAR115: escolha a categoria do site' using errcode = 'P0001';
  end if;
  v_pendencia := public.radar_pendencia_assunto(v_c.assunto_id);
  if v_pendencia is not null then
    raise exception '%', v_pendencia using errcode = 'P0001';
  end if;
  if exists (select 1 from public.radar_site_envios e where e.conteudo_id = p_conteudo and e.situacao in ('autorizado','enviando')) then
    raise exception 'RADAR116: a publicação deste conteúdo já está autorizada e aguardando o robô' using errcode = 'P0001';
  end if;
  if exists (select 1 from public.radar_divulgacoes d where d.conteudo_id = p_conteudo)
     or exists (select 1 from public.radar_site_envios e where e.conteudo_id = p_conteudo and e.situacao = 'publicado') then
    raise exception 'RADAR117: este conteúdo já tem publicação registrada no site; para mudar a notícia, altere no painel do site' using errcode = 'P0001';
  end if;
  insert into public.radar_site_envios (conteudo_id, categoria, conteudo_lido_em, autorizado_por)
  values (p_conteudo, btrim(p_categoria), v_c.atualizado_em, auth.uid())
  returning id into v_id;
  return v_id;
end $$;

-- Cancelar a autorização enquanto o robô ainda não começou a enviar.
create or replace function public.radar_cancelar_site(p_envio bigint) returns boolean
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR110: só o administrador mexe na autorização de publicação' using errcode = '42501';
  end if;
  update public.radar_site_envios
     set situacao = 'cancelado', cancelado_por = auth.uid(), cancelado_em = now(), atualizado_em = now()
   where id = p_envio and situacao = 'autorizado';
  if not found then
    raise exception 'RADAR118: não dá mais para cancelar: o robô já começou a publicar (ou a autorização não existe)' using errcode = 'P0001';
  end if;
  return true;
end $$;

-- Conteúdo alterado depois de autorizado (e antes de o robô começar): a autorização cai — o que vai ao ar é só o que foi visto.
create or replace function public.radar_fn_conteudo_envio() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.titulo is distinct from old.titulo or new.corpo is distinct from old.corpo or new.status is distinct from old.status
     or new.imagem_id is distinct from old.imagem_id or new.autor is distinct from old.autor
     or new.fonte_credito is distinct from old.fonte_credito or new.fora_do_site is distinct from old.fora_do_site then
    update public.radar_site_envios
       set situacao = 'cancelado', cancelado_em = now(), atualizado_em = now(),
           erro = 'Autorização cancelada sozinha: o conteúdo mudou depois de autorizado. Confira e autorize de novo.'
     where conteudo_id = new.id and situacao = 'autorizado';
  end if;
  return null;
end $$;

-- v0.11.0: só as capturas da fila que passaram agora de dias_baixa dias (e ainda não estão baixas) descem para "baixa";
-- não recalcula a fila inteira a cada coleta. Devolve quantas desceram.
create or replace function public.radar_envelhecer_fila() returns int
language plpgsql security definer set search_path = public as $$
declare v_n int;
begin
  perform set_config('radar.reavaliando', '1', true);
  update public.radar_capturas c
     set relevancia = y.nivel, relevancia_motivos = y.motivos
    from public.radar_capturas k
         cross join lateral public.radar_relevancia_idade(k.relevancia, k.relevancia_motivos, k.data_publicacao, k.capturado_em) y
   where k.id = c.id and k.relevancia <> 'baixa' and y.nivel = 'baixa'
     and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = k.id);
  get diagnostics v_n = row_count;
  perform set_config('radar.reavaliando', '', true);
  return v_n;
end $$;

-- v0.9.0: a fila não acumula. Ao fim de cada coleta, o robô tira da triagem (como "Ignorado", em Assuntos) o que
-- está na fila há mais de radar_config.relevancia.arquivar_dias (padrão 10; 0 desliga) e é de relevância baixa ou
-- tem nota da IA até arquivar_nota (padrão 2). Vale o mesmo caminho do "Ignorar" (as repetições vão junto).
-- No máximo p_limite por vez. Devolve quantas capturas saíram da fila.
create or replace function public.radar_arquivar_fila(p_limite int default 500) returns int
language plpgsql security definer set search_path = public as $$
declare
  v_conf jsonb := coalesce((select c.valor from public.radar_config c where c.chave = 'relevancia'), '{}'::jsonb);
  v_dias int := case when jsonb_typeof(v_conf->'arquivar_dias') = 'number'
                     then least(greatest((v_conf->>'arquivar_dias')::numeric, 0), 365)::int else 10 end;
  v_nota int := case when jsonb_typeof(v_conf->'arquivar_nota') = 'number'
                     then least(greatest((v_conf->>'arquivar_nota')::numeric, -1), 10)::int else 2 end;
  v_antes int;
  v_id bigint;
begin
  perform public.radar_envelhecer_fila();               -- v0.11.0: a notícia que passou de dias_baixa dias desce para "baixa"
  if v_dias = 0 then
    return 0;
  end if;
  select count(*) into v_antes from public.radar_v_fila;
  for v_id in select f.id from public.radar_v_fila f
               where f.principal and f.capturado_em < now() - make_interval(days => v_dias)
                 and (f.nota_grupo <= v_nota                       -- nota do grupo: a maior entre a captura e as repetições
                      or (f.relevancia = 'baixa'                   -- baixa, desde que nenhuma repetição na fila seja relevante
                          -- baixa só pela idade sai depois de 3 vezes o prazo (v0.11.0): relevante, mas velha demais
                          and (not (f.relevancia_motivos @> '[{"idade": true}]') or f.capturado_em < now() - make_interval(days => v_dias * 3))
                          and not exists (select 1 from public.radar_capturas r
                                           where r.duplicata_de = f.id and r.relevancia <> 'baixa'
                                             and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = r.id))))
               order by f.capturado_em
               limit least(greatest(coalesce(p_limite, 500), 1), 500) loop
    if not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = v_id) then
      perform public.radar_abrir_assunto(v_id, true);
    end if;
  end loop;
  return v_antes - (select count(*) from public.radar_v_fila);
end $$;

create or replace function public.radar_fn_divulgacao_efeitos() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_assunto bigint;
begin
  select c.assunto_id into v_assunto from public.radar_conteudos c
   where c.id = case when tg_op = 'DELETE' then old.conteudo_id else new.conteudo_id end;
  perform 1 from public.radar_assuntos a where a.id = v_assunto for update;      -- um registro por vez em cada assunto
  if tg_op = 'INSERT' then    -- assunto ignorado ou arquivado continua como está
    update public.radar_assuntos set status = 'publicado' where id = v_assunto and status not in ('publicado','ignorado','arquivado');
  else   -- registro excluído: se nada mais do assunto foi publicado, ele volta a aparecer como "em andamento"
    update public.radar_assuntos a set status = 'aprovado'
     where a.id = v_assunto and a.status = 'publicado'
       and not exists (select 1 from public.radar_divulgacoes d join public.radar_conteudos c on c.id = d.conteudo_id
                       where c.assunto_id = v_assunto);
  end if;
  return null;
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
  insert into public.radar_assuntos (titulo, categoria, abrangencia, status, resumo, relevancia)
  select c.titulo, f.categoria_padrao, f.abrangencia,
         case when p_ignorar then 'ignorado' else 'capturado' end, c.resumo_fonte,
         -- v0.11.0: a idade só ordena a triagem; o assunto guarda a importância do conteúdo
         coalesce((select m->>'antes' from jsonb_array_elements(case when jsonb_typeof(c.relevancia_motivos) = 'array'
                                                                     then c.relevancia_motivos else '[]'::jsonb end) m
                    where m->>'idade' = 'true' and m->>'antes' in ('alta','media') limit 1), c.relevancia)
  from public.radar_capturas c join public.radar_fontes f on f.id = c.fonte_id
  where c.id = p_captura
  returning id into v_id;
  if v_id is null then
    raise exception 'RADAR041: captura não encontrada' using errcode = 'P0001';
  end if;
  insert into public.radar_assunto_capturas (assunto_id, captura_id) values (v_id, p_captura);
  -- v0.7.0: vão junto, para o MESMO assunto, só as capturas que a tela mostra recolhidas atrás desta:
  --   * sempre: as repetições que apontam para ela ("Mesmo fato em mais N capturas");
  --   * ao ABRIR pela repetição recolhida (origem ainda na fila): a origem e as demais repetições dela.
  -- IGNORAR uma repetição recolhida ignora só ela; e a captura cuja origem já está em outro assunto
  -- tem cartão próprio na triagem — as irmãs dela não são levadas sem alguém decidir.
  insert into public.radar_assunto_capturas (assunto_id, captura_id, juntada_pela_ia_em)
  select v_id, c.id, now()
    from public.radar_capturas c
    left join (select k.duplicata_de as raiz from public.radar_capturas k
                where k.id = p_captura and k.duplicata_de is not null and not coalesce(p_ignorar, false)
                  and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = k.duplicata_de)) r on true
   where (c.duplicata_de = p_captura or c.id = r.raiz or c.duplicata_de = r.raiz) and c.id <> p_captura
     and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = c.id)
  on conflict do nothing;
  return v_id;
end $$;

-- Avaliação da IA gravada pelo robô (v0.7.0). Cada item: {"id", "nota" 0..10, "motivo", "tema", "igual_a"}.
-- "igual_a" é o id de outra captura que trata do MESMO fato: a captura vira repetição dela (duplicata_de) e,
-- se a original já virou assunto (ou foi ignorada), a repetição entra no mesmo assunto e não volta à triagem.
-- Só o robô (service_role) executa. Itens inválidos são pulados, nunca derrubam o lote.
-- security definer: precisa escrever na auditoria (que o robô só lê). Quem pode chamar é só o service_role (grant abaixo).
-- v0.11.1: fonte NÃO oficial (boletim, portal, editora) nunca é a "origem" de uma captura oficial. Se o mesmo fato
-- chegou antes por um boletim, a captura oficial fica como principal e o boletim passa a ser a repetição dela.
create or replace function public.radar_fn_captura_origem() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  -- boletim que chega depois da publicação oficial do mesmo fato (mesmo título): entra como repetição dela
  if tg_op = 'INSERT' and new.duplicata_de is null
     and not coalesce((select f.oficial from public.radar_fontes f where f.id = new.fonte_id), false) then
    select c.id into new.duplicata_de
      from public.radar_capturas c join public.radar_fontes f on f.id = c.fonte_id
     where f.oficial and c.duplicata_de is null and c.hash_titulo = new.hash_titulo and c.fonte_id <> new.fonte_id
     order by c.id limit 1;
  end if;
  -- (se o boletim já virou assunto, o vínculo fica: a oficial entra nesse assunto ou mostra o aviso "parece o mesmo fato")
  if new.duplicata_de is not null
     and (select f.oficial from public.radar_fontes f where f.id = new.fonte_id)
     and not coalesce((select f.oficial from public.radar_capturas c join public.radar_fontes f on f.id = c.fonte_id
                        where c.id = new.duplicata_de), false)
     and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = new.duplicata_de) then
    new.duplicata_de := null;
  end if;
  return new;
end $$;

-- Põe a captura não oficial p_outra (e as repetições dela) atrás da oficial p_oficial. Não mexe no que já virou assunto.
create or replace function public.radar_promover_oficial(p_oficial bigint, p_outra bigint) returns int
language plpgsql security definer set search_path = public as $$
declare v_n int;
begin
  if p_oficial is null or p_outra is null or p_oficial = p_outra
     or not exists (select 1 from public.radar_capturas c join public.radar_fontes f on f.id = c.fonte_id
                     where c.id = p_oficial and f.oficial and c.duplicata_de is null)
     or not exists (select 1 from public.radar_capturas c join public.radar_fontes f on f.id = c.fonte_id
                     where c.id = p_outra and not f.oficial and c.duplicata_de is null
                       and c.metadados->'separada_em' is null) then   -- a equipe disse que não é o mesmo fato
    return 0;
  end if;
  update public.radar_capturas c set duplicata_de = p_oficial
   where (c.id = p_outra or c.duplicata_de = p_outra) and c.id <> p_oficial
     and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = c.id)
     and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = p_outra);
  get diagnostics v_n = row_count;
  return v_n;
end $$;

-- Captura oficial nova: o boletim que trouxe o mesmo fato antes (mesmo título ou mesmo texto) vai para trás dela.
create or replace function public.radar_fn_captura_promover() returns trigger
language plpgsql security definer set search_path = public as $$
declare v_outra bigint;
begin
  if new.duplicata_de is null and (select f.oficial from public.radar_fontes f where f.id = new.fonte_id) then
    for v_outra in select c.id from public.radar_capturas c join public.radar_fontes f on f.id = c.fonte_id
                    where c.duplicata_de is null and c.id <> new.id and not f.oficial
                      and (c.hash_titulo = new.hash_titulo or (new.hash_conteudo is not null and c.hash_conteudo = new.hash_conteudo)) loop
      perform public.radar_promover_oficial(new.id, v_outra);
    end loop;
  end if;
  return null;
end $$;

create or replace function public.radar_gravar_avaliacao_ia(p_itens jsonb)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  v_item jsonb; v_id bigint; v_raiz bigint; v_prox bigint; v_assunto bigint; v_n int;
  v_gravadas int := 0; v_repetidas int := 0; v_juntadas int := 0; v_puladas int := 0;
begin
  if jsonb_typeof(p_itens) is distinct from 'array' then
    raise exception 'RADAR044: a avaliação precisa ser uma lista' using errcode = 'P0001';
  end if;
  if jsonb_array_length(p_itens) > 200 then
    raise exception 'RADAR044: no máximo 200 avaliações por vez' using errcode = 'P0001';
  end if;
  for v_item in select * from jsonb_array_elements(p_itens) loop
    begin
      if jsonb_typeof(v_item) is distinct from 'object' or jsonb_typeof(v_item->'id') is distinct from 'number'
         or jsonb_typeof(v_item->'nota') is distinct from 'number' then
        v_puladas := v_puladas + 1; continue;
      end if;
      v_id := (v_item->>'id')::numeric::bigint;
      if not exists (select 1 from public.radar_capturas c where c.id = v_id) then
        v_puladas := v_puladas + 1; continue;
      end if;
      -- origem da repetição: sobe até a captura que não é repetição de ninguém (no máximo 5 passos, sem voltar a si mesma)
      v_raiz := null;
      if jsonb_typeof(v_item->'igual_a') = 'number' then
        v_raiz := (v_item->>'igual_a')::numeric::bigint;
        for v_n in 1..5 loop
          select c.duplicata_de into v_prox from public.radar_capturas c where c.id = v_raiz;
          if not found then v_raiz := null; exit; end if;
          exit when v_prox is null;
          v_raiz := v_prox;
        end loop;
        if v_raiz = v_id or exists (select 1 from public.radar_capturas c where c.duplicata_de = v_id) then
          v_raiz := null;                      -- não aponta para si mesma nem vira repetição quem já é origem de outras
        end if;
        -- v0.11.1: captura oficial igual a um boletim não oficial: o boletim é que vira a repetição
        if v_raiz is not null and exists (select 1 from public.radar_capturas c join public.radar_fontes f on f.id = c.fonte_id where c.id = v_id and f.oficial)
           and not exists (select 1 from public.radar_capturas c join public.radar_fontes f on f.id = c.fonte_id where c.id = v_raiz and f.oficial) then
          if public.radar_promover_oficial(v_id, v_raiz) > 0 then
            v_raiz := null;                    -- (boletim que já é assunto: a oficial segue para o assunto, como antes)
          end if;
        end if;
      end if;
      update public.radar_capturas c
         set ia_nota = least(greatest(round((v_item->>'nota')::numeric), 0), 10)::smallint,
             ia_motivo = nullif(left(btrim(coalesce(v_item->>'motivo', '')), 200), ''),
             ia_tema = nullif(left(btrim(coalesce(v_item->>'tema', '')), 80), ''),
             ia_avaliado_em = now(),
             duplicata_de = coalesce(v_raiz, c.duplicata_de)
       where c.id = v_id;
      v_gravadas := v_gravadas + 1;
      if v_raiz is not null then
        v_repetidas := v_repetidas + 1;
        -- só entra sozinha em assunto EM ANDAMENTO. Se a origem foi ignorada, publicada ou arquivada, a repetição
        -- fica na triagem, com o aviso de que parece o mesmo fato: a IA pode errar e nada some sem alguém ver.
        -- (procura no grupo todo: a origem pode ter sido ignorada e outra repetição dela ter virado assunto)
        select ac.assunto_id into v_assunto
          from public.radar_assunto_capturas ac join public.radar_assuntos a on a.id = ac.assunto_id
          join public.radar_capturas g on g.id = ac.captura_id
         where (g.id = v_raiz or g.duplicata_de = v_raiz) and g.id <> v_id
           and a.status not in ('ignorado','publicado','arquivado')
         order by ac.assunto_id limit 1;
        if v_assunto is not null and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = v_id) then
          insert into public.radar_assunto_capturas (assunto_id, captura_id, juntada_pela_ia_em) values (v_assunto, v_id, now()) on conflict do nothing;
          insert into public.radar_auditoria (tabela, registro_id, acao, usuario, depois)
          values ('radar_assunto_capturas', v_assunto || ':' || v_id, 'INSERT', null,
                  jsonb_build_object('assunto_id', v_assunto, 'captura_id', v_id, 'repeticao_de', v_raiz, 'juntada_pela_ia', true));
          v_juntadas := v_juntadas + 1;
        end if;
      end if;
    exception when others then
      v_puladas := v_puladas + 1;              -- número fora de faixa, etc.: pula o item e segue
    end;
  end loop;
  return jsonb_build_object('gravadas', v_gravadas, 'repetidas', v_repetidas, 'juntadas_a_assunto', v_juntadas, 'puladas', v_puladas);
end $$;

-- "Não é o mesmo fato" (v0.7.0): desfaz a junção de uma captura que entrou no assunto como repetição apontada pela IA.
-- A captura volta para a triagem como item próprio. Só editor/admin; só para vínculo marcado como juntado pela IA
-- e sem evidência registrada nessa captura (a fundamentação nunca é desfeita por aqui).
create or replace function public.radar_separar_captura(p_assunto bigint, p_captura bigint)
returns void language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'permission denied for function radar_separar_captura' using errcode = '42501';
  end if;
  if not exists (select 1 from public.radar_assunto_capturas ac
                  where ac.assunto_id = p_assunto and ac.captura_id = p_captura and ac.juntada_pela_ia_em is not null) then
    raise exception 'RADAR045: esta captura não foi juntada ao assunto como repetição' using errcode = 'P0001';
  end if;
  if exists (select 1 from public.radar_evidencias e where e.assunto_id = p_assunto and e.captura_id = p_captura) then
    raise exception 'RADAR046: há evidência registrada nesta captura; ela continua no assunto' using errcode = 'P0001';
  end if;
  if (select count(*) from public.radar_assunto_capturas ac where ac.assunto_id = p_assunto) < 2 then
    raise exception 'RADAR047: o assunto ficaria sem nenhuma captura' using errcode = 'P0001';
  end if;
  delete from public.radar_assunto_capturas ac where ac.assunto_id = p_assunto and ac.captura_id = p_captura;
  update public.radar_capturas set duplicata_de = null,
         metadados = coalesce(metadados, '{}'::jsonb) || jsonb_build_object('separada_em', now())   -- v0.11.1: não volta a ser agrupada sozinha
   where id = p_captura;
  -- se era a origem do grupo, as demais deixam de apontar para ela
  update public.radar_capturas set duplicata_de = null where duplicata_de = p_captura;
  insert into public.radar_auditoria (tabela, registro_id, acao, usuario, antes)
  values ('radar_assunto_capturas', p_assunto || ':' || p_captura, 'DELETE', auth.uid(),
          jsonb_build_object('assunto_id', p_assunto, 'captura_id', p_captura, 'motivo', 'não é o mesmo fato'));
end $$;

-- Fonte do conteúdo já preenchida (v0.7.0): ao criar um conteúdo sem "Fonte", entra o órgão das capturas
-- de fonte oficial do assunto (ex.: "Receita Federal do Brasil"). A equipe pode trocar ou apagar depois.
create or replace function public.radar_fn_conteudo_fonte() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.fonte_credito is null or btrim(new.fonte_credito) = '' then
    select left(string_agg(o.orgao, ', ' order by o.orgao), 300) into new.fonte_credito
      from (select distinct f.orgao
              from public.radar_assunto_capturas ac
              join public.radar_capturas c on c.id = ac.captura_id
              join public.radar_fontes f on f.id = c.fonte_id
             where ac.assunto_id = new.assunto_id and f.oficial) o;
  end if;
  return new;
end $$;

-- Ignorar várias capturas de uma vez (v0.6.0): a triagem das de baixa relevância não precisa ser uma a uma.
-- Vale o mesmo caminho do "Ignorar" individual (as regras e a auditoria são as mesmas). No máximo 500 por chamada.
create or replace function public.radar_ignorar_capturas(p_capturas bigint[])
returns integer language plpgsql set search_path = public as $$
declare
  v_id bigint;
  v_n  integer := 0;
begin
  if coalesce(array_length(p_capturas, 1), 0) > 500 then
    raise exception 'RADAR043: no máximo 500 capturas por vez' using errcode = 'P0001';
  end if;
  select count(*) into v_n from public.radar_v_fila;
  for v_id in select distinct x from unnest(coalesce(p_capturas, '{}'::bigint[])) x
              where x is not null
              order by x loop
    -- a repetição de uma captura já ignorada neste mesmo lote entrou junto: não vira outro assunto
    if not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = v_id) then
      perform public.radar_abrir_assunto(v_id, true);
    end if;
  end loop;
  return v_n - (select count(*) from public.radar_v_fila);      -- quantas saíram da triagem, repetições incluídas
end $$;

-- Texto oficial incluído pela equipe (colado da fonte), para quando o robô ainda não capturou aquele
-- endereço. A captura fica marcada como "manual", com quem incluiu, e a inclusão entra na auditoria.
-- Se o endereço já foi capturado COM texto, o texto existente NÃO é substituído: só é vinculado.
-- Se foi capturado sem texto (o robô não conseguiu ler), o texto colado entra, marcado como manual.
create or replace function public.radar_incluir_texto_oficial(p_assunto bigint, p_fonte bigint, p_url text,
                                                              p_titulo text, p_data date, p_texto text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  v_id     bigint;
  v_url    text := btrim(coalesce(p_url, ''));
  v_titulo text := btrim(coalesce(p_titulo, ''));
  v_texto  text := btrim(coalesce(p_texto, ''));
  v_dom_fonte text;
  v_dom_url   text;
  v_dominios  jsonb;
  v_tem_texto boolean;
  v_nova      boolean := false;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'permission denied for function radar_incluir_texto_oficial' using errcode = '42501';
  end if;
  if not exists (select 1 from public.radar_assuntos a where a.id = p_assunto) then
    raise exception 'RADAR080: assunto não encontrado' using errcode = 'P0001';
  end if;
  if not exists (select 1 from public.radar_fontes f where f.id = p_fonte) then
    raise exception 'RADAR081: escolha uma fonte cadastrada (aba Fontes)' using errcode = 'P0001';
  end if;
  if v_url !~ '^https?://[!-~]+$' or v_url ~ '[<>"''`]' or length(v_url) > 1000 then
    raise exception 'RADAR082: informe o endereço completo da página oficial, começando com https://' using errcode = 'P0001';
  end if;
  if length(v_titulo) not between 5 and 300 then
    raise exception 'RADAR083: informe o título do ato ou da notícia (5 a 300 caracteres)' using errcode = 'P0001';
  end if;
  if length(v_texto) < 50 then
    raise exception 'RADAR084: cole o texto oficial (no mínimo 50 caracteres)' using errcode = 'P0001';
  end if;
  if length(v_texto) > 500000 then
    raise exception 'RADAR084: o texto colado é grande demais (máximo de 500 mil caracteres); cole só o ato ou a notícia' using errcode = 'P0001';
  end if;
  if p_data is not null and (p_data > current_date + 1 or p_data < date '1900-01-01') then
    raise exception 'RADAR085: a data de publicação da fonte não pode estar no futuro' using errcode = 'P0001';
  end if;
  v_url := public.radar_url_base(v_url);
  perform pg_advisory_xact_lock(hashtextextended('radar_texto_oficial:' || v_url, 0));
  -- o mesmo endereço já capturado (em qualquer fonte, com ou sem barra no fim): não se cria captura paralela
  select c.id, nullif(btrim(coalesce(c.texto, '')), '') is not null into v_id, v_tem_texto
    from public.radar_capturas c where public.radar_url_base(c.url) = v_url
   order by (c.fonte_id = p_fonte) desc, c.id limit 1;
  if v_id is not null and v_tem_texto then
    insert into public.radar_assunto_capturas (assunto_id, captura_id) values (p_assunto, v_id) on conflict do nothing;
    return jsonb_build_object('captura_id', v_id, 'ja_existia', true, 'texto_incluido', false);
  end if;
  if v_id is not null then
    -- o robô registrou o endereço mas não conseguiu ler o texto (PDF, página bloqueada): entra o texto colado
    update public.radar_capturas
       set texto = v_texto, data_publicacao = coalesce(data_publicacao, p_data),
           metadados = metadados || jsonb_build_object('manual', true, 'incluido_por', auth.uid(), 'incluido_em', now())
     where id = v_id;
  else
    -- o endereço tem de ser do site da fonte escolhida (ou de um domínio listado em config.dominios):
    -- não se atribui a um órgão o texto de outro site
    select lower(substring(f.url from '^https?://([^/:?#]+)')), f.config->'dominios' into v_dom_fonte, v_dominios
      from public.radar_fontes f where f.id = p_fonte;
    v_dom_fonte := regexp_replace(v_dom_fonte, '^www\.', '');
    v_dom_url   := lower(substring(v_url from '^https?://([^/:?#]+)'));
    if not (v_dom_url = v_dom_fonte or v_dom_url like '%.' || v_dom_fonte
            or (jsonb_typeof(v_dominios) = 'array' and exists (
                  select 1 from jsonb_array_elements_text(v_dominios) d
                  where v_dom_url = lower(d) or v_dom_url like '%.' || lower(d)))) then
      raise exception 'RADAR086: este endereço não é do site da fonte escolhida (%). Escolha a fonte certa ou peça ao administrador para cadastrá-la na aba Fontes', v_dom_fonte
        using errcode = 'P0001';
    end if;
    insert into public.radar_capturas (fonte_id, url, titulo, data_publicacao, texto, hash_titulo, metadados)
    values (p_fonte, v_url, v_titulo, p_data, v_texto, md5(public.radar_normalizar(v_titulo)),
            jsonb_build_object('manual', true, 'incluido_por', auth.uid(), 'incluido_em', now()))
    returning id into v_id;
    v_nova := true;
  end if;
  insert into public.radar_assunto_capturas (assunto_id, captura_id) values (p_assunto, v_id) on conflict do nothing;
  insert into public.radar_auditoria (tabela, registro_id, acao, usuario, depois)
  values ('radar_capturas', v_id::text, case when v_nova then 'INSERT' else 'UPDATE' end, auth.uid(),
          jsonb_build_object('manual', true, 'assunto_id', p_assunto, 'fonte_id', p_fonte, 'url', v_url, 'titulo', v_titulo,
                             'data_publicacao', p_data, 'caracteres', length(v_texto)));
  return jsonb_build_object('captura_id', v_id, 'ja_existia', not v_nova, 'texto_incluido', true);
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

drop trigger if exists radar_tg_normas_atualizado on public.radar_normas;
create trigger radar_tg_normas_atualizado before update on public.radar_normas
  for each row execute function public.radar_fn_atualizado_em();

drop trigger if exists radar_tg_captura_versionar on public.radar_capturas;
create trigger radar_tg_captura_versionar before insert or update on public.radar_capturas
  for each row execute function public.radar_fn_captura_versionar();

drop trigger if exists radar_tg_captura_origem on public.radar_capturas;
create trigger radar_tg_captura_origem before insert or update of duplicata_de on public.radar_capturas
  for each row execute function public.radar_fn_captura_origem();
drop trigger if exists radar_tg_captura_promover on public.radar_capturas;
create trigger radar_tg_captura_promover after insert on public.radar_capturas
  for each row execute function public.radar_fn_captura_promover();

drop trigger if exists radar_tg_captura_relevancia on public.radar_capturas;
create trigger radar_tg_captura_relevancia before insert or update on public.radar_capturas
  for each row execute function public.radar_fn_captura_relevancia();
drop trigger if exists radar_tg_config_relevancia on public.radar_config;
create trigger radar_tg_config_relevancia after insert or update or delete on public.radar_config
  for each row execute function public.radar_fn_config_relevancia();

drop trigger if exists radar_tg_conteudo_fonte on public.radar_conteudos;
create trigger radar_tg_conteudo_fonte before insert on public.radar_conteudos
  for each row execute function public.radar_fn_conteudo_fonte();

drop trigger if exists radar_tg_captura_reconferir on public.radar_capturas;
create trigger radar_tg_captura_reconferir after update on public.radar_capturas
  for each row execute function public.radar_fn_captura_reconferir();

drop trigger if exists radar_tg_evidencia_conferir on public.radar_evidencias;
create trigger radar_tg_evidencia_conferir before insert or update on public.radar_evidencias
  for each row execute function public.radar_fn_evidencia_conferir();

drop trigger if exists radar_tg_conteudo_envio on public.radar_conteudos;
create trigger radar_tg_conteudo_envio after update on public.radar_conteudos
  for each row execute function public.radar_fn_conteudo_envio();

drop trigger if exists radar_tg_conteudo_aprovacao on public.radar_conteudos;
create trigger radar_tg_conteudo_aprovacao before insert or update on public.radar_conteudos
  for each row execute function public.radar_fn_conteudo_aprovacao();


drop trigger if exists radar_tg_informativo on public.radar_informativos;
create trigger radar_tg_informativo before insert or update on public.radar_informativos
  for each row execute function public.radar_fn_informativo();
drop trigger if exists radar_tg_informativos_atualizado on public.radar_informativos;
create trigger radar_tg_informativos_atualizado before update on public.radar_informativos
  for each row execute function public.radar_fn_atualizado_em();
drop trigger if exists radar_tg_informativo_item on public.radar_informativo_itens;
create trigger radar_tg_informativo_item before insert or update or delete on public.radar_informativo_itens
  for each row execute function public.radar_fn_informativo_item();
drop trigger if exists radar_tg_fonte_formato on public.radar_fontes;
create trigger radar_tg_fonte_formato before insert or update on public.radar_fontes
  for each row execute function public.radar_fn_fonte_formato();
drop trigger if exists radar_tg_divulgacao on public.radar_divulgacoes;
create trigger radar_tg_divulgacao before insert or update on public.radar_divulgacoes
  for each row execute function public.radar_fn_divulgacao();
drop trigger if exists radar_tg_divulgacao_efeitos on public.radar_divulgacoes;
create trigger radar_tg_divulgacao_efeitos after insert or delete on public.radar_divulgacoes
  for each row execute function public.radar_fn_divulgacao_efeitos();
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
                           'radar_evidencias','radar_conteudos',
                           'radar_informativos','radar_config','radar_divulgacoes','radar_site_envios'] loop
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
       end as saude,
       -- v0.9.0: quando entrou a última captura (fonte que roda sem erro mas não traz nada novo há dias)
       (select max(c.capturado_em) from public.radar_capturas c where c.fonte_id = f.id) as ultima_captura_em
from public.radar_fontes f;

-- Fila de triagem: capturas que ainda não viraram assunto (nem foram ignoradas)
create or replace view public.radar_v_fila
with (security_invoker = true) as
select c.id, c.fonte_id, f.slug as fonte_slug, f.nome as fonte_nome, f.orgao, f.abrangencia,
       f.categoria_padrao, f.oficial, c.url, c.titulo, c.data_publicacao, c.resumo_fonte,
       c.capturado_em, c.versao, (c.texto is not null) as tem_texto, c.duplicata_de,
       c.relevancia, c.relevancia_pontos, c.relevancia_motivos,
       c.ia_nota, c.ia_motivo, c.ia_tema, c.ia_avaliado_em,
       (select count(*) from public.radar_capturas r where r.duplicata_de = c.id
          and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = r.id)) as repetidas,
       -- principal: é a que representa o fato na triagem. A repetição só fica escondida enquanto a origem dela
       -- também está na fila; se a origem já virou assunto (ou foi ignorada), a repetição aparece por conta própria.
       (c.duplicata_de is null
        or exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = c.duplicata_de)) as principal,
       -- nota do grupo: a maior entre a captura e as repetições dela que estão na fila
       greatest(c.ia_nota, (select max(r.ia_nota) from public.radar_capturas r where r.duplicata_de = c.id
          and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = r.id))) as nota_grupo,
       -- assunto em que a origem da repetição está (para avisar "parece o mesmo fato de …")
       -- (procura no grupo todo e prefere o assunto em andamento)
       o.id as origem_assunto_id, o.titulo || ' (' || o.status || ')' as origem_assunto
from public.radar_capturas c
join public.radar_fontes f on f.id = c.fonte_id
left join lateral (
  select a.id, a.titulo, a.status
    from public.radar_capturas g
    join public.radar_assunto_capturas ac on ac.captura_id = g.id
    join public.radar_assuntos a on a.id = ac.assunto_id
   where c.duplicata_de is not null and (g.id = c.duplicata_de or g.duplicata_de = c.duplicata_de)
   order by (a.status in ('ignorado','publicado','arquivado')), a.id
   limit 1) o on true
where not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = c.id);

-- "Em alta" (v0.7.0): o que a tela de Capturas mostra ao abrir. Só o que não é repetição nem de baixa relevância,
-- com nota da IA a partir do corte (ou ainda não avaliada), da maior nota para a menor, limitado à quantidade
-- configurada em radar_config.relevancia: "nota_corte" (padrão 6) e "quantidade" (padrão 10).
create or replace view public.radar_v_em_alta
with (security_invoker = true) as
select f.*
  from public.radar_v_fila f
 where f.principal and f.relevancia <> 'baixa'
   and (f.nota_grupo is null or f.nota_grupo >= coalesce((select case when jsonb_typeof(c.valor->'nota_corte') = 'number'
                                                               then least(greatest((c.valor->>'nota_corte')::numeric, 0), 10) end
                                                      from public.radar_config c where c.chave = 'relevancia'), 6))
 order by f.nota_grupo desc nulls last, f.relevancia_pontos desc, f.capturado_em desc, f.id desc
 limit coalesce((select case when jsonb_typeof(c.valor->'quantidade') = 'number'
                             then least(greatest((c.valor->>'quantidade')::numeric, 1), 100)::int end
                   from public.radar_config c where c.chave = 'relevancia'), 10);

-- Assuntos com os números que a lista do dashboard mostra
-- drop + create: a coluna publicacoes_no_ar saiu na v0.8.0 (create or replace não remove coluna)
drop view if exists public.radar_v_assuntos;
create view public.radar_v_assuntos
with (security_invoker = true) as
select a.*,
       (select count(*) from public.radar_evidencias e where e.assunto_id = a.id) as evidencias,
       (select count(*) from public.radar_evidencias e where e.assunto_id = a.id and e.trecho_conferido) as evidencias_conferidas,
       (select count(*) from public.radar_conteudos c where c.assunto_id = a.id) as conteudos,
       (select count(*) from public.radar_conteudos c where c.assunto_id = a.id and c.status = 'em_revisao') as em_revisao,
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
where em >= (date_trunc('month', now() at time zone 'America/Sao_Paulo') at time zone 'America/Sao_Paulo');   -- mês de Brasília (v0.11.1)

-- Números do painel do dia (uma linha). É recriada: assim colunas novas entram em qualquer atualização.
drop view if exists public.radar_v_painel;
create view public.radar_v_painel
with (security_invoker = true) as
select (select count(*) from public.radar_v_saude_fontes where ativo) as fontes_ativas,
       (select count(*) from public.radar_v_saude_fontes where saude = 'ok') as fontes_ok,
       (select count(*) from public.radar_capturas where capturado_em > now() - interval '24 hours') as capturas_24h,
       (select count(*) from public.radar_v_fila where relevancia <> 'baixa') as na_fila,      -- só o que merece triagem
       (select count(*) from public.radar_assuntos
         where relevancia = 'alta' and status not in ('publicado','ignorado','arquivado')) as alta_relevancia,
       (select count(*) from public.radar_assuntos
         where situacao_confirmacao = 'em_verificacao' and status not in ('publicado','ignorado','arquivado')) as em_verificacao,
       (select count(*) from public.radar_conteudos where status = 'em_revisao') as aguardando_aprovacao,
       (select count(*) from public.radar_v_fila where relevancia = 'baixa') as na_fila_baixa,
       (select count(*) from public.radar_v_fila where relevancia = 'alta') as na_fila_alta,
       (select count(*) from public.radar_v_em_alta) as em_alta,
       (select count(*) from public.radar_v_fila where relevancia <> 'baixa' and ia_avaliado_em is null) as sem_avaliacao_ia,
       (select count(*) from public.radar_v_fila where relevancia <> 'baixa' and principal) as na_fila_principal,
       (select count(distinct conteudo_id) from public.radar_divulgacoes) as no_site,
       (select count(*) from public.radar_conteudos c where c.status = 'aprovado' and not c.fora_do_site
          and not exists (select 1 from public.radar_divulgacoes d where d.conteudo_id = c.id)) as aprovados_sem_site,
       -- v0.9.0: rascunhos que o robô preparou e ninguém mexeu ainda
       (select count(*) from public.radar_conteudos c where c.status = 'rascunho' and c.modelo_ia like '%(robô)') as rascunhos_robo;

-- registro das publicações no site, com o estado atual do conteúdo (sem o texto, que é grande)
drop view if exists public.radar_v_divulgacoes;
create view public.radar_v_divulgacoes
with (security_invoker = true) as
select d.id, d.conteudo_id, d.url, d.publicado_em, d.observacao, d.titulo, d.registrado_por, d.registrado_em,
       c.assunto_id, c.status as conteudo_status, c.formato,
       (c.titulo is distinct from d.titulo or c.corpo is distinct from d.corpo) as texto_mudou,
       -- o texto mudou, mas já existe registro mais novo com o texto atual: este é só o histórico de uma versão anterior
       exists (select 1 from public.radar_divulgacoes n where n.conteudo_id = d.conteudo_id and n.id > d.id
                 and n.titulo = c.titulo and n.corpo = c.corpo) as versao_anterior,
       d.fundamentacao,
       -- a base que sustentava o registro deixou de existir (assunto desconfirmado ou sem trecho conferido em fonte oficial)
       (a.situacao_confirmacao <> 'confirmado_oficialmente' or not exists (
          select 1 from public.radar_evidencias e
          join public.radar_capturas k on k.id = e.captura_id
          join public.radar_fontes   f on f.id = k.fonte_id
          where e.assunto_id = c.assunto_id and e.trecho_conferido and f.oficial)) as base_caiu
from public.radar_divulgacoes d
join public.radar_conteudos c on c.id = d.conteudo_id
join public.radar_assuntos  a on a.id = c.assunto_id;

-- ---------------------------------------------------------------------
-- 5. RLS
-- ---------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['radar_instalacoes','radar_perfis','radar_categorias','radar_fontes',
      'radar_execucoes','radar_capturas','radar_capturas_versoes','radar_normas','radar_assuntos',
      'radar_assunto_capturas','radar_evidencias','radar_conteudos',
      'radar_auditoria','radar_ia_uso','radar_imagens','radar_config',
      'radar_informativos','radar_informativo_itens','radar_divulgacoes','radar_site_envios'] loop
    execute format('alter table public.%I enable row level security', t);
    -- parte do zero: o Supabase concede tudo a esses papéis por padrão
    execute format('revoke all on public.%I from public, anon, authenticated, service_role', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);  -- quem decide é a RLS
    execute format('grant select on public.%I to service_role', t);
  end loop;
end $$;

-- service_role (robô e, no Bloco 2, a função de IA): só o que precisa gravar.
-- NÃO grava auditoria, perfis, fontes, versões nem apaga nada.
grant insert, update on public.radar_execucoes, public.radar_capturas to service_role;
-- v0.8.0: o robô registra a publicação que encontrou no site (só inclui; as regras do registro valem igual)
grant insert on public.radar_divulgacoes to service_role;

-- v0.10.0: o robô que publica no site marca o andamento de cada autorização (nunca cria nem apaga)
grant update on public.radar_site_envios to service_role;
grant insert, update on public.radar_assuntos, public.radar_assunto_capturas, public.radar_evidencias,
                        public.radar_conteudos, public.radar_normas to service_role;

-- v0.5.0: não há mais página pública. O visitante (anon) não lê NADA do Radar: as permissões
-- foram retiradas no laço acima e nenhuma é concedida de volta. A publicação é feita no site da Artecon.
-- imagem não se altera depois de enviada (troca-se por outra)
revoke update on public.radar_imagens from authenticated;
-- o vínculo assunto–captura não se altera (cria-se ou remove-se): assim ninguém marca à mão um vínculo como
-- "juntado pela IA" para depois removê-lo pelo "Não é o mesmo fato" (remover vínculo comum é só do administrador)
revoke update on public.radar_assunto_capturas from authenticated;

revoke all on public.radar_v_saude_fontes, public.radar_v_fila, public.radar_v_em_alta, public.radar_v_assuntos, public.radar_v_painel, public.radar_v_ia_mes, public.radar_v_divulgacoes
  from public, anon, authenticated, service_role;
grant select on public.radar_v_saude_fontes, public.radar_v_fila, public.radar_v_em_alta, public.radar_v_assuntos, public.radar_v_painel, public.radar_v_ia_mes, public.radar_v_divulgacoes
  to authenticated, service_role;
-- uso da IA: só se consulta; quem grava é a função radar_registrar_uso_ia
revoke insert, update, delete on public.radar_ia_uso from authenticated;
-- v0.10.0: autorizações de publicação no site: a equipe só lê; quem grava são radar_autorizar_site/radar_cancelar_site e o robô
revoke insert, update, delete on public.radar_site_envios from authenticated;

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
-- v0.9.0: o robô abre o assunto da notícia de topo para deixar o rascunho pronto (rascunhos automáticos)
grant execute on function public.radar_abrir_assunto(bigint, boolean) to service_role;
revoke all on function public.radar_ignorar_capturas(bigint[]) from public, anon;
grant execute on function public.radar_ignorar_capturas(bigint[]) to authenticated;
grant execute on function public.radar_gravar_avaliacao_ia(jsonb) to service_role;
grant execute on function public.radar_limpar_imagens_sem_uso(int) to service_role;
grant execute on function public.radar_arquivar_fila(int) to service_role;
grant execute on function public.radar_separar_captura(bigint, bigint) to authenticated;
grant execute on function public.radar_admin_usuarios() to authenticated;
grant execute on function public.radar_registrar_uso_ia(text, text, int, int, bigint) to authenticated;
grant execute on function public.radar_registrar_evidencia_ia(bigint, bigint, text, text) to authenticated;
grant execute on function public.radar_incluir_texto_oficial(bigint, bigint, text, text, date, text) to authenticated;
-- v0.10.0: autorização de publicação no site (a função confere que é o administrador)
grant execute on function public.radar_autorizar_site(bigint, text, timestamptz) to authenticated;
grant execute on function public.radar_cancelar_site(bigint) to authenticated;
-- o robô confere de novo as exigências do assunto logo antes de enviar ao site
grant execute on function public.radar_pendencia_assunto(bigint) to service_role;

-- perfis
drop policy if exists radar_perfis_sel on public.radar_perfis;
create policy radar_perfis_sel on public.radar_perfis for select to authenticated
  using (user_id = auth.uid() or (select public.radar_papel()) = 'admin');
drop policy if exists radar_perfis_adm on public.radar_perfis;
create policy radar_perfis_adm on public.radar_perfis for all to authenticated
  using ((select public.radar_papel()) = 'admin') with check ((select public.radar_papel()) = 'admin');

-- categorias (a equipe lê; escrita do admin)
drop policy if exists radar_categorias_sel on public.radar_categorias;
create policy radar_categorias_sel on public.radar_categorias for select to authenticated
  using ((select public.radar_papel()) is not null);
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
  foreach t in array array['radar_execucoes','radar_capturas','radar_capturas_versoes','radar_site_envios'] loop
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
                           'radar_evidencias','radar_conteudos',
                           'radar_imagens','radar_informativos','radar_informativo_itens','radar_divulgacoes'] loop
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

-- imagens: sem acesso público (a política antiga da vitrine é removida)
drop policy if exists radar_imagens_vitrine on public.radar_imagens;

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
where not exists (select 1 from public.radar_instalacoes i where i.depois is not null)
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
where not exists (select 1 from public.radar_instalacoes i where i.depois is not null)
on conflict (slug) do nothing;


-- Configurações iniciais (só na PRIMEIRA vez em que cada chave não existe; depois valem as suas)
insert into public.radar_config (chave, valor) values
  ('obrigacoes', '[{"nome": "Salário dos Colaboradores (Empregados)", "regra": "quinto_dia_util"}, {"nome": "Salários - Trabalhador Doméstico", "regra": "dia", "dia": 7, "ajuste": "antecipa"}, {"nome": "ICMS", "regra": "dia", "dia": 10, "ajuste": "posterga"}, {"nome": "ICMS Substituição Tributária", "regra": "dia", "dia": 10, "ajuste": "posterga"}, {"nome": "Carnê INSS Individual", "regra": "dia", "dia": 15, "ajuste": "posterga"}, {"nome": "FGTS - Fundo de Garantia Por Tempo de Serviço", "regra": "dia", "dia": 20, "ajuste": "antecipa"}, {"nome": "GPS (Empresa)", "regra": "dia", "dia": 20, "ajuste": "antecipa"}, {"nome": "IRRF (Rendimento Serviço Prestado Cód. 1708)", "regra": "dia", "dia": 20, "ajuste": "antecipa"}, {"nome": "IRRF (Rendimento de Trabalhador Cód. 0561)", "regra": "dia", "dia": 20, "ajuste": "antecipa"}, {"nome": "Simples Doméstico", "regra": "dia", "dia": 20, "ajuste": "posterga"}, {"nome": "Simples Nacional", "regra": "dia", "dia": 20, "ajuste": "posterga"}, {"nome": "Honorário contábil", "regra": "dia", "dia": 20, "ajuste": "posterga"}, {"nome": "PIS", "regra": "dia", "dia": 25, "ajuste": "antecipa"}, {"nome": "COFINS", "regra": "dia", "dia": 25, "ajuste": "antecipa"}, {"nome": "IPI", "regra": "dia", "dia": 25, "ajuste": "antecipa"}, {"nome": "CSLL - Contribuição Social sobre o Lucro Líquido", "regra": "ultimo_dia_util"}, {"nome": "IRPJ - Imposto de Renda Pessoa Jurídica", "regra": "ultimo_dia_util"}, {"nome": "Imposto de Renda Pessoa Física (Cód. 0190)", "regra": "ultimo_dia_util"}, {"nome": "INSS - Parcelamento p/ Ingresso no Simples Nacional", "regra": "ultimo_dia_util"}, {"nome": "Parcelamentos Federais e Parcelamento Especial", "regra": "ultimo_dia_util"}, {"nome": "PERT – Programa Esp. Regularização Tributária", "regra": "ultimo_dia_util"}, {"nome": "Parcelamento Especial - Simples Nacional", "regra": "ultimo_dia_util"}]'::jsonb),
  ('feriados_extras', '[]'::jsonb),
  ('fale_conosco', '{"setores": [{"nome": "Geral", "rotulo": "Atendimento Geral", "telefones": [{"numero": "48-3242-0530", "whatsapp": true}], "emails": ["artecon@artecon.cnt.br"], "equipe": []}, {"nome": "Setor Contábil", "rotulo": "Setor Contábil", "telefones": [], "emails": ["dc@artecon.cnt.br"], "equipe": [], "responsaveis_rotulo": "Contadores Responsáveis", "responsaveis": []}, {"nome": "Setor Fiscal", "rotulo": "Setor Fiscal", "telefones": [], "emails": ["df@artecon.cnt.br"], "equipe": []}, {"nome": "Departamento Pessoal", "rotulo": "Departamento Pessoal", "telefones": [], "emails": ["rh@artecon.cnt.br"], "equipe": []}, {"nome": "Setor Institucional", "rotulo": "Setor Institucional", "telefones": [], "emails": ["societario@artecon.cnt.br"], "equipe": []}], "observacao": ""}'::jsonb),
  ('assinatura', '{"local": "Palhoça, SC", "empresa": "Artecon Artes Contábeis ME", "responsavel": "Cleiver Gonçalves"}'::jsonb),
  ('rascunhos', '{"ligado": true, "nota_minima": 9, "por_dia": 2, "dias": 3, "formato": "informativo"}'::jsonb),
  ('relevancia', '{"limite_alta": 8, "limite_media": 3, "termos": [{"termo": "reforma tributária", "pontos": 5}, {"termo": "IBS", "pontos": 5}, {"termo": "CBS", "pontos": 5}, {"termo": "imposto seletivo", "pontos": 5}, {"termo": "Simples Nacional", "pontos": 5}, {"termo": "MEI", "pontos": 5}, {"termo": "microempreendedor", "pontos": 5}, {"termo": "prorroga", "pontos": 5}, {"termo": "prorrogado", "pontos": 5}, {"termo": "prorrogados", "pontos": 5}, {"termo": "prorrogação", "pontos": 5}, {"termo": "prazo", "pontos": 5}, {"termo": "prazos", "pontos": 5}, {"termo": "lei complementar", "pontos": 5}, {"termo": "transação", "pontos": 5}, {"termo": "parcelamento", "pontos": 5}, {"termo": "regularização", "pontos": 5}, {"termo": "Refis", "pontos": 5}, {"termo": "instrução normativa", "pontos": 4}, {"termo": "vencimento", "pontos": 4}, {"termo": "obrigação acessória", "pontos": 4}, {"termo": "DCTF", "pontos": 4}, {"termo": "DCTFWeb", "pontos": 4}, {"termo": "EFD", "pontos": 4}, {"termo": "ECF", "pontos": 4}, {"termo": "ECD", "pontos": 4}, {"termo": "eSocial", "pontos": 4}, {"termo": "Reinf", "pontos": 4}, {"termo": "imposto de renda", "pontos": 4}, {"termo": "IRPF", "pontos": 4}, {"termo": "IRPJ", "pontos": 4}, {"termo": "CSLL", "pontos": 4}, {"termo": "PIS", "pontos": 4}, {"termo": "Cofins", "pontos": 4}, {"termo": "ICMS", "pontos": 4}, {"termo": "ISS", "pontos": 4}, {"termo": "substituição tributária", "pontos": 4}, {"termo": "DIFAL", "pontos": 4}, {"termo": "NFS-e", "pontos": 4}, {"termo": "NF-e", "pontos": 4}, {"termo": "nota fiscal", "pontos": 4}, {"termo": "FGTS", "pontos": 4}, {"termo": "INSS", "pontos": 4}, {"termo": "contribuição previdenciária", "pontos": 4}, {"termo": "folha de pagamento", "pontos": 4}, {"termo": "desoneração", "pontos": 4}, {"termo": "lucro presumido", "pontos": 4}, {"termo": "lucro real", "pontos": 4}, {"termo": "dividendos", "pontos": 4}, {"termo": "distribuição de lucros", "pontos": 4}, {"termo": "edital", "pontos": 4}, {"termo": "editais", "pontos": 4}, {"termo": "Regularize", "pontos": 4}, {"termo": "exclusão", "pontos": 4}, {"termo": "opção", "pontos": 4}, {"termo": "decreto", "pontos": 3}, {"termo": "medida provisória", "pontos": 3}, {"termo": "alíquota", "pontos": 3}, {"termo": "alíquotas", "pontos": 3}, {"termo": "tabela", "pontos": 3}, {"termo": "CNPJ", "pontos": 3}, {"termo": "contribuinte", "pontos": 3}, {"termo": "contribuintes", "pontos": 3}, {"termo": "empresas", "pontos": 3}, {"termo": "tributária", "pontos": 3}, {"termo": "tributário", "pontos": 3}, {"termo": "tributos", "pontos": 3}, {"termo": "benefício fiscal", "pontos": 3}, {"termo": "TTD", "pontos": 3}, {"termo": "Santa Catarina", "pontos": 3}, {"termo": "salário mínimo", "pontos": 3}, {"termo": "perguntas e respostas", "pontos": 3}, {"termo": "orientação", "pontos": 3}, {"termo": "guia", "pontos": 3}, {"termo": "CGIBS", "pontos": 3}, {"termo": "CGSN", "pontos": 3}, {"termo": "restituição", "pontos": 3}, {"termo": "compensação", "pontos": 3}, {"termo": "crédito", "pontos": 3}, {"termo": "declaração", "pontos": 3}, {"termo": "malha", "pontos": 3}, {"termo": "débitos", "pontos": 3}, {"termo": "dívida ativa", "pontos": 3}, {"termo": "solução de consulta", "pontos": 2}, {"termo": "portaria", "pontos": 2}, {"termo": "resolução", "pontos": 2}, {"termo": "ato DIAT", "pontos": 2}, {"termo": "ato declaratório executivo", "pontos": -3}, {"termo": "apreende", "pontos": -8}, {"termo": "apreensão", "pontos": -8}, {"termo": "apreendidos", "pontos": -8}, {"termo": "apreendidas", "pontos": -8}, {"termo": "contrabando", "pontos": -8}, {"termo": "descaminho", "pontos": -8}, {"termo": "leilão", "pontos": -8}, {"termo": "maconha", "pontos": -8}, {"termo": "cocaína", "pontos": -8}, {"termo": "drogas", "pontos": -8}, {"termo": "haxixe", "pontos": -8}, {"termo": "cigarros", "pontos": -8}, {"termo": "armas", "pontos": -8}, {"termo": "aduana", "pontos": -8}, {"termo": "alfândega", "pontos": -8}, {"termo": "alfandegado", "pontos": -8}, {"termo": "aeroporto", "pontos": -8}, {"termo": "fronteira", "pontos": -8}, {"termo": "concurso", "pontos": -8}, {"termo": "servidores", "pontos": -8}, {"termo": "nomeia", "pontos": -8}, {"termo": "designa", "pontos": -8}, {"termo": "delega", "pontos": -8}, {"termo": "credenciamento", "pontos": -8}, {"termo": "despachante", "pontos": -8}, {"termo": "Instagram", "pontos": -8}, {"termo": "homenagem", "pontos": -8}, {"termo": "prêmio", "pontos": -8}, {"termo": "seminário", "pontos": -8}]}'::jsonb)
on conflict (chave) do nothing;

-- v0.9.0: Destaques do DOU (fonte de sql/radar-fontes-novas-2026-10.sql) — só os atos fiscais e as leis, decretos e MPs.
-- Só troca se o padrão ainda for o original: não desfaz um ajuste feito na tela; sem a fonte, não faz nada.
update public.radar_fontes
   set config = jsonb_set(config, '{padrao_url}',
         to_jsonb('/web/dou/-/(?:lei-|decreto-n-|medida-provisoria-|[^?#]*(?:rfb|pgfn|cgsn|cgibs|cosit|receita|fazenda|[-/]mf[-/]))[^?#]*-\d{6,}$'::text))
 where slug = 'dou-destaques' and config->>'padrao_url' = '/web/dou/-/[^?#]+-\d{6,}$';

-- v0.11.1: captura oficial que tinha ficado atrás de um boletim não oficial volta a ser a principal (fora as que já viraram assunto)
do $$
declare r record;
begin
  for r in select c.id, c.duplicata_de as outra
             from public.radar_capturas c join public.radar_fontes f on f.id = c.fonte_id
             join public.radar_capturas o on o.id = c.duplicata_de join public.radar_fontes fo on fo.id = o.fonte_id
            where f.oficial and not fo.oficial
              and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = c.id)
              and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = o.id)
            order by c.id loop
    continue when (select c.duplicata_de from public.radar_capturas c where c.id = r.id) is distinct from r.outra;   -- já arrumada no passo anterior
    update public.radar_capturas set duplicata_de = null where id = r.id;
    perform public.radar_promover_oficial(r.id, r.outra);
  end loop;
end $$;

-- capturas que já estavam no banco são avaliadas pelas regras em vigor
select public.radar_reavaliar_capturas() as capturas_reavaliadas;

-- ---------------------------------------------------------------------
-- 7. REGISTRO DA INSTALAÇÃO E EVIDÊNCIA
-- ---------------------------------------------------------------------
update public.radar_instalacoes
set depois = (select jsonb_agg(jsonb_build_object('tabela', c.relname, 'rls', c.relrowsecurity) order by c.relname)
              from pg_class c join pg_namespace n on n.oid = c.relnamespace
              where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'radar\_%')
where id = (select max(id) from public.radar_instalacoes) and depois is null;

commit;

-- EVIDÊNCIA: exporte este resultado em CSV e guarde/envie para conferência.
-- Esperado: 20 tabelas, todas com rls = true; 6 fontes; 8 categorias; ao menos 1 instalação concluída (v0.11.1).
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
select 'instalacoes concluidas', count(*)::text, max(versao), null, null from public.radar_instalacoes where depois is not null
order by 1, 2;
