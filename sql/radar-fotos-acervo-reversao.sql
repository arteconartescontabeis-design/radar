-- Radar v0.63.0 — REVERSÃO do acervo de fotos da Artecon (sql/radar-fotos-acervo-v0.63.0.sql).
-- Apaga a tabela e as funções do acervo e devolve a limpeza de imagens ao texto anterior (v0.42.0).
-- ATENÇÃO: as fotos do acervo que estiverem em radar_imagens ficam sem uso e saem na faxina diária do robô
-- (as fotos originais continuam na pasta do OneDrive).

drop function if exists public.radar_foto_acervo_gravar(text, text, bigint);
drop function if exists public.radar_foto_acervo_apagar(bigint);
drop table if exists public.radar_fotos_acervo;

-- a limpeza volta ao texto da v0.42.0 (sem a exceção do acervo)
create or replace function public.radar_fn_imagem_sem_uso() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  -- v0.16.0: vale também para a ilustração guardada (ilustracao_id)
  -- v0.21.0: a foto ou a lâmina aprovada de uma peça da Pauta nunca é apagada por aqui
  -- v0.42.0: nem a lâmina de uma publicação nas redes (radar_redes_envios.artes: o carrossel da notícia)
  delete from public.radar_imagens i
   where i.id in (old.imagem_id, old.ilustracao_id)
     and (tg_op = 'DELETE' or (i.id is distinct from new.imagem_id and i.id is distinct from new.ilustracao_id))
     and not exists (select 1 from public.radar_conteudos c where c.imagem_id = i.id or c.ilustracao_id = i.id)
     and not exists (select 1 from public.radar_pauta_pecas p where i.id = any(p.fotos) or i.id = any(p.artes))
     and not exists (select 1 from public.radar_redes_envios e where i.id = any(e.artes));
  return null;
end $$;

create or replace function public.radar_limpar_imagens_sem_uso(p_horas int default 24) returns int
language plpgsql security definer set search_path = public as $$
declare v_n int;
begin
  delete from public.radar_imagens i
   where i.criado_em < now() - make_interval(hours => least(greatest(coalesce(p_horas, 24), 1), 8760))
     and not exists (select 1 from public.radar_conteudos c where c.imagem_id = i.id or c.ilustracao_id = i.id)
     and not exists (select 1 from public.radar_pauta_pecas p where i.id = any(p.fotos) or i.id = any(p.artes))
     and not exists (select 1 from public.radar_redes_envios e where i.id = any(e.artes));
  get diagnostics v_n = row_count;
  return v_n;
end $$;
