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


# v0.17.0: reconhecimento da lista de notícias (para a exclusão pedida pelo administrador) — só lê
LISTA_TABELA = """<meta name="csrf-token" content="abcdefghijklmnopqrstuvwxyz0123456789ABCD"><a href="/admin/news/register">Nova notícia</a>
<table><tr><th>Título</th><th>Ações</th></tr>
<tr><td>Prazo do IRPF</td><td><a href="/admin/news/edit/12">Editar</a>
<form method="post" action="/admin/news/12" onsubmit="return confirm('Excluir?')"><input type="hidden" name="_token" value="tokenSecretoDoFormularioXXXXXXXXXXXXXXXX">
<input type="hidden" name="_method" value="DELETE"><button>Excluir</button></form></td></tr></table>
<a href="/admin/news?page=2">2</a><script src="/js/admin.js"></script>"""


def test_reconhece_a_lista_sem_abrir_excluir_nem_mostrar_token():
    painel = PAINEL + '<a href="/admin/news/delete/9">Excluir</a>'
    s = Sessao({sa.LOGIN: LOGIN_OK, sa.BASE + "/admin/news": LISTA_TABELA}, painel)
    url, html = sa.achar_lista(s, sa.entrar(s, "u", "segredo"), sa.BASE + "/admin")
    texto = sa.relatorio_lista(url, html)
    assert url.endswith("/admin/news") and len(s.posts) == 1                          # só o login foi enviado
    assert not any(sa.APAGA.search(g) for g in s.gets)                                # nunca abre "excluir" nem "sair"
    assert "formulário POST → /admin/news/12 ocultos=['_token', '_method=DELETE']" in texto
    assert "tokenSecreto" not in texto and "abcdefghij" not in texto                  # valores ocultos e códigos longos não aparecem
    assert "/admin/news?page=2" in texto and "/js/admin.js" in texto and "linha 1: 2 célula(s)" in texto
    assert "Prazo do IRPF" not in texto and "/admin/news/edit/…" in texto and "/edit/12" not in texto  # v0.22.0: nem célula nem código
    s.paginas[sa.BASE + "/js/admin.js"] = "$('#tab').DataTable({ajax: '/admin/news/list'}); $(document).on('click', '.del', function(){ swal('Excluir?') })"
    scripts = sa.scripts_do_painel(s, url, html)
    assert "/admin/news/list" in scripts and "swal" in scripts and len(s.posts) == 1 and not any(sa.APAGA.search(g) for g in s.gets)
    # os dados da lista (GET no data-url da tabela, como o painel faz): a notícia e as ações dela, sem abrir nenhuma
    tabela = '<table class="table datatable" data-url="https://artecon.cnt.br/admin/news/list"></table>'
    codigo = "eyJpdiI6" + "Q" * 160 + "In0"                                          # o código do painel: 172 caracteres
    s.paginas[sa.BASE + "/admin/news/list"] = ('{"data": [["Prazo do IRPF", "<img src=x>", "Federal", "01/10/2026", "Mariana", '
        f'"<a href=\\"https://artecon.cnt.br/admin/news/register/{codigo}\\">Editar</a> <a href=\\"https://artecon.cnt.br/admin/news/delete/7\\" '
        'data-confirm=\\"Excluir?\\">Excluir</a>"]], "recordsTotal": 1}')
    s.get = lambda u, **k: (s.gets.append(u), type("R", (), {"url": u, "text": s.paginas.get(u, ""), "status_code": 200,
                            "headers": {"content-type": "application/json"}, "json": lambda self: __import__("json").loads(s.paginas[u])})())[1]
    dados = sa.dados_da_lista(s, sa.BASE + "/admin/news", tabela)
    assert "1 notícia(s)" in dados and "notícia 1: 6 célula(s); com marcação: [2, 6]" in dados
    assert "/admin/news/delete/… data-confirm=Excluir?" in dados and "/admin/news/register/…" in dados
    # v0.22.0: o registro do Actions é público: nem título, nem quem cadastrou (coluna "Usuário"), nem o código dos links
    # de excluir/editar (a exclusão do painel é um GET sem CSRF)
    for proibido in ("Prazo do IRPF", "Mariana", "Federal", codigo[:20], "QQQQ", "/delete/7", "/register/eyJ"):
        assert proibido not in dados, proibido
    assert not any(sa.APAGA.search(g) for g in s.gets)


def test_relatorio_publico_sem_codigo_de_link_nem_chave_de_biblioteca(monkeypatch, capsys):
    """A máscara final do main() pega o que escapar: código de excluir/editar e chave no caminho de script de fora."""
    longo = "a1B2" * 43
    assert sa._caminho(sa.BASE, f"/admin/news/delete/{longo}") == "/admin/news/delete/…"
    assert sa._caminho(sa.BASE, f"/admin/news/register/{longo}?x=1") == "/admin/news/register/…?x=1"
    assert sa._caminho(sa.BASE, "/admin/news/register") == "/admin/news/register"          # o formulário de cadastro fica
    assert sa._caminho(sa.BASE, f"https://cdn.tiny.cloud/1/{longo}/tinymce/6/tinymce.min.js") == "cdn.tiny.cloud/…"
    assert sa._molde(f"x /admin/news/delete/{longo} e token {longo} fim") == "x /admin/news/delete/… e token … fim"
    monkeypatch.setenv("ARTECON_SITE_USUARIO", "robo@artecon")
    monkeypatch.setenv("ARTECON_SITE_SENHA", "senha-secreta")

    def falso(*a, **k):
        raise sa.Parada(f"teste em /admin/news/delete/{longo} com senha-secreta")
    monkeypatch.setattr(sa, "entrar", falso)
    assert sa.main() == 1
    saida = capsys.readouterr().out
    assert "/admin/news/delete/…" in saida and longo not in saida and "senha-secreta" not in saida


def test_lista_nao_encontrada_para_com_aviso():
    s = Sessao({sa.LOGIN: LOGIN_OK, sa.BASE + "/admin/news": "<p>vazio</p>"}, PAINEL)
    with pytest.raises(sa.Parada, match="não achei a lista"):
        sa.achar_lista(s, sa.entrar(s, "u", "s"), sa.BASE + "/admin")
