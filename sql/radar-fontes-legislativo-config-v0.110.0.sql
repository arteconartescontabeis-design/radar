-- sql/radar-fontes-legislativo-config-v0.110.0.sql — ajustes nas fontes Câmara e Senado (Dados Abertos).
-- 1) sem_pagina_de_texto: a ementa que a API já traz vira o texto guardado. Sem isto, o robô tentava baixar a página
--    (SPA) da ficha/matéria, que vem quase vazia → a fonte ficava sempre "parcial" e gastava uma requisição por item.
-- 2) palavras: as siglas curtas (iss, cbs, ibs, pis, mei, clt) passam a ser ancoradas com \b, para não casar pedaço de
--    palavra (comissão → "iss", primeiro → "mei", episódio → "pis"), que metia CPIs/educação/etc. num feed tributário/trabalhista.
-- Só mexe na config destas duas fontes; não cria nem apaga nada. Pode rodar de novo (idempotente).

update public.radar_fontes
   set config = '{"casa": "camara", "janela_dias": 15, "temas": [70, 58], "paginas_max": 3, "sem_pagina_de_texto": true, "palavras": "tribut|imposto|icms|\\biss\\b|\\bcbs\\b|\\bibs\\b|\\bpis\\b|cofins|reforma tribut|simples|\\bmei\\b|trabalh|\\bclt\\b|emprego|fgts|inss|previd|salario|folha"}'::jsonb
 where slug = 'camara-proposicoes';

update public.radar_fontes
   set config = '{"casa": "senado", "janela_dias": 15, "paginas_max": 1, "sem_pagina_de_texto": true, "palavras": "tribut|imposto|icms|\\biss\\b|\\bcbs\\b|\\bibs\\b|\\bpis\\b|cofins|reforma tribut|simples|\\bmei\\b|trabalh|\\bclt\\b|emprego|fgts|inss|previd|salario|folha"}'::jsonb
 where slug = 'senado-materias';
