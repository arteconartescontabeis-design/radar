"""Radar Artecon — Diário Oficial da União pelo INLABS (v0.8.0).

O INLABS (inlabs.in.gov.br, da Imprensa Nacional) entrega o DOU de cada dia em arquivos XML oficiais,
um por ato, dentro de um .zip por seção. O acesso é gratuito, mas pede cadastro: o e-mail e a senha
ficam nos segredos do GitHub (INLABS_EMAIL e INLABS_SENHA), nunca no código nem no banco.

Para não haver enxurrada, só entram os atos dos órgãos e tipos escolhidos na fonte:
    config.orgaos       expressão sobre o órgão (artCategory), ex.: "Receita Federal|Procuradoria-Geral da Fazenda"
    config.tipos        expressão sobre o tipo do ato (artType), ex.: "Instrução Normativa|Ato Declaratório"
    config.excluir_orgao expressão para tirar unidades regionais, ex.: "Superintendência Regional|Delegacia"
    config.secoes       seções do DOU (padrão ["DO1", "DO1E"]: seção 1 e edição extra)
    config.janela_dias  quantos dias para trás (padrão 5: cobre fim de semana e feriado emendado)
    config.palavras / config.excluir_palavras   v0.31.0: filtro de tema sobre o título e a ementa do ato (lista de pedaços de
                        expressão ou um texto; sem diferença de maiúsculas e acentos). Veja radar_coletores.filtro_de_tema.

v0.31.0: várias fontes do INLABS na mesma rodada (atos da Receita, leis e decretos, CONFAZ, trabalho e previdência) entram uma vez
só no site: o que a rodada já baixou fica guardado na sessão (o login e os atos de cada dia e seção); as outras fontes só filtram.
"""
from __future__ import annotations

import io
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

from radar_coletores import Item, Listagem, _finalizar
from radar_util import ErroDownload, hoje_brasilia, normalizar_espacos

BASE = "https://inlabs.in.gov.br"
LEITURA = "https://www.in.gov.br/leiturajornal?data={data}&secao={secao}"


def _data_br(valor: str | None) -> date | None:
    m = re.match(r"\s*(\d{2})/(\d{2})/(\d{4})", valor or "")
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None
    except ValueError:
        return None


def ler_xml(conteudo: bytes | str) -> dict | None:
    """Um ato do DOU (XML do INLABS) → dados do ato, ou None se não for um ato."""
    raiz = ET.fromstring(conteudo)
    art = raiz if raiz.tag == "article" else raiz.find(".//article")
    if art is None:
        return None
    corpo = art.find("body")
    pega = lambda nome: (corpo.findtext(nome) if corpo is not None else None) or ""
    identifica, ementa = normalizar_espacos(pega("Identifica")), normalizar_espacos(pega("Ementa"))
    sopa = BeautifulSoup(pega("Texto"), "lxml")
    texto = normalizar_espacos(sopa.get_text(" ", strip=True))
    if not ementa:
        # v0.31.0: o campo <Ementa> pode vir vazio; a ementa está no <p class="ementa"> do texto (é dela que o filtro de tema precisa)
        p = sopa.select_one("p.ementa")
        ementa = normalizar_espacos(p.get_text(" ", strip=True)) if p is not None else ""
    return {"id": art.get("idMateria") or art.get("id") or "", "tipo": art.get("artType") or "",
            "pagina": art.get("pdfPage") or "",
            "orgao": art.get("artCategory") or "", "secao": art.get("pubName") or "",
            "data": _data_br(art.get("pubDate")), "titulo": identifica or art.get("name") or "",
            "ementa": ementa, "texto": texto}


def filtrar(atos: list[dict], config: dict) -> list[dict]:
    orgaos = re.compile(config["orgaos"], re.I) if config.get("orgaos") else None
    tipos = re.compile(config["tipos"], re.I) if config.get("tipos") else None
    excluir = re.compile(config["excluir_orgao"], re.I) if config.get("excluir_orgao") else None
    return [a for a in atos if a and a["id"] and a["titulo"]
            and (orgaos is None or orgaos.search(a["orgao"])) and (tipos is None or tipos.search(a["tipo"]))
            and not (excluir and excluir.search(a["orgao"]))]


def atos_do_zip(dados: bytes) -> list[dict]:
    atos = []
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        for nome in z.namelist():
            if nome.lower().endswith(".xml"):
                try:
                    atos.append(ler_xml(z.read(nome)))
                except ET.ParseError:
                    continue                     # um arquivo estragado não derruba o dia
    return [a for a in atos if a]


def endereco(ato: dict) -> str:
    """Link oficial: a página do DOU onde o ato saiu (pdfPage do XML), com o número da matéria para
    distinguir atos da mesma página. Sem pdfPage, a edição do dia no leitor do DOU."""
    base = ato["pagina"] if re.match(r"https?://", ato["pagina"]) else LEITURA.format(
        data=ato["data"].strftime("%d-%m-%Y") if ato["data"] else "", secao=(ato["secao"] or "do1").lower())
    return f"{base}{'&' if '?' in base else '?'}materia={ato['id']}"


