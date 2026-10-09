"""Radar Artecon — acesso ao painel do site da Artecon (artecon.cnt.br/admin), só para CADASTRAR notícias.

Regras combinadas com o escritório (05/10/2026):
  * o acesso é por usuário e senha, guardados SÓ nos segredos do GitHub (ARTECON_SITE_USUARIO e
    ARTECON_SITE_SENHA) — nunca no código, no banco, no chat ou nos registros;
  * o robô só usa a opção de cadastrar notícias; nada de mexer em outras áreas do painel;
  * nenhuma notícia vai ao ar sem autorização expressa do escritório: o robô só grava como rascunho
    (não publicada). Se o formulário não tiver como gravar sem publicar, o robô NÃO envia nada;
  * o "não sou um robô" (reCAPTCHA) nunca é resolvido nem contornado: o login vai sem ele (o usuário do Radar foi
    liberado pelo site); se o site exigir, o robô para.

Este arquivo, por enquanto, só RECONHECE o painel (modo padrão): entra, acha o formulário de cadastro
de notícias e lista os campos dele, sem enviar nada. O relatório não traz senha, cookie nem conteúdo,
porque o registro do GitHub Actions é público.

Uso (workflow manual "Radar — teste do site"):  python radar_site_admin.py
"""
from __future__ import annotations

import os
import re
import sys
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

BASE = "https://artecon.cnt.br"
LOGIN = BASE + "/admin/signin"
CAPTCHA = re.compile(r"g-recaptcha|grecaptcha|recaptcha/api|hcaptcha|cf-turnstile|challenges\.cloudflare", re.I)
NOTICIA = re.compile(r"news|noticia|not[ií]cia", re.I)
CRIAR = re.compile(r"create|new|nova|novo|cadastr|adicion|add\b|incluir", re.I)
PUBLICACAO = re.compile(r"status|publi|ativo|active|visib|draft|rascunho|situa", re.I)
AGENTE = {"User-Agent": "Mozilla/5.0 (RadarArtecon; cadastro de noticias)"}


class Parada(Exception):
    """O robô não segue (captcha, login recusado, formulário não encontrado). A mensagem diz o porquê."""


def mesmo_site(url: str) -> bool:
    return (urlsplit(url).hostname or "").removeprefix("www.") == (urlsplit(BASE).hostname or "").removeprefix("www.")


def formularios(html: str, base: str) -> list[dict]:
    """Cada formulário: endereço, método e campos (nome, tipo, obrigatório, opções, rótulo). Nunca os valores digitados."""
    sopa = BeautifulSoup(html or "", "lxml")
    rotulos = {l.get("for"): " ".join(l.get_text(" ").split()) for l in sopa.find_all("label") if l.get("for")}
    saida = []
    for f in sopa.find_all("form"):
        campos = []
        for c in f.find_all(["input", "select", "textarea"]):
            tipo = c.name if c.name != "input" else (c.get("type") or "text").lower()
            if tipo in ("submit", "button", "image", "reset"):
                continue
            campo = {"nome": c.get("name") or "", "tipo": tipo, "obrigatorio": c.has_attr("required"),
                     "rotulo": rotulos.get(c.get("id"), "")[:80]}
            if tipo == "select":
                campo["opcoes"] = [" ".join(o.get_text(" ").split())[:60] for o in c.find_all("option")][:40]
            if tipo in ("checkbox", "radio"):
                campo["valor"] = (c.get("value") or "")[:40]          # o valor da opção (ex.: "1", "rascunho"), não algo digitado
            campos.append(campo)
        botoes = [" ".join(b.get_text(" ").split())[:40] or (b.get("value") or "")[:40]
                  for b in f.find_all(["button", "input"]) if (b.get("type") or "submit").lower() == "submit"]
        saida.append({"acao": urljoin(base, f.get("action") or base), "metodo": (f.get("method") or "get").lower(),
                      "campos": campos, "botoes": botoes})
    return saida


