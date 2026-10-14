"""Robô de publicação no site (v0.10.0): só envia o que o administrador autorizou, nunca reenvia e registra o link.

Banco real (PostgreSQL + PostgREST) e um site da Artecon de mentira, servido localmente, com o mesmo formulário
de /admin/news/register (title, keywords, metadescription, text, category, image).
"""
from __future__ import annotations

import html
import json
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
from radar_banco import Banco, ErroBanco
from radar_util import hoje_brasilia
from test_radar_banco import aprovar, cenario_publicavel

PORTA = 3997
BASE = f"http://127.0.0.1:{PORTA}"
MESES = "Janeiro Fevereiro Março Abril Maio Junho Julho Agosto Setembro Outubro Novembro Dezembro".split()
SITE = {"noticias": [], "envios": [], "logins": 0, "exigir_captcha": False, "publicar": True, "categorias": None, "fora": False,
        "exclusoes": [], "excluir": True, "encurtar": None, "editar": True}
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
        if self.path == "/admin/news/list":                         # v0.17.0: a lista do painel (como o site real: JSON do DataTables)
            if not self._logado():
                return self._html(302, "", [("Location", "/admin/signin")])
            # rodada 2: o painel pode encurtar o título longo ("…comprido...") e tem o link do formulário de edição de cada notícia
            curto = lambda t: t[:SITE["encurtar"]] + "..." if SITE["encurtar"] and len(t) > SITE["encurtar"] else t
            linhas = [[curto(n["title"]), "<img src='x.jpg'>", "Tributário", "09/10/2026 10:00", "Robo",
                       f"<a href='{BASE}/admin/news/register/ed-{n['slug']}'><i></i></a> <a href='{BASE}/admin/news/delete/tk-{n['slug']}' "
                       "class='text-danger' data-confirm='Tem certeza que deseja excluir esta notícia?'><i></i></a>"] for n in SITE["noticias"]]
            return self._html(200, json.dumps({"data": linhas}))
        m = re.fullmatch(r"/admin/news/register/ed-(.+)", self.path)
        if m and self._logado() and SITE["editar"]:                 # o formulário de edição, com o título inteiro
            n = next((n for n in SITE["noticias"] if n["slug"] == m.group(1)), None)
            if n:
                return self._html(200, f"<form method='post'><input name='title' type='text' value=\"{html.escape(n['title'])}\"></form>")
        m = re.fullmatch(r"/admin/news/delete/tk-(.+)", self.path)
        if m and self._logado():
            SITE["exclusoes"].append(m.group(1))
            if SITE["excluir"]:
                SITE["noticias"] = [n for n in SITE["noticias"] if n["slug"] != m.group(1)]
            return self._html(302, "", [("Location", "/admin/news")])
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
    servidor.server_close()


@pytest.fixture()
def cenario(api_postgrest, site, limpo):
    SITE.update(noticias=[], envios=[], logins=0, exigir_captcha=False, publicar=True, categorias=None, fora=False, exclusoes=[], excluir=True,
                encurtar=None, editar=True)
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
    assert "Texto elaborado por: <strong>Equipe Artecon</strong>" in e["text"]
    assert 'Fonte: <a href="https://exemplo.gov.br/in-2290" target="_blank" rel="noopener">Receita Federal</a>' in e["text"]   # v0.11.0
    assert e["image"][0] == "capa-radar.png" and e["image"][1].startswith(b"\x89PNG")
    assert len(e["metadescription"]) <= 160 and "**" not in e["metadescription"]
    assert situacao(cenario, envio) == ("publicado", BASE + "/news/view/noticia-1", None)
    url, obs = cenario.execute("select url, observacao from radar_divulgacoes where conteudo_id = %s", (c,)).fetchone()
    assert url == BASE + "/news/view/noticia-1" and f"envio nº {envio}" in obs
    assert rodar() == [] and len(SITE["envios"]) == 1                     # nada mais a fazer: não reenvia


