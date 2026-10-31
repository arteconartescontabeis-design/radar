-- Radar v0.60.0 — Vídeo de venda: a biblioteca de roteiros (projeto "vídeos de venda dos serviços").
-- Incremental idempotente sobre o banco v0.50.0 (com os incrementais anteriores): create or replace /
-- if not exists; nada é apagado; pode rodar de novo.

-- ---------------------------------------------------------------------
-- Vídeo de VENDA (v0.60.0): a biblioteca de roteiros dos serviços.
-- O roteiro é escrito pela IA (radar-ia, ação "roteiro_venda"), revisado pela equipe e guardado aqui;
-- a gravação (teleprompter) e a correção seguem pelo fluxo do vídeo AVULSO, com as travas de sempre.
-- ---------------------------------------------------------------------
create table if not exists public.radar_venda_roteiros (
  id         bigint generated always as identity primary key,
  servico    text not null check (length(servico) between 3 and 80),
  titulo     text not null check (length(titulo) between 3 and 120),
  roteiro    text not null check (length(roteiro) between 80 and 4000),
  criado_em  timestamptz not null default now(),
  criado_por uuid not null default auth.uid()
);

-- Gravar (editor e administrador): a tela chama DEPOIS que a pessoa revisa o texto da IA.
create or replace function public.radar_venda_gravar(p_servico text, p_titulo text, p_roteiro text) returns bigint
language plpgsql security definer set search_path = public as $$
declare
  v_servico text := trim(coalesce(p_servico, ''));
  v_titulo  text := trim(coalesce(p_titulo, ''));
  v_roteiro text := trim(coalesce(p_roteiro, ''));
  v_id      bigint;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') not in ('admin','editor') then
    raise exception 'RADAR330: só o editor ou o administrador mexe na biblioteca de vídeos de venda' using errcode = 'P0001';
  end if;
  if length(v_servico) not between 3 and 80 then
    raise exception 'RADAR331: diga o serviço do vídeo (de 3 a 80 caracteres)' using errcode = 'P0001';
  end if;
  if length(v_titulo) not between 3 and 120 then
    raise exception 'RADAR331: dê um título ao roteiro (de 3 a 120 caracteres)' using errcode = 'P0001';
  end if;
  if length(v_roteiro) not between 80 and 4000 then
    raise exception 'RADAR331: o roteiro deve ter de 80 a 4.000 caracteres' using errcode = 'P0001';
  end if;
  if (v_servico || v_titulo) ~ '[<>{}\\]' or (v_servico || v_titulo) ~ '[[:cntrl:]]' then
    raise exception 'RADAR331: o serviço e o título não levam < > { } nem \' using errcode = 'P0001';
  end if;
  if (select count(*) from public.radar_venda_roteiros) >= 60 then
    raise exception 'RADAR332: a biblioteca está cheia (60 roteiros): apague os que não usa mais' using errcode = 'P0001';
  end if;
  insert into public.radar_venda_roteiros (servico, titulo, roteiro)
  values (v_servico, v_titulo, v_roteiro) returning id into v_id;
  return v_id;
end $$;

-- Apagar (só o administrador).
create or replace function public.radar_venda_apagar(p_id bigint) returns void
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR333: só o administrador apaga um roteiro da biblioteca' using errcode = 'P0001';
  end if;
  delete from public.radar_venda_roteiros where id = p_id;
  if not found then
    raise exception 'RADAR333: roteiro não encontrado (atualize a página)' using errcode = 'P0001';
  end if;
end $$;

-- Segurança: como as demais tabelas do Radar — nada ao anon/público; a leitura é só do editor/admin (RLS);
-- a escrita é só pelas funções. A sequência da identity também é revogada.
alter table public.radar_venda_roteiros enable row level security;
revoke all on public.radar_venda_roteiros from public, anon, authenticated, service_role;
revoke all on sequence public.radar_venda_roteiros_id_seq from public, anon, authenticated, service_role;
drop policy if exists radar_venda_roteiros_sel on public.radar_venda_roteiros;
create policy radar_venda_roteiros_sel on public.radar_venda_roteiros for select
  using (coalesce(public.radar_papel(), '') in ('admin','editor'));
revoke all on function public.radar_venda_gravar(text, text, text) from public, anon, authenticated, service_role;
revoke all on function public.radar_venda_apagar(bigint) from public, anon, authenticated, service_role;
grant select on public.radar_venda_roteiros to authenticated;
grant execute on function public.radar_venda_gravar(text, text, text) to authenticated;
grant execute on function public.radar_venda_apagar(bigint) to authenticated;
