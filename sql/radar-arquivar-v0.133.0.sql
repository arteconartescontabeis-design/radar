-- Radar Artecon — migração v0.133.0: arquivar (ocultar da lista, reversível, só o administrador)
--
-- Acrescenta a coluna arquivado_em (nulo = ativo; com data = arquivado) em radar_capturas, radar_normas,
-- radar_assuntos e radar_conteudos, e a função radar_arquivar(tabela, id, arquivar) que o administrador usa para
-- arquivar e desarquivar. NADA é apagado — o item só sai da lista normal e volta pelo filtro "Arquivados".
-- Pode rodar quantas vezes quiser (idempotente). O mesmo conteúdo está no sql/radar-setup-v0.50.0.sql.

alter table public.radar_capturas  add column if not exists arquivado_em timestamptz;
alter table public.radar_normas     add column if not exists arquivado_em timestamptz;
alter table public.radar_assuntos   add column if not exists arquivado_em timestamptz;
alter table public.radar_conteudos  add column if not exists arquivado_em timestamptz;

-- Só o administrador arquiva/desarquiva; a tabela precisa ser uma das quatro da lista branca (sem injeção: %I + USING).
create or replace function public.radar_arquivar(p_tabela text, p_id bigint, p_arquivar boolean default true)
returns void language plpgsql security definer set search_path = public as $$
begin
  if coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR385: só o administrador arquiva ou desarquiva' using errcode = '42501';
  end if;
  if p_tabela not in ('radar_capturas', 'radar_normas', 'radar_assuntos', 'radar_conteudos') then
    raise exception 'RADAR385: essa lista não pode ser arquivada' using errcode = '22023';
  end if;
  execute format('update public.%I set arquivado_em = $1 where id = $2', p_tabela)
    using (case when p_arquivar then now() end), p_id;
end $$;
revoke all on function public.radar_arquivar(text, bigint, boolean) from public, anon, authenticated, service_role;
grant execute on function public.radar_arquivar(text, bigint, boolean) to authenticated;

-- v0.133.0: as views que as listas usam passam a expor arquivado_em (e "Em alta" não mostra a arquivada).
-- create or replace (coluna nova no fim) e drop+create (radar_v_assuntos).

create or replace view public.radar_v_fila
with (security_invoker = true) as
select c.id, c.fonte_id, f.slug as fonte_slug, f.nome as fonte_nome, f.orgao, f.abrangencia,
       f.categoria_padrao, f.oficial, c.url, c.titulo, c.data_publicacao, c.resumo_fonte,
       c.capturado_em, c.versao, (c.texto is not null) as tem_texto, c.duplicata_de,
       c.relevancia, c.relevancia_pontos, c.relevancia_motivos,
       c.ia_nota, c.ia_motivo, c.ia_tema, c.ia_avaliado_em,
       (select count(*) from public.radar_capturas r where r.duplicata_de = c.id
          and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = r.id)) as repetidas,
       -- principal: é a que representa o fato na triagem. A repetição só fica escondida enquanto a origem dela
       -- também está na fila; se a origem já virou assunto (ou foi ignorada), a repetição aparece por conta própria.
       (c.duplicata_de is null
        or exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = c.duplicata_de)) as principal,
       -- nota do grupo: a maior entre a captura e as repetições dela que estão na fila
       greatest(c.ia_nota, (select max(r.ia_nota) from public.radar_capturas r where r.duplicata_de = c.id
          and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = r.id))) as nota_grupo,
       -- assunto em que a origem da repetição está (para avisar "parece o mesmo fato de …")
       -- (procura no grupo todo e prefere o assunto em andamento)
       o.id as origem_assunto_id, o.titulo || ' (' || o.status || ')' as origem_assunto,
       c.base_legal,                                   -- v0.15.0: normas citadas no texto capturado
       -- v0.15.0: a captura que não cita norma mostra a de outra captura do mesmo fato que ainda está na fila e cita
       -- (a origem, as repetições dela ou as irmãs)
       (select r.base_legal from public.radar_capturas r
         where r.id <> c.id
           and (r.duplicata_de = c.id or r.id = c.duplicata_de or (c.duplicata_de is not null and r.duplicata_de = c.duplicata_de))
           and coalesce((r.base_legal->>'total')::int, 0) > 0
           and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = r.id)
         order by (r.id = c.duplicata_de) desc, r.id limit 1) as base_legal_repeticao,
       c.arquivado_em                                  -- v0.133.0: arquivar a captura/legislação (ocultar da lista) — coluna no fim (create or replace view)
from public.radar_capturas c
join public.radar_fontes f on f.id = c.fonte_id
left join lateral (
  select a.id, a.titulo, a.status
    from public.radar_capturas g
    join public.radar_assunto_capturas ac on ac.captura_id = g.id
    join public.radar_assuntos a on a.id = ac.assunto_id
   where c.duplicata_de is not null and (g.id = c.duplicata_de or g.duplicata_de = c.duplicata_de)
   order by (a.status in ('ignorado','publicado','arquivado')), a.id
   limit 1) o on true
where not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = c.id);

create or replace view public.radar_v_em_alta
with (security_invoker = true) as
select f.*
  from public.radar_v_fila f
 where f.principal and f.relevancia <> 'baixa' and f.arquivado_em is null   -- v0.133.0: a arquivada não entra em "Em alta"
   and (f.nota_grupo is null or f.nota_grupo >= coalesce((select case when jsonb_typeof(c.valor->'nota_corte') = 'number'
                                                               then least(greatest((c.valor->>'nota_corte')::numeric, 0), 10) end
                                                      from public.radar_config c where c.chave = 'relevancia'), 6))
 order by f.nota_grupo desc nulls last, f.relevancia_pontos desc, f.capturado_em desc, f.id desc
 limit coalesce((select case when jsonb_typeof(c.valor->'quantidade') = 'number'
                             then least(greatest((c.valor->>'quantidade')::numeric, 1), 100)::int end
                   from public.radar_config c where c.chave = 'relevancia'), 10);

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
          join public.radar_capturas c on c.id = ac.captura_id where ac.assunto_id = a.id) as capturado_em,
       a.arquivado_em                                  -- v0.133.0: arquivar o assunto (ocultar da lista)
from public.radar_assuntos a;
