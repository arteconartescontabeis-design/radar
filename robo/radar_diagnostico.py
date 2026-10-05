"""Radar Artecon — diagnóstico das fontes (só lê; não grava nada no banco).

Com SUPABASE_URL e SUPABASE_SERVICE_KEY, confere as fontes ATIVAS do banco (inclusive as
cadastradas pela tela); sem elas, ou se o banco não responder, usa robo/radar_fontes.json.
Para cada fonte, tenta reconhecer os itens, baixa o
texto do primeiro item e grava tudo em ./diagnostico/ (páginas originais +
relatorio.json + relatorio.md). Serve para validar as fontes reais antes de
ligar a coleta e para reajustar a configuração quando um site mudar.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import radar_inlabs
from radar_banco import Banco, ErroBanco
from radar_coletores import enderecos_da_listagem as listar_enderecos, listar_paginas
from radar_util import VERSAO, ErroDownload, baixar, extrair_texto

AQUI = Path(__file__).resolve().parent


def estrutura_da_pagina(html: str) -> dict:
    """Resumo da página que o robô não entendeu, para ajustar a fonte só pelo log do GitHub:
    título, quantas tabelas/linhas/formulários há, links e o começo do texto e do HTML."""
    sopa = BeautifulSoup(html or "", "lxml")
    links = [f"{normalizar(a.get_text(' ', strip=True))[:60]} -> {a['href'][:160]}" for a in sopa.find_all("a", href=True)]
    for lixo in sopa(["script", "style", "noscript"]):
        lixo.decompose()
    return {
        "titulo": normalizar(sopa.title.get_text()) if sopa.title else "",
        "tabelas": len(sopa.find_all("table")), "linhas": len(sopa.find_all("tr")),
        "formularios": len(sopa.find_all("form")), "scripts": html.count("<script"),
        "links": len(links), "amostra_links": links[:40],
        "inicio_texto": normalizar(sopa.get_text(" ", strip=True))[:1500],
        "inicio_html": re.sub(r"\s+", " ", html or "")[:3000],
        "scripts_src": [t["src"] for t in BeautifulSoup(html or "", "lxml").find_all("script", src=True)][:10],
        # feed RSS/Atom anunciado pela página: é o jeito mais estável de ler um site de notícias
        "feeds": [f"{l.get('title') or ''} -> {l['href']}" for l in BeautifulSoup(html or "", "lxml").find_all("link", href=True)
                  if "rss" in (l.get("type") or "") or "atom" in (l.get("type") or "")][:5],
    }


RE_ENDERECO = re.compile(r"""["'`]((?:https?://[^"'`\s]{4,200})|(?:/[A-Za-z0-9_\-]*(?:api|rest|consulta|servico|service|ato|norma)[A-Za-z0-9_\-/.{}$]*))["'`]""", re.I)


def enderecos_nos_scripts(url: str, scripts: list[str], sessao: requests.Session) -> dict:
    """Página montada por JavaScript: baixa os scripts e lista os endereços que aparecem neles
    (é onde fica a API de onde a página tira os dados)."""
    r = sessao.get(url, timeout=40, headers={"User-Agent": "Mozilla/5.0 RadarArtecon"})
    final = r.url
    base = BeautifulSoup(r.text, "lxml").find("base", href=True)
    raiz = urljoin(final, base["href"]) if base else final      # <base href="/">: scripts ficam na raiz do site
    achados: dict[str, list[str]] = {"_final": [final, "base: " + raiz]}
    for src in scripts:
        endereco = urljoin(raiz, src)
        try:
            js = sessao.get(endereco, timeout=40, headers={"User-Agent": "Mozilla/5.0 RadarArtecon"}).text
        except requests.RequestException as e:
            achados[endereco] = [f"erro: {e}"]
            continue
        vistos = sorted({m.group(1) for m in RE_ENDERECO.finditer(js)
                         if not re.search(r"\.(css|svg|png|woff2?|ttf|ico)$|w3\.org|angular\.io|github\.com", m.group(1))})
        achados[endereco] = [f"{len(js)} bytes"] + [v for v in vistos if not re.search(r"schemas\.|openoffice|oasis|purl\.|sheetjs|jspdf|macVml", v)][:40]
        # o endereço da API costuma ser montado em pedaços: mostra o código em volta das chamadas
        trechos = []
        for m in re.finditer(r"`\$\{this\.\w*(?:[Uu]rl|[Aa]pi)\w*\}[^`]{0,120}`", js):
            trecho = re.sub(r"\s+", " ", js[max(0, m.start() - 80): m.end() + 120])
            if trecho not in trechos:
                trechos.append(trecho)
            if len(trechos) >= 40:
                break
        achados[endereco] += [f"…{t}…" for t in trechos]
    return achados


def normalizar(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


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

        if fonte.get("tipo_coletor") == "inlabs":
            listagem, r["http"] = radar_inlabs.listar_paginas(sessao, fonte)
        else:
            listagem, r["http"] = listar_paginas(baixar_e_guardar, fonte)
        r["bytes"] = sum(len(c.encode("utf-8")) for c in paginas)
        r["brutos"], r["na_janela"] = listagem.brutos, len(listagem.itens)
        r["amostra"] = [{"titulo": i.titulo, "data": i.data.isoformat() if i.data else None, "url": i.url}
                        for i in listagem.itens[:5]]
        if listagem.itens and (config.get("sem_pagina_de_texto")
                               or (config.get("texto_do_feed") and listagem.itens[0].texto_da_listagem)):
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
        if fonte.get("avulsa"):                     # teste de site novo: sempre mostra como a página está montada
            r["estrutura"] = estrutura_da_pagina(paginas[0] if paginas else "")
        if r["brutos"] == 0:
            r["veredito"] = "REVISAR — nenhum item reconhecido"
            r["estrutura"] = r.get("estrutura") or estrutura_da_pagina(paginas[0] if paginas else "")
            if r["estrutura"]["scripts_src"] and not r["estrutura"]["links"]:
                try:
                    r["estrutura"]["enderecos_js"] = enderecos_nos_scripts(
                        listar_enderecos(fonte)[0], r["estrutura"]["scripts_src"], sessao)
                except Exception as e:
                    r["estrutura"]["enderecos_js"] = {"erro": [f"{type(e).__name__}: {e}"]}
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
        if r.get("estrutura"):
            e = r["estrutura"]
            linhas.append(f"\n{'Como a página está montada' if r['brutos'] else 'Página não reconhecida'} — título: _{e['titulo']}_; {e['tabelas']} tabela(s), {e['linhas']} linha(s), "
                          f"{e['formularios']} formulário(s), {e['scripts']} script(s), {e['links']} link(s).")
            if e.get("feeds"):
                linhas += ["", "Feeds RSS/Atom anunciados:", *[f"- `{f}`" for f in e["feeds"]]]
            linhas += ["", "Links (amostra):", *[f"- `{l}`" for l in e["amostra_links"]]]
            linhas += ["", f"Texto: _{e['inicio_texto']}_", "", "```html", e["inicio_html"], "```"]
            for js, lista in (e.get("enderecos_js") or {}).items():
                linhas += ["", f"Endereços em `{js}`:", *[f"- `{x}`" for x in lista]]
    return "\n".join(linhas)


def fontes_avulsas(enderecos: str, padrao: str = "") -> list[dict]:
    """Endereços para testar antes de cadastrar (Actions → diagnóstico → "endereços"): cada um vira uma fonte
    provisória do tipo "página com lista de links"; sem padrão, todos os links contam."""
    fontes = []
    for n, url in enumerate([u for u in re.split(r"[\s,;]+", enderecos or "") if u.startswith(("http://", "https://"))][:10], 1):
        fontes.append({"slug": f"teste-{n}", "url": url, "tipo_coletor": "rss" if re.search(r"(rss|feed|atom)", url, re.I) else "html_links",
                       "config": {"padrao_url": padrao or ".", "janela_dias": 30, "texto_do_feed": True}, "avulsa": True})
    return fontes


def carregar_fontes() -> tuple[list[dict], str]:
    """Endereços avulsos (variável ENDERECOS); senão, fontes ativas do banco quando há chave; senão, as do arquivo."""
    avulsas = fontes_avulsas(os.environ.get("ENDERECOS", ""), os.environ.get("PADRAO", ""))
    if avulsas:
        return avulsas, "endereços informados para teste"
    url, chave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if url and chave:
        try:
            fontes = [f for f in Banco(url, chave).fontes_ativas() if (f.get("config") or {}).get("origem") != "email"]
            return fontes, "fontes ativas do banco"
        except ErroBanco as e:
            print(f"! banco indisponível ({e}); usando robo/radar_fontes.json", file=sys.stderr)
    return json.loads((AQUI / "radar_fontes.json").read_text(encoding="utf-8")), "robo/radar_fontes.json"


def main() -> int:
    fontes, origem = carregar_fontes()
    print(f"Fontes conferidas: {len(fontes)} ({origem})")
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
    texto = relatorio_md(resultados) + f"\n\n_Fontes conferidas: {len(fontes)} ({origem})._"
    (pasta / "relatorio.md").write_text(texto, encoding="utf-8")
    destino = os.environ.get("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(texto + "\n")
    print("\n" + texto)
    return 0   # o diagnóstico informa; quem decide é quem lê o relatório


if __name__ == "__main__":
    sys.exit(main())