def entrar(sessao: requests.Session, usuario: str, senha: str) -> str:
    """Faz o login e devolve o HTML da primeira página do painel."""
    r = sessao.get(LOGIN, timeout=40)
    r.raise_for_status()
    # A página carrega o "não sou um robô" para todos; o usuário do Radar foi liberado pelo site para entrar só com
    # usuário e senha. O robô NÃO resolve nem contorna a verificação: envia o login sem ela; se o site exigir, para.
    com_captcha = bool(CAPTCHA.search(r.text))
    form = next((f for f in formularios(r.text, r.url) if any(c["tipo"] == "password" for c in f["campos"])), None)
    if form is None:
        raise Parada("não achei o formulário de login na página /admin/signin")
    sopa = BeautifulSoup(r.text, "lxml")
    dados = {i.get("name"): i.get("value") or "" for i in sopa.find_all("input", type="hidden") if i.get("name")}
    texto = next((c["nome"] for c in form["campos"] if c["tipo"] in ("email", "text") and c["nome"]), None)
    oculto = next((c["nome"] for c in form["campos"] if c["tipo"] == "password" and c["nome"]), None)
    if not (texto and oculto):
        raise Parada("o formulário de login não tem os campos esperados (usuário e senha)")
    dados[texto], dados[oculto] = usuario, senha
    r = sessao.post(form["acao"], data=dados, timeout=40, allow_redirects=True)
    if r.status_code >= 400 or any(c["tipo"] == "password" for f in formularios(r.text, r.url) for c in f["campos"]):
        if com_captcha:
            raise Parada("o site exigiu a verificação \"não sou um robô\" (reCAPTCHA) para este usuário. O robô não contorna: "
                         "peça ao desenvolvedor para dispensar a verificação para o usuário do Radar.")
        raise Parada(f"o login não foi aceito (HTTP {r.status_code}); confira usuário e senha nos segredos do GitHub")
    return r.text if mesmo_site(r.url) else ""


def achar_cadastro(sessao: requests.Session, html: str, base: str) -> tuple[str, dict]:
    """Endereço e formulário de cadastro de notícia (segue no máximo os links de notícia do menu)."""
    sopa = BeautifulSoup(html or "", "lxml")
    links = []
    for a in sopa.find_all("a", href=True):
        url, texto = urljoin(base, a["href"]), " ".join(a.get_text(" ").split())
        if mesmo_site(url) and "/admin" in url and (NOTICIA.search(url) or NOTICIA.search(texto)):
            links.append((url, texto))
    candidatos = [u for u, t in links if CRIAR.search(u) or CRIAR.search(t)] + [u for u, t in links]
    vistos, i = set(), 0
    while i < len(candidatos) and len(vistos) < 8:
        url, i = candidatos[i], i + 1
        if url in vistos or re.search(r"delete|excluir|remove|destroy|logout|sair", url, re.I):
            continue                                  # nunca abre link que apaga ou sai
        vistos.add(url)
        r = sessao.get(url, timeout=40)
        forms = [f for f in formularios(r.text, r.url) if f["metodo"] == "post" and len(f["campos"]) >= 2]
        if forms:
            return r.url, max(forms, key=lambda f: len(f["campos"]))
        for u, t in [(urljoin(r.url, a["href"]), a.get_text(" ")) for a in BeautifulSoup(r.text, "lxml").find_all("a", href=True)]:
            if mesmo_site(u) and (CRIAR.search(u) or CRIAR.search(t)) and NOTICIA.search(u) and u not in vistos:
                candidatos.append(u)
    raise Parada("entrei no painel, mas não achei o formulário de cadastro de notícias "
                 f"(links de notícia vistos: {', '.join(urlsplit(u).path for u, _ in links[:10]) or 'nenhum'})")


def relatorio(url: str, form: dict) -> str:
    linhas = [f"Formulário de cadastro: {urlsplit(url).path}  →  envia para {urlsplit(form['acao']).path} ({form['metodo'].upper()})", "", "Campos:"]
    for c in form["campos"]:
        if c["tipo"] == "hidden":
            continue
        extra = f" opções: {c['opcoes']}" if c.get("opcoes") else (f" valor: {c['valor']}" if c.get("valor") else "")
        marca = "  ← controla a publicação?" if PUBLICACAO.search(c["nome"] + " " + c["rotulo"]) else ""
        linhas.append(f"  - {c['nome'] or '(sem nome)'} [{c['tipo']}{', obrigatório' if c['obrigatorio'] else ''}] "
                      f"{c['rotulo']}{extra}{marca}")
    linhas += ["", f"Botões: {form['botoes']}"]
    pub = [c for c in form["campos"] if PUBLICACAO.search(c["nome"] + " " + c["rotulo"]) and c["tipo"] != "hidden"]
    linhas += ["", "Gravar sem publicar: " + ("há campo de situação/publicação (ver acima) — dá para testar como rascunho."
                                              if pub else "NÃO achei campo de situação/publicação. Sem ele, o robô não envia nada.")]
    return "\n".join(linhas)


