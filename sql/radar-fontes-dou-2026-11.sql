-- =====================================================================
-- Radar Artecon — DOU em novembro/2026: o conserto dos Destaques e as fontes-espelho do site oficial
-- (enquanto o INLABS está em manutenção). Rode no Supabase (SQL Editor). Pode rodar de novo:
-- a PARTE 1 só reescreve a configuração dos Destaques; na PARTE 2, fonte que já existe não é alterada.
--
-- O que aconteceu: o INLABS (inlabs.in.gov.br) está fora do ar desde 19/10/2026 — "Manutenção
-- Programada", avisada na própria página oficial, que aponta a "Base de Dados de Publicações do DOU"
-- no site www.in.gov.br. As 4 fontes do INLABS ficaram falhando (HTTP 404) e o DOU quase parou de
-- entrar. Além disso, a fonte "DOU — Destaques" guardava o TEMA dentro do padrão dos links: num dia
-- sem destaque fiscal, nenhum link casava e a coleta acusava "possível mudança de layout" à toa.
-- =====================================================================

-- ---------------------------------------------------------------------
-- PARTE 1 — "DOU — Destaques": o padrão dos links passa a reconhecer QUALQUER matéria do DOU
-- (/web/dou/-/…-NÚMERO) e o tema vai para o filtro de palavras (título + resumo do cartão), como nas
-- outras fontes. Dia sem destaque fiscal vira "fora do tema", não falha.
-- ---------------------------------------------------------------------
update public.radar_fontes
   set config = (config - 'padrao_url' - 'palavras')
             || jsonb_build_object(
                  'padrao_url', '/web/dou/-/[^?#]*-\d{6,}$',
                  'palavras', jsonb_build_array(
                    'receita federal', '\brfb\b', 'pgfn', 'procuradoria-geral da fazenda',
                    'simples nacional', '\bcgsn\b', '\bcgibs\b', 'comitê gestor', 'cosit',
                    'ministério da fazenda', '^lei n', '^lei complementar', '^decreto', '^medida provisória',
                    'tribut', 'imposto', 'contribuiç', '\bicms\b', '\bibs\b', '\bcbs\b',
                    '\bfgts\b', 'esocial', '\binss\b', 'previdênci', 'trabalhist')),
       atualizado_em = now()
 where slug = 'dou-destaques';

-- ---------------------------------------------------------------------
-- PARTE 2 — as fontes-espelho "(site)": o mesmo DOU das 4 fontes do INLABS, pela página pública
-- "Leitura do Jornal" do in.gov.br (coletor novo dou_site, v0.65.0; sem login). Cada espelho COPIA a
-- configuração da fonte do INLABS correspondente (órgãos, tipos, palavras e exclusões) e muda só:
--   * secoes: ["do1", "do1e"] (a grafia da Leitura do Jornal);
--   * o texto completo vem da página do ato no in.gov.br (seletor_texto), não mais do XML
--     (texto_do_feed sai: o JSON da Leitura traz só um trecho);
--   * janela_dias 3 (a edição sai de manhã; fim de semana sem edição é pulado sem falha).
-- As fontes do INLABS FICAM COMO ESTÃO: quando o INLABS voltar, elas voltam sozinhas, e os atos
-- repetidos entre as duas famílias caem na detecção de duplicata de sempre (título/conteúdo).
-- Aí é escolher em Fontes → Configurar qual família desligar.
-- Rode esta parte DEPOIS de publicar a v0.65.0 e de o robô novo coletar uma vez (GitHub → Actions →
-- "Radar — coleta das fontes oficiais" → Run workflow): o robô antigo não conhece o coletor dou_site.
-- ---------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from public.radar_execucoes e
                  where case when e.versao_robo ~ '^[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}$'
                             then string_to_array(e.versao_robo, '.')::int[] >= array[0, 65, 0] else false end) then
    raise exception 'RADAR: rode a PARTE 2 depois de publicar a v0.65.0 e de o robô novo coletar uma vez (GitHub → Actions → "Radar — coleta das fontes oficiais" → Run workflow). O robô antigo não conhece o coletor dou_site. A PARTE 1 (Destaques) já ficou gravada.'
      using errcode = 'P0001';
  end if;
end $$;

-- o tipo novo entra na restrição dos coletores (bancos instalados antes da v0.65.0)
alter table public.radar_fontes drop constraint if exists radar_fontes_tipo_coletor_check;
alter table public.radar_fontes add constraint radar_fontes_tipo_coletor_check
  check (tipo_coletor in ('rss','html_links','normas_rfb','inlabs','ciga_dados','dou_site'));

insert into public.radar_fontes (slug, nome, orgao, abrangencia, oficial, ativo, tipo_coletor, url, config, categoria_padrao, frequencia_horas)
select f.slug || '-site',
       replace(f.nome, '(INLABS)', '(site oficial)'),
       f.orgao, f.abrangencia, f.oficial, true, 'dou_site',
       'https://www.in.gov.br/leiturajornal',
       (f.config - 'texto_do_feed')
         || jsonb_build_object('secoes', jsonb_build_array('do1', 'do1e'),
                               'seletor_texto', '.texto-dou, article, main',
                               'janela_dias', 3),
       f.categoria_padrao, f.frequencia_horas
  from public.radar_fontes f
 where f.slug in ('dou-inlabs', 'dou-presidencia', 'dou-confaz', 'dou-trabalho-previdencia')
   and not exists (select 1 from public.radar_fontes j where j.slug = f.slug || '-site');

select slug, nome, ativo, tipo_coletor from public.radar_fontes where slug like 'dou-%' order by slug;
