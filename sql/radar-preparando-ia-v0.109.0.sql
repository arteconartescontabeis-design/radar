-- sql/radar-preparando-ia-v0.109.0.sql — "⏳ Preparando com IA" guardado no banco.
-- Enquanto a IA prepara uma notícia (o botão "Preparar com IA", ou o preparo em lote),
-- a coluna radar_assuntos.preparando_ia_em guarda o instante em que começou. A lista de
-- Assuntos mostra o selo "⏳ Preparando com IA" olhando essa coluna — assim o aviso não
-- some ao trocar de aba, recarregar ou abrir em outro aparelho, e volta sozinho quando
-- termina (a tela limpa a coluna no fim, com sucesso ou com erro) ou quando o carimbo
-- envelhece (a tela ignora carimbos com mais de 10 minutos).
-- Pode rodar de novo (idempotente): nenhuma tabela nova, nada é apagado.

alter table public.radar_assuntos add column if not exists preparando_ia_em timestamptz;

-- A view da lista de Assuntos passa a entregar a nova coluna (recriada para incluí-la).
drop view if exists public.radar_v_assuntos;
create view public.radar_v_assuntos
with (security_invoker = true) as
-- colunas listadas (não a.*): coluna nova em radar_assuntos (ex.: a liberação da v0.12.0) não muda esta lista
select a.id, a.titulo, a.categoria, a.subcategoria, a.abrangencia, a.relevancia, a.situacao_confirmacao, a.status,
       a.resumo, a.publico_afetado, a.responsavel, a.criado_em, a.atualizado_em, a.preparando_ia_em,
       (select count(*) from public.radar_evidencias e where e.assunto_id = a.id) as evidencias,
       (select count(*) from public.radar_evidencias e where e.assunto_id = a.id and e.trecho_conferido) as evidencias_conferidas,
       (select count(*) from public.radar_conteudos c where c.assunto_id = a.id) as conteudos,
       (select count(*) from public.radar_conteudos c where c.assunto_id = a.id and c.status = 'em_revisao') as em_revisao,
       (select string_agg(distinct f.orgao, ' · ') from public.radar_assunto_capturas ac
          join public.radar_capturas c on c.id = ac.captura_id
          join public.radar_fontes f on f.id = c.fonte_id where ac.assunto_id = a.id) as orgaos,
       -- v0.54.0: a data em que a informação foi capturada da fonte (a primeira captura do assunto), para a lista de Assuntos
       (select min(c.capturado_em) from public.radar_assunto_capturas ac
          join public.radar_capturas c on c.id = ac.captura_id where ac.assunto_id = a.id) as capturado_em
from public.radar_assuntos a;

revoke all on public.radar_v_assuntos from public, anon, authenticated, service_role;
grant select on public.radar_v_assuntos to authenticated, service_role;
