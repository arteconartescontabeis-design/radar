"""Radar Artecon — publicação no site da Artecon com autorização (v0.10.0; v0.17.0: redes junto e exclusão; v0.25.0: a mesma imagem).

Na tela do assunto, o administrador clica em "Autorizar publicação no site" (passo 4). Isso grava uma linha em
radar_site_envios (situação "autorizado"). A cada 15 minutos este robô:
  1. pega as autorizações abertas;
  2. confere que o conteúdo continua aprovado e igual ao que foi autorizado (senão, cancela);
  3. marca "enviando" ANTES de enviar — assim nunca reenvia a mesma notícia;
  4. entra no painel do site (artecon.cnt.br/admin) e preenche só o cadastro de notícias
     (título, palavras-chave, descrição, texto, categoria e capa) e clica em "Gravar notícia";
  5. procura a notícia em artecon.cnt.br/news, registra o link em "Publicações no site" e marca "publicado".

Regras combinadas com o escritório (05/10/2026), as mesmas do radar_site_admin.py:
  * só cadastrar notícias; nada de mexer em outras áreas do painel;
  * nada vai ao ar sem autorização: o robô só envia o que estiver "autorizado" no banco, e o banco só aceita
    autorização do administrador (radar_autorizar_site);
  * usuário e senha só nos segredos do GitHub (ARTECON_SITE_USUARIO e ARTECON_SITE_SENHA);
  * o "não sou um robô" (reCAPTCHA) nunca é resolvido nem contornado: se o site exigir, o robô para e avisa.

Se o envio for interrompido no meio (queda, tempo esgotado), a linha fica "enviando": nas rodadas seguintes o robô
só PROCURA a notícia no site; se não achar em 2 horas, marca "erro" e pede para conferir no painel do site antes
de autorizar de novo (para não duplicar).

v0.25.0 (etapa 6): a capa da notícia é a imagem da publicação do conteúdo (radar_conteudos.imagem_id), a mesma que vai ao Instagram e
ao Facebook; com a imagem da IA, o texto do site termina com a linha "Imagem ilustrativa gerada por IA." (para_html).

v0.32.0 (17/10/2026): o título vai ao site sem "nº" e sem "º"/"ª"/"°" depois de números ("Lei nº 15.415/2026" → "Lei 15.415/2026";
radar_site.titulo_para_o_site), porque o site monta o endereço da notícia com o título e não abre a página quando ele tem esses sinais. No
Radar, no Instagram e no Facebook o título não muda; o texto da notícia também não. Achada a notícia na lista do site, a página dela tem
de abrir com o texto: se a lista mostra a notícia (o mesmo título) e a página não abre (404, 500) ou abre sem o texto, o envio vira
"erro" com o pedido de apagá-la no painel do site e autorizar de novo — nada é reenviado sozinho (vale também para o envio "enviando").
Revisão: só quando se repete. Na primeira vez o envio continua "enviando" com a nota PAGINA_A_CONFERIR (no campo erro; a hora é o
atualizado_em) e vira "erro" só se a página continuar sem abrir numa rodada pelo menos CONFERIR_DE_NOVO depois: uma falha passageira do
site (HTTP 500 duas vezes, um 404 isolado, a página "em manutenção") não manda apagar uma notícia boa. Só o 404 e o 5xx contam
(endereco_quebrado): o 401 e o 403 (acesso recusado ao robô), o 410 e a sobrecarga (SITE_OCUPADO) não; a página que abre sem o texto tem
a sua mensagem (PAGINA_SEM_TEXTO), sem "endereço quebrado".

v0.17.0, na mesma rodada:
  * "Publicar em todos": o Instagram e o Facebook que o administrador autorizou junto com o site ficam prontos quando a
    notícia entra no site; o robô pede à função radar-redes (Supabase) que publique — a função confere tudo de novo;
  * exclusão pedida pelo administrador na aba Publicações: radar_site_excluir.py tira a notícia do site.

O registro público do GitHub Actions não recebe texto da notícia, usuário, senha nem cookie.

Uso (workflow "Radar — publicar no site"):  python radar_site_publicar.py
Variáveis: SUPABASE_URL, SUPABASE_SERVICE_KEY, ARTECON_SITE_USUARIO, ARTECON_SITE_SENHA.
"""
from __future__ import annotations

import base64
import html as html_lib
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

import radar_site
import radar_site_admin as admin
import radar_site_excluir
from radar_banco import Banco, ErroBanco, cabecalhos_da_chave
from radar_util import ErroDownload, baixar, hoje_brasilia