def para_item(ato: dict) -> Item:
    texto = " ".join(p for p in (ato["titulo"], ato["ementa"], ato["texto"]) if p)
    return Item(url=endereco(ato), titulo=ato["titulo"][:300], data=ato["data"],
                resumo=ato["ementa"] or None, texto_da_listagem=texto or None,
                metadados={"orgao": ato["orgao"], "tipo": ato["tipo"], "secao": ato["secao"], "inlabs_id": ato["id"]},
                # v0.31.0: ato sem ementa nenhuma — o filtro de tema olha só o começo do texto (nunca o texto todo: o preâmbulo
                # "O MINISTRO DE ESTADO DO TRABALHO E EMPREGO..." faria tudo passar)
                trecho_do_tema=None if ato["ementa"] else (ato["texto"][:500] or None))


def entrar(sessao: requests.Session, email: str | None = None, senha: str | None = None) -> None:
    # v0.23.0: sem os espaços e as quebras de linha das pontas (um colado no segredo do GitHub fez o login falhar em produção)
    email = (email or os.environ.get("INLABS_EMAIL") or "").strip()
    senha = (senha or os.environ.get("INLABS_SENHA") or "").strip()
    if not (email and senha):
        raise ErroDownload("INLABS: cadastre o acesso (inlabs.in.gov.br) e grave INLABS_EMAIL e INLABS_SENHA "
                           "nos segredos do GitHub")
    try:
        r = sessao.post(f"{BASE}/logar.php", data={"email": email, "password": senha}, timeout=40)
    except requests.RequestException as e:
        raise ErroDownload(f"INLABS: sem conexão — {type(e).__name__}: {e}") from e
    if r.status_code >= 400 or not sessao.cookies.get("inlabs_session_cookie"):
        raise ErroDownload(f"INLABS: o login não foi aceito (HTTP {r.status_code}); confira o e-mail e a senha nos segredos")


def baixar_secao(sessao: requests.Session, dia: date, secao: str) -> bytes | None:
    """O .zip da seção no dia, ou None quando não houve edição (fim de semana, feriado, sem extra)."""
    arquivo = f"{dia.isoformat()}-{secao}.zip"
    try:
        r = sessao.get(f"{BASE}/index.php", params={"p": dia.isoformat(), "dl": arquivo}, timeout=90,
                       headers={"origem": "736372697074"})
    except requests.RequestException as e:
        raise ErroDownload(f"INLABS {arquivo}: {type(e).__name__}: {e}") from e
    if r.status_code == 404:
        return None                      # não houve edição (fim de semana, feriado, sem extra)
    if r.status_code != 200:
        raise ErroDownload(f"INLABS {arquivo}: HTTP {r.status_code}", r.status_code)
    if not r.content.startswith(b"PK"):
        if b"logar" in r.content[:20000].lower() or b"password" in r.content[:20000].lower():
            raise ErroDownload("INLABS: a sessão não foi aceita (o site pediu login de novo)")
        return None                      # página de aviso no lugar do arquivo: não houve edição
    return r.content


def _memoria(sessao) -> dict:
    """v0.31.0: o que a rodada já leu do INLABS (o login e os atos de cada dia e seção), guardado na própria sessão da rodada: a
    rodada seguinte (outra sessão) baixa tudo de novo, então a edição extra que sair depois entra na próxima coleta."""
    memoria = getattr(sessao, "radar_inlabs", None)
    if memoria is None:
        memoria = {"logado": False, "atos": {}}
        try:
            setattr(sessao, "radar_inlabs", memoria)
        except AttributeError:
            pass
    return memoria


def _dias_e_secoes(config: dict, hoje: date) -> list[tuple[date, str]]:
    return [(hoje - timedelta(days=n), secao) for n in range(int(config.get("janela_dias", 5)))
            for secao in (config.get("secoes") or ["DO1", "DO1E"])]


def janela_em_memoria(sessao, fonte: dict, hoje: date | None = None) -> bool:
    """A rodada já tem todos os dias e seções da fonte (ela não vai baixar nada: só filtrar)."""
    memoria = getattr(sessao, "radar_inlabs", None)
    if not memoria:
        return False
    return all(chave in memoria["atos"] for chave in _dias_e_secoes(fonte.get("config") or {}, hoje or hoje_brasilia()))


def listar_paginas(sessao: requests.Session, fonte: dict, hoje: date | None = None) -> tuple[Listagem, int | None]:
    config = fonte.get("config") or {}
    hoje = hoje or hoje_brasilia()
    janela = int(config.get("janela_dias", 5))
    memoria = _memoria(sessao)
    atos = []
    for dia, secao in _dias_e_secoes(config, hoje):
        if (dia, secao) not in memoria["atos"]:
            if not memoria["logado"]:
                entrar(sessao)
                memoria["logado"] = True
            dados = baixar_secao(sessao, dia, secao)
            memoria["atos"][(dia, secao)] = atos_do_zip(dados) if dados else []
        atos += memoria["atos"][(dia, secao)]
    escolhidos = filtrar(atos, config)
    resultado = _finalizar([para_item(a) for a in escolhidos], dict(config, janela_dias=janela + 1), hoje)
    resultado.brutos = len(atos)
    return resultado, 200