# v0.17.0: reconhecimento da LISTA de notícias do painel (para a exclusão pedida pelo administrador). Só lê: nunca abre
# link de excluir/sair e não envia formulário nenhum. Valores de campos ocultos e códigos longos não vão para o relatório.
APAGA = re.compile(r"delete|excluir|destroy|remove|apagar|logout|sair", re.I)
ACAO = re.compile(r"delete|excluir|destroy|remove|apagar|edit|editar|alterar|show|ver|visualizar|news/\d|/\d+", re.I)


def _curto(t: str, n: int = 80) -> str:
    t = " ".join(str(t or "").split())
    return re.sub(r"[A-Za-z0-9+/=_-]{30,}", "…", t)[:n]


def _caminho(base: str, href: str) -> str:
    u = urlsplit(urljoin(base, href or ""))
    return (u.path or "/") + (("?" + u.query) if u.query else "") if mesmo_site(u.geturl()) or not u.netloc else u.geturl()[:80]


def _acoes(no, base: str) -> list[str]:
    """Links e formulários de uma linha da lista: texto, endereço, método e o que confirma (nunca valores digitados)."""
    saida = []
    for a in no.find_all("a"):
        attrs = {k: v for k, v in a.attrs.items() if k.startswith("data-") or k in ("onclick", "target", "class", "title")}
        extra = " ".join(f"{k}={_curto(' '.join(v) if isinstance(v, list) else v, 60)}" for k, v in attrs.items())
        saida.append(f"link “{_curto(a.get_text(' '), 30)}” → {_caminho(base, a.get('href'))} {extra}".rstrip())
    for f in no.find_all("form"):
        ocultos = [(i.get("name") or "") + ("=" + _curto(i.get("value"), 20) if (i.get("name") or "") == "_method" else "")
                   for i in f.find_all("input", type="hidden")]
        botoes = [_curto(b.get_text(" ") or b.get("value"), 30) for b in f.find_all(["button", "input"])
                  if (b.get("type") or "submit").lower() in ("submit", "button")]
        conf = " onsubmit=" + _curto(f.get("onsubmit"), 60) if f.get("onsubmit") else ""
        saida.append(f"formulário {(f.get('method') or 'get').upper()} → {_caminho(base, f.get('action'))} ocultos={ocultos} botões={botoes}{conf}")
    for b in no.find_all("button"):
        if b.find_parent("form") is None:
            attrs = {k: v for k, v in b.attrs.items() if k.startswith("data-") or k in ("onclick", "class")}
            saida.append(f"botão “{_curto(b.get_text(' '), 30)}” " + " ".join(f"{k}={_curto(' '.join(v) if isinstance(v, list) else v, 60)}"
                                                                         for k, v in attrs.items()))
    return saida