CADASTRO = "/admin/news/register"
ESPERA_MAXIMA = timedelta(hours=2)       # "enviando" sem achar a notícia no site depois disso: erro, conferir à mão
FONTES_PAGAS = ("itc-email",)            # v0.18.0: boletim pago (o mesmo de radar_rascunhos.FONTES_PAGAS): nunca é o link da fonte
OBSERVACAO = "Publicado pelo robô com autorização do administrador (envio nº {})."
CAMPOS = {"title", "keywords", "metadescription", "text", "category", "image"}
# v0.32.0: a lista do site mostra a notícia, mas a página dela não abre (o endereço com "º" do título: HTTP 404) ou abre sem o texto
PAGINA_QUEBRADA = ("A notícia foi gravada no site, mas a página dela não abre (endereço quebrado). Apague-a no painel do site e "
                   "autorize de novo.")
# revisão: a página abre, mas sem o texto aprovado (o site em manutenção, outra notícia com o mesmo título): não é "endereço quebrado"
PAGINA_SEM_TEXTO = ("A notícia foi gravada no site, mas a página dela abre sem o texto aprovado. Confira-a no site: se estiver errada, "
                    "apague-a no painel do site e autorize de novo; se estiver certa, registre o link à mão (sem autorizar de novo, para "
                    "não duplicar).")
# revisão: a primeira vez que a página não abre, o envio continua "enviando" com esta nota (no campo erro, que a tela não mostra enquanto
# "enviando"); vira "erro" só se a página continuar sem abrir numa rodada pelo menos CONFERIR_DE_NOVO depois da nota
PAGINA_A_CONFERIR = "A página da notícia no site ainda não abriu; o robô confere de novo na próxima rodada."
CONFERIR_DE_NOVO = timedelta(minutes=10)
SITE_OCUPADO = (408, 429, 502, 503, 504)  # página que não abriu por sobrecarga do site: não é endereço quebrado (procura de novo depois)
titulo_para_o_site = radar_site.titulo_para_o_site     # v0.32.0: o título que vai ao campo "title" do cadastro do site


def endereco_quebrado(status: int | None) -> bool:
    """Revisão: só o 404 e o erro do próprio site (5xx fora da sobrecarga) dizem que a página não abre. Sem resposta (tempo esgotado),
    o 401 e o 403 (acesso recusado ao robô), o 410 e os outros 4xx não dizem nada do endereço: não contam."""
    return status == 404 or (status is not None and 500 <= status < 600 and status not in SITE_OCUPADO)


# ------------------------------------------------------------------ texto do Radar → HTML do site
# v0.24.0: o endereço escrito no texto (o link oficial da linha "Fonte oficial" do fim — etapa 5 —, ou da seção "Fundamentação legal"
# dos textos de antes) vira link, como na prévia da tela (renderTexto): a pontuação colada no fim não faz parte do endereço, a não ser
# o ")" que fecha um "(" do próprio endereço. O robô não acrescenta chamada comercial nenhuma: só o texto aprovado, os créditos e a
# linha "Conteúdo informativo"
_ENDERECO = re.compile(r"(https?://[^\s<>\"']+)", re.I)
LINHA_INFORMATIVO = "Conteúdo informativo"         # v0.24.0: a linha do texto Informativo no fim da notícia (a mesma da tela)
# v0.25.0 (etapa 6): com a imagem da IA na publicação (a mesma no site, no Instagram e no Facebook, com o aviso desenhado no canto pela
# tela), o texto do site também termina com esta linha (a mesma da tela, LINHA_AVISO_IA)
LINHA_AVISO_IA = "Imagem ilustrativa gerada por IA."


def _ligar(t: str) -> str:
    partes = _ENDERECO.split(t)
    saida = []
    for i, p in enumerate(partes):
        if i % 2 == 0:
            saida.append(html_lib.escape(p, quote=False))
            continue
        fim = re.search(r"[.,;:!?*)]*$", p).group(0)
        while ")" in fim and p[:len(p) - len(fim)].count("(") > p[:len(p) - len(fim)].count(")"):
            fim = fim[fim.index(")") + 1:]
        u = p[:len(p) - len(fim)]
        saida.append(f'<a href="{html_lib.escape(u, quote=True)}" target="_blank" rel="noopener">{html_lib.escape(u, quote=False)}</a>'
                     + html_lib.escape(fim, quote=False))
    return "".join(saida)


