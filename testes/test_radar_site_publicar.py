"""Robô de publicação no site (v0.10.0): só envia o que o administrador autorizou, nunca reenvia e registra o link.

Banco real (PostgreSQL + PostgREST) e um site da Artecon de mentira, servido localmente, com o mesmo formulário
de /admin/news/register (title, keywords, metadescription, text, category, image).
"""
from __future__ import annotations

import re
import threading
from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import pytest

import radar_site_admin
import radar_site_publicar as pub
from conftest import ADMIN, EDITOR, como, jwt, API
from radar_banco import Banco
from radar_util import hoje_brasilia
from test_radar_banco import aprovar, cenario_publicavel

PORTA = 3997
BASE = f"http://127.0.0.1:{PORTA}"
MESES = "Janeiro Fevereiro Março Abril Maio Junho Julho Agosto Setembro Outubro Novembro Dezembro".split()
SITE = {"noticias": [], "envios": [], "logins": 0, "exigir_captcha": False, "publicar": True, "categorias": None, "fora": False}
FORM = """<form method="post" action="/admin/news/register" enctype="multipart/form-data">
  <input type="hidden" name="_token" value="tok123">
  <label for="t">Título</label><input id="t" name="title" type="text" required>
  <input name="keywords" type="text"><textarea name="metadescription"></textarea><textarea name="text"></textarea>
  <select name="category" required><option value="">Selecione</option>{opcoes}</select>
  <input name="image" type="file"><button type="submit">Gravar notícia</button></form>"""
LOGIN = """<html><script src="https://www.google.com/recaptcha/api.js"></script><form method="post" action="/admin/signin">
  <input type="hidden" name="_token" value="tok123"><input name="email" type="email"><input name="password" type="password">
  <div class="g-recaptcha"></div><button>Entrar</button></form></html>"""


class Site(BaseHTTPRequestHandler):
    def _html(self, status, corpo, extras=()):
        dados = corpo.encode()
        self.send_response(status)
        for k, v in extras:
            self.send_header(k, v)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _logado(self):
        return "sessao=ok" in (self.headers.get("Cookie") or "")

    def do_GET(self):
        if SITE["fora"] and self.path.startswith("/admin"):
            return self._html(503, "fora do ar")
        if self.path == "/admin/signin":
            return self._html(200, LOGIN)
        if self.path == "/admin":
            return self._html(200, "<a href='/admin/news'>Notícias</a>" if self._logado() else LOGIN)
        if self.path == "/admin/news":
            return self._html(200, "<h1>Notícias</h1>" if self._logado() else LOGIN)
        if self.path == "/admin/news/register":
            if not self._logado():
                return self._html(302, "", [("Location", "/admin/signin")])
            cats = SITE["categorias"] or ["IRRF", "Simples Nacional", "Tributário"]
            return self._html(200, FORM.format(opcoes="".join(f"<option value='{i + 1}'>{c}</option>" for i, c in enumerate(cats))))
        if self.path == "/news":
            return self._html(200, "".join(f"<div><a href='/news/view/{n['slug']}'>LEIA</a></div>" for n in reversed(SITE["noticias"])))
        m = re.fullmatch(r"/news/view/(.+)", self.path)
        if m:
            n = next((n for n in SITE["noticias"] if n["slug"] == m.group(1)), None)
            if n:
                d = hoje_brasilia()
                return self._html(200, f"<html><head><meta property='og:title' content='{n['title']}'></head><body>"
                                       f"<p>Publicada em {d.day:02d} de {MESES[d.month - 1]} de {d.year}</p>{n['text']}</body></html>")
        return self._html(404, "nao encontrado")

    def do_POST(self):
        bruto = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/admin/signin":
            SITE["logins"] += 1
            dados = {k: v[0] for k, v in parse_qs(bruto.decode()).items()}
            if SITE["exigir_captcha"] or dados.get("email") != "robo@artecon" or dados.get("password") != "s3nha":
                return self._html(200, LOGIN)
            return self._html(302, "", [("Location", "/admin"), ("Set-Cookie", "sessao=ok; Path=/")])
        if self.path == "/admin/news/register" and self._logado():
            msg = BytesParser(policy=HTTP).parsebytes(b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + bruto)
            campos = {}
            for parte in msg.iter_parts():
                nome = parte.get_param("name", header="content-disposition")
                bruto_parte = parte.get_payload(decode=True)
                campos[nome] = (parte.get_filename(), bruto_parte) if parte.get_filename() else bruto_parte.decode("utf-8")
            SITE["envios"].append(campos)
            if SITE["publicar"]:
                SITE["noticias"].append({"slug": f"noticia-{len(SITE['noticias']) + 1}", "title": campos["title"], "text": campos["text"]})
            return self._html(302, "", [("Location", "/admin/news")])
        return self._html(403, "proibido")

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def site():
    servidor = ThreadingHTTPServer(("127.0.0.1", PORTA), Site)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    antes = radar_site_admin.BASE, radar_site_admin.LOGIN
    radar_site_admin.BASE, radar_site_admin.LOGIN = BASE, BASE + "/admin/signin"
    yield
    radar_site_admin.BASE, radar_site_admin.LOGIN = antes
    servidor.shutdown()


