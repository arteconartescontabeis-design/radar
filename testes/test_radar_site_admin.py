"""Acesso ao painel do site: só reconhece; para no captcha; nunca põe a senha no relatório."""
from __future__ import annotations

import pytest

import radar_site_admin as sa

LOGIN_OK = """<form method="post" action="/admin/signin"><input type="hidden" name="_token" value="abc">
<label for="e">E-mail</label><input id="e" name="email" type="email"><input name="password" type="password"><button>Entrar</button></form>"""
PAINEL = """<nav><a href="/admin/news">Notícias</a><a href="/admin/news/delete/3">Excluir</a><a href="/admin/logout">Sair</a></nav>"""
LISTA = """<a href="/admin/news/create">Nova notícia</a>"""
CADASTRO = """<form method="post" action="/admin/news/store"><input type="hidden" name="_token" value="x">
<label for="t">Título</label><input id="t" name="title" required><textarea name="body"></textarea>
<select name="category_id"><option>Federal</option><option>Trabalhista</option></select>
<label for="s">Situação</label><select id="s" name="status"><option>Rascunho</option><option>Publicada</option></select>
<button type="submit">Salvar</button></form>"""


class Resp:
    def __init__(self, url, text, status=200):
        self.url, self.text, self.status_code = url, text, status

    def raise_for_status(self):
        pass


class Sessao:
    def __init__(self, paginas, depois_login):
        self.paginas, self.depois_login, self.posts, self.gets = paginas, depois_login, [], []

    def get(self, url, **k):
        self.gets.append(url)
        return Resp(url, self.paginas.get(url, ""))

    def post(self, url, data=None, **k):
        self.posts.append((url, data))
        return Resp(sa.BASE + "/admin", self.depois_login)


def test_reconhece_o_formulario_sem_enviar_nada_alem_do_login():
    s = Sessao({sa.LOGIN: LOGIN_OK, sa.BASE + "/admin/news": LISTA, sa.BASE + "/admin/news/create": CADASTRO}, PAINEL)
    painel = sa.entrar(s, "robo@artecon", "segredo")
    assert s.posts == [(sa.BASE + "/admin/signin", {"_token": "abc", "email": "robo@artecon", "password": "segredo"})]
    url, form = sa.achar_cadastro(s, painel, sa.BASE + "/admin")
    assert url.endswith("/admin/news/create") and len(s.posts) == 1                  # só o login foi enviado
    assert not any("delete" in g or "logout" in g for g in s.gets)                    # nunca abre "excluir" nem "sair"
    texto = sa.relatorio(url, form)
    assert "title [text, obrigatório] Título" in texto and "status [select]" in texto and "controla a publicação" in texto
    assert "dá para testar como rascunho" in texto and "segredo" not in texto


def test_para_no_captcha_e_no_login_recusado():
    com = LOGIN_OK + '<div class="g-recaptcha"></div>'
    s = Sessao({sa.LOGIN: com}, PAINEL)
    sa.entrar(s, "u", "s")                                                             # liberado: entra sem resolver nada
    assert not any("captcha" in k for k in s.posts[0][1])                               # nenhum campo de verificação enviado
    with pytest.raises(sa.Parada, match="exigiu a verificação"):
        sa.entrar(Sessao({sa.LOGIN: com}, com), "u", "s")                               # o site pediu: para
    with pytest.raises(sa.Parada, match="não foi aceito"):
        sa.entrar(Sessao({sa.LOGIN: LOGIN_OK}, LOGIN_OK), "u", "s")                  # voltou para a tela de senha


def test_sem_campo_de_situacao_avisa_que_nao_envia():
    form = sa.formularios(CADASTRO.replace("status", "x").replace("Situação", "Outro"), sa.BASE)[0]
    assert "o robô não envia nada" in sa.relatorio(sa.BASE + "/admin/news/create", form)


def test_sem_segredos_nao_tenta(monkeypatch, capsys):
    monkeypatch.delenv("ARTECON_SITE_USUARIO", raising=False)
    monkeypatch.delenv("ARTECON_SITE_SENHA", raising=False)
    assert sa.main() == 1 and "ARTECON_SITE_USUARIO" in capsys.readouterr().out