def _inline(t: str) -> str:
    # negrito primeiro (sobre o texto bruto); dentro e fora dele, os endereços viram link
    return "".join(f"<strong>{_ligar(p)}</strong>" if i % 2 else _ligar(p) for i, p in enumerate(re.split(r"\*\*(.+?)\*\*", t)))


def _celulas(linha: str) -> list[str]:
    t = linha.strip()[1:]                                   # a linha começa com "|"
    if t.endswith("|") and not t.endswith("\\|"):
        t = t[:-1]
    return [p.replace("\\|", "|").strip() for p in re.split(r"(?<!\\)\|", t)]


# v0.12.0: o texto da notícia vai justificado (como na prévia e no "Copiar texto"); os créditos continuam à direita
JUSTIFICADO = "text-align:justify"


def para_html(corpo: str, autor: str | None = None, fonte: str | None = None, fonte_url: str | None = None,
              informativo: bool = False, imagem_ia: bool = False) -> str:
    """A mesma formatação da tela ("## " subtítulo, "- " lista, **negrito**, linhas com "|" tabela) e os créditos no fim.
    v0.24.0: o endereço no texto vira link, e o texto Informativo leva a linha "Conteúdo informativo" no fim. v0.25.0: com a imagem
    da IA na publicação, a linha "Imagem ilustrativa gerada por IA." por último."""
    saida, paragrafo, lista, tabela = [], [], [], []

    def fechar():
        if paragrafo:
            saida.append(f'<p style="{JUSTIFICADO}">' + "<br>".join(_inline(l) for l in paragrafo) + "</p>")
            paragrafo.clear()
        if lista:
            saida.append("<ul>" + "".join(f'<li style="{JUSTIFICADO}">{_inline(i)}</li>' for i in lista) + "</ul>")
            lista.clear()
        if tabela:
            cab, *resto = tabela
            linhas = [l for l in resto if not all(re.fullmatch(r":?-{2,}:?", c) for c in l if c)]
            saida.append("<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in cab) + "</tr></thead><tbody>" +
                          "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in l) + "</tr>" for l in linhas) + "</tbody></table>")
            tabela.clear()

    for bruta in str(corpo or "").splitlines():
        linha = bruta.rstrip()
        if not linha.strip():
            fechar()
        elif linha.startswith("## "):
            fechar()
            saida.append(f"<h2>{_inline(linha[3:].strip())}</h2>")
        elif re.match(r"\s*- ", linha):
            if paragrafo or tabela:
                fechar()
            lista.append(re.sub(r"^\s*- ", "", linha))
        elif linha.lstrip().startswith("|"):
            if paragrafo or lista:
                fechar()
            tabela.append(_celulas(linha))
        else:
            if lista or tabela:
                fechar()
            paragrafo.append(linha.strip())
    fechar()
    if autor:
        saida.append(f'<p style="text-align:right"><em>Texto elaborado por: <strong>{html_lib.escape(autor)}</strong></em></p>')
    url = fonte_url if fonte_url and re.match(r"https?://[^\s\"'<>`]+$", fonte_url) else None
    if fonte or url:                                         # v0.11.0: a fonte sai com o link da origem
        nome = html_lib.escape(fonte or url)
        saida.append(f'<p style="text-align:right"><em>Fonte: '
                     + (f'<a href="{html_lib.escape(url, quote=True)}" target="_blank" rel="noopener">{nome}</a>' if url else nome) + '</em></p>')
    if informativo:
        saida.append(f'<p style="text-align:right"><em>{LINHA_INFORMATIVO}</em></p>')
    if imagem_ia:
        saida.append(f'<p style="text-align:right"><em>{LINHA_AVISO_IA}</em></p>')
    return "\n".join(saida)


def eh_informativo(c: dict) -> bool:
    """v0.24.0: o texto Informativo (sem fundamentação legal específica): o primeiro aviso da IA começa com "INFORMATIVO"."""
    avisos = c.get("avisos_ia")
    return isinstance(avisos, list) and bool(avisos) and str(avisos[0] or "").startswith("INFORMATIVO")


def imagem_da_ia(c: dict) -> bool:
    """v0.25.0: a imagem da publicação é a imagem da IA (a tela a grava como a ilustração do conteúdo: imagem_id = ilustracao_id), com o
    aviso no canto. A capa montada antes da v0.25.0 com a ilustração ao fundo (imagem_id diferente) não conta: nela o aviso é o que a
    equipe escreveu no texto, como antes."""
    return bool(c.get("imagem_id")) and c.get("imagem_id") == c.get("ilustracao_id")


def texto_simples(corpo: str) -> str:
    t = re.sub(r"^\s*(## |- |\|)", "", str(corpo or ""), flags=re.M).replace("**", "").replace("|", " ")
    return " ".join(t.split())


def resumo(corpo: str, limite: int = 155) -> str:
    t = texto_simples(corpo)
    if len(t) <= limite:
        return t
    corte = t[:limite].rsplit(" ", 1)[0].rstrip(",;:—-")
    return corte + "…"


# ------------------------------------------------------------------ o formulário do site
def formulario_cadastro(html: str, base: str) -> tuple[str, dict, dict, dict]:
    """(endereço de envio, campos a enviar por padrão, opções da categoria {rótulo: valor}, campos {nome: tipo})."""
    sopa = BeautifulSoup(html or "", "lxml")
    for f in sopa.find_all("form"):
        nomes = {c.get("name") for c in f.find_all(["input", "select", "textarea"]) if c.get("name")}
        if not {"title", "text", "category"} <= nomes:
            continue
        padrao, tipos, categorias = {}, {}, {}
        for c in f.find_all(["input", "select", "textarea"]):
            nome = c.get("name")
            if not nome:
                continue
            tipo = c.name if c.name != "input" else (c.get("type") or "text").lower()
            if tipo in ("submit", "button", "image", "reset"):
                continue
            tipos[nome] = tipo
            if nome in CAMPOS:
                if nome == "category":
                    for o in c.find_all("option"):
                        rotulo = " ".join(o.get_text(" ").split())
                        if rotulo and (o.get("value") or "").strip():
                            categorias[rotulo] = o.get("value")
                continue
            # campo que o Radar não conhece: obrigatório e sem valor é sinal de que o formulário mudou — para
            if tipo == "hidden":
                padrao[nome] = c.get("value") or ""
            elif tipo == "select":
                o = c.find("option", selected=True) or c.find("option")
                if o is not None and (o.get("value") or "") != "":
                    padrao[nome] = o.get("value")
                elif c.has_attr("required"):
                    raise admin.Parada(f"o formulário de cadastro tem um campo novo obrigatório ({nome}); o robô não envia sem conferir")
            elif tipo in ("checkbox", "radio"):
                if c.has_attr("checked"):
                    padrao[nome] = c.get("value") or "on"
                elif c.has_attr("required"):
                    raise admin.Parada(f"o formulário de cadastro tem um campo novo obrigatório ({nome}); o robô não envia sem conferir")
            elif c.has_attr("required") and not (c.get("value") or c.get_text()):
                raise admin.Parada(f"o formulário de cadastro tem um campo novo obrigatório ({nome}); o robô não envia sem conferir")
            elif c.get("value"):
                padrao[nome] = c.get("value")
        acao = requests.compat.urljoin(base, f.get("action") or base)
        if not admin.mesmo_site(acao) or (f.get("method") or "get").lower() != "post":
            raise admin.Parada("o formulário de cadastro aponta para fora do site ou não é de envio (POST)")
        return acao, padrao, categorias, tipos
    raise admin.Parada("não achei o formulário de cadastro de notícias (campos title, text e category) em " + CADASTRO)


def imagem_do_banco(dados: str | None) -> tuple[str, bytes, str] | None:
    m = re.match(r"data:image/(jpeg|png|webp);base64,(.+)$", str(dados or ""), re.S)
    if not m:
        return None
    ext = {"jpeg": "jpg"}.get(m.group(1), m.group(1))
    return f"capa-radar.{ext}", base64.b64decode(m.group(2)), f"image/{m.group(1)}"


# ------------------------------------------------------------------ o banco
def _quando(valor) -> datetime | None:
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00")) if valor else None
    except ValueError:
        return None


class SiteFora(Exception):
    """O site não respondeu antes do envio (fora do ar, lento): nada foi enviado; a autorização continua valendo."""


class PaginaQuebrada(Exception):
    """v0.32.0: a lista do site mostra a notícia (o mesmo título), mas a página dela não abre ou abre sem o texto (sem_texto)."""

    def __init__(self, url: str, sem_texto: bool = False):
        super().__init__(url)
        self.url, self.sem_texto = url, sem_texto


class Publicador:
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
        return texto[:900]

    def marcar(self, envio: dict, de: str, **campos) -> bool:
        """Muda a situação só se ela ainda for `de` (o administrador pode ter cancelado enquanto isso)."""
        campos["atualizado_em"] = self.agora().isoformat()
        if "erro" in campos and campos["erro"]:
            campos["erro"] = self._limpo(campos["erro"])
        linhas = self.banco._pedir("PATCH", "radar_site_envios", params={"id": f"eq.{envio['id']}", "situacao": f"eq.{de}"},
                                   corpo=campos, prefer="return=representation")
        return bool(linhas)

    def conteudo(self, conteudo_id: int) -> dict | None:
        linhas = self.banco._pedir("GET", "radar_conteudos", params={
            "select": "id,assunto_id,titulo,corpo,status,atualizado_em,aprovado_em,fora_do_site,imagem_id,ilustracao_id,autor,fonte_credito,avisos_ia,"
                      "radar_divulgacoes!left(id,url)",
            "id": f"eq.{conteudo_id}"}) or []
        return linhas[0] if linhas else None

    # -------------------------------------------------------------- o site
    def entrar(self):
        if not self.logado:
            admin.entrar(self.sessao, self.usuario, self.senha)
            self.logado = True

    def preparar(self, envio: dict, c: dict) -> tuple[str, dict, dict | None]:
        """Login, página de cadastro e campos preenchidos — tudo ANTES de marcar "enviando": falha aqui não envia nada."""
        try:
            self.entrar()
            r = self.sessao.get(admin.BASE + CADASTRO, timeout=40)
        except requests.RequestException as e:
            raise SiteFora(f"o site não respondeu ({type(e).__name__})") from e
        if r.status_code >= 500:
            raise SiteFora(f"o site respondeu HTTP {r.status_code}")
        if r.status_code >= 400 or not admin.mesmo_site(r.url):
            raise admin.Parada(f"a página de cadastro de notícias não abriu (HTTP {r.status_code})")
        acao, dados, categorias, tipos = formulario_cadastro(r.text, r.url)
        if any(t == "password" for t in tipos.values()):
            raise admin.Parada("o site pediu login de novo ao abrir o cadastro")
        valor = categorias.get(envio["categoria"])
        if not valor:
            raise admin.Parada(f"a categoria \"{envio['categoria']}\" não existe mais no site; escolha outra e autorize de novo")
        dados.update({"title": titulo_para_o_site(c["titulo"]), "text": para_html(c["corpo"], c.get("autor"), c.get("fonte_credito"), self.link_fonte(c), eh_informativo(c),
                                                              imagem_da_ia(c)),
                      "category": valor})
        if "keywords" in tipos:
            dados["keywords"] = ", ".join(x for x in (envio["categoria"], c.get("fonte_credito") or "", "Artecon") if x)[:250]
        if "metadescription" in tipos:
            dados["metadescription"] = resumo(c["corpo"])
        arquivos = None
        if tipos.get("image") == "file" and c.get("imagem_id"):
            dados_capa = self.banco.capa(c["imagem_id"])                          # v0.21.0: pela vista radar_v_capas
            arquivo = imagem_do_banco(dados_capa) if dados_capa else None
            if arquivo:
                arquivos = {"image": arquivo}
        return acao, dados, arquivos

    def link_fonte(self, c: dict) -> str | None:
        """Link da notícia ou norma de origem: a captura de fonte oficial do assunto (ou, sem ela, a primeira). v0.18.0: o boletim
        pago fica por último (o campo Fonte não o cita; o link não pode levar a ele quando há outra captura)."""
        vinc = self.banco._pedir("GET", "radar_assunto_capturas", params={
            "select": "radar_capturas(id,url,radar_fontes(oficial,slug))", "assunto_id": f"eq.{c['assunto_id']}"}) or []
        caps = sorted((v["radar_capturas"] for v in vinc if v.get("radar_capturas")),
                      key=lambda x: ((x.get("radar_fontes") or {}).get("slug") in FONTES_PAGAS,
                                     not (x.get("radar_fontes") or {}).get("oficial"), x["id"]))
        if not caps:
            return None
        partes = urlsplit(caps[0]["url"])
        if "radar" in parse_qs(partes.query):               # boletim por e-mail: o endereço é só um marcador interno
            return urlunsplit((partes.scheme, partes.netloc, partes.path or "/", "", ""))
        return caps[0]["url"]

    def enviar(self, envio: dict, acao: str, dados: dict, arquivos):
        """O único passo que pode ter chegado ao site mesmo dando erro: depois dele, nunca "erro" direto."""
        resposta = self.sessao.post(acao, data=dados, files=arquivos, timeout=90, allow_redirects=True)
        if resposta.status_code >= 400:
            self.feito.append(f"envio {envio['id']}: o site respondeu HTTP {resposta.status_code} ao gravar")

    def procurar(self, c: dict) -> str | None:
        """O link da notícia em artecon.cnt.br/news que corresponde ao conteúdo (o mesmo critério do registro automático).
        v0.32.0: a página tem de abrir com o texto. Se nenhuma abre e a lista mostra uma notícia com o mesmo título (o do Radar ou o
        que vai ao site) cuja página não abre (HTTP 404, 500...: endereco_quebrado) ou abre sem o texto, levanta PaginaQuebrada (quem
        chama decide se já é "erro": pagina_quebrada)."""
        cfg = radar_site.configuracao(self.banco)
        registrados = {radar_site.chave_url(r["url"]) for r in self.banco.links_publicados() if r.get("url")}
        alvo = {"id": c["id"], "titulo": c["titulo"], "corpo": c["corpo"], "aprovado_em": c.get("aprovado_em")}
        titulos = {radar_site_excluir.titulo_normal(t).rstrip(" .") for t in (c["titulo"], titulo_para_o_site(c["titulo"]))}
        aprovado, quebrada, sem_texto = radar_site.dia_brasilia(c.get("aprovado_em")), None, None
        for item in radar_site.noticias_da_lista(self.baixar(cfg["lista"]), cfg["lista"], cfg["padrao"], int(cfg["max_noticias"])):
            url = item["url"]
            if radar_site.chave_url(url) in registrados or not radar_site.no_site(url, cfg):
                continue
            na_lista = any(radar_site_excluir.titulo_normal(t).rstrip(" .") in titulos for t in item["textos"])
            try:
                noticia = radar_site.ler_noticia(self.baixar(url))
            except ErroDownload as e:
                if na_lista and endereco_quebrado(e.http_status):
                    quebrada = quebrada or url              # a lista mostra a notícia, mas a página não abre
                continue
            if radar_site.escolher(noticia, [alvo]):
                return url
            if na_lista and not (noticia["data"] and aprovado and noticia["data"] < aprovado) and \
                    radar_site.contido(c["corpo"], noticia["texto"]) < radar_site.TEXTO_COM_TITULO:
                sem_texto = sem_texto or url                # abre, mas sem o texto (e não é uma notícia de antes da aprovação)
        if quebrada or sem_texto:
            raise PaginaQuebrada(quebrada or sem_texto, sem_texto=not quebrada)
        return None

    def pagina_quebrada(self, envio: dict, q: PaginaQuebrada):
        """v0.32.0: gravada no site, mas a página não abre (ou abre sem o texto): "erro" para o administrador apagar no painel e
        autorizar de novo (nunca reenvia sozinho, para não duplicar). Revisão: só quando se repete — na primeira vez fica "enviando" com
        a nota PAGINA_A_CONFERIR; vira "erro" se a página continuar assim numa rodada pelo menos CONFERIR_DE_NOVO depois da nota (a hora
        da nota é o atualizado_em do envio, que o robô grava com ela)."""
        nota = self._limpo(PAGINA_A_CONFERIR)
        desde = _quando(envio.get("atualizado_em")) if envio.get("erro") == nota else None
        if desde is not None and self.agora() - desde >= CONFERIR_DE_NOVO:
            self.marcar(envio, "enviando", situacao="erro", erro=PAGINA_SEM_TEXTO if q.sem_texto else PAGINA_QUEBRADA)
            self.feito.append(f"envio {envio['id']}: gravado no site, mas a página da notícia " + ("abre sem o texto" if q.sem_texto else "não abre"))
            return
        if desde is None:
            self.marcar(envio, "enviando", erro=PAGINA_A_CONFERIR)
        self.feito.append(f"envio {envio['id']}: a notícia está na lista do site, mas a página dela ainda não abriu; confere de novo na próxima rodada")

    def concluir(self, envio: dict, c: dict, url: str):
        erro = None
        try:
            self.banco.registrar_divulgacao(c["id"], url, hoje_brasilia(), OBSERVACAO.format(envio["id"]))
        except ErroBanco as e:
            erro = f"Publicado no site, mas o registro em \"Publicações no site\" foi recusado: {e}"
        self.marcar(envio, "enviando", situacao="publicado", url=url, erro=erro)
        self.feito.append(f"envio {envio['id']}: publicado")

    # -------------------------------------------------------------- a rodada
    def executar(self) -> list[str]:
        # v0.45.0: a autorização com HORA MARCADA (agendado_para) só entra quando a hora chega; a "enviando" entra sempre
        agora = datetime.now(timezone.utc).isoformat()
        envios = self.banco._pedir("GET", "radar_site_envios", params={
            "select": "id,conteudo_id,categoria,conteudo_lido_em,situacao,enviado_em,erro,atualizado_em", "situacao": "in.(autorizado,enviando)",
            "or": f"(agendado_para.is.null,agendado_para.lte.{agora},situacao.eq.enviando)",
            "order": "id"}) or []
        fora = False
        for envio in envios:
            if fora and envio["situacao"] == "autorizado":
                continue                                    # site fora do ar: as autorizadas esperam a próxima rodada
            try:
                self.um(envio)
            except SiteFora as e:                           # nada foi enviado: continua autorizado, tenta na próxima rodada
                self.feito.append(f"envio {envio['id']}: {e}; tenta de novo na próxima rodada")
                fora = True
            except admin.Parada as e:                       # nada foi enviado: pode autorizar de novo depois de resolver
                self.feito.append(f"envio {envio['id']}: parou")
                self.marcar(envio, envio["situacao"], situacao="erro", erro=f"Não publicado: {e}.")
                if "reCAPTCHA" in str(e) or "login" in str(e):
                    break                                   # sem login, as outras também não vão
            except Exception as e:                          # imprevisto: registra e segue com as outras (o estado fica como estava)
                self.feito.append(self._limpo(f"envio {envio['id']}: erro inesperado ({type(e).__name__}: {e})"))
        return self.feito

    def um(self, envio: dict):
        c = self.conteudo(envio["conteudo_id"])
        if envio["situacao"] == "enviando":                 # rodada anterior interrompida: só procura, nunca reenvia
            registrado = (c or {}).get("radar_divulgacoes") or []
            try:
                url = registrado[-1]["url"] if registrado else (self.procurar(c) if c else None)
            except PaginaQuebrada as q:                     # v0.32.0: está na lista, mas a página não abre
                self.pagina_quebrada(envio, q)
                return
            if registrado:                                  # a coleta (radar_site.py) já achou e registrou a notícia
                self.marcar(envio, "enviando", situacao="publicado", url=url, erro=None)
                self.feito.append(f"envio {envio['id']}: publicado (registro já feito pela coleta)")
            elif url:
                self.concluir(envio, c, url)
            elif (self.agora() - (_quando(envio.get("enviado_em")) or self.agora())) > ESPERA_MAXIMA:
                self.marcar(envio, "enviando", situacao="erro", erro="O envio ao site foi interrompido e a notícia não apareceu em "
                            "artecon.cnt.br/news. Confira no painel do site se ela foi gravada antes de autorizar de novo (para não duplicar).")
                self.feito.append(f"envio {envio['id']}: não achado no site")
            return
        motivo = None
        if c is None:
            motivo = "o conteúdo não existe mais"
        elif c["status"] != "aprovado":
            motivo = "o conteúdo não está mais aprovado"
        elif c["fora_do_site"]:
            motivo = "o conteúdo foi marcado como \"não vai ao site\""
        elif _quando(c["atualizado_em"]) != _quando(envio["conteudo_lido_em"]):
            motivo = "o conteúdo mudou depois de autorizado"
        elif c.get("radar_divulgacoes"):
            motivo = "o conteúdo já tem publicação registrada no site"
        else:                                               # o assunto pode ter perdido a confirmação ou o trecho oficial depois
            pendencia = self.banco._pedir("POST", "rpc/radar_pendencia_assunto", corpo={"p_assunto": c["assunto_id"]})
            if pendencia:
                motivo = "o assunto deixou de cumprir as exigências do site (" + re.sub(r"^RADAR\d+:\s*", "", str(pendencia))[:200] + ")"
        if motivo:
            self.marcar(envio, "autorizado", situacao="cancelado", erro=f"Autorização cancelada pelo robô: {motivo}. Confira e autorize de novo.")
            self.feito.append(f"envio {envio['id']}: cancelado")
            return
        acao, dados, arquivos = self.preparar(envio, c)     # login e formulário antes: se falhar, nada foi enviado
        if not self.marcar(envio, "autorizado", situacao="enviando", enviado_em=self.agora().isoformat()):
            return                                          # cancelado pelo administrador agora há pouco
        envio = dict(envio, situacao="enviando")
        try:
            self.enviar(envio, acao, dados, arquivos)
        except requests.RequestException as e:
            # pode ter chegado ao site ou não: fica "enviando" e as próximas rodadas procuram a notícia
            self.feito.append(f"envio {envio['id']}: sem resposta do site ({type(e).__name__}); vai procurar na próxima rodada")
            return
        try:
            url = self.procurar(c)
        except ErroDownload:
            url = None
        except PaginaQuebrada as q:                         # v0.32.0: gravada, mas a página da notícia não abre (ainda)
            self.pagina_quebrada(dict(envio, erro=None), q)  # logo depois do envio: é sempre a primeira vez
            return
        if url:
            self.concluir(envio, c, url)
        else:
            self.feito.append(f"envio {envio['id']}: enviado; a notícia ainda não apareceu na lista do site")


# ------------------------------------------------------------------ v0.17.0: as redes autorizadas junto com o site
NOME_REDE = {"instagram": "Instagram", "facebook": "Facebook"}


def publicar_redes(banco: Banco, url: str, chave: str, post=requests.post) -> list[str]:
    """Pede à função radar-redes que publique o Instagram e o Facebook autorizados junto com o site ("Publicar em todos")
    e que já estão prontos (a notícia entrou no site). A função confere de novo as exigências e registra o resultado."""
    envios = banco._pedir("GET", "radar_redes_envios", params={
        "select": "id,canal", "situacao": "eq.autorizado", "junto_com_site": "eq.true", "order": "id"}) or []
    feito = []
    for e in envios:
        nome = NOME_REDE.get(e["canal"], e["canal"])
        try:
            r = post(url.rstrip("/") + "/functions/v1/radar-redes", json={"acao": "publicar", "envio": e["id"]}, timeout=170,
                     headers=cabecalhos_da_chave(chave) | {"Content-Type": "application/json"})      # v0.22.0: sb_secret_ só no apikey
            dados = r.json() if r.text else {}
        except (requests.RequestException, ValueError) as x:
            feito.append(f"{nome} (envio {e['id']}): sem resposta da função radar-redes ({type(x).__name__}); confira na tela")
            continue
        if r.status_code >= 400:
            feito.append(f"{nome} (envio {e['id']}): {str(dados.get('message') or f'HTTP {r.status_code}')[:200]}")
        else:
            feito.append(f"{nome} (envio {e['id']}): {dados.get('situacao', '?')}")
    return feito


def main() -> int:
    url, chave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    usuario, senha = os.environ.get("ARTECON_SITE_USUARIO", ""), os.environ.get("ARTECON_SITE_SENHA", "")
    if not (url and chave):
        print("Publicar no site: sem as chaves do banco; nada a fazer.")
        return 0
    banco = Banco(url, chave)
    if not (usuario and senha):
        print("Publicar no site: faltam os segredos ARTECON_SITE_USUARIO e ARTECON_SITE_SENHA no GitHub.")
        return 1
    p = Publicador(banco, usuario, senha)
    try:
        feito = p.executar()
    except (ErroBanco, requests.RequestException) as e:
        print("! publicar no site: " + p._limpo(f"{type(e).__name__}: {e}"), file=sys.stderr)
        return 1
    print("Publicar no site: " + ("; ".join(feito) if feito else "nenhuma autorização pendente."))
    erro = 0
    try:                                                    # v0.17.0: Instagram e Facebook que iam junto com o site
        redes = publicar_redes(banco, url, chave)
        if redes:
            print("Instagram e Facebook junto com o site: " + "; ".join(redes))
    except ErroBanco as e:
        print("! redes junto com o site: " + p._limpo(str(e)), file=sys.stderr)
        erro = 1
    ex = radar_site_excluir.Excluidor(banco, usuario, senha, sessao=p.sessao)
    ex.logado = p.logado                                    # aproveita o login da publicação, se houve
    try:                                                    # v0.17.0: exclusões pedidas pelo administrador
        excluidas = ex.executar()
        if excluidas:
            print("Excluir do site: " + "; ".join(excluidas))
    except (ErroBanco, requests.RequestException) as e:
        print("! excluir do site: " + ex._limpo(f"{type(e).__name__}: {e}"), file=sys.stderr)
        erro = 1
    return erro


if __name__ == "__main__":
    sys.exit(main())
