-- =====================================================================
-- Radar Artecon — fontes novas (outubro/2026)
-- Rode UMA vez no Supabase (SQL Editor) depois da v0.7.1. Pode rodar de novo:
-- fonte que já existe (mesmo identificador) não é alterada.
--
-- As quatro fontes de sites entram DESLIGADAS (ativo = false) e "a validar":
-- ligue cada uma na aba Fontes → Configurar → Fonte ativa, depois de rodar o
-- diagnóstico. Só o DOU é fonte oficial; as demais são portais e consultorias
-- (servem de alerta e pauta, não de fundamentação).
--
-- A fonte "ITC Consultoria (e-mail)" não é visitada pelo robô (config.origem = email):
-- as capturas dela são gravadas pela rotina diária que lê o boletim no e-mail.
-- =====================================================================

insert into public.radar_fontes (slug, nome, orgao, abrangencia, oficial, ativo, tipo_coletor, url, config, categoria_padrao, frequencia_horas)
select v.slug, v.nome, v.orgao, v.abrangencia, v.oficial, v.ativo, v.tipo_coletor, v.url, v.config,
       (select c.slug from public.radar_categorias c where c.slug = v.categoria),   -- categoria apagada: fica sem
       v.frequencia_horas
from (values
  ('dou-destaques', 'Diário Oficial da União — Destaques', 'Imprensa Nacional', 'federal', true, false, 'html_links',
   'https://www.in.gov.br/web/guest/servicos/diario-oficial-da-uniao/destaques-do-diario-oficial-da-uniao',
   '{"janela_dias": 10, "padrao_url": "/web/dou/-/[^?#]+-\\d{6,}$", "seletor_texto": ".texto-dou, #materia, article, main", "max_itens": 60}'::jsonb,
   'federal', 12),
  ('contabeis-noticias', 'Contábeis — Notícias', 'Portal Contábeis', 'geral', false, false, 'rss',
   'https://www.contabeis.com.br/rss/noticias/',
   '{"janela_dias": 10, "texto_do_feed": true, "seletor_texto": "article, main"}'::jsonb,
   null, 12),
  ('econet-blog', 'Econet Editora — Blog', 'Econet Editora', 'geral', false, false, 'rss',
   'https://blog.econeteditora.com.br/feed/',
   '{"janela_dias": 15, "texto_do_feed": true, "seletor_texto": "article, .entry-content, main"}'::jsonb,
   null, 24),
  ('portalcontabilsc-noticias', 'Portal Contábil SC — Notícias', 'Portal Contábil SC', 'estadual_sc', false, false, 'rss',
   'https://portalcontabilsc.com.br/categoria/noticias/feed/',
   '{"janela_dias": 10, "texto_do_feed": true, "seletor_texto": "article, .entry-content, main", "tempo_max_segundos": 240}'::jsonb,
   'santa-catarina', 24),
  ('itc-email', 'ITC Consultoria — boletim por e-mail', 'ITC Consultoria', 'geral', false, true, 'rss',
   'https://www.itcnet.com.br/',
   '{"origem": "email", "remetente": "itc@itcnet.com.br"}'::jsonb,
   null, 24)
) as v (slug, nome, orgao, abrangencia, oficial, ativo, tipo_coletor, url, config, categoria, frequencia_horas)
on conflict (slug) do nothing;


-- Recebe as matérias de um boletim lido no e-mail (usada pela rotina diária da ITC).
-- p_itens: [{"titulo": "...", "data": "AAAA-MM-DD", "area": "...", "texto": "...", "assunto_email": "..."}, ...]
-- Cada matéria vira uma captura da fonte; a mesma manchete em dois boletins (ITCNET Mail e
-- Legislação & Tribunais) entra uma vez só. Devolve quantas entraram e quantas já existiam.
create or replace function public.radar_receber_email(p_fonte text, p_itens jsonb) returns jsonb
language plpgsql set search_path = public as $$
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
             'áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ', 'aaaaaeeeeiiiiooooouuuucnAAAAAEEEEIIIIOOOOOUUUUCN')),
             '[^a-z0-9 ]+', ' ', 'g'), '\s+', ' ', 'g')), 'UTF8')), 'hex') as h
      from jsonb_to_recordset(p_itens) as i(titulo text, data date, area text, texto text, assunto_email text)
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
revoke all on function public.radar_receber_email(text, jsonb) from public, anon, authenticated;

select slug, nome, ativo, oficial from public.radar_fontes
 where slug in ('dou-destaques','contabeis-noticias','econet-blog','portalcontabilsc-noticias','itc-email')
 order by id;
