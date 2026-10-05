"""Radar Artecon — acesso ao painel do site da Artecon (artecon.cnt.br/admin), só para CADASTRAR notícias.

Regras combinadas com o escritório (05/10/2026):
  * o acesso é por usuário e senha, guardados SÓ nos segredos do GitHub (ARTECON_SITE_USUARIO e
    ARTECON_SITE_SENHA) — nunca no código, no banco, no chat ou nos registros;
  * o robô só usa a opção de cadastrar notícias; nada de mexer em outras áreas do painel;
  * nenhuma notícia vai ao ar sem autorização expressa do escritório: o robô só grava como rascunho
    (não publicada). Se o formulário não tiver como gravar sem publicar, o robô NÃO envia nada;
  * se o login pedir "não sou um robô" (reCAPTCHA), o robô para: não se contorna.

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
    return (urlsplit(url).hostname or "").removeprefix("www.") == "artecon.cnt.br"


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
    if CAPTCHA.search(r.text):
        raise Parada("a tela de login ainda pede verificação \"não sou um robô\" (reCAPTCHA). O robô não contorna: "
                     "peça ao desenvolvedor para liberar este usuário da verificação.")
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
