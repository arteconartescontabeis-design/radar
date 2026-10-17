-- =====================================================================
-- Radar Artecon — fontes oficiais que faltavam (v0.31.0, 17/10/2026)
-- Rode no Supabase (SQL Editor) DEPOIS de publicar a v0.31.0 e de o robô novo coletar uma vez (GitHub → Actions → "Radar — coleta
-- das fontes oficiais" → Run workflow): é o robô da v0.31.0 que entende o filtro de tema ("palavras" e "excluir_palavras"); o robô
-- antigo ignoraria o filtro e traria tudo das fontes novas. Antes disso, este arquivo para no começo, sem mudar nada.
-- Pode rodar de novo: fonte que já existe (mesmo identificador) não é alterada — o que você ligou, desligou ou ajustou fica.
--
-- Entram LIGADAS as fontes cujo cadastro foi conferido com páginas e atos reais (17/10/2026), todas oficiais:
--   * Diário Oficial da União pelo INLABS (o mesmo acesso da fonte dou-inlabs; nenhum segredo novo): leis, decretos, MPs e emendas
--     (dou-presidencia); CONFAZ (dou-confaz: é por aqui que os convênios chegam, porque o site do CONFAZ não abre fora do Brasil);
--     trabalho, FGTS, eSocial e previdência (dou-trabalho-previdencia). O robô baixa o DOU de cada dia uma vez só por rodada.
--   * gov.br: notícias do eSocial, comunicados do FGTS Digital e notícias da Previdência (só empresas e contribuições).
--   Têm filtro de tema ("palavras" e/ou "excluir_palavras") as do Diário Oficial, a da Previdência e as do DOM/SC.
--   O eSocial e o FGTS Digital ficam sem filtro: tudo o que publicam é do departamento pessoal, e são poucas notícias por mês.
-- Entram DESLIGADAS (ligue em Fontes → Configurar → Fonte ativa, se quiser):
--   * dou-fazenda-ministro (opcional, fora do pedido): portarias do Ministro da Fazenda, como as alíquotas da CBS;
--   * inss-noticias: quase tudo é orientação ao segurado (3 de 60 notícias tocavam o escritório);
--   * DOM/SC (Diário Oficial dos Municípios de SC): leis e decretos de Palhoça e de São José (os sites das prefeituras recusam o robô)
--     achados pela pesquisa do próprio site (tributos, IPTU, ITBI, ISS, nota fiscal, alvará...). Essa pesquisa olha o ato inteiro e até
--     o nome do arquivo, e deixa passar atos de outros assuntos: por isso cada fonte também tira, em "excluir_palavras", os que
--     apareceram nos feeds reais (qualificação de entidade, Temporada de Verão, nomeação de conselho, utilidade pública, serviços
--     funerários, operação de crédito). O feed foi conferido, mas o site pede, no robots.txt, que robôs não entrem: decisão do dono
--     antes de ligar (e antes de testar pelo diagnóstico).
--     Ligado, o robô lê só o feed de cada pesquisa (1 pedido por fonte por dia), sem abrir a página de cada ato.
-- Florianópolis fica de fora nesta versão: o site da prefeitura recusa o robô e, no DOM/SC, a lista não diz o assunto do ato.
--
-- A fonte rfb-normas (atos da Receita, sistema Normas) passa para a pesquisa pública nova do Normas e CONTINUA DESLIGADA: em
-- 04/10/2026 a mesma pesquisa recusou o GitHub (HTTP 403). Ligue só depois de o diagnóstico pelo GitHub dar HTTP 200 (Actions →
-- "Radar — diagnóstico das fontes" → em "endereços", escreva rfb-normas). O endereço só é trocado se ainda for o antigo.
-- =====================================================================

-- o robô da v0.31.0 já rodou? (a versão fica em cada execução de coleta)
do $$
begin
  if not exists (select 1 from public.radar_execucoes e
                  where case when e.versao_robo ~ '^[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}$'
                             then string_to_array(e.versao_robo, '.')::int[] >= array[0, 31, 0] else false end) then
    raise exception 'RADAR: rode este SQL depois de publicar a v0.31.0 e de o robô novo coletar uma vez (GitHub → Actions → "Radar — coleta das fontes oficiais" → Run workflow). O robô antigo não entende o filtro de tema e traria tudo das fontes novas. Nada foi alterado.'
      using errcode = 'P0001';
  end if;
end $$;

insert into public.radar_fontes (slug, nome, orgao, abrangencia, oficial, ativo, tipo_coletor, url, config, categoria_padrao, frequencia_horas)
select v.slug, v.nome, v.orgao, v.abrangencia, v.oficial, v.ativo, v.tipo_coletor, v.url, v.config,
       (select c.slug from public.radar_categorias c where c.slug = v.categoria),   -- categoria apagada: fica sem
       v.frequencia_horas
from (values
-- DOU (INLABS): leis, leis complementares, decretos, MPs e emendas; só pelo TIPO do ato (a Imprensa Nacional às vezes troca o órgão) e pelo tema
  ('dou-presidencia', 'Diário Oficial da União — leis, decretos e medidas provisórias (INLABS)', 'Presidência da República', 'federal', true, true, 'inlabs',
   'https://inlabs.in.gov.br/',
   '{"janela_dias": 5, "secoes": ["DO1", "DO1E"], "texto_do_feed": true, "texto_minimo": 1, "max_itens": 30, "tempo_max_segundos": 600, "tipos": "^(Lei|Lei Complementar|Decreto|Decreto numerado|Medida Provisória|Emenda Constitucional)$", "palavras": ["tribut", "impost", "contribuiç", "IRPF", "IRPJ", "IRRF", "CSLL", "\\bPIS\\b", "Pasep", "Cofins", "\\bIPI\\b", "\\bIOF\\b", "ICMS", "\\bISS\\b", "\\bIBS\\b", "\\bCBS\\b", "alíquota", "Simples Nacional", "microempre", "\\bMEI\\b", "pequeno porte", "empresa", "empresári", "CNPJ", "contáb", "contador", "trabalh", "emprego", "empregad", "salári", "FGTS", "previdênc", "INSS", "aposentad", "seguro-desemprego", "férias", "jornada", "repouso semanal", "parcelamento", "transação", "dívida ativa", "débito", "crédito tributário", "Receita Federal", "Fazenda Nacional", "nota fiscal", "dividendo", "lucro", "Refis", "regularização", "incentivos? fisca", "benefícios? fisca", "isenç", "Zona Franca", "Livre Comércio", "desoneração", "folha de pagamento", "Consolidação das Leis do Trabalho", "Código Tributário", "Lei Complementar (?:n\\S{0,2}\\s*)?(?:87|116|123|214|227)\\b", "Lei (?:n\\S{0,2}\\s*)?(?:5\\.172|7\\.689|7\\.713|8\\.036|8\\.212|8\\.213|9\\.249|9\\.250|9\\.430|9\\.718|10\\.522|10\\.637|10\\.833|12\\.546|13\\.988|6\\.404|10\\.406|11\\.101|6\\.830)\\b", "Decreto-Lei (?:n\\S{0,2}\\s*)?5\\.452"], "excluir_palavras": ["crédito extraordinário", "crédito suplementar", "crédito especial", "Orçamento de Investimento", "Orçamento Fiscal", "Estrutura Regimental", "cargos em comissão", "funções de confiança", "organização social", "forças militares", "programação orçamentária", "Denomina (o|a|os|as) ", "Institui o Dia", "Inscreve o nome", "Livro dos Heróis", "título de Capital", "Patrono", "Patrona", "Confere o título", "calendário turístico", "Rota Turística", "radiodifusão"]}'::jsonb,
   'federal', 12),
-- DOU (INLABS): CONFAZ e COTEPE (convênios, ajustes, protocolos, atos declaratórios); fora o PMPF e as listas de empresas credenciadas
  ('dou-confaz', 'Diário Oficial da União — CONFAZ: convênios, ajustes e protocolos do ICMS (INLABS)', 'Conselho Nacional de Política Fazendária (CONFAZ)', 'federal', true, true, 'inlabs',
   'https://inlabs.in.gov.br/',
   '{"janela_dias": 5, "secoes": ["DO1", "DO1E"], "texto_do_feed": true, "texto_minimo": 1, "max_itens": 30, "tempo_max_segundos": 600, "orgaos": "Conselho Nacional de Política Fazendária|Comissão Técnica Permanente do ICMS", "excluir_palavras": ["PMPF", "preço médio ponderado", "relação d[aeo]s? (contribuintes|empresas)"]}'::jsonb,
   'santa-catarina', 12),
-- DOU (INLABS): MTE, Previdência, INSS, Conselho Curador do FGTS, CODEFAT e circulares da Caixa, só no tema do DP
  ('dou-trabalho-previdencia', 'Diário Oficial da União — Trabalho, FGTS, eSocial e Previdência (INLABS)', 'Ministério do Trabalho e Emprego e Ministério da Previdência Social', 'federal', true, true, 'inlabs',
   'https://inlabs.in.gov.br/',
   '{"janela_dias": 5, "secoes": ["DO1", "DO1E"], "texto_do_feed": true, "texto_minimo": 1, "max_itens": 30, "tempo_max_segundos": 600, "orgaos": "^Ministério do Trabalho e Emprego|^Ministério da Previdência Social|Caixa Econômica Federal", "tipos": "^(Portaria|Portaria Conjunta|Portaria Interministerial|Instrução Normativa|Resolução|Resolução Conjunta|Circular)$", "excluir_orgao": "Superintendência Regional|Gerência|Agência da Previdência|Previdência Complementar|Coordenação-Geral de Recursos|Relações do Trabalho|Fundacentro|Tecnologia da Informação|Conselho de Recursos|Corregedoria|Auditoria|Procuradoria", "palavras": ["FGTS Digital", "conta vinculada", "contas vinculadas", "depósitos? (?:do|no) FGTS", "recolhimento", "saque", "eSocial", "empregador", "empregad[oa]s?", "trabalhador", "contrato de trabalho", "jornada", "férias", "décimo terceiro", "gratificação natalina", "salário-maternidade", "salário maternidade", "salário-família", "incapacidade", "auxílio-doença", "afastad", "afastamento", "aviso prévio", "rescis", "seguro-desemprego", "abono salarial", "\\bRAIS\\b", "CAGED", "Norma Regulamentadora", "\\bNR-?\\s?\\d", "segurança e saúde no trabalho", "Fator Acidentário", "\\bFAP\\b", "\\bRAT\\b", "contribuição previdenciária", "contribuições previdenciárias", "salário de contribuição", "salário-de-contribuição", "reajuste dos benefícios", "salário mínimo", "aprendiz", "pessoa com deficiência", "consignado", "consignação", "Crédito do Trabalhador", "carteira de trabalho", "\\bCTPS\\b", "registro de ponto", "ponto eletrônico", "registro eletrônico de ponto", "feriados", "domingos", "convenção coletiva", "Portaria[/ ]MTP (?:n\\S{0,2}\\s*)?671\\b", "Portaria MTE (?:n\\S{0,2}\\s*)?3\\.665\\b", "Instrução Normativa[/ ]MTP (?:n\\S{0,2}\\s*)?2\\b", "trabalho temporário", "Certificado de Regularidade", "aposentadoria", "pensão por morte", "\\bsegurad[oa]s?\\b", "Domicílio Eletrônico Trabalhista", "inspeção do trabalho", "auto de infração", "parcelamento", "multa", "encargos"], "excluir_palavras": ["Manual de Fomento", "habitação", "habitacional", "moradia", "saneamento", "infraestrutura", "mobilidade urbana", "Pró-Transporte", "Pró-Cidades", "Regimento Interno", "Política de Governança", "governança de dados", "gestão de riscos", "avaliação de desempenho institucional", "imóve", "patrimonial", "despesas imobiliárias", "Pescador Artesanal", "fatores de atualização", "Mesa Nacional", "Fórum", "FCVS", "Variações Salariais", "produtividade", "orçamento", "metas", "demonstrações financeiras", "campanha", "alocação de recursos", "taxa de administração", "tarifas", "Termo de Conciliação", "cargos comissionados", "funções comissionadas", "Comitê Estratégico"]}'::jsonb,
   'trabalhista', 12),
-- DOU (INLABS), OPCIONAL (desligada): portarias do Ministro da Fazenda (alíquotas da CBS, Portarias Conjuntas MF/CGIBS)
  ('dou-fazenda-ministro', 'Diário Oficial da União — portarias do Ministro da Fazenda (INLABS)', 'Ministério da Fazenda', 'federal', true, false, 'inlabs',
   'https://inlabs.in.gov.br/',
   '{"janela_dias": 5, "secoes": ["DO1", "DO1E"], "texto_do_feed": true, "texto_minimo": 1, "max_itens": 30, "tempo_max_segundos": 600, "orgaos": "^Ministério da Fazenda/Gabinete do Ministro$", "tipos": "^(Portaria|Portaria Conjunta|Portaria Interministerial|Portaria Normativa|Instrução Normativa|Resolução)$", "palavras": ["tribut", "impost", "contribuiç", "IRPF", "IRPJ", "IRRF", "CSLL", "\\bPIS\\b", "Pasep", "Cofins", "\\bIPI\\b", "\\bIOF\\b", "ICMS", "\\bISS\\b", "\\bIBS\\b", "\\bCBS\\b", "alíquota", "Simples Nacional", "microempre", "\\bMEI\\b", "pequeno porte", "empresa", "empresári", "CNPJ", "contáb", "contador", "trabalh", "emprego", "empregad", "salári", "FGTS", "previdênc", "INSS", "aposentad", "seguro-desemprego", "férias", "jornada", "repouso semanal", "parcelamento", "transação", "dívida ativa", "débito", "crédito tributário", "Receita Federal", "Fazenda Nacional", "nota fiscal", "dividendo", "lucro", "Refis", "regularização", "incentivos? fisca", "benefícios? fisca", "isenç", "Zona Franca", "Livre Comércio", "desoneração", "folha de pagamento", "Consolidação das Leis do Trabalho", "Código Tributário", "Lei Complementar (?:n\\S{0,2}\\s*)?(?:87|116|123|214|227)\\b", "Lei (?:n\\S{0,2}\\s*)?(?:5\\.172|7\\.689|7\\.713|8\\.036|8\\.212|8\\.213|9\\.249|9\\.250|9\\.430|9\\.718|10\\.522|10\\.637|10\\.833|12\\.546|13\\.988|6\\.404|10\\.406|11\\.101|6\\.830)\\b", "Decreto-Lei (?:n\\S{0,2}\\s*)?5\\.452"], "excluir_palavras": ["inidoneidade", "licitar", "equalização", "subvenção", "valores autorizados para pagamento", "delega(r)? competência", "Estrutura Regimental", "cargos em comissão", "funções de confiança", "programação orçamentária", "Novação de Dívidas", "contragarantia", "operação de crédito"]}'::jsonb,
   'federal', 12),
-- gov.br: notícias do eSocial (raiz e subpastas da Receita, do MTE e da Previdência)
  ('esocial-noticias', 'eSocial — Notícias', 'Comitê Gestor do eSocial', 'federal', true, true, 'html_links',
   'https://www.gov.br/esocial/pt-br/noticias',
   '{"janela_dias": 30, "padrao_url": "^https://www\\.gov\\.br/esocial/pt-br/noticias/(?:[a-z0-9-]+/)?[a-z0-9]+(?:-[a-z0-9]+)+$", "excluir_url": "/noticias/(?:colecao-[^/]*|receita-federal|ministerio-do-trabalho-e-emprego|previdencia-social)$", "seletor_texto": "[property=''rnews:articleBody''], #parent-fieldname-text, #content-core, article, main"}'::jsonb,
   'trabalhista', 12),
-- gov.br: comunicados do FGTS Digital, em ordem de publicação (a pasta simples está em ordem manual)
  ('fgts-digital-comunicados', 'FGTS Digital — Comunicados', 'Ministério do Trabalho e Emprego', 'federal', true, true, 'html_links',
   'https://www.gov.br/trabalho-e-emprego/pt-br/servicos/empregador/fgtsdigital/comunicados/summary_view?contentFilter.sort_on:record=effective&contentFilter.sort_order:record=reverse',
   '{"janela_dias": 30, "padrao_url": "^https://www\\.gov\\.br/trabalho-e-emprego/pt-br/servicos/empregador/fgtsdigital/comunicados/[a-z0-9]+(?:-[a-z0-9]+)+$", "excluir_url": "/comunicados/(?:summary_view|listing_view|tabular_view|album_view|full_view)$", "seletor_texto": "[property=''rnews:articleBody''], #parent-fieldname-text, #content-core, article, main"}'::jsonb,
   'trabalhista', 12),
-- gov.br: notícias da Previdência, só as do tema (empresas e contribuições: FAP, RAT, alíquotas...)
  ('previdencia-noticias', 'Ministério da Previdência Social — Notícias (só empresas e contribuições)', 'Ministério da Previdência Social', 'federal', true, true, 'html_links',
   'https://www.gov.br/previdencia/pt-br/noticias',
   '{"janela_dias": 30, "padrao_url": "^https://www\\.gov\\.br/previdencia/pt-br/noticias/\\d{4}/[a-z]+/[^/?#]+$", "palavras": "\\bFAP\\b|fator acidentario|\\bRAT\\b|\\bGILRAT\\b|aliquota|contribuic(?:ao|oes) (?:previdenciaria|patronal|sobre a folha)|tabela de contribuic|empregador|\\bempresas?\\b|esocial|dctfweb|folha de (?:pagamento|salarios)|salario[- ]familia|salario[- ]maternidade|teto do (?:INSS|RGPS)|portaria interministerial|desoneracao|reoneracao|\\bMEI\\b|contribuinte individual|complementac|menor que o salario minimo|abaixo do salario minimo|acidente de trabalho|\\bCAT\\b|\\bCNIS\\b", "seletor_texto": "[property=''rnews:articleBody''], #parent-fieldname-text, #content-core, article, main"}'::jsonb,
   'trabalhista', 24),
-- gov.br, DESLIGADA: notícias do INSS (quase tudo é orientação ao segurado; o endereço /inss/pt-br/noticias leva ao login)
  ('inss-noticias', 'INSS — Notícias (só empresas e contribuições)', 'Instituto Nacional do Seguro Social', 'federal', true, false, 'html_links',
   'https://www.gov.br/inss/pt-br/assuntos/noticias/ultimas-noticias',
   '{"janela_dias": 30, "exigir_data": true, "padrao_url": "^https://www\\.gov\\.br/inss/pt-br/assuntos/(?:noticias/)?[a-z0-9]+(?:-[a-z0-9]+){3,}$", "excluir_url": "/assuntos/noticias/ultimas-noticias$", "palavras": "\\bFAP\\b|fator acidentario|\\bRAT\\b|\\bGILRAT\\b|aliquota|contribuic(?:ao|oes) (?:previdenciaria|patronal|sobre a folha)|tabela de contribuic|empregador|\\bempresas?\\b|esocial|dctfweb|folha de (?:pagamento|salarios)|salario[- ]familia|salario[- ]maternidade|teto do (?:INSS|RGPS)|portaria interministerial|desoneracao|reoneracao|\\bMEI\\b|contribuinte individual|complementac|menor que o salario minimo|abaixo do salario minimo|acidente de trabalho|\\bCAT\\b|\\bCNIS\\b", "seletor_texto": "[property=''rnews:articleBody''], #parent-fieldname-text, #content-core, article, main"}'::jsonb,
   'trabalhista', 24),
-- DOM/SC, DESLIGADA até o dono decidir (o site pede que robôs não entrem: robots.txt): o feed RSS da pesquisa do site (Palhoça, Leis: tributos, IPTU, ISS...) menos os assuntos de fora
  ('domsc-palhoca-leis', 'Palhoça — leis sobre tributos (Diário Oficial dos Municípios)', 'Prefeitura Municipal de Palhoça', 'municipal', true, false, 'rss',
   'https://diariomunicipal.sc.gov.br/?r=site/portal&codigoEntidade=185&categoria=Leis&q=(tribut*%20OR%20IPTU%20OR%20ITBI%20OR%20ISS%20OR%20ISSQN%20OR%20%22nota%20fiscal%22%20OR%20NFSe%20OR%20REFIS%20OR%20%22d%C3%ADvida%20ativa%22%20OR%20alvar%C3%A1%20OR%20%22cadastro%20econ%C3%B4mico%22%20OR%20%22Simples%20Nacional%22%20OR%20%22contribui%C3%A7%C3%A3o%20de%20melhoria%22)&excluiTermos=suplementar%20exonera%20nomeia%20legitima*&view=rss',
   '{"janela_dias": 30, "max_itens": 10, "sem_pagina_de_texto": true, "tempo_max_segundos": 60, "excluir_palavras": ["qualificação de entidade", "organização social", "organizações sociais", "Temporada de Verão", "nomeação dos membros", "utilidade pública", "serviços funerários", "operação de crédito"]}'::jsonb,
   'santa-catarina', 24),
-- DOM/SC, DESLIGADA até o dono decidir (o site pede que robôs não entrem: robots.txt): o feed RSS da pesquisa do site (Palhoça, Decretos: tributos, IPTU, ISS...) menos os assuntos de fora
  ('domsc-palhoca-decretos', 'Palhoça — decretos sobre tributos (Diário Oficial dos Municípios)', 'Prefeitura Municipal de Palhoça', 'municipal', true, false, 'rss',
   'https://diariomunicipal.sc.gov.br/?r=site/portal&codigoEntidade=185&categoria=Decretos&q=(tribut*%20OR%20IPTU%20OR%20ITBI%20OR%20ISS%20OR%20ISSQN%20OR%20%22nota%20fiscal%22%20OR%20NFSe%20OR%20REFIS%20OR%20%22d%C3%ADvida%20ativa%22%20OR%20alvar%C3%A1%20OR%20%22cadastro%20econ%C3%B4mico%22%20OR%20%22Simples%20Nacional%22%20OR%20%22contribui%C3%A7%C3%A3o%20de%20melhoria%22)&excluiTermos=suplementar%20exonera%20nomeia%20legitima*&view=rss',
   '{"janela_dias": 30, "max_itens": 10, "sem_pagina_de_texto": true, "tempo_max_segundos": 60, "excluir_palavras": ["qualificação de entidade", "organização social", "organizações sociais", "Temporada de Verão", "nomeação dos membros", "utilidade pública", "serviços funerários", "operação de crédito"]}'::jsonb,
   'santa-catarina', 24),
-- DOM/SC, DESLIGADA até o dono decidir (o site pede que robôs não entrem: robots.txt): o feed RSS da pesquisa do site (São José, Leis: tributos, IPTU, ISS...) menos os assuntos de fora
  ('domsc-saojose-leis', 'São José — leis sobre tributos (Diário Oficial dos Municípios)', 'Prefeitura Municipal de São José', 'municipal', true, false, 'rss',
   'https://diariomunicipal.sc.gov.br/?r=site/portal&codigoEntidade=251&categoria=Leis&q=(tribut*%20OR%20IPTU%20OR%20ITBI%20OR%20ISS%20OR%20ISSQN%20OR%20%22nota%20fiscal%22%20OR%20NFSe%20OR%20REFIS%20OR%20%22d%C3%ADvida%20ativa%22%20OR%20alvar%C3%A1%20OR%20%22cadastro%20econ%C3%B4mico%22%20OR%20%22Simples%20Nacional%22%20OR%20%22contribui%C3%A7%C3%A3o%20de%20melhoria%22)&excluiTermos=suplementar%20exonera%20nomeia%20legitima*&view=rss',
   '{"janela_dias": 30, "max_itens": 10, "sem_pagina_de_texto": true, "tempo_max_segundos": 60, "excluir_palavras": ["qualificação de entidade", "organização social", "organizações sociais", "Temporada de Verão", "nomeação dos membros", "utilidade pública", "serviços funerários", "operação de crédito"]}'::jsonb,
   'santa-catarina', 24),
-- DOM/SC, DESLIGADA até o dono decidir (o site pede que robôs não entrem: robots.txt): o feed RSS da pesquisa do site (São José, Decretos: tributos, IPTU, ISS...) menos os assuntos de fora
  ('domsc-saojose-decretos', 'São José — decretos sobre tributos (Diário Oficial dos Municípios)', 'Prefeitura Municipal de São José', 'municipal', true, false, 'rss',
   'https://diariomunicipal.sc.gov.br/?r=site/portal&codigoEntidade=251&categoria=Decretos&q=(tribut*%20OR%20IPTU%20OR%20ITBI%20OR%20ISS%20OR%20ISSQN%20OR%20%22nota%20fiscal%22%20OR%20NFSe%20OR%20REFIS%20OR%20%22d%C3%ADvida%20ativa%22%20OR%20alvar%C3%A1%20OR%20%22cadastro%20econ%C3%B4mico%22%20OR%20%22Simples%20Nacional%22%20OR%20%22contribui%C3%A7%C3%A3o%20de%20melhoria%22)&excluiTermos=suplementar%20exonera%20nomeia%20legitima*&view=rss',
   '{"janela_dias": 30, "max_itens": 10, "sem_pagina_de_texto": true, "tempo_max_segundos": 60, "excluir_palavras": ["qualificação de entidade", "organização social", "organizações sociais", "Temporada de Verão", "nomeação dos membros", "utilidade pública", "serviços funerários", "operação de crédito"]}'::jsonb,
   'santa-catarina', 24)
) as v (slug, nome, orgao, abrangencia, oficial, ativo, tipo_coletor, url, config, categoria, frequencia_horas)
on conflict (slug) do nothing;

-- Atos da Receita (rfb-normas): a pesquisa pública nova do sistema Normas (a mesma que a página usa; sem captcha, sem login) e o texto
-- de cada ato pela consulta externa. Saem as Coana (aduana) e entram as Soluções de Consulta das Disit (IRPJ, Simples, contribuições;
-- a dou-inlabs não as traz); fora do tema: classificação de mercadorias (NCM), devedor contumaz, Remessa Conforme e OEA. Só troca se
-- o endereço ainda for o da consulta antiga (não desfaz um ajuste feito na tela) e NÃO liga a fonte.
update public.radar_fontes
   set url = 'https://normas.receita.fazenda.gov.br/api/indexacao/ato/pesquisar',
       config = '{"janela_dias": 10, "paginas_max": 5, "itens_por_pagina": 100, "max_itens": 300, "excluir_orgao": "^(SRRF|DRF|ALF|IRF|DERAT|DEFIS|DELEX|DECEX|DEMAC|DRJ|ARF|Coana)", "excluir_palavras": "Classificação de Mercadorias|devedora contumaz|Remessa Conforme|Operador Econômico Autorizado", "url_texto": "https://normasinternet2.receita.fazenda.gov.br/api/consulta-externa/ato/{id}/visao/multivigente", "dominios": ["normasinternet2.receita.fazenda.gov.br"], "tempo_max_segundos": 180}'::jsonb
 where slug = 'rfb-normas' and (url like '%sijut2consulta%' or url like '%{inicio}%');

-- Conferência: as fontes desta versão e se estão ligadas
select f.slug, f.nome, case when f.ativo then 'ligada' else 'desligada' end as situacao, f.oficial, f.tipo_coletor, f.categoria_padrao
  from public.radar_fontes f
 where f.slug in ('dou-presidencia','dou-confaz','dou-trabalho-previdencia','dou-fazenda-ministro','esocial-noticias',
                  'fgts-digital-comunicados','previdencia-noticias','inss-noticias','domsc-palhoca-leis','domsc-palhoca-decretos',
                  'domsc-saojose-leis','domsc-saojose-decretos','rfb-normas')
 order by f.id;