def relatorio_lista(url: str, html: str) -> str:
    sopa = BeautifulSoup(html or "", "lxml")
    linhas = [f"Lista de notícias: {urlsplit(url).path}"]
    for n, t in enumerate(sopa.find_all("table")[:3], 1):
        cab = [_curto(th.get_text(" "), 30) for th in t.find_all("th")]
        linhas.append(f"Tabela {n}: colunas {cab}")
        for k, tr in enumerate([tr for tr in t.find_all("tr") if tr.find("td")][:4], 1):
            linhas.append(f"  linha {k}: " + " | ".join(_curto(td.get_text(" "), 50) for td in tr.find_all("td")))
            linhas += [f"     {x}" for x in _acoes(tr, url)]
        linhas.append(f"  ({len([tr for tr in t.find_all('tr') if tr.find('td')])} linhas nesta página)")
    if not sopa.find_all("table"):                       # lista sem tabela (cartões): mostra os blocos com ação
        blocos = [b for b in sopa.find_all(["li", "div", "article"]) if b.find("a", href=APAGA) or b.find("form")][:4]
        for k, b in enumerate(blocos, 1):
            linhas.append(f"  bloco {k}: {_curto(b.get_text(' '), 100)}")
            linhas += [f"     {x}" for x in _acoes(b, url)]
    soltos = [f for f in sopa.find_all("form") if not f.find_parent("table")]
    if soltos:
        linhas.append("Formulários fora da tabela:")
        for f in soltos[:5]:
            linhas += [f"  {x}" for x in _acoes(f.parent or f, url) if x.startswith("formulário")][:1]
    pags = sorted({_caminho(url, a["href"]) for a in sopa.find_all("a", href=True) if re.search(r"page=|pagina=|/page/", a["href"])})[:5]
    linhas.append(f"Paginação: {pags or 'nenhuma'}")
    meta = [m.get("name") for m in sopa.find_all("meta") if "csrf" in (m.get("name") or "").lower()]
    linhas.append(f"Meta CSRF: {meta or 'não'}")
    trechos = []
    for s in sopa.find_all("script"):
        txt = s.string or ""
        m = re.search(r"(?i)(delete|destroy|excluir|swal|confirm\(|_method)", txt)
        if m:
            trechos.append(_curto(txt[max(0, m.start() - 120): m.start() + 240], 360))
    linhas.append("Scripts da página que tratam exclusão/confirmação:" + ("".join(f"\n  - {t}" for t in trechos[:6]) if trechos else " nenhum"))
    externos = [_caminho(url, s["src"]) for s in sopa.find_all("script", src=True)][:12]
    linhas.append(f"Scripts externos: {externos or 'nenhum'}")
    for t in sopa.find_all("table")[:2]:
        attrs = {k: (" ".join(v) if isinstance(v, list) else v) for k, v in t.attrs.items()}
        linhas.append(f"Atributos da tabela: {{{', '.join(f'{k}={_curto(v, 80)}' for k, v in attrs.items())}}}")
    return "\n".join(linhas)


def trechos_script(js: str, limite: int = 14) -> list[str]:
    """Trechos do script do painel que montam a lista e tratam a exclusão (endereços, método, confirmação)."""
    saida, fim = [], -1
    for m in re.finditer(r"(?i)news|delete|destroy|excluir|ajax|swal|datatable|_token|csrf|\$\.(post|get)|fetch\(", js or ""):
        if m.start() < fim:
            continue
        ini, fim = max(0, m.start() - 160), m.start() + 320
        saida.append(_curto(js[ini:fim], 480))
        if len(saida) >= limite:
            break
    return saida


def scripts_do_painel(sessao: requests.Session, url: str, html: str) -> str:
    """Lê (GET) os scripts próprios do painel citados na página da lista — nunca os de bibliotecas — e mostra os trechos."""
    linhas = []
    for s in BeautifulSoup(html or "", "lxml").find_all("script", src=True):
        alvo = urljoin(url, s["src"])
        if not mesmo_site(alvo) or "/lib/" in alvo or APAGA.search(urlsplit(alvo).path):
            continue
        r = sessao.get(alvo, timeout=40)
        linhas.append(f"Script {urlsplit(alvo).path} (HTTP {r.status_code}, {len(r.text)} caracteres):")
        i = r.text.find("data-confirm")
        if i >= 0:                                         # a confirmação da exclusão: o trecho inteiro
            linhas.append("  confirmação: " + _curto(r.text[i - 40: i + 1400], 1500))
        else:
            linhas += [f"  - {t}" for t in trechos_script(r.text)] or ["  (nada sobre notícias ou exclusão)"]
    return "\n".join(linhas) or "Scripts próprios do painel: nenhum"