def test_capa_vem_da_vista_e_com_o_banco_antigo_de_radar_imagens(monkeypatch):
    """v0.21.0: a chave do robô não lê radar_imagens (as fotos da equipe e as lâminas da Pauta ficam lá): a capa vem de radar_v_capas.
    Com o banco de antes da v0.21.0 (a vista não existe: 404), lê radar_imagens como antes; outro erro não é engolido."""
    pedidos = []

    def pedir(self, metodo, caminho, **k):
        pedidos.append(caminho)
        if caminho == "radar_v_capas" and erro:
            raise ErroBanco(f"GET radar_v_capas: HTTP {erro} — {{}}")
        return [{"dados": CAPA}]
    monkeypatch.setattr(Banco, "_pedir", pedir)
    banco = Banco("http://127.0.0.1:1", "chave")
    for erro, caminhos in [(None, ["radar_v_capas"]), (404, ["radar_v_capas", "radar_imagens"])]:
        pedidos.clear()
        assert banco.capa(7) == CAPA and pedidos == caminhos
    erro = 500
    with pytest.raises(ErroBanco, match="HTTP 500"):
        banco.capa(7)


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
    assert "&lt;script&gt;" in h and "<h2>Prazos</h2>" in h and '<li style="text-align:justify"><strong>Até 31/01</strong>: opção</li>' in h
    assert '<p style="text-align:justify">Abre com <strong>negrito</strong>' in h        # v0.12.0: texto justificado
    assert 'text-align:right' in pub.para_html("Texto.", autor="Equipe Artecon")           # créditos continuam à direita
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



# ------------------------------------------------------------------- v0.17.0: exclusão no site e redes junto com o site
import radar_site_excluir as exc                                        # noqa: E402


def excluir(agora=None):
    banco = Banco(API, jwt("service_role"), prefixo="")
    return exc.Excluidor(banco, "robo@artecon", "s3nha", agora=agora).executar()


def pedir_exclusao(c):
    with como("authenticated", ADMIN) as x:
        return x.execute("select radar_pedir_exclusao_site(%s)", (c,)).fetchone()[0]


def test_exclui_do_site_so_com_pedido_e_confere_que_saiu(cenario):
    c, envio = autorizado(cenario)
    rodar()
    assert excluir() == [] and SITE["exclusoes"] == []                     # sem pedido, nada é excluído (nem entra no site)
    outra = {"slug": "outra", "title": "Outra notícia que fica", "text": "x"}
    SITE["noticias"].append(outra)
    x = pedir_exclusao(c)
    assert excluir() == [f"exclusão {x}: excluída do site"]
    assert SITE["exclusoes"] == ["noticia-1"] and SITE["noticias"] == [outra]     # só a pedida saiu
    assert cenario.execute("select situacao from radar_site_exclusoes where id = %s", (x,)).fetchone()[0] == "excluido"
    assert cenario.execute("select count(*) from radar_divulgacoes where conteudo_id = %s", (c,)).fetchone()[0] == 0
    assert situacao(cenario, envio)[0] == "excluido"
    assert excluir() == []                                                 # concluído: não volta ao site


def test_exclusao_na_duvida_nao_exclui_nada(cenario):
    c, envio = autorizado(cenario)
    rodar()
    titulo = SITE["noticias"][0]["title"]
    SITE["noticias"].append({"slug": "copia", "title": titulo, "text": "x"})         # duas com o mesmo título
    x = pedir_exclusao(c)
    assert excluir() == [f"exclusão {x}: não concluída"] and SITE["exclusoes"] == []
    sit, erro = cenario.execute("select situacao, erro from radar_site_exclusoes where id = %s", (x,)).fetchone()
    assert sit == "erro" and "há 2 notícias com este título" in erro and "tk-" not in erro and "s3nha" not in erro
    assert cenario.execute("select count(*) from radar_divulgacoes where conteudo_id = %s", (c,)).fetchone()[0] == 1
    # título mudado no site (não está na lista do painel) e a página ainda no ar: não exclui
    SITE["noticias"] = [{"slug": "noticia-1", "title": "Título mudado à mão no site", "text": "x"}]
    with como("authenticated", ADMIN) as a:
        a.execute("select radar_cancelar_exclusao_site(%s)", (x,))
    x = pedir_exclusao(c)
    assert excluir() == [f"exclusão {x}: não concluída"] and SITE["exclusoes"] == []
    assert "não achei a notícia com este título" in cenario.execute("select erro from radar_site_exclusoes where id = %s", (x,)).fetchone()[0]
    # o site não excluiu de fato: erro para conferir
    SITE["noticias"] = [{"slug": "noticia-1", "title": titulo, "text": "x"}]
    SITE["excluir"] = False
    with como("authenticated", ADMIN) as a:
        a.execute("select radar_cancelar_exclusao_site(%s)", (x,))
    x = pedir_exclusao(c)
    assert excluir() == [f"exclusão {x}: não concluída"] and SITE["exclusoes"] == ["noticia-1"]
    assert "o site não excluiu" in cenario.execute("select erro from radar_site_exclusoes where id = %s", (x,)).fetchone()[0]
    # já não está no painel nem no ar (excluída à mão): conclui
    SITE["noticias"], SITE["excluir"] = [], True
    with como("authenticated", ADMIN) as a:
        a.execute("select radar_cancelar_exclusao_site(%s)", (x,))
    x = pedir_exclusao(c)
    assert excluir() == [f"exclusão {x}: excluída do site"]