@pytest.fixture()
def cenario(api_postgrest, site, limpo):
    SITE.update(noticias=[], envios=[], logins=0, exigir_captcha=False, publicar=True, categorias=None, fora=False)
    limpo.execute("insert into radar_config (chave, valor) values ('site', %s::jsonb) "
                  "on conflict (chave) do update set valor = excluded.valor", (f'{{"lista": "{BASE}/news"}}',))
    yield limpo
    limpo.execute("delete from radar_config where chave = 'site'")


CORPO = ("O Comitê Gestor do Simples Nacional estendeu o prazo para as empresas optarem pelo regime em 2027. "
         "Agora a opção pode ser feita até **31 de janeiro de 2027**, tanto por quem está começando quanto por quem já funciona.\n\n"
         "## Quem pode optar\n- **Empresas novas**: dentro do prazo de abertura\n- **Empresas em atividade**: até o fim de janeiro\n\n"
         "## Análise Artecon\nA medida dá mais tempo para quem ainda compara os regimes e quer decidir com os números do ano fechados.")
from test_radar_banco import PIXEL as CAPA                                 # noqa: E402


def autorizado(db, categoria="Simples Nacional"):
    a, c = cenario_publicavel(db)
    img = db.execute("insert into radar_imagens (dados) values (%s) returning id", (CAPA,)).fetchone()[0]
    db.execute("update radar_conteudos set titulo = 'Prazo de opção pelo Simples Nacional vai até 31 de janeiro de 2027', "
               "corpo = %s, autor = 'Equipe Artecon', fonte_credito = 'Receita Federal', imagem_id = %s where id = %s", (CORPO, img, c))
    aprovar(c)
    lido = db.execute("select atualizado_em from radar_conteudos where id = %s", (c,)).fetchone()[0]
    with como("authenticated", ADMIN) as x:
        envio = x.execute("select radar_autorizar_site(%s, %s, %s)", (c, categoria, lido)).fetchone()[0]
    return c, envio


def rodar(agora=None):
    banco = Banco(API, jwt("service_role"), prefixo="")
    return pub.Publicador(banco, "robo@artecon", "s3nha", agora=agora).executar()


def situacao(db, envio):
    return db.execute("select situacao, url, erro from radar_site_envios where id = %s", (envio,)).fetchone()


def test_publica_so_o_autorizado_registra_o_link_e_nunca_reenvia(cenario):
    assert rodar() == [] and SITE["logins"] == 0                         # sem autorização, nem entra no site
    c, envio = autorizado(cenario)
    feito = rodar()
    assert feito == [f"envio {envio}: publicado"] and len(SITE["envios"]) == 1
    e = SITE["envios"][0]
    assert e["_token"] == "tok123" and e["category"] == "2" and e["title"].startswith("Prazo de opção pelo Simples")
    assert "<h2>Quem pode optar</h2>" in e["text"] and "<strong>31 de janeiro de 2027</strong>" in e["text"]
    assert "Texto elaborado por: <strong>Equipe Artecon</strong>" in e["text"] and "Fonte: Receita Federal" in e["text"]
    assert e["image"][0] == "capa-radar.png" and e["image"][1].startswith(b"\x89PNG")
    assert len(e["metadescription"]) <= 160 and "**" not in e["metadescription"]
    assert situacao(cenario, envio) == ("publicado", BASE + "/news/view/noticia-1", None)
    url, obs = cenario.execute("select url, observacao from radar_divulgacoes where conteudo_id = %s", (c,)).fetchone()
    assert url == BASE + "/news/view/noticia-1" and f"envio nº {envio}" in obs
    assert rodar() == [] and len(SITE["envios"]) == 1                     # nada mais a fazer: não reenvia


def test_conteudo_mudado_ou_cancelado_nao_vai_ao_site(cenario):
    c, envio = autorizado(cenario)
    with como("authenticated", ADMIN) as x:
        assert x.execute("select radar_cancelar_site(%s)", (envio,)).fetchone()[0] is True
    assert rodar() == [] and SITE["envios"] == []
    # o banco cancela sozinho quando o texto muda; o robô ainda confere, para o caso de a linha escapar
    lido = cenario.execute("select atualizado_em from radar_conteudos where id = %s", (c,)).fetchone()[0]
    with como("authenticated", ADMIN) as x:
        envio = x.execute("select radar_autorizar_site(%s, 'Simples Nacional', %s)", (c, lido)).fetchone()[0]
    cenario.execute("alter table radar_conteudos disable trigger radar_tg_conteudo_envio")
    try:
        cenario.execute("update radar_conteudos set atualizado_em = now() + interval '1 second' where id = %s", (c,))
        assert rodar() == [f"envio {envio}: cancelado"]
    finally:
        cenario.execute("alter table radar_conteudos enable trigger radar_tg_conteudo_envio")
    assert situacao(cenario, envio)[0] == "cancelado" and "mudou depois de autorizado" in situacao(cenario, envio)[2]
    assert SITE["envios"] == []