def dados_da_lista(sessao: requests.Session, url: str, html: str) -> str:
    """A lista em si (data-url da tabela, lida por GET como o painel faz): quantas notícias e as 2 primeiras, com as ações."""
    tabela = BeautifulSoup(html or "", "lxml").find("table", attrs={"data-url": True})
    if tabela is None:
        return "Dados da lista: a tabela não indica de onde vêm as linhas"
    alvo = urljoin(url, tabela["data-url"])
    if not mesmo_site(alvo) or APAGA.search(urlsplit(alvo).path):
        return f"Dados da lista: endereço não lido ({_caminho(url, alvo)})"
    r = sessao.get(alvo, timeout=40, headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
    linhas = [f"Dados da lista: GET {urlsplit(alvo).path} → HTTP {r.status_code}, {r.headers.get('content-type', '?')}"]
    try:
        dados = r.json()
    except ValueError:
        return "\n".join(linhas + ["  (não é JSON) " + _curto(r.text, 200)])
    linhas.append(f"  chaves: {list(dados)[:10] if isinstance(dados, dict) else type(dados).__name__}")
    itens = dados.get("data") if isinstance(dados, dict) else dados
    itens = itens if isinstance(itens, list) else []
    linhas.append(f"  {len(itens)} notícia(s) na resposta; recordsTotal={dados.get('recordsTotal') if isinstance(dados, dict) else '?'}")
    for k, item in enumerate(itens[:2], 1):
        celulas = item if isinstance(item, list) else list(item.values()) if isinstance(item, dict) else [item]
        linhas.append(f"  notícia {k}: " + " | ".join(_curto(BeautifulSoup(str(c), "lxml").get_text(" "), 60) for c in celulas))
        for c in celulas:
            if "<" in str(c):
                linhas += [f"     {x}" for x in _acoes(BeautifulSoup(str(c), "lxml"), alvo)]
    return "\n".join(linhas)


def achar_lista(sessao: requests.Session, html: str, base: str) -> tuple[str, str]:
    """A página com a lista das notícias cadastradas (segue só links de notícia do menu; nunca abre excluir nem sair)."""
    sopa = BeautifulSoup(html or "", "lxml")
    candidatos = [BASE + "/admin/news"]
    for a in sopa.find_all("a", href=True):
        url, texto = urljoin(base, a["href"]), " ".join(a.get_text(" ").split())
        if mesmo_site(url) and "/admin" in url and (NOTICIA.search(url) or NOTICIA.search(texto)) and not CRIAR.search(url):
            candidatos.append(url)
    vistos = set()
    for url in candidatos:
        if url in vistos or APAGA.search(url) or len(vistos) >= 5:
            continue
        vistos.add(url)
        r = sessao.get(url, timeout=40)
        if r.status_code >= 400 or not mesmo_site(r.url):
            continue
        pagina = BeautifulSoup(r.text, "lxml")
        if pagina.find("table") is not None or pagina.find("a", href=APAGA) is not None:
            return r.url, r.text
    raise Parada(f"não achei a lista de notícias do painel (abri: {', '.join(urlsplit(u).path for u in vistos)})")


def main() -> int:
    usuario, senha = os.environ.get("ARTECON_SITE_USUARIO", ""), os.environ.get("ARTECON_SITE_SENHA", "")
    if not (usuario and senha):
        print("Faltam os segredos ARTECON_SITE_USUARIO e ARTECON_SITE_SENHA no GitHub (Settings → Secrets and variables → Actions).")
        return 1
    sessao = requests.Session()
    sessao.headers.update(AGENTE)
    try:
        painel = entrar(sessao, usuario, senha)
        print("Login: aceito.")
        url, form = achar_cadastro(sessao, painel, BASE + "/admin")
        texto = relatorio(url, form)
        try:                                               # v0.17.0: a lista (só leitura) para preparar a exclusão
            url_lista, html_lista = achar_lista(sessao, painel, BASE + "/admin")
            texto += "\n\n" + relatorio_lista(url_lista, html_lista) + "\n\n" + scripts_do_painel(sessao, url_lista, html_lista) \
                     + "\n\n" + dados_da_lista(sessao, url_lista, html_lista)
        except Parada as e:
            texto += f"\n\nLista de notícias: {e}"
    except Parada as e:
        texto = f"PAROU: {e}"
    except requests.RequestException as e:
        texto = f"PAROU: sem conexão com o site ({type(e).__name__})"
    texto = texto.replace(senha, "***").replace(usuario, "***")      # nunca no registro público
    print(texto)
    destino = os.environ.get("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write("### Teste do site (só leitura, nada foi enviado)\n\n```\n" + texto + "\n```\n")
    return 0 if not texto.startswith("PAROU") else 1


if __name__ == "__main__":
    sys.exit(main())
