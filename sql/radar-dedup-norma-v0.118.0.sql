-- Radar Artecon — v0.118.0: dedup também pela NORMA (não só pelo título igual)
-- A mesma norma vinda de duas fontes OFICIAIS com títulos diferentes (ex.: "Portaria RFB nº 754, de 03/11/2026" no
-- rfb-normas e "PORTARIA RFB Nº 754, DE 3 DE NOVEMBRO DE 2026" no DOU) vira repetição da primeira — casada pelo
-- base_legal.ato (o ato que a captura É). O "ato" só é preenchido quando o TÍTULO é a norma (a notícia que apenas
-- CITA a norma tem ato nulo), então isto NÃO funde comentários diferentes sobre a mesma lei.
-- Pode rodar de novo (idempotente): troca a função e agrupa as duplicatas de norma que ainda estão soltas na fila.

create or replace function public.radar_fn_captura_origem() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  -- boletim que chega depois da publicação oficial do mesmo fato (mesmo título): entra como repetição dela
  if tg_op = 'INSERT' and new.duplicata_de is null
     and not coalesce((select f.oficial from public.radar_fontes f where f.id = new.fonte_id), false) then
    select c.id into new.duplicata_de
      from public.radar_capturas c join public.radar_fontes f on f.id = c.fonte_id
     where f.oficial and c.duplicata_de is null and c.hash_titulo = new.hash_titulo and c.fonte_id <> new.fonte_id
     order by c.id limit 1;
  end if;
  -- v0.118.0: casa também pela NORMA (o ato que a captura É), não só pelo título igual
  if tg_op = 'INSERT' and new.duplicata_de is null
     and nullif(new.base_legal->>'ato', '') is not null
     and coalesce((select f.oficial from public.radar_fontes f where f.id = new.fonte_id), false) then
    select c.id into new.duplicata_de
      from public.radar_capturas c join public.radar_fontes f on f.id = c.fonte_id
     where f.oficial and c.duplicata_de is null and c.fonte_id <> new.fonte_id
       and nullif(c.base_legal->>'ato', '') = new.base_legal->>'ato'
     order by c.id limit 1;
  end if;
  -- (se o boletim já virou assunto, o vínculo fica: a oficial entra nesse assunto ou mostra o aviso "parece o mesmo fato")
  if new.duplicata_de is not null
     and (select f.oficial from public.radar_fontes f where f.id = new.fonte_id)
     and not coalesce((select f.oficial from public.radar_capturas c join public.radar_fontes f on f.id = c.fonte_id
                        where c.id = new.duplicata_de), false)
     and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = new.duplicata_de) then
    new.duplicata_de := null;
  end if;
  return new;
end $$;

-- backfill: agrupa as normas oficiais duplicadas que já estão na fila (nenhuma em assunto), a mais antiga como principal
with grupos as (
  select c.id,
    first_value(c.id) over (partition by nullif(c.base_legal->>'ato','') order by c.id) as raiz
  from public.radar_capturas c
  join public.radar_fontes f on f.id = c.fonte_id
  where f.oficial and c.duplicata_de is null and nullif(c.base_legal->>'ato','') is not null
    and not exists (select 1 from public.radar_assunto_capturas ac where ac.captura_id = c.id)
)
update public.radar_capturas t set duplicata_de = g.raiz
from grupos g where t.id = g.id and g.id <> g.raiz;
