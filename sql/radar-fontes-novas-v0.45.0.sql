-- =====================================================================
-- Radar Artecon — fonte nova da v0.45.0: Palhoça e São José pelos DADOS ABERTOS da CIGA
-- Rode no Supabase (SQL Editor) DEPOIS de publicar a v0.45.0 e de o robô novo coletar uma vez
-- (GitHub → Actions → "Radar — coleta das fontes oficiais" → Run workflow): é o robô da v0.45.0
-- que conhece o coletor "ciga_dados". Antes disso, este arquivo para no começo, sem mudar nada.
-- Pode rodar de novo: fonte que já existe (mesmo identificador) não é alterada.
--
-- O caminho combinado com a CIGA (20/10/2026): o site do diário (diariomunicipal.sc.gov.br) pede,
-- no robots.txt, que robôs não entrem, e o suporte confirmou que não há exceção — o robô NUNCA o
-- visita. A leitura é pelo portal de dados abertos da própria CIGA (dados.ciga.sc.gov.br), que
-- publica as edições para download: UMA rodada por dia, lendo a página do conjunto do mês e os
-- arquivos do dia anterior (e do anterior a ele, por segurança), com pausa de 10 segundos entre
-- os pedidos (o Crawl-Delay do robots.txt do portal) e o robô identificado no User-Agent.
-- O texto completo de cada ato vem no próprio arquivo; o endereço da captura aponta ao diário
-- oficial SÓ para a pessoa abrir no navegador (consulta humana é uso normal do site).
--
-- A fonte entra LIGADA, no lugar das quatro antigas do DOM/SC (domsc-palhoca-leis,
-- domsc-palhoca-decretos, domsc-saojose-leis, domsc-saojose-decretos), que seguem DESLIGADAS e
-- podem ser apagadas na tela (Fontes → Configurar), se quiser.
-- Filtros: municípios Palhoça e São José; categorias Leis e Decretos; e o mesmo tema de tributos
-- das fontes antigas (IPTU, ITBI, ISS, nota fiscal, REFIS, dívida ativa, alvará...), com as
-- exclusões vistas nos diários reais. Tudo ajustável em Fontes → Configurar.
-- =====================================================================

-- o robô da v0.45.0 já rodou? (a versão fica em cada execução de coleta)
do $$
begin
  if not exists (select 1 from public.radar_execucoes e
                  where case when e.versao_robo ~ '^[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}$'
                             then string_to_array(e.versao_robo, '.')::int[] >= array[0, 45, 0] else false end) then
    raise exception 'RADAR: rode este SQL depois de publicar a v0.45.0 e de o robô novo coletar uma vez (GitHub → Actions → "Radar — coleta das fontes oficiais" → Run workflow). O robô antigo não conhece o coletor dos dados abertos da CIGA. Nada foi alterado.'
      using errcode = 'P0001';
  end if;
end $$;

insert into public.radar_fontes (slug, nome, orgao, abrangencia, oficial, ativo, tipo_coletor, url, config, categoria_padrao, frequencia_horas)
select v.slug, v.nome, v.orgao, v.abrangencia, v.oficial, v.ativo, v.tipo_coletor, v.url, v.config,
       (select c.slug from public.radar_categorias c where c.slug = v.categoria),   -- categoria apagada: fica sem
       v.frequencia_horas
from (values
  ('domsc-ciga', 'Palhoça e São José — leis e decretos sobre tributos (dados abertos da CIGA)',
   'Consórcio de Inovação na Gestão Pública (CIGA) — Diário Oficial dos Municípios de SC', 'municipal', true, true, 'ciga_dados',
   'https://dados.ciga.sc.gov.br/',
   '{"janela_dias": 2, "municipios": ["Palhoça", "São José"], "categorias": ["Leis", "Decretos"], "max_zips": 8, "texto_do_feed": true, "texto_minimo": 1, "max_itens": 20, "tempo_max_segundos": 360, "palavras": ["tribut", "IPTU", "ITBI", "\\bISS\\b", "ISSQN", "nota fiscal", "NFS-?e", "REFIS", "dívida ativa", "alvará", "cadastro econômico", "Simples Nacional", "contribuição de melhoria", "taxa", "\\bIBS\\b", "parcelamento", "isenç", "anistia", "remissão", "código tributário"], "excluir_palavras": ["qualificação de entidade", "organização social", "organizações sociais", "Temporada de Verão", "nomeação dos membros", "utilidade pública", "serviços funerários", "operação de crédito", "crédito suplementar", "crédito especial", "crédito adicional"]}'::jsonb,
   'santa-catarina', 24)
) as v (slug, nome, orgao, abrangencia, oficial, ativo, tipo_coletor, url, config, categoria, frequencia_horas)
on conflict (slug) do nothing;

-- Conferência: a fonte nova e as quatro antigas do DOM/SC (seguem desligadas)
select f.slug, f.nome, case when f.ativo then 'ligada' else 'desligada' end as situacao, f.tipo_coletor, f.frequencia_horas
  from public.radar_fontes f
 where f.slug in ('domsc-ciga', 'domsc-palhoca-leis', 'domsc-palhoca-decretos', 'domsc-saojose-leis', 'domsc-saojose-decretos')
 order by f.id;
