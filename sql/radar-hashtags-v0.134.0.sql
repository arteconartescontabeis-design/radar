-- Radar Artecon — v0.134.0 (#8): conjunto fixo de hashtags por canal (Instagram, Facebook e site/blog).
--
-- O que faz: troca o campo "hashtags" da configuração "pauta" (antes uma lista única de até 3, igual para todos os canais) pelo
-- formato por canal, já com um conjunto pesquisado para contabilidade em Santa Catarina. As demais chaves de "pauta"
-- (agenda_ligada, hora_padrao, janela_horas, fatos_fixos, cronograma_inicio…) ficam como estão.
--
-- Não mexe em NENHUMA tabela nem função (só no dado da configuração). Pode rodar de novo SEM perder ajustes: só troca quando "hashtags"
-- ainda é o formato antigo (uma lista) ou não existe; se você já tiver o formato por canal (um objeto), o script NÃO sobrescreve.
-- A IA continua sugerindo as hashtags do TEMA de cada notícia por cima dessas fixas. Ajustar depois: Configurações → Pauta → "hashtags".
--
-- Observação: no Instagram cabem mais (até 30); no Facebook, poucas (use 2 a 3 por post); "site" são palavras-chave do blog (sem #).
-- 8 a 15 hashtags bem escolhidas rendem mais que 30, e repetir sempre o mesmo bloco gigante parece automação — por isso o conjunto
-- fixo é a BASE e a IA acrescenta as do tema. Edite a lista conforme o que funcionar melhor para a Artecon.

update public.radar_config
   set valor = valor || jsonb_build_object('hashtags', jsonb_build_object(
         'instagram', jsonb_build_array(
           '#contabilidade', '#contador', '#escritoriocontabil', '#contabil', '#contabilidadedigital',
           '#empreendedorismo', '#empreendedor', '#gestaofinanceira', '#impostoderenda', '#simplesnacional',
           '#mei', '#reformatributaria', '#esocial', '#aberturadeempresa', '#pequenasempresas',
           '#palhoca', '#saojose', '#florianopolis', '#santacatarina', '#contabilidadesc'),
         'facebook', jsonb_build_array(
           '#contabilidade', '#contador', '#simplesnacional', '#santacatarina', '#palhoca'),
         'site', jsonb_build_array(
           'Simples Nacional', 'MEI', 'Reforma Tributária', 'CBS e IBS', 'eSocial', 'Abertura de empresa')))
 where chave = 'pauta'
   and jsonb_typeof(valor->'hashtags') is distinct from 'object';   -- só o formato antigo (lista) ou ausente; não mexe num objeto por canal já ajustado

-- Se, por algum motivo, a configuração "pauta" ainda não existir, cria com o mínimo + as hashtags.
insert into public.radar_config (chave, valor)
select 'pauta', '{"agenda_ligada": true, "hora_padrao": "09:30", "janela_horas": 6, "hashtags": {"instagram": ["#contabilidade", "#contador", "#escritoriocontabil", "#contabil", "#contabilidadedigital", "#empreendedorismo", "#empreendedor", "#gestaofinanceira", "#impostoderenda", "#simplesnacional", "#mei", "#reformatributaria", "#esocial", "#aberturadeempresa", "#pequenasempresas", "#palhoca", "#saojose", "#florianopolis", "#santacatarina", "#contabilidadesc"], "facebook": ["#contabilidade", "#contador", "#simplesnacional", "#santacatarina", "#palhoca"], "site": ["Simples Nacional", "MEI", "Reforma Tributária", "CBS e IBS", "eSocial", "Abertura de empresa"]}}'::jsonb
where not exists (select 1 from public.radar_config where chave = 'pauta');