def test_captcha_ou_categoria_sumida_param_sem_enviar(cenario):
    c, envio = autorizado(cenario)
    SITE["exigir_captcha"] = True
    assert rodar() == [f"envio {envio}: parou"] and SITE["envios"] == []
    s = situacao(cenario, envio)
    assert s[0] == "erro" and "reCAPTCHA" in s[2] and "s3nha" not in s[2] and "robo@artecon" not in s[2]
    SITE["exigir_captcha"] = False
    lido = cenario.execute("select atualizado_em from radar_conteudos where id = %s", (c,)).fetchone()[0]
    with como("authenticated", ADMIN) as x:
        envio = x.execute("select radar_autorizar_site(%s, 'Legislação Municipal', %s)", (c, lido)).fetchone()[0]
    assert rodar() == [f"envio {envio}: parou"] and SITE["envios"] == []
    assert "Legislação Municipal" in situacao(cenario, envio)[2]


def test_envio_interrompido_so_procura_e_depois_pede_conferencia(cenario):
    c, envio = autorizado(cenario)
    SITE["publicar"] = False                                             # o site gravou, mas a notícia não aparece na lista
    assert rodar() == [f"envio {envio}: enviado; a notícia ainda não apareceu na lista do site"]
    assert situacao(cenario, envio)[0] == "enviando" and len(SITE["envios"]) == 1
    assert rodar() == [] and len(SITE["envios"]) == 1                     # só procura: nunca reenvia
    SITE["noticias"].append({"slug": "apareceu", "title": SITE["envios"][0]["title"], "text": SITE["envios"][0]["text"]})
    assert rodar() == [f"envio {envio}: publicado"] and situacao(cenario, envio)[1] == BASE + "/news/view/apareceu"
    # outro, que nunca aparece: depois de 2 horas vira erro com o pedido de conferência
    SITE["noticias"].clear()
    cenario.execute("delete from radar_divulgacoes")
    cenario.execute("update radar_site_envios set situacao = 'enviando', enviado_em = now() - interval '3 hours', url = null where id = %s", (envio,))
    assert rodar() == [f"envio {envio}: não achado no site"]
    assert situacao(cenario, envio)[0] == "erro" and "antes de autorizar de novo" in situacao(cenario, envio)[2]


def test_texto_vira_html_do_site():
    h = pub.para_html("Abre com **negrito** e <script>x</script>.\n\n## Prazos\n- **Até 31/01**: opção\n\n| A | B |\n|---|---|\n| a \\| b | c |")
    assert "&lt;script&gt;" in h and "<h2>Prazos</h2>" in h and "<li><strong>Até 31/01</strong>: opção</li>" in h
    assert "<td>a | b</td><td>c</td>" in h and "---" not in h
    assert pub.resumo("## Título\n" + "palavra " * 60).endswith("…") and len(pub.resumo("x " * 200)) <= 156


def test_site_fora_do_ar_antes_do_envio_mantem_a_autorizacao(cenario):
    c, envio = autorizado(cenario)
    SITE["fora"] = True
    feito = rodar()
    assert "tenta de novo na próxima rodada" in feito[0] and SITE["envios"] == []
    assert situacao(cenario, envio)[0] == "autorizado"                       # nada foi enviado: segue valendo
    SITE["fora"] = False
    assert rodar() == [f"envio {envio}: publicado"]


def test_assunto_que_perdeu_a_confirmacao_nao_vai_ao_site(cenario):
    c, envio = autorizado(cenario)
    a = cenario.execute("select assunto_id from radar_conteudos where id = %s", (c,)).fetchone()[0]
    cenario.execute("update radar_assuntos set situacao_confirmacao = 'em_verificacao' where id = %s", (a,))
    assert rodar() == [f"envio {envio}: cancelado"] and SITE["envios"] == []
    assert "exigências do site" in situacao(cenario, envio)[2]


def test_registro_feito_pela_coleta_encerra_o_envio_e_publicado_nao_se_autoriza_de_novo(cenario):
    c, envio = autorizado(cenario)
    SITE["publicar"] = False
    rodar()
    assert situacao(cenario, envio)[0] == "enviando"
    cenario.execute("insert into radar_divulgacoes (conteudo_id, url, publicado_em) values (%s, %s, current_date)",
                    (c, BASE + "/news/view/achada-pela-coleta"))
    assert rodar() == [f"envio {envio}: publicado (registro já feito pela coleta)"]
    assert situacao(cenario, envio)[:2] == ("publicado", BASE + "/news/view/achada-pela-coleta")
    cenario.execute("delete from radar_divulgacoes")                       # registro apagado: mesmo assim não publica de novo
    lido = cenario.execute("select atualizado_em from radar_conteudos where id = %s", (c,)).fetchone()[0]
    with como("authenticated", ADMIN) as x, pytest.raises(Exception, match="RADAR117"):
        x.execute("select radar_autorizar_site(%s, 'Simples Nacional', %s)", (c, lido))
