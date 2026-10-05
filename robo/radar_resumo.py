"""Radar Artecon — resumo semanal por e-mail (v0.8.0).

Toda segunda-feira abre UM aviso (issue) no GitHub com o que entrou de mais relevante nos últimos 7 dias,
agrupado por tema, e fecha o resumo da semana anterior. O GitHub manda o e-mail. É a única mensagem
semanal do Radar: as notícias continuam só na tela, sem um aviso por item.

O repositório é público: o resumo lista só o que veio de sites públicos. As matérias do boletim
da ITC (fonte alimentada por e-mail) aparecem apenas como contagem.

Uso (no workflow semanal):  python radar_resumo.py
Variáveis: SUPABASE_URL, SUPABASE_SERVICE_KEY, GITHUB_TOKEN e GITHUB_REPOSITORY.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import requests

from radar_alertas import GitHub
from radar_banco import Banco, ErroBanco
from radar_util import BRASILIA

PREFIXO_RESUMO = "Radar: resumo da semana — "
MAX_ITENS = 25
NOTA_MINIMA = 7          # nota da IA que basta para entrar, mesmo sem relevância "alta" pelas palavras
DIAS_SEM_NOVIDADE = 5    # fonte ativa sem nada novo há mais que isso aparece no resumo (site mudou? boletim parou?)


def periodo(agora: datetime) -> tuple[datetime, datetime]:
    fim = agora.astimezone(BRASILIA).replace(hour=0, minute=0, second=0, microsecond=0)
    return fim - timedelta(days=7), fim


def titulo_resumo(inicio: datetime, fim: datetime) -> str:
    return f"{PREFIXO_RESUMO}{inicio:%d/%m} a {(fim - timedelta(days=1)):%d/%m/%Y}"


def selecionar(capturas: list[dict]) -> tuple[list[dict], int]:
    """(itens dos sites públicos que entram no resumo, quantos relevantes vieram do boletim por e-mail)."""
    publicos, do_email = [], 0
    for c in capturas:
        if c.get("duplicata_de"):
            continue
        if not (c.get("relevancia") == "alta" or (c.get("ia_nota") or 0) >= NOTA_MINIMA):
            continue
        fonte = c.get("radar_fontes") or {}
        if (fonte.get("config") or {}).get("origem") == "email":
            do_email += 1
        else:
            publicos.append(c)
    publicos.sort(key=lambda c: (-(c.get("ia_nota") or 0), c.get("relevancia") != "alta", c.get("titulo") or ""))
    return publicos[:MAX_ITENS], do_email


def corpo_resumo(itens: list[dict], do_email: int, numeros: dict, inicio: datetime, fim: datetime,
                 sem_novidade: list[dict] | None = None) -> str:
    linhas = [f"Resumo do Radar de **{inicio:%d/%m} a {(fim - timedelta(days=1)):%d/%m/%Y}**.", "",
              f"- Capturas novas na semana: **{numeros.get('capturas', 0)}**",
              f"- Conteúdos aprovados: **{numeros.get('aprovados', 0)}** · publicações registradas no site: **{numeros.get('publicados', 0)}**", ""]
    if not itens and not do_email:
        linhas.append("Nenhuma notícia de relevância alta nesta semana.")
    grupos: dict[str, list[dict]] = {}
    for c in itens:
        grupos.setdefault((c.get("ia_tema") or "").strip() or "Outros", []).append(c)
    for tema in sorted(grupos, key=lambda t: (t == "Outros", -len(grupos[t]), t)):
        linhas += [f"### {tema}", ""]
        for c in grupos[tema]:
            fonte = (c.get("radar_fontes") or {})
            nota = f" · nota {c['ia_nota']}" if c.get("ia_nota") is not None else ""
            linhas.append(f"- [{c['titulo']}]({c['url']}) — {fonte.get('nome') or 'fonte'}"
                          f"{'' if fonte.get('oficial', True) else ' (não oficial)'}{nota}")
        linhas.append("")
    if do_email:
        linhas += [f"Mais **{do_email}** matéria(s) relevante(s) do boletim da ITC — veja no Radar (o conteúdo do boletim "
                   "não é reproduzido aqui).", ""]
    if sem_novidade:
        linhas += [f"### Fontes sem notícia nova há mais de {DIAS_SEM_NOVIDADE} dias", ""]
        for f in sem_novidade:
            quando = str(f.get("ultima_captura_em") or "")[:10]
            linhas.append(f"- {f.get('nome') or f['slug']} — " + (f"última em {quando[8:10]}/{quando[5:7]}/{quando[:4]}"
                                                                   if quando else "nunca trouxe nada"))
        linhas += ["", "Pode ser só uma semana fraca. Se continuar, rode o diagnóstico da fonte "
                   "(Actions → \"Radar — diagnóstico das fontes\"); no boletim por e-mail, confira a rotina diária.", ""]
    linhas.append("Para abrir um assunto, use a triagem do Radar. Este aviso é fechado sozinho quando sair o próximo resumo.")
    return "\n".join(linhas)


def executar(banco: Banco, github: GitHub, agora: datetime | None = None) -> list[str]:
    inicio, fim = periodo(agora or datetime.now(timezone.utc))
    capturas = banco.capturas_entre(inicio, fim)
    itens, do_email = selecionar(capturas)
    numeros = {"capturas": len(capturas), **banco.numeros_da_semana(inicio, fim)}
    sem_novidade = banco.fontes_sem_novidade(fim - timedelta(days=DIAS_SEM_NOVIDADE))
    titulo = titulo_resumo(inicio, fim)
    abertos = github.avisos_abertos(PREFIXO_RESUMO)
    if titulo in abertos:
        return [f"resumo já aberto (#{abertos[titulo]})"]
    feito = [f"resumo #{github.abrir_aviso(titulo, corpo_resumo(itens, do_email, numeros, inicio, fim, sem_novidade))} aberto: "
             f"{len(itens)} notícia(s), {do_email} do boletim por e-mail"]
    for t, numero in abertos.items():
        github.fechar(numero, "Substituído pelo resumo desta semana.")
        feito.append(f"resumo anterior #{numero} fechado")
    return feito


def main() -> int:
    url, chave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (url and chave and token and repo):
        print("Resumo semanal: sem as variáveis necessárias; nada a fazer.")
        return 0
    try:
        feito = executar(Banco(url, chave), GitHub(repo, token))
    except (ErroBanco, RuntimeError, requests.RequestException) as e:
        print(f"! resumo semanal não foi aberto: {e}", file=sys.stderr)
        return 1
    print("Resumo semanal: " + "; ".join(feito))
    return 0


if __name__ == "__main__":
    sys.exit(main())