def test_exclusao_pelo_comeco_do_titulo_so_com_o_titulo_inteiro_conferido(cenario):
    """Rodada 2 da varredura geral: o painel mostra o título longo cortado ("…vai..."). A notícia achada só pelo começo do título
    podia ser OUTRA da mesma série (a pedida foi apagada à mão ou teve o título mudado lá) e era excluída sem conferir. Agora o robô
    lê o título inteiro no formulário de edição do painel (só abre): exclui só a pedida; a outra fica."""
    c, envio = autorizado(cenario)
    rodar()
    SITE["encurtar"] = 40
    pedida = SITE["noticias"][0]
    serie = {"slug": "serie-2028", "title": "Prazo de opção pelo Simples Nacional vai até 29 de janeiro de 2028", "text": "x"}
    assert pedida["title"][:40] == serie["title"][:40] and pedida["title"] != serie["title"]

    def de_novo(x):
        with como("authenticated", ADMIN) as a:
            a.execute("select radar_cancelar_exclusao_site(%s)", (x,))
        return pedir_exclusao(c)
    # a pedida teve o título mudado à mão (a página continua no ar) e só a da série seguinte aparece com o mesmo começo: não exclui
    SITE["noticias"] = [dict(pedida, title="Título trocado à mão no painel"), serie]
    x = pedir_exclusao(c)
    assert excluir() == [f"exclusão {x}: não concluída"] and SITE["exclusoes"] == []
    assert "não achei a notícia com este título" in cenario.execute("select erro from radar_site_exclusoes where id = %s", (x,)).fetchone()[0]
    # sem o formulário de edição (o painel mudou), na dúvida não exclui
    SITE["noticias"], SITE["editar"] = [pedida], False
    x = de_novo(x)
    assert excluir() == [f"exclusão {x}: não concluída"] and SITE["noticias"] == [pedida] and SITE["exclusoes"] == []
    erro = cenario.execute("select erro from radar_site_exclusoes where id = %s", (x,)).fetchone()[0]
    assert "não consegui ler o título inteiro" in erro and "ed-" not in erro and "tk-" not in erro
    # a pedida está no painel (cortada): o título inteiro confere e só ela sai
    SITE["noticias"], SITE["editar"] = [pedida, {"slug": "outra", "title": "Outra notícia que fica", "text": "x"}], True
    x = de_novo(x)
    assert excluir() == [f"exclusão {x}: excluída do site"] and SITE["exclusoes"] == [pedida["slug"]]
    # publicada de novo e apagada à mão no painel; só a da série seguinte aparece (cortada, com o mesmo começo): a página pedida já
    # não abre, então conclui sem excluir nada (antes, a da série saía no lugar dela)
    with como("authenticated", ADMIN) as a:
        a.execute("select radar_autorizar_site(%s, 'Simples Nacional', %s)",
                  (c, cenario.execute("select atualizado_em from radar_conteudos where id = %s", (c,)).fetchone()[0]))
    rodar()
    SITE["noticias"] = [serie]
    x = pedir_exclusao(c)
    assert excluir() == [f"exclusão {x}: excluída do site"]
    assert SITE["noticias"] == [serie] and SITE["exclusoes"] == [pedida["slug"]]


def test_exclusao_com_o_site_fora_do_ar_tenta_de_novo_e_desiste_depois_de_2_horas(cenario):
    c, envio = autorizado(cenario)
    rodar()
    x = pedir_exclusao(c)
    SITE["fora"] = True
    assert "tenta de novo na próxima rodada" in excluir()[0]
    assert cenario.execute("select situacao from radar_site_exclusoes where id = %s", (x,)).fetchone()[0] == "excluindo"
    depois = lambda: datetime.now(timezone.utc) + timedelta(hours=3)
    assert excluir(agora=depois) == [f"exclusão {x}: não concluída"]
    assert "não respondeu por 2 horas" in cenario.execute("select erro from radar_site_exclusoes where id = %s", (x,)).fetchone()[0]


