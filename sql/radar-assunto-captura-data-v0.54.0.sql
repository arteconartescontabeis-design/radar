-- Radar Artecon — v0.54.0
-- Acrescenta a coluna "capturado_em" (a data em que a informação foi capturada da fonte)
-- na consulta radar_v_assuntos, usada pela lista de Assuntos (Notícias → Assuntos).
--
-- É só uma consulta (view): NÃO cria tabela, NÃO apaga nada, pode rodar de novo quando quiser.
-- Rode no Supabase → SQL Editor. Depois publique o index.html com os demais .js e aperte Ctrl+F5.
--
-- A data mostrada é a da PRIMEIRA captura do assunto (quando o tema entrou no radar). A coluna "Fonte"
-- da tela já existia na consulta (o órgão de onde a informação veio) e não precisa de nada aqui.

create or replace view public.radar_v_assuntos
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
          join public.radar_fontes f on f.id = c.fonte_id where ac.assunto_id = a.id) as orgaos,
       -- v0.54.0: a data em que a informação foi capturada da fonte (a primeira captura do assunto)
       (select min(c.capturado_em) from public.radar_assunto_capturas ac
          join public.radar_capturas c on c.id = ac.captura_id where ac.assunto_id = a.id) as capturado_em
from public.radar_assuntos a;
