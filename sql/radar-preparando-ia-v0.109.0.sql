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

-- Marcar/desmarcar o aviso "⏳ Preparando com IA" é só da tela: não é edição do assunto nem decisão de ninguém.
-- Sem isto, cada preparo bumparia atualizado_em (o item saltaria na lista) e escreveria 2 linhas na trilha (Histórico).
-- Os dois gatilhos abaixo passam a ignorar a coluna preparando_ia_em. (create or replace: só troca o corpo da função.)
create or replace function public.radar_fn_atualizado_em() returns trigger
language plpgsql set search_path = public as $$
begin
  if tg_table_name = 'radar_conteudos'
     and (to_jsonb(new) - array['fora_do_site','kit_ia','conferencia']) = (to_jsonb(old) - array['fora_do_site','kit_ia','conferencia']) then
    new.atualizado_em := old.atualizado_em;
    return new;
  end if;
  if tg_table_name = 'radar_pauta_pecas' and (to_jsonb(new) - 'ia') = (to_jsonb(old) - 'ia') then
    new.atualizado_em := old.atualizado_em;
    return new;
  end if;
  -- v0.109.0: só o aviso "⏳ Preparando com IA" mudou → a data do assunto não muda
  if tg_table_name = 'radar_assuntos' and (to_jsonb(new) - 'preparando_ia_em') = (to_jsonb(old) - 'preparando_ia_em') then
    new.atualizado_em := old.atualizado_em;
    return new;
  end if;
  new.atualizado_em := now();
  return new;
end $$;

create or replace function public.radar_fn_auditar() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_reg jsonb;
  v_tira text[] := case tg_table_name
                     when 'radar_redes_envios' then array['imagem']
                     when 'radar_pauta_pecas'  then array['ia','assunto','objetivo','observacao','quem_aparece']
                     when 'radar_pessoas'      then array['nome','nome_na_peca','crc','area','cpf']   -- v0.46.0: + cpf
                     when 'radar_videos'       then array['relatorio','fala_roteiro','ajustes','cartela_linhas']
                     else array[]::text[] end;
begin
  if tg_op = 'DELETE' then v_reg := to_jsonb(old); else v_reg := to_jsonb(new); end if;
  -- v0.109.0: preparando_ia_em (o aviso "⏳ Preparando com IA") é marca de tela, não decisão de ninguém — fora da trilha
  if tg_op = 'UPDATE'
     and (to_jsonb(old) - array['ultimo_sucesso_em','ultima_falha_em','ultimo_erro','falhas_consecutivas','atualizado_em','preparando_ia_em'])
       = (to_jsonb(new) - array['ultimo_sucesso_em','ultima_falha_em','ultimo_erro','falhas_consecutivas','atualizado_em','preparando_ia_em']) then
    return new;
  end if;
  if tg_op = 'UPDATE' and tg_table_name in ('radar_redes_envios','radar_pauta_pecas','radar_pessoas','radar_videos')
     and (to_jsonb(old) - v_tira - array['atualizado_em','disparos','disparado_em','pego_em','tentativas','rodada','palavras_tentativa','fila_em','reservas','retentar_em'])
       = (to_jsonb(new) - v_tira - array['atualizado_em','disparos','disparado_em','pego_em','tentativas','rodada','palavras_tentativa','fila_em','reservas','retentar_em']) then
    return new;
  end if;
  insert into public.radar_auditoria (tabela, registro_id, acao, usuario, antes, depois)
  values (tg_table_name,
          coalesce(v_reg->>'id', v_reg->>'user_id', v_reg->>'slug', v_reg->>'chave', '?'),
          tg_op, auth.uid(),
          case when tg_op <> 'INSERT' then to_jsonb(old) - v_tira end,
          case when tg_op <> 'DELETE' then to_jsonb(new) - v_tira end);
  if tg_op = 'DELETE' then return old; end if;
  return new;
end $$;
