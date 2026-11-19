-- Radar Artecon — fontes oficiais federais para INCLUSÃO MANUAL de texto (Planalto e Diário Oficial)
--
-- Cadastra duas fontes oficiais que faltavam para "Incluir texto oficial" aceitar links de:
--   * Planalto (planalto.gov.br) — leis, medidas provisórias e decretos
--   * Diário Oficial da União / Imprensa Nacional (in.gov.br)
--
-- Elas entram DESLIGADAS (ativo = false): servem só para colar o texto à mão na tela do assunto
-- (o robô NÃO as varre — ele só lê fontes ativas). Aparecem no seletor "Fonte" do formulário, e o
-- endereço colado (do mesmo site) passa a ser aceito.
--
-- Não faz parte do setup padrão (as fontes semeadas são todas ativas/varridas); é um acréscimo para
-- este Radar. Pode rodar quantas vezes quiser (on conflict do nothing).

insert into public.radar_fontes
  (slug, nome, orgao, abrangencia, oficial, tipo_coletor, url, config, categoria_padrao, frequencia_horas, ativo, validada)
values
  ('planalto-manual', 'Planalto — Leis, MPs e Decretos (inclusão manual)', 'Presidência da República',
   'federal', true, 'html_links', 'https://www.planalto.gov.br/', '{"somente_manual": true}'::jsonb, null, 24, false, false),
  ('dou-manual', 'Diário Oficial da União — Imprensa Nacional (inclusão manual)', 'Imprensa Nacional',
   'federal', true, 'html_links', 'https://www.in.gov.br/', '{"somente_manual": true}'::jsonb, null, 24, false, false)
on conflict (slug) do nothing;
