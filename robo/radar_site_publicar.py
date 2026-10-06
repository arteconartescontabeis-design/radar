"""Radar Artecon — publicação no site da Artecon com autorização (v0.10.0).

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
from radar_banco import Banco, ErroBanco
from radar_util import ErroDownload, baixar, hoje_brasilia

CADASTRO = "/admin/news/register"
ESPERA_MAXIMA = timedelta(hours=2)       # "enviando" sem achar a notícia no site depois disso: erro, conferir à mão
OBSERVACAO = "Publicado pelo robô com autorização do administrador (envio nº {})."
CAMPOS = {"title", "keywords", "metadescription", "text", "category", "image"}


# ------------------------------------------------------------------ texto do Radar → HTML do site
def _inline(t: str) -> str:
    t = html_lib.escape(t, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)


def _celulas(linha: str) -> list[str]:
    t = linha.strip()[1:]                                   # a linha começa com "|"
    if t.endswith("|") and not t.endswith("\\|"):
        t = t[:-1]
    return [p.replace("\\|", "|").strip() for p in re.split(r"(?<!\\)\|", t)]


# v0.12.0: o texto da notícia vai justificado (como na prévia e no "Copiar texto"); os créditos continuam à direita
JUSTIFICADO = "text-align:justify"


def para_html(corpo: str, autor: str | None = None, fonte: str | None = None, fonte_url: str | None = None) -> str:
    """A mesma formatação da tela ("## " subtítulo, "- " lista, **negrito**, linhas com "|" tabela) e os créditos no fim."""
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
    return "\n".join(saida)


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
            "select": "id,assunto_id,titulo,corpo,status,atualizado_em,aprovado_em,fora_do_site,imagem_id,autor,fonte_credito,radar_divulgacoes!left(id,url)",
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
        dados.update({"title": c["titulo"], "text": para_html(c["corpo"], c.get("autor"), c.get("fonte_credito"), self.link_fonte(c)),
                      "category": valor})
        if "keywords" in tipos:
            dados["keywords"] = ", ".join(x for x in (envio["categoria"], c.get("fonte_credito") or "", "Artecon") if x)[:250]
        if "metadescription" in tipos:
            dados["metadescription"] = resumo(c["corpo"])
        arquivos = None
        if tipos.get("image") == "file" and c.get("imagem_id"):
            img = self.banco._pedir("GET", "radar_imagens", params={"select": "dados", "id": f"eq.{c['imagem_id']}"}) or []
            arquivo = imagem_do_banco(img[0]["dados"]) if img else None
            if arquivo:
                arquivos = {"image": arquivo}
        return acao, dados, arquivos

    def link_fonte(self, c: dict) -> str | None:
        """Link da notícia ou norma de origem: a captura de fonte oficial do assunto (ou, sem ela, a primeira)."""
        vinc = self.banco._pedir("GET", "radar_assunto_capturas", params={
            "select": "radar_capturas(id,url,radar_fontes(oficial))", "assunto_id": f"eq.{c['assunto_id']}"}) or []
        caps = sorted((v["radar_capturas"] for v in vinc if v.get("radar_capturas")),
                      key=lambda x: (not (x.get("radar_fontes") or {}).get("oficial"), x["id"]))
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
        """O link da notícia em artecon.cnt.br/news que corresponde ao conteúdo (o mesmo critério do registro automático)."""
        cfg = radar_site.configuracao(self.banco)
        registrados = {radar_site.chave_url(r["url"]) for r in self.banco.links_publicados() if r.get("url")}
        alvo = {"id": c["id"], "titulo": c["titulo"], "corpo": c["corpo"], "aprovado_em": c.get("aprovado_em")}
        for url in radar_site.links_da_lista(self.baixar(cfg["lista"]), cfg["lista"], cfg["padrao"], int(cfg["max_noticias"])):
            if radar_site.chave_url(url) in registrados or not radar_site.no_site(url, cfg):
                continue
            try:
                noticia = radar_site.ler_noticia(self.baixar(url))
            except ErroDownload:
                continue
            if radar_site.escolher(noticia, [alvo]):
                return url
        return None

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
        envios = self.banco._pedir("GET", "radar_site_envios", params={
            "select": "id,conteudo_id,categoria,conteudo_lido_em,situacao,enviado_em", "situacao": "in.(autorizado,enviando)",
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
            url = registrado[-1]["url"] if registrado else (self.procurar(c) if c else None)
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
        if url:
            self.concluir(envio, c, url)
        else:
            self.feito.append(f"envio {envio['id']}: enviado; a notícia ainda não apareceu na lista do site")


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
    return 0


if __name__ == "__main__":
    sys.exit(main())
