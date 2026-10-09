"""Radar Artecon — exclusão de notícia no site da Artecon, a pedido do administrador (v0.17.0).

Na aba Publicações, o administrador clica em "Excluir do site". Isso grava um pedido em radar_site_exclusoes
(situação "pedido"). Na rodada seguinte do workflow "Radar — publicar no site" (a cada 15 minutos), este robô:
  1. marca o pedido como "excluindo";
  2. entra no painel do site e lê a lista de notícias do painel (o mesmo endereço que a tela do painel usa);
  3. acha a notícia pelo título que está no site — só segue se houver exatamente uma com esse título;
  4. abre o link "Excluir" dessa notícia, como o painel faz depois do "Tem certeza que deseja excluir esta notícia?";
  5. lê a lista de novo e confere que a notícia saiu; só então conclui (o registro em "Publicações no site" é retirado).

Regras (as mesmas do cadastro, com a autorização do escritório de 09/10/2026 para excluir quando o administrador pedir):
  * só exclui notícia com pedido do administrador gravado no banco (radar_pedir_exclusao_site confere o perfil);
  * nunca exclui na dúvida: título não encontrado, ou mais de uma notícia com o mesmo título, vira "erro" para conferir à mão;
  * usuário e senha só nos segredos do GitHub; o registro público do GitHub Actions não recebe senha, cookie nem os
    endereços de exclusão do painel.
"""
from __future__ import annotations

import html as html_lib
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

import radar_site_admin as admin
from radar_banco import Banco, ErroBanco
from radar_util import ErroDownload, baixar

LISTA = "/admin/news/list"
EXCLUIR = re.compile(r"^/admin/news/delete/[A-Za-z0-9._~-]+$")
ESPERA_MAXIMA = timedelta(hours=2)        # "excluindo" parado por mais tempo (o site não responde): vira erro para conferir


def titulo_normal(t: str | None) -> str:
    """Título comparável: sem marcação, sem acento, minúsculo, espaços e aspas uniformes."""
    t = BeautifulSoup(html_lib.unescape(str(t or "")), "lxml").get_text(" ")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[\"'“”‘’`´]", "", t)
    return " ".join(t.split())


def _quando(valor) -> datetime | None:
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00")) if valor else None
    except ValueError:
        return None