def test_redes_que_iam_junto_com_o_site_sao_mandadas_para_a_funcao(cenario):
    c, envio = autorizado(cenario)
    with como("authenticated", ADMIN) as x:                                # a autorização do site já existe: aqui só as redes
        x.execute("select radar_cancelar_site(%s)", (envio,))
        lido = x.execute("select atualizado_em from radar_conteudos where id = %s", (c,)).fetchone()[0]
        r = x.execute("select radar_autorizar_todos(%s, 'Simples Nacional', %s, %s, %s, %s)",
                      (c, lido, "data:image/jpeg;base64," + "A" * 200, "Legenda do Instagram com link na bio", "Leia: {LINK DO SITE}")).fetchone()[0]
    chamadas = []

    class Resp:
        status_code, text = 200, "{}"
        def json(self):
            return {"situacao": "publicado"}

    def post(url, json=None, headers=None, timeout=None):
        chamadas.append((url, json, headers["Authorization"]))
        return Resp()
    banco = Banco(API, jwt("service_role"), prefixo="")
    assert pub.publicar_redes(banco, "https://projeto.supabase.co", "chave-interna", post=post) == []   # o site ainda não saiu
    rodar()                                                                 # o robô publica no site: as redes ficam prontas
    feito = pub.publicar_redes(banco, "https://projeto.supabase.co", "chave-interna", post=post)
    assert feito == [f"Instagram (envio {r['instagram']}): publicado", f"Facebook (envio {r['facebook']}): publicado"]
    assert chamadas == [("https://projeto.supabase.co/functions/v1/radar-redes", {"acao": "publicar", "envio": r[k]}, "Bearer chave-interna")
                        for k in ("instagram", "facebook")]
    fb = cenario.execute("select legenda from radar_redes_envios where id = %s", (r["facebook"],)).fetchone()[0]
    assert fb == "Leia: " + BASE + "/news/view/noticia-1"


def test_robos_mandam_a_chave_interna_nova_so_no_apikey():
    """Rodada 2 da varredura geral: o Supabase desliga a chave service_role antiga (JWT) até o fim de 2026. Com a nova (sb_secret_…) no
    segredo SUPABASE_SERVICE_KEY, os robôs a mandam só no apikey (no Authorization o Supabase recusa: "Invalid Compact JWS"), no banco
    e no pedido à radar-redes; a antiga continua nos dois cabeçalhos."""
    import radar_banco
    from conftest import SECRETA
    servico = jwt("service_role")
    assert radar_banco.cabecalhos_da_chave(SECRETA) == {"apikey": SECRETA}
    assert radar_banco.cabecalhos_da_chave(servico) == {"apikey": servico, "Authorization": "Bearer " + servico}
    b = Banco("https://projeto.supabase.co", SECRETA)
    assert b.sessao.headers["apikey"] == SECRETA and "Authorization" not in b.sessao.headers
    assert Banco("https://projeto.supabase.co", servico).sessao.headers["Authorization"] == "Bearer " + servico
    chamadas = []

    class Resp:
        status_code, text = 200, "{}"
        def json(self):
            return {"situacao": "publicado"}

    class BancoFalso:
        def _pedir(self, *a, **k):
            return [{"id": 7, "canal": "instagram"}]
    pub.publicar_redes(BancoFalso(), "https://projeto.supabase.co", SECRETA, post=lambda url, json=None, headers=None, timeout=None:
                       chamadas.append(headers) or Resp())
    assert chamadas == [{"apikey": SECRETA, "Content-Type": "application/json"}]


def test_sem_a_funcao_de_concluir_no_banco_nao_exclui_nada_do_site(cenario):
    c, envio = autorizado(cenario)
    rodar()
    pedir_exclusao(c)
    banco = Banco(API, jwt("service_role"), prefixo="")
    original = banco._pedir
    def sem_funcao(metodo, caminho, **k):
        if caminho == "rpc/radar_site_exclusao_concluir":
            raise pub.ErroBanco("POST rpc/radar_site_exclusao_concluir: HTTP 404 — {\"code\":\"PGRST202\"}")
        return original(metodo, caminho, **k)
    banco._pedir = sem_funcao
    feito = exc.Excluidor(banco, "robo@artecon", "s3nha").executar()
    assert "falta aplicar no banco" in feito[0] and SITE["exclusoes"] == [] and len(SITE["noticias"]) == 1 and SITE["logins"] == 1


