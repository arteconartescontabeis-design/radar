-- sql/radar-fontes-legislativo-v0.108.0.sql — coletor novo "api_legislativo" (Câmara e Senado).
-- Idempotente; pode rodar de novo. Amplia o CHECK de tipo_coletor e cadastra as duas fontes (não-oficiais).
begin;

alter table public.radar_fontes drop constraint if exists radar_fontes_tipo_coletor_check;
alter table public.radar_fontes add constraint radar_fontes_tipo_coletor_check
  check (tipo_coletor in ('rss','html_links','normas_rfb','inlabs','ciga_dados','dou_site','api_legislativo'));

insert into public.radar_fontes (slug, nome, orgao, abrangencia, oficial, tipo_coletor, url, config, categoria_padrao, frequencia_horas)
values
  ('camara-proposicoes', 'Câmara dos Deputados — Proposições (tributário/trabalhista)', 'Câmara dos Deputados', 'federal', false, 'api_legislativo', 'https://dadosabertos.camara.leg.br/api/v2/proposicoes', '{"casa": "camara", "janela_dias": 15, "temas": [70, 58], "paginas_max": 3, "palavras": "tribut|imposto|icms|iss|cbs|ibs|pis|cofins|reforma tribut|simples|mei|trabalh|clt|emprego|fgts|inss|previd|salario|folha"}'::jsonb, 'federal', 12),
  ('senado-materias', 'Senado Federal — Matérias (tributário/trabalhista)', 'Senado Federal', 'federal', false, 'api_legislativo', 'https://legis.senado.leg.br/dadosabertos/processo', '{"casa": "senado", "janela_dias": 15, "paginas_max": 1, "palavras": "tribut|imposto|icms|iss|cbs|ibs|pis|cofins|reforma tribut|simples|mei|trabalh|clt|emprego|fgts|inss|previd|salario|folha"}'::jsonb, 'federal', 12)
on conflict (slug) do nothing;

commit;
