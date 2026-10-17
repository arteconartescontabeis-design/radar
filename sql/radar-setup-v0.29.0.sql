-- =====================================================================
-- RADAR ARTECON — Plataforma de Inteligência Contábil e Tributária
-- radar-setup-v0.29.0.sql  ·  banco, coletores, telas, IA, Informativo Mensal, Pauta das redes, corretor de vídeo dos reels e lembretes
--
-- Serve para instalar do zero e para atualizar qualquer versão anterior (se já estiver instalada).
-- IDEMPOTENTE: pode ser executado mais de uma vez sem duplicar nem apagar
-- dados. Cada execução fica registrada em radar_instalacoes com o estado
-- ANTES e DEPOIS. A última instrução devolve a evidência da instalação.
-- v0.21.0: aba Pauta (radar_pauta_pecas, radar_pessoas) e publicação agendada; a agenda do banco (pg_cron) fica à parte,
-- em sql/radar-redes-agenda.sql, rodado DEPOIS deste.
-- v0.22.0: corretor de vídeo dos reels (radar_videos, radar_video_acessos, funções radar_video_*; o vídeo aprovado fica amarrado à
-- peça pelo sha256). Os arquivos ficam no bucket PRIVADO radar-videos, que só a função radar-video toca; a agenda dela (reserva da
-- fila e limpeza diária, pg_cron) e as chaves do Vault ficam em sql/radar-video-agenda.sql, rodado DEPOIS deste.
-- v0.24.0: Diretrizes editoriais do escritório. A "Conferência das Diretrizes" (os 10 critérios antes de aprovar: a lista da IA e o
-- "Revisei e assumo" do administrador) fica em radar_conteudos.conferencia, presa à versão do texto, e a aprovação confere; o texto
-- INFORMATIVO (sem fundamentação legal específica) só é aprovado depois que o administrador autoriza a publicação do assunto (o mesmo
-- "Publicar mesmo assim", com o motivo). Nenhuma tabela nova; as agendas (sql/radar-*-agenda.sql) não mudam.
-- v0.24.0 (etapa 5): a base legal do texto termina com a linha "Fonte oficial: <norma> — <link>" (a seção "Fundamentação legal" dos
-- textos de antes continua valendo) e a revisão editorial automática da IA fica guardada na mesma coluna (conferencia->'editorial',
-- só informativa: não trava a aprovação), presa à versão do texto do conteúdo (radar_texto_versao).
-- v0.25.0 (etapa 6): uma imagem só para a publicação (a mesma no site, no Instagram e no Facebook). A imagem gerada pela IA vai inteira, em
-- 3:2, com o aviso "Imagem ilustrativa gerada por IA" desenhado pela tela no canto, e fica guardada como a ilustração do conteúdo
-- (imagem_id = ilustracao_id); trocada pela capa padrão ou por uma foto da equipe, ela continua guardada (ilustracao_id), para voltar sem
-- nova cobrança. O critério 6 da Conferência das Diretrizes (radar_conferencia_codigo) passa a reconhecer as duas situações. Nenhuma
-- tabela ou coluna nova; nada é apagado; as agendas (sql/radar-*-agenda.sql) não mudam.
-- v0.28.0: "+ Nova peça" e "Sócio(a) da Artecon" na Pauta. radar_pauta_criar: o administrador cria a peça de um dia que ainda não tem
-- nenhuma (de hoje em diante, de Brasília; uma peça por dia), com a mesma conferência da importação do calendário (radar_pauta_linha_invalida);
-- ela nasce planejada e não publica nem agenda nada. radar_pessoas.socio: o(a) sócio(a) da Artecon, maior de idade, não precisa do
-- termo de uso de imagem nem do termo do corretor de vídeo (radar_pauta_termo_ok, radar_video_pessoa_falta e radar_video_limpeza);
-- continuam valendo: ativa, maior de idade, marcada em "Quem aparece" e as quatro declarações do envio do vídeo. Uma coluna nova (com
-- valor padrão), nenhuma tabela nova; nada é apagado; as agendas (sql/radar-*-agenda.sql) não mudam.
-- v0.29.0: lembretes antes do dia, por e-mail (um aviso no GitHub, como os avisos de hoje, sem nome de ninguém). Uma tabela nova,
-- radar_lembretes (uma linha por pendência: a peça da Pauta de amanhã, ou a de hoje, que ainda não está aprovada; a peça pronta que
-- espera a aprovação há mais de N horas; o vídeo do reel que o corretor terminou; a notícia que deu erro no envio ao site ou às redes,
-- ou que está autorizada e parada há mais de X horas), as funções radar_lembretes_* e a chave "lembretes" das Configurações (entra com
-- os padrões; a que já existir não é sobrescrita). Quem decide o que lembrar e quando é o banco (radar_lembretes_devidos: no máximo um
-- e-mail por tipo por dia, cada pendência uma vez só, e a pendência "fecha" sozinha quando é resolvida). A agenda que pede o robô dos
-- lembretes ao GitHub (de 15 em 15 minutos) fica em sql/radar-redes-agenda.sql, rodado DEPOIS deste. Nada é apagado.
-- Reversão: radar-reversao-v0.29.0.sql
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
  insert into public.radar_instalacoes (versao, antes) values ('v0.29.0', v_antes);
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
-- v0.15.0: fundamentação legal citada no texto capturado (normas e códigos), calculada pelo banco — null = ainda não lida
alter table public.radar_capturas add column if not exists base_legal jsonb;

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
-- v0.12.0: o administrador pode liberar a publicação no site sem a fundamentação oficial (com o motivo, que fica registrado)
alter table public.radar_assuntos add column if not exists liberado_sem_base_por    uuid references auth.users(id) on delete set null;
alter table public.radar_assuntos add column if not exists liberado_sem_base_em     timestamptz;
alter table public.radar_assuntos add column if not exists liberado_sem_base_motivo text check (length(liberado_sem_base_motivo) between 10 and 500);
-- v0.14.0: resultado da verificação em fontes oficiais feita pela IA na internet (situação, resumo e as fontes oficiais
-- encontradas, com o link). É só apoio: a fundamentação continua sendo o texto oficial incluído e o trecho conferido.
alter table public.radar_assuntos add column if not exists verificacao   jsonb check (verificacao is null or jsonb_typeof(verificacao) = 'object');
alter table public.radar_assuntos add column if not exists verificado_em timestamptz;

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

-- v0.12.0: boletins da ITC já lidos pela função radar-itc (Microsoft Graph). Só o identificador do e-mail e contagens:
-- o conteúdo do boletim (pago) fica só nas capturas, como antes.
create table if not exists public.radar_itc_lidos (
  message_id   text        primary key check (length(message_id) between 1 and 400),
  assunto      text        check (length(assunto) <= 200),
  recebido_em  timestamptz,
  lido_em      timestamptz not null default now(),
  materias     int         not null default 0 check (materias >= 0),
  novas        int         not null default 0 check (novas >= 0),
  tentativas   int         not null default 1 check (tentativas >= 1)   -- leituras sem matéria (ou com erro): desiste na 3ª
);
alter table public.radar_itc_lidos add column if not exists tentativas int not null default 1 check (tentativas >= 1);
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
-- v0.16.0: a ilustração da IA fica guardada à parte; a capa é montada com ela ao fundo (logotipo, categoria e título por cima)
-- e pode ser refeita com o título novo sem gerar outra ilustração
alter table public.radar_conteudos   add column if not exists ilustracao_id bigint references public.radar_imagens(id) on delete set null;
-- v0.16.0: "Autorizar mesmo assim" o texto com trecho igual ao da fonte: quem, quando e por quê. Cai quando o texto muda.
alter table public.radar_conteudos   add column if not exists copia_autorizada_em     timestamptz;
alter table public.radar_conteudos   add column if not exists copia_autorizada_por    uuid references auth.users(id) on delete set null;
alter table public.radar_conteudos   add column if not exists copia_autorizada_motivo text;
-- v0.20.0: kit das redes feito pela IA (chamada e apoio da arte, legendas do Instagram e do Facebook, roteiro de reel).
-- É sugestão: o que vai ao ar é o que o administrador autoriza (radar_redes_envios). Gravar o kit não muda a data do
-- conteúdo nem derruba autorizações; mudar o texto marca o kit como desatualizado (radar_fn_conteudo_aprovacao).
alter table public.radar_conteudos add column if not exists kit_ia jsonb not null default '{}'::jsonb;
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'radar_conteudos_kit_ia') then
    alter table public.radar_conteudos add constraint radar_conteudos_kit_ia
      check (jsonb_typeof(kit_ia) = 'object' and length(kit_ia::text) <= 20000) not valid;
  end if;
end $$;
-- v0.24.0: Conferência das Diretrizes (os 10 critérios do escritório antes de aprovar): a lista da IA ("Revisar com IA") e o "Revisei e
-- assumo" do administrador, presos à versão do texto (radar_conferencia_versao). Só mudam pelas funções radar_registrar_conferencia e
-- radar_assumir_conferencia; gravar a conferência não muda a data do conteúdo (radar_fn_atualizado_em). '{}' = ainda não conferido.
-- v0.24.0 (etapa 5): a chave 'editorial' é a revisão editorial automática (só pela função radar_registrar_revisao_editorial).
alter table public.radar_conteudos add column if not exists conferencia jsonb not null default '{}'::jsonb;
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'radar_conteudos_conferencia') then
    alter table public.radar_conteudos add constraint radar_conteudos_conferencia
      check (jsonb_typeof(conferencia) = 'object' and length(conferencia::text) <= 20000) not valid;
  end if;
end $$;

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
                   check (situacao in ('autorizado','enviando','publicado','erro','cancelado','excluido')),
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

-- v0.13.0: publicação no Instagram e no Facebook (API da Meta), sempre depois da autorização do administrador.
-- A tela monta a imagem (JPEG; vertical, 1080×1350, desde a v0.20.0) e a legenda; o administrador confere e autoriza;
-- a função radar-redes (Supabase) envia a imagem ao armazenamento, publica e registra o link. v0.22.0 (rodada 2 da varredura
-- geral): o armazenamento é o privado da Pauta (radar-pauta, nome aleatório, a Meta recebe um link de 10 minutos); antes era o
-- público radar-redes, com nome previsível, para sempre. imagem_url guarda o endereço interno (ou o público, nos envios antigos).
-- "dispensado" = não vai a este canal.
-- Nunca publica duas vezes: só uma autorização em andamento ou concluída por conteúdo e canal.
create table if not exists public.radar_redes_envios (
  id               bigint generated always as identity primary key,
  conteudo_id      bigint      not null references public.radar_conteudos(id) on delete restrict,
  canal            text        not null check (canal in ('instagram','facebook')),
  legenda          text        not null check (length(legenda) between 10 and 2200),
  imagem           text        check (imagem is null or (imagem like 'data:image/jpeg;base64,%' and length(imagem) <= 3000000)),
  conteudo_lido_em timestamptz not null,          -- versão do texto que foi vista e autorizada
  situacao         text        not null default 'autorizado'
                   check (situacao in ('aguardando_site','autorizado','enviando','publicado','erro','cancelado','dispensado','excluido')),
  autorizado_por   uuid        references auth.users(id) on delete set null,
  autorizado_em    timestamptz not null default now(),
  cancelado_por    uuid        references auth.users(id) on delete set null,
  cancelado_em     timestamptz,
  enviado_em       timestamptz,
  publicado_em     timestamptz,
  post_id          text        check (length(post_id) <= 100),
  url              text        check (url is null or (url ~ '^https://[!-~]+$' and length(url) <= 500)),
  imagem_url       text        check (imagem_url is null or (imagem_url ~ '^https?://[!-~]+$' and length(imagem_url) <= 500)),
  erro             text        check (length(erro) <= 1000),
  atualizado_em    timestamptz not null default now()
);
create index if not exists radar_redes_envios_conteudo_idx on public.radar_redes_envios (conteudo_id);
create unique index if not exists radar_redes_envios_aberto_uk on public.radar_redes_envios (conteudo_id, canal)
  where situacao in ('aguardando_site','autorizado','enviando','erro','publicado','dispensado');

-- v0.17.0: "Publicar em todos" e exclusão da publicação, a pedido do administrador.
--   aguardando_site: autorizado junto com o site; vira "autorizado" sozinho quando a notícia entra no site (o link do site
--                    entra na legenda no lugar de {LINK DO SITE}) e o robô do site manda publicar logo em seguida
--   excluido:        a publicação foi apagada da rede (pela função radar-redes ou à mão, registrado pelo administrador)
alter table public.radar_redes_envios add column if not exists junto_com_site boolean not null default false;
alter table public.radar_redes_envios add column if not exists excluido_em    timestamptz;
alter table public.radar_redes_envios add column if not exists excluido_por   uuid references auth.users(id) on delete set null;
alter table public.radar_redes_envios add column if not exists excluido_como  text check (excluido_como in ('api','manual'));
alter table public.radar_site_envios  add column if not exists excluido_em    timestamptz;
-- instalação anterior: troca a regra dos estados e o índice de "uma em aberto por canal" (só se ainda forem os antigos)
do $$
begin
  if not exists (select 1 from pg_constraint where conrelid = 'public.radar_redes_envios'::regclass
                  and conname = 'radar_redes_envios_situacao_check' and pg_get_constraintdef(oid) like '%aguardando_site%') then
    alter table public.radar_redes_envios drop constraint if exists radar_redes_envios_situacao_check;
    alter table public.radar_redes_envios add constraint radar_redes_envios_situacao_check
      check (situacao in ('aguardando_site','autorizado','enviando','publicado','erro','cancelado','dispensado','excluido'));
  end if;
  if not exists (select 1 from pg_indexes where schemaname = 'public' and indexname = 'radar_redes_envios_aberto_uk'
                  and indexdef like '%aguardando_site%') then
    drop index if exists public.radar_redes_envios_aberto_uk;
    create unique index radar_redes_envios_aberto_uk on public.radar_redes_envios (conteudo_id, canal)
      where situacao in ('aguardando_site','autorizado','enviando','erro','publicado','dispensado');
  end if;
  if not exists (select 1 from pg_constraint where conrelid = 'public.radar_site_envios'::regclass
                  and conname = 'radar_site_envios_situacao_check' and pg_get_constraintdef(oid) like '%excluido%') then
    alter table public.radar_site_envios drop constraint if exists radar_site_envios_situacao_check;
    alter table public.radar_site_envios add constraint radar_site_envios_situacao_check
      check (situacao in ('autorizado','enviando','publicado','erro','cancelado','excluido'));
  end if;
end $$;

-- v0.21.0: quem pode aparecer nas peças da Pauta e o termo de uso de imagem de cada pessoa. Só no banco (o repositório é
-- público): leem o administrador e o editor, grava só o administrador; o leitor e o robô não leem. A trilha guarda as datas do
-- termo, os canais, os usos e quem mudou — nunca o nome, o nome na peça, a área nem o CRC (radar_fn_auditar).
create table if not exists public.radar_pessoas (
  id                bigint generated always as identity primary key,
  nome              text    not null check (length(btrim(nome)) between 2 and 80),          -- nome completo (interno)
  nome_na_peca      text    not null check (length(btrim(nome_na_peca)) between 2 and 60),  -- como o termo autoriza (completo ou só o primeiro)
  area              text    not null default '' check (length(area) <= 60),
  categoria         text    not null default '' check (categoria in ('','contador','contadora','tecnico','tecnica')),
  crc               text    not null default '' check (crc = '' or (length(crc) <= 40 and crc ~ '^CRC' and crc ~ '[0-9]{4,6}')),
  termo_assinado_em date,
  termo_valido_ate  date,
  termo_revogado_em date,
  termo_canais      text[]  not null default '{}' check (termo_canais <@ array['instagram','facebook']::text[]),
  termo_usos        text[]  not null default '{}' check (termo_usos <@ array['equipe','orientacao','datas','captacao']::text[]),
  ativo             boolean not null default true,
  criado_em         timestamptz not null default now(),
  atualizado_em     timestamptz not null default now(),
  constraint radar_pessoas_categoria_crc check (categoria = '' or crc <> ''),     -- "contador(a)" e "técnico(a)" só com registro
  constraint radar_pessoas_termo_prazo check (termo_valido_ate is null or (termo_assinado_em is not null and termo_valido_ate >= termo_assinado_em))
);
-- v0.22.0: o corretor de vídeo. termo_corretor_em: a pessoa assinou o termo que cita o corretor do Radar e os operadores (Supabase,
-- GitHub/Microsoft, Azure Speech; desenho 3.4) — sem ele, nenhum vídeo com ela é aceito (radar_video_criar). quer_ver_peca: o item
-- "quero ver a peça" do termo (a aprovação pede a caixa "A pessoa viu o vídeo final"). menor: menor de 18 anos (o corretor recusa
-- nesta versão). Vão para a trilha (não são nome).
alter table public.radar_pessoas add column if not exists termo_corretor_em date;
alter table public.radar_pessoas add column if not exists quer_ver_peca boolean not null default false;
alter table public.radar_pessoas add column if not exists menor boolean not null default false;
-- v0.28.0: sócio(a) da Artecon. Quem tem a marca (e é maior de idade) não precisa do termo de uso de imagem (datas, canais e
-- finalidades) nem do termo do corretor de vídeo (radar_pauta_termo_ok, radar_video_pessoa_falta e radar_video_limpeza). Continuam
-- valendo: ativa, maior de idade, marcada em "Quem aparece" e as quatro declarações do envio do vídeo. Só o administrador marca
-- (radar_pessoas_adm); a mudança vai para a trilha como as datas do termo (radar_fn_auditar: não é nome).
alter table public.radar_pessoas add column if not exists socio boolean not null default false;

-- v0.21.0: a Pauta (uma peça por dia do calendário de publicações). Assunto, objetivo, observação e "quem aparece" são do plano
-- (referência: não vão ao ar nem à trilha). O que vai ao ar é o que o administrador aprova (radar_pauta_aprovar): a peça aprovada
-- não se edita (radar_fn_pauta_peca). "Publicada" não é situação gravada: sai dos envios (radar_redes_envios) e do registro manual.
create table if not exists public.radar_pauta_pecas (
  id                 bigint generated always as identity primary key,
  data               date     not null unique,
  hora               time     not null default '09:30',                      -- hora de Brasília
  tipo               text     not null check (tipo in ('noticia','reel','quem_cuida','agenda','bastidor','educativo','captacao','data_equipe','sem_post')),
  formato            text     not null check (formato in ('imagem','foto','carrossel','carrossel_fotos','reel','story','nenhum')),
  assunto            text     not null default '' check (length(assunto) <= 1000),
  quem_aparece       text     not null default '' check (length(quem_aparece) <= 300),
  objetivo           text     not null default '' check (length(objetivo) <= 200),
  observacao         text     not null default '' check (length(observacao) <= 1000),
  situacao           text     not null default 'planejada' check (situacao in ('planejada','em_producao','pronta','aprovada','cancelada')),
  pessoas            bigint[] not null default '{}' check (cardinality(pessoas) <= 12),   -- radar_pessoas.id
  fotos              bigint[] not null default '{}' check (cardinality(fotos) <= 10),     -- radar_imagens.id, na ordem
  -- [{informacao, fonte}] (quem confere cada item é radar_pauta_problemas)
  conferidas         jsonb    not null default '[]' check (case when jsonb_typeof(conferidas) = 'array'
                                                                then jsonb_array_length(conferidas) <= 20 and length(conferidas::text) <= 12000 else false end),
  chamada            text     not null default '' check (length(chamada) <= 120),
  apoio              text     not null default '' check (length(apoio) <= 200),
  cartoes            jsonb    not null default '[]' check (case when jsonb_typeof(cartoes) = 'array'          -- [{titulo, texto}]
                                                              then jsonb_array_length(cartoes) <= 9 and length(cartoes::text) <= 6000 else false end),
  roteiro            text     not null default '' check (length(roteiro) <= 6000),                     -- reel (colado à mão)
  legenda_instagram  text     not null default '' check (length(legenda_instagram) <= 2200),
  legenda_facebook   text     not null default '' check (length(legenda_facebook) <= 2200),
  ia                 jsonb    not null default '{}' check (jsonb_typeof(ia) = 'object' and length(ia::text) <= 30000),   -- só sugestão
  versao_publicavel  timestamptz not null default now(),        -- muda só quando muda o que vai ao ar (gatilho)
  aprovado_por       uuid references auth.users(id) on delete set null,
  aprovado_em        timestamptz,
  aprovado_modo      text check (aprovado_modo in ('agendar','manual')),
  aprovado_conferencias text[] not null default '{}' check (aprovado_conferencias <@ array['pessoas','datas','rede','video','viu']::text[]),
  aprovado_canais    text[]   not null default '{}' check (aprovado_canais <@ array['instagram','facebook']::text[]),  -- os canais aprovados
  -- a aprovação à mão foi desfeita (a peça pode ter sido postada à mão sem o link registrado): a próxima aprovação pede a caixa
  -- "Conferi no Instagram e no Facebook: não saiu" (radar_pauta_aprovar), para nunca sair duas vezes
  manual_desfeita_em timestamptz,
  artes              bigint[] not null default '{}' check (cardinality(artes) <= 10),   -- radar_imagens.id das lâminas APROVADAS
  arte_identificacao text check (length(arte_identificacao) <= 300),                    -- a linha legal desenhada nas lâminas
  link_instagram     text check (link_instagram is null or (link_instagram ~ '^https://[!-~]+$' and length(link_instagram) <= 500)),
  link_facebook      text check (link_facebook  is null or (link_facebook  ~ '^https://[!-~]+$' and length(link_facebook)  <= 500)),
  publicado_manual_em  date,
  publicado_manual_por uuid references auth.users(id) on delete set null,
  criado_por         uuid references auth.users(id) on delete set null,
  criado_em          timestamptz not null default now(),
  atualizado_em      timestamptz not null default now()
);

-- v0.22.0: as gravações dos reels e o resultado do corretor de vídeo (uma linha por envio da equipe; "versao" conta os envios da peça).
-- Os arquivos ficam no bucket PRIVADO radar-videos, em caminhos que saem só do id (nada de nome): bruto/<id>/<n> (os clipes, na ordem),
-- trabalho/<id>/<tentativa>/palavras.json (a transcrição, que o robô grava; vale a de palavras_tentativa), corrigido/<id>/<sha256>.mp4 e
-- quadros/<id>/<sha256>/qK.jpg (o caminho nunca se sobrescreve: o que o administrador vê e aprova é o que vai ao ar). Ninguém grava aqui
-- direto: só as funções radar_video_* (a tela, o robô pela função radar-video e a limpeza). A fala para conferência, o relatório (que
-- tem a fala transcrita), os ajustes e as linhas da cartela (com o nome na peça e o CRC) não vão à trilha (radar_fn_auditar) e são
-- limpos nos prazos de radar_video_limpeza ("textos" em arquivos_apagados).
--   aguardando_envio → na_fila (radar_video_enviado) → processando (radar_video_pegar) → pronto | regravar | erro (radar_video_concluir,
--   radar_video_falhar); pronto | regravar | erro → na_fila (radar_video_ajustar, radar_video_reconferir, radar_video_de_novo);
--   o envio novo da mesma peça deixa o anterior "substituido" só quando os clipes dele chegam (radar_video_enviado): até lá, o
--   vídeo vivo continua valendo, ao lado do envio que espera os arquivos; "descartado" pela tela ou pela limpeza (envio abandonado).
create table if not exists public.radar_videos (
  id             uuid     primary key default gen_random_uuid(),
  peca_id        bigint   not null references public.radar_pauta_pecas(id) on delete restrict,
  versao         smallint not null default 1 check (versao between 1 and 50),
  situacao       text     not null default 'aguardando_envio' check (situacao in
                 ('aguardando_envio','na_fila','processando','pronto','regravar','erro','substituido','descartado')),
  modo           text     not null default 'completo' check (modo in ('completo','montagem')),   -- montagem: sem transcrever de novo
  -- [{n, tipo, bytes}]: os clipes declarados pela tela, na ordem (radar_video_criar confere a forma)
  partes         jsonb    not null check (jsonb_typeof(partes) = 'array' and jsonb_array_length(partes) between 1 and 12),
  fala_pessoa    bigint   not null,                                           -- radar_pessoas.id de quem fala (marcada na peça)
  -- quem estava marcada na peça no envio e quando os clipes chegaram (radar_video_criar e radar_video_enviado): quem pode estar no
  -- vídeo. Desmarcar a pessoa na peça depois não a tira do vídeo: as travas (radar_video_pessoas_falta) e a limpeza da revogação
  -- continuam olhando para ela
  pessoas        bigint[] not null default '{}',
  fala_roteiro   text     not null default '' check (length(fala_roteiro) <= 6000),  -- a fala para conferência (está no roteiro)
  roteiro_hash   text     not null,                                           -- radar_hash_texto(roteiro da peça) no envio
  cartela_linhas text[]   not null default '{}' check (cardinality(cartela_linhas) <= 4),  -- identificação legal e a linha de quem fala
  gancho         text     check (length(gancho) <= 120),                      -- cópia da chamada da peça, se escolhido
  declaracoes    text[]   not null check (declaracoes <@ array['so_marcadas','sem_fundo','so_voz','fala_confere']::text[]
                                          and declaracoes @> array['so_marcadas','sem_fundo','so_voz','fala_confere']::text[]),
  ajustes        jsonb    not null default '{}' check (jsonb_typeof(ajustes) = 'object' and length(ajustes::text) <= 20000),
  tentativas     smallint not null default 0 check (tentativas between 0 and 5),        -- as do pedido atual (até 3; o ajuste zera)
  rodada         smallint not null default 0 check (rodada between 0 and 200),           -- cada vez que o robô pega: o <t> de trabalho/<id>/<t>/
  fila_em        timestamptz,                                                 -- entrou (ou voltou) na fila: a reserva da agenda olha aqui
  pego_em        timestamptz,
  -- quantas vezes a reserva da agenda acionou o robô com o pedido esperando, desde que ele entrou na fila (radar_video_reserva: no
  -- 3º sem o robô pegar, vira erro "robo_nao_pegou"); volta a 0 quando o robô pega ou o pedido volta à fila
  reservas       smallint not null default 0 check (reservas between 0 and 100),
  palavras_tentativa smallint,                                                -- qual trabalho/<id>/<t>/palavras.json vale
  segundos_audio numeric(7,1) check (segundos_audio between 0 and 3600),      -- áudio transcrito deste envio (soma; a cota do mês)
  audio_rodada   smallint,                                                    -- a rodada cujo áudio já entrou na soma (uma vez por rodada)
  transcrito_em  timestamptz,
  sha256         text     check (sha256 ~ '^[0-9a-f]{64}$'),
  bytes          bigint   check (bytes between 1 and 314572800),
  duracao_final  numeric(6,2) check (duracao_final between 0 and 600),
  antigos        boolean  not null default false,                             -- há versões antigas de corrigido/ e quadros/ a apagar
  relatorio      jsonb    not null default '{}' check (jsonb_typeof(relatorio) = 'object' and length(relatorio::text) <= 60000),
  erro_codigo    text     check (erro_codigo ~ '^[a-z_]{3,40}$'),
  enviado_por    uuid     references auth.users(id) on delete set null,
  enviado_em     timestamptz,
  encerrado_em   timestamptz,                                                 -- virou substituido ou descartado
  apagado_aparelho_em  timestamptz,               -- "Apaguei do celular e da nuvem pessoal" (termo: apagar no mesmo dia)
  apagado_aparelho_por uuid references auth.users(id) on delete set null,
  arquivos_apagados text[] not null default '{}' check (arquivos_apagados <@ array['bruto','trabalho','corrigido','textos']::text[]),
  criado_em      timestamptz not null default now(),
  atualizado_em  timestamptz not null default now(),
  -- a fala e a cartela só ficam vazias depois da limpeza dos textos
  constraint radar_videos_textos check ('textos' = any(arquivos_apagados) or (length(fala_roteiro) >= 20 and cardinality(cartela_linhas) >= 1))
);
create unique index if not exists radar_videos_peca_versao_uk on public.radar_videos (peca_id, versao);
-- um vídeo "vivo" por peça (o envio que chega deixa o anterior substituido) e, ao lado dele, no máximo um envio esperando os arquivos
-- (o vivo só sai quando os clipes do novo chegam: o envio abandonado, ou que falhou no meio, não leva o vídeo bom junto)
drop index if exists public.radar_videos_peca_ativo_uk;
create unique index if not exists radar_videos_peca_vivo_uk on public.radar_videos (peca_id)
  where situacao in ('na_fila','processando','pronto','regravar','erro');
create unique index if not exists radar_videos_peca_envio_uk on public.radar_videos (peca_id) where situacao = 'aguardando_envio';
create index if not exists radar_videos_fila_idx on public.radar_videos (fila_em) where situacao = 'na_fila';

-- v0.22.0: quem viu a prévia ou baixou o vídeo (o link assinado sai só pela função radar-video, com prazo fixo) e quem, depois de
-- postar, apagou do aparelho o vídeo aprovado que baixou ("apagou"). Não vai à trilha: já é o registro. Lê só o administrador.
create table if not exists public.radar_video_acessos (
  id        bigint generated always as identity primary key,
  video_id  uuid not null references public.radar_videos(id) on delete cascade,
  usuario   uuid references auth.users(id) on delete set null,
  acao      text not null check (acao in ('previa','baixar','apagou')),
  em        timestamptz not null default now()
);
create index if not exists radar_video_acessos_video_idx on public.radar_video_acessos (video_id, em desc);

-- v0.22.0: a peça reel aprovada fica amarrada ao vídeo que o administrador viu (só radar_pauta_aprovar grava; desaprovar zera). As
-- caixas novas da aprovação: "video" (Conferi o vídeo: só as pessoas marcadas, sem tela, documento ou cliente ao fundo, só a voz) e
-- "viu" (A pessoa viu o vídeo final, quando alguma pessoa marcada pediu no termo).
alter table public.radar_pauta_pecas add column if not exists video_id     uuid references public.radar_videos(id) on delete restrict;
alter table public.radar_pauta_pecas add column if not exists video_sha256 text check (video_sha256 ~ '^[0-9a-f]{64}$');
do $$
begin
  if not exists (select 1 from pg_constraint where conrelid = 'public.radar_pauta_pecas'::regclass
                  and conname = 'radar_pauta_pecas_aprovado_conferencias_check' and pg_get_constraintdef(oid) like '%viu%') then
    alter table public.radar_pauta_pecas drop constraint if exists radar_pauta_pecas_aprovado_conferencias_check;
    alter table public.radar_pauta_pecas add constraint radar_pauta_pecas_aprovado_conferencias_check
      check (aprovado_conferencias <@ array['pessoas','datas','rede','video','viu']::text[]);
  end if;
end $$;

-- v0.21.0: a peça da Pauta sai pelo mesmo radar_redes_envios da notícia (a máquina de estados, o "concluir", a exclusão e a trilha
-- são os mesmos). Na linha da peça: peca_id no lugar de conteudo_id; agendado_para = a hora marcada (nula na notícia, que sai na
-- hora); disparos e disparado_em = as chamadas da agenda do banco (radar_agenda_vencidas); conteudo_lido_em = a versao_publicavel
-- aprovada; imagem = a cópia da arte aprovada (o "concluir" apaga depois que vai ao armazenamento); imagem_url = o endereço INTERNO
-- do armazenamento privado (radar-pauta), que não abre sem a chave. "Agendada" = autorizado com agendado_para no futuro.
alter table public.radar_redes_envios alter column conteudo_id drop not null;
alter table public.radar_redes_envios add column if not exists peca_id       bigint references public.radar_pauta_pecas(id) on delete restrict;
alter table public.radar_redes_envios add column if not exists agendado_para timestamptz;            -- nulo na notícia
alter table public.radar_redes_envios add column if not exists disparos      int not null default 0 check (disparos between 0 and 100);
alter table public.radar_redes_envios add column if not exists disparado_em  timestamptz;
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'radar_redes_envios_origem_ck') then
    alter table public.radar_redes_envios add constraint radar_redes_envios_origem_ck
      check (num_nonnulls(conteudo_id, peca_id) = 1) not valid;                                -- ou da notícia, ou da peça
  end if;
  if not exists (select 1 from pg_constraint where conname = 'radar_redes_envios_peca_ck') then
    alter table public.radar_redes_envios add constraint radar_redes_envios_peca_ck
      check (peca_id is null or (agendado_para is not null and not junto_com_site)) not valid;  -- a peça tem hora e nunca espera o site
  end if;
end $$;
create index if not exists radar_redes_envios_peca_idx on public.radar_redes_envios (peca_id) where peca_id is not null;
-- uma em aberto (ou feita) por peça e canal; o índice da notícia (conteudo_id, canal) não alcança a peça (nulos são distintos)
create unique index if not exists radar_redes_envios_peca_uk on public.radar_redes_envios (peca_id, canal)
  where peca_id is not null and situacao in ('autorizado','enviando','erro','publicado','dispensado');
create index if not exists radar_redes_envios_agenda_idx on public.radar_redes_envios (agendado_para)
  where situacao = 'autorizado' and peca_id is not null;

-- v0.17.0: exclusão da notícia no site, a pedido do administrador. O robô (workflow "Radar — publicar no site") entra no
-- painel do site, acha a notícia pelo título na lista do painel, exclui do jeito do botão "Excluir" do painel e confere
-- que ela saiu. Só então o registro em "Publicações no site" é retirado (a cópia fica aqui e na auditoria).
create table if not exists public.radar_site_exclusoes (
  id             bigint generated always as identity primary key,
  conteudo_id    bigint      not null references public.radar_conteudos(id) on delete restrict,
  url            text        not null check (url ~ '^https?://[!-~]+$' and length(url) <= 500),
  titulo         text        not null check (length(titulo) between 1 and 500),   -- o título que está no site
  situacao       text        not null default 'pedido'
                 check (situacao in ('pedido','excluindo','excluido','erro','cancelado')),
  pedido_por     uuid        references auth.users(id) on delete set null,
  pedido_em      timestamptz not null default now(),
  cancelado_por  uuid        references auth.users(id) on delete set null,
  cancelado_em   timestamptz,
  iniciado_em    timestamptz,
  excluido_em    timestamptz,
  erro           text        check (length(erro) <= 1000),
  atualizado_em  timestamptz not null default now()
);
create index if not exists radar_site_exclusoes_conteudo_idx on public.radar_site_exclusoes (conteudo_id);
-- um pedido em aberto por conteúdo
create unique index if not exists radar_site_exclusoes_aberta_uk on public.radar_site_exclusoes (conteudo_id)
  where situacao in ('pedido','excluindo');

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

-- v0.29.0: lembretes antes do dia. Uma linha por pendência ("episódio": a peça de amanhã ainda não aprovada, a peça pronta esperando a
-- aprovação, o vídeo do reel que o corretor terminou, a notícia que não saiu). O que vai ao e-mail é só o que está em "ref" (número,
-- data, hora, formato, situação, canal e desde quando): nunca nome, assunto, legenda, erro ou texto do boletim (o aviso é público).
-- Só as funções radar_lembretes_* gravam; o administrador lê (a situação, em Configurações). A pendência resolvida ganha resolvido_em
-- e sai sozinha depois de 90 dias.
create table if not exists public.radar_lembretes (
  id           bigint generated always as identity primary key,
  tipo         text        not null check (tipo in ('pauta','aprovacao','video','noticia')),
  chave        text        not null check (chave ~ '^[a-z]+(:[0-9a-z_-]+){1,4}$' and length(chave) <= 120),
  ref          jsonb       not null default '{}' check (jsonb_typeof(ref) = 'object' and length(ref::text) <= 1000),
  aberto_em    timestamptz not null default now(),   -- desde quando a pendência existe (a peça pronta: desde quando está pronta)
  acionado_em  timestamptz,                          -- último pedido da agenda ao GitHub (no máximo 1 a cada 30 minutos)
  lote         uuid,                                 -- reservada pelo robô dos lembretes (até ele confirmar o e-mail)
  avisado_em   timestamptz,                          -- foi para um e-mail: nunca mais é lembrada
  aviso        int         check (aviso > 0),        -- o número do aviso no GitHub
  resolvido_em timestamptz                           -- a condição sumiu (aprovada, cancelada, saiu, autorizada de novo…)
);
-- uma pendência aberta por tipo e chave (a mesma chave volta a abrir depois de resolvida: é um episódio novo)
create unique index if not exists radar_lembretes_aberta_uk on public.radar_lembretes (tipo, chave) where resolvido_em is null;
create index if not exists radar_lembretes_avisado_idx on public.radar_lembretes (tipo, avisado_em) where avisado_em is not null;

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
  -- v0.20.0: gravar o kit das redes (kit_ia) também não: a data é a versão do texto que foi visto e autorizado
  -- v0.24.0: nem a Conferência das Diretrizes (ela é presa à versão do texto, não à data)
  if tg_table_name = 'radar_conteudos'
     and (to_jsonb(new) - array['fora_do_site','kit_ia','conferencia']) = (to_jsonb(old) - array['fora_do_site','kit_ia','conferencia']) then
    new.atualizado_em := old.atualizado_em;
    return new;
  end if;
  -- v0.21.0: na peça da Pauta, gravar só a sugestão da IA (ia) também não muda a versão que a tela abriu
  if tg_table_name = 'radar_pauta_pecas' and (to_jsonb(new) - 'ia') = (to_jsonb(old) - 'ia') then
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
  -- v0.13.0: a imagem da publicação nas redes (até 3 MB) não vai para a trilha; ficam quem, quando, canal, legenda e link
  -- v0.21.0: a trilha nunca se apaga: da peça da Pauta não guarda o plano (assunto, objetivo, observação, quem aparece) nem a
  -- sugestão da IA, e da pessoa não guarda o nome, o nome na peça, a área nem o CRC. Ficam o que foi aprovado (datas, pessoas e
  -- fotos pelo número, informações conferidas, textos e legendas) e o termo (datas, canais, usos), com quem e quando
  v_tira text[] := case tg_table_name
                     when 'radar_redes_envios' then array['imagem']
                     when 'radar_pauta_pecas'  then array['ia','assunto','objetivo','observacao','quem_aparece']
                     when 'radar_pessoas'      then array['nome','nome_na_peca','crc','area']
                     -- v0.22.0: do vídeo, a fala (para conferência e transcrita, no relatório), os ajustes da legenda e a cartela (nome e
                     -- CRC de quem fala) ficam fora; ficam a situação, os clipes declarados, o hash e quem enviou
                     when 'radar_videos'       then array['relatorio','fala_roteiro','ajustes','cartela_linhas']
                     else array[]::text[] end;
begin
  if tg_op = 'DELETE' then v_reg := to_jsonb(old); else v_reg := to_jsonb(new); end if;
  -- atualização que só mexe nos campos de saúde/relógio (feita pelo próprio banco
  -- a cada execução do robô) não é decisão de ninguém: não entra na trilha
  if tg_op = 'UPDATE'
     and (to_jsonb(old) - array['ultimo_sucesso_em','ultima_falha_em','ultimo_erro','falhas_consecutivas','atualizado_em'])
       = (to_jsonb(new) - array['ultimo_sucesso_em','ultima_falha_em','ultimo_erro','falhas_consecutivas','atualizado_em']) then
    return new;
  end if;
  -- v0.21.0: nem a que só mexe no que não vai à trilha (o plano, a sugestão da IA, o nome, a cópia da imagem) ou nas marcas da
  -- agenda do banco (disparos, disparado_em, a cada 5 minutos); v0.22.0: nem as marcas do robô do vídeo (pego_em, tentativas, rodada,
  -- palavras_tentativa, fila_em) e da reserva da agenda (reservas, a cada 10 minutos)
  if tg_op = 'UPDATE' and tg_table_name in ('radar_redes_envios','radar_pauta_pecas','radar_pessoas','radar_videos')
     and (to_jsonb(old) - v_tira - array['atualizado_em','disparos','disparado_em','pego_em','tentativas','rodada','palavras_tentativa','fila_em','reservas'])
       = (to_jsonb(new) - v_tira - array['atualizado_em','disparos','disparado_em','pego_em','tentativas','rodada','palavras_tentativa','fila_em','reservas']) then
    return new;
  end if;
  insert into public.radar_auditoria (tabela, registro_id, acao, usuario, antes, depois)
  values (tg_table_name,
          coalesce(v_reg->>'id', v_reg->>'user_id', v_reg->>'slug', v_reg->>'chave', '?'),
          tg_op, auth.uid(),
          case when tg_op <> 'INSERT' then to_jsonb(old) - v_tira end,
          case when tg_op <> 'DELETE' then to_jsonb(new) - v_tira end);
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
  -- v0.16.0: a decisão da equipe "não é o mesmo fato" também fica (o robô regrava os metadados quando o texto muda)
  if old.metadados ? 'separada_em' and not (coalesce(new.metadados, '{}'::jsonb) ? 'separada_em') then
    new.metadados := coalesce(new.metadados, '{}'::jsonb) || jsonb_build_object('separada_em', old.metadados->'separada_em');
  end if;
  if old.metadados ? 'separada_de' and not (coalesce(new.metadados, '{}'::jsonb) ? 'separada_de') then
    new.metadados := coalesce(new.metadados, '{}'::jsonb) || jsonb_build_object('separada_de', old.metadados->'separada_de');
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

-- ---------------------------------------------------------------- fundamentação legal das capturas (v0.15.0)
-- Expressão que casa a palavra em maiúsculas ou minúsculas, com ou sem acento ("instrucao" casa "Instrução", "INSTRUÇÃO")
-- Feita sem upper()/lower() do banco: o resultado não depende da configuração de idioma do servidor.
create or replace function public.radar_rx_termo(p text) returns text
language sql immutable set search_path = public as $$
  select string_agg(case
           when ch = ' ' then '\s+'
           when ch = '-' then '[-\s]?'
           when ch = 'a' then '[aáàâãAÁÀÂÃ]'
           when ch = 'e' then '[eéêEÉÊ]'
           when ch = 'i' then '[iíIÍ]'
           when ch = 'o' then '[oóôõOÓÔÕ]'
           when ch = 'u' then '[uúüUÚÜ]'
           when ch = 'c' then '[cçCÇ]'
           when ch ~ '[a-z]' then '[' || ch || translate(ch, 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ') || ']'
           else ch end, '' order by n)
    from regexp_split_to_table(p, '') with ordinality as t(ch, n);
$$;

-- Minúsculas e sem acento, sem depender da configuração de idioma do servidor ("INSTRUÇÕES" → "instrucoes")
create or replace function public.radar_base_legal_chave(p text) returns text
language sql immutable set search_path = public as $$
  select lower(translate(coalesce(p, ''), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇáàâãäéèêëíìîïóòôõöúùûüç', 'AAAAAEEEEIIIIOOOOOUUUUCaaaaaeeeeiiiiooooouuuuc'));
$$;

-- Nome da norma como o Radar mostra ("instrucoes normativas" → "Instrução Normativa")
create or replace function public.radar_base_legal_tipo(p text) returns text
language sql immutable set search_path = public as $$
  with t as (select regexp_replace(public.radar_base_legal_chave(p), '[-\s]+', ' ', 'g') as k)
  select case
    when k ~ '^(leis? complementar(es)?|lcs?)$' then 'Lei Complementar'
    when k ~ '^(decretos? ?leis?|dls?|dec\.? ?leis?)$' then 'Decreto-Lei'
    when k ~ '^decretos? legislativos?$' then 'Decreto Legislativo'
    when k ~ '^decretos?$' then 'Decreto'
    when k ~ '^leis?$' then 'Lei'
    when k ~ '^(medidas? provisorias?|mpv?s?)$' then 'Medida Provisória'
    when k ~ '^(emendas? constituciona(l|is)|ecs?)$' then 'Emenda Constitucional'
    when k ~ '^(instruc(ao|oes) normativas?|ins?)$' then 'Instrução Normativa'
    when k ~ '^resoluc(ao|oes)$' then 'Resolução'
    when k ~ '^portarias?$' then 'Portaria'
    when k ~ '^soluc(ao|oes) de consulta$' then 'Solução de Consulta'
    when k ~ '^soluc(ao|oes) de divergencia$' then 'Solução de Divergência'
    when k ~ '^respostas? a consulta( tributaria)?$' then 'Resposta à Consulta Tributária'
    when k ~ '^atos? declaratorios?$' then 'Ato Declaratório'
    when k ~ '^atos? tecnicos? conjuntos?$' then 'Ato Técnico Conjunto'
    when k ~ '^atos? conjuntos?$' then 'Ato Conjunto'
    when k ~ '^edita(l|is) de transacao( por adesao)?$' then 'Edital de Transação'
    when k ~ '^(editais|edital)$' then 'Edital'
    when k ~ '^res\.$' then 'Resolução'
    when k ~ '^dec\.$' then 'Decreto'
    when k ~ '^port\.$' then 'Portaria'
    when k ~ '^parecer(es)? normativos?$' then 'Parecer Normativo'
    when k ~ '^convenios? icms$' then 'Convênio ICMS'
    when k ~ '^ajustes? sinief$' then 'Ajuste SINIEF'
    when k ~ '^protocolos? icms$' then 'Protocolo ICMS'
    when k ~ '^atos? cotepe$' then 'Ato COTEPE'
    when k ~ '^atos? diat$' then 'Ato DIAT'
    when k ~ '^sumulas?$' then 'Súmula'
  end from t;
$$;

-- Os nomes de norma, em qualquer caixa e com ou sem acento
create or replace function public.radar_base_legal_nomes_rx() returns text
language sql immutable set search_path = public as $$
  select (select string_agg(public.radar_rx_termo(x), '|' order by o) from unnest(array[
           'leis complementares', 'lei complementar', 'decretos-leis', 'decretos-lei', 'decreto-lei', 'decretos legislativos', 'decreto legislativo',
           'decretos', 'decreto', 'leis', 'lei', 'medidas provisorias', 'medida provisoria', 'emendas constitucionais', 'emenda constitucional',
           'instrucoes normativas', 'instrucao normativa', 'resolucoes', 'resolucao', 'portarias', 'portaria',
           'solucoes de consulta', 'solucao de consulta', 'solucoes de divergencia', 'solucao de divergencia',
           'respostas a consulta tributaria', 'resposta a consulta tributaria', 'respostas a consulta', 'resposta a consulta',
           'atos declaratorios', 'ato declaratorio', 'atos tecnicos conjuntos', 'ato tecnico conjunto', 'atos conjuntos', 'ato conjunto',
           'editais de transacao por adesao', 'edital de transacao por adesao', 'editais de transacao', 'edital de transacao',
           'editais', 'edital', 'pareceres normativos', 'parecer normativo',
           'convenios icms', 'convenio icms', 'ajustes sinief', 'ajuste sinief', 'protocolos icms', 'protocolo icms',
           'atos cotepe', 'ato cotepe', 'atos diat', 'ato diat', 'sumulas', 'sumula']) with ordinality as u(x, o))
      -- abreviaturas: "Res. Gecex nº 272", "Dec.-Lei nº 1.598", "Dec. nº 11.158", "Port. RFB nº 1"
      || '|[Rr]es\.|RES\.|[Dd]ec\.?\s*-\s*[Ll]ei|DEC\.?\s*-\s*LEI|[Dd]ec\.|DEC\.|[Pp]ort\.|PORT\.';
$$;

-- O ano de uma citação: "/2025", "/96", ", de 16 de janeiro de 2025" (também ", 16 de janeiro de 2025" e "de 27 de janeiro
-- 1992"), ", de 24/09/2026", ", de 05.07.2022", ", de 1996" e ", de 2002 e 2003, respectivamente" (esta não diz qual é de qual)
create or replace function public.radar_base_legal_ano_rx() returns text
language sql immutable set search_path = public as $$
  select '\s*/\s*(?:\d{4}|\d{2})(?![\d])(?![/.]\d)'                          -- "29/09/2026" logo depois do nome é data, não norma
      || '|\s*,?\s+[Dd][Ee]\s+\d{1,2}[º°o]?\s+[Dd][Ee]\s+[A-Za-zÇç]+\s+(?:[Dd][Ee]\s+)?\d{4}'
      || '|\s*,\s*\d{1,2}[º°o]?\s+[Dd][Ee]\s+[A-Za-zÇç]+\s+[Dd][Ee]\s+\d{4}'
      || '|\s*,?\s+[Dd][Ee]\s+\d{1,2}/\d{1,2}/\d{4}'
      || '|\s*,?\s+[Dd][Ee]\s+\d{1,2}[º°]?\.\d{1,2}\.(?:\d{4}|\d{2})(?![\d])'
      || '|\s*,?\s+[Dd][Ee]\s+(?:19|20)\d{2}(?:\s*(?:,|\s[eE])\s*(?:19|20)\d{2})*(?:,?\s*respectivamente)?(?![\d])';
$$;

-- O ano, com 4 dígitos, do trecho casado por radar_base_legal_ano_rx; null se não tem ou se tem mais de um ("de 2002 e 2003,
-- respectivamente"). Ano com 2 dígitos: até 30 é deste século ("/26" = 2026), depois é do passado ("/43" = 1943) — rever em 2030.
create or replace function public.radar_base_legal_ano(p text) returns text
language sql immutable set search_path = public as $$
  select case when p is null or regexp_count(p, '(?:19|20)\d{2}(?![\d])') > 1 then null
              else (select case when length(a) = 2 then case when a::int > 30 then '19' else '20' end || a else a end
                      from substring(p from '(\d{4}|\d{2})\D*$') a) end;
$$;

-- Apelido entre parênteses depois da norma ("(LGPD)", "(Lei Geral do Esporte)", "(DOU de 29/09/2026)"). O parêntese com
-- outra norma dentro ("(com a redação dada pela Lei nº 12.973/2014)") não é apelido: fica para a leitura seguinte.
create or replace function public.radar_base_legal_apelido_rx() returns text
language sql immutable set search_path = public as $$
  select '(?:\s*\((?![^()\n]*(?:' || public.radar_base_legal_nomes_rx() || '|(?:LC|MPV?|IN|EC|DL)(?![[:alnum:]]))'
      || '(?:\s+(?:(?:[Dd][aeo]s?|D[AEO]S?|[eE])\s+)?[A-Za-zÀ-ÿ/-]+){0,7}\s*(?:[Nn]\s?[º°oª.]|\d))[^()\n]{1,120}\))?';
$$;

-- Um número da lista que vem depois de um nome no plural, com o ano e o apelido
-- ("Leis nºs 14.596, de 14 de junho de 2023, 14.597, de 2023 (Lei Geral do Esporte), e 15.421"). Grupos: 1 o número; 2 o ano.
create or replace function public.radar_base_legal_lista_rx() returns text
language sql immutable set search_path = public as $$
  select '((?:\d{1,3}(?:\.\d{3})+|\d+)(?:-\d{1,2}(?![\d.]))?)(?![\dº°ª])(' || public.radar_base_legal_ano_rx() || ')?' || public.radar_base_legal_apelido_rx();
$$;

-- Expressão de uma citação de norma com número. Grupos: 1 o nome; 2 o órgão ou a qualificação ("RFB", "Executivo Coana",
-- "Conjunta RFB/PGFN", "do CGSN", "estadual", "da Procuradoria-Geral da Fazenda Nacional", o "/ICMS" de "Ato COTEPE/ICMS");
-- 3 o "nº"; 4 o número; 5 o ano; 6 os outros números da lista depois de um nome no plural ("Leis nºs 10.637/2002 e 10.833/2003").
create or replace function public.radar_base_legal_rx() returns text
language sql immutable set search_path = public as $$
  select '(?:^|[^[:alnum:]])(' || public.radar_base_legal_nomes_rx() || '|LCs|MPVs|MPs|INs|ECs|DLs|LC|MPV|MP|IN|EC|DL)'
      -- ponto solto antes do "nº" ("Decreto. nº 11.158") e sigla entre parênteses ("Lei Complementar (LC) nº 123",
      -- "Instrução Normativa (IN) RFB nº 2.229")
      || '(?:\.(?=\s*[Nn][º°]))?(?:\s*\([A-Z]{2,5}\))?'
      -- órgão ou qualificação: até 6 palavras com inicial maiúscula ou da lista em minúscula, com "do/da/de" entre elas. Não
      -- valem como órgão o "No"/"Número" (são o "nº"), o artigo ("A Portaria") e outro nome de norma ("Nova portaria A Portaria nº 5")
      || '((?:/[A-Z]{2,6})?(?:\s+(?:(?:[Dd][aeo]s?|D[AEO]S?|[eE])\s+)?'
      ||     '(?!(?:N[oOº°ª][sS]?|N[úÚuU]mero|NÚMERO|[AaOoEe]s?|[Dd][AaEeOo][sS]?|LC|MPV?|IN|EC|DL|' || public.radar_base_legal_nomes_rx()
      ||     ')(?![A-Za-zÀ-ÿ]))'
      ||     '(?:[A-ZÀ-Ý][A-Za-zÀ-ÿ0-9]*(?:[-/][A-Za-zÀ-ÿ0-9]+)*|estadual|federal|municipal|distrital|conjunta|interministerial)){0,6})'
      || '(?:\s*\([A-Z]{2,5}\))?\s*'
      || '([Nn](?:\.\s?|\s)?[º°ª][sS]?\.?\s*|[Nn](?:\.\s?)?[oO][sS]?\.?\s*|[Nn]\.\s*|[Nn][úu]mero\s+|NÚMERO\s+)?'
      -- o número (nunca ordinal: "no 1º dia"; nem o dia de uma data: "Portaria SEF 03.10.2026"), com a reedição da MP ("2.158-35")
      || '((?:\d{1,3}(?:\.\d{3})+|\d+)(?:-\d{1,2}(?![\d.]))?)(?![\dº°ª])(?![/.]\d{1,2}[/.](?:\d{4}|\d{2})(?!\d))'
      || '(' || public.radar_base_legal_ano_rx() || ')?'
      || public.radar_base_legal_apelido_rx()
      -- a lista do plural: os mesmos itens de radar_base_legal_lista_rx, aqui sem grupos
      || '((?:\s*(?:,\s*(?:[eE]\s+)?|\s[eE]\s+)(?:[Nn][º°oO][sS]?\.?\s*)?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:-\d{1,2}(?![\d.]))?(?![\dº°ª])'
      ||     '(?:' || public.radar_base_legal_ano_rx() || ')?' || public.radar_base_legal_apelido_rx() || ')*)';
$$;

-- A citação casada pela expressão é mesmo de uma norma? (m = os grupos de radar_base_legal_rx)
create or replace function public.radar_base_legal_valida(m text[], p_tipo text default null) returns boolean
language sql immutable set search_path = public as $$
  with x as (select coalesce(p_tipo, public.radar_base_legal_tipo(m[1])) as tipo,
                    length(replace(m[4], '.', '')) as dig, m[5] is not null as com_ano, coalesce(m[3], '') as no,
                    regexp_replace(btrim(regexp_replace(coalesce(m[2], ''), '\s+', ' ', 'g')), '^(?:[Dd][aeo]s?|D[AEO]S?)\s+', '') as qual)
  select tipo is not null
     and ltrim(replace(m[4], '.', ''), '0') <> ''
     -- sigla com número de 1 ou 2 dígitos só com o ano ou com "nº"/"n.": "MP 2", "MP Eleitoral 2" e "MP no 2º grau" não são norma
     and not (m[1] in ('LC','MP','MPV','IN','EC','DL','LCs','MPs','MPVs','INs','ECs','DLs') and dig < 3 and not com_ano
              and no !~ '[º°ª]|^[Nn]\.')
     -- "no"/"nos" do português: só depois do nome com maiúscula ("Lei no 9.430") e com 3 ou mais dígitos ou o ano
     -- ("as portarias nos 30 dias", "as instruções normativas nos 100 primeiros dias" não são norma)
     and not (no ~ '^[Nn][oO][sS]?\s*$' and ((dig < 3 and not com_ano) or m[1] !~ '^[A-ZÀ-Ý]'))
     -- "nos" no plural só com uma lista ("Leis nos 10.637 e 10.833"); "Portarias Nos 100 Primeiros Dias" não é norma
     and not (no ~ '^[Nn][oO][sS]\s*$' and coalesce(m[6], '') = '')
     -- "Edital" sozinho só o da transação tributária (PGFN, PGDAU, PGF, AGU, RFB); edital de concurso ou licitação não é norma
     and (tipo is distinct from 'Edital' or qual ~* '(^|[\s/])(pgfn|pgdau|pgf|agu|rfb)($|[\s/])')
     -- sem "nº" e sem ano, o número não pode ser um ano ("Lei do IRPF 2026") e só vale depois do nome sozinho (3 ou mais
     -- dígitos: "Lei 9.430") ou de um órgão conhecido ("Portaria MF 12"); "Lei Kandir 25 anos", "Decreto Altera 3 Regras" e
     -- "PORTARIA COM 12 NOVAS REGRAS" não são norma
     and (no <> '' or com_ano
          or (m[4] !~ '^(19|20)\d{2}$'
              and ((qual = '' and dig >= 3)
                   or (qual <> '' and (select bool_and(p ~ '/' or public.radar_base_legal_chave(p) ~ ('^(rfb|srf|mf|me|mte|mps|mtp|pgfn|cgsn|cgibs|'
                          || 'confaz|cotepe|sinief|icms|sefaz|sef|carf|cvm|bcb|bacen|cmn|inss|secex|gecex|camex|mdic|anpd|cosit|coana|cosar|sutri|'
                          || 'disit|cst|cfc|pge|federal|estadual|municipal|distrital|conjunta|interministerial|executivo|interpretativo|normativo)$'))
                                       from regexp_split_to_table(qual, ' ') p)))))
  from x;
$$;

-- Texto preparado para a leitura: Unicode composto (o acento separado da letra, comum em PDF, vira um só caractere),
-- espaço especial como espaço comum, e "projeto de lei", "proposta de emenda (à Constituição)", "minuta de instrução
-- normativa" ficam de fora (ainda não são norma)
create or replace function public.radar_base_legal_preparar(p text) returns text
language sql immutable set search_path = public as $$
  select regexp_replace(regexp_replace(translate(normalize(coalesce(p, ''), NFC), chr(160), ' '),
           '((?:[Pp]rojetos?|PROJETOS?|[Aa]nteprojetos?|ANTEPROJETOS?|[Pp]ropostas?|PROPOSTAS?|[Mm]inutas?|MINUTAS?)\s+(?:[Dd][EeAaOo]s?|D[EAO]S?)\s+)',
           '\1x', 'g'),
           '((?:[Ee]mendas?|EMENDAS?)\s+(?:[àaÀA]\s+)?)((?:[Cc]onstitui|CONSTITUI))', '\1x\2', 'g');
$$;

-- Leis e códigos citados só pelo nome, sem número: "Constituição Federal", "art. 195 da CF", "art. 150 da Constituição",
-- "CF/88", "CTN", "RIR/2018", "RICMS/SC", "Código Civil", "CLT"
create or replace function public.radar_base_legal_codigos_rx() returns text
language sql immutable set search_path = public as $$
  select '(?:^|[^[:alnum:]])('
      || (select string_agg(public.radar_rx_termo(x), '|' order by o) from unnest(array[
           'ato das disposicoes constitucionais transitorias', 'constituicao federal', 'constituicao da republica',
           'codigo tributario nacional', 'regulamento do imposto de renda', 'regulamento do icms',
           'codigo civil', 'consolidacao das leis do trabalho']) with ordinality as u(x, o))
      -- "da CF" (não o "CF-e", cupom fiscal) e "da Constituição" seguida de pontuação, "Federal", "de 1988" ou "da República"
      -- ("a Constituição de Empresas", "na Constituição Estadual" e "da Constituição de Santa Catarina" não são a Federal)
      || '|(?:[Dd][AaOo]|[Nn][AaOo]|[àÀ]|[aA]|[Pp][Ee][Ll][Aa])\s+CF(?![-/[:alnum:]])|CF(?=\s*,\s*[Aa][Rr][Tt])|(?<=,\s)CF(?=\s*\))'
      || '|(?:d[ao]|n[ao]|à|a|pela)\s+(?:Constitui[çc][ãa]o|CONSTITUI[ÇC][ÃA]O)'
      ||   '(?=\s*[.,;:)]|\s*$|\s+(?:[Ff]ederal|FEDERAL|[Dd][Ee]\s+1988|[Dd][Aa]\s+[Rr][Ee][Pp]|[-–—]))'
      || '|CF\s*/\s*(?:19)?88|CTN|ADCT|RIR\s*/\s*(?:\d{4}|\d{2})|RICMS(?:\s*[/-]\s*[A-Z]{2})?|CLT)(?![[:alnum:]])';
$$;

-- Chave do órgão para juntar a mesma norma escrita de jeitos diferentes: sem acento, em maiúsculas, sem o "do/da" do
-- começo, o nome por extenso trocado pela sigla ("Comitê Gestor do Simples Nacional" = "CGSN") e sem o ministério no fim
-- ("PGFN/MF" = "PGFN")
create or replace function public.radar_base_legal_orgao(p text) returns text
language sql immutable set search_path = public as $$
  select regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(
           upper(public.radar_base_legal_chave(regexp_replace(btrim(coalesce(p, '')), '^(?:[Dd][aeo]s?|D[AEO]S?)\s+', ''))),
           '^(SECRETARIA (ESPECIAL )?DA )?RECEITA FEDERAL( DO BRASIL)?$', 'RFB'),
           '^PROCURADORIA-GERAL DA FAZENDA NACIONAL$', 'PGFN'),
           '^COMITE GESTOR DO SIMPLES NACIONAL$', 'CGSN'),
           '^COMITE GESTOR DO (IBS|IMPOSTO SOBRE BENS E SERVICOS)$', 'CGIBS'),
           '^(MINISTERIO|MINISTRO( DE ESTADO)?) DA FAZENDA$', 'MF'),
           '^MINISTERIO DO TRABALHO E EMPREGO$', 'MTE'),
           '^([A-Z]+)/M[EF]$', '\1');
$$;

-- O órgão como o cartão mostra: o "DO/DA" do título em maiúsculas em minúscula e as palavras comuns com inicial maiúscula
-- ("PORTARIA CONJUNTA RFB/PGFN" → "Portaria Conjunta RFB/PGFN"); siglas ficam como estão
create or replace function public.radar_base_legal_orgao_exibir(p text) returns text
language sql immutable set search_path = public as $$
  select string_agg(case
           when w ~ '^(D[AEO]S?|E)$' then lower(w)
           when public.radar_base_legal_chave(w) ~ ('^(normativ[ao]s?|conjunt[ao]s?|executiv[ao]s?|interpretativ[ao]s?|tecnic[ao]s?|federal|'
                || 'estadual|municipal|distrital|interministerial|ministro|ministerio|estado|fazenda|secretaria|especial|receita|brasil|'
                || 'nacional|comite|gestor|simples|diretoria|colegiada|trabalho|emprego|imposto|sobre|bens|servicos|procuradoria-geral)$')
                and w !~ '[a-zà-ÿ]'
             then substr(w, 1, 1) || lower(translate(substr(w, 2), 'ÁÀÂÃÉÊÍÓÔÕÚÇ', 'áàâãéêíóôõúç'))
           else w end, ' ' order by n)
    from regexp_split_to_table(btrim(coalesce(p, '')), '\s+') with ordinality t(w, n);
$$;

-- Fundamentação legal citada no texto capturado: as normas (lei, lei complementar, decreto, instrução normativa,
-- resolução, portaria, solução de consulta, convênio ICMS...) e os códigos (Constituição, CTN, RIR, RICMS, CLT).
-- Devolve {"normas": [até 12, na ordem em que aparecem], "total": quantas, "ato": a norma que a captura é, quando o
-- título é a própria norma (ex.: "Solução de Consulta Cosit nº 190, de 30/09/2026"), senão null}.
-- É uma leitura do texto, não uma conferência: diz o que está citado, não se a citação está certa.
create or replace function public.radar_base_legal(p_titulo text, p_resumo text, p_texto text) returns jsonb
language plpgsql immutable set search_path = public as $$
declare
  v_rx    text := public.radar_base_legal_rx();
  v_lrx   text := public.radar_base_legal_lista_rx();
  v_tit   text := public.radar_base_legal_preparar(p_titulo);
  -- título, resumo e texto são lidos juntos, mas uma citação não passa de uma parte para outra (o ¶ separa). Do texto, só os
  -- primeiros 100 mil caracteres: a leitura roda dentro da gravação da captura e precisa caber no tempo-limite do Supabase
  v_txt   text := v_tit || E'\n¶\n' || public.radar_base_legal_preparar(p_resumo) || E'\n¶\n' || public.radar_base_legal_preparar(left(p_texto, 100000));
  v_fim   text := coalesce(nullif(btrim(p_texto), ''), p_resumo, '');
  v_lista jsonb;          -- [{nome, tipo, dig, ano}] uma por norma, na ordem da primeira citação
  v_saida text[];
  v_cod   text[] := '{}';
  v_nome  text;
  v_ato   text;
  m       text[];
begin
  with bruto as (
    select r.o, r.m, public.radar_base_legal_tipo(r.m[1]) as tipo from regexp_matches(v_txt, v_rx, 'g') with ordinality r(m, o)
  ), cit as (                                      -- cada número citado (no plural, também os da lista)
    select b.o, x.k, b.tipo,
           btrim(regexp_replace(coalesce(b.m[2], ''), '\s+', ' ', 'g')) as qual,
           -- o sufixo "-35" só é reedição na medida provisória; nas outras normas fica de fora
           case when b.tipo = 'Medida Provisória' then x.num else regexp_replace(x.num, '-\d{1,2}$', '') end as num,
           x.ano
      from bruto b
      cross join lateral (
        -- a lista com um ano só, no fim e por extenso ("Portarias SEF nºs 250 e 251, de 2026"): o ano vale para todos
        select y.k, y.num, coalesce(y.ano, case when y.anos = 1 and y.ult_ano is not null and y.ult_bruto !~ '^\s*/' then y.ult_ano end) as ano
          from (select z.*, count(z.ano) over () as anos,
                       last_value(z.ano) over (order by z.k rows between unbounded preceding and unbounded following) as ult_ano,
                       last_value(z.bruto) over (order by z.k rows between unbounded preceding and unbounded following) as ult_bruto
                  from (select 0::bigint as k, b.m[4] as num, b.m[5] as bruto, public.radar_base_legal_ano(b.m[5]) as ano
                        union all
                        select l.k, l.n[1], l.n[2], public.radar_base_legal_ano(l.n[2])
                          from regexp_matches(coalesce(b.m[6], ''), v_lrx, 'g') with ordinality l(n, k)
                         where public.radar_base_legal_chave(b.m[1]) ~ ('^(leis|decretos|medidas|emendas|instrucoes|resolucoes|portarias|'
                                 || 'solucoes|respostas|atos|pareceres|editais|convenios|ajustes|protocolos|sumulas|lcs|ins|mps|mpvs|ecs|dls)')
                           -- na lista, um ano solto ("de 2002 e 2003") ou uma quantidade sem ano ("e 12 outras") não é norma
                           and not (l.n[1] ~ '^(19|20)\d{2}$' and l.n[2] is null)
                           and not (length(replace(l.n[1], '.', '')) < 3 and length(replace(b.m[4], '.', '')) >= 3 and l.n[2] is null)) z) y
      ) x
     where public.radar_base_legal_valida(b.m, b.tipo)
  ), comchave as (
    -- "Edital de Transação PGFN/RFB nº 5/2026" e "Edital nº 5/2026" são a mesma norma
    select c.*, case when c.tipo = 'Edital de Transação' then 'Edital' else c.tipo end as tipo_g,
           ltrim(replace(c.num, '.', ''), '0') as dig, public.radar_base_legal_orgao(c.qual) as chave
      from cit c where ltrim(replace(regexp_replace(c.num, '-\d{1,2}$', ''), '.', ''), '0') <> ''
  ), chaves as (
    select c.tipo_g, c.dig, c.chave, coalesce(string_to_array(nullif(c.chave, ''), ' '), '{}') as partes, min(array[c.o, c.k]) as primeiro
      from comchave c group by c.tipo_g, c.dig, c.chave
  ), orgao as (
    -- a mesma norma citada com e sem o órgão ("IN RFB nº 2.229" e "IN nº 2.229"), ou com parte dele ("Ato Declaratório Coana"
    -- e "Ato Declaratório Executivo Coana", "Portaria RFB/PGFN" e "Portaria Conjunta RFB/PGFN") é uma só: fica com o órgão mais
    -- completo que contém o seu. Órgãos diferentes são normas diferentes (Portaria MF nº 12 e Portaria RFB nº 12)
    select distinct on (c.o, c.k) c.*, coalesce(k.chave, c.chave) as ck
      from comchave c
      left join chaves k on k.tipo_g = c.tipo_g and k.dig = c.dig and k.partes @> coalesce(string_to_array(nullif(c.chave, ''), ' '), '{}')
     order by c.o, c.k, cardinality(k.partes) desc nulls last, k.primeiro
  ), ano as (
    -- o ano separa as normas que recomeçam a numeração (Resolução CGIBS nº 1/2025 e nº 1/2026); a citação sem ano fica
    -- com a primeira que tem
    select c.*, coalesce(c.ano, first_value(c.ano) over (partition by c.tipo_g, c.dig, c.ck order by c.ano is null, c.o, c.k)) as ak
      from orgao c
  ), grupo as (
    select (array_agg(g.tipo order by length(g.tipo) desc, g.o, g.k))[1] as tipo, g.dig, g.ak, min(array[g.o, g.k]) as primeiro,
           -- "Atos Declaratórios Executivos Corat" → "Ato Declaratório Executivo Corat"
           regexp_replace(public.radar_base_legal_orgao_exibir(
                            coalesce((array_agg(g.qual order by cardinality(string_to_array(nullif(g.chave, ''), ' ')) desc nulls last, g.o, g.k)
                                        filter (where g.chave = g.ck))[1], '')),
                          '(Executiv|Interpretativ|Normativ|T[ée]cnic|Conjunt)([oa])s(?![[:alpha:]])', '\1\2', 'g') as qual,
           (array_agg(g.num order by g.num like '%.%' desc, g.o, g.k))[1] as num       -- "2.342" antes de "2342"
      from ano g
     group by g.tipo_g, g.dig, g.ck, g.ak
  )
  select coalesce(jsonb_agg(jsonb_build_object(
           'nome', g.tipo || case when g.qual ~ '^/' then g.qual when g.qual <> '' then ' ' || g.qual else '' end
                   || ' nº ' || g.num || coalesce('/' || g.ak, ''),
           'tipo', g.tipo, 'dig', g.dig, 'ano', g.ak) order by g.primeiro), '[]'::jsonb)
    into v_lista
    from grupo g;
  select coalesce(array_agg(j->>'nome' order by o), '{}') into v_saida from jsonb_array_elements(v_lista) with ordinality e(j, o);
  -- a captura é o próprio ato: o título é a norma, sozinha ou seguida de " - " e da ementa ("– Altera…", "– Dispõe…");
  -- "Lei nº 15.270/2025: o que muda" e "Lei nº 15.270/2025 – entenda" são notícias sobre a lei, não a lei
  m := regexp_match(v_tit, '^\s*' || substr(v_rx, length('(?:^|[^[:alnum:]])') + 1) || '\s*(?:\([^()]*\))?\s*\.?\s*(?:$|[-–—]\s+(?:'
       || (select string_agg(public.radar_rx_termo(x), '|') from unnest(array['dispoe', 'altera', 'aprova', 'institui', 'estabelece',
            'prorroga', 'regulamenta', 'divulga', 'disciplina', 'define', 'fixa', 'revoga', 'torna', 'autoriza', 'retifica', 'reduz',
            'concede', 'homologa', 'habilita', 'cancela', 'designa', 'dispensa', 'suspende', 'acrescenta', 'consolida']) x) || '))');
  if m is not null and public.radar_base_legal_valida(m) then
    select j->>'nome' into v_ato
      from jsonb_array_elements(v_lista) with ordinality e(j, o)
     where (case when j->>'tipo' = 'Edital de Transação' then 'Edital' else j->>'tipo' end)
             = (case when public.radar_base_legal_tipo(m[1]) = 'Edital de Transação' then 'Edital' else public.radar_base_legal_tipo(m[1]) end)
       and j->>'dig' = ltrim(replace(m[4], '.', ''), '0')
     order by o limit 1;
  end if;
  -- códigos citados pelo nome (o mesmo código escrito de dois jeitos conta uma vez: "RIR/18" = "RIR/2018")
  for m in select regexp_matches(v_txt, public.radar_base_legal_codigos_rx(), 'g') loop
    v_nome := case
      when m[1] ~ '^ADCT' or public.radar_base_legal_chave(m[1]) ~ '^ato das disposicoes' then 'Ato das Disposições Constitucionais Transitórias (ADCT)'
      when public.radar_base_legal_chave(m[1]) ~ '(^|\s)(constituicao|cf)' or m[1] = 'CF' then 'Constituição Federal'
      when public.radar_base_legal_chave(m[1]) ~ '^(codigo tributario|ctn)' then 'Código Tributário Nacional (CTN)'
      when m[1] ~ '^RIR' then 'Regulamento do Imposto de Renda (RIR/' || public.radar_base_legal_ano(m[1]) || ')'
      when public.radar_base_legal_chave(m[1]) ~ '^regulamento do icms' then 'RICMS'
      when public.radar_base_legal_chave(m[1]) ~ '^regulamento' then 'Regulamento do Imposto de Renda'
      when m[1] ~ '^RICMS' then 'RICMS' || coalesce('/' || substring(m[1] from '[/-]\s*([A-Z]{2})$'), '')
      when public.radar_base_legal_chave(m[1]) ~ '^codigo civil' then 'Código Civil'
      else 'Consolidação das Leis do Trabalho (CLT)' end;
    -- o código que já está na lista pela lei que o criou não entra de novo ("Lei nº 5.172/1966 (Código Tributário Nacional)")
    continue when exists (select 1 from jsonb_array_elements(v_lista) j
                           where (j->>'tipo') || '|' || (j->>'dig') = case v_nome
                                   when 'Código Tributário Nacional (CTN)' then 'Lei|5172'
                                   when 'Consolidação das Leis do Trabalho (CLT)' then 'Decreto-Lei|5452'
                                   when 'Código Civil' then 'Lei|10406'
                                   when 'Regulamento do Imposto de Renda (RIR/2018)' then 'Decreto|9580'
                                   when 'Regulamento do Imposto de Renda (RIR/1999)' then 'Decreto|3000' end
                              or (v_nome in ('Regulamento do Imposto de Renda') and (j->>'tipo') || '|' || (j->>'dig') in ('Decreto|9580', 'Decreto|3000'))
                              or (v_nome in ('RICMS', 'RICMS/SC') and (j->>'tipo') || '|' || (j->>'dig') || '|' || coalesce(j->>'ano', '') = 'Decreto|2870|2001'));
    if not v_nome = any(v_cod) then v_cod := v_cod || v_nome; end if;
  end loop;
  -- o nome genérico some quando o mesmo código aparece com o estado ou o ano ("Regulamento do ICMS (RICMS/SC)")
  if exists (select 1 from unnest(v_cod) c where c like 'RICMS/%') then v_cod := array_remove(v_cod, 'RICMS'); end if;
  if exists (select 1 from unnest(v_cod) c where c like 'Regulamento do Imposto de Renda (%') then
    v_cod := array_remove(v_cod, 'Regulamento do Imposto de Renda');
  end if;
  -- com mais de 12, os códigos (a Constituição, o CTN...) não ficam escondidos no "e mais": entram no fim das 12
  return jsonb_build_object('normas', to_jsonb(coalesce(v_saida[1:12 - least(coalesce(array_length(v_cod, 1), 0), 12)] || v_cod, '{}')),
                            'total', coalesce(array_length(v_saida, 1), 0) + coalesce(array_length(v_cod, 1), 0),
                            'ato', v_ato)
         -- o texto capturado termina em "..." (resumo cortado, como o do boletim da ITC): a norma pode estar no restante. O "…"
         -- do fim de um endereço encurtado ("Acesse: https://www.gov.br/…/programas…") não conta
         || case when v_fim ~* '(\.\.\.|…|\[(…|\.\.\.)\]|leia mais:?)\s*$' and v_fim !~* '(https?://|www\.)\S*(\.\.\.|…)\s*$'
                 then '{"cortado": true}'::jsonb else '{}'::jsonb end;
end $$;

-- Captura gravada como texto parcial (metadados.texto_parcial: o boletim da ITC, que traz só o começo da matéria) que não
-- cita norma fica como "cortado": a norma pode estar no restante
create or replace function public.radar_base_legal_parcial(p_base jsonb, p_metadados jsonb) returns jsonb
language sql immutable set search_path = public as $$
  select p_base || case when coalesce(p_metadados->>'texto_parcial', '') = 'true' and coalesce((p_base->>'total')::int, 0) = 0
                        then '{"cortado": true}'::jsonb else '{}'::jsonb end;
$$;

-- A fundamentação legal da captura é sempre calculada pelo banco (ninguém marca à mão): na entrada e quando o título,
-- o resumo ou o texto mudam. A captura que o robô só reconfere, sem mudança, não é lida de novo.
create or replace function public.radar_fn_captura_base_legal() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if coalesce(current_setting('radar.base_legal', true), '') = '1' then
    return new;                          -- recálculo geral em curso (radar_recalcular_base_legal)
  end if;
  if tg_op = 'INSERT' or old.base_legal is null or new.titulo is distinct from old.titulo
     or new.resumo_fonte is distinct from old.resumo_fonte or new.texto is distinct from old.texto
     or (new.metadados->>'texto_parcial') is distinct from (old.metadados->>'texto_parcial') then
    new.base_legal := public.radar_base_legal_parcial(public.radar_base_legal(new.titulo, new.resumo_fonte, new.texto), new.metadados);
  else
    new.base_legal := old.base_legal;
  end if;
  return new;
end $$;

-- Lê de novo a fundamentação legal de todas as capturas (na instalação e quando a leitura das normas melhora).
-- Devolve quantas mudaram.
create or replace function public.radar_recalcular_base_legal() returns int
language plpgsql security definer set search_path = public as $$
declare v_n int;
begin
  perform set_config('radar.base_legal', '1', true);        -- só nesta transação: deixa o gatilho aceitar o valor recalculado
  update public.radar_capturas c
     set base_legal = x.b
    from (select k.id, public.radar_base_legal_parcial(public.radar_base_legal(k.titulo, k.resumo_fonte, k.texto), k.metadados) as b
            from public.radar_capturas k) x
   where x.id = c.id and c.base_legal is distinct from x.b;
  get diagnostics v_n = row_count;
  perform set_config('radar.base_legal', '', true);
  return v_n;
end $$;

-- Imagem trocada ou conteúdo apagado: a imagem que ninguém mais usa é removida (v0.6.0 — todo conteúdo nasce com capa,
-- e cada capa refeita deixaria uma imagem sem uso no banco)
create or replace function public.radar_fn_imagem_sem_uso() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  -- v0.16.0: vale também para a ilustração guardada (ilustracao_id)
  -- v0.21.0: a foto ou a lâmina aprovada de uma peça da Pauta nunca é apagada por aqui
  delete from public.radar_imagens i
   where i.id in (old.imagem_id, old.ilustracao_id)
     and (tg_op = 'DELETE' or (i.id is distinct from new.imagem_id and i.id is distinct from new.ilustracao_id))
     and not exists (select 1 from public.radar_conteudos c where c.imagem_id = i.id or c.ilustracao_id = i.id)
     and not exists (select 1 from public.radar_pauta_pecas p where i.id = any(p.fotos) or i.id = any(p.artes));
  return null;
end $$;
drop trigger if exists radar_tg_imagem_sem_uso on public.radar_conteudos;
create trigger radar_tg_imagem_sem_uso after update of imagem_id, ilustracao_id or delete on public.radar_conteudos
  for each row execute function public.radar_fn_imagem_sem_uso();

-- v0.7.1: imagem que ficou sem uso por outro caminho (envio que falhou entre gravar a imagem e ligá-la ao conteúdo,
-- capas trocadas antes da v0.6.0) é apagada pelo robô ao fim de cada coleta. Só as com mais de p_horas (padrão 24):
-- uma imagem acabada de enviar, que a tela ainda vai ligar ao conteúdo, não é tocada. Devolve quantas apagou.
-- v0.21.0: as fotos e as lâminas aprovadas das peças da Pauta também ficam (sem isso, sumiriam um dia depois de enviadas)
create or replace function public.radar_limpar_imagens_sem_uso(p_horas int default 24) returns int
language plpgsql security definer set search_path = public as $$
declare v_n int;
begin
  delete from public.radar_imagens i
   where i.criado_em < now() - make_interval(hours => least(greatest(coalesce(p_horas, 24), 1), 8760))
     and not exists (select 1 from public.radar_conteudos c where c.imagem_id = i.id or c.ilustracao_id = i.id)
     and not exists (select 1 from public.radar_pauta_pecas p where i.id = any(p.fotos) or i.id = any(p.artes));
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

-- v0.16.0: os pontos a conferir de um conteúdo só crescem: a lista nova começa pela antiga e acrescenta até 10 textos
create or replace function public.radar_avisos_acrescimo(p_novo jsonb, p_antigo jsonb) returns boolean
language sql immutable set search_path = public as $$
  select jsonb_typeof(p_novo) = 'array' and jsonb_typeof(p_antigo) = 'array'
     and jsonb_array_length(p_novo) between jsonb_array_length(p_antigo) and jsonb_array_length(p_antigo) + 10
     and (select coalesce(jsonb_agg(e order by i), '[]'::jsonb) from jsonb_array_elements(p_novo) with ordinality t(e, i)
           where i <= jsonb_array_length(p_antigo)) = p_antigo
     and not exists (select 1 from jsonb_array_elements(p_novo) with ordinality t(e, i)
                      where i > jsonb_array_length(p_antigo) and (jsonb_typeof(e) <> 'string' or length(e #>> '{}') > 2000))
$$;

-- Aprovação: só pessoa (admin/editor); texto alterado depois de aprovado volta para revisão
create or replace function public.radar_fn_conteudo_aprovacao() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_marcas text;
begin
  if tg_op = 'UPDATE' and new.assunto_id is distinct from old.assunto_id then
    raise exception 'RADAR021: um conteúdo não pode ser transferido para outro assunto'
      using errcode = 'P0001';
  end if;

  if tg_op = 'UPDATE' then
    new.gerado_por := old.gerado_por;     -- a origem do texto não se reescreve
    new.modelo_ia  := old.modelo_ia;
    -- nem os pontos que a verificação mandou conferir. v0.16.0: só se pode ACRESCENTAR (a revisão com IA anota o que tirou do texto)
    if not coalesce(public.radar_avisos_acrescimo(new.avisos_ia, old.avisos_ia), false) then
      new.avisos_ia := old.avisos_ia;
    end if;
    -- v0.16.0: a autorização do trecho igual ao da fonte só muda pela função radar_autorizar_copia...
    if coalesce(current_setting('radar.autorizando_copia', true), '') <> '1' then
      new.copia_autorizada_em     := old.copia_autorizada_em;
      new.copia_autorizada_por    := public.radar_manter_usuario(old.copia_autorizada_por, new.copia_autorizada_por);
      new.copia_autorizada_motivo := old.copia_autorizada_motivo;
    end if;
    -- ... e cai quando o texto muda (vale para o texto que foi visto)
    if new.corpo is distinct from old.corpo then
      new.copia_autorizada_em := null; new.copia_autorizada_por := null; new.copia_autorizada_motivo := null;
    end if;
    -- v0.24.0: a Conferência das Diretrizes só muda pelas funções radar_registrar_conferencia e radar_assumir_conferencia (o texto
    -- mudou, ela continua guardada, mas não vale: é presa à versão do texto)
    if coalesce(current_setting('radar.conferindo', true), '') <> '1' then
      new.conferencia := old.conferencia;
    end if;
    -- v0.20.0: o texto mudou e o kit não veio junto: o kit fica marcado como desatualizado (as legendas e o roteiro saem do texto).
    -- Só o título mudar não marca (escolher outro título sugerido é o passo seguinte ao "Gerar com IA"): o kit guarda o título de
    -- quando foi feito, e a tela pede para conferir a chamada da arte
    if new.corpo is distinct from old.corpo
       and new.kit_ia is not distinct from old.kit_ia and new.kit_ia <> '{}'::jsonb then
      new.kit_ia := new.kit_ia || '{"desatualizado": true}'::jsonb;
      -- kit no limite de tamanho (só se escrito à mão): a marca não pode impedir a edição do texto
      if length(new.kit_ia::text) > 20000 then new.kit_ia := '{"desatualizado": true}'::jsonb; end if;
    end if;
  else
    new.copia_autorizada_em := null; new.copia_autorizada_por := null; new.copia_autorizada_motivo := null;
    new.conferencia := '{}'::jsonb;                    -- v0.24.0: o conteúdo novo nasce sem a Conferência das Diretrizes
    if new.gerado_por = 'humano' then
      new.modelo_ia := null;
      new.avisos_ia := '[]'::jsonb;
    end if;
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
    -- v0.14.3: ponto marcado com [VERIFICAR] não vai ao leitor
    v_marcas := public.radar_marcas_verificar(coalesce(new.titulo, '') || E'\n' || coalesce(new.corpo, ''));
    if v_marcas is not null then
      raise exception '%', v_marcas using errcode = 'P0001';
    end if;
    -- v0.22.0 (varredura geral): nem frase do boletim pago (a tela já não deixa; aqui vale para qualquer caminho)
    if public.radar_copia_paga_assunto(new.assunto_id, array[new.titulo, new.corpo]) then
      raise exception 'RADAR146: frase do boletim pago (ITC) no texto: reescreva com palavras próprias antes de aprovar (o boletim pago nunca é reproduzido, nem citando a fonte nem entre aspas)' using errcode = 'P0001';
    end if;
    if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
      raise exception 'RADAR020: a aprovação exige um usuário com perfil de editor ou administrador (o robô e a IA não aprovam)'
        using errcode = 'P0001';
    end if;
    -- v0.24.0: o texto INFORMATIVO (sem fundamentação legal específica) só é aprovado depois que o administrador autoriza a
    -- publicação do assunto ("Autorizar a publicação do Informativo", o mesmo "Publicar mesmo assim", com o motivo)
    if coalesce(new.avisos_ia->>0, '') like 'INFORMATIVO%'
       and not exists (select 1 from public.radar_assuntos a where a.id = new.assunto_id and a.liberado_sem_base_em is not null) then
      raise exception 'RADAR180: texto Informativo (sem fundamentação legal específica) só é aprovado depois que o administrador autoriza a publicação (“Autorizar a publicação do Informativo”, com o motivo)'
        using errcode = 'P0001';
    end if;
    -- v0.24.0: e só com a Conferência das Diretrizes deste texto, sem critério que não atende (ou com o "Revisei e assumo")
    v_marcas := public.radar_conferencia_pendente(new);
    if v_marcas is not null then
      raise exception '%', v_marcas using errcode = 'P0001';
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
  -- v0.12.0: liberado pelo administrador ("Publicar mesmo assim"): a exigência de fundamentação não vale para este assunto
  if exists (select 1 from public.radar_assuntos a where a.id = p_assunto and a.liberado_sem_base_em is not null) then
    return null;
  end if;
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

-- v0.12.0: "Publicar mesmo assim" — só o administrador, com motivo. p_motivo nulo desfaz a liberação.
create or replace function public.radar_liberar_sem_fundamentacao(p_assunto bigint, p_motivo text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR120: só o administrador libera a publicação sem a fundamentação oficial' using errcode = '42501';
  end if;
  if p_motivo is not null and length(btrim(p_motivo)) not between 10 and 500 then
    raise exception 'RADAR121: escreva o motivo da liberação (de 10 a 500 caracteres)' using errcode = 'P0001';
  end if;
  perform set_config('radar.liberando', '1', true);
  update public.radar_assuntos
     set liberado_sem_base_por = case when p_motivo is null then null else auth.uid() end,
         liberado_sem_base_em = case when p_motivo is null then null else now() end,
         liberado_sem_base_motivo = nullif(btrim(p_motivo), '')
   where id = p_assunto;
  if not found then
    raise exception 'RADAR122: assunto não encontrado' using errcode = 'P0001';
  end if;
  perform set_config('radar.liberando', '', true);
  -- v0.24.0: desfeita a liberação, o texto Informativo aprovado do assunto volta para a revisão (a autorização dele era essa; sem
  -- ela, nada dele vai ao site nem às redes, e as autorizações de publicação que esperavam caem com a mudança)
  if p_motivo is null then
    update public.radar_conteudos set status = 'em_revisao'
     where assunto_id = p_assunto and status = 'aprovado' and coalesce(avisos_ia->>0, '') like 'INFORMATIVO%';
  end if;
end $$;

-- v0.14.3: marcas [VERIFICAR …] que a IA deixa onde falta conferir uma informação. Enquanto houver alguma no título, no texto
-- ou na legenda, nada é aprovado nem publicado. Devolve a mensagem com cada marca encontrada (NULL quando não há nenhuma).
create or replace function public.radar_marcas_verificar(p_texto text) returns text
language sql immutable set search_path = public as $$
  select case when count(*) = 0 then null
    else 'RADAR139: resolva antes de liberar: ' || count(*) || ' ponto(s) marcado(s) com [VERIFICAR] — ' ||
         string_agg('"' || left(regexp_replace(m[1], '\s+', ' ', 'g'), 160) || '"', '; ') ||
         '. Troque cada marca pela informação conferida (ou tire o trecho), salve e tente de novo.'
  end
  from regexp_matches(coalesce(p_texto, ''), '(\[[\s\u00a0]*verificar[^]\n]{0,250}\]?)', 'gi') as m
$$;
revoke all on function public.radar_marcas_verificar(text) from public, anon, authenticated, service_role;

-- v0.14.0: tira do texto as linhas que só avisam a origem ("este informativo é baseado em material de fonte não oficial",
-- "Fonte não oficial: boletim X"): esse aviso é interno (fica em avisos_ia), não vai para o leitor. Parágrafo que fala de
-- fonte não oficial como assunto ("boletos de fontes não oficiais são golpe") fica.
create or replace function public.radar_tirar_aviso_fonte(p_texto text) returns text
language sql immutable set search_path = public as $$
  select btrim(regexp_replace(
           regexp_replace(coalesce(p_texto, ''),
             '^[ \t*_>]*((este|esta|o presente|a presente)\s+(informativo|texto|conte[úu]do|material|an[áa]lise|not[íi]cia|artigo)\y[^\n]*?(baseado|baseada|com base|elaborado|elaborada|escrito|escrita|produzido|produzida|feito|feita|a partir)[^\n]*fontes?\s+n[ãa]o[\s-]+oficia(l|is)|fontes?\s+n[ãa]o[\s-]+oficia(l|is)\s*:)[^\n]*(\n|$)',
             '', 'gin'),
           '\n{3,}', E'\n\n', 'g'), E' \n')
$$;

-- v0.12.1: com a publicação liberada pelo administrador, o texto para análise (fonte não oficial) pode virar um conteúdo
-- normal: é criada uma CÓPIA em rascunho, sem a marca de análise, que segue revisão e aprovação como qualquer outro.
-- O texto para análise original fica como está (fora do site).
create or replace function public.radar_converter_analise(p_conteudo bigint) returns bigint
language plpgsql security definer set search_path = public as $$
declare
  v_c public.radar_conteudos%rowtype;
  v_id bigint;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR123: só o administrador transforma o texto para análise em texto para publicar' using errcode = '42501';
  end if;
  select * into v_c from public.radar_conteudos c where c.id = p_conteudo;
  if v_c.id is null or coalesce(v_c.avisos_ia->>0, '') not like 'TEXTO PARA ANÁLISE%' then
    raise exception 'RADAR124: este conteúdo não é um texto para análise' using errcode = 'P0001';
  end if;
  if not exists (select 1 from public.radar_assuntos a where a.id = v_c.assunto_id and a.liberado_sem_base_em is not null) then
    raise exception 'RADAR125: primeiro libere a publicação deste assunto ("Publicar mesmo assim", com o motivo)' using errcode = 'P0001';
  end if;
  insert into public.radar_conteudos (assunto_id, formato, titulo, corpo, gerado_por, modelo_ia, status, avisos_ia,
                                      titulos_sugeridos, imagem_id, ilustracao_id, autor, fonte_credito, fora_do_site)
  values (v_c.assunto_id, v_c.formato, v_c.titulo, public.radar_tirar_aviso_fonte(v_c.corpo), v_c.gerado_por, v_c.modelo_ia, 'rascunho',
          jsonb_build_array('Feito a partir do texto para análise (fonte NÃO oficial), com a publicação liberada pelo administrador. ' ||
                            'Confira cada número, data e norma e resolva os [VERIFICAR] antes de aprovar.') || (v_c.avisos_ia - 0),
          v_c.titulos_sugeridos, v_c.imagem_id, v_c.ilustracao_id, v_c.autor, v_c.fonte_credito, false)
  returning id into v_id;
  return v_id;
end $$;

-- v0.16.0: "Autorizar mesmo assim" o conteúdo com trecho igual ao texto da fonte (a comparação é feita na tela, que
-- não deixa aprovar sem isto). Editor ou administrador, com o motivo; vale para o texto que estava na tela (p_lido) e
-- cai sozinha quando o texto muda. Quem, quando e o motivo ficam no conteúdo e na auditoria.
create or replace function public.radar_autorizar_copia(p_conteudo bigint, p_motivo text, p_lido timestamptz)
returns timestamptz language plpgsql security definer set search_path = public as $$
declare v_em timestamptz;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'permission denied for function radar_autorizar_copia' using errcode = '42501';
  end if;
  if length(btrim(coalesce(p_motivo, ''))) < 5 then
    raise exception 'RADAR143: diga em poucas palavras por que o trecho igual ao da fonte pode ficar (ex.: transcrição do artigo da lei, com a fonte citada)' using errcode = 'P0001';
  end if;
  -- v0.22.0 (varredura geral): a frase do boletim pago não se autoriza (só o trecho igual ao de fonte livre, com motivo)
  if exists (select 1 from public.radar_conteudos c where c.id = p_conteudo
              and public.radar_copia_paga_assunto(c.assunto_id, array[c.titulo, c.corpo])) then
    raise exception 'RADAR146: frase do boletim pago (ITC) no texto não se autoriza: reescreva com palavras próprias (o boletim pago nunca é reproduzido, nem citando a fonte nem entre aspas)' using errcode = 'P0001';
  end if;
  perform set_config('radar.autorizando_copia', '1', true);
  update public.radar_conteudos
     set copia_autorizada_em = now(), copia_autorizada_por = auth.uid(), copia_autorizada_motivo = left(btrim(p_motivo), 500)
   where id = p_conteudo and atualizado_em = p_lido
  returning copia_autorizada_em into v_em;
  perform set_config('radar.autorizando_copia', '', true);
  if v_em is null then
    raise exception 'RADAR144: o conteúdo mudou depois que a tela foi aberta (ou não existe mais); confira o texto e autorize de novo' using errcode = 'P0001';
  end if;
  return v_em;
end $$;

-- ---------------------------------------------------------------- v0.24.0: Conferência das Diretrizes
-- Os 10 critérios do escritório antes de aprovar (Diretriz 7). A IA confere ("Revisar com IA", função radar-ia) e grava a lista por
-- radar_registrar_conferencia; o que dá para conferir por código o banco confere sozinho e vale por cima da lista; o administrador
-- pode assumir ("Revisei e assumo", com o motivo). Tudo preso à versão do texto: mudou o título, o texto, a fonte ou a capa, a
-- conferência anterior deixa de valer. A aprovação (radar_fn_conteudo_aprovacao) só passa com a conferência desta versão sem critério
-- que não atende, ou com o "Revisei e assumo" desta versão; as travas de antes ([VERIFICAR], boletim pago) continuam valendo sempre.

-- A versão do texto que a conferência vale: o título, o texto, a fonte e a capa (se tem imagem e qual ilustração da IA; a capa refeita
-- com o título novo, com a mesma ilustração, não muda a versão). É também coluna calculada na leitura da tela
-- (select=*,radar_conferencia_versao).
create or replace function public.radar_conferencia_versao(c public.radar_conteudos) returns text
language sql immutable set search_path = public as $$
  select md5(concat_ws(E'\x1f', coalesce(c.titulo, ''), coalesce(c.corpo, ''), coalesce(c.fonte_credito, ''),
                       case when c.imagem_id is null then '-' else 'imagem' end, coalesce(c.ilustracao_id::text, '-')))
$$;

-- O texto cita norma com número (lei, decreto, IN, portaria, resolução, convênio, MP, EC, ato declaratório, solução de consulta,
-- parecer normativo) ou artigo: afirmação com base legal, que pede a linha "Fonte oficial" (v0.24.0, etapa 5; antes, a seção
-- "Fundamentação legal"). A mesma regra está na função radar-ia (citaNorma; testes/test_radar_funcao_ia.py confere as duas com os
-- mesmos exemplos).
create or replace function public.radar_cita_norma(p text) returns boolean
language sql immutable set search_path = public as $$
  select coalesce(p, '') ~* ('(^|[^[:alnum:]])(lei(\s+complementar)?|decreto(-lei)?|instru[çc][ãa]o\s+normativa|portaria|resolu[çc][ãa]o'
                             || '|conv[êe]nio|medida\s+provis[óo]ria|emenda\s+constitucional|ato\s+declarat[óo]rio|solu[çc][ãa]o\s+de\s+consulta'
                             || '|parecer\s+normativo|lc|in|mp|ec)(\s+[[:alpha:]][[:alpha:]/.-]*){0,3}\s*(n[º°o.]+\s*)?[0-9]')
      or coalesce(p, '') ~* '(^|[^[:alnum:]])art(igo|s?\.)\s*[0-9]'
$$;

-- O texto tem, numa linha só dela, "Fonte oficial:" (v0.24.0, etapa 5: "Fonte oficial: <norma> — <link>", no fim; também em negrito ou
-- como item de lista) ou a seção "## Fundamentação legal" dos textos de antes, e dali até o fim há ao menos um link oficial (gov.br,
-- jus.br, leg.br, mp.br, def.br: os mesmos domínios da verificação em fontes oficiais). A mesma regra está na função radar-ia
-- (temFundamentacao).
create or replace function public.radar_tem_fundamentacao(p text) returns boolean
language sql immutable set search_path = public as $$
  select coalesce((regexp_match(coalesce(p, ''), '(?:^|\n)[ \t]*(?:[-•][ \t]+)?(?:##[ \t]*fundamenta[çc][ãa]o legal|\**fontes?[ \t]+oficia(?:l|is)\**[ \t]*:)(.*)$', 'i'))[1]
                  ~* 'https?://([a-z0-9-]+\.)*(gov|jus|leg|mp|def)\.br($|[^a-z0-9-])', false)
$$;

-- O que o banco confere sozinho, por código (vale por cima da lista da IA): {"6": {"situacao", "motivo"}, …}. A imagem (6) sai
-- sempre daqui (a IA não vê a capa); os outros, só quando não atendem.
-- v0.25.0 (etapa 6): a imagem da IA guardada nesta versão é a imagem da publicação inteira, em 3:2 (largura × 2 = altura × 3), com o
-- aviso desenhado pela tela no canto (a da v0.16.0 à v0.24.0 é a ilustração crua, sempre 1200×630, que ia ao fundo da capa com o título
-- e não leva aviso). Ela em uso (imagem_id = ilustracao_id) atende; guardada fora da publicação (a capa padrão ou a foto da equipe no
-- lugar), também. A capa antiga montada com a ilustração continua pedindo o aviso escrito no texto, como antes.
create or replace function public.radar_conferencia_codigo(c public.radar_conteudos) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  v jsonb;
  v_falha text := 'nao_atende';
  v_ia_com_aviso boolean := exists (select 1 from public.radar_imagens i where i.id = c.ilustracao_id and i.largura * 2 = i.altura * 3);
begin
  -- 6: capa padrão da Artecon ou imagem enviada pela equipe atende; a imagem da IA, com o aviso no canto (v0.25.0) ou escrito no texto
  v := jsonb_build_object('6', case
    when c.imagem_id is null then jsonb_build_object('situacao', 'nao_se_aplica', 'motivo', 'Sem imagem de capa.')
    when c.imagem_id = c.ilustracao_id and v_ia_com_aviso then jsonb_build_object('situacao', 'atende', 'motivo',
      'Imagem gerada por IA, inteira, com o aviso “Imagem ilustrativa gerada por IA” no canto (colocado pelo Radar).')
    when c.ilustracao_id is null then jsonb_build_object('situacao', 'atende', 'motivo', 'Capa padrão da Artecon ou imagem enviada pela equipe.')
    when c.imagem_id is distinct from c.ilustracao_id and v_ia_com_aviso then jsonb_build_object('situacao', 'atende', 'motivo',
      'Capa padrão da Artecon ou imagem enviada pela equipe (a imagem da IA está guardada, fora da publicação).')
    when coalesce(c.corpo, '') ~* 'imagem ilustrativa gerada (por|com) (a )?(ia|intelig[êe]ncia artificial)'
      then jsonb_build_object('situacao', 'atende', 'motivo', 'Ilustração de IA com o aviso “Imagem ilustrativa gerada por IA”.')
    else jsonb_build_object('situacao', v_falha, 'motivo', 'Capa com ilustração de IA sem o aviso “Imagem ilustrativa gerada por IA”: '
                            || 'use “Usar a imagem da IA de novo” (ela sai inteira, com o aviso no canto), a capa padrão ou uma foto da equipe, '
                            || 'ou escreva o aviso no fim do texto.') end);
  if public.radar_marcas_verificar(coalesce(c.titulo, '') || E'\n' || coalesce(c.corpo, '')) is not null then
    v := v || jsonb_build_object(
      '2', jsonb_build_object('situacao', v_falha, 'motivo', 'Há ponto marcado com [VERIFICAR]: a informação ainda não foi confirmada.'),
      '8', jsonb_build_object('situacao', v_falha, 'motivo', 'Há ponto marcado com [VERIFICAR]: confira e atualize antes de aprovar.'));
  -- (o Informativo não tem a linha: a norma que ele menciona é informação atribuída à fonte; o critério 2 dele fica com a IA)
  elsif coalesce(c.avisos_ia->>0, '') not like 'INFORMATIVO%'
        and public.radar_cita_norma(c.corpo) and not public.radar_tem_fundamentacao(c.corpo) then
    v := v || jsonb_build_object('2', jsonb_build_object('situacao', v_falha, 'motivo',
      'O texto cita norma, mas não termina com a linha “Fonte oficial” com o link oficial (a norma e o link do documento oficial).'));
  end if;
  if coalesce(c.avisos_ia->>0, '') like 'INFORMATIVO%' and btrim(coalesce(c.fonte_credito, '')) = '' then
    v := v || jsonb_build_object('3', jsonb_build_object('situacao', v_falha, 'motivo',
      'Informativo sem a fonte citada: preencha o campo Fonte (ele sai no fim da notícia, com o link).'));
  end if;
  if public.radar_copia_paga_assunto(c.assunto_id, array[c.titulo, c.corpo]) then
    v := v || jsonb_build_object('4', jsonb_build_object('situacao', v_falha, 'motivo',
      'Frase igual à do boletim pago (ITC): reescreva com palavras próprias.'));
  end if;
  return v;
end $$;

-- A conferência vale para a aprovação? NULL = vale; senão, o motivo (RADAR181/182), como a aprovação mostra.
create or replace function public.radar_conferencia_pendente(c public.radar_conteudos) returns text
language sql stable set search_path = public as $$
  select case
    when c.conferencia->'assumida'->>'versao' = public.radar_conferencia_versao(c) then null
    when c.conferencia->>'versao' is distinct from public.radar_conferencia_versao(c)
         or jsonb_typeof(c.conferencia->'itens') is distinct from 'array' or jsonb_array_length(c.conferencia->'itens') <> 10 then
      'RADAR181: falta a Conferência das Diretrizes deste texto: clique em “Revisar com IA” (se a IA não puder, o administrador usa '
      || '“Revisei e assumo”, com o motivo) e aprove de novo'
    when exists (select 1 from jsonb_array_elements(c.conferencia->'itens') e where e->>'situacao' is distinct from 'atende'
                                                                               and e->>'situacao' is distinct from 'nao_se_aplica') then
      'RADAR182: a Conferência das Diretrizes tem critério que não atende (' ||
      (select string_agg(e->>'item', ', ' order by (e->>'item')::int) from jsonb_array_elements(c.conferencia->'itens') e
        where e->>'situacao' is distinct from 'atende' and e->>'situacao' is distinct from 'nao_se_aplica') ||
      '): corrija o texto e clique em “Revisar com IA” de novo, ou o administrador usa “Revisei e assumo”, com o motivo'
  end
$$;

-- Grava a lista da IA para o texto que ela conferiu (p_lido: a data do conteúdo que foi à IA). Editor ou administrador (a função
-- radar-ia grava como quem pediu). O que o banco confere sozinho vale por cima; o "Revisei e assumo" que houver continua guardado.
create or replace function public.radar_registrar_conferencia(p_conteudo bigint, p_lido timestamptz, p_itens jsonb, p_modelo text default null)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  v_c public.radar_conteudos%rowtype;
  v_codigo jsonb;
  v_itens jsonb;
  v_conf jsonb;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR183: só o editor ou o administrador confere o conteúdo' using errcode = '42501';
  end if;
  if jsonb_typeof(p_itens) is distinct from 'array' or jsonb_array_length(p_itens) <> 10
     or (select count(distinct e->>'item') from jsonb_array_elements(p_itens) e
          where jsonb_typeof(e) = 'object' and e->>'item' ~ '^([1-9]|10)$'
            and e->>'situacao' in ('atende','nao_atende','nao_se_aplica')
            and jsonb_typeof(e->'motivo') = 'string' and length(btrim(e->>'motivo')) between 1 and 300) <> 10 then
    raise exception 'RADAR185: a conferência precisa ter os 10 critérios, cada um uma vez, com a situação e o motivo (até 300 caracteres)'
      using errcode = 'P0001';
  end if;
  select * into v_c from public.radar_conteudos c where c.id = p_conteudo for update;
  if v_c.id is null or v_c.atualizado_em is distinct from p_lido then
    raise exception 'RADAR184: o conteúdo mudou depois que a conferência começou (ou não existe mais): confira de novo' using errcode = 'P0001';
  end if;
  v_codigo := public.radar_conferencia_codigo(v_c);
  select jsonb_agg(jsonb_build_object('item', (e->>'item')::int) ||
                   coalesce(v_codigo->(e->>'item'), jsonb_build_object('situacao', e->>'situacao', 'motivo', btrim(e->>'motivo')))
                   order by (e->>'item')::int)
    into v_itens from jsonb_array_elements(p_itens) e;
  -- quem não é o administrador não tira o ✗ que a lista desta mesma versão do texto já tinha (conferir de novo o mesmo texto não apaga
  -- o critério que não atende): ele cai com um texto novo ou com o "Revisei e assumo" do administrador
  if coalesce(public.radar_papel(), '') <> 'admin' and v_c.conferencia->>'versao' = public.radar_conferencia_versao(v_c)
     and jsonb_typeof(v_c.conferencia->'itens') = 'array' then
    select jsonb_agg(case when e->>'situacao' = 'nao_atende' then e
                          else coalesce((select x from jsonb_array_elements(v_c.conferencia->'itens') x
                                          where x->>'item' = e->>'item' and x->>'situacao' = 'nao_atende' limit 1), e) end
                     order by (e->>'item')::int)
      into v_itens from jsonb_array_elements(v_itens) e;
  end if;
  v_conf := jsonb_build_object('versao', public.radar_conferencia_versao(v_c), 'itens', v_itens, 'em', now(), 'por', auth.uid(),
                               'modelo', left(nullif(btrim(coalesce(p_modelo, '')), ''), 80))
            || case when v_c.conferencia ? 'assumida' then jsonb_build_object('assumida', v_c.conferencia->'assumida') else '{}'::jsonb end
            -- v0.24.0 (etapa 5): a revisão editorial guardada continua (ela tem a versão dela)
            || case when v_c.conferencia ? 'editorial' then jsonb_build_object('editorial', v_c.conferencia->'editorial') else '{}'::jsonb end;
  perform set_config('radar.conferindo', '1', true);
  update public.radar_conteudos set conferencia = v_conf where id = p_conteudo;
  perform set_config('radar.conferindo', '', true);
  return v_conf;
end $$;

-- "Revisei e assumo": o administrador libera a aprovação desta versão do texto, com o motivo (fica na conferência e no Histórico).
-- Não passa por cima das travas de antes ([VERIFICAR], boletim pago) nem da autorização do Informativo.
create or replace function public.radar_assumir_conferencia(p_conteudo bigint, p_motivo text, p_lido timestamptz)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  v_c public.radar_conteudos%rowtype;
  v_conf jsonb;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR186: só o administrador assume a conferência (“Revisei e assumo”)' using errcode = '42501';
  end if;
  if length(btrim(coalesce(p_motivo, ''))) not between 10 and 500 then
    raise exception 'RADAR187: escreva o motivo (de 10 a 500 caracteres): ele fica no histórico' using errcode = 'P0001';
  end if;
  select * into v_c from public.radar_conteudos c where c.id = p_conteudo for update;
  if v_c.id is null or v_c.atualizado_em is distinct from p_lido then
    raise exception 'RADAR184: o conteúdo mudou depois que a tela foi aberta (ou não existe mais): confira e tente de novo' using errcode = 'P0001';
  end if;
  v_conf := v_c.conferencia || jsonb_build_object('assumida', jsonb_build_object('versao', public.radar_conferencia_versao(v_c),
                                                  'por', auth.uid(), 'em', now(), 'motivo', btrim(p_motivo)));
  perform set_config('radar.conferindo', '1', true);
  update public.radar_conteudos set conferencia = v_conf where id = p_conteudo;
  perform set_config('radar.conferindo', '', true);
  return v_conf;
end $$;

-- ---------------------------------------------------------------- v0.24.0 (etapa 5): revisão editorial automática
-- Depois de escrever o texto principal, a função radar-ia confere o rascunho pelas 10 perguntas da revisão editorial (item 7 da
-- Diretriz de Humanização) e reescreve os trechos com problema; o resultado fica no conteúdo (conferencia->'editorial') para a tela
-- mostrar o quadro "Revisão editorial". É só informativo: a aprovação continua pedindo a Conferência das Diretrizes (os 10 critérios).

-- A versão do TEXTO a que a revisão editorial se refere: só o corpo (o título escolhido entre as sugestões e a capa não contam). Também
-- é coluna calculada na leitura da tela (select=*,radar_texto_versao): diferente da guardada, a tela avisa que o texto mudou depois.
create or replace function public.radar_texto_versao(c public.radar_conteudos) returns text
language sql immutable set search_path = public as $$
  select md5(coalesce(c.corpo, ''))
$$;

-- Grava a revisão editorial do texto que está no conteúdo (p_lido: a data do conteúdo gravado pela função). Editor ou administrador (a
-- função radar-ia grava como quem pediu). p_revisao: {"feita": true, "perguntas": [{"n", "situacao" (ok | ajustado), "motivo"}] (as 10,
-- cada uma uma vez), "reescritos": [{"antes", "depois"}] (até 12), "modelo"} ou {"feita": false, "motivo"} (não coube no tempo, a IA
-- falhou ou a reescrita foi recusada). Só essas chaves ficam; o banco põe a versão do texto, quando e quem.
create or replace function public.radar_registrar_revisao_editorial(p_conteudo bigint, p_lido timestamptz, p_revisao jsonb)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  v_c public.radar_conteudos%rowtype;
  v jsonb;
  v_feita boolean := jsonb_typeof(p_revisao) = 'object' and p_revisao->'feita' = 'true'::jsonb;
  v_ruim boolean;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR188: só o editor ou o administrador registra a revisão editorial' using errcode = '42501';
  end if;
  -- em passos (o tipo de cada parte antes de contar ou percorrer: lista que não é lista vira o erro da validação, não outro)
  if jsonb_typeof(p_revisao) is distinct from 'object' or length(p_revisao::text) > 12000
     or jsonb_typeof(p_revisao->'feita') is distinct from 'boolean' then
    v_ruim := true;
  elsif not v_feita then
    v_ruim := jsonb_typeof(p_revisao->'motivo') is distinct from 'string' or length(btrim(p_revisao->>'motivo')) not between 1 and 300;
  elsif jsonb_typeof(p_revisao->'perguntas') is distinct from 'array'
        or jsonb_typeof(coalesce(p_revisao->'reescritos', '[]'::jsonb)) is distinct from 'array' then
    v_ruim := true;
  else
    v_ruim := jsonb_array_length(p_revisao->'perguntas') <> 10
      or (select count(distinct e->>'n') from jsonb_array_elements(p_revisao->'perguntas') e
           where jsonb_typeof(e) = 'object' and e->>'n' ~ '^([1-9]|10)$' and e->>'situacao' in ('ok','ajustado')
             and jsonb_typeof(e->'motivo') = 'string' and length(btrim(e->>'motivo')) between 1 and 300) <> 10
      or jsonb_array_length(coalesce(p_revisao->'reescritos', '[]'::jsonb)) > 12
      or exists (select 1 from jsonb_array_elements(coalesce(p_revisao->'reescritos', '[]'::jsonb)) r
                  where jsonb_typeof(r) is distinct from 'object' or jsonb_typeof(r->'antes') is distinct from 'string'
                     or jsonb_typeof(r->'depois') is distinct from 'string' or length(r->>'antes') not between 1 and 400
                     or length(r->>'depois') > 400);
  end if;
  if v_ruim then
    raise exception 'RADAR189: a revisão editorial precisa ter as 10 perguntas, cada uma uma vez, com “ok” ou “ajustado” e o motivo (até 300 caracteres), e até 12 trechos reescritos; ou, não feita, o motivo'
      using errcode = 'P0001';
  end if;
  select * into v_c from public.radar_conteudos c where c.id = p_conteudo for update;
  if v_c.id is null or v_c.atualizado_em is distinct from p_lido then
    raise exception 'RADAR190: o conteúdo mudou depois que a revisão editorial começou (ou não existe mais): faça a revisão de novo' using errcode = 'P0001';
  end if;
  v := jsonb_build_object('feita', v_feita, 'versao', public.radar_texto_versao(v_c), 'em', now(), 'por', auth.uid(),
                          'modelo', left(nullif(btrim(coalesce(p_revisao->>'modelo', '')), ''), 80))
       || case when v_feita then jsonb_build_object(
            'perguntas', (select jsonb_agg(jsonb_build_object('n', (e->>'n')::int, 'situacao', e->>'situacao', 'motivo', btrim(e->>'motivo'))
                                           order by (e->>'n')::int) from jsonb_array_elements(p_revisao->'perguntas') e),
            'reescritos', coalesce((select jsonb_agg(jsonb_build_object('antes', r->>'antes', 'depois', r->>'depois') order by k)
                                      from jsonb_array_elements(coalesce(p_revisao->'reescritos', '[]'::jsonb)) with ordinality x(r, k)), '[]'::jsonb))
          else jsonb_build_object('motivo', btrim(p_revisao->>'motivo')) end;
  perform set_config('radar.conferindo', '1', true);
  update public.radar_conteudos set conferencia = conferencia || jsonb_build_object('editorial', v) where id = p_conteudo;
  perform set_config('radar.conferindo', '', true);
  return v;
end $$;

-- a liberação só muda pela função radar_liberar_sem_fundamentacao (a equipe edita o assunto, mas não esses campos)
create or replace function public.radar_fn_assunto_liberacao() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if coalesce(current_setting('radar.liberando', true), '') = '1' then
    return new;
  end if;
  if tg_op = 'INSERT' then
    new.liberado_sem_base_por := null; new.liberado_sem_base_em := null; new.liberado_sem_base_motivo := null;
  else
    new.liberado_sem_base_por := public.radar_manter_usuario(old.liberado_sem_base_por, new.liberado_sem_base_por);
    new.liberado_sem_base_em := old.liberado_sem_base_em; new.liberado_sem_base_motivo := old.liberado_sem_base_motivo;
  end if;
  return new;
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

-- v0.22.0 (varredura geral): o domínio de um link (minúsculas, sem "www.") e o do site da Artecon, o mesmo que o robô do site
-- usa (Configurações → "site" → "lista"; sem ela, artecon.cnt.br)
create or replace function public.radar_url_host(p_url text) returns text
language sql immutable set search_path = public as $$
  select nullif(regexp_replace(lower(substring(coalesce(p_url, '') from '^[A-Za-z][A-Za-z0-9+.-]*://(?:[^/?#@]*@)?([^/?#:]+)')), '^www\.', ''), '')
$$;
create or replace function public.radar_site_host() returns text
language sql stable set search_path = public as $$
  select coalesce((select public.radar_url_host(c.valor->>'lista') from public.radar_config c
                    where c.chave = 'site' and jsonb_typeof(c.valor) = 'object' and c.valor->>'lista' ~ '^https?://[!-~]+$'), 'artecon.cnt.br')
$$;

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
    -- v0.22.0 (varredura geral): com a publicação no site autorizada e o robô na vez, quem registra é o robô (com o link que
    -- ele achou no site): o registro à mão nessa hora liberaria o Instagram e o Facebook com um link que ninguém conferiu
    if auth.uid() is not null and exists (select 1 from public.radar_site_envios e
                                           where e.conteudo_id = new.conteudo_id and e.situacao in ('autorizado','enviando')) then
      raise exception 'RADAR145: a publicação no site está autorizada e o robô registra o link sozinho ao concluir; espere ou cancele a autorização antes de registrar à mão'
        using errcode = 'P0001';
    end if;
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
  v_pendencia := public.radar_marcas_verificar(coalesce(v_c.titulo, '') || E'\n' || coalesce(v_c.corpo, ''));   -- v0.14.3
  if v_pendencia is not null then
    raise exception '%', v_pendencia using errcode = 'P0001';
  end if;
  if public.radar_copia_paga_assunto(v_c.assunto_id, array[v_c.titulo, v_c.corpo]) then      -- v0.22.0 (varredura geral)
    raise exception 'RADAR146: frase do boletim pago (ITC) no texto: reescreva com palavras próprias (o boletim pago nunca é reproduzido, nem citando a fonte nem entre aspas)' using errcode = 'P0001';
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
    -- v0.13.0: o mesmo para o Instagram e o Facebook (a que deu erro também: o texto que iria já não é o aprovado)
    -- v0.17.0: e a que esperava o site ("Publicar em todos")
    update public.radar_redes_envios
       set situacao = 'cancelado', cancelado_em = now(), atualizado_em = now(),
           erro = 'Autorização cancelada sozinha: o conteúdo mudou depois de autorizado. Confira e autorize de novo.'
     where conteudo_id = new.id and situacao in ('aguardando_site','autorizado','erro');
  end if;
  return null;
end $$;

-- v0.22.0 (varredura geral): a publicação da notícia cancelada no meio do envio ("publicando" parada: a Meta pode ter publicado e o
-- registro não ter entrado) pode estar no ar. Autorizar de novo o mesmo canal pede a caixa "Conferi no Instagram/Facebook: não saiu"
-- (p_conferi_rede), como na Pauta (RADAR166): nunca publicar duas vezes. O mesmo critério da Pauta (enviado e sem post_id), até
-- que uma publicação desse canal saia de fato.
create or replace function public.radar_rede_cancelada_no_envio(p_conteudo bigint, p_canal text) returns boolean
language sql stable set search_path = public as $$
  select exists (select 1 from public.radar_redes_envios e
                  where e.conteudo_id = p_conteudo and e.canal = p_canal and e.peca_id is null
                    and e.situacao = 'cancelado' and e.enviado_em is not null and e.post_id is null
                    and not exists (select 1 from public.radar_redes_envios d where d.conteudo_id = p_conteudo and d.canal = p_canal
                                     and d.id > e.id and d.post_id is not null))
$$;

-- v0.13.0: Instagram e Facebook. Valem as exigências do site (conteúdo aprovado, assunto com fundamentação — ou liberado
-- pelo administrador) e mais uma: a notícia já precisa estar no site (a legenda leva o leitor até ela).
-- v0.22.0 (varredura geral): + p_conferi_rede (radar_rede_cancelada_no_envio)
drop function if exists public.radar_autorizar_rede(bigint, text, text, text, timestamptz);
create or replace function public.radar_autorizar_rede(p_conteudo bigint, p_canal text, p_legenda text, p_imagem text, p_lido timestamptz,
                                                       p_conferi_rede boolean default false)
returns bigint language plpgsql security definer set search_path = public as $$
declare
  v_c public.radar_conteudos%rowtype;
  v_pendencia text;
  v_id bigint;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR130: só o administrador autoriza a publicação no Instagram e no Facebook' using errcode = '42501';
  end if;
  if p_canal is null or p_canal not in ('instagram','facebook') then
    raise exception 'RADAR131: canal desconhecido' using errcode = 'P0001';
  end if;
  select * into v_c from public.radar_conteudos c where c.id = p_conteudo for update;
  if v_c.id is null then
    raise exception 'RADAR111: conteúdo não encontrado' using errcode = 'P0001';
  end if;
  if v_c.status is distinct from 'aprovado' or coalesce(v_c.avisos_ia->>0, '') like 'TEXTO PARA ANÁLISE%' then
    raise exception 'RADAR132: só conteúdo aprovado (que não seja texto para análise) vai para as redes' using errcode = 'P0001';
  end if;
  if p_lido is distinct from v_c.atualizado_em then
    raise exception 'RADAR114: o conteúdo foi alterado depois que esta tela foi aberta; recarregue, confira e autorize de novo' using errcode = 'P0001';
  end if;
  v_pendencia := public.radar_pendencia_assunto(v_c.assunto_id);
  if v_pendencia is not null then
    raise exception '%', v_pendencia using errcode = 'P0001';
  end if;
  if not exists (select 1 from public.radar_divulgacoes d where d.conteudo_id = p_conteudo) then
    raise exception 'RADAR133: publique primeiro no site: a legenda leva o leitor até a notícia' using errcode = 'P0001';
  end if;
  if length(btrim(coalesce(p_legenda, ''))) not between 10 and 2200 then
    raise exception 'RADAR134: a legenda precisa ter de 10 a 2.200 caracteres' using errcode = 'P0001';
  end if;
  -- v0.14.3: nem na legenda nem no texto do site pode sobrar ponto marcado com [VERIFICAR]
  v_pendencia := public.radar_marcas_verificar(coalesce(p_legenda, '') || E'\n' || coalesce(v_c.titulo, '') || E'\n' || coalesce(v_c.corpo, ''));
  if v_pendencia is not null then
    raise exception '%', v_pendencia using errcode = 'P0001';
  end if;
  if public.radar_copia_paga_assunto(v_c.assunto_id, array[p_legenda, v_c.titulo, v_c.corpo]) then      -- v0.22.0 (varredura geral)
    raise exception 'RADAR146: frase do boletim pago (ITC) na legenda ou no texto: reescreva com palavras próprias (o boletim pago nunca é reproduzido, nem citando a fonte nem entre aspas)' using errcode = 'P0001';
  end if;
  if p_imagem is null or p_imagem not like 'data:image/jpeg;base64,%' or length(p_imagem) > 3000000 then
    raise exception 'RADAR135: falta a imagem (JPEG) da publicação' using errcode = 'P0001';
  end if;
  if exists (select 1 from public.radar_redes_envios e where e.conteudo_id = p_conteudo and e.canal = p_canal
              and e.situacao in ('autorizado','enviando','erro','publicado','dispensado')) then
    raise exception 'RADAR136: este conteúdo já tem publicação autorizada, feita ou dispensada neste canal' using errcode = 'P0001';
  end if;
  if not coalesce(p_conferi_rede, false) and public.radar_rede_cancelada_no_envio(p_conteudo, p_canal) then
    raise exception 'RADAR166: a publicação deste conteúdo no % foi cancelada no meio do envio: confira no % que ela não saiu e marque “Conferi no %: não saiu”',
      initcap(p_canal), initcap(p_canal), initcap(p_canal) using errcode = 'P0001';
  end if;
  insert into public.radar_redes_envios (conteudo_id, canal, legenda, imagem, conteudo_lido_em, autorizado_por)
  values (p_conteudo, p_canal, btrim(p_legenda), p_imagem, v_c.atualizado_em, auth.uid())
  returning id into v_id;
  return v_id;
end $$;

-- "Não publicar neste canal": o passo da trilha fica resolvido sem publicar.
create or replace function public.radar_dispensar_rede(p_conteudo bigint, p_canal text) returns bigint
language plpgsql security definer set search_path = public as $$
declare
  v_c public.radar_conteudos%rowtype;
  v_id bigint;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR130: só o administrador autoriza a publicação no Instagram e no Facebook' using errcode = '42501';
  end if;
  if p_canal is null or p_canal not in ('instagram','facebook') then
    raise exception 'RADAR131: canal desconhecido' using errcode = 'P0001';
  end if;
  select * into v_c from public.radar_conteudos c where c.id = p_conteudo for update;
  if v_c.id is null then
    raise exception 'RADAR111: conteúdo não encontrado' using errcode = 'P0001';
  end if;
  if exists (select 1 from public.radar_redes_envios e where e.conteudo_id = p_conteudo and e.canal = p_canal
              and e.situacao in ('autorizado','enviando','erro','publicado','dispensado')) then
    raise exception 'RADAR136: este conteúdo já tem publicação autorizada, feita ou dispensada neste canal' using errcode = 'P0001';
  end if;
  insert into public.radar_redes_envios (conteudo_id, canal, legenda, conteudo_lido_em, situacao, autorizado_por)
  values (p_conteudo, p_canal, '(não publicado neste canal)', v_c.atualizado_em, 'dispensado', auth.uid())
  returning id into v_id;
  return v_id;
end $$;

-- Cancelar: autorizada (ainda não enviada), com erro ou dispensada. "Enviando" só depois de 10 minutos parada
-- (a função caiu no meio): confira na rede se saiu antes de autorizar de novo.
create or replace function public.radar_cancelar_rede(p_envio bigint) returns boolean
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR130: só o administrador mexe na autorização das redes' using errcode = '42501';
  end if;
  -- v0.22.0 (varredura geral): a cancelada no meio do envio diz o porquê da caixa "Conferi…: não saiu" na próxima autorização
  update public.radar_redes_envios
     set situacao = 'cancelado', cancelado_por = auth.uid(), cancelado_em = now(), atualizado_em = now(), imagem = null,
         erro = case when situacao = 'enviando'
                     then 'Cancelada no meio do envio: a publicação pode ter saído no ' || initcap(canal) || ' sem o registro no Radar. '
                          || 'Antes de autorizar de novo, confira lá que ela não saiu.' else erro end
   where id = p_envio
     and (situacao in ('aguardando_site','autorizado','erro','dispensado') or (situacao = 'enviando' and enviado_em < now() - interval '10 minutes'));
  if not found then
    raise exception 'RADAR137: não dá para cancelar agora (a publicação está saindo, já saiu ou não existe)' using errcode = 'P0001';
  end if;
  return true;
end $$;

-- A função radar-redes pega a autorização para enviar (uma vez só) e confere de novo as exigências.
create or replace function public.radar_rede_iniciar(p_envio bigint) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_e public.radar_redes_envios%rowtype;
  v_c public.radar_conteudos%rowtype;
  v_pendencia text;
begin
  -- v0.21.0: a peça da Pauta sai por radar_pauta_iniciar; quem chama aqui é a radar-redes de antes da v0.21.0 (nada muda)
  if exists (select 1 from public.radar_redes_envios where id = p_envio and peca_id is not null) then
    raise exception 'RADAR171: esta publicação é da Pauta: atualize a função radar-redes para a v0.21.0 (nada foi publicado)' using errcode = 'P0001';
  end if;
  select * into v_e from public.radar_redes_envios where id = p_envio for update;
  if v_e.id is null or v_e.situacao not in ('autorizado','erro') then
    raise exception 'RADAR138: esta autorização não está aguardando envio (já saiu, foi cancelada ou está saindo)' using errcode = 'P0001';
  end if;
  select * into v_c from public.radar_conteudos where id = v_e.conteudo_id;
  if v_c.status is distinct from 'aprovado' or v_c.atualizado_em is distinct from v_e.conteudo_lido_em then
    update public.radar_redes_envios set situacao = 'cancelado', cancelado_em = now(), atualizado_em = now(), imagem = null,
           erro = 'Autorização cancelada sozinha: o conteúdo mudou depois de autorizado. Confira e autorize de novo.'
     where id = p_envio;
    return jsonb_build_object('cancelado', true);
  end if;
  v_pendencia := coalesce(public.radar_pendencia_assunto(v_c.assunto_id),
                           -- v0.14.3: autorização antiga (de antes da trava) com [VERIFICAR] na legenda ou no texto também não sai
                           public.radar_marcas_verificar(coalesce(v_e.legenda, '') || E'\n' || coalesce(v_c.titulo, '') || E'\n' || coalesce(v_c.corpo, '')),
                           -- v0.22.0 (varredura geral): nem frase do boletim pago (autorização de antes da trava, ou boletim chegado depois)
                           case when public.radar_copia_paga_assunto(v_c.assunto_id, array[v_e.legenda, v_c.titulo, v_c.corpo])
                                then 'RADAR146: frase do boletim pago (ITC) na legenda ou no texto: reescreva com palavras próprias e autorize de novo' end);
  if v_pendencia is not null then
    update public.radar_redes_envios set situacao = 'erro', erro = left(v_pendencia, 1000), atualizado_em = now() where id = p_envio;
    return jsonb_build_object('erro', v_pendencia);
  end if;
  if v_e.imagem is null and v_e.imagem_url is null then
    update public.radar_redes_envios set situacao = 'erro', erro = 'A imagem da publicação se perdeu: cancele e autorize de novo.', atualizado_em = now()
     where id = p_envio;
    return jsonb_build_object('erro', 'sem imagem');
  end if;
  update public.radar_redes_envios set situacao = 'enviando', enviado_em = now(), erro = null, atualizado_em = now() where id = p_envio;
  return jsonb_build_object('id', v_e.id, 'canal', v_e.canal, 'conteudo_id', v_e.conteudo_id, 'legenda', v_e.legenda,
                            'imagem', v_e.imagem, 'imagem_url', v_e.imagem_url);
end $$;

-- Resultado do envio. A imagem guardada é apagada quando já está no armazenamento público (fica o link).
-- "erro" só quando a Meta recusou com certeza (pode tentar de novo); se não deu para saber se saiu, a função deixa "enviando".
create or replace function public.radar_rede_concluir(p_envio bigint, p_ok boolean, p_post_id text, p_url text, p_imagem_url text, p_erro text)
returns boolean language plpgsql security definer set search_path = public as $$
declare
  v_img text := case when p_imagem_url ~ '^https?://[!-~]+$' and length(p_imagem_url) <= 500 then p_imagem_url end;
begin
  update public.radar_redes_envios
     set situacao = case when p_ok then 'publicado' else 'erro' end,
         publicado_em = case when p_ok then now() end,
         post_id = case when p_ok then left(p_post_id, 100) end,
         url = case when p_ok and p_url ~ '^https://[!-~]+$' and length(p_url) <= 500 then p_url end,
         imagem_url = coalesce(v_img, imagem_url),
         imagem = case when coalesce(v_img, imagem_url) is not null then null else imagem end,
         erro = case when p_ok then null else left(coalesce(nullif(btrim(p_erro), ''), 'Erro sem descrição.'), 1000) end,
         atualizado_em = now()
   where id = p_envio and situacao = 'enviando';
  return found;
end $$;

-- v0.17.0: "Publicar em todos": o administrador autoriza de uma vez o site, o Instagram e o Facebook. Valem todas as exigências
-- de cada canal (as do site pela própria radar_autorizar_site). As redes ficam "aguardando_site": saem sozinhas logo depois que
-- a notícia entra no site; se o site não sair (cancelado ou erro) ou o texto mudar, elas caem junto.
-- v0.22.0 (varredura geral): + p_conferi_rede (radar_rede_cancelada_no_envio)
drop function if exists public.radar_autorizar_todos(bigint, text, timestamptz, text, text, text);
create or replace function public.radar_autorizar_todos(p_conteudo bigint, p_categoria text, p_lido timestamptz, p_imagem text,
                                                        p_legenda_instagram text, p_legenda_facebook text, p_conferi_rede boolean default false)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  v_c public.radar_conteudos%rowtype;
  v_pendencia text;
  v_site bigint;
  v_canal text;
  v_legenda text;
  v_ids jsonb := '{}'::jsonb;
  v_id bigint;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR110: só o administrador autoriza a publicação no site' using errcode = '42501';
  end if;
  if nullif(btrim(coalesce(p_legenda_instagram, '')), '') is null and nullif(btrim(coalesce(p_legenda_facebook, '')), '') is null then
    raise exception 'RADAR153: escolha ao menos o Instagram ou o Facebook (para só o site, use "Autorizar publicação no site")' using errcode = 'P0001';
  end if;
  -- as redes primeiro, para não deixar o site autorizado sozinho se uma legenda estiver errada
  foreach v_canal in array array['instagram','facebook'] loop
    v_legenda := btrim(coalesce(case v_canal when 'instagram' then p_legenda_instagram else p_legenda_facebook end, ''));
    continue when v_legenda = '';
    if length(v_legenda) not between 10 and 2000 then
      raise exception 'RADAR154: a legenda do % precisa ter de 10 a 2.000 caracteres (o link do site ainda entra nela)',
        case v_canal when 'instagram' then 'Instagram' else 'Facebook' end using errcode = 'P0001';
    end if;
    if exists (select 1 from public.radar_redes_envios e where e.conteudo_id = p_conteudo and e.canal = v_canal
                and e.situacao in ('aguardando_site','autorizado','enviando','erro','publicado','dispensado')) then
      raise exception 'RADAR136: este conteúdo já tem publicação autorizada, feita ou dispensada neste canal' using errcode = 'P0001';
    end if;
    if not coalesce(p_conferi_rede, false) and public.radar_rede_cancelada_no_envio(p_conteudo, v_canal) then
      raise exception 'RADAR166: a publicação deste conteúdo no % foi cancelada no meio do envio: confira no % que ela não saiu e marque “Conferi no %: não saiu”',
        initcap(v_canal), initcap(v_canal), initcap(v_canal) using errcode = 'P0001';
    end if;
  end loop;
  if p_imagem is null or p_imagem not like 'data:image/jpeg;base64,%' or length(p_imagem) > 3000000 then
    raise exception 'RADAR135: falta a imagem (JPEG) da publicação' using errcode = 'P0001';
  end if;
  -- o site: confere tudo o que a autorização do site confere (perfil, aprovação, fundamentação, texto da tela, marcas)
  v_site := public.radar_autorizar_site(p_conteudo, p_categoria, p_lido);
  select * into v_c from public.radar_conteudos c where c.id = p_conteudo;
  v_pendencia := public.radar_marcas_verificar(coalesce(p_legenda_instagram, '') || E'\n' || coalesce(p_legenda_facebook, ''));
  if v_pendencia is not null then
    raise exception '%', v_pendencia using errcode = 'P0001';
  end if;
  if public.radar_copia_paga_assunto(v_c.assunto_id, array[p_legenda_instagram, p_legenda_facebook]) then      -- v0.22.0 (varredura geral)
    raise exception 'RADAR146: frase do boletim pago (ITC) na legenda: reescreva com palavras próprias (o boletim pago nunca é reproduzido, nem citando a fonte nem entre aspas)' using errcode = 'P0001';
  end if;
  foreach v_canal in array array['instagram','facebook'] loop
    v_legenda := btrim(coalesce(case v_canal when 'instagram' then p_legenda_instagram else p_legenda_facebook end, ''));
    continue when v_legenda = '';
    insert into public.radar_redes_envios (conteudo_id, canal, legenda, imagem, conteudo_lido_em, situacao, junto_com_site, autorizado_por)
    values (p_conteudo, v_canal, v_legenda, p_imagem, v_c.atualizado_em, 'aguardando_site', true, auth.uid())
    returning id into v_id;
    v_ids := v_ids || jsonb_build_object(v_canal, v_id);
  end loop;
  return jsonb_build_object('site', v_site) || v_ids;
end $$;

-- v0.17.0: o site não saiu (autorização cancelada, ou o robô não conseguiu): o Instagram e o Facebook que iam junto caem também
create or replace function public.radar_fn_site_envio_redes() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.situacao in ('cancelado','erro') and new.situacao is distinct from old.situacao then
    update public.radar_redes_envios
       set situacao = 'cancelado', cancelado_em = now(), atualizado_em = now(), imagem = null,
           erro = 'A publicação no site não saiu' || case when new.situacao = 'erro' then ' (o robô não conseguiu)' else ' (autorização cancelada)' end ||
                  ': a deste canal, que ia junto, foi cancelada. Confira e autorize de novo.'
     where conteudo_id = new.conteudo_id and situacao = 'aguardando_site';
  end if;
  return null;
end $$;

-- v0.17.0: publicação apagada do Instagram ou do Facebook. A função radar-redes chama depois que a Meta confirmou a
-- exclusão ("api"); o administrador chama quando apagou direto na rede ("manual"). Depois disso dá para publicar de novo.
create or replace function public.radar_rede_marcar_excluida(p_envio bigint, p_como text) returns boolean
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR130: só o administrador mexe nas publicações do Instagram e do Facebook' using errcode = '42501';
  end if;
  if p_como is null or p_como not in ('api','manual') then
    raise exception 'RADAR155: informe como a publicação foi excluída' using errcode = 'P0001';
  end if;
  update public.radar_redes_envios
     set situacao = 'excluido', excluido_em = now(), excluido_por = auth.uid(), excluido_como = p_como, imagem = null, atualizado_em = now()
   where id = p_envio and situacao = 'publicado';
  if not found then
    raise exception 'RADAR156: esta publicação não está publicada (já foi excluída ou não existe)' using errcode = 'P0001';
  end if;
  return true;
end $$;

-- ---------------------------------------------------------------- v0.21.0: Pauta (peças das redes) e publicação agendada
-- "Hoje" da Pauta é sempre o dia de Brasília: nenhuma função da Pauta usa current_date (o dia do servidor, em UTC, vira às 21h).
create or replace function public.radar_pauta_hoje() returns date
language sql stable set search_path = public as $$
  select (now() at time zone 'America/Sao_Paulo')::date
$$;

-- Texto para comparar palavras: minúsculas, sem acento e só letras e algarismos, separados por um espaço
-- (os acentos maiúsculos também: o resultado não depende da configuração de idioma do servidor)
create or replace function public.radar_pauta_normalizar(p text) returns text
language sql immutable set search_path = public as $$
  select btrim(regexp_replace(lower(translate(coalesce(p, ''),
           'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ', 'AAAAAEEEEIIIIOOOOOUUUUCNaaaaaeeeeiiiiooooouuuucn')),
           '[^a-z0-9]+', ' ', 'g'))
$$;

-- Texto para achar o nome de uma pessoa: em NFC (o texto colado do Mac vem em NFD, com o acento separado da letra) e sem acento,
-- COM a maiúscula ("Lúcia" e "Lucia" ficam "Lucia"; "LÚCIA", "LUCIA")
create or replace function public.radar_pauta_sem_acento(p text) returns text
language sql immutable set search_path = public as $$
  select translate(normalize(coalesce(p, ''), NFC), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ',
                   'AAAAAEEEEIIIIOOOOOUUUUCNaaaaaeeeeiiiiooooouuuucn')
$$;

-- A expressão que acha um nome de pessoa no texto de radar_pauta_sem_acento: palavra inteira, o nome sem acento e escapado, com
-- qualquer espaço entre as palavras, como está cadastrado ("Lucia Exemplo") ou todo em maiúsculas ("LUCIA EXEMPLO", a chamada em
-- caixa alta). Com a maiúscula: "a rosa do jardim" não é a Rosa.
create or replace function public.radar_pauta_rx_nome(p text) returns text
language sql immutable set search_path = public as $$
  select '(?<![A-Za-zÀ-ÿ0-9])(?:' || string_agg(regexp_replace(regexp_replace(x, '([^[:alnum:][:space:]])', '\\\1', 'g'), '\s+', '\\s+', 'g'), '|')
         || ')(?![A-Za-zÀ-ÿ0-9])'
    from (select distinct x from unnest(array[btrim(public.radar_pauta_sem_acento(p)), upper(btrim(public.radar_pauta_sem_acento(p)))]) x) t
$$;

-- Configurações → Pauta → "janela_horas": passado esse tempo da hora marcada, a peça vira erro em vez de sair atrasada
-- (de 1 a 48; fora disso, ou sem a chave, vale 6: nada do que está ali trava a agenda)
create or replace function public.radar_pauta_janela() returns int
language sql stable set search_path = public as $$
  select coalesce((select case when jsonb_typeof(c.valor->'janela_horas') = 'number'
                               then least(greatest((c.valor->>'janela_horas')::numeric, 1), 48)::int end
                     from public.radar_config c where c.chave = 'pauta'), 6)
$$;

-- Os canais da peça que têm legenda escrita (os que vão ao ar, quando a tela não diz quais)
create or replace function public.radar_pauta_canais(p_instagram text, p_facebook text) returns text[]
language sql immutable set search_path = public as $$
  select array_remove(array[case when btrim(coalesce(p_instagram, '')) <> '' then 'instagram' end,
                            case when btrim(coalesce(p_facebook, '')) <> '' then 'facebook' end], null)
$$;

-- A identificação legal (Configurações → Assinatura: empresa, CNPJ e CRC) está no texto? Compara só as letras e os algarismos,
-- em maiúsculas: a formatação da linha (linhaIdentificacao, na tela) não precisa ser refeita aqui. NULL = está.
-- v0.22.0 (varredura geral): o registro no CRC das Configurações como a tela o escreve (crcFormatado, index.html: "CRC-SC 007129/O-0";
-- o zero da categoria vira a letra O; o formato antigo "1SC007129/O-0" ganha o "CRC " na frente) e, dele, a expressão que o acha num
-- texto em maiúsculas sem acento: cada parte (CRC, SC, 007129, O, 0) na ordem, com qualquer separador entre elas e sem letra ou
-- algarismo colado nas pontas. Rodada 2: sem acento (radar_pauta_sem_acento), como o texto que ela confere ("CRC-SC 007129/O-0
-- (Originário)" virava "ORIGIN" + "RIO" e nunca casava com o "ORIGINARIO" do texto: nenhuma peça era aprovada)
create or replace function public.radar_crc_padrao(p_crc text) returns text
language plpgsql immutable set search_path = public as $$
declare
  t text := regexp_replace(btrim(public.radar_pauta_sem_acento(p_crc)), '\s+', ' ', 'g');
  m text[];
  f text;
begin
  m := regexp_match(t, '^(?:CRC\s*[-/]?\s*)?(?:SC\s*[-/]?\s*)?([0-9]{4,6})(?:\s*/\s*([0OSTPostp])\s*-?\s*([0-9]))?$', 'i');
  if m is not null then
    f := 'CRC-SC ' || m[1] || case when m[2] is not null then '/' || case when m[2] = '0' then 'O' else upper(m[2]) end || '-' || m[3] else '' end;
  elsif t ~* '^[0-9]?SC\s*[0-9]{4,6}\s*/\s*[0OSTP]\s*-?\s*[0-9]$' then
    f := 'CRC ' || regexp_replace(upper(t), '/(\s*)0', '/\1O');
  else
    f := regexp_replace(t, '/0(?=\s*-\s*[0-9](?![0-9]))', '/O', 'g');
  end if;
  return '(^|[^A-Z0-9])' || array_to_string(array(select x from regexp_split_to_table(upper(f), '[^A-Z0-9]+') x where x <> ''), '[^A-Z0-9]*')
         || '($|[^A-Z0-9])';
end $$;

create or replace function public.radar_pauta_identificacao_falta(p_texto text) returns text
language plpgsql stable set search_path = public as $$
declare
  v      jsonb := (select c.valor from public.radar_config c where c.chave = 'assinatura');
  v_emp  text;
  v_cnpj text;
  v_crc  text;
  v_txt  text;
begin
  v_emp  := upper(regexp_replace(translate(coalesce(v->>'empresa', ''), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ',
                                           'AAAAAEEEEIIIIOOOOOUUUUCNaaaaaeeeeiiiiooooouuuucn'), '[^A-Za-z0-9]', '', 'g'));
  v_cnpj := upper(regexp_replace(coalesce(v->>'cnpj', ''), '[[:space:]./-]', '', 'g'));
  v_crc  := substring(coalesce(v->>'crc', '') from '[0-9]{4,6}');
  if v_emp = '' or v_cnpj !~ '^[0-9A-Z]{12}[0-9]{2}$' or v_crc is null then
    return 'Identificação legal incompleta: preencha o CNPJ e o CRC em Configurações → Assinatura';
  end if;
  v_txt := upper(regexp_replace(translate(coalesce(p_texto, ''), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ',
                                          'AAAAAEEEEIIIIOOOOOUUUUCNaaaaaeeeeiiiiooooouuuucn'), '[^A-Za-z0-9]', '', 'g'));
  -- v0.22.0 (varredura geral): o registro no CRC inteiro, como a tela o escreve (crcFormatado: "CRC-SC 007129/O-0"), com a UF e a
  -- categoria, e não só os algarismos em qualquer ponto do texto ("CRC-PR 007129/O-5", "007129/0-0" com zero no lugar da letra O
  -- ou um telefone com os mesmos algarismos passavam). Entre as partes, qualquer separador ("CRC/SC 007129 / O-0" vale).
  if strpos(v_txt, v_emp) = 0 or strpos(v_txt, v_cnpj) = 0
     or upper(public.radar_pauta_sem_acento(p_texto)) !~ public.radar_crc_padrao(v->>'crc') then
    return 'falta a linha de identificação (empresa, CNPJ e CRC de Configurações → Assinatura)';
  end if;
  return null;
end $$;

-- Os números de um texto como estão escritos (com os zeros à esquerda: "0530"), sem o número de item de lista ("1. Revise"),
-- com "1.000" = "1000" e "1.500,00" = "1500". Não lê número por extenso.
create or replace function public.radar_pauta_numeros_escritos(p text) returns text[]
language sql immutable set search_path = public as $$
  select coalesce(array_agg(m[1]), '{}')
    from regexp_matches(regexp_replace(regexp_replace(regexp_replace(coalesce(p, ''),
                          '^[[:blank:]]*[0-9]{1,2}[.)][[:blank:]]', '', 'gn'),
                          '([0-9])\.(?=[0-9]{3}(?![0-9]))', '\1', 'g'),
                          '([0-9]),00(?![0-9])', '\1', 'g'),
                        '([0-9]+(?:,[0-9]+)?)', 'g') as m
$$;

-- Os números de um texto como a tela os compara (numerosForaDoTexto, index.html): os de radar_pauta_numeros_escritos, sem os
-- zeros à esquerda ("05" = "5") e sem repetir.
create or replace function public.radar_pauta_numeros(p text) returns text[]
language sql immutable set search_path = public as $$
  select coalesce(array_agg(distinct regexp_replace(n, '^0+(?=[0-9])', '')), '{}') from unnest(public.radar_pauta_numeros_escritos(p)) n
$$;

-- Números dos textos que vão ao ar e que não estão na base: as informações conferidas e o registro no CRC das pessoas marcadas
-- (p_base), mais o que as Configurações já trazem conferido — a empresa, o CNPJ (como está e formatado) e o CRC da Assinatura, que
-- entram na linha de identificação; os telefones do Fale Conosco; e os "fatos_fixos" da Pauta que têm fonte (ex.: "desde 1984").
-- O link e as hashtags não contam. Cada número volta como está escrito no texto ("0530", não "530"), sem repetir.
create or replace function public.radar_pauta_numeros_fora(p_textos text, p_base text) returns text[]
language plpgsql stable set search_path = public as $$
declare
  v      jsonb := (select c.valor from public.radar_config c where c.chave = 'assinatura');
  v_fale jsonb := (select c.valor from public.radar_config c where c.chave = 'fale_conosco');
  v_fixo jsonb := (select c.valor->'fatos_fixos' from public.radar_config c where c.chave = 'pauta');
  v_cnpj text  := upper(regexp_replace(coalesce(v->>'cnpj', ''), '[[:space:]./-]', '', 'g'));
  v_base text[];
begin
  v_base := public.radar_pauta_numeros(concat_ws(E'\n', p_base, v->>'empresa', v->>'cnpj', v->>'crc',
              case when v_cnpj ~ '^[0-9A-Z]{12}[0-9]{2}$' then regexp_replace(v_cnpj, '^(..)(...)(...)(....)(..)$', '\1.\2.\3/\4-\5') end,
              -- os telefones do Fale Conosco: dos setores ("48-3242-0530" ou {"numero": …}) e dos responsáveis ({"telefone": …})
              (select string_agg(case jsonb_typeof(t) when 'string' then t #>> '{}' when 'object' then concat_ws(' ', t->>'numero', t->>'telefone') end, E'\n')
                 from (select jsonb_path_query(coalesce(v_fale, '{}'), 'lax $.setores[*].telefones[*]')
                       union all select jsonb_path_query(coalesce(v_fale, '{}'), 'lax $.setores[*].responsaveis[*]')) x(t)),
              -- Configurações → Pauta → "fatos_fixos": [{"informacao", "fonte"}], só os que têm a fonte escrita
              (select string_agg(f->>'informacao', E'\n')
                 from jsonb_array_elements(case when jsonb_typeof(v_fixo) = 'array' then v_fixo else '[]' end) f
                where jsonb_typeof(f) = 'object' and jsonb_typeof(f->'informacao') = 'string' and btrim(coalesce(f->>'fonte', '')) <> '')));
  return coalesce((select array_agg(distinct n order by n)
                     from unnest(public.radar_pauta_numeros_escritos(regexp_replace(coalesce(p_textos, ''), 'https?://[^[:space:]]+|#[[:alnum:]_]+', ' ', 'g'))) n
                    where not regexp_replace(n, '^0+(?=[0-9])', '') = any(v_base)), '{}');
end $$;

-- Rodada 2 da varredura geral: a matéria do boletim que é o próprio ato oficial ("Legislação Federal - Últimas Publicações": a
-- radar-itc e a rotina gravam título = o nome do ato com o Diário Oficial e a data, "Lei nº 15526/2026 (DOU DE 30/09/2026)", e
-- texto = a ementa) não é texto da ITC: é a ementa oficial, de domínio público (Lei 9.610/1998, art. 8º, IV), e a mesma do DOU.
-- Fica fora da base paga: a peça educativa ou o roteiro que copia a ementa do DOU para as "Informações conferidas" não trava como
-- "frase do boletim pago". Só o título que começa pelo nome da norma e termina no Diário Oficial com a data, entre parênteses.
create or replace function public.radar_copia_paga_ato_oficial(p_titulo text) returns boolean
language sql immutable set search_path = public as $$
  select coalesce(p_titulo, '') ~* ('^\s*(?:lei|leis|decreto|decretos|decreto-lei|medida|instru[çc][ãa]o|portaria|resolu[çc][ãa]o|ato|atos'
           || '|solu[çc][ãa]o|parecer|despacho|emenda|delibera[çc][ãa]o|conv[êe]nio|ajuste|protocolo|circular|comunicado|nota|edital'
           || '|retifica[çc][ãa]o)(?![[:alpha:]-]).*\(\s*D\.?\s*O\.?\s*(?:U|E(?:\s*[-/]?\s*SC)?)(?![[:alpha:]])[^()]*'
           || '[0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}\s*\)\s*\.?\s*$')
$$;

-- A base da trava do boletim pago: o texto normalizado de todas as capturas do boletim que estão no banco (nenhuma é apagada e a
-- tela do assunto mostra qualquer uma, de qualquer idade), menos as matérias que são o próprio ato oficial. NULL = não há boletim.
create or replace function public.radar_copia_paga_base() returns text
language sql stable set search_path = public as $$
  select ' ' || string_agg(public.radar_pauta_normalizar(concat_ws(' ', c.titulo, c.resumo_fonte, c.texto)), ' | ') || ' '
    from public.radar_capturas c join public.radar_fontes f on f.id = c.fonte_id
   where f.slug in ('itc-email') and not public.radar_copia_paga_ato_oficial(c.titulo)
$$;

-- As capturas de fonte livre (não pagas) do assunto da notícia: a janela que também está numa delas não conta
create or replace function public.radar_copia_paga_livres(p_assunto bigint) returns text[]
language sql stable set search_path = public as $$
  select array_agg(concat_ws(' ', c.titulo, c.resumo_fonte, c.texto))
    from public.radar_assunto_capturas ac
    join public.radar_capturas c on c.id = ac.captura_id
    join public.radar_fontes f on f.id = c.fonte_id
   where ac.assunto_id = p_assunto and f.slug not in ('itc-email')
$$;

-- Frase do boletim pago (ITC, a mesma lista de FONTES_PAGAS da tela e da radar-ia) num texto: cada campo à parte, em janelas de 12
-- palavras, procuradas na base do boletim (radar_copia_paga_base). Devolve só sim ou não: o trecho do boletim nunca sai daqui (nem
-- para a tela, nem para o log). v0.22.0 (varredura geral): todas as capturas do boletim; antes eram só as dos últimos 90 dias, e
-- uma frase de boletim mais antigo passava sem aviso. p_livres: textos de fonte livre (as capturas não pagas do assunto da
-- notícia); a janela que também está num deles não conta (o dispositivo legal que o boletim copiou do DOU e o texto transcreve da
-- fonte oficial).
create or replace function public.radar_copia_paga(p_textos text[], p_livres text[]) returns boolean
language plpgsql stable set search_path = public as $$
declare
  v_base  text := public.radar_copia_paga_base();
  v_livre text;
  v_t     text;
  v_pal   text[];
  v_jan   text;
  i       int;
begin
  if v_base is null then return false; end if;
  v_livre := coalesce(' ' || (select string_agg(public.radar_pauta_normalizar(l), ' | ') from unnest(p_livres) l) || ' ', '');
  foreach v_t in array coalesce(p_textos, '{}') loop
    v_pal := string_to_array(public.radar_pauta_normalizar(v_t), ' ');
    continue when coalesce(array_length(v_pal, 1), 0) < 12;
    for i in 1 .. array_length(v_pal, 1) - 11 loop
      v_jan := ' ' || array_to_string(v_pal[i:i + 11], ' ') || ' ';
      if strpos(v_base, v_jan) > 0 and strpos(v_livre, v_jan) = 0 then
        return true;
      end if;
    end loop;
  end loop;
  return false;
end $$;

-- A Pauta não tem fonte livre ao lado: qualquer janela do boletim conta (menos a ementa do ato oficial, fora da base)
create or replace function public.radar_pauta_copia_paga(p_textos text[]) returns boolean
language sql stable set search_path = public as $$
  select public.radar_copia_paga(p_textos, '{}')
$$;

-- v0.22.0 (varredura geral): a notícia (site, Instagram e Facebook) também, no banco. A tela já marcava a frase do boletim, mas a
-- trava era só dela (e oferecia "Autorizar mesmo assim"). Descontado o que também está nas capturas livres do assunto.
create or replace function public.radar_copia_paga_assunto(p_assunto bigint, p_textos text[]) returns boolean
language sql stable set search_path = public as $$
  select public.radar_copia_paga(p_textos, public.radar_copia_paga_livres(p_assunto))
$$;

-- Rodada 2 da varredura geral: ONDE, no texto da própria notícia, está o que a trava acima (radar_copia_paga_assunto, RADAR146)
-- recusaria. A tela compara só com as capturas ligadas ao assunto; o banco, com todas as do boletim (de outro assunto ou ainda na
-- fila): sem isto, ela mostrava "✓ nenhum trecho copiado" e o banco recusava sem dizer qual frase. Para cada texto de p_textos
-- (o título e o texto de cada conteúdo, na ordem), a lista das faixas [início, fim) em caracteres do PRÓPRIO texto (contados como o
-- banco conta, um por letra; a tela conta igual), juntando as janelas de 12 palavras encostadas. Mesma regra do banco: as palavras
-- de radar_pauta_normalizar (com números e nomes de norma), a mesma base e o mesmo desconto das capturas livres do assunto. Nada do
-- boletim sai daqui (só posições no texto de quem pede); só o editor e o administrador, como a radar-ia (Revisar com IA).
create or replace function public.radar_copia_paga_trechos(p_assunto bigint, p_textos text[]) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  v_base  text;
  v_livre text;
  v_saida jsonb := '[]';
  v_lista jsonb;
  v_t     text;
  v_pal   text[];
  v_ini   int[];
  v_fim   int[];
  v_jan   text;
  a       int;
  b       int;
  i       int;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR147: só o editor ou o administrador confere o texto contra o boletim pago' using errcode = '42501';
  end if;
  if coalesce(array_length(p_textos, 1), 0) > 60 or exists (select 1 from unnest(p_textos) t where length(t) > 100000) then
    raise exception 'RADAR147: textos demais para conferir de uma vez' using errcode = 'P0001';
  end if;
  v_base := public.radar_copia_paga_base();
  v_livre := coalesce(' ' || (select string_agg(public.radar_pauta_normalizar(l), ' | ')
                                from unnest(public.radar_copia_paga_livres(p_assunto)) l) || ' ', '');
  foreach v_t in array coalesce(p_textos, '{}') loop
    v_lista := '[]';
    if v_base is not null then
      -- as palavras como radar_pauta_normalizar as vê (sem acento, letras e algarismos seguidos), com a posição no texto: o translate
      -- troca letra por letra, então a posição no texto traduzido é a mesma do original
      select array_agg(lower(m.w) order by m.n), array_agg(m.fim - length(m.w) order by m.n), array_agg(m.fim order by m.n)
        into v_pal, v_ini, v_fim
        from (select x.n, x.m[2] as w, sum(length(x.m[1]) + length(x.m[2])) over (order by x.n)::int as fim
                from regexp_matches(translate(coalesce(v_t, ''), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ',
                                              'AAAAAEEEEIIIIOOOOOUUUUCNaaaaaeeeeiiiiooooouuuucn'),
                                    '([^A-Za-z0-9]*)([A-Za-z0-9]+)', 'g') with ordinality x(m, n)) m;
      a := null;
      if coalesce(array_length(v_pal, 1), 0) >= 12 then
        for i in 1 .. array_length(v_pal, 1) - 11 loop
          v_jan := ' ' || array_to_string(v_pal[i:i + 11], ' ') || ' ';
          continue when strpos(v_base, v_jan) = 0 or strpos(v_livre, v_jan) > 0;
          if a is not null and v_ini[i] <= b then
            b := greatest(b, v_fim[i + 11]);
          else
            if a is not null then v_lista := v_lista || jsonb_build_array(jsonb_build_array(a, b)); end if;
            a := v_ini[i]; b := v_fim[i + 11];
          end if;
        end loop;
      end if;
      if a is not null then v_lista := v_lista || jsonb_build_array(jsonb_build_array(a, b)); end if;
    end if;
    v_saida := v_saida || jsonb_build_array(v_lista);
  end loop;
  return v_saida;
end $$;

-- A função radar-ia (ação "peca", com o token de quem pede) confere, antes de chamar a IA, que nada do boletim pago vai junto (o plano
-- e as informações conferidas da peça): só o editor e o administrador; devolve só sim ou não (o trecho do boletim não sai daqui).
create or replace function public.radar_pauta_copia_paga_ia(p_textos text[]) returns boolean
language plpgsql stable security definer set search_path = public as $$
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR159: só o editor ou o administrador mexe na Pauta' using errcode = '42501';
  end if;
  return public.radar_pauta_copia_paga(p_textos);
end $$;

-- O termo de uso de imagem da pessoa vale para a peça (tipo), o canal e o dia? NULL = vale; senão o motivo, sem o nome.
-- Roda como quem chama (security invoker): o leitor não lê radar_pessoas e recebe "pessoa não cadastrada". A finalidade do
-- termo vem do tipo da peça: Quem cuida e Bastidor = apresentar a equipe; Reel, Educativo, Agenda e Notícia = orientação;
-- Data com a equipe = datas da empresa; Captação = captação de clientes.
-- v0.28.0: o(a) sócio(a) da Artecon (radar_pessoas.socio), ativo(a) e maior de idade, não precisa do termo: NULL em todo tipo, canal e dia.
create or replace function public.radar_pauta_termo_ok(p_pessoa bigint, p_tipo text, p_canal text, p_data date) returns text
language plpgsql stable set search_path = public as $$
declare
  v     public.radar_pessoas%rowtype;
  v_uso text := case when p_tipo in ('quem_cuida','bastidor') then 'equipe'
                     when p_tipo in ('reel','educativo','agenda','noticia') then 'orientacao'
                     when p_tipo = 'data_equipe' then 'datas'
                     when p_tipo = 'captacao' then 'captacao' end;
begin
  select * into v from public.radar_pessoas where id = p_pessoa;
  if v.id is null then return 'pessoa não cadastrada'; end if;
  if not v.ativo then return 'pessoa inativa'; end if;
  -- v0.28.0: sócio(a) da Artecon, maior de idade: o termo de uso de imagem não é exigido (nenhuma data, canal ou finalidade do termo é
  -- conferida, nem a revogação: para tirar da Pauta, desmarque "Ativa"). Menor de idade continua precisando do termo
  if v.socio and not v.menor then return null; end if;
  if v.termo_assinado_em is null then return 'sem termo assinado'; end if;
  if p_data is null or v.termo_assinado_em > p_data then return 'termo assinado depois desta data'; end if;
  if v.termo_revogado_em is not null and v.termo_revogado_em <= p_data then return 'termo revogado'; end if;
  if v.termo_valido_ate is not null and v.termo_valido_ate < p_data then return 'termo vencido'; end if;
  if p_canal is null or not p_canal = any(v.termo_canais) then return 'canal não autorizado no termo'; end if;
  if v_uso is null or not v_uso = any(v.termo_usos) then return 'finalidade não autorizada no termo'; end if;
  return null;
end $$;

-- Tudo o que impede a peça de ficar pronta ou de ser aprovada, numa lista: a tela mostra (radar_pauta_conferir) e as funções
-- travam com ela. p_canais: os canais que vão ao ar; p_data: o dia da peça. A lista pode citar o nome da pessoa: volta só para
-- a tela, nunca vai num raise nem é gravada.
create or replace function public.radar_pauta_problemas(p_peca bigint, p_canais text[], p_data date) returns text[]
language plpgsql stable set search_path = public as $$
declare
  p          public.radar_pauta_pecas%rowtype;
  v          text[] := '{}';
  v_canais   text[];
  v_canal    text;
  v_leg      text;
  v_textos   text[] := '{}';     -- o que vai ao ar, cada campo à parte (legendas, chamada, apoio, roteiro e cada cartão)
  v_tudo     text;
  v_lista    text[] := '{}';     -- na Agenda da semana em Imagem 4:5, a lista desenhada na lâmina (a informação de cada conferida)
  v_ar       text;               -- tudo o que vai ao ar: v_tudo e a lista da lâmina
  v_cmp      text;               -- v_ar para achar nome: em NFC e sem acento, com a maiúscula (radar_pauta_sem_acento)
  v_num      text;               -- v_tudo para contar os números (o roteiro sem as marcações de tempo)
  v_base     text;
  v_x        text;
  v_i        bigint;
  v_item     jsonb;
  v_pe       public.radar_pessoas%rowtype;
  v_vid      public.radar_videos%rowtype;    -- v0.22.0: o vídeo vivo do reel
  v_marcadas text[];             -- os nomes das pessoas marcadas, sem acento (o xará que não está marcado não é acusado por eles)
  v_forma    text;
  v_n        text;
  -- começo e fim de palavra, com acento, sem depender do idioma do servidor
  b constant text := '(?<![A-Za-zÀ-ÿ0-9])';
  e constant text := '(?![A-Za-zÀ-ÿ0-9])';
  v_contador text := b || public.radar_rx_termo('contador') || '(?:[aA]|\([aA]\))?' || e;
  v_tecnico  text := b || public.radar_rx_termo('tecnic') || '(?:[oO]\([aA]\)|[oaOA])' || e;
  v_espec    text := b || public.radar_rx_termo('especialista') || '[sS]?' || e;
begin
  select * into p from public.radar_pauta_pecas where id = p_peca;
  if p.id is null then return array['Peça não encontrada.']; end if;
  select coalesce(array_agg(distinct c), '{}') into v_canais from unnest(coalesce(p_canais, '{}')) c;
  -- 1. tipo e formato
  if p.tipo = 'noticia' then v := array_append(v, 'Dia de notícia: publique por Assuntos ou Publicações'); end if;
  if p.tipo = 'sem_post' or p.formato in ('story','nenhum') then v := array_append(v, 'Sem publicação pela Pauta nesta versão'); end if;
  if p.tipo = 'quem_cuida' and cardinality(p.pessoas) = 0 then v := array_append(v, 'Quem cuida: marque a pessoa em Quem aparece'); end if;
  if p.formato = 'foto' and cardinality(p.fotos) = 0 then v := array_append(v, 'Foto: envie a foto da peça'); end if;
  if p.formato = 'carrossel_fotos' and cardinality(p.fotos) not between 2 and 10 then
    v := array_append(v, 'Carrossel de fotos: envie de 2 a 10 fotos');
  end if;
  -- no carrossel de fotos, o cartão vai na lâmina da foto da mesma ordem: o que passa do número de fotos não aparece em lâmina nenhuma
  if p.formato = 'carrossel_fotos' and cardinality(p.fotos) > 0 and jsonb_array_length(p.cartoes) > cardinality(p.fotos) then
    v := array_append(v, format('Carrossel de fotos: o cartão nº %s não tem foto (a peça tem %s): tire o cartão ou envie mais uma foto',
                                cardinality(p.fotos) + 1, cardinality(p.fotos)));
  end if;
  if p.formato = 'carrossel' and jsonb_array_length(p.cartoes) not between 2 and 9 then
    v := array_append(v, 'Carrossel: escreva de 2 a 9 cartões');
  end if;
  if p.formato = 'reel' and btrim(p.roteiro) = '' then v := array_append(v, 'Reel: cole o roteiro'); end if;
  -- v0.22.0: o reel só fica pronto (e só é aprovado) com o vídeo corrigido pronto e em dia com a peça
  if p.formato = 'reel' then
    v_x := public.radar_video_pendencia(p.id);
    if v_x is not null then v := array_append(v, v_x); end if;
  end if;
  if p.tipo = 'agenda' and jsonb_array_length(p.conferidas) = 0 then
    v := array_append(v, 'Agenda da semana: calcule a agenda e confira as datas (Informações conferidas)');
  end if;
  for v_item, v_i in select c, o from jsonb_array_elements(p.cartoes) with ordinality t(c, o) loop
    if jsonb_typeof(v_item) is distinct from 'object' or coalesce(jsonb_typeof(v_item->'titulo'), 'string') not in ('string','null')
       or coalesce(jsonb_typeof(v_item->'texto'), 'string') not in ('string','null') then
      v := array_append(v, 'Cartão nº ' || v_i || ': título e texto em formato inválido');
    end if;
  end loop;
  -- 2. canais e legendas; 3. identificação legal em cada legenda
  if cardinality(v_canais) = 0 then v := array_append(v, 'Escolha ao menos um canal (escreva a legenda do Instagram ou do Facebook)'); end if;
  foreach v_canal in array v_canais loop
    if v_canal not in ('instagram','facebook') then v := array_append(v, 'Canal desconhecido'); continue; end if;
    v_leg := case v_canal when 'instagram' then p.legenda_instagram else p.legenda_facebook end;
    if length(btrim(v_leg)) not between 10 and 2200 then
      v := array_append(v, 'Legenda do ' || initcap(v_canal) || ': de 10 a 2.200 caracteres');
    end if;
    v_x := public.radar_pauta_identificacao_falta(v_leg);
    if v_x like 'Identificação legal incompleta%' then
      if not v_x = any(v) then v := array_append(v, v_x); end if;
    elsif v_x is not null then
      v := array_append(v, 'Legenda do ' || initcap(v_canal) || ': ' || v_x);
    end if;
    v_textos := array_append(v_textos, v_leg);
  end loop;
  v_textos := v_textos || array[p.chamada, p.apoio]
              || coalesce((select array_agg(concat_ws(E'\n', c->>'titulo', c->>'texto') order by o)
                             from jsonb_array_elements(p.cartoes) with ordinality t(c, o) where jsonb_typeof(c) = 'object'), '{}');
  -- v0.22.0: o que o vídeo do reel leva ao ar — a fala (o texto final da legenda gravada), o texto do gancho gravado de 0 a 3 s (a cópia
  -- da chamada no envio, que pode ser diferente da chamada de hoje), as linhas da cartela e o texto extra dela que o robô gravou (o do
  -- relatório; o das Configurações só no relatório sem ele) — passa pelas mesmas travas do resto: boletim pago, números, nomes,
  -- marcadores e "contador" sem registro. É o texto que está no vídeo, e não o da peça ou das Configurações de hoje
  if p.formato = 'reel' then
    select * into v_vid from public.radar_videos
     where peca_id = p.id and situacao in ('pronto','regravar') order by versao desc limit 1;
    if v_vid.id is not null then
      v_textos := v_textos || array[coalesce(v_vid.relatorio->>'texto_final', ''), array_to_string(v_vid.cartela_linhas, E'\n'),
                                    case when v_vid.relatorio ? 'cartela_extra' then coalesce(v_vid.relatorio->>'cartela_extra', '')
                                         else public.radar_video_cfg_texto('cartela_extra') end,
                                    case when v_vid.ajustes->'sem_gancho' is distinct from 'true'::jsonb then coalesce(v_vid.gancho, '') else '' end];
    end if;
  end if;
  -- os números, sem os do marcador entre chaves ({PESSOA2}: a trava do marcador já pega) e, no roteiro do reel, sem as marcações da
  -- gravação ("0 a 3 s", "cerca de 44 segundos", "0:15", "110 palavras"): o tempo de cada cena não é fato que vai ao ar
  v_num := regexp_replace(array_to_string(v_textos, E'\n') || E'\n'
             || regexp_replace(p.roteiro, '[0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?|(?<![0-9.,])[0-9]+(?:,[0-9]+)?(?:[[:blank:]]*(?:a|até|–|-)[[:blank:]]*[0-9]+(?:,[0-9]+)?)?'
                                       '[[:blank:]]*(?:s|seg|segundos?|palavras)(?![A-Za-zÀ-ÿ0-9])', ' ', 'gi'),
             '\{[^{}\n]{1,120}\}', ' ', 'g');
  v_textos := array_append(v_textos, p.roteiro);
  v_tudo := array_to_string(v_textos, E'\n');
  -- a Agenda da semana em Imagem 4:5 desenha na lâmina a informação de cada conferida (laminasPeca, em radar-pauta.js): a lista vai
  -- ao ar e passa pelas mesmas travas de marca, de chaves e de nome (os números dela são a própria base)
  if p.tipo = 'agenda' and p.formato = 'imagem' then
    v_lista := coalesce((select array_agg(c->>'informacao' order by o) from jsonb_array_elements(p.conferidas) with ordinality t(c, o)
                          where jsonb_typeof(c) = 'object' and jsonb_typeof(c->'informacao') = 'string'), '{}');
  end if;
  v_ar := array_to_string(array_append(v_lista, v_tudo), E'\n');
  v_cmp := public.radar_pauta_sem_acento(v_ar);
  -- 4. marcas: [VERIFICAR …], {confirmar …} (a IA marca o fato que não está nas informações conferidas) e qualquer outro marcador
  --    dos modelos do plano entre chaves ({formação}, {ano de entrada}, {PESSOA2}…), que iria ao ar escrito assim
  v_x := public.radar_marcas_verificar(v_ar);
  if v_x is not null then v := array_append(v, regexp_replace(v_x, '^RADAR139: ', '')); end if;
  if v_ar ~* '\{\s*confirmar[^}]*\}' then
    v := array_append(v, 'Há {confirmar …} no texto: troque pela informação conferida (ou tire o trecho)');
  end if;
  if regexp_replace(v_ar, '\{\s*confirmar[^}]*\}', ' ', 'gi') ~ '\{[^{}\n]{1,120}\}' then
    v := array_append(v, 'Há marcador do modelo entre chaves ({…}): troque pelo texto ou tire');
  end if;
  -- "(conferir)": a marca de que falta conferir (no texto colado, ou na fonte escrita à mão) não vai ao ar
  if v_tudo ~* '\(\s*conferir\s*\)' then
    v := array_append(v, 'Há “(conferir)” no texto: confira na fonte oficial e tire a marca');
  end if;
  -- 5. informações conferidas: informação e fonte, e a fonte nunca é o boletim pago
  for v_item, v_i in select c, o from jsonb_array_elements(p.conferidas) with ordinality t(c, o) loop
    if jsonb_typeof(v_item) is distinct from 'object' or jsonb_typeof(v_item->'informacao') is distinct from 'string'
       or jsonb_typeof(v_item->'fonte') is distinct from 'string'
       or length(btrim(v_item->>'informacao')) not between 1 and 300 or length(btrim(v_item->>'fonte')) not between 1 and 300 then
      v := array_append(v, 'Informação conferida nº ' || v_i || ': escreva a informação e a fonte (até 300 caracteres cada)');
    elsif (v_item->>'fonte') ~* '\mITC\M|itcnet|i\.t\.c\.|boletim pago' then
      v := array_append(v, 'Informação conferida nº ' || v_i || ': use a fonte oficial (o boletim pago da ITC não é fonte)');
    elsif concat_ws(E'\n', v_item->>'informacao', v_item->>'fonte') ~* '\(\s*conferir\s*\)' then
      v := array_append(v, 'Informação conferida nº ' || v_i || ': troque “(conferir)” pela fonte oficial em que a informação foi conferida');
    end if;
  end loop;
  -- a base dos números: as informações conferidas e o registro no CRC das pessoas marcadas ("Ana, contadora · CRC-SC 012345")
  v_base := concat_ws(E'\n', (select string_agg(concat_ws(E'\n', c->>'informacao', c->>'fonte'), E'\n')
                                from jsonb_array_elements(p.conferidas) c where jsonb_typeof(c) = 'object'),
                      (select string_agg(pe.crc, E'\n') from public.radar_pessoas pe where pe.id = any(p.pessoas)));
  -- 6. boletim pago: só sim ou não (o trecho não aparece)
  if public.radar_pauta_copia_paga(v_textos || coalesce((select array_agg(c->>'informacao') from jsonb_array_elements(p.conferidas) c
                                                          where jsonb_typeof(c) = 'object'), '{}')) then
    v := array_append(v, 'Há frase igual à do boletim pago (ITC): reescreva com palavras próprias');
  end if;
  -- 7. números que não estão nas informações conferidas (como estão escritos no texto)
  v_x := array_to_string(public.radar_pauta_numeros_fora(v_num, v_base), ', ');
  if v_x <> '' then
    v := array_append(v, 'Números que não estão nas informações conferidas: ' || v_x || '. Acrescente cada um em Informações conferidas, com a fonte (ou tire do texto)');
  end if;
  -- 8. o termo de cada pessoa marcada, em cada canal, no dia da peça (v0.22.0: no reel, também a que estava marcada quando o vídeo foi
  --    gravado e foi desmarcada depois: ela continua no vídeo; v0.28.0: o(a) sócio(a) da Artecon passa por radar_pauta_termo_ok)
  foreach v_i in array p.pessoas || array(select x from unnest(coalesce(v_vid.pessoas, '{}')) x where not x = any(p.pessoas)) loop
    select * into v_pe from public.radar_pessoas where id = v_i;
    foreach v_canal in array v_canais loop
      continue when v_canal not in ('instagram','facebook');
      v_x := public.radar_pauta_termo_ok(v_i, p.tipo, v_canal, p_data);
      if v_x is not null then
        v_x := '“' || coalesce(v_pe.nome_na_peca, 'pessoa nº ' || v_i) || '” (' || initcap(v_canal) || '): ' || v_x;
        if not v_x = any(v) then v := array_append(v, v_x); end if;
      end if;
    end loop;
  end loop;
  -- 9. nome no texto: de toda pessoa, ativa ou não (palavra inteira, com a maiúscula, sem diferença de acento nem de NFC/NFD, e
  --    também em caixa alta: radar_pauta_rx_nome no texto sem acento)
  select coalesce(array_agg(distinct public.radar_pauta_sem_acento(x)), '{}') into v_marcadas
    from public.radar_pessoas pe
         cross join lateral unnest(array[btrim(pe.nome_na_peca), btrim(pe.nome), split_part(btrim(pe.nome), ' ', 1)]) x
   where pe.id = any(p.pessoas);
  for v_pe in select * from public.radar_pessoas order by id loop
    if v_pe.id = any(p.pessoas) then
      -- marcada: a palavra do nome completo (com maiúscula e 3 letras ou mais) que o termo não autoriza é sobrenome a tirar. v0.28.0:
      -- sócio(a) da Artecon (maior de idade) não tem termo: o recado fala do "Nome na peça" do cadastro (a regra é a mesma)
      if exists (select 1 from regexp_split_to_table(btrim(v_pe.nome), '\s+') w
                  where length(w) >= 3 and w ~ '^[A-ZÀ-Ý]'
                    and not public.radar_pauta_sem_acento(w) = any(regexp_split_to_array(public.radar_pauta_sem_acento(btrim(v_pe.nome_na_peca)), '\s+'))
                    and v_cmp ~ public.radar_pauta_rx_nome(w)) then
        v := array_append(v, case when v_pe.socio and not v_pe.menor
          then 'O “Nome na peça” do(a) sócio(a) é só “' || btrim(v_pe.nome_na_peca) || '”: tire o sobrenome (ou mude o Nome na peça em Pessoas e termos)'
          else 'O termo autoriza só “' || btrim(v_pe.nome_na_peca) || '”: tire o sobrenome' end);
      end if;
    else
      for v_forma in select x from unnest(array[btrim(v_pe.nome_na_peca), btrim(v_pe.nome),
                                                case when length(split_part(btrim(v_pe.nome), ' ', 1)) >= 3 then split_part(btrim(v_pe.nome), ' ', 1) end]) x
                      where x is not null and not public.radar_pauta_sem_acento(x) = any(v_marcadas) loop
        if v_cmp ~ public.radar_pauta_rx_nome(v_forma) then
          v := array_append(v, '“' || v_forma || '” aparece no texto e não está marcada em Quem aparece');
          exit;
        end if;
      end loop;
    end if;
    -- 10. "contador(a)", "técnico(a)" e "especialista" a até uns 40 caracteres do nome na peça, conforme o registro da pessoa (o
    --     nome sem diferença de maiúscula: a palavra vizinha já evita confundir com uma palavra comum)
    v_n := public.radar_pauta_rx_nome(v_pe.nome_na_peca);
    continue when not v_cmp ~* v_n;
    if v_pe.categoria = ''
       and v_cmp ~* ('(?:' || v_n || ')[^\n]{0,40}(?:' || v_contador || '|' || v_tecnico || ')|(?:' || v_contador || '|' || v_tecnico || ')[^\n]{0,40}(?:' || v_n || ')') then
      v := array_append(v, '“' || btrim(v_pe.nome_na_peca) || '” não tem registro no CRC (Pauta → Pessoas e termos): não chame de contador(a) nem de técnico(a)');
    end if;
    if v_pe.categoria in ('tecnico','tecnica')
       and v_cmp ~* ('(?:' || v_n || ')[^\n]{0,40}(?:' || v_contador || ')|(?:' || v_contador || ')[^\n]{0,40}(?:' || v_n || ')') then
      v := array_append(v, '“' || btrim(v_pe.nome_na_peca) || '” é técnico(a) em contabilidade: não chame de contador(a)');
    end if;
    if v_cmp ~* ('(?:' || v_n || ')[^\n]{0,40}(?:' || v_espec || ')|(?:' || v_espec || ')[^\n]{0,40}(?:' || v_n || ')') then
      v := array_append(v, '“especialista” perto de “' || btrim(v_pe.nome_na_peca) || '”: não há título de especialista registrado, tire a palavra');
    end if;
  end loop;
  return v;
end $$;

-- A peça da Pauta. Quem grava direto (a tela, com o papel de editor ou administrador) mexe nos textos, nas fotos, nas pessoas,
-- nas informações conferidas, na hora, no plano e na sugestão da IA. A situação só muda nas transições abaixo; a aprovação, as
-- lâminas aprovadas, os links e o registro manual só mudam pelas funções radar_pauta_* (marca radar.pauta, como em
-- radar.autorizando_copia). Mudou o que vai ao ar: a versao_publicavel muda (é ela que a publicação agendada confere). v0.22.0: o vídeo
-- amarrado na aprovação (video_id, video_sha256) também só muda pelas funções.
--   planejada → em_producao (sozinha, ao mudar o que vai ao ar); planejada | em_producao | pronta → cancelada → (Reabrir) planejada;
--   em_producao → pronta (radar_pauta_marcar_pronta); pronta → em_producao (ao mudar o que vai ao ar, ou "Voltar para produção");
--   pronta → aprovada (radar_pauta_aprovar, só o administrador); aprovada → pronta (radar_pauta_desaprovar).
-- Peça aprovada (ou cancelada) não muda o que vai ao ar nem a hora: desfaça a aprovação (ou reabra) antes.
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
    v_mudou := new.data is distinct from old.data or new.tipo is distinct from old.tipo or new.formato is distinct from old.formato
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

-- Pessoa que está numa peça não se apaga (para tirá-la das próximas, desmarque "Ativa"). Da peça cancelada ela sai junto.
create or replace function public.radar_fn_pessoa_apagar() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if exists (select 1 from public.radar_pauta_pecas p where old.id = any(p.pessoas) and p.situacao <> 'cancelada') then
    raise exception 'RADAR174: esta pessoa está numa peça da Pauta: para tirá-la das próximas, desmarque “Ativa”' using errcode = 'P0001';
  end if;
  -- v0.22.0 (varredura geral): nem num vídeo do corretor que ainda guarda arquivos ou textos (desmarcada na peça, ela continua no
  -- vídeo enviado). Apagada, a limpeza não saberia que é dela, e os links a retirar das redes sumiriam da tela: o caminho é marcar a
  -- revogação do termo (ou desmarcar “Ativa”), que apaga o vídeo dela na limpeza seguinte
  if exists (select 1 from public.radar_videos v
              where (old.id = any(v.pessoas) or v.fala_pessoa = old.id)
                and not v.arquivos_apagados @> array['bruto','trabalho','corrigido','textos']) then
    raise exception 'RADAR174: esta pessoa está num vídeo do corretor que ainda tem arquivos guardados: marque a revogação do termo (ou desmarque “Ativa”) e a limpeza apaga o vídeo dela' using errcode = 'P0001';
  end if;
  perform set_config('radar.pauta', '1', true);
  update public.radar_pauta_pecas set pessoas = array_remove(pessoas, old.id) where old.id = any(pessoas);
  perform set_config('radar.pauta', '', true);
  return old;
end $$;

-- v0.28.0: a conferência de uma linha do calendário, a mesma na importação (radar_pauta_importar) e na "+ Nova peça" (radar_pauta_criar):
-- NULL = vale; senão o campo inválido (nunca o conteúdo). Em plpgsql (e não em sql) de propósito: assim a data só é convertida depois de
-- conferida ("2026-02-30" volta 'data', sem erro).
create or replace function public.radar_pauta_linha_invalida(x jsonb) returns text
language plpgsql stable set search_path = public as $$
begin
  return case
    when jsonb_typeof(x) is distinct from 'object' then 'linha'
    when coalesce(x->>'data', '') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' or not public.radar_data_valida(x->>'data') then 'data'
    when (x->>'data')::date not between date '2020-01-01' and date '2100-12-31' then 'data'
    when coalesce(x->>'tipo', '') not in ('noticia','reel','quem_cuida','agenda','bastidor','educativo','captacao','data_equipe','sem_post') then 'tipo'
    when coalesce(x->>'formato', '') not in ('imagem','foto','carrossel','carrossel_fotos','reel','story','nenhum') then 'formato'
    when jsonb_typeof(x->'assunto') not in ('string','null') or length(coalesce(x->>'assunto', '')) > 1000 then 'assunto'
    when jsonb_typeof(x->'quem_aparece') not in ('string','null') or length(coalesce(x->>'quem_aparece', '')) > 300 then 'quem_aparece'
    when jsonb_typeof(x->'objetivo') not in ('string','null') or length(coalesce(x->>'objetivo', '')) > 200 then 'objetivo'
    when jsonb_typeof(x->'observacao') not in ('string','null') or length(coalesce(x->>'observacao', '')) > 1000 then 'observacao'
  end;
end $$;

-- v0.28.0: a hora das peças que entram pela importação e pela "+ Nova peça": Configurações → Pauta → "hora_padrao" (HH:MM); senão 09:30
create or replace function public.radar_pauta_hora_padrao() returns time
language plpgsql stable set search_path = public as $$
declare v_conf jsonb := (select c.valor from public.radar_config c where c.chave = 'pauta');
begin
  return case when coalesce(v_conf->>'hora_padrao', '') ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$' then (v_conf->>'hora_padrao')::time
              else '09:30' end;
end $$;

-- Importa o calendário (as linhas do CSV, já lidas pela tela). Confere tudo antes de gravar e para no primeiro erro, com a linha e
-- o campo — nunca o conteúdo. Por data: a peça nova entra (planejada, na hora de Configurações → Pauta → "hora_padrao"); a que
-- existe só é atualizada se ainda estiver planejada (a que já entrou em produção fica como está). Não liga pessoas: "quem
-- aparece" é só lembrete. Devolve {novas, alteradas, iguais, mantidas}.
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

-- v0.28.0: "+ Nova peça" (Pauta, só o administrador): a peça de um dia que ainda não tem nenhuma (uma peça por dia: a data é única,
-- também a da peça cancelada), de hoje em diante (de Brasília), com a conferência da importação (radar_pauta_linha_invalida) e o assunto
-- obrigatório. Nasce planejada, na hora padrão (radar_pauta_hora_padrao), sem pessoas, sem aprovação e sem envio (radar_fn_pauta_peca):
-- não publica nem agenda nada; segue o caminho de sempre (preparar, marcar como pronta e a aprovação do administrador). Vai à trilha como
-- a importada (o INSERT, sem o plano: radar_fn_auditar). O erro diz o campo, nunca o conteúdo. Devolve o número da peça.
-- Uma importação do calendário depois, com uma linha para o mesmo dia, trata a peça como a de qualquer outra origem: ainda planejada,
-- recebe o tipo, o formato e o plano do arquivo (a hora fica); já em produção (ou pronta, aprovada, cancelada), fica como está.
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
  exception when unique_violation then                                      -- a peça gravada por outra tela no mesmo instante
    raise exception 'RADAR193: já existe uma peça em %: é uma peça por dia (recarregue a página)', to_char(v_data, 'DD/MM/YYYY')
      using errcode = 'P0001';
  end;
  return v_id;
end $$;

-- O que falta resolver na peça (a tela mostra a lista). p_canais nulo: os canais que têm legenda.
create or replace function public.radar_pauta_conferir(p_peca bigint, p_canais text[]) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare p public.radar_pauta_pecas%rowtype;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR159: só o editor ou o administrador mexe na Pauta' using errcode = '42501';
  end if;
  select * into p from public.radar_pauta_pecas where id = p_peca;
  if p.id is null then
    raise exception 'RADAR160: peça não encontrada' using errcode = 'P0001';
  end if;
  return jsonb_build_object('problemas', to_jsonb(public.radar_pauta_problemas(p.id,
           coalesce(p_canais, public.radar_pauta_canais(p.legenda_instagram, p.legenda_facebook)), p.data)));
end $$;

-- "Salvar e marcar como pronta": a peça em produção, sem nenhum problema, fica pronta para o administrador aprovar.
-- Devolve a nova versão da peça (atualizado_em), para a tela.
create or replace function public.radar_pauta_marcar_pronta(p_peca bigint, p_lido timestamptz) returns timestamptz
language plpgsql security definer set search_path = public as $$
declare
  p      public.radar_pauta_pecas%rowtype;
  v_prob text[];
  v_em   timestamptz;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR159: só o editor ou o administrador mexe na Pauta' using errcode = '42501';
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
  v_prob := public.radar_pauta_problemas(p.id, public.radar_pauta_canais(p.legenda_instagram, p.legenda_facebook), p.data);
  if cardinality(v_prob) > 0 then
    raise exception 'RADAR165: há % ponto(s) a resolver: a lista aparece na tela', cardinality(v_prob) using errcode = 'P0001';
  end if;
  perform set_config('radar.pauta', '1', true);
  update public.radar_pauta_pecas set situacao = 'pronta' where id = p.id returning atualizado_em into v_em;
  perform set_config('radar.pauta', '', true);
  return v_em;
end $$;

-- Aprovação (só o administrador). Confere de novo tudo (radar_pauta_problemas, com o dia da peça), as caixas de conferência, as
-- lâminas desenhadas na tela dele e guardadas agora em radar_imagens (o que se aprova é o que ele viu) e a hora. Modo "agendar"
-- (imagem única: Imagem 4:5 e Foto): um envio por canal, com a cópia da legenda e da lâmina, que a agenda do banco publica na
-- hora marcada. Modo "manual" (carrossel e reel nesta versão, ou quem preferir): não cria envio; libera baixar e copiar, só nos
-- canais aprovados (aprovado_canais). Depois de uma aprovação à mão desfeita, pede a caixa "rede" (a peça pode ter sido postada).
-- v0.22.0: no reel, p_video_sha256 é o hash do vídeo corrigido que a tela mostrou: tem de ser o do vídeo pronto, e a peça fica amarrada
-- a ele (video_id, video_sha256); pede a caixa "video" e, se alguma pessoa marcada quer ver a peça antes (termo), a caixa "viu".
drop function if exists public.radar_pauta_aprovar(bigint, timestamptz, text[], text, bigint[], text, text[]);
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
  if p_modo = 'agendar' and p.formato not in ('imagem','foto') then
    raise exception 'RADAR164: carrossel e reel saem à mão nesta versão (escolha “Vou publicar à mão”)' using errcode = 'P0001';
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
    select i.dados into v_img from public.radar_imagens i where i.id = v_artes[1];
    foreach v_canal in array v_canais loop
      begin
        insert into public.radar_redes_envios (peca_id, canal, legenda, imagem, conteudo_lido_em, situacao, autorizado_por, agendado_para)
        values (p.id, v_canal, btrim(case v_canal when 'instagram' then p.legenda_instagram else p.legenda_facebook end), v_img,
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

-- "Desfazer aprovação" (editor ou administrador): o que ainda não saiu é cancelado e a peça volta a pronta, sem as lâminas
-- aprovadas (v0.22.0: e sem a amarra com o vídeo, que pode mudar de novo). Não desfaz o que está saindo agora nem o que já saiu (exclua da rede antes). A peça aprovada à mão pode ter sido
-- postada sem o link registrado: só desfaz com p_conferi_rede ("Conferi no Instagram e no Facebook: não foi postada à mão"), e a
-- próxima aprovação pede a mesma caixa (manual_desfeita_em). Devolve a nova versão da peça.
drop function if exists public.radar_pauta_desaprovar(bigint);
create or replace function public.radar_pauta_desaprovar(p_peca bigint, p_conferi_rede boolean default false) returns timestamptz
language plpgsql security definer set search_path = public as $$
declare
  p    public.radar_pauta_pecas%rowtype;
  v_em timestamptz;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR159: só o editor ou o administrador mexe na Pauta' using errcode = '42501';
  end if;
  select * into p from public.radar_pauta_pecas where id = p_peca for update;
  if p.id is null then
    raise exception 'RADAR160: peça não encontrada' using errcode = 'P0001';
  end if;
  if p.situacao <> 'aprovada' then
    raise exception 'RADAR164: a peça não está aprovada (situação atual: %)', p.situacao using errcode = 'P0001';
  end if;
  if exists (select 1 from public.radar_redes_envios e where e.peca_id = p.id and e.situacao = 'enviando') then
    raise exception 'RADAR169: a peça está sendo publicada agora: espere terminar (parada há mais de 10 minutos, o administrador cancela na própria peça, na Pauta)'
      using errcode = 'P0001';
  end if;
  if p.publicado_manual_em is not null or exists (select 1 from public.radar_redes_envios e where e.peca_id = p.id and e.situacao = 'publicado') then
    raise exception 'RADAR170: a peça já saiu numa rede: exclua a publicação da rede antes de desfazer a aprovação' using errcode = 'P0001';
  end if;
  if p.aprovado_modo = 'manual' and not coalesce(p_conferi_rede, false) then
    raise exception 'RADAR166: a peça foi aprovada para publicar à mão: confira no Instagram e no Facebook que ela não foi postada e marque “Conferi no Instagram e no Facebook: não foi postada à mão”'
      using errcode = 'P0001';
  end if;
  update public.radar_redes_envios
     set situacao = 'cancelado', cancelado_por = auth.uid(), cancelado_em = now(), imagem = null,
         erro = 'Aprovação desfeita na Pauta.', atualizado_em = now()
   where peca_id = p.id and situacao in ('autorizado','erro');
  perform set_config('radar.pauta', '1', true);
  update public.radar_pauta_pecas
     set situacao = 'pronta', aprovado_por = null, aprovado_em = null, aprovado_modo = null, aprovado_conferencias = '{}',
         aprovado_canais = '{}', artes = '{}', arte_identificacao = null, video_id = null, video_sha256 = null,   -- v0.22.0
         manual_desfeita_em = case when p.aprovado_modo = 'manual' then now() else manual_desfeita_em end
   where id = p.id
  returning atualizado_em into v_em;
  perform set_config('radar.pauta', '', true);
  return v_em;
end $$;

-- "Publicar agora" e "Tentar de novo" (só o administrador): só remarcam a hora dos envios que esperam (ou que deram erro) para
-- agora; quem publica é a agenda do banco (ou a tela, com a agenda desligada), que confere tudo de novo. O que deu erro só volta
-- com a caixa "Conferi no Instagram e no Facebook: não saiu". Devolve os envios remarcados.
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
    foreach v_id in array p.pessoas loop
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
       set situacao = 'autorizado', agendado_para = now(), disparos = 0, disparado_em = null, erro = null, atualizado_em = now()
     where peca_id = p.id and situacao in ('autorizado','erro')
    returning id
  ) select coalesce(array_agg(u.id order by u.id), '{}') into v_ids from u;
  if cardinality(v_ids) = 0 then
    raise exception 'RADAR164: não há publicação desta peça esperando a hora (ou com erro)' using errcode = 'P0001';
  end if;
  return v_ids;
end $$;

-- Copiar a legenda e o roteiro e baixar as lâminas: só na peça aprovada para publicar à mão, na versão que está na tela, só nos
-- canais aprovados (p_canal: a legenda daquele canal; nulo: as lâminas e o roteiro, que valem para os canais aprovados) e com o termo
-- de cada pessoa valendo HOJE nesses canais. Devolve {ok, artes, canais} ou {motivo} (sem nome).
drop function if exists public.radar_pauta_pode_copiar(bigint, timestamptz);
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
    foreach v_id in array p.pessoas loop
      v_x := public.radar_pauta_termo_ok(v_id, p.tipo, v_canal, v_hoje);
      if v_x is not null then
        return jsonb_build_object('motivo', format('O termo de uso de imagem de uma pessoa da peça não vale hoje no %s (%s): confira em Pauta → Pessoas e termos.',
                                                   initcap(v_canal), v_x));
      end if;
    end loop;
  end loop;
  return jsonb_build_object('ok', true, 'artes', to_jsonb(p.artes), 'canais', to_jsonb(p.aprovado_canais));
end $$;

-- Registro da peça postada à mão: o link (Instagram ou Facebook, só de canal aprovado) e o dia, do dia da aprovação até hoje.
-- Completa o link que faltar, sem trocar o que já foi registrado.
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
    foreach v_id in array p.pessoas loop
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

-- A agenda do banco (sql/radar-redes-agenda.sql) está instalada e rodando? Só para o administrador (os outros recebem {}). Sem o
-- pg_cron (ou com qualquer erro), {instalada: false}. "agenda_ligada": Configurações → Pauta.
create or replace function public.radar_agenda_situacao() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  v_ligada boolean := coalesce((select c.valor->'agenda_ligada' from public.radar_config c where c.chave = 'pauta'), 'true'::jsonb)
                      is distinct from 'false'::jsonb;
  v_ativa  boolean;
  v_ult    timestamptz;
  v_status text;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    return '{}'::jsonb;
  end if;
  begin
    execute 'select j.active from cron.job j where j.jobname = ''radar-redes-agenda'' limit 1' into v_ativa;
    if v_ativa is null then
      return jsonb_build_object('instalada', false, 'agenda_ligada', v_ligada);
    end if;
    execute 'select coalesce(d.end_time, d.start_time), d.status from cron.job_run_details d join cron.job j on j.jobid = d.jobid
              where j.jobname = ''radar-redes-agenda'' order by d.start_time desc nulls last limit 1' into v_ult, v_status;
  exception when others then
    return jsonb_build_object('instalada', false, 'agenda_ligada', v_ligada);
  end;
  return jsonb_build_object('instalada', true, 'ativa', v_ativa, 'ultima_execucao', v_ult, 'ultimo_status', v_status, 'agenda_ligada', v_ligada);
end $$;

-- Conferência curta, logo antes de disparar e de novo no início do envio: devolve o primeiro motivo para a peça NÃO sair (ou
-- NULL). Sem nome de pessoa: o texto vai para radar_redes_envios.erro.
create or replace function public.radar_pauta_pode_sair(p_envio bigint) returns text
language plpgsql stable security definer set search_path = public as $$
declare
  e        public.radar_redes_envios%rowtype;
  p        public.radar_pauta_pecas%rowtype;
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
  if e.imagem is null and e.imagem_url is null then
    return 'A imagem da publicação se perdeu: desfaça a aprovação e aprove de novo.';
  end if;
  return null;
end $$;

-- A agenda do banco (o pg_cron, de 5 em 5 minutos) chama aqui: devolve até p_limite envios da Pauta que venceram, já com a
-- tentativa marcada, e o comando do cron faz um pedido à função radar-redes por envio (nenhuma linha = nenhum pedido). Cada
-- envio é chamado no máximo 3 vezes, de 10 em 10 minutos; depois vira "erro" (final para a agenda: só o administrador o devolve,
-- por radar_pauta_publicar_agora). O que não pode sair (radar_pauta_pode_sair) vira "erro" antes de qualquer coisa ir à Meta.
-- "erro" e "enviando" nunca são pegos. Não trava a peça (a ordem das travas é peça e depois envio, em todas as funções).
create or replace function public.radar_agenda_vencidas(p_limite int default 2) returns setof bigint
language plpgsql security definer set search_path = public as $$
declare
  r        record;
  v_motivo text;
begin
  -- pausa sem SQL: Configurações → Pauta → "agenda_ligada": false
  if (select c.valor->'agenda_ligada' from public.radar_config c where c.chave = 'pauta') = 'false'::jsonb then
    return;
  end if;
  for r in select e.id, e.disparos from public.radar_redes_envios e
            where e.situacao = 'autorizado' and e.peca_id is not null and e.agendado_para <= now()
              and (e.disparado_em is null or e.disparado_em < now() - interval '10 minutes')
            order by e.agendado_para, e.id
            limit least(greatest(coalesce(p_limite, 2), 1), 10)
            for update skip locked loop
    v_motivo := case when r.disparos >= 3
      then 'A publicação agendada não saiu: o Radar chamou a função radar-redes 3 vezes, de 10 em 10 minutos, e ela não publicou. '
           'Confira em Publicações → Testar conexão se a radar-redes é a v0.21.0 e se o Instagram e o Facebook estão configurados; '
           'depois use Tentar de novo.'
      else public.radar_pauta_pode_sair(r.id) end;            -- confere ANTES de qualquer coisa ir à Meta
    if v_motivo is not null then
      update public.radar_redes_envios set situacao = 'erro', erro = left(v_motivo, 1000), atualizado_em = now() where id = r.id;
      continue;
    end if;
    update public.radar_redes_envios set disparos = disparos + 1, disparado_em = now() where id = r.id;
    return next r.id;
  end loop;
end $$;

-- A função radar-redes (v0.21.0) pega o envio da peça para publicar: uma vez só (autorizado → enviando, com a peça e o envio
-- travados, nessa ordem), na hora marcada, e conferindo tudo de novo. O problema vira "erro" (contado e avisado), nunca
-- "cancelado" calado. Qualquer exceção aqui desfaz tudo: nada foi ao armazenamento nem à Meta (o envio da imagem vem depois).
create or replace function public.radar_pauta_iniciar(p_envio bigint) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_peca   bigint;
  e        public.radar_redes_envios%rowtype;
  v_motivo text;
begin
  select peca_id into v_peca from public.radar_redes_envios where id = p_envio;     -- sem trava: a ordem é peça, depois envio
  if v_peca is null then
    raise exception 'RADAR138: esta autorização não está aguardando envio (já saiu, foi cancelada ou está saindo)' using errcode = 'P0001';
  end if;
  perform 1 from public.radar_pauta_pecas where id = v_peca for update;
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
  update public.radar_redes_envios set situacao = 'enviando', enviado_em = now(), erro = null, atualizado_em = now() where id = p_envio;
  return jsonb_build_object('id', e.id, 'canal', e.canal, 'conteudo_id', null, 'peca_id', e.peca_id, 'legenda', e.legenda,
                            'imagem', e.imagem, 'imagem_url', e.imagem_url);
end $$;

-- v0.17.0: pedido de exclusão da notícia no site. Usa o registro mais recente em "Publicações no site" (link e título).
create or replace function public.radar_pedir_exclusao_site(p_conteudo bigint) returns bigint
language plpgsql security definer set search_path = public as $$
declare
  v_d public.radar_divulgacoes%rowtype;
  v_id bigint;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR150: só o administrador pede a exclusão de notícia no site' using errcode = '42501';
  end if;
  perform 1 from public.radar_conteudos c where c.id = p_conteudo for update;   -- um pedido por vez em cada conteúdo
  select * into v_d from public.radar_divulgacoes d where d.conteudo_id = p_conteudo order by d.id desc limit 1;
  if v_d.id is null then
    raise exception 'RADAR151: este conteúdo não tem publicação registrada no site' using errcode = 'P0001';
  end if;
  if exists (select 1 from public.radar_site_exclusoes x where x.conteudo_id = p_conteudo and x.situacao in ('pedido','excluindo')) then
    raise exception 'RADAR152: a exclusão desta notícia já foi pedida e está aguardando o robô' using errcode = 'P0001';
  end if;
  if exists (select 1 from public.radar_site_envios e where e.conteudo_id = p_conteudo and e.situacao in ('autorizado','enviando')) then
    raise exception 'RADAR157: há uma publicação deste conteúdo saindo para o site agora; espere o robô terminar' using errcode = 'P0001';
  end if;
  insert into public.radar_site_exclusoes (conteudo_id, url, titulo, pedido_por)
  values (p_conteudo, v_d.url, left(coalesce(nullif(btrim(v_d.titulo), ''), '(sem título)'), 500), auth.uid())
  returning id into v_id;
  return v_id;
end $$;

-- Cancelar o pedido de exclusão enquanto o robô ainda não começou.
create or replace function public.radar_cancelar_exclusao_site(p_exclusao bigint) returns boolean
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR150: só o administrador pede a exclusão de notícia no site' using errcode = '42501';
  end if;
  update public.radar_site_exclusoes
     set situacao = 'cancelado', cancelado_por = auth.uid(), cancelado_em = now(), atualizado_em = now()
   where id = p_exclusao and situacao in ('pedido','erro');
  if not found then
    raise exception 'RADAR158: não dá mais para cancelar: o robô já está excluindo (ou o pedido não existe)' using errcode = 'P0001';
  end if;
  return true;
end $$;

-- O robô terminou a exclusão. Deu certo: tira o registro em "Publicações no site" daquele link (a cópia fica no pedido e na
-- auditoria) e a autorização que publicou passa a "excluido" — o conteúdo pode ser publicado de novo, se for o caso.
create or replace function public.radar_site_exclusao_concluir(p_exclusao bigint, p_ok boolean, p_erro text) returns boolean
language plpgsql security definer set search_path = public as $$
declare v_x public.radar_site_exclusoes%rowtype;
begin
  select * into v_x from public.radar_site_exclusoes where id = p_exclusao and situacao in ('pedido','excluindo') for update;
  if v_x.id is null then
    return false;
  end if;
  if not p_ok then
    update public.radar_site_exclusoes
       set situacao = 'erro', erro = left(coalesce(nullif(btrim(p_erro), ''), 'Erro sem descrição.'), 1000), atualizado_em = now()
     where id = p_exclusao;
    return true;
  end if;
  delete from public.radar_divulgacoes d where d.conteudo_id = v_x.conteudo_id and d.url = v_x.url;
  update public.radar_site_envios set situacao = 'excluido', excluido_em = now(), atualizado_em = now()
   where conteudo_id = v_x.conteudo_id and situacao = 'publicado';
  update public.radar_site_exclusoes set situacao = 'excluido', excluido_em = now(), erro = null, atualizado_em = now()
   where id = p_exclusao;
  return true;
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
  v_motivo  text;
begin
  select c.assunto_id into v_assunto from public.radar_conteudos c
   where c.id = case when tg_op = 'DELETE' then old.conteudo_id else new.conteudo_id end;
  perform 1 from public.radar_assuntos a where a.id = v_assunto for update;      -- um registro por vez em cada assunto
  if tg_op = 'INSERT' then    -- assunto ignorado ou arquivado continua como está
    update public.radar_assuntos set status = 'publicado' where id = v_assunto and status not in ('publicado','ignorado','arquivado');
    -- v0.17.0: "Publicar em todos": o Instagram e o Facebook autorizados junto com o site ficam prontos para sair, com o
    -- link da notícia no lugar de {LINK DO SITE} (o robô do site manda publicar logo em seguida).
    -- v0.22.0 (varredura geral): só o registro que é mesmo a notícia no site libera as redes. O link tem de ser do site
    -- (radar_site_host) e o registro, do robô (sem usuário: o do site ou a coleta) ou de uma pessoa depois que o envio do site
    -- saiu ("publicado"). Fora disso (o link da fonte colado por engano, outro endereço), as redes que esperavam o site caem,
    -- com o motivo: o que vai ao ar é só o que o administrador viu, e nunca com um link que ele não viu.
    v_motivo := case
      when public.radar_url_host(new.url) is distinct from public.radar_site_host()
        then 'o link registrado não é do site da Artecon (' || public.radar_site_host() || ')'
      when auth.uid() is not null and not exists (select 1 from public.radar_site_envios e
                                                   where e.conteudo_id = new.conteudo_id and e.situacao = 'publicado')
        then 'a publicação foi registrada à mão antes de o robô do site concluir o envio' end;
    if v_motivo is null then
      update public.radar_redes_envios
         set situacao = 'autorizado', atualizado_em = now(),
             legenda = left(replace(legenda, '{LINK DO SITE}', new.url), 2200)
       where conteudo_id = new.conteudo_id and situacao = 'aguardando_site';
    else
      update public.radar_redes_envios
         set situacao = 'cancelado', cancelado_em = now(), atualizado_em = now(), imagem = null,
             erro = 'Não publicado: ' || v_motivo || '. A deste canal, que ia junto com o site, foi cancelada. Confira o link e autorize de novo.'
       where conteudo_id = new.conteudo_id and situacao = 'aguardando_site';
    end if;
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
      -- v0.16.0: a captura que a equipe separou ("não é o mesmo fato") não volta a ser juntada pela IA
      v_raiz := null;
      if jsonb_typeof(v_item->'igual_a') = 'number'
         and not exists (select 1 from public.radar_capturas c where c.id = v_id and c.metadados ? 'separada_em') then
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
        -- v0.16.0: a equipe disse que estas duas não são o mesmo fato (vale nos dois sentidos)
        if v_raiz is not null and exists (select 1 from public.radar_capturas c
             where (c.id = v_id and coalesce(c.metadados->'separada_de', '[]'::jsonb) @> to_jsonb(v_raiz))
                or (c.id = v_raiz and coalesce(c.metadados->'separada_de', '[]'::jsonb) @> to_jsonb(v_id))) then
          v_raiz := null;
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
declare v_outras jsonb;
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
  -- v0.16.0: de quem ela foi separada (a origem e as demais capturas do assunto): a IA não junta de novo, em nenhum sentido
  select coalesce(jsonb_agg(x.id), '[]'::jsonb) into v_outras
    from (select c.duplicata_de as id from public.radar_capturas c where c.id = p_captura and c.duplicata_de is not null
          union select ac.captura_id from public.radar_assunto_capturas ac where ac.assunto_id = p_assunto and ac.captura_id <> p_captura) x;
  delete from public.radar_assunto_capturas ac where ac.assunto_id = p_assunto and ac.captura_id = p_captura;
  update public.radar_capturas set duplicata_de = null,
         metadados = coalesce(metadados, '{}'::jsonb) || jsonb_build_object('separada_em', now(),   -- v0.11.1: não volta a ser agrupada sozinha
                       'separada_de', coalesce(metadados->'separada_de', '[]'::jsonb) || v_outras)
   where id = p_captura;
  update public.radar_capturas c
     set metadados = coalesce(c.metadados, '{}'::jsonb) || jsonb_build_object('separada_de', coalesce(c.metadados->'separada_de', '[]'::jsonb) || to_jsonb(p_captura))
   where c.id in (select (jsonb_array_elements_text(v_outras))::bigint);
  -- se era a origem do grupo, as demais deixam de apontar para ela
  update public.radar_capturas set duplicata_de = null where duplicata_de = p_captura;
  insert into public.radar_auditoria (tabela, registro_id, acao, usuario, antes)
  values ('radar_assunto_capturas', p_assunto || ':' || p_captura, 'DELETE', auth.uid(),
          jsonb_build_object('assunto_id', p_assunto, 'captura_id', p_captura, 'motivo', 'não é o mesmo fato'));
end $$;

-- v0.16.0: na aba Capturas, "Não é o mesmo fato": a captura que a IA marcou como repetição volta a aparecer sozinha na
-- triagem (e não é juntada de novo pelo boletim oficial). Só editor/admin; só para a que ainda está na fila.
create or replace function public.radar_separar_repeticao(p_captura bigint)
returns void language plpgsql security definer set search_path = public as $$
declare v_origem bigint;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'permission denied for function radar_separar_repeticao' using errcode = '42501';
  end if;
  if exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = p_captura) then
    raise exception 'RADAR141: esta captura já está num assunto; separe pelo botão "Não é o mesmo fato" na tela do assunto' using errcode = 'P0001';
  end if;
  select c.duplicata_de into v_origem from public.radar_capturas c where c.id = p_captura for update;
  if v_origem is null then
    raise exception 'RADAR142: esta captura não está marcada como repetição de outra' using errcode = 'P0001';
  end if;
  update public.radar_capturas set duplicata_de = null,
         metadados = coalesce(metadados, '{}'::jsonb) || jsonb_build_object('separada_em', now(),
                       'separada_de', coalesce(metadados->'separada_de', '[]'::jsonb) || to_jsonb(v_origem))
   where id = p_captura;
  update public.radar_capturas            -- e na origem: a IA não junta as duas de novo, nem pelo outro lado
     set metadados = coalesce(metadados, '{}'::jsonb) || jsonb_build_object('separada_de', coalesce(metadados->'separada_de', '[]'::jsonb) || to_jsonb(p_captura))
   where id = v_origem;
  insert into public.radar_auditoria (tabela, registro_id, acao, usuario, antes, depois)
  values ('radar_capturas', p_captura::text, 'UPDATE', auth.uid(), jsonb_build_object('duplicata_de', v_origem),
          jsonb_build_object('duplicata_de', null, 'motivo', 'não é o mesmo fato (separada na triagem)'));
end $$;

-- Fonte do conteúdo já preenchida (v0.7.0): ao criar um conteúdo sem "Fonte", entra o órgão das capturas
-- de fonte oficial do assunto (ex.: "Receita Federal do Brasil"). A equipe pode trocar ou apagar depois.
-- v0.18.0: o texto pode usar as frases da fonte citando-a, então entra também o portal de notícias de onde veio a informação
-- (depois dos órgãos oficiais, ex.: "Receita Federal do Brasil, Portal Contábil SC"). O boletim pago (itc-email) não entra.
create or replace function public.radar_fn_conteudo_fonte() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.fonte_credito is null or btrim(new.fonte_credito) = '' then
    select left(string_agg(o.orgao, ', ' order by o.oficial desc, o.orgao), 300) into new.fonte_credito
      from (select f.orgao, bool_or(f.oficial) as oficial
              from public.radar_assunto_capturas ac
              join public.radar_capturas c on c.id = ac.captura_id
              join public.radar_fontes f on f.id = c.fonte_id
             where ac.assunto_id = new.assunto_id and f.slug <> 'itc-email' and btrim(coalesce(f.orgao, '')) <> ''
             group by f.orgao) o;
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

-- v0.12.0: boletim por e-mail. A função radar_receber_email (antes só em radar-fontes-novas-2026-10.sql) passa a
-- fazer parte do setup e a rodar com o dono (a função radar-itc grava pelo papel do robô).
-- Recebe as matérias de um boletim lido no e-mail (usada pela rotina diária da ITC).
-- p_itens: [{"titulo": "...", "data": "AAAA-MM-DD", "area": "...", "texto": "...", "assunto_email": "..."}, ...]
-- Cada matéria vira uma captura da fonte; a mesma manchete em dois boletins (ITCNET Mail e
-- Legislação & Tribunais) entra uma vez só. Devolve quantas entraram e quantas já existiam.
create or replace function public.radar_data_valida(p text) returns boolean
language plpgsql immutable set search_path = public as $$
begin
  perform p::date;
  return true;
exception when others then
  return false;
end $$;

create or replace function public.radar_receber_email(p_fonte text, p_itens jsonb) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_fonte bigint; v_url_base text; v_recebidos int; v_novos int;
begin
  select f.id, rtrim(f.url, '/') into v_fonte, v_url_base
    from public.radar_fontes f where f.slug = p_fonte and f.config->>'origem' = 'email';
  if v_fonte is null then
    raise exception 'RADAR095: fonte de e-mail "%" não cadastrada (rode sql/radar-fontes-novas-2026-10.sql)', p_fonte using errcode = 'P0001';
  end if;
  if jsonb_typeof(p_itens) is distinct from 'array' then
    raise exception 'RADAR096: as matérias precisam vir numa lista JSON' using errcode = 'P0001';
  end if;
  with itens as (
    select btrim(i.titulo) as titulo, i.data, nullif(btrim(i.area), '') as area,
           nullif(btrim(i.texto), '') as texto, i.assunto_email,
           -- o mesmo cálculo do robô (radar_util.hash_titulo): sem acento, sem pontuação, minúsculas
           encode(sha256(convert_to(btrim(regexp_replace(regexp_replace(lower(translate(btrim(i.titulo),
             'áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑºª¹²³', 'aaaaaeeeeiiiiooooouuuucnAAAAAEEEEIIIIOOOOOUUUUCNoa123')),
             '[^a-z0-9 ]+', ' ', 'g'), '\s+', ' ', 'g')), 'UTF8')), 'hex') as h
      from (select j.titulo, j.area, j.texto, j.assunto_email,
                   -- data só no formato AAAA-MM-DD e válida; o resto vira "sem data" (um item ruim não derruba o boletim)
                   case when j.data ~ '^\d{4}-\d{2}-\d{2}$' and public.radar_data_valida(j.data) then j.data::date end as data
              from jsonb_to_recordset(p_itens) as j(titulo text, data text, area text, texto text, assunto_email text)) i
     where length(btrim(coalesce(i.titulo, ''))) between 5 and 300
       and (i.data is null or i.data <= current_date + 1)
  ), unicos as (
    select distinct on (h) * from itens order by h, length(coalesce(texto, '')) desc
  ), gravados as (
    insert into public.radar_capturas (fonte_id, url, titulo, data_publicacao, resumo_fonte, texto, hash_titulo, metadados, verificado_em)
    select v_fonte, v_url_base || '/?radar=' || left(u.h, 16), u.titulo, u.data, u.area, u.texto, u.h,
           jsonb_build_object('origem', 'email', 'texto_parcial', true, 'area', u.area, 'assunto_email', u.assunto_email),
           now()
      from unicos u
    on conflict (fonte_id, url) do nothing
    returning 1
  )
  select (select count(*) from unicos), (select count(*) from gravados) into v_recebidos, v_novos;
  -- a tela mostra a fonte como funcionando (o mesmo campo que o robô atualiza nas outras fontes)
  update public.radar_fontes set ultimo_sucesso_em = now(), ultimo_erro = null, falhas_consecutivas = 0
   where id = v_fonte;
  return jsonb_build_object('recebidos', v_recebidos, 'novos', v_novos, 'ja_existiam', v_recebidos - v_novos);
end $$;

-- v0.12.0: quais destes e-mails a função radar-itc já leu (para não gastar IA de novo com o mesmo boletim).
-- Lido = trouxe matérias, ou já foi tentado 3 vezes sem resultado (a IA ou a leitura falharam): aí desiste.
create or replace function public.radar_itc_ja_lidos(p_ids text[]) returns text[]
language sql stable security definer set search_path = public as $$
  select coalesce(array_agg(l.message_id), '{}') from public.radar_itc_lidos l
   where l.message_id = any(coalesce(p_ids, '{}')) and (l.materias > 0 or l.tentativas >= 3);
$$;

-- p_materias = 0: tentativa sem resultado (conta mais uma). Com matérias, fica registrado de vez.
create or replace function public.radar_itc_marcar_lido(p_id text, p_assunto text, p_recebido timestamptz, p_materias int, p_novas int)
returns void language sql security definer set search_path = public as $$
  insert into public.radar_itc_lidos as l (message_id, assunto, recebido_em, materias, novas)
  values (p_id, left(p_assunto, 200), p_recebido, greatest(coalesce(p_materias, 0), 0), greatest(coalesce(p_novas, 0), 0))
  on conflict (message_id) do update
     set tentativas = l.tentativas + case when excluded.materias > 0 then 0 else 1 end,
         materias = greatest(l.materias, excluded.materias), novas = l.novas + excluded.novas, lido_em = now()
   where l.materias = 0;
$$;

-- a falha da leitura aparece na aba Fontes (só o motivo; o conteúdo do boletim nunca); a próxima leitura boa apaga
create or replace function public.radar_itc_registrar_falha(p_motivo text) returns void
language sql security definer set search_path = public as $$
  update public.radar_fontes set ultimo_erro = left('Leitura do boletim: ' || coalesce(p_motivo, 'falhou'), 500), ultima_falha_em = now()
   where slug = 'itc-email';
$$;

-- v0.12.0: a agenda do banco (pg_cron, sql/radar-itc-agenda.sql) chama a função radar-itc com uma chave guardada no Vault.
-- Sem o Vault (ou sem a chave), nunca confere.
create or replace function public.radar_itc_conferir_agenda(p_chave text) returns boolean
language plpgsql stable security definer set search_path = public as $$
declare v_certa text;
begin
  if length(coalesce(p_chave, '')) < 32 then return false; end if;
  execute 'select decrypted_secret from vault.decrypted_secrets where name = ''radar_itc_agenda'' limit 1' into v_certa;
  return v_certa is not null and length(v_certa) >= 32 and v_certa = p_chave;
exception when others then
  return false;
end $$;

-- v0.21.0: a agenda que publica a Pauta aprovada (pg_cron, sql/radar-redes-agenda.sql) chama a função radar-redes com a chave
-- 'radar_redes_agenda' do Vault (cabeçalho x-radar-agenda); a função confere por aqui. Sem o Vault (ou sem a chave), nunca confere.
create or replace function public.radar_redes_conferir_agenda(p_chave text) returns boolean
language plpgsql stable security definer set search_path = public as $$
declare v_certa text;
begin
  if length(coalesce(p_chave, '')) < 32 then return false; end if;
  execute 'select decrypted_secret from vault.decrypted_secrets where name = ''radar_redes_agenda'' limit 1' into v_certa;
  return v_certa is not null and length(v_certa) >= 32 and v_certa = p_chave;
exception when others then
  return false;
end $$;

-- ---------------------------------------------------------------- v0.22.0: corretor de vídeo dos reels
-- Quem faz o quê (desenho da v0.22.0, com os ajustes do dono): a tela registra a gravação (radar_video_criar: tudo é conferido ANTES
-- de qualquer arquivo sair do celular) e manda os clipes direto ao bucket privado radar-videos; a função radar-video aciona o robô do
-- repositório privado radar-video, que não tem chave do Supabase: ele fala só com a radar-video, por um token estreito (Vault
-- 'radar_video_robo'), e chega a estas funções (radar_video_pegar, _registrar_audio, _parcial, _concluir, _falhar) pelo papel interno
-- dela. A transcrição é do robô (Azure F0, Speech SDK): aqui fica só a conta dos segundos do mês. Nada daqui devolve nome de pessoa.

-- Configurações → Corretor de vídeo ("corretor_video"): o número dentro dos limites da tela (validarConfig); fora deles, ou sem a
-- chave, vale o padrão — nada do que está ali trava o corretor.
create or replace function public.radar_video_cfg_num(p_chave text, p_padrao numeric, p_min numeric, p_max numeric) returns numeric
language sql stable set search_path = public as $$
  select coalesce((select case when jsonb_typeof(c.valor->p_chave) = 'number' and (c.valor->>p_chave)::numeric between p_min and p_max
                               then (c.valor->>p_chave)::numeric end
                     from public.radar_config c where c.chave = 'corretor_video'), p_padrao)
$$;

-- O texto da chave (até 120 caracteres; vazio sem ela)
create or replace function public.radar_video_cfg_texto(p_chave text) returns text
language sql stable set search_path = public as $$
  select coalesce((select case when jsonb_typeof(c.valor->p_chave) = 'string' then left(btrim(c.valor->>p_chave), 120) end
                     from public.radar_config c where c.chave = 'corretor_video'), '')
$$;

-- O que o robô recebe das Configurações: o glossário (até 200 termos de 2 a 40 caracteres), as variantes de cada termo (até 20), os
-- limites das pausas, o volume, a cartela e a duração máxima. Só o que tem a forma certa entra.
create or replace function public.radar_video_config() returns jsonb
language sql stable set search_path = public as $$
  with c as (select coalesce((select case when jsonb_typeof(x.valor) = 'object' then x.valor end
                                from public.radar_config x where x.chave = 'corretor_video'), '{}'::jsonb) as v)
  select jsonb_build_object(
    'glossario', coalesce((select jsonb_agg(btrim(t.x #>> '{}') order by t.o)
                             from c, jsonb_array_elements(case when jsonb_typeof(c.v->'glossario') = 'array' then c.v->'glossario' else '[]' end)
                                     with ordinality t(x, o)
                            where jsonb_typeof(t.x) = 'string' and length(btrim(t.x #>> '{}')) between 2 and 40 and t.o <= 200), '[]'::jsonb),
    'variantes', coalesce((select jsonb_object_agg(w.k, (select coalesce(jsonb_agg(btrim(u.y #>> '{}') order by u.i), '[]'::jsonb)
                                                          from jsonb_array_elements(w.e) with ordinality u(y, i)
                                                         where jsonb_typeof(u.y) = 'string' and length(btrim(u.y #>> '{}')) between 1 and 40 and u.i <= 20))
                             from c, jsonb_each(case when jsonb_typeof(c.v->'variantes') = 'object' then c.v->'variantes' else '{}' end) w(k, e)
                            where jsonb_typeof(w.e) = 'array' and length(w.k) between 2 and 40), '{}'::jsonb),
    'pausa_max_s',   public.radar_video_cfg_num('pausa_max_s', 1.0, 0.6, 2),
    'pausa_bloco_s', public.radar_video_cfg_num('pausa_bloco_s', 0.8, 0.4, 2),
    'lufs',          public.radar_video_cfg_num('lufs', -14, -24, -9),
    'cartela_s',     public.radar_video_cfg_num('cartela_s', 3, 2, 5),
    'cartela_extra', public.radar_video_cfg_texto('cartela_extra'),
    'duracao_max_s', public.radar_video_cfg_num('duracao_max_s', 45, 15, 90))
$$;

-- A cota do Radar no mês (de Brasília): os segundos de áudio que o corretor mandou transcrever e o limite (Configurações → Corretor de
-- vídeo → limite_min_mes, de 1 a 300 minutos; padrão 30). O F0 da Azure (300 minutos por mês no recurso inteiro) é dividido com a
-- Agenda, que se reserva 270: o padrão é o que sobra. Acima de 30, só com o serviço pago (AZURE_FALA_MODO = rapido) ou com a Agenda
-- reservando menos; senão a Agenda recebe a recusa de cota da Azure antes do limite dela.
create or replace function public.radar_video_segundos_mes() returns numeric
language sql stable set search_path = public as $$
  select coalesce(sum(v.segundos_audio), 0) from public.radar_videos v
   where v.transcrito_em >= (date_trunc('month', now() at time zone 'America/Sao_Paulo') at time zone 'America/Sao_Paulo')
$$;
create or replace function public.radar_video_limite_s() returns numeric
language sql stable set search_path = public as $$
  select 60 * public.radar_video_cfg_num('limite_min_mes', 30, 1, 300)
$$;

-- A fala para conferência está no roteiro da peça? As palavras dela (radar_pauta_normalizar) aparecem no roteiro, todas e na mesma
-- ordem — o roteiro pode ter mais (o "Na tela", os tempos, a tarja) —, e são ao menos 10.
create or replace function public.radar_video_fala_no_roteiro(p_fala text, p_roteiro text) returns boolean
language plpgsql immutable set search_path = public as $$
declare
  f text[] := string_to_array(public.radar_pauta_normalizar(p_fala), ' ');
  r text[] := string_to_array(public.radar_pauta_normalizar(p_roteiro), ' ');
  n int := coalesce(array_length(f, 1), 0);
  i int := 1;
  w text;
begin
  if n < 10 then return false; end if;
  foreach w in array coalesce(r, '{}') loop
    if w = f[i] then
      i := i + 1;
      exit when i > n;
    end if;
  end loop;
  return i > n;
end $$;

-- A pessoa pode estar num vídeo do corretor hoje? NULL = pode; senão o motivo, sem o nome. Além do termo de uso de imagem da Pauta
-- (radar_pauta_termo_ok, valendo HOJE nos canais da peça — os que têm legenda; sem legenda ainda, em pelo menos um dos dois —), o termo
-- novo, que cita o corretor e os operadores (termo_corretor_em), e a idade (menor de 18: o corretor recusa nesta versão).
-- v0.28.0: o(a) sócio(a) da Artecon (maior de idade) não precisa dos dois termos; a pessoa inativa continua recusada (radar_pauta_termo_ok).
create or replace function public.radar_video_pessoa_falta(p_pessoa bigint, p_peca bigint) returns text
language plpgsql stable set search_path = public as $$
declare
  pe       public.radar_pessoas%rowtype;
  p        public.radar_pauta_pecas%rowtype;
  v_hoje   date := public.radar_pauta_hoje();
  v_canais text[];
  v_canal  text;
  v_x      text;
begin
  select * into pe from public.radar_pessoas where id = p_pessoa;
  select * into p from public.radar_pauta_pecas where id = p_peca;
  if pe.id is null then return 'pessoa não cadastrada'; end if;
  if pe.menor then return 'menor de idade: o corretor de vídeo não aceita nesta versão'; end if;
  -- v0.28.0: sócio(a) da Artecon (o menor já voltou acima) não precisa do termo novo; o de uso de imagem, radar_pauta_termo_ok dispensa,
  -- e a pessoa inativa continua recusada por ela
  if not pe.socio and (pe.termo_corretor_em is null or pe.termo_corretor_em > v_hoje) then
    return 'sem o termo novo, que cita o corretor de vídeo';
  end if;
  v_canais := public.radar_pauta_canais(p.legenda_instagram, p.legenda_facebook);
  if cardinality(v_canais) > 0 then
    foreach v_canal in array v_canais loop
      v_x := public.radar_pauta_termo_ok(p_pessoa, p.tipo, v_canal, v_hoje);
      if v_x is not null then return v_x || ' no ' || initcap(v_canal); end if;
    end loop;
    return null;
  end if;
  v_x := public.radar_pauta_termo_ok(p_pessoa, p.tipo, 'instagram', v_hoje);
  if v_x is null or public.radar_pauta_termo_ok(p_pessoa, p.tipo, 'facebook', v_hoje) is null then return null; end if;
  return v_x;
end $$;

-- As pessoas do vídeo podem estar nele hoje? NULL = podem; senão o motivo, sem nome: quem fala continua marcada na peça e cada pessoa
-- marcada passa em radar_video_pessoa_falta — as marcadas hoje e as que estavam marcadas quando o vídeo foi gravado (p_pessoas,
-- radar_videos.pessoas: desmarcar na peça não tira a pessoa do vídeo). Não só no envio e na aprovação: todo o caminho do processamento
-- confere de novo (radar_video_pegar, antes de o robô baixar os clipes e mandar o áudio à Azure; o envio que chega, o ajuste,
-- "Conferir com o roteiro novo", "Tentar de novo", a prévia e o baixar): a pessoa que revogou o termo, ficou inativa, foi marcada
-- menor ou ficou com o termo vencido depois do envio não passa mais pelo corretor (v0.28.0: nem a pessoa que perdeu a marca de sócio(a)
-- sem ter os termos).
drop function if exists public.radar_video_pessoas_falta(bigint, bigint);
create or replace function public.radar_video_pessoas_falta(p_peca bigint, p_fala_pessoa bigint, p_pessoas bigint[]) returns text
language plpgsql stable set search_path = public as $$
declare
  p   public.radar_pauta_pecas%rowtype;
  v_i bigint;
  v_x text;
begin
  select * into p from public.radar_pauta_pecas where id = p_peca;
  if p.id is null or p_fala_pessoa is null or not p_fala_pessoa = any(p.pessoas) then
    return 'quem fala não está mais marcada na peça';
  end if;
  foreach v_i in array p.pessoas || array(select x from unnest(coalesce(p_pessoas, '{}')) x where not x = any(p.pessoas)) loop
    v_x := public.radar_video_pessoa_falta(v_i, p.id);
    if v_x is not null then
      return 'uma pessoa da peça não pode aparecer no vídeo (' || v_x || '): confira em Pauta → Pessoas e termos';
    end if;
  end loop;
  return null;
end $$;

-- As linhas da cartela conferem? NULL = conferem; senão o motivo, sem nome. A tela monta: a identificação legal (linhaIdentificacao,
-- Configurações → Assinatura) e, se quem fala tem registro no CRC (Pauta → Pessoas e termos), a linha dela ("Ana, contadora · CRC-SC
-- 012345/O-9"). Nada além disso: o texto extra (Configurações → Corretor de vídeo → cartela_extra) o robô acrescenta. "Contador(a)" e
-- "técnico(a)" só na linha de quem fala, conforme o registro dela; "especialista", nunca (mesmas expressões de radar_pauta_problemas).
create or replace function public.radar_video_cartela_falta(p_linhas text[], p_pessoa bigint) returns text
language plpgsql stable set search_path = public as $$
declare
  pe         public.radar_pessoas%rowtype;
  v_l        text;
  v_cmp      text;
  v_x        text;
  v_crc      text;
  v_resp     boolean := false;
  b constant text := '(?<![A-Za-zÀ-ÿ0-9])';
  e constant text := '(?![A-Za-zÀ-ÿ0-9])';
  v_contador text := b || public.radar_rx_termo('contador') || '(?:[aA]|\([aA]\))?' || e;
  v_tecnico  text := b || public.radar_rx_termo('tecnic') || '(?:[oO]\([aA]\)|[oaOA])' || e;
  v_espec    text := b || public.radar_rx_termo('especialista') || '[sS]?' || e;
begin
  if p_linhas is null or cardinality(p_linhas) not between 1 and 4
     or exists (select 1 from unnest(p_linhas) l where l is null or length(btrim(l)) not between 2 and 150 or l ~ '[[:cntrl:]]') then
    return 'a cartela tem de 1 a 4 linhas, cada uma com até 150 caracteres';
  end if;
  v_x := public.radar_pauta_identificacao_falta(array_to_string(p_linhas, ' '));
  if v_x is not null then return v_x; end if;
  select * into pe from public.radar_pessoas where id = p_pessoa;
  v_crc := substring(coalesce(pe.crc, '') from '[0-9]{4,6}');
  foreach v_l in array p_linhas loop
    v_cmp := public.radar_pauta_sem_acento(v_l);
    if v_cmp ~ v_espec then
      return 'a cartela não diz “especialista” (não há título de especialista registrado)';
    end if;
    if pe.id is not null and pe.categoria <> '' and v_cmp ~* public.radar_pauta_rx_nome(pe.nome_na_peca) then
      -- a linha de quem fala: com o registro dela no CRC; o técnico(a) não é chamado de contador(a)
      if v_crc is null or strpos(regexp_replace(v_l, '[^0-9]', '', 'g'), v_crc) = 0 then
        return 'a linha de quem fala leva o registro dela no CRC (Pauta → Pessoas e termos)';
      end if;
      if pe.categoria in ('tecnico','tecnica') and v_cmp ~ v_contador then
        return 'quem fala é técnico(a) em contabilidade: a cartela não a chama de contador(a)';
      end if;
      v_resp := true;
    elsif public.radar_pauta_identificacao_falta(v_l) is not null then
      return 'a cartela só leva a identificação legal (Configurações → Assinatura) e, se quem fala tem registro no CRC, a linha dela';
    elsif v_cmp ~ v_contador or v_cmp ~ v_tecnico then
      return 'a cartela só diz contador(a) ou técnico(a) na linha de quem fala, com o registro dela no CRC';
    end if;
  end loop;
  if pe.id is not null and pe.categoria <> '' and not v_resp then
    return 'falta a linha de quem fala (nome na peça, categoria e registro no CRC)';
  end if;
  return null;
end $$;

-- Os ajustes do administrador (radar_video_ajustar) têm a forma que o robô espera? NULL = têm; senão o motivo.
--   {manter: ["c:q"], transcricao_errou: ["id"], legenda: [["u" ou "u:n", "texto"], …], estilo: "normal" | "compacta", sem_gancho: true | false}
-- manter: os cortes no meio da fala a manter, pela chave do corte no relatório ("<clipe>:<quadro>", robo/video/cortes.py);
-- transcricao_errou: as divergências em que vale o roteiro, pelo id de cada uma no relatório (16 letras de 0-9a-f: o instante e o texto
-- da divergência, robo/video/alinhar.py). Nunca pela posição na lista: o robô alinha de novo a cada rodada, com as Configurações do
-- momento, e a numeração muda (uma variante nova tira uma divergência da lista; "a transcrição errou" pode criar um corte); a marca
-- que não confere com nenhum item fica sem efeito (a divergência continua pedindo regravar). legenda: o editor (u = a 1ª
-- unidade do bloco, n = as palavras; o robô aplica NA ORDEM da lista — o jsonb guarda a ordem de uma lista, e não a das chaves de um
-- objeto: a edição nova, no fim, vale sobre a antiga do mesmo trecho —, confere palavra por palavra e lista os recusados; o objeto
-- {"u:n": "texto"} de antes também passa). Até 200 itens; textos de até 120 caracteres, sem comando de legenda ({ } \) nem caractere
-- de controle.
create or replace function public.radar_video_ajustes_falta(p jsonb) returns text
language plpgsql immutable set search_path = public as $$
declare
  k text;
  x jsonb;
begin
  if p is null or jsonb_typeof(p) <> 'object' or length(p::text) > 20000 then return 'os ajustes vão num objeto de até 20.000 caracteres'; end if;
  if exists (select 1 from jsonb_object_keys(p) c where c not in ('manter','transcricao_errou','legenda','estilo','sem_gancho')) then
    return 'ajuste desconhecido';
  end if;
  -- (cada conferência só depois da forma: jsonb_array_elements e jsonb_each não rodam sobre o que não é lista nem objeto)
  foreach k in array array['manter','transcricao_errou'] loop
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
                                     or (y->>1) ~ '[{}\\[:cntrl:]]' end) then
        return 'legenda: até 200 blocos ("u" ou "u:n"), cada um com um texto de 1 a 120 caracteres, sem { } \ nem caractere de controle';
      end if;
    elsif jsonb_typeof(x) <> 'object' then
      return 'legenda: até 200 blocos ("u" ou "u:n"), cada um com um texto de 1 a 120 caracteres, sem { } \ nem caractere de controle';
    elsif (select count(*) from jsonb_object_keys(x)) > 200
       or exists (select 1 from jsonb_each(x) w
                   where w.key !~ '^[0-9]{1,4}(:[0-9]{1,3})?$' or jsonb_typeof(w.value) <> 'string'
                      or length(btrim(w.value #>> '{}')) not between 1 and 120 or (w.value #>> '{}') ~ '[{}\\[:cntrl:]]') then
      return 'legenda: até 200 blocos ("u" ou "u:n"), cada um com um texto de 1 a 120 caracteres, sem { } \ nem caractere de controle';
    end if;
  end if;
  if p ? 'estilo' and (jsonb_typeof(p->'estilo') <> 'string' or p->>'estilo' not in ('normal','compacta')) then
    return 'estilo: normal ou compacta';
  end if;
  if p ? 'sem_gancho' and jsonb_typeof(p->'sem_gancho') <> 'boolean' then return 'sem_gancho: sim ou não'; end if;
  return null;
end $$;

-- O que falta no vídeo do reel para a peça ficar pronta e ser aprovada (radar_pauta_problemas chama): NULL ou o 1º motivo, sem nome.
create or replace function public.radar_video_pendencia(p_peca bigint) returns text
language plpgsql stable set search_path = public as $$
declare
  p   public.radar_pauta_pecas%rowtype;
  v   public.radar_videos%rowtype;
  v_x text;
begin
  select * into p from public.radar_pauta_pecas where id = p_peca;
  if p.id is null or p.formato <> 'reel' then return null; end if;
  -- o envio que espera os arquivos vem primeiro: enquanto há gravação nova a caminho, o vídeo vivo anterior não é aprovado por engano
  -- (termine o envio ou descarte-o)
  if exists (select 1 from public.radar_videos where peca_id = p.id and situacao = 'aguardando_envio') then
    return 'Reel: termine de enviar a gravação (Corretor de vídeo)';
  end if;
  select * into v from public.radar_videos
   where peca_id = p.id and situacao in ('na_fila','processando','pronto','regravar','erro') order by versao desc limit 1;
  if v.id is null then return 'Reel: envie a gravação (Corretor de vídeo)'; end if;
  if v.situacao in ('na_fila','processando') then return 'Reel: o corretor ainda está trabalhando'; end if;
  if v.situacao = 'erro' then return 'Reel: o corretor parou com erro (' || coalesce(v.erro_codigo, 'erro_interno') || ')'; end if;
  if v.situacao = 'regravar' then return 'Reel: o vídeo precisa ser regravado (veja o relatório)'; end if;
  if v.sha256 is null or 'corrigido' = any(v.arquivos_apagados) then
    return 'Reel: o vídeo corrigido foi apagado (prazo de guarda): envie a gravação de novo';
  end if;
  if v.roteiro_hash is distinct from public.radar_hash_texto(p.roteiro) then
    return 'Reel: o roteiro mudou depois da gravação: use “Conferir com o roteiro novo” ou grave de novo';
  end if;
  v_x := public.radar_video_pessoas_falta(p.id, v.fala_pessoa, v.pessoas);
  if v_x is not null then return 'Reel: ' || v_x; end if;
  if public.radar_video_cartela_falta(v.cartela_linhas, v.fala_pessoa) is not null then
    return 'Reel: a cartela não confere com as Configurações ou com Pessoas e termos: refaça a cartela';
  end if;
  -- o que está gravado no vídeo e mudou na peça ou nas Configurações depois: o texto do gancho (a cópia da chamada no envio) e o texto
  -- extra da cartela (o que o robô gravou, no relatório). O vídeo aprovado é o que vai ao ar: ele não pode levar o texto de antes
  if v.gancho is not null and v.ajustes->'sem_gancho' is distinct from 'true'::jsonb and v.gancho is distinct from btrim(p.chamada) then
    return 'Reel: o texto do gancho mudou depois da gravação (o vídeo tem o de antes): o administrador marca “Sem o texto do gancho” nos ajustes, ou envie a gravação de novo';
  end if;
  if v.relatorio ? 'cartela_extra' and v.relatorio->>'cartela_extra' is distinct from public.radar_video_cfg_texto('cartela_extra') then
    return 'Reel: o texto extra da cartela mudou nas Configurações depois da montagem: o administrador marca “Refazer a cartela” nos ajustes (o vídeo é montado de novo)';
  end if;
  if v.duracao_final > 90 then return 'Reel: o vídeo passou de 90 s'; end if;
  return null;
end $$;

-- ------------------------------------------- tela (cada função confere o papel; a ordem das travas é a peça e depois o vídeo)
-- Registra a gravação do reel ANTES de qualquer arquivo sair do celular (a função radar-video chama com o token de quem envia e só
-- depois entrega os tokens de envio). Confere, nesta ordem: a peça (reel, não aprovada, não cancelada, não publicada); a fala para
-- conferência (está no roteiro, palavra por palavra e na ordem); o boletim pago (no roteiro e na fala); as pessoas (quem fala está
-- marcada; cada pessoa marcada com o termo novo, maior de idade e com o termo de uso de imagem valendo hoje); a cartela; os clipes (de
-- 1 a 12, MP4 ou MOV, até 500 MB no total), as quatro declarações, o gancho e a cota do mês — com p_duracao (a soma das durações
-- que o navegador leu dos clipes, quando leu), a gravação tem de caber no que sobra do mês: senão os clipes subiriam inteiros e o robô
-- só pararia no passo da transcrição (cota_radar), gastando o envio, o tempo do robô e os minutos do GitHub. O vídeo vivo da peça continua valendo
-- até os clipes deste envio chegarem (radar_video_enviado o substitui): o envio abandonado, ou que falhou no meio, não leva o vídeo
-- bom junto; só o envio anterior que esperava os arquivos vira "substituido". Devolve {id, versao}.
drop function if exists public.radar_video_criar(bigint, jsonb, bigint, text, text[], boolean, text[]);
create or replace function public.radar_video_criar(p_peca bigint, p_partes jsonb, p_fala_pessoa bigint, p_fala_roteiro text,
                                                    p_cartela text[], p_gancho boolean, p_declaracoes text[], p_duracao numeric default null)
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
  -- 3. o boletim pago: só sim ou não (o trecho não aparece)
  if public.radar_pauta_copia_paga(array[p.roteiro, v_fala]) then
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
    if v_x is not null then
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
       or coalesce(v_parte->>'tipo', '') not in ('video/mp4','video/quicktime')
       or jsonb_typeof(v_parte->'bytes') is distinct from 'number' or (v_parte->>'bytes') !~ '^[0-9]{1,9}$' then
      raise exception 'RADAR306: o clipe nº % não confere (MP4 ou MOV, de 1 byte a 500 MB, na ordem)', v_n using errcode = 'P0001';
    end if;
    if (v_parte->>'bytes')::bigint not between 1 and 524288000 then
      raise exception 'RADAR306: o clipe nº % não confere (MP4 ou MOV, de 1 byte a 500 MB, na ordem)', v_n using errcode = 'P0001';
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
                                   enviado_por)
  values (p.id, v_versao, v_partes, p_fala_pessoa, p.pessoas, v_fala, public.radar_hash_texto(p.roteiro),
          array(select btrim(l) from unnest(p_cartela) with ordinality t(l, o) order by o),
          case when coalesce(p_gancho, false) then btrim(p.chamada) end,
          array(select d from unnest(v_decl) d), auth.uid())
  returning id into v_id;
  return jsonb_build_object('id', v_id, 'versao', v_versao);
end $$;

-- O envio que espera os arquivos (a função radar-video lê, com o token de quem chama, para renovar os tokens de envio e para conferir
-- os arquivos no fim): só quem registrou o envio, ou o administrador. Devolve {id, peca, partes}.
create or replace function public.radar_video_para_envio(p_id uuid) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare v public.radar_videos%rowtype;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR300: só o editor ou o administrador envia a gravação do reel' using errcode = '42501';
  end if;
  select * into v from public.radar_videos where id = p_id;
  if v.id is null or v.situacao <> 'aguardando_envio' then
    raise exception 'RADAR309: este envio não está esperando os arquivos (já foi para a fila, foi substituído ou descartado)' using errcode = 'P0001';
  end if;
  if v.enviado_por is distinct from auth.uid() and public.radar_papel() <> 'admin' then
    raise exception 'RADAR309: só quem começou o envio (ou o administrador) continua o envio' using errcode = 'P0001';
  end if;
  return jsonb_build_object('id', v.id, 'peca', v.peca_id, 'partes', v.partes);
end $$;

-- Os arquivos chegaram (a função radar-video conferiu cada clipe no armazenamento: tamanho e tipo): o envio vai para a fila do robô e
-- só agora o vídeo vivo anterior da peça vira "substituido". Confere de novo a peça (não aprovada, não cancelada, não publicada) e as
-- pessoas (o termo pode ter mudado durante o envio).
create or replace function public.radar_video_enviado(p_id uuid) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_peca bigint;
  p      public.radar_pauta_pecas%rowtype;
  v      public.radar_videos%rowtype;
  v_x    text;
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
  v_x := public.radar_video_pessoas_falta(p.id, v.fala_pessoa, v.pessoas);
  if v_x is not null then
    raise exception 'RADAR304: %', v_x using errcode = 'P0001';
  end if;
  update public.radar_videos set situacao = 'substituido', encerrado_em = now(), pego_em = null
   where peca_id = p.id and id <> v.id and situacao in ('na_fila','processando','pronto','regravar','erro');
  update public.radar_videos set situacao = 'na_fila', enviado_em = now(), fila_em = now(), reservas = 0, pessoas = v.pessoas where id = v.id;
  return jsonb_build_object('id', v.id, 'situacao', 'na_fila');
end $$;

-- Trava comum das funções da tela que mexem num vídeo pronto, para regravar ou com erro: a peça (não aprovada) e o vídeo, nessa ordem.
-- Devolve o vídeo travado.
create or replace function public.radar_video_travar(p_id uuid) returns public.radar_videos
language plpgsql security definer set search_path = public as $$
declare
  v_peca bigint;
  p      public.radar_pauta_pecas%rowtype;
  v      public.radar_videos%rowtype;
begin
  select peca_id into v_peca from public.radar_videos where id = p_id;
  select * into p from public.radar_pauta_pecas where id = v_peca for update;
  select * into v from public.radar_videos where id = p_id for update;
  if v.id is null then
    raise exception 'RADAR309: vídeo não encontrado' using errcode = 'P0001';
  end if;
  if p.situacao = 'aprovada' then
    raise exception 'RADAR301: a peça está aprovada: para mudar o vídeo, use Desfazer aprovação' using errcode = 'P0001';
  end if;
  if p.situacao = 'cancelada' then
    raise exception 'RADAR301: a peça está cancelada: para mudar o vídeo, use Reabrir' using errcode = 'P0001';
  end if;
  return v;
end $$;

-- O vídeo volta à fila sem novos arquivos: com a transcrição guardada (palavras_tentativa), só a montagem; sem ela, tudo de novo. As
-- pessoas conferem de novo (o termo, a idade, quem fala marcada): os clipes voltam ao robô.
create or replace function public.radar_video_refazer(v public.radar_videos) returns text
language plpgsql security definer set search_path = public as $$
declare v_x text;
begin
  if v.situacao not in ('pronto','regravar','erro') then
    raise exception 'RADAR309: só o vídeo pronto, para regravar ou com erro volta ao corretor (situação atual: %)', v.situacao using errcode = 'P0001';
  end if;
  if v.arquivos_apagados && array['bruto','textos'] then
    raise exception 'RADAR311: os clipes originais já foram apagados (prazo de guarda): envie a gravação de novo' using errcode = 'P0001';
  end if;
  v_x := public.radar_video_pessoas_falta(v.peca_id, v.fala_pessoa, v.pessoas);
  if v_x is not null then
    raise exception 'RADAR304: %', v_x using errcode = 'P0001';
  end if;
  return case when v.palavras_tentativa is null then 'completo' else 'montagem' end;
end $$;

-- Ajustes do administrador depois de ouvir a prévia (legenda, "manter este trecho", "a transcrição errou", legenda compacta, sem o
-- gancho, cartela refeita): o robô monta de novo, sem transcrever de novo — o áudio nunca muda. Devolve {id, modo}.
create or replace function public.radar_video_ajustar(p_id uuid, p_ajustes jsonb, p_cartela text[] default null) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v      public.radar_videos%rowtype;
  v_modo text;
  v_x    text;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR300: só o administrador ajusta o vídeo corrigido' using errcode = '42501';
  end if;
  v := public.radar_video_travar(p_id);
  v_modo := public.radar_video_refazer(v);
  v_x := public.radar_video_ajustes_falta(p_ajustes);
  if v_x is not null then
    raise exception 'RADAR310: %', v_x using errcode = 'P0001';
  end if;
  if p_cartela is not null then
    v_x := public.radar_video_cartela_falta(p_cartela, v.fala_pessoa);
    if v_x is not null then
      raise exception 'RADAR305: %', v_x using errcode = 'P0001';
    end if;
  end if;
  update public.radar_videos
     set ajustes = p_ajustes,
         cartela_linhas = case when p_cartela is null then cartela_linhas
                               else array(select btrim(l) from unnest(p_cartela) with ordinality t(l, o) order by o) end,
         modo = v_modo, situacao = 'na_fila', tentativas = 0, fila_em = now(), reservas = 0, pego_em = null, erro_codigo = null
   where id = v.id;
  return jsonb_build_object('id', v.id, 'modo', v_modo);
end $$;

-- O roteiro da peça mudou depois da gravação ("Conferir com o roteiro novo"): a fala para conferência nova tem de estar no roteiro
-- novo, sem o boletim pago. Com a MESMA fala (mudou só o que o corretor não usa: o "Texto na tela", os tempos, a tarja), o vídeo seria
-- o mesmo: só o roteiro novo fica registrado (roteiro_hash), sem voltar à fila, e os ajustes do administrador continuam valendo
-- (devolve modo null). Com a fala mudada, o robô alinha e monta de novo (o áudio é o mesmo): os ajustes que apontam um trecho do
-- alinhamento antigo (manter, a transcrição errou, a legenda editada) saem; ficam o estilo e o gancho. Devolve {id, modo}.
create or replace function public.radar_video_reconferir(p_id uuid, p_fala_roteiro text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v      public.radar_videos%rowtype;
  p      public.radar_pauta_pecas%rowtype;
  v_fala text := btrim(regexp_replace(coalesce(p_fala_roteiro, ''), '[[:space:]]+', ' ', 'g'));
  v_modo text;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR300: só o editor ou o administrador mexe no vídeo do reel' using errcode = '42501';
  end if;
  v := public.radar_video_travar(p_id);
  v_modo := public.radar_video_refazer(v);
  select * into p from public.radar_pauta_pecas where id = v.peca_id;
  if length(v_fala) not between 20 and 6000 or not public.radar_video_fala_no_roteiro(v_fala, p.roteiro) then
    raise exception 'RADAR302: a fala para conferência tem de estar no roteiro da peça, palavra por palavra e na ordem (ao menos 10 palavras)'
      using errcode = 'P0001';
  end if;
  if public.radar_pauta_copia_paga(array[p.roteiro, v_fala]) then
    raise exception 'RADAR303: o roteiro tem frase igual à do boletim pago (ITC): reescreva com palavras próprias' using errcode = 'P0001';
  end if;
  if v_fala = v.fala_roteiro then
    update public.radar_videos set roteiro_hash = public.radar_hash_texto(p.roteiro) where id = v.id;
    return jsonb_build_object('id', v.id, 'modo', null);
  end if;
  update public.radar_videos
     set fala_roteiro = v_fala, roteiro_hash = public.radar_hash_texto(p.roteiro), ajustes = ajustes - array['manter','transcricao_errou','legenda'],
         modo = v_modo, situacao = 'na_fila', tentativas = 0, fila_em = now(), reservas = 0, pego_em = null, erro_codigo = null
   where id = v.id;
  return jsonb_build_object('id', v.id, 'modo', v_modo);
end $$;

-- "Tentar de novo" depois de um erro (o robô parou: Azure ocupada, armazenamento fora do ar, tempo esgotado): o mesmo pedido volta à
-- fila, com as tentativas zeradas. Com p_cartela, as linhas da cartela são refeitas (conferidas como no envio): a cartela que não coube
-- ("cartela_nao_cabe") só sai do erro com as linhas de hoje — a identificação ou o nome na peça encurtados —, e o "Refazer a cartela"
-- dos ajustes pede o relatório final, que o vídeo parado antes da montagem não tem. Devolve {id, modo}.
drop function if exists public.radar_video_de_novo(uuid);
create or replace function public.radar_video_de_novo(p_id uuid, p_cartela text[] default null) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v      public.radar_videos%rowtype;
  v_modo text;
  v_x    text;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR300: só o editor ou o administrador mexe no vídeo do reel' using errcode = '42501';
  end if;
  v := public.radar_video_travar(p_id);
  if v.situacao <> 'erro' then
    raise exception 'RADAR309: só o vídeo com erro é tentado de novo (situação atual: %)', v.situacao using errcode = 'P0001';
  end if;
  v_modo := public.radar_video_refazer(v);
  if p_cartela is not null then
    v_x := public.radar_video_cartela_falta(p_cartela, v.fala_pessoa);
    if v_x is not null then
      raise exception 'RADAR305: %', v_x using errcode = 'P0001';
    end if;
  end if;
  update public.radar_videos set modo = v_modo, situacao = 'na_fila', tentativas = 0, fila_em = now(), reservas = 0, pego_em = null,
         erro_codigo = null,
         cartela_linhas = case when p_cartela is null then cartela_linhas
                               else array(select btrim(l) from unnest(p_cartela) with ordinality t(l, o) order by o) end
   where id = v.id;
  return jsonb_build_object('id', v.id, 'modo', v_modo);
end $$;

-- "Descartar" a gravação (a peça não pode estar aprovada). Os arquivos saem na limpeza seguinte; os textos, depois do prazo.
create or replace function public.radar_video_descartar(p_id uuid) returns boolean
language plpgsql security definer set search_path = public as $$
declare v public.radar_videos%rowtype;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR300: só o editor ou o administrador mexe no vídeo do reel' using errcode = '42501';
  end if;
  v := public.radar_video_travar(p_id);
  if v.situacao in ('substituido','descartado') then
    raise exception 'RADAR309: esta gravação já foi substituída ou descartada' using errcode = 'P0001';
  end if;
  update public.radar_videos set situacao = 'descartado', encerrado_em = now(), pego_em = null where id = v.id;
  return true;
end $$;

-- "Apaguei do celular e da nuvem pessoal" (o termo pede apagar no mesmo dia): só registra quem e quando; não trava nada.
create or replace function public.radar_video_apaguei(p_id uuid) returns timestamptz
language plpgsql security definer set search_path = public as $$
declare v_em timestamptz;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR300: só o editor ou o administrador mexe no vídeo do reel' using errcode = '42501';
  end if;
  update public.radar_videos
     set apagado_aparelho_em = coalesce(apagado_aparelho_em, now()), apagado_aparelho_por = coalesce(apagado_aparelho_por, auth.uid())
   where id = p_id
  returning apagado_aparelho_em into v_em;
  if v_em is null then
    raise exception 'RADAR309: vídeo não encontrado' using errcode = 'P0001';
  end if;
  return v_em;
end $$;

-- "Apaguei do celular e da nuvem pessoal (depois de postar)", depois de "Baixar o vídeo aprovado": registra que quem baixou apagou o
-- vídeo final do aparelho (radar_video_acessos, "apagou"), à parte dos clipes do envio (radar_video_apaguei). Só quem baixou este vídeo.
create or replace function public.radar_video_apaguei_baixado(p_id uuid) returns timestamptz
language plpgsql security definer set search_path = public as $$
declare v_em timestamptz;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR300: só o editor ou o administrador mexe no vídeo do reel' using errcode = '42501';
  end if;
  if not exists (select 1 from public.radar_video_acessos a where a.video_id = p_id and a.usuario = auth.uid() and a.acao = 'baixar') then
    raise exception 'RADAR309: o vídeo aprovado não foi baixado por você: nada a registrar' using errcode = 'P0001';
  end if;
  insert into public.radar_video_acessos (video_id, usuario, acao) values (p_id, auth.uid(), 'apagou') returning em into v_em;
  return v_em;
end $$;

-- A prévia (a função radar-video assina o vídeo e os 4 quadros por 600 s, prazo fixo nela): só o vídeo vivo pronto ou para regravar,
-- com o corrigido guardado, e com as pessoas do vídeo podendo aparecer nele HOJE (como o baixar: o termo revogado, o do corretor
-- retirado, a pessoa marcada menor ou inativa fecham a prévia na hora, sem esperar a limpeza). Registra quem viu. Devolve os caminhos
-- no bucket e o hash (que a aprovação manda de volta).
create or replace function public.radar_video_para_previa(p_id uuid) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v   public.radar_videos%rowtype;
  v_x text;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR300: só o editor ou o administrador vê o vídeo do reel' using errcode = '42501';
  end if;
  select * into v from public.radar_videos where id = p_id;
  if v.id is null or v.situacao not in ('pronto','regravar') or v.sha256 is null or 'corrigido' = any(v.arquivos_apagados) then
    raise exception 'RADAR309: o vídeo corrigido não está disponível (ainda não ficou pronto, foi substituído ou apagado)' using errcode = 'P0001';
  end if;
  v_x := public.radar_video_pessoas_falta(v.peca_id, v.fala_pessoa, v.pessoas);
  if v_x is not null then
    raise exception 'RADAR304: %', v_x using errcode = 'P0001';
  end if;
  insert into public.radar_video_acessos (video_id, usuario, acao) values (v.id, auth.uid(), 'previa');
  return jsonb_build_object('video', format('corrigido/%s/%s.mp4', v.id, v.sha256), 'sha256', v.sha256,
                            'quadros', (select jsonb_agg(format('quadros/%s/%s/q%s.jpg', v.id, v.sha256, k) order by k) from generate_series(1, 4) k));
end $$;

-- Baixar o vídeo aprovado para postar à mão: as conferências de radar_pauta_pode_copiar (aprovada à mão, a versão da tela, o termo de
-- hoje nos canais aprovados), o vídeo amarrado na aprovação (o mesmo hash, guardado) e, de novo, as pessoas no corretor. Registra quem
-- baixou. Devolve {ok, caminho, data} ou {motivo} (sem nome).
create or replace function public.radar_video_para_baixar(p_peca bigint, p_lido timestamptz) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_r jsonb;
  p   public.radar_pauta_pecas%rowtype;
  v   public.radar_videos%rowtype;
  v_i bigint;
  v_x text;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR300: só o editor ou o administrador baixa o vídeo do reel' using errcode = '42501';
  end if;
  v_r := public.radar_pauta_pode_copiar(p_peca, p_lido, null);
  if v_r ? 'motivo' then return v_r; end if;
  select * into p from public.radar_pauta_pecas where id = p_peca;
  if p.formato <> 'reel' or p.video_id is null or p.video_sha256 is null then
    return jsonb_build_object('motivo', 'Só o reel aprovado com o vídeo corrigido tem vídeo para baixar.');
  end if;
  select * into v from public.radar_videos where id = p.video_id;
  if v.sha256 is distinct from p.video_sha256 or v.situacao <> 'pronto' then
    return jsonb_build_object('motivo', 'O vídeo aprovado não é mais o vídeo da peça: desfaça a aprovação e confira.');
  end if;
  if 'corrigido' = any(v.arquivos_apagados) then
    return jsonb_build_object('motivo', 'O vídeo corrigido foi apagado (prazo de guarda): desfaça a aprovação e envie a gravação de novo.');
  end if;
  foreach v_i in array p.pessoas || array(select x from unnest(v.pessoas) x where not x = any(p.pessoas)) loop
    v_x := public.radar_video_pessoa_falta(v_i, p.id);
    if v_x is not null then
      return jsonb_build_object('motivo', format('Uma pessoa da peça não pode aparecer no vídeo hoje (%s): confira em Pauta → Pessoas e termos.', v_x));
    end if;
  end loop;
  insert into public.radar_video_acessos (video_id, usuario, acao) values (v.id, auth.uid(), 'baixar');
  return jsonb_build_object('ok', true, 'caminho', format('corrigido/%s/%s.mp4', v.id, v.sha256), 'data', p.data);
end $$;

-- As peças com a pessoa que já saíram (à mão ou pela agenda), com os links a retirar das redes no prazo do termo quando ela revoga o
-- termo ou fica inativa, e se ainda há vídeo dela guardado (a limpeza seguinte apaga). Só o administrador.
create or replace function public.radar_pauta_pecas_da_pessoa(p_pessoa bigint)
returns table(peca bigint, data date, link_instagram text, link_facebook text, video_guardado boolean)
language plpgsql stable security definer set search_path = public as $$
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR300: só o administrador vê as peças publicadas de uma pessoa' using errcode = '42501';
  end if;
  return query
    select p.id, p.data,
           coalesce(p.link_instagram, (select e.url from public.radar_redes_envios e
                                        where e.peca_id = p.id and e.canal = 'instagram' and e.situacao = 'publicado' order by e.id desc limit 1)),
           coalesce(p.link_facebook, (select e.url from public.radar_redes_envios e
                                       where e.peca_id = p.id and e.canal = 'facebook' and e.situacao = 'publicado' order by e.id desc limit 1)),
           exists (select 1 from public.radar_videos v where v.peca_id = p.id and v.situacao <> 'aguardando_envio'
                      and not v.arquivos_apagados @> array['bruto','trabalho','corrigido'])
      from public.radar_pauta_pecas p
     where (p_pessoa = any(p.pessoas)
            -- o reel publicado com o vídeo em que a pessoa estava (desmarcada depois, ela continua no vídeo)
            or exists (select 1 from public.radar_videos v where v.id = p.video_id and p_pessoa = any(v.pessoas || v.fala_pessoa)))
       and (p.publicado_manual_em is not null
            or exists (select 1 from public.radar_redes_envios e where e.peca_id = p.id and e.situacao = 'publicado'))
     order by p.data, p.id;
end $$;

-- Quanto o corretor ainda transcreve neste mês (o editor e o administrador): a tela mostra antes do envio, e o banco confere de novo
-- em radar_video_criar com a duração dos clipes. Só os dois números.
create or replace function public.radar_video_cota() returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR300: só o editor ou o administrador envia a gravação do reel' using errcode = '42501';
  end if;
  return jsonb_build_object('segundos_mes', public.radar_video_segundos_mes(), 'limite_s', public.radar_video_limite_s());
end $$;

-- O diagnóstico da radar-video (só o administrador): a fila, há quanto tempo o mais antigo espera e a cota do mês.
create or replace function public.radar_video_resumo() returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR300: só o administrador vê o diagnóstico do corretor de vídeo' using errcode = '42501';
  end if;
  return jsonb_build_object(
    'na_fila', (select count(*) from public.radar_videos where situacao = 'na_fila'),
    'processando', (select count(*) from public.radar_videos where situacao = 'processando'),
    'espera_s', (select extract(epoch from now() - min(fila_em))::int from public.radar_videos where situacao = 'na_fila'),
    'segundos_mes', public.radar_video_segundos_mes(), 'limite_s', public.radar_video_limite_s());
end $$;

-- ------------------------------------------- função radar-video e robô (só o papel interno; o robô chega aqui só pela radar-video)
-- A chave do robô (cabeçalho x-radar-video-robo) e a da agenda (x-radar-agenda) estão no Vault ('radar_video_robo' e
-- 'radar_video_agenda', criadas por sql/radar-video-agenda.sql); a função confere por aqui. Sem o Vault (ou sem a chave), nunca confere.
-- Compara os resumos (sha256), e não as chaves: o "=" de texto para no primeiro byte diferente, e o tempo diria quanto do começo da
-- chave confere; o do resumo não diz nada da chave.
create or replace function public.radar_video_conferir_robo(p_chave text) returns boolean
language plpgsql stable security definer set search_path = public as $$
declare v_certa text;
begin
  if length(coalesce(p_chave, '')) < 32 then return false; end if;
  execute 'select decrypted_secret from vault.decrypted_secrets where name = ''radar_video_robo'' limit 1' into v_certa;
  return v_certa is not null and length(v_certa) >= 32 and sha256(convert_to(v_certa, 'UTF8')) = sha256(convert_to(p_chave, 'UTF8'));
exception when others then
  return false;
end $$;
create or replace function public.radar_video_conferir_agenda(p_chave text) returns boolean
language plpgsql stable security definer set search_path = public as $$
declare v_certa text;
begin
  if length(coalesce(p_chave, '')) < 32 then return false; end if;
  execute 'select decrypted_secret from vault.decrypted_secrets where name = ''radar_video_agenda'' limit 1' into v_certa;
  return v_certa is not null and length(v_certa) >= 32 and sha256(convert_to(v_certa, 'UTF8')) = sha256(convert_to(p_chave, 'UTF8'));
exception when others then
  return false;
end $$;

-- Há trabalho para o robô? Pedido na fila há p_minutos ou mais ou parado em "processando" há mais de 20 minutos (radar_video_pegar
-- devolve à fila). A função radar-video confere antes de acionar.
create or replace function public.radar_video_ha_fila(p_minutos int default 0) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.radar_videos v
                  where (v.situacao = 'na_fila' and v.fila_em <= now() - make_interval(mins => greatest(coalesce(p_minutos, 0), 0)))
                     or (v.situacao = 'processando' and v.pego_em < now() - interval '20 minutes'))
$$;

-- A reserva da agenda (sql/radar-video-agenda.sql, de 10 em 10 minutos) aciona o robô? Só com pedido esperando há 3 minutos ou mais
-- (a tela já acionou na hora) ou parado em "processando" há mais de 20, e nunca enquanto o robô trabalha num pedido (pegou há menos de
-- 20 minutos: os acionamentos que esperam na fila do GitHub seguem sozinhos). Cada acionamento conta no pedido que espera (reservas);
-- no 3º sem o robô pegar — a chave do robô (RADAR_VIDEO_ROBO_CHAVE) ou as variáveis RADAR_VIDEO_URL e RADAR_VIDEO_COMMIT erradas, o
-- token do GitHub vencido, o workflow desligado —, o pedido vira erro "robo_nao_pegou": um aviso só, na peça, e a reserva para (sem
-- uma execução vermelha a cada 10 minutos nem os minutos do GitHub gastos à toa) até alguém mandar tentar de novo ou enviar de novo.
create or replace function public.radar_video_reserva() returns boolean
language plpgsql security definer set search_path = public as $$
begin
  if exists (select 1 from public.radar_videos where situacao = 'processando' and pego_em >= now() - interval '20 minutes') then
    return false;
  end if;
  update public.radar_videos set situacao = 'erro', erro_codigo = 'robo_nao_pegou', pego_em = null
   where reservas >= 3 and (situacao = 'na_fila' or (situacao = 'processando' and pego_em < now() - interval '20 minutes'));
  update public.radar_videos set reservas = reservas + 1
   where (situacao = 'na_fila' and fila_em <= now() - interval '3 minutes')
      or (situacao = 'processando' and pego_em < now() - interval '20 minutes');
  return found;
end $$;

-- O robô pega o próximo pedido. Antes, o que ficou parado em "processando" há mais de 20 minutos volta à fila (até 3 tentativas; com a
-- transcrição já guardada, só para a montagem) ou vira erro "tempo_esgotado". Do mais antigo da fila (o outro robô pula o que está
-- travado): a peça com uma pessoa que não pode mais aparecer (termo revogado ou vencido, inativa, menor, quem fala desmarcada, a marca
-- de sócio(a) tirada sem os termos — v0.28.0: radar_video_pessoas_falta) vira erro "termo" ANTES de qualquer clipe sair para o robô ou áudio para a Azure; sem a transcrição
-- guardada e com a cota do mês esgotada, vira erro "cota_radar"; e pega o próximo. Marca "processando", a tentativa (até 3 por pedido)
-- e a rodada (o <t> de trabalho/<id>/<t>/, que nunca se repete no mesmo vídeo). Devolve o pedido — a fala para conferência, a cartela,
-- o gancho, os ajustes, os clipes, a transcrição guardada, o que sobra da cota em segundos e as Configurações — ou NULL. Nenhum nome
-- além do que vai na cartela.
create or replace function public.radar_video_pegar() returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v        public.radar_videos%rowtype;
  r        record;
  v_limite numeric := public.radar_video_limite_s();
  v_usado  numeric;
begin
  for r in select id, tentativas from public.radar_videos
            where situacao = 'processando' and pego_em < now() - interval '20 minutes' for update skip locked loop
    if r.tentativas < 3 then
      update public.radar_videos set situacao = 'na_fila', fila_em = now(), reservas = 0, pego_em = null,
             modo = case when palavras_tentativa is not null then 'montagem' else modo end where id = r.id;
    else
      update public.radar_videos set situacao = 'erro', erro_codigo = 'tempo_esgotado', pego_em = null where id = r.id;
    end if;
  end loop;
  loop
    select * into v from public.radar_videos where situacao = 'na_fila' order by fila_em nulls first, criado_em limit 1 for update skip locked;
    if v.id is null then return null; end if;
    if v.arquivos_apagados && array['bruto','textos'] or v.tentativas >= 3 or v.rodada >= 200 then
      update public.radar_videos set situacao = 'erro', erro_codigo = case when v.tentativas >= 3 then 'tentativas' else 'arquivos_apagados' end
       where id = v.id;
      continue;
    end if;
    if public.radar_video_pessoas_falta(v.peca_id, v.fala_pessoa, v.pessoas) is not null then
      update public.radar_videos set situacao = 'erro', erro_codigo = 'termo' where id = v.id;
      continue;
    end if;
    v_usado := public.radar_video_segundos_mes();
    if v.modo = 'completo' and v.palavras_tentativa is null and v_usado >= v_limite then
      update public.radar_videos set situacao = 'erro', erro_codigo = 'cota_radar' where id = v.id;
      continue;
    end if;
    update public.radar_videos set situacao = 'processando', pego_em = now(), tentativas = tentativas + 1, rodada = rodada + 1, reservas = 0
     where id = v.id returning * into v;
    return jsonb_build_object('id', v.id, 'tentativa', v.rodada, 'modo', v.modo, 'partes', v.partes, 'fala_roteiro', v.fala_roteiro,
                              'cartela_linhas', to_jsonb(v.cartela_linhas), 'gancho', v.gancho, 'ajustes', v.ajustes,
                              'palavras_tentativa', v.palavras_tentativa, 'restante_s', greatest(v_limite - v_usado, 0),
                              'config', public.radar_video_config());
  end loop;
end $$;

-- O pedido ainda é deste robô, nesta rodada (p_tentativa)? Senão RADAR316: foi substituído, descartado, ajustado ou passou do tempo, e o
-- robô para sem gravar nada. Com p_travar, trava o vídeo (as funções que gravam).
create or replace function public.radar_video_do_robo(p_id uuid, p_tentativa int, p_travar boolean default false) returns public.radar_videos
language plpgsql security definer set search_path = public as $$
declare v public.radar_videos%rowtype;
begin
  if p_travar then
    select * into v from public.radar_videos where id = p_id for update;
  else
    select * into v from public.radar_videos where id = p_id;
  end if;
  if v.id is null or v.situacao <> 'processando' or v.rodada is distinct from p_tentativa then
    raise exception 'RADAR316: este pedido não está mais com o robô nesta tentativa (foi substituído, descartado, ajustado ou passou do tempo)'
      using errcode = 'P0001';
  end if;
  return v;
end $$;

-- A função radar-video confere, antes de dar um link ao robô, que o pedido está com ele e que a limpeza não apagou os clipes nem os
-- textos dele no meio do caminho (a revogação de uma pessoa da peça, o prazo): nenhum link novo, nada que suba depois da limpeza e
-- fique órfão no armazenamento. Devolve o que ela precisa para montar os caminhos (nenhum texto do pedido).
create or replace function public.radar_video_em_curso(p_id uuid, p_tentativa int) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare v public.radar_videos%rowtype;
begin
  v := public.radar_video_do_robo(p_id, p_tentativa);
  if v.arquivos_apagados && array['bruto','textos'] then
    raise exception 'RADAR316: os clipes ou os textos deste pedido foram apagados (revogação ou prazo de guarda)' using errcode = 'P0001';
  end if;
  return jsonb_build_object('id', v.id, 'tentativa', v.rodada, 'modo', v.modo, 'partes', jsonb_array_length(v.partes),
                            'palavras_tentativa', v.palavras_tentativa, 'sha256', v.sha256);
end $$;

-- O robô transcreveu (Azure, no passo próprio do workflow): soma os segundos de áudio na cota do mês — uma vez por rodada (audio_rodada:
-- o robô repete a chamada que falhou no caminho sem contar duas vezes) — e, se a radar-video achou o palavras.json desta rodada no
-- armazenamento (p_palavras), é ele que vale daqui em diante (o ajuste monta sem transcrever de novo). Devolve {restante_s}.
create or replace function public.radar_video_registrar_audio(p_id uuid, p_tentativa int, p_segundos numeric, p_palavras boolean) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v       public.radar_videos%rowtype;
  v_somar boolean;
begin
  v := public.radar_video_do_robo(p_id, p_tentativa, true);
  if p_segundos is null or p_segundos < 0 or p_segundos > 300 then
    raise exception 'RADAR316: segundos de áudio fora do esperado (de 0 a 300)' using errcode = 'P0001';
  end if;
  v_somar := p_segundos > 0 and v.audio_rodada is distinct from v.rodada;
  update public.radar_videos
     set segundos_audio = case when v_somar then least(coalesce(segundos_audio, 0) + round(p_segundos, 1), 3600) else segundos_audio end,
         transcrito_em = case when v_somar then now() else transcrito_em end,
         audio_rodada = case when p_segundos > 0 then v.rodada else audio_rodada end,
         palavras_tentativa = case when coalesce(p_palavras, false) then v.rodada else palavras_tentativa end
   where id = v.id;
  return jsonb_build_object('restante_s', greatest(public.radar_video_limite_s() - public.radar_video_segundos_mes(), 0));
end $$;

-- O relatório parcial (logo depois do alinhamento, antes da montagem): a equipe sabe se precisa regravar sem esperar o vídeo.
create or replace function public.radar_video_parcial(p_id uuid, p_tentativa int, p_relatorio jsonb) returns boolean
language plpgsql security definer set search_path = public as $$
declare v public.radar_videos%rowtype;
begin
  v := public.radar_video_do_robo(p_id, p_tentativa, true);
  if v.arquivos_apagados && array['bruto','textos'] then                    -- a limpeza passou no meio: o relatório não volta
    raise exception 'RADAR316: os clipes ou os textos deste pedido foram apagados (revogação ou prazo de guarda)' using errcode = 'P0001';
  end if;
  if p_relatorio is null or jsonb_typeof(p_relatorio) <> 'object' or length(p_relatorio::text) > 59000 then
    raise exception 'RADAR316: relatório parcial fora do formato' using errcode = 'P0001';
  end if;
  update public.radar_videos set relatorio = p_relatorio || '{"parcial": true}'::jsonb where id = v.id;
  return true;
end $$;

-- O robô terminou (a radar-video já conferiu no armazenamento o corrigido/<id>/<sha256>.mp4, com o tamanho, e os 4 quadros). O banco
-- decide a situação de novo, sem confiar no robô: a divergência (número, prazo ou termo) que o administrador não marcou "a transcrição
-- errou" (ajustes.transcricao_errou, pelo id da divergência, e não pela posição na lista, que muda de uma rodada para a outra) e a fala
-- com frase do boletim pago (aviso "boletim_pago") dão "regravar". Devolve {situacao}.
create or replace function public.radar_video_concluir(p_id uuid, p_tentativa int, p_situacao text, p_relatorio jsonb, p_sha256 text,
                                                       p_bytes bigint, p_duracao numeric) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v      public.radar_videos%rowtype;
  v_rel  jsonb;
  v_sit  text := p_situacao;
  v_err  jsonb;
begin
  v := public.radar_video_do_robo(p_id, p_tentativa, true);
  if v.arquivos_apagados && array['bruto','textos'] then                    -- a limpeza passou no meio: o relatório (a fala) não volta
    raise exception 'RADAR316: os clipes ou os textos deste pedido foram apagados (revogação ou prazo de guarda)' using errcode = 'P0001';
  end if;
  if p_situacao is null or p_situacao not in ('pronto','regravar') then
    raise exception 'RADAR316: situação final fora do esperado' using errcode = 'P0001';
  end if;
  if p_sha256 is null or p_sha256 !~ '^[0-9a-f]{64}$' or p_bytes is null or p_bytes not between 1 and 314572800
     or p_duracao is null or p_duracao <= 0 or p_duracao > 600 then
    raise exception 'RADAR316: o vídeo corrigido não confere (hash, tamanho ou duração)' using errcode = 'P0001';
  end if;
  if p_relatorio is null or jsonb_typeof(p_relatorio) <> 'object' or length(p_relatorio::text) > 59000 then
    raise exception 'RADAR316: relatório fora do formato' using errcode = 'P0001';
  end if;
  v_rel := p_relatorio || '{"parcial": false}'::jsonb;
  v_err := case when jsonb_typeof(v.ajustes->'transcricao_errou') = 'array' then v.ajustes->'transcricao_errou' else '[]'::jsonb end;
  if exists (select 1 from jsonb_array_elements(case when jsonb_typeof(v_rel->'divergencias') = 'array' then v_rel->'divergencias' else '[]' end) d
              where jsonb_typeof(d) <> 'object' or coalesce(d->'regravar', 'true'::jsonb) <> 'false'::jsonb
                    and not exists (select 1 from jsonb_array_elements(v_err) k where k = d->'id')) then
    v_sit := 'regravar';
  end if;
  if public.radar_pauta_copia_paga(array[coalesce(v_rel->>'texto_final', '')]) then
    v_sit := 'regravar';
    v_rel := v_rel || jsonb_build_object('avisos', (case when jsonb_typeof(v_rel->'avisos') = 'array' then v_rel->'avisos' else '[]'::jsonb end)
                                                   || '["boletim_pago"]'::jsonb);
  end if;
  update public.radar_videos
     set situacao = v_sit, relatorio = v_rel, sha256 = p_sha256, bytes = p_bytes, duracao_final = round(p_duracao, 2),
         erro_codigo = null, pego_em = null, antigos = antigos or (sha256 is not null and sha256 <> p_sha256)
   where id = v.id;
  return jsonb_build_object('situacao', v_sit);
end $$;

-- O robô parou com erro (código fixo, ^[a-z_]{3,40}$; outro vira "erro_interno"). Os transitórios (armazenamento, rede, Azure fora do
-- ar, GitHub) voltam à fila enquanto há tentativa (até 3) — se a transcrição desta gravação já ficou guardada, só para a montagem (não
-- gasta a cota de novo); os outros — a recusa da entrada, a cota, a Azure ocupada por 10 minutos ("transcricao_ocupada": a equipe tenta
-- de novo) — viram "erro". Devolve {situacao}.
create or replace function public.radar_video_falhar(p_id uuid, p_tentativa int, p_codigo text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v     public.radar_videos%rowtype;
  v_cod text := case when coalesce(p_codigo, '') ~ '^[a-z_]{3,40}$' then p_codigo else 'erro_interno' end;
  v_sit text;
begin
  v := public.radar_video_do_robo(p_id, p_tentativa, true);
  v_sit := case when v_cod in ('storage','rede','azure_fora','github') and v.tentativas < 3 then 'na_fila' else 'erro' end;
  update public.radar_videos
     set situacao = v_sit, erro_codigo = v_cod, pego_em = null, fila_em = case when v_sit = 'na_fila' then now() else fila_em end, reservas = 0,
         modo = case when v_sit = 'na_fila' and palavras_tentativa is not null then 'montagem' else modo end
   where id = v.id;
  return jsonb_build_object('situacao', v_sit);
end $$;

-- A limpeza diária (sql/radar-video-agenda.sql chama a radar-video, ação "limpar", que chama aqui). Prazos: retencao_dias (padrão 30,
-- de 7 a 120) e retencao_publicado_dias (padrão 30, de 0 a 365) de Configurações → Corretor de vídeo.
--   bruto e trabalho (os clipes e a transcrição): ao publicar, ao substituir ou descartar, na revogação ou inativação de uma pessoa do
--     vídeo (marcada na peça ou no envio), no termo do corretor retirado, na pessoa marcada menor de idade, no envio abandonado (esperando os arquivos há mais de 1 dia, que vira "descartado") ou retencao_dias depois do envio;
--     (v0.28.0: de sócio(a) da Artecon, maior de idade, a revogação e o termo do corretor não contam; "Ativa" desmarcada e a marca de
--     sócio(a) tirada sem os termos, sim)
--   corrigido (o vídeo e os quadros): ao substituir ou descartar, na revogação ou inativação, retencao_publicado_dias depois de sair ou,
--     sem sair, retencao_dias depois do envio — o vídeo amarrado à peça aprovada que ainda não saiu (espera o dia de postar), contado
--     do dia da peça, se for depois do envio; as versões antigas do mesmo vídeo (ajustes), na limpeza seguinte ("antigos");
--   textos (a fala, o relatório, os ajustes e a cartela, aqui no banco, apagados agora): retencao_publicado_dias depois de sair,
--     retencao_dias depois de substituir ou descartar, junto com o corrigido que sai pelo prazo sem a peça ter saído (peça cancelada,
--     reel adiado) e na revogação ou inativação. Nada fica para sempre.
-- Como prova ficam o hash, as datas, os links e o termo. Devolve {itens: [{id, apagar: [grupos], manter: sha256}], textos} — no máximo
-- 50 itens por vez; a função apaga os arquivos pela API do armazenamento e confirma cada um em radar_video_limpo.
create or replace function public.radar_video_limpeza() returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_d      interval := make_interval(days => public.radar_video_cfg_num('retencao_dias', 30, 7, 120)::int);
  v_pd     interval := make_interval(days => public.radar_video_cfg_num('retencao_publicado_dias', 30, 0, 365)::int);
  v_hoje   date := public.radar_pauta_hoje();
  r        record;
  v_enc    boolean;
  v_aband  boolean;
  v_velho  boolean;
  v_velho_corr boolean;
  v_grupos text[];
  v_itens  jsonb := '[]'::jsonb;
  v_textos int := 0;
begin
  for r in
    select v.id, v.situacao, v.criado_em, v.enviado_em, v.encerrado_em, v.arquivos_apagados, v.antigos, v.sha256,
           -- o vídeo da peça aprovada, que espera o dia de postar: o prazo do corrigido conta do dia da peça (se for depois do envio)
           case when p.situacao = 'aprovada' and p.video_id = v.id
                then greatest(coalesce(v.enviado_em, v.criado_em), p.data::timestamp at time zone 'America/Sao_Paulo')
                else coalesce(v.enviado_em, v.criado_em) end as prazo_corrigido,
           least(case when p.publicado_manual_em is not null then p.publicado_manual_em::timestamp at time zone 'America/Sao_Paulo' end,
                 (select min(e.publicado_em) from public.radar_redes_envios e where e.peca_id = p.id and e.publicado_em is not null)) as saiu_em,
           -- uma pessoa do vídeo (as marcadas hoje e as do envio, radar_videos.pessoas) que não pode mais estar nele: o termo revogado,
           -- inativa, o termo do corretor retirado (ou com data no futuro) ou marcada menor de idade — os motivos de radar_video_pessoa_falta
           -- que tiram a autorização (o termo de imagem só vencido fica de fora: ele pode ser renovado)
           exists (select 1 from public.radar_pessoas pe
                    where pe.id = any(p.pessoas || v.pessoas || v.fala_pessoa)
                      and (not pe.ativo or pe.menor
                           -- v0.28.0: de sócio(a) da Artecon (maior de idade) os termos não são exigidos: a revogação e o termo do
                           -- corretor não contam (quem tira o vídeo dele(a) é "Ativa" desmarcada, ou a marca de sócio(a) tirada sem os termos)
                           or (not pe.socio and ((pe.termo_revogado_em is not null and pe.termo_revogado_em <= v_hoje)
                                                 or pe.termo_corretor_em is null or pe.termo_corretor_em > v_hoje))))
           -- v0.22.0 (varredura geral): a pessoa que nem existe mais (apagada antes da trava de radar_fn_pessoa_apagar) também
           or exists (select 1 from unnest(p.pessoas || v.pessoas || v.fala_pessoa) x
                       where not exists (select 1 from public.radar_pessoas pe where pe.id = x)) as revogado
      from public.radar_videos v join public.radar_pauta_pecas p on p.id = v.peca_id
     where not v.arquivos_apagados @> array['bruto','trabalho','corrigido','textos'] or v.antigos
     order by v.criado_em
     for update of v skip locked
  loop
    v_enc   := r.situacao in ('substituido','descartado');
    v_aband := r.situacao = 'aguardando_envio' and r.criado_em < now() - interval '1 day';
    v_velho := coalesce(r.enviado_em, r.criado_em) < now() - v_d;
    v_velho_corr := r.prazo_corrigido < now() - v_d;
    v_grupos := '{}';
    if v_enc or v_aband or r.revogado or r.saiu_em is not null or v_velho then
      v_grupos := v_grupos || array['bruto','trabalho'];
    end if;
    if v_enc or v_aband or r.revogado or r.saiu_em < now() - v_pd or (r.saiu_em is null and v_velho_corr) then
      v_grupos := v_grupos || array['corrigido'];
    end if;
    v_grupos := array(select g from unnest(v_grupos) g where not g = any(r.arquivos_apagados));
    -- as versões antigas do vídeo corrigido (cada ajuste gera um sha256 novo); nunca enquanto o robô monta outra
    if r.antigos and not 'corrigido' = any(v_grupos || r.arquivos_apagados) and r.situacao in ('pronto','regravar','erro') then
      v_grupos := v_grupos || array['antigos'];
    end if;
    if not 'textos' = any(r.arquivos_apagados)
       and (r.revogado or (v_enc and r.encerrado_em < now() - v_d) or r.saiu_em < now() - v_pd
            or (r.saiu_em is null and v_velho_corr and not v_enc and not v_aband)) then
      update public.radar_videos
         set fala_roteiro = '', relatorio = '{}', ajustes = '{}', cartela_linhas = '{}',
             arquivos_apagados = array(select distinct g from unnest(arquivos_apagados || array['textos']) g order by g)
       where id = r.id;
      v_textos := v_textos + 1;
    end if;
    if cardinality(v_grupos) > 0 and jsonb_array_length(v_itens) < 50 then
      v_itens := v_itens || jsonb_build_array(jsonb_build_object('id', r.id, 'apagar', to_jsonb(v_grupos),
                                                                 'manter', case when 'antigos' = any(v_grupos) then r.sha256 end));
    end if;
  end loop;
  return jsonb_build_object('itens', v_itens, 'textos', v_textos);
end $$;

-- A radar-video apagou os arquivos destes grupos (bruto, trabalho, corrigido; "antigos": só as versões antigas do corrigido): registra.
-- O envio abandonado que perdeu os clipes vira "descartado".
create or replace function public.radar_video_limpo(p_id uuid, p_grupos text[]) returns boolean
language plpgsql security definer set search_path = public as $$
declare v_g text[] := array(select distinct g from unnest(coalesce(p_grupos, '{}')) g where g in ('bruto','trabalho','corrigido'));
begin
  update public.radar_videos
     set arquivos_apagados = array(select distinct g from unnest(arquivos_apagados || v_g) g order by g),
         antigos = antigos and not ('antigos' = any(coalesce(p_grupos, '{}')) or 'corrigido' = any(v_g)),
         encerrado_em = case when situacao = 'aguardando_envio' and 'bruto' = any(v_g) then now() else encerrado_em end,
         situacao = case when situacao = 'aguardando_envio' and 'bruto' = any(v_g) then 'descartado' else situacao end
   where id = p_id;
  return found;
end $$;

-- ---------------------------------------------------------------- v0.29.0: lembretes antes do dia
-- O Radar lembra ANTES do dia, por e-mail (o aviso no GitHub que o robô dos lembretes abre ou comenta: robo/radar_lembretes.py). Quem
-- decide o que lembrar e quando é o banco; a agenda (pg_cron, sql/radar-redes-agenda.sql) só pede o robô ao GitHub quando há o que
-- mandar. Regras do dono: no máximo um e-mail por tipo por dia; cada pendência é lembrada uma vez só ("avisado_em") e fecha sozinha
-- quando é resolvida ("resolvido_em"); nada de nome, assunto, legenda, erro ou texto do boletim no e-mail (só o que está em "ref").
-- "Hoje" é sempre o dia de Brasília (nenhuma destas funções usa current_date). p_agora é o relógio: a agenda e o robô passam now(); os
-- testes, uma hora fixa.

-- Configurações → Lembretes por e-mail, com o padrão no que faltar ou estiver fora dos limites (como radar_pauta_janela: nada do que está
-- ali trava os lembretes). "ligado" e os 4 tipos: true ou false (padrão true); "hora", "de" e "ate": "HH:MM" de Brasília (padrão "16:00",
-- "08:00" e "20:00"; com "de" depois de "ate", valem os dois padrões); "aprovacao_horas": inteiro de 1 a 168 (padrão 24);
-- "parada_horas": inteiro de 1 a 48 (padrão 3).
create or replace function public.radar_lembretes_cfg() returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v    jsonb := coalesce((select c.valor from public.radar_config c where c.chave = 'lembretes' and jsonb_typeof(c.valor) = 'object'), '{}');
  r    jsonb := '{}';
  k    text;
  rx   constant text := '^([01][0-9]|2[0-3]):[0-5][0-9]$';
  hora constant jsonb := '{"hora": "16:00", "de": "08:00", "ate": "20:00"}';
  num  constant jsonb := '{"aprovacao_horas": [1, 168, 24], "parada_horas": [1, 48, 3]}';
begin
  foreach k in array array['ligado','pauta','aprovacao','video','noticia'] loop
    r := r || jsonb_build_object(k, case when jsonb_typeof(v->k) = 'boolean' then v->k else 'true'::jsonb end);
  end loop;
  foreach k in array array['hora','de','ate'] loop
    r := r || jsonb_build_object(k, case when jsonb_typeof(v->k) = 'string' and v->>k ~ rx then v->k else hora->k end);
  end loop;
  if (r->>'de')::time > (r->>'ate')::time then
    r := r || jsonb_build_object('de', hora->'de', 'ate', hora->'ate');
  end if;
  foreach k in array array['aprovacao_horas','parada_horas'] loop
    r := r || jsonb_build_object(k, case when jsonb_typeof(v->k) is distinct from 'number' then num->k->2
                                         when (v->>k)::numeric <> trunc((v->>k)::numeric)
                                              or (v->>k)::numeric not between (num->k->>0)::numeric and (num->k->>1)::numeric then num->k->2
                                         else to_jsonb((v->>k)::numeric::int) end);
  end loop;
  return r;
end $$;

-- A pendência já pode ser lembrada? A peça pronta só depois de "aprovacao_horas" pronta (desde aberto_em); as outras, na hora.
create or replace function public.radar_lembretes_madura(p_tipo text, p_aberto timestamptz, p_cfg jsonb, p_agora timestamptz) returns boolean
language sql immutable set search_path = public as $$
  select p_tipo <> 'aprovacao' or p_aberto <= p_agora - make_interval(hours => (p_cfg->>'aprovacao_horas')::int)
$$;

-- O que está pendente agora, comparado com o que já está em radar_lembretes: a pendência nova entra; a que ainda não foi avisada (nem
-- reservada pelo robô) fica com o "ref" de agora; a que sumiu ganha resolvido_em (fecha); a resolvida há mais de 90 dias sai. Só o
-- dono executa (a agenda, o robô e a tela chegam aqui pelas funções abaixo). Peça cancelada, "sem post" ou sem formato não entra.
--   pauta     a peça de hoje ou de amanhã ainda não aprovada (planejada, em produção ou pronta) e a de hoje aprovada para publicar à mão
--             e ainda sem o registro da publicação. A chave não muda de um dia para o outro: lembrada na véspera, não é lembrada de novo
--             no dia (a de hoje entra só se ainda não foi lembrada: criada hoje, por exemplo)
--   aprovacao a peça pronta que espera a aprovação do administrador, desde quando ficou pronta (a de hoje e a de amanhã ficam com o
--             lembrete da Pauta, quando ele está ligado: um lembrete só por peça)
--   video     o vídeo do reel que o corretor terminou (pronto para conferir, precisa regravar ou parou), enquanto a peça (de hoje em
--             diante) não for aprovada com ele; cada resultado novo do corretor (outra rodada, outra situação) é um episódio novo
--   noticia   o envio ao site com erro (o mais novo do conteúdo, que continua aprovado, vai ao site e ainda não está no site), a
--             autorização do site parada há mais de "parada_horas" (o robô do site depende do GitHub, que atrasa), e o Instagram e o
--             Facebook da notícia com erro ou parados (os da Pauta têm o aviso "publicação agendada não saiu"). Erro de mais de 7 dias
--             fica de fora (a primeira rodada não traz o que é antigo)
create or replace function public.radar_lembretes_observar(p_agora timestamptz) returns void
language plpgsql security definer set search_path = public as $$
declare
  v_cfg    jsonb := public.radar_lembretes_cfg();
  v_hoje   date := (p_agora at time zone 'America/Sao_Paulo')::date;
  v_parada interval := make_interval(hours => (v_cfg->>'parada_horas')::int);
  v_aprov  date := (p_agora at time zone 'America/Sao_Paulo')::date + case when (v_cfg->>'pauta')::boolean then 2 else 0 end;
  v_n      int;
begin
  perform pg_advisory_xact_lock(hashtext('radar_lembretes'));        -- a agenda e o robô ao mesmo tempo: um de cada vez
  with atuais (tipo, chave, ref, aberto_em) as (
    select 'pauta'::text, 'peca:' || p.id || ':' || to_char(p.data, 'YYYY-MM-DD'),
           jsonb_build_object('n', p.id, 'data', to_char(p.data, 'YYYY-MM-DD'), 'hora', to_char(p.hora, 'HH24:MI'), 'formato', p.formato,
                              'situacao', p.situacao), p_agora
      from public.radar_pauta_pecas p
     where p.data in (v_hoje, v_hoje + 1) and p.situacao in ('planejada','em_producao','pronta')
       and p.tipo <> 'sem_post' and p.formato <> 'nenhum'
    union all
    select 'pauta', 'peca:' || p.id || ':' || to_char(p.data, 'YYYY-MM-DD') || ':manual',
           jsonb_build_object('n', p.id, 'data', to_char(p.data, 'YYYY-MM-DD'), 'hora', to_char(p.hora, 'HH24:MI'), 'formato', p.formato,
                              'situacao', 'aprovada_manual'), p_agora
      from public.radar_pauta_pecas p
     where p.data = v_hoje and p.situacao = 'aprovada' and p.aprovado_modo = 'manual' and p.publicado_manual_em is null
       and p.link_instagram is null and p.link_facebook is null and p.tipo <> 'sem_post' and p.formato <> 'nenhum'
    union all
    select 'aprovacao', 'aprovacao:' || p.id,
           jsonb_build_object('n', p.id, 'data', to_char(p.data, 'YYYY-MM-DD'), 'hora', to_char(p.hora, 'HH24:MI'), 'formato', p.formato),
           least(p.atualizado_em, p_agora)
      from public.radar_pauta_pecas p
     where p.situacao = 'pronta' and p.data >= v_aprov and p.tipo <> 'sem_post' and p.formato <> 'nenhum'
    union all
    select 'video', 'video:' || v.id || ':' || v.rodada || ':' || v.situacao,
           jsonb_build_object('n', p.id, 'data', to_char(p.data, 'YYYY-MM-DD'), 'formato', p.formato, 'situacao', v.situacao), p_agora
      from public.radar_videos v join public.radar_pauta_pecas p on p.id = v.peca_id
     where v.situacao in ('pronto','regravar','erro') and p.data >= v_hoje and p.situacao <> 'cancelada'
       and p.tipo <> 'sem_post' and p.formato <> 'nenhum'
       and not (p.situacao = 'aprovada' and p.video_id is not distinct from v.id)
    union all
    select 'noticia', 'site:' || e.id || ':erro',
           jsonb_build_object('n', e.id, 'canal', 'site', 'situacao', 'erro', 'desde', e.autorizado_em), p_agora
      from public.radar_site_envios e join public.radar_conteudos c on c.id = e.conteudo_id
     where e.situacao = 'erro' and e.atualizado_em >= p_agora - interval '7 days'
       and c.status = 'aprovado' and not c.fora_do_site
       and not exists (select 1 from public.radar_site_envios o where o.conteudo_id = e.conteudo_id and o.id > e.id)
       and not exists (select 1 from public.radar_divulgacoes d where d.conteudo_id = e.conteudo_id)
    union all
    select 'noticia', 'site:' || e.id || ':parada',
           jsonb_build_object('n', e.id, 'canal', 'site', 'situacao', 'parada', 'desde', e.autorizado_em), p_agora
      from public.radar_site_envios e
     where e.situacao in ('autorizado','enviando') and e.autorizado_em <= p_agora - v_parada
    union all
    select 'noticia', 'redes:' || e.id || ':' || case when e.situacao = 'erro' then 'erro' else 'parada' end,
           jsonb_build_object('n', e.id, 'canal', e.canal, 'situacao', case when e.situacao = 'erro' then 'erro' else 'parada' end,
                              'desde', e.autorizado_em), p_agora
      from public.radar_redes_envios e
     where e.conteudo_id is not null
       and ((e.situacao = 'erro' and e.atualizado_em >= p_agora - interval '7 days')
            -- parada: autorizada (desde quando ficou autorizada, também a que esperava o site) ou "enviando" (desde o início do envio)
            or (e.situacao in ('autorizado','enviando')
                and coalesce(case when e.situacao = 'enviando' then e.enviado_em end, e.atualizado_em) <= p_agora - v_parada))
  ),
  novas as (
    insert into public.radar_lembretes (tipo, chave, ref, aberto_em)
    select a.tipo, a.chave, a.ref, a.aberto_em from atuais a
    on conflict (tipo, chave) where resolvido_em is null do nothing
    returning 1
  ),
  refs as (
    update public.radar_lembretes l set ref = a.ref
      from atuais a
     where l.tipo = a.tipo and l.chave = a.chave and l.resolvido_em is null and l.avisado_em is null and l.lote is null
       and l.ref is distinct from a.ref
    returning 1
  ),
  fim as (
    update public.radar_lembretes l set resolvido_em = p_agora
     where l.resolvido_em is null and not exists (select 1 from atuais a where a.tipo = l.tipo and a.chave = l.chave)
    returning 1
  )
  select (select count(*) from novas) + (select count(*) from refs) + (select count(*) from fim) into v_n;
  delete from public.radar_lembretes where resolvido_em < p_agora - interval '90 days';
end $$;

-- Os tipos que podem mandar lembrete agora (depois de observar): ligados em Configurações → Lembretes por e-mail, no horário de Brasília
-- (a Pauta a partir da "hora", até o fim do dia; os outros entre "de" e "ate"), sem e-mail do tipo HOJE e com pendência nova e madura.
-- "ligado": false = nada é observado nem devolvido. Só o dono executa.
create or replace function public.radar_lembretes_devidos(p_agora timestamptz) returns text[]
language plpgsql security definer set search_path = public as $$
declare
  v_cfg  jsonb := public.radar_lembretes_cfg();
  v_hoje date := (p_agora at time zone 'America/Sao_Paulo')::date;
  v_hm   time := to_char(p_agora at time zone 'America/Sao_Paulo', 'HH24:MI')::time;
  v      text[] := '{}';
  t      text;
begin
  if not (v_cfg->>'ligado')::boolean then
    return v;
  end if;
  perform public.radar_lembretes_observar(p_agora);
  foreach t in array array['pauta','aprovacao','video','noticia'] loop
    continue when not (v_cfg->>t)::boolean;
    continue when case when t = 'pauta' then v_hm < (v_cfg->>'hora')::time
                       else v_hm < (v_cfg->>'de')::time or v_hm > (v_cfg->>'ate')::time end;
    -- no máximo um e-mail por tipo por dia (de Brasília)
    continue when exists (select 1 from public.radar_lembretes l
                           where l.tipo = t and l.avisado_em is not null and (l.avisado_em at time zone 'America/Sao_Paulo')::date = v_hoje);
    if exists (select 1 from public.radar_lembretes l
                where l.tipo = t and l.resolvido_em is null and l.avisado_em is null
                  and public.radar_lembretes_madura(l.tipo, l.aberto_em, v_cfg, p_agora)) then
      v := v || t;
    end if;
  end loop;
  return v;
end $$;

-- A agenda do banco (pg_cron, de 15 em 15 minutos: sql/radar-redes-agenda.sql) chama antes de pedir o robô ao GitHub. true = pedir.
-- Há tipo devido e alguma das pendências dele ainda não foi pedida, ou foi pedida há 30 minutos ou mais (o token falhou, o GitHub não
-- rodou): no máximo um pedido a cada 30 minutos por pendência. Nada a lembrar = nenhum pedido. Só o dono executa.
create or replace function public.radar_lembretes_acionar() returns boolean
language plpgsql security definer set search_path = public as $$
declare
  v_cfg   jsonb := public.radar_lembretes_cfg();
  v_tipos text[] := public.radar_lembretes_devidos(now());
begin
  if cardinality(v_tipos) = 0 then
    return false;
  end if;
  update public.radar_lembretes l set acionado_em = now()
   where l.tipo = any(v_tipos) and l.resolvido_em is null and l.avisado_em is null
     and public.radar_lembretes_madura(l.tipo, l.aberto_em, v_cfg, now())
     and (l.acionado_em is null or l.acionado_em <= now() - interval '30 minutes');
  return found;
end $$;

-- O workflow dos lembretes, antes de instalar o robô (a rodada de hora em hora, de reserva): há lembrete para mandar agora?
create or replace function public.radar_lembretes_ha_envio() returns boolean
language sql security definer set search_path = public as $$
  select cardinality(public.radar_lembretes_devidos(now())) > 0
$$;

-- O que o robô dos lembretes manda agora: para cada tipo devido, até 30 pendências maduras, reservadas num lote (o mesmo lote que o
-- robô reservou e não confirmou volta, com "retomado": true — se o comentário já saiu, o robô só confirma). Cada item leva só número,
-- data, hora, formato, situação, quando ("amanha" ou "hoje", na Pauta), canal e desde quando: nunca nome, assunto, legenda ou erro.
-- [{tipo, lote, retomado, horas, itens: [{id, n, data, hora, formato, situacao, quando, canal, desde}]}]. Só o dono executa (os testes
-- passam a hora); o robô chama radar_lembretes_lote().
create or replace function public.radar_lembretes_lote_em(p_agora timestamptz) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_cfg   jsonb := public.radar_lembretes_cfg();
  v_hoje  date := (p_agora at time zone 'America/Sao_Paulo')::date;
  v_tipos text[] := public.radar_lembretes_devidos(p_agora);
  v_r     jsonb := '[]';
  v_itens jsonb;
  v_lote  uuid;
  v_ret   boolean;
  t       text;
begin
  foreach t in array v_tipos loop
    select l.lote into v_lote from public.radar_lembretes l
     where l.tipo = t and l.lote is not null and l.resolvido_em is null and l.avisado_em is null
     order by l.id limit 1;
    v_ret := v_lote is not null;
    v_lote := coalesce(v_lote, gen_random_uuid());
    update public.radar_lembretes l set lote = v_lote
     where l.id in (select x.id from public.radar_lembretes x
                     where x.tipo = t and x.lote is null and x.resolvido_em is null and x.avisado_em is null
                       and public.radar_lembretes_madura(x.tipo, x.aberto_em, v_cfg, p_agora)
                     order by x.aberto_em, x.id
                     limit greatest(30 - (select count(*) from public.radar_lembretes y
                                           where y.lote = v_lote and y.resolvido_em is null and y.avisado_em is null), 0));
    select jsonb_agg(jsonb_build_object(
             'id', l.id, 'n', l.ref->'n', 'data', l.ref->'data', 'hora', l.ref->'hora', 'formato', l.ref->'formato',
             'situacao', l.ref->'situacao', 'canal', l.ref->'canal',
             'quando', case when t = 'pauta' then case when (l.ref->>'data')::date > v_hoje then 'amanha' else 'hoje' end end,
             'desde', case when t = 'aprovacao' then to_jsonb(l.aberto_em) else l.ref->'desde' end)
           order by case when t = 'pauta' then l.ref->>'data' end desc nulls last,          -- a de amanhã antes da de hoje
                    case when t in ('aprovacao','video') then l.ref->>'data' end,
                    case when t = 'noticia' then (l.ref->>'desde')::timestamptz end, l.id)
      into v_itens
      from public.radar_lembretes l
     where l.lote = v_lote and l.resolvido_em is null and l.avisado_em is null;
    continue when v_itens is null;
    v_r := v_r || jsonb_build_array(jsonb_build_object('tipo', t, 'lote', v_lote, 'retomado', v_ret,
             'horas', case t when 'aprovacao' then v_cfg->'aprovacao_horas' when 'noticia' then v_cfg->'parada_horas' end,
             'itens', v_itens));
  end loop;
  return v_r;
end $$;

-- O robô dos lembretes (chave interna, pelo PostgREST): o lote de agora.
create or replace function public.radar_lembretes_lote() returns jsonb
language sql security definer set search_path = public as $$
  select public.radar_lembretes_lote_em(now())
$$;

-- O e-mail saiu (o aviso p_aviso foi aberto ou comentado): as pendências p_ids do lote nunca mais são lembradas. O resto do lote (o que
-- não entrou no comentário) é liberado e fica para o próximo dia. Devolve quantas foram marcadas. Só o dono executa (os testes passam a
-- hora); o robô chama radar_lembretes_enviado().
create or replace function public.radar_lembretes_enviado_em(p_lote uuid, p_aviso int, p_ids bigint[], p_agora timestamptz) returns int
language plpgsql security definer set search_path = public as $$
declare
  v_n int;
begin
  if p_lote is null or p_aviso is null or p_aviso <= 0 then
    raise exception 'RADAR340: informe o lote e o número do aviso do lembrete' using errcode = 'P0001';
  end if;
  update public.radar_lembretes set avisado_em = p_agora, aviso = p_aviso, lote = null
   where lote = p_lote and id = any(coalesce(p_ids, '{}')) and avisado_em is null;
  get diagnostics v_n = row_count;
  update public.radar_lembretes set lote = null where lote = p_lote and avisado_em is null;
  return v_n;
end $$;

create or replace function public.radar_lembretes_enviado(p_lote uuid, p_aviso int, p_ids bigint[]) returns int
language sql security definer set search_path = public as $$
  select public.radar_lembretes_enviado_em(p_lote, p_aviso, p_ids, now())
$$;

-- Configurações → Lembretes por e-mail: a situação, só para o administrador (os outros recebem {}). A agenda do banco (o agendamento
-- radar-redes-agenda-lembretes do sql/radar-redes-agenda.sql) instalada e a última rodada dela; por tipo, o último lembrete (quando e o
-- número do aviso); e quantas pendências esperam o próximo lembrete. O pg_cron só aparece dentro de "execute": sem ele (ou com qualquer
-- erro), "instalada": false.
create or replace function public.radar_lembretes_situacao() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  v_ativa  boolean;
  v_ult    timestamptz;
  v_status text;
  v_agenda jsonb;
  v_tipos  jsonb := '{}';
  t        text;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    return '{}'::jsonb;
  end if;
  begin
    execute 'select j.active from cron.job j where j.jobname = ''radar-redes-agenda-lembretes'' limit 1' into v_ativa;
    if v_ativa is null then
      v_agenda := jsonb_build_object('instalada', false);
    else
      execute 'select coalesce(d.end_time, d.start_time), d.status from cron.job_run_details d join cron.job j on j.jobid = d.jobid
                where j.jobname = ''radar-redes-agenda-lembretes'' order by d.start_time desc nulls last limit 1' into v_ult, v_status;
      v_agenda := jsonb_build_object('instalada', true, 'ativa', v_ativa, 'ultima_execucao', v_ult, 'ultimo_status', v_status);
    end if;
  exception when others then
    v_agenda := jsonb_build_object('instalada', false);
  end;
  foreach t in array array['pauta','aprovacao','video','noticia'] loop
    v_tipos := v_tipos || jsonb_build_object(t, (select jsonb_build_object('em', l.avisado_em, 'aviso', l.aviso) from public.radar_lembretes l
                                                  where l.tipo = t and l.avisado_em is not null order by l.avisado_em desc, l.id desc limit 1));
  end loop;
  return jsonb_build_object('agenda', v_agenda, 'tipos', v_tipos,
                            'esperando', (select count(*) from public.radar_lembretes l where l.resolvido_em is null and l.avisado_em is null));
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

drop trigger if exists radar_tg_assunto_liberacao on public.radar_assuntos;
create trigger radar_tg_assunto_liberacao before insert or update on public.radar_assuntos
  for each row execute function public.radar_fn_assunto_liberacao();

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
drop trigger if exists radar_tg_captura_base_legal on public.radar_capturas;
create trigger radar_tg_captura_base_legal before insert or update on public.radar_capturas
  for each row execute function public.radar_fn_captura_base_legal();
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

-- v0.17.0: o site não saiu → as redes que iam junto ("Publicar em todos") caem também
drop trigger if exists radar_tg_site_envio_redes on public.radar_site_envios;
create trigger radar_tg_site_envio_redes after update of situacao on public.radar_site_envios
  for each row execute function public.radar_fn_site_envio_redes();

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

-- v0.21.0: Pauta. Gravar só a sugestão da IA não muda a versão da peça (radar_fn_atualizado_em); as transições e o que só as
-- funções mudam ficam em radar_fn_pauta_peca; pessoa numa peça não se apaga. Nenhum gatilho novo em radar_redes_envios.
drop trigger if exists radar_tg_pauta_atualizado on public.radar_pauta_pecas;
create trigger radar_tg_pauta_atualizado before update on public.radar_pauta_pecas
  for each row execute function public.radar_fn_atualizado_em();
drop trigger if exists radar_tg_pauta_peca on public.radar_pauta_pecas;
create trigger radar_tg_pauta_peca before insert or update on public.radar_pauta_pecas
  for each row execute function public.radar_fn_pauta_peca();
drop trigger if exists radar_tg_pessoa_atualizado on public.radar_pessoas;
create trigger radar_tg_pessoa_atualizado before update on public.radar_pessoas
  for each row execute function public.radar_fn_atualizado_em();
drop trigger if exists radar_tg_pessoa_apagar on public.radar_pessoas;
create trigger radar_tg_pessoa_apagar before delete on public.radar_pessoas
  for each row execute function public.radar_fn_pessoa_apagar();
-- v0.22.0: o vídeo do reel (as transições ficam nas funções radar_video_*: ninguém grava direto)
drop trigger if exists radar_tg_video_atualizado on public.radar_videos;
create trigger radar_tg_video_atualizado before update on public.radar_videos
  for each row execute function public.radar_fn_atualizado_em();

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
                           'radar_informativos','radar_config','radar_divulgacoes','radar_site_envios','radar_redes_envios',
                           'radar_site_exclusoes','radar_pessoas','radar_pauta_pecas','radar_videos'] loop
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
       o.id as origem_assunto_id, o.titulo || ' (' || o.status || ')' as origem_assunto,
       c.base_legal,                                   -- v0.15.0: normas citadas no texto capturado
       -- v0.15.0: a captura que não cita norma mostra a de outra captura do mesmo fato que ainda está na fila e cita
       -- (a origem, as repetições dela ou as irmãs)
       (select r.base_legal from public.radar_capturas r
         where r.id <> c.id
           and (r.duplicata_de = c.id or r.id = c.duplicata_de or (c.duplicata_de is not null and r.duplicata_de = c.duplicata_de))
           and coalesce((r.base_legal->>'total')::int, 0) > 0
           and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = r.id)
         order by (r.id = c.duplicata_de) desc, r.id limit 1) as base_legal_repeticao
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
-- colunas listadas (não a.*): coluna nova em radar_assuntos (ex.: a liberação da v0.12.0) não muda esta lista
select a.id, a.titulo, a.categoria, a.subcategoria, a.abrangencia, a.relevancia, a.situacao_confirmacao, a.status,
       a.resumo, a.publico_afetado, a.responsavel, a.criado_em, a.atualizado_em,
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
       (select count(*) from public.radar_conteudos c where c.status = 'rascunho' and c.modelo_ia like '%(robô)') as rascunhos_robo,
       -- v0.21.0: publicações da Pauta que não saíram: com erro, paradas em "enviando" há mais de 15 min, ou com a hora passada há
       -- mais de 20 min sem sair (a agenda do banco roda de 5 em 5 minutos: parou ou está desligada)
       (select count(*) from public.radar_redes_envios e where e.peca_id is not null
          and (e.situacao = 'erro'
               or (e.situacao = 'enviando'   and e.enviado_em    < now() - interval '15 minutes')
               or (e.situacao = 'autorizado' and e.agendado_para < now() - interval '20 minutes'))) as pauta_falhas,
       -- v0.22.0 (rodada 2 da varredura geral): a última rodada do robô de coleta (GitHub, de 6 em 6 horas) e se ela passou de 12 horas
       -- com fonte ativa que o robô coleta (a do e-mail não passa por ele). No repositório público, o GitHub desliga sozinho os robôs
       -- agendados depois de 60 dias sem atividade: a coleta, o robô do site, os avisos e o resumo param juntos, sem e-mail
       (select max(x.iniciado_em) from public.radar_execucoes x) as ultima_coleta,
       (exists (select 1 from public.radar_fontes f where f.ativo and coalesce(f.config->>'origem', '') <> 'email')
        and coalesce((select max(x.iniciado_em) from public.radar_execucoes x), '-infinity') < now() - interval '12 hours') as coleta_atrasada;

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
       (a.liberado_sem_base_em is null and (a.situacao_confirmacao <> 'confirmado_oficialmente' or not exists (
          select 1 from public.radar_evidencias e
          join public.radar_capturas k on k.id = e.captura_id
          join public.radar_fontes   f on f.id = k.fonte_id
          where e.assunto_id = c.assunto_id and e.trecho_conferido and f.oficial))) as base_caiu
from public.radar_divulgacoes d
join public.radar_conteudos c on c.id = d.conteudo_id
join public.radar_assuntos  a on a.id = c.assunto_id;

-- v0.21.0: as pessoas de cada peça da Pauta, com o selo do termo de uso de imagem em cada canal (NULL = vale; senão o motivo),
-- no dia da peça (v0.28.0: e se os termos estão dispensados, de sócio(a) da Artecon). Roda como quem lê: o leitor não lê radar_pessoas e não vê nenhuma linha.
drop view if exists public.radar_v_pauta_pessoas;
create view public.radar_v_pauta_pessoas
with (security_invoker = true) as
select p.id as peca_id, p.data, pe.id as pessoa_id, pe.nome_na_peca,
       public.radar_pauta_termo_ok(pe.id, p.tipo, 'instagram', p.data) as motivo_instagram,
       public.radar_pauta_termo_ok(pe.id, p.tipo, 'facebook',  p.data) as motivo_facebook,
       -- v0.28.0: sócio(a) da Artecon, maior de idade: os termos não são exigidos (a tela mostra o selo "Sócio(a) — termos dispensados")
       pe.socio and not pe.menor as termos_dispensados
from public.radar_pauta_pecas p
cross join lateral unnest(p.pessoas) as u(pessoa_id)
join public.radar_pessoas pe on pe.id = u.pessoa_id;

-- v0.21.0: a capa de cada conteúdo, para o robô que publica no site (robo/radar_site_publicar.py). A chave do robô não lê
-- radar_imagens: lá ficam também as fotos da equipe e as lâminas da Pauta. Roda como o dono da vista: só o service_role a lê.
drop view if exists public.radar_v_capas;
create view public.radar_v_capas with (security_barrier = true) as
select i.id, i.dados from public.radar_imagens i
where exists (select 1 from public.radar_conteudos c where c.imagem_id = i.id);

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
      'radar_informativos','radar_informativo_itens','radar_divulgacoes','radar_site_envios','radar_itc_lidos',
      'radar_redes_envios','radar_site_exclusoes','radar_pessoas','radar_pauta_pecas','radar_videos','radar_video_acessos'] loop
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
revoke insert, update, delete on public.radar_itc_lidos from authenticated;   -- v0.12.0: só a função radar-itc grava
revoke insert, update, delete on public.radar_redes_envios from authenticated; -- v0.13.0: só pelas funções de autorização
-- v0.17.0: pedidos de exclusão no site: a equipe só lê; quem grava são as funções do administrador e o robô (só o andamento)
revoke insert, update, delete on public.radar_site_exclusoes from authenticated;
grant update on public.radar_site_exclusoes to service_role;
-- v0.21.0: o robô e a função radar-redes não leem a Pauta nem as pessoas (radar_pauta_iniciar é security definer; a radar-ia lê
-- com o token de quem pediu; o robô de avisos lê só radar_redes_envios)
revoke select on public.radar_pessoas, public.radar_pauta_pecas from service_role;
-- v0.21.0: nem onde ficam as fotos, as lâminas, as legendas e o nome na peça (a chave do robô é segredo do GitHub Actions de um
-- repositório público): radar_imagens (a capa do conteúdo vem por radar_v_capas), a auditoria (que guarda as legendas) e, nos
-- envios, a legenda, a imagem e o texto do erro (que pode citar um nome). O robô e a radar-redes leem do envio só o andamento;
-- a legenda e a imagem chegam à radar-redes por radar_rede_iniciar e radar_pauta_iniciar (security definer).
revoke select on public.radar_imagens, public.radar_auditoria, public.radar_redes_envios from service_role;
grant select (id, conteudo_id, peca_id, canal, situacao, junto_com_site, conteudo_lido_em, autorizado_em, cancelado_em, enviado_em,
              publicado_em, post_id, url, imagem_url, atualizado_em, excluido_em, excluido_como, agendado_para, disparos, disparado_em)
  on public.radar_redes_envios to service_role;
revoke all on public.radar_v_capas from public, anon, authenticated, service_role;
grant select on public.radar_v_capas to service_role;
-- v0.21.0: a cópia da lâmina no envio (imagem) também ninguém da equipe lê pela API (a tela não usa; o leitor, que não vê as fotos nem
-- as lâminas da Pauta, também não a leria por aqui): a imagem chega à radar-redes só pelas funções de início, security definer
revoke select on public.radar_redes_envios from authenticated;
grant select (id, conteudo_id, peca_id, canal, legenda, conteudo_lido_em, situacao, autorizado_por, autorizado_em, cancelado_por, cancelado_em,
              enviado_em, publicado_em, post_id, url, imagem_url, erro, atualizado_em, junto_com_site, excluido_em, excluido_por, excluido_como,
              agendado_para, disparos, disparado_em)
  on public.radar_redes_envios to authenticated;
-- v0.21.0: as pessoas da peça com o selo do termo: só a equipe logada (o leitor não vê linha nenhuma, pela regra de radar_pessoas)
revoke all on public.radar_v_pauta_pessoas from public, anon, authenticated, service_role;
grant select on public.radar_v_pauta_pessoas to authenticated;
-- v0.22.0: o vídeo do reel e quem viu ou baixou. A equipe (administrador e editor, pela regra) só lê; grava só pelas funções. O papel
-- interno (a chave do robô do repositório público e as funções) não lê nem grava ESTAS TABELAS: a radar-video chega ao vídeo só pelas
-- funções radar_video_* (security definer), como a Pauta da v0.21.0. (Os ARQUIVOS do armazenamento não estão aqui: a chave service_role
-- lê todos os buckets privados, radar-videos e radar-pauta inclusive — varredura geral: por isso os pacotes dos robôs públicos vão
-- com versão exata e hash, robo/requirements.txt.)
revoke insert, update, delete on public.radar_videos, public.radar_video_acessos from authenticated;
revoke select, insert, update, delete on public.radar_videos, public.radar_video_acessos from service_role;
-- v0.29.0: os lembretes. Só as funções radar_lembretes_* gravam; o administrador lê (pela regra abaixo). A chave do robô (service_role,
-- segredo de um repositório público) não lê a tabela: o robô dos lembretes chega aqui só pelas funções do lote (radar_lembretes_lote e
-- radar_lembretes_enviado), que devolvem só número, data, hora, formato, situação e canal.
alter table public.radar_lembretes enable row level security;
revoke all on public.radar_lembretes from public, anon, authenticated, service_role;
grant select on public.radar_lembretes to authenticated;

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
grant execute on function public.radar_separar_repeticao(bigint) to authenticated;                 -- v0.16.0
grant execute on function public.radar_autorizar_copia(bigint, text, timestamptz) to authenticated; -- v0.16.0
-- v0.24.0: a Conferência das Diretrizes (as funções conferem quem pode: editor ou administrador grava a lista; só o administrador assume);
-- a versão do texto é coluna calculada na leitura da tela
grant execute on function public.radar_registrar_conferencia(bigint, timestamptz, jsonb, text) to authenticated;
grant execute on function public.radar_assumir_conferencia(bigint, text, timestamptz) to authenticated;
grant execute on function public.radar_conferencia_versao(public.radar_conteudos) to authenticated;
-- v0.24.0 (etapa 5): a revisão editorial (a função confere o papel); a versão do texto é coluna calculada na leitura da tela
grant execute on function public.radar_registrar_revisao_editorial(bigint, timestamptz, jsonb) to authenticated;
grant execute on function public.radar_texto_versao(public.radar_conteudos) to authenticated;
grant execute on function public.radar_admin_usuarios() to authenticated;
grant execute on function public.radar_registrar_uso_ia(text, text, int, int, bigint) to authenticated;
grant execute on function public.radar_registrar_evidencia_ia(bigint, bigint, text, text) to authenticated;
grant execute on function public.radar_incluir_texto_oficial(bigint, bigint, text, text, date, text) to authenticated;
-- v0.10.0: autorização de publicação no site (a função confere que é o administrador)
grant execute on function public.radar_autorizar_site(bigint, text, timestamptz) to authenticated;
grant execute on function public.radar_cancelar_site(bigint) to authenticated;
-- o robô confere de novo as exigências do assunto logo antes de enviar ao site
grant execute on function public.radar_pendencia_assunto(bigint) to service_role;
grant execute on function public.radar_liberar_sem_fundamentacao(bigint, text) to authenticated;   -- a função confere que é o administrador
grant execute on function public.radar_converter_analise(bigint) to authenticated;                 -- idem (v0.12.1)
-- v0.12.0: a função radar-itc grava o boletim pelo papel do robô
grant execute on function public.radar_receber_email(text, jsonb) to service_role;
grant execute on function public.radar_itc_ja_lidos(text[]) to service_role;
grant execute on function public.radar_itc_marcar_lido(text, text, timestamptz, int, int) to service_role;
grant execute on function public.radar_itc_conferir_agenda(text) to service_role;
grant execute on function public.radar_itc_registrar_falha(text) to service_role;
-- v0.13.0: Instagram e Facebook — o administrador autoriza (as funções conferem); a função radar-redes envia
grant execute on function public.radar_autorizar_rede(bigint, text, text, text, timestamptz, boolean) to authenticated;   -- v0.22.0: + a caixa
grant execute on function public.radar_dispensar_rede(bigint, text) to authenticated;
grant execute on function public.radar_cancelar_rede(bigint) to authenticated;
grant execute on function public.radar_rede_iniciar(bigint) to service_role;
grant execute on function public.radar_rede_concluir(bigint, boolean, text, text, text, text) to service_role;
-- v0.17.0: "Publicar em todos" e exclusão (as funções conferem que é o administrador); o robô conclui a exclusão no site
grant execute on function public.radar_autorizar_todos(bigint, text, timestamptz, text, text, text, boolean) to authenticated;   -- v0.22.0: + a caixa
grant execute on function public.radar_rede_marcar_excluida(bigint, text) to authenticated;
grant execute on function public.radar_pedir_exclusao_site(bigint) to authenticated;
grant execute on function public.radar_cancelar_exclusao_site(bigint) to authenticated;
grant execute on function public.radar_site_exclusao_concluir(bigint, boolean, text) to service_role;
-- v0.21.0: Pauta — a tela chama (cada função confere o papel); a função radar-redes inicia o envio da peça e confere a chave da
-- agenda do banco. As auxiliares (radar_pauta_problemas, radar_pauta_pode_sair, radar_agenda_vencidas…) ficam só com o dono.
grant execute on function public.radar_pauta_importar(jsonb) to authenticated;
grant execute on function public.radar_pauta_criar(jsonb) to authenticated;          -- v0.28.0 (a função confere que é o administrador)
grant execute on function public.radar_pauta_conferir(bigint, text[]) to authenticated;
grant execute on function public.radar_pauta_marcar_pronta(bigint, timestamptz) to authenticated;
grant execute on function public.radar_pauta_aprovar(bigint, timestamptz, text[], text, bigint[], text, text[], text) to authenticated;   -- v0.22.0: + o vídeo
grant execute on function public.radar_pauta_desaprovar(bigint, boolean) to authenticated;
grant execute on function public.radar_pauta_publicar_agora(bigint, boolean) to authenticated;
grant execute on function public.radar_pauta_pode_copiar(bigint, timestamptz, text) to authenticated;
grant execute on function public.radar_pauta_registrar_manual(bigint, text, text, date) to authenticated;
grant execute on function public.radar_pauta_termo_ok(bigint, text, text, date) to authenticated;
grant execute on function public.radar_pauta_copia_paga_ia(text[]) to authenticated;
-- rodada 2 da varredura geral: onde, no texto da notícia, está a frase do boletim que o banco recusaria (a tela e o Revisar com IA)
grant execute on function public.radar_copia_paga_trechos(bigint, text[]) to authenticated;
grant execute on function public.radar_agenda_situacao() to authenticated;
grant execute on function public.radar_pauta_iniciar(bigint) to service_role;
grant execute on function public.radar_redes_conferir_agenda(text) to service_role;
-- v0.22.0: corretor de vídeo. A tela chama as funções do vídeo (cada uma confere o papel); a função radar-video chama as do robô, da
-- agenda e da limpeza pelo papel interno. As auxiliares (radar_video_pendencia, _pessoa_falta, _pessoas_falta, _cartela_falta,
-- _travar…) e a reserva da agenda (radar_video_reserva, que o pg_cron roda como dono) ficam só com o dono.
grant execute on function public.radar_video_criar(bigint, jsonb, bigint, text, text[], boolean, text[], numeric) to authenticated;
grant execute on function public.radar_video_cota() to authenticated;
grant execute on function public.radar_video_para_envio(uuid) to authenticated;
grant execute on function public.radar_video_enviado(uuid) to authenticated;
grant execute on function public.radar_video_ajustar(uuid, jsonb, text[]) to authenticated;
grant execute on function public.radar_video_reconferir(uuid, text) to authenticated;
grant execute on function public.radar_video_de_novo(uuid, text[]) to authenticated;
grant execute on function public.radar_video_descartar(uuid) to authenticated;
grant execute on function public.radar_video_apaguei(uuid) to authenticated;
grant execute on function public.radar_video_apaguei_baixado(uuid) to authenticated;
grant execute on function public.radar_video_para_previa(uuid) to authenticated;
grant execute on function public.radar_video_para_baixar(bigint, timestamptz) to authenticated;
grant execute on function public.radar_video_resumo() to authenticated;
grant execute on function public.radar_pauta_pecas_da_pessoa(bigint) to authenticated;
grant execute on function public.radar_video_conferir_robo(text) to service_role;
grant execute on function public.radar_video_conferir_agenda(text) to service_role;
grant execute on function public.radar_video_ha_fila(int) to service_role;
grant execute on function public.radar_video_pegar() to service_role;
grant execute on function public.radar_video_em_curso(uuid, int) to service_role;
grant execute on function public.radar_video_registrar_audio(uuid, int, numeric, boolean) to service_role;
grant execute on function public.radar_video_parcial(uuid, int, jsonb) to service_role;
grant execute on function public.radar_video_concluir(uuid, int, text, jsonb, text, bigint, numeric) to service_role;
grant execute on function public.radar_video_falhar(uuid, int, text) to service_role;
grant execute on function public.radar_video_limpeza() to service_role;
grant execute on function public.radar_video_limpo(uuid, text[]) to service_role;
-- v0.29.0: os lembretes. O robô dos lembretes (workflow radar-lembretes.yml) pergunta se há o que mandar, pega o lote e confirma o
-- e-mail; a tela (Configurações, só o administrador: a função confere) lê a situação. O resto (observar, devidos, acionar, a
-- configuração e as versões com a hora dos testes) fica só com o dono: o pg_cron roda radar_lembretes_acionar como dono.
grant execute on function public.radar_lembretes_ha_envio(), public.radar_lembretes_lote(),
                          public.radar_lembretes_enviado(uuid, int, bigint[]) to service_role;
grant execute on function public.radar_lembretes_situacao() to authenticated;
-- v0.20.0: a conferência da chave da radar-concorrentes (sql/radar-concorrentes.sql, v0.19.1, opcional) também perde o acesso no
-- laço acima: se ela existe, o papel interno volta a executá-la (sem isso, toda chamada com a chave do Vault recebe 401)
do $$
begin
  if to_regprocedure('public.radar_concorrentes_conferir(text)') is not null then
    execute 'grant execute on function public.radar_concorrentes_conferir(text) to service_role';
  end if;
end $$;

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
  foreach t in array array['radar_execucoes','radar_capturas','radar_capturas_versoes','radar_site_envios','radar_redes_envios',
                           'radar_site_exclusoes'] loop
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
                           'radar_imagens','radar_informativos','radar_informativo_itens','radar_divulgacoes',
                           'radar_pauta_pecas'] loop          -- v0.21.0: as transições da peça ficam no gatilho radar_fn_pauta_peca
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
-- v0.21.0: as fotos e as lâminas das peças da Pauta (a equipe, com o nome e o registro) só o editor e o administrador leem, como as
-- pessoas; o leitor lê as outras imagens (as capas dos conteúdos).
-- v0.22.0 (varredura geral): a regra se inverte para o leitor: ele lê só a imagem ligada a um conteúdo (a capa ou a ilustração, o que
-- a tela e o informativo mostram). Antes ele lia toda imagem que não estivesse numa peça NAQUELE momento — a foto tirada da peça, as
-- lâminas de uma aprovação recusada ou desfeita ficavam legíveis até a faxina do robô (24 horas depois, na coleta seguinte)
drop policy if exists radar_imagens_sel on public.radar_imagens;
create policy radar_imagens_sel on public.radar_imagens for select to authenticated
  using ((select public.radar_papel()) in ('admin','editor')
         or ((select public.radar_papel()) is not null
             and exists (select 1 from public.radar_conteudos c where c.imagem_id = radar_imagens.id or c.ilustracao_id = radar_imagens.id)
             and not exists (select 1 from public.radar_pauta_pecas p where radar_imagens.id = any(p.fotos) or radar_imagens.id = any(p.artes))));

-- configurações: a equipe lê; o administrador altera
drop policy if exists radar_config_sel on public.radar_config;
create policy radar_config_sel on public.radar_config for select to authenticated
  using ((select public.radar_papel()) is not null);
drop policy if exists radar_config_adm on public.radar_config;
create policy radar_config_adm on public.radar_config for all to authenticated
  using ((select public.radar_papel()) = 'admin') with check ((select public.radar_papel()) = 'admin');

-- v0.21.0: pessoas e termos de uso de imagem: o administrador e o editor leem; só o administrador grava
drop policy if exists radar_pessoas_sel on public.radar_pessoas;
create policy radar_pessoas_sel on public.radar_pessoas for select to authenticated
  using ((select public.radar_papel()) in ('admin','editor'));
drop policy if exists radar_pessoas_adm on public.radar_pessoas;
create policy radar_pessoas_adm on public.radar_pessoas for all to authenticated
  using ((select public.radar_papel()) = 'admin') with check ((select public.radar_papel()) = 'admin');

-- v0.22.0: o vídeo do reel (com a fala e o relatório): o administrador e o editor leem; quem viu ou baixou, só o administrador
drop policy if exists radar_videos_sel on public.radar_videos;
create policy radar_videos_sel on public.radar_videos for select to authenticated
  using ((select public.radar_papel()) in ('admin','editor'));
drop policy if exists radar_video_acessos_sel on public.radar_video_acessos;
create policy radar_video_acessos_sel on public.radar_video_acessos for select to authenticated
  using ((select public.radar_papel()) = 'admin');

-- v0.29.0: os lembretes (só número, data, situação e canal; nada de nome): só o administrador lê
drop policy if exists radar_lembretes_sel on public.radar_lembretes;
create policy radar_lembretes_sel on public.radar_lembretes for select to authenticated
  using ((select public.radar_papel()) = 'admin');

-- uso da IA: a equipe lê; a gravação é só pela função radar_registrar_uso_ia
drop policy if exists radar_ia_uso_sel on public.radar_ia_uso;
create policy radar_ia_uso_sel on public.radar_ia_uso for select to authenticated
  using ((select public.radar_papel()) is not null);
drop policy if exists radar_ia_uso_ins on public.radar_ia_uso;

-- auditoria e instalações: só admin lê; ninguém grava pela API
drop policy if exists radar_auditoria_sel on public.radar_auditoria;
create policy radar_auditoria_sel on public.radar_auditoria for select to authenticated
  using ((select public.radar_papel()) = 'admin');
drop policy if exists radar_itc_lidos_sel on public.radar_itc_lidos;
create policy radar_itc_lidos_sel on public.radar_itc_lidos for select to authenticated
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
-- v0.20.0: "assinatura" leva também "cnpj" e "crc" (identificação legal na arte e na legenda das redes; vazios, a tela
-- avisa e não inventa). Na instalação que já existe, o administrador acrescenta os dois em Configurações.
-- v0.21.0: "pauta" (agenda automática ligada, hora que entra na importação do calendário, janela em horas depois da hora marcada
-- e hashtags fixas); em "obrigacoes", o item com "redes": false fica fora da agenda da semana publicada nas redes.
-- v0.22.0: "corretor_video" (o glossário e as variantes que a transcrição erra, a duração máxima do reel, as pausas, o volume, a
-- cartela e o texto extra dela, o limite de minutos de transcrição do mês e os prazos de guarda). Na instalação que já existe, a
-- chave entra com os padrões (o insert abaixo não sobrescreve).
-- v0.22.0: o "Simples Doméstico" (DAE) passa a antecipar quando o dia 20 não é dia útil (Lei 8.212/1991, art. 30, V, e § 2º, II;
-- Manual do Empregador Doméstico do eSocial). Na instalação que já existe, o administrador troca o "ajuste" em Configurações.
-- v0.29.0: "lembretes" (os lembretes por e-mail antes do dia: ligados, a Pauta de amanhã a partir das 16:00, os outros das 08:00 às
-- 20:00, a peça pronta depois de 24 horas sem aprovação e a notícia autorizada depois de 3 horas parada). Na instalação que já existe, a
-- chave entra com os padrões (o insert abaixo não sobrescreve a que o administrador já tiver ajustado).
insert into public.radar_config (chave, valor) values
  ('obrigacoes', '[{"nome": "Salário dos Colaboradores (Empregados)", "regra": "quinto_dia_util"}, {"nome": "Salários - Trabalhador Doméstico", "regra": "dia", "dia": 7, "ajuste": "antecipa"}, {"nome": "ICMS", "regra": "dia", "dia": 10, "ajuste": "posterga"}, {"nome": "ICMS Substituição Tributária", "regra": "dia", "dia": 10, "ajuste": "posterga"}, {"nome": "Carnê INSS Individual", "regra": "dia", "dia": 15, "ajuste": "posterga"}, {"nome": "FGTS - Fundo de Garantia Por Tempo de Serviço", "regra": "dia", "dia": 20, "ajuste": "antecipa"}, {"nome": "GPS (Empresa)", "regra": "dia", "dia": 20, "ajuste": "antecipa"}, {"nome": "IRRF (Rendimento Serviço Prestado Cód. 1708)", "regra": "dia", "dia": 20, "ajuste": "antecipa"}, {"nome": "IRRF (Rendimento de Trabalhador Cód. 0561)", "regra": "dia", "dia": 20, "ajuste": "antecipa"}, {"nome": "Simples Doméstico", "regra": "dia", "dia": 20, "ajuste": "antecipa"}, {"nome": "Simples Nacional", "regra": "dia", "dia": 20, "ajuste": "posterga"}, {"nome": "Honorário contábil", "regra": "dia", "dia": 20, "ajuste": "posterga", "redes": false}, {"nome": "PIS", "regra": "dia", "dia": 25, "ajuste": "antecipa"}, {"nome": "COFINS", "regra": "dia", "dia": 25, "ajuste": "antecipa"}, {"nome": "IPI", "regra": "dia", "dia": 25, "ajuste": "antecipa"}, {"nome": "CSLL - Contribuição Social sobre o Lucro Líquido", "regra": "ultimo_dia_util"}, {"nome": "IRPJ - Imposto de Renda Pessoa Jurídica", "regra": "ultimo_dia_util"}, {"nome": "Imposto de Renda Pessoa Física (Cód. 0190)", "regra": "ultimo_dia_util"}, {"nome": "INSS - Parcelamento p/ Ingresso no Simples Nacional", "regra": "ultimo_dia_util"}, {"nome": "Parcelamentos Federais e Parcelamento Especial", "regra": "ultimo_dia_util"}, {"nome": "PERT – Programa Esp. Regularização Tributária", "regra": "ultimo_dia_util"}, {"nome": "Parcelamento Especial - Simples Nacional", "regra": "ultimo_dia_util"}]'::jsonb),
  ('feriados_extras', '[]'::jsonb),
  ('fale_conosco', '{"setores": [{"nome": "Geral", "rotulo": "Atendimento Geral", "telefones": [{"numero": "48-3242-0530", "whatsapp": true}], "emails": ["artecon@artecon.cnt.br"], "equipe": []}, {"nome": "Setor Contábil", "rotulo": "Setor Contábil", "telefones": [], "emails": ["dc@artecon.cnt.br"], "equipe": [], "responsaveis_rotulo": "Contadores Responsáveis", "responsaveis": []}, {"nome": "Setor Fiscal", "rotulo": "Setor Fiscal", "telefones": [], "emails": ["df@artecon.cnt.br"], "equipe": []}, {"nome": "Departamento Pessoal", "rotulo": "Departamento Pessoal", "telefones": [], "emails": ["rh@artecon.cnt.br"], "equipe": []}, {"nome": "Setor Institucional", "rotulo": "Setor Institucional", "telefones": [], "emails": ["societario@artecon.cnt.br"], "equipe": []}], "observacao": ""}'::jsonb),
  ('assinatura', '{"local": "Palhoça, SC", "empresa": "Artecon Artes Contábeis ME", "responsavel": "Cleiver Gonçalves", "cnpj": "", "crc": ""}'::jsonb),
  ('rascunhos', '{"ligado": true, "nota_minima": 9, "por_dia": 2, "dias": 3, "formato": "informativo"}'::jsonb),
  ('pauta', '{"agenda_ligada": true, "hora_padrao": "09:30", "janela_horas": 6, "hashtags": ["#Contabilidade", "#Palhoça"]}'::jsonb),
  ('lembretes', '{"ligado": true, "hora": "16:00", "de": "08:00", "ate": "20:00", "aprovacao_horas": 24, "parada_horas": 3, "pauta": true, "aprovacao": true, "video": true, "noticia": true}'::jsonb),
  ('corretor_video', '{"glossario": ["eSocial", "DCTFWeb", "IBS", "CBS", "Simples Nacional", "MEI", "CNPJ", "DAS", "DARF", "FGTS", "Cofins", "PIS", "PGDAS-D", "Artecon", "Palhoça"], "variantes": {"eSocial": ["e social", "é social"], "DCTFWeb": ["dctf web"], "IBS": ["ips", "ibis"], "CBS": ["cps"], "DARF": ["dar f"], "FGTS": ["fgt s"], "Cofins": ["confins"], "PIS": ["piz"], "CNPJ": ["cnp j"], "PGDAS-D": ["pg das d", "pgdasd"], "Artecon": ["arte com", "artcon"]}, "duracao_max_s": 45, "pausa_max_s": 1.0, "pausa_bloco_s": 0.8, "lufs": -14, "cartela_s": 3, "cartela_extra": "", "limite_min_mes": 30, "retencao_dias": 30, "retencao_publicado_dias": 30}'::jsonb),
  ('relevancia', '{"limite_alta": 8, "limite_media": 3, "termos": [{"termo": "reforma tributária", "pontos": 5}, {"termo": "IBS", "pontos": 5}, {"termo": "CBS", "pontos": 5}, {"termo": "imposto seletivo", "pontos": 5}, {"termo": "Simples Nacional", "pontos": 5}, {"termo": "MEI", "pontos": 5}, {"termo": "microempreendedor", "pontos": 5}, {"termo": "prorroga", "pontos": 5}, {"termo": "prorrogado", "pontos": 5}, {"termo": "prorrogados", "pontos": 5}, {"termo": "prorrogação", "pontos": 5}, {"termo": "prazo", "pontos": 5}, {"termo": "prazos", "pontos": 5}, {"termo": "lei complementar", "pontos": 5}, {"termo": "transação", "pontos": 5}, {"termo": "parcelamento", "pontos": 5}, {"termo": "regularização", "pontos": 5}, {"termo": "Refis", "pontos": 5}, {"termo": "instrução normativa", "pontos": 4}, {"termo": "vencimento", "pontos": 4}, {"termo": "obrigação acessória", "pontos": 4}, {"termo": "DCTF", "pontos": 4}, {"termo": "DCTFWeb", "pontos": 4}, {"termo": "EFD", "pontos": 4}, {"termo": "ECF", "pontos": 4}, {"termo": "ECD", "pontos": 4}, {"termo": "eSocial", "pontos": 4}, {"termo": "Reinf", "pontos": 4}, {"termo": "imposto de renda", "pontos": 4}, {"termo": "IRPF", "pontos": 4}, {"termo": "IRPJ", "pontos": 4}, {"termo": "CSLL", "pontos": 4}, {"termo": "PIS", "pontos": 4}, {"termo": "Cofins", "pontos": 4}, {"termo": "ICMS", "pontos": 4}, {"termo": "ISS", "pontos": 4}, {"termo": "substituição tributária", "pontos": 4}, {"termo": "DIFAL", "pontos": 4}, {"termo": "NFS-e", "pontos": 4}, {"termo": "NF-e", "pontos": 4}, {"termo": "nota fiscal", "pontos": 4}, {"termo": "FGTS", "pontos": 4}, {"termo": "INSS", "pontos": 4}, {"termo": "contribuição previdenciária", "pontos": 4}, {"termo": "folha de pagamento", "pontos": 4}, {"termo": "desoneração", "pontos": 4}, {"termo": "lucro presumido", "pontos": 4}, {"termo": "lucro real", "pontos": 4}, {"termo": "dividendos", "pontos": 4}, {"termo": "distribuição de lucros", "pontos": 4}, {"termo": "edital", "pontos": 4}, {"termo": "editais", "pontos": 4}, {"termo": "Regularize", "pontos": 4}, {"termo": "exclusão", "pontos": 4}, {"termo": "opção", "pontos": 4}, {"termo": "decreto", "pontos": 3}, {"termo": "medida provisória", "pontos": 3}, {"termo": "alíquota", "pontos": 3}, {"termo": "alíquotas", "pontos": 3}, {"termo": "tabela", "pontos": 3}, {"termo": "CNPJ", "pontos": 3}, {"termo": "contribuinte", "pontos": 3}, {"termo": "contribuintes", "pontos": 3}, {"termo": "empresas", "pontos": 3}, {"termo": "tributária", "pontos": 3}, {"termo": "tributário", "pontos": 3}, {"termo": "tributos", "pontos": 3}, {"termo": "benefício fiscal", "pontos": 3}, {"termo": "TTD", "pontos": 3}, {"termo": "Santa Catarina", "pontos": 3}, {"termo": "salário mínimo", "pontos": 3}, {"termo": "perguntas e respostas", "pontos": 3}, {"termo": "orientação", "pontos": 3}, {"termo": "guia", "pontos": 3}, {"termo": "CGIBS", "pontos": 3}, {"termo": "CGSN", "pontos": 3}, {"termo": "restituição", "pontos": 3}, {"termo": "compensação", "pontos": 3}, {"termo": "crédito", "pontos": 3}, {"termo": "declaração", "pontos": 3}, {"termo": "malha", "pontos": 3}, {"termo": "débitos", "pontos": 3}, {"termo": "dívida ativa", "pontos": 3}, {"termo": "solução de consulta", "pontos": 2}, {"termo": "portaria", "pontos": 2}, {"termo": "resolução", "pontos": 2}, {"termo": "ato DIAT", "pontos": 2}, {"termo": "ato declaratório executivo", "pontos": -3}, {"termo": "apreende", "pontos": -8}, {"termo": "apreensão", "pontos": -8}, {"termo": "apreendidos", "pontos": -8}, {"termo": "apreendidas", "pontos": -8}, {"termo": "contrabando", "pontos": -8}, {"termo": "descaminho", "pontos": -8}, {"termo": "leilão", "pontos": -8}, {"termo": "maconha", "pontos": -8}, {"termo": "cocaína", "pontos": -8}, {"termo": "drogas", "pontos": -8}, {"termo": "haxixe", "pontos": -8}, {"termo": "cigarros", "pontos": -8}, {"termo": "armas", "pontos": -8}, {"termo": "aduana", "pontos": -8}, {"termo": "alfândega", "pontos": -8}, {"termo": "alfandegado", "pontos": -8}, {"termo": "aeroporto", "pontos": -8}, {"termo": "fronteira", "pontos": -8}, {"termo": "concurso", "pontos": -8}, {"termo": "servidores", "pontos": -8}, {"termo": "nomeia", "pontos": -8}, {"termo": "designa", "pontos": -8}, {"termo": "delega", "pontos": -8}, {"termo": "credenciamento", "pontos": -8}, {"termo": "despachante", "pontos": -8}, {"termo": "Instagram", "pontos": -8}, {"termo": "homenagem", "pontos": -8}, {"termo": "prêmio", "pontos": -8}, {"termo": "seminário", "pontos": -8}]}'::jsonb)
on conflict (chave) do nothing;

-- v0.20.0: na instalação que já existe, a assinatura ganha os campos da identificação legal vazios ("cnpj" e "crc"), para o
-- administrador só preencher entre as aspas (Configurações). O que já estiver preenchido fica como está.
update public.radar_config set valor = '{"cnpj": "", "crc": ""}'::jsonb || valor
 where chave = 'assinatura' and jsonb_typeof(valor) = 'object' and not (valor ? 'cnpj' and valor ? 'crc');

-- v0.21.0: na instalação que já existe, o "Honorário contábil" (interno) sai da agenda da semana das redes ("redes": false), se o
-- administrador ainda não decidiu nada sobre ele. O resto da lista fica como está.
update public.radar_config
   set valor = (select jsonb_agg(case when jsonb_typeof(o) = 'object' and o->>'nome' = 'Honorário contábil' and not (o ? 'redes')
                                      then o || '{"redes": false}'::jsonb else o end order by i)
                  from jsonb_array_elements(valor) with ordinality t(o, i))
 where chave = 'obrigacoes' and jsonb_typeof(valor) = 'array'
   and exists (select 1 from jsonb_array_elements(valor) o
                where jsonb_typeof(o) = 'object' and o->>'nome' = 'Honorário contábil' and not (o ? 'redes'));

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
-- v0.15.0: e têm a fundamentação legal lida pelas regras em vigor
select public.radar_recalcular_base_legal() as capturas_base_legal;

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
-- Esperado: 28 tabelas, todas com rls = true; 6 fontes; 8 categorias; ao menos 1 instalação concluída (v0.29.0).
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
-- a versão da instalação concluída mais nova (a ordem é a do registro: como texto, "v0.9.0" viria depois de "v0.21.0")
select 'instalacoes concluidas', count(*)::text,
       (select i.versao from public.radar_instalacoes i where i.depois is not null order by i.id desc limit 1), null, null
  from public.radar_instalacoes where depois is not null
order by 1, 2;