def test_link_da_fonte_nunca_e_o_do_boletim_pago_quando_ha_outra_captura():
    """v0.18.0: o campo Fonte não cita o boletim pago (ITC); o link da fonte também não leva a ele quando há outra captura."""
    class Banco:
        def __init__(self, caps): self.caps = caps
        def _pedir(self, metodo, caminho, params=None, **_):
            assert caminho == "radar_assunto_capturas" and "slug" in params["select"]
            return [{"radar_capturas": c} for c in self.caps]
    itc = {"id": 1, "url": "https://www.itcnet.com.br/?radar=abc", "radar_fontes": {"oficial": False, "slug": "itc-email"}}
    portal = {"id": 2, "url": "https://portalcontabilsc.com.br/noticias/x", "radar_fontes": {"oficial": False, "slug": "portalcontabilsc-noticias"}}
    rfb = {"id": 3, "url": "https://www.gov.br/receitafederal/x", "radar_fontes": {"oficial": True, "slug": "rfb-noticias"}}
    link = lambda *caps: pub.Publicador(Banco(list(caps)), "u", "s").link_fonte({"assunto_id": 1})
    assert link(itc, portal) == portal["url"] and link(itc, portal, rfb) == rfb["url"]
    assert link(itc) == "https://www.itcnet.com.br/"                   # só o boletim: o endereço do site, sem o marcador interno


def test_informativo_sai_com_a_linha_no_fim_e_o_endereco_vira_link(cenario):
    """v0.24.0: o texto Informativo (o primeiro aviso começa com "INFORMATIVO"), autorizado pelo administrador e aprovado, sai no site
    com a linha "Conteúdo informativo" no fim, depois dos créditos; o endereço do texto (o link oficial da seção "Fundamentação legal")
    vira link, como na prévia da tela, com a pontuação de fora; o texto que não é Informativo não leva a linha."""
    a, _ = cenario_publicavel(cenario)
    marca = "INFORMATIVO (sem fundamentação legal específica): só vai ao site e às redes depois que o administrador autoriza a publicação."
    corpo = CORPO + "\n\n## Fundamentação legal\n- Instrução Normativa RFB nº 2.290 — https://exemplo.gov.br/in-2290."
    img = cenario.execute("insert into radar_imagens (dados) values (%s) returning id", (CAPA,)).fetchone()[0]
    c = cenario.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo, status, gerado_por, avisos_ia, fonte_credito, imagem_id)
                           values (%s, 'informativo', 'Informativo de teste sobre o Simples', %s, 'em_revisao', 'ia', %s, 'Receita Federal', %s)
                           returning id""", (a, corpo, json.dumps([marca]), img)).fetchone()[0]
    with como("authenticated", ADMIN) as x:
        x.execute("select radar_liberar_sem_fundamentacao(%s, 'Informativo autorizado no teste')", (a,))
    aprovar(c)
    lido = cenario.execute("select atualizado_em from radar_conteudos where id = %s", (c,)).fetchone()[0]
    with como("authenticated", ADMIN) as x:
        envio = x.execute("select radar_autorizar_site(%s, 'Simples Nacional', %s)", (c, lido)).fetchone()[0]
    assert rodar() == [f"envio {envio}: publicado"]
    texto = SITE["envios"][-1]["text"]
    assert texto.endswith('<p style="text-align:right"><em>Fonte: <a href="https://exemplo.gov.br/in-2290" target="_blank" rel="noopener">'
                          'Receita Federal</a></em></p>\n<p style="text-align:right"><em>Conteúdo informativo</em></p>')
    assert ('<li style="text-align:justify">Instrução Normativa RFB nº 2.290 — <a href="https://exemplo.gov.br/in-2290" target="_blank" '
            'rel="noopener">https://exemplo.gov.br/in-2290</a>.</li>') in texto
    assert "Conteúdo informativo" not in pub.para_html("Texto.", fonte="Receita Federal")
    assert pub.eh_informativo({"avisos_ia": [marca]}) and not pub.eh_informativo({"avisos_ia": ["Outro aviso"]}) and not pub.eh_informativo({})
    h = pub.para_html("Veja **https://www.gov.br/a?b=1&c=2** e (https://www.gov.br/x_(y)). Nada de javascript:alert(1) nem <b>x</b>.")
    assert ('<strong><a href="https://www.gov.br/a?b=1&amp;c=2" target="_blank" rel="noopener">https://www.gov.br/a?b=1&amp;c=2</a></strong>'
            in h and '(<a href="https://www.gov.br/x_(y)" target="_blank" rel="noopener">https://www.gov.br/x_(y)</a>).' in h)
    assert "javascript:alert(1)" in h and h.count("<a ") == 2 and "&lt;b&gt;x&lt;/b&gt;" in h