class Excluidor:
    def __init__(self, banco: Banco, usuario: str, senha: str, sessao: requests.Session | None = None,
                 baixar_pagina=lambda url: baixar(url, tentativas=2)[1], agora=None):
        self.banco, self.usuario, self.senha = banco, usuario, senha
        self.sessao = sessao or requests.Session()
        self.sessao.headers.update(admin.AGENTE)
        self.baixar = baixar_pagina
        self.agora = agora or (lambda: datetime.now(timezone.utc))
        self.logado = False
        self.feito: list[str] = []

    def _limpo(self, texto: str) -> str:
        for segredo in (self.senha, self.usuario):
            if segredo:
                texto = texto.replace(segredo, "***")
        return re.sub(r"/admin/news/delete/\S+", "/admin/news/delete/…", texto)[:900]

    # -------------------------------------------------------------- o site
    def entrar(self):
        if not self.logado:
            admin.entrar(self.sessao, self.usuario, self.senha)
            self.logado = True

    def lista(self) -> list[dict]:
        """As notícias do painel: título e o link de exclusão de cada uma."""
        r = self.sessao.get(admin.BASE + LISTA, timeout=60, headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
        if r.status_code >= 400 or not admin.mesmo_site(r.url):
            raise admin.Parada(f"a lista de notícias do painel não abriu (HTTP {r.status_code})")
        try:
            dados = r.json()
        except ValueError as e:
            raise admin.Parada("a lista de notícias do painel não veio no formato esperado (o site pediu login de novo?)") from e
        linhas = dados.get("data") if isinstance(dados, dict) else None
        if not isinstance(linhas, list):
            raise admin.Parada("a lista de notícias do painel mudou de formato")
        saida = []
        for linha in linhas:
            celulas = linha if isinstance(linha, list) else list(linha.values()) if isinstance(linha, dict) else []
            if not celulas:
                continue
            excluir = None
            for c in celulas:
                for a in BeautifulSoup(str(c), "lxml").find_all("a", href=True):
                    alvo = urljoin(admin.BASE + LISTA, a["href"])
                    if admin.mesmo_site(alvo) and EXCLUIR.match(urlsplit(alvo).path or ""):
                        excluir = alvo
            saida.append({"titulo": titulo_normal(celulas[0]), "excluir": excluir})
        return saida

    @staticmethod
    def achar(lista: list[dict], titulo: str) -> list[dict]:
        alvo = titulo_normal(titulo).rstrip(" .")
        iguais = [n for n in lista if n["titulo"].rstrip(" .") == alvo]
        if iguais:
            return iguais
        # o painel pode encurtar o título longo ("Título muito comprido..."): vale o começo, com pelo menos 30 caracteres
        curtos = [(n, n["titulo"][:-3].rstrip()) for n in lista if n["titulo"].endswith("...")]
        return [n for n, inicio in curtos if len(inicio) >= 30 and alvo.startswith(inicio)]

    def saiu_do_site(self, url: str) -> bool:
        """A página pública da notícia não existe mais (404/410)."""
        try:
            self.baixar(url)
        except ErroDownload as e:
            return e.http_status in (404, 410)
        return False

    # -------------------------------------------------------------- o banco
    def banco_pronto(self) -> bool:
        """A função que conclui a exclusão existe no banco? Sem ela o robô não exclui nada do site (a notícia sairia do ar e o
        Radar continuaria mostrando como publicada). Pergunta por um pedido que não existe: a resposta é só "não achei"."""
        try:
            self.banco._pedir("POST", "rpc/radar_site_exclusao_concluir", corpo={"p_exclusao": 0, "p_ok": False, "p_erro": None})
            return True
        except ErroBanco as e:
            if "404" in str(e) or "PGRST202" in str(e):
                return False
            raise

    def marcar(self, pedido: dict, de: str, **campos) -> bool:
        campos["atualizado_em"] = self.agora().isoformat()
        linhas = self.banco._pedir("PATCH", "radar_site_exclusoes", params={"id": f"eq.{pedido['id']}", "situacao": f"eq.{de}"},
                                   corpo=campos, prefer="return=representation")
        return bool(linhas)

    def concluir(self, pedido: dict, ok: bool, erro: str | None = None):
        self.banco._pedir("POST", "rpc/radar_site_exclusao_concluir",
                          corpo={"p_exclusao": pedido["id"], "p_ok": ok, "p_erro": self._limpo(erro) if erro else None})
        self.feito.append(f"exclusão {pedido['id']}: " + ("excluída do site" if ok else "não concluída"))

    # -------------------------------------------------------------- a rodada
    def executar(self) -> list[str]:
        pedidos = self.banco._pedir("GET", "radar_site_exclusoes", params={
            "select": "id,conteudo_id,url,titulo,situacao,iniciado_em", "situacao": "in.(pedido,excluindo)", "order": "id"}) or []
        if pedidos and not self.banco_pronto():
            self.feito.append(f"{len(pedidos)} exclusão(ões) esperando: falta aplicar no banco a função radar_site_exclusao_concluir "
                              "(arquivo do pacote da v0.17.0, no SQL Editor do Supabase); nada foi excluído do site")
            return self.feito
        for pedido in pedidos:
            try:
                self.um(pedido)
            except admin.Parada as e:                       # nada foi excluído: o administrador confere e pede de novo
                self.concluir(pedido, False, f"Não excluída: {e}.")
                if "reCAPTCHA" in str(e) or "login" in str(e):
                    break
            except (requests.RequestException, ErroDownload) as e:
                # site fora do ar ou lento: tenta de novo na próxima rodada (excluir de novo não estraga nada)
                inicio = _quando(pedido.get("iniciado_em"))
                if inicio and self.agora() - inicio > ESPERA_MAXIMA:
                    self.concluir(pedido, False, "O site não respondeu por 2 horas. Confira no painel do site se a notícia ainda está lá "
                                                 "e peça a exclusão de novo.")
                else:
                    self.feito.append(f"exclusão {pedido['id']}: o site não respondeu ({type(e).__name__}); tenta de novo na próxima rodada")
                break
        return self.feito

    def um(self, pedido: dict):
        if pedido["situacao"] == "pedido":
            if not self.marcar(pedido, "pedido", situacao="excluindo", iniciado_em=self.agora().isoformat()):
                return                                      # cancelado pelo administrador agora há pouco
            pedido = dict(pedido, situacao="excluindo", iniciado_em=self.agora().isoformat())
        self.entrar()
        achadas = self.achar(self.lista(), pedido["titulo"])
        if not achadas:
            if self.saiu_do_site(pedido["url"]):            # já não está no painel nem no ar (excluída antes, à mão ou numa rodada interrompida)
                self.concluir(pedido, True)
                return
            raise admin.Parada("não achei a notícia com este título na lista do painel do site (o título pode ter sido mudado lá). "
                               "Exclua à mão no painel do site e depois tire o registro em Publicações")
        if len(achadas) > 1:
            raise admin.Parada(f"há {len(achadas)} notícias com este título no painel do site; exclua à mão a que deve sair")
        if not achadas[0]["excluir"]:
            raise admin.Parada("a notícia está no painel, mas sem o botão de excluir (o painel mudou)")
        r = self.sessao.get(achadas[0]["excluir"], timeout=60, allow_redirects=True)
        if r.status_code >= 500:
            raise requests.ConnectionError(f"o site respondeu HTTP {r.status_code} ao excluir")
        if self.achar(self.lista(), pedido["titulo"]):
            raise admin.Parada(f"o site não excluiu a notícia (respondeu HTTP {r.status_code}); confira no painel do site")
        self.concluir(pedido, True)
