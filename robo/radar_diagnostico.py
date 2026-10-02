"""Radar Artecon — diagnóstico das fontes (NÃO usa banco nem chaves).

Baixa cada fonte de radar_fontes.json, tenta reconhecer os itens, baixa o
texto do primeiro item e grava tudo em ./diagnostico/ (páginas originais +
relatorio.json + relatorio.md). Serve para validar as fontes reais antes de
ligar a coleta e para reajustar a configuração quando um site mudar.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

from radar_coletores import listar_paginas
from radar_util import VERSAO, ErroDownload, baixar, extrair_texto

AQUI = Path(__file__).resolve().parent


def diagnosticar(fonte: dict, pasta: Path, sessao: requests.Session) -> dict:
    slug = fonte["slug"]
    config = fonte.get("config") or {}
    r = {"fonte": slug, "url": fonte["url"], "http": None, "bytes": 0, "brutos": 0, "na_janela": 0,
         "amostra": [], "texto_primeiro_item": 0, "inicio_texto": "", "veredito": "FALHA", "erro": None}
    try:
        paginas = []

        def baixar_e_guardar(url):
            status, conteudo = baixar(url, sessao)
            paginas.append(conteudo)
            sufixo = "" if len(paginas) == 1 else f"-p{len(paginas)}"
            (pasta / f"{slug}-lista{sufixo}.txt").write_text(conteudo, encoding="utf-8")
            return status, conteudo

        listagem, r["http"] = listar_paginas(baixar_e_guardar, fonte)
        r["bytes"] = sum(len(c.encode("utf-8")) for c in paginas)
        r["brutos"], r["na_janela"] = listagem.brutos, len(listagem.itens)
        r["amostra"] = [{"titulo": i.titulo, "data": i.data.isoformat() if i.data else None, "url": i.url}
                        for i in listagem.itens[:5]]
        if listagem.itens and config.get("sem_pagina_de_texto"):
            r["texto_primeiro_item"] = len(listagem.itens[0].texto_da_listagem or "")
            r["inicio_texto"] = (listagem.itens[0].texto_da_listagem or "")[:300]
            for extra in config.get("diagnostico_urls", []):      # páginas guardadas só para estudo
                try:
                    _, html = baixar(extra, sessao, tentativas=1)
                    (pasta / f"{slug}-extra{config['diagnostico_urls'].index(extra) + 1}.txt").write_text(html, encoding="utf-8")
                except ErroDownload:
                    pass
        elif listagem.itens:
            primeiro = listagem.itens[0]
            _, html = baixar(primeiro.url_texto or primeiro.url, sessao, tentativas=2)
            (pasta / f"{slug}-item.txt").write_text(html, encoding="utf-8")
            texto = extrair_texto(html, config.get("seletor_texto"))
            r["texto_primeiro_item"] = len(texto)
            r["inicio_texto"] = texto[:300]
        if r["brutos"] == 0:
            r["veredito"] = "REVISAR — nenhum item reconhecido"
        elif r["na_janela"] and r["texto_primeiro_item"] < (40 if config.get("sem_pagina_de_texto") else 200):
            r["veredito"] = "REVISAR — lista ok, texto do item não extraído"
        elif any(i["data"] is None for i in r["amostra"]):
            r["veredito"] = "OK (com itens sem data)"
        else:
            r["veredito"] = "OK"
    except ErroDownload as e:
        r["http"] = e.http_status or r["http"]
        r["erro"] = str(e)
    except Exception as e:
        r["erro"] = f"{type(e).__name__}: {e}"
        r["veredito"] = "REVISAR — erro ao ler a página"
    return r


def relatorio_md(resultados: list[dict]) -> str:
    linhas = [f"## Radar Artecon — diagnóstico das fontes (robô v{VERSAO})", "",
              "| Fonte | HTTP | Reconhecidos | Na janela | Texto do 1º item | Veredito |",
              "|---|---:|---:|---:|---:|---|"]
    for r in resultados:
        linhas.append(f"| {r['fonte']} | {r['http'] or '—'} | {r['brutos']} | {r['na_janela']} | "
                      f"{r['texto_primeiro_item']} | {r['veredito']}{' — ' + r['erro'] if r['erro'] else ''} |")
    for r in resultados:
        linhas += ["", f"### {r['fonte']}"]
        for a in r["amostra"]:
            linhas.append(f"- {a['data'] or 'sem data'} — {a['titulo']}  \n  {a['url']}")
        if r["inicio_texto"]:
            linhas.append(f"\nInício do texto extraído: _{r['inicio_texto']}_")
    return "\n".join(linhas)


def main() -> int:
    fontes = json.loads((AQUI / "radar_fontes.json").read_text(encoding="utf-8"))
    pasta = Path("diagnostico")
    pasta.mkdir(exist_ok=True)
    sessao = requests.Session()
    resultados = []
    for fonte in fontes:
        print(f"→ {fonte['slug']}")
        r = diagnosticar(fonte, pasta, sessao)
        print(f"  {r['veredito']} (HTTP {r['http']}, {r['brutos']} reconhecidos, {r['na_janela']} na janela)")
        resultados.append(r)
    (pasta / "relatorio.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    texto = relatorio_md(resultados)
    (pasta / "relatorio.md").write_text(texto, encoding="utf-8")
    destino = os.environ.get("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(texto + "\n")
    print("\n" + texto)
    return 0   # o diagnóstico informa; quem decide é quem lê o relatório


if __name__ == "__main__":
    sys.exit(main())
