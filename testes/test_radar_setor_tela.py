"""Aba Setor (v0.34.0) no navegador de verdade (Chromium via Playwright), com o PostgREST e o banco reais. A função radar-concorrentes
é imitada na própria página (route): a tela só a chama no "Atualizar a análise" e no "Incluir a conta da Artecon".

Confere: a aba (entre a Pauta e as Fontes) para todos os perfis; o aviso de ética no alto; os números do cenário P em pt-BR; os gráficos
(série, formatos com o % escrito, engajamento por conta, dias e horários com "—", temas); as publicações de maior engajamento só com o
link do Instagram (nova aba, sem passar quem abriu) e um trecho de até 100 caracteres (o que vem depois nunca aparece); nenhuma imagem;
"Aguardando a aprovação da Meta" na hashtag; o leitor e o editor sem os controles do administrador; o administrador cria o setor, inclui
contas, edita os temas, pausa, retoma, remove e apaga; o "Atualizar a análise" (até ler tudo, a pausa da Meta, a função ausente ou
antiga); a conta da Artecon; a configuração; a recusa da Meta em português na tabela; o celular sem rolagem lateral; o arquivo que não
carregou ou de outra versão; e os nomes globais do radar-setor.js sem colidir com os outros três scripts.
"""
from __future__ import annotations

import json
import re
from datetime import date

import pytest

import test_radar_setor_banco as sb
from conftest import RAIZ
from test_radar_telas import BASE, entrar, navegador, pagina, sem_rolagem_lateral  # noqa: F401  (fixtures)

LEITOR_EMAIL, EDITORA_EMAIL, ADMIN_EMAIL = "leitor@artecon.test", "editora@artecon.test", "admin@artecon.test"
ETICA = "Serve para ver formatos e temas, nunca para copiar (NBC PG 01)."
VERSAO_TELA = re.search(r'(?m)^const VERSAO = "([^"]+)"', (RAIZ / "index.html").read_text(encoding="utf-8")).group(1)


@pytest.fixture()
def tela(pagina, limpo):
    sb.limpar(limpo)
    pagina.db = limpo
    yield pagina
    sb.limpar(limpo)


def hoje_brasilia(db) -> date:
    return db.execute("select (now() at time zone 'America/Sao_Paulo')::date").fetchone()[0]


def cenario(db):
    """O cenário P do teste do banco, com as datas contadas a partir de hoje (Brasília) e lido agora (lido ontem, a cobertura das contas
    terminaria ontem e os números mudariam perto da meia-noite)."""
    return sb.cenario_p(db, hoje_brasilia(db), db.execute("select now()").fetchone()[0])


def abrir_setor(pg, email=LEITOR_EMAIL, esperar="#setor"):
    entrar(pg, email)
    pg.wait_for_selector("nav.abas")
    pg.click("nav.abas button[data-aba=setor]")
    pg.wait_for_selector(esperar)
    # no runner carregado do CI, o executar() do login ainda pode estar OCUPADO quando a tela já apareceu — e um clique
    # com OCUPADO há menos de 1,5 s é IGNORADO em silêncio (regra do clique duplo). Espera desocupar antes de clicar.
    pg.wait_for_function("() => !OCUPADO")


def funcao_imitada(pg, respostas, pedidos):
    """A função radar-concorrentes imitada: cada pedido recebe a próxima resposta (status, corpo) e fica guardado."""
    fila = list(respostas)

    def tratar(rota):
        pedidos.append(json.loads(rota.request.post_data or "{}"))
        status, corpo = fila.pop(0) if fila else (200, {"versao": VERSAO_TELA, "motivo": "nada"})
        rota.fulfill(status=status, content_type="application/json", body=json.dumps(corpo))
    pg.route("**/functions/v1/radar-concorrentes", tratar)


# ------------------------------------------------------------------------------------- quem só lê
@pytest.mark.parametrize("email", [LEITOR_EMAIL, EDITORA_EMAIL])
def test_leitor_e_editor_veem_o_painel_sem_os_controles(tela, email):
    cenario(tela.db)
    abrir_setor(tela, email, "#setor-resumo")
    assert "ativa" in tela.get_attribute("[data-acao=setor-dias][data-dias='90']", "class")       # o período padrão: 90 dias
    tela.click("[data-acao=setor-dias][data-dias='30']")                                      # o cenário P é de 30 dias
    tela.wait_for_selector("[data-acao=setor-dias][data-dias='30'].ativa")
    abas = tela.locator("nav.abas button").all_inner_texts()
    # entre a Pauta e as Fontes (a editora tem a aba Vídeo entre a Pauta e a Setor; a v0.35.0 pôs a Respostas depois da Setor)
    assert abas.index("Pauta") < abas.index("Setor") < abas.index("Fontes")
    assert ETICA in tela.inner_text("#setor-etica")
    resumo = tela.inner_text("#setor-resumo")
    for trecho in ("Contas analisadas", "3", "1,4", "Artecon 0,7", "2,00%", "Foto", "69%"):
        assert trecho in resumo, trecho
    assert tela.locator("#setor-semanas svg path").count() >= 3 and tela.locator("#setor-semanas svg circle").count() >= 3
    assert "em andamento" in tela.inner_text("#setor-semanas") or tela.locator("#setor-semanas svg text", has_text="em andamento").count()
    formatos = tela.inner_text("#setor-formatos")
    assert "Foto 69%" in formatos and "Reel 19%" in formatos and "Carrossel 13%" in formatos and "Reel 4,00%" in formatos
    assert tela.locator("#setor-formatos .setor-pilha span").count() == 3 + 2            # setor (3 formatos) e Artecon (2)
    assert "—" in tela.inner_text("#setor-dias-horas") and tela.locator("#setor-dias-horas table tr").count() == 9
    assert "Imposto de Renda" in tela.inner_text("#setor-temas") and "Outros" in tela.inner_text("#setor-temas")
    assert tela.locator("#setor-engajamento .setor-barra").count() == 4 and "poucos dados" in tela.inner_text("#setor-engajamento")
    itens = tela.locator("#setor-melhores > ol.setor-melhores:not(#setor-melhores-artecon) > li")
    assert itens.count() == 6 and "@bruno.exemplo" in itens.nth(0).inner_text() and "5,00%" in itens.nth(0).inner_text()
    link = itens.nth(0).locator("a")
    assert link.inner_text() == "Ver no Instagram ↗" and link.get_attribute("href").startswith("https://www.instagram.com/p/")
    assert link.get_attribute("target") == "_blank" and link.get_attribute("rel") == "noopener noreferrer"
    trecho = itens.nth(0).locator("q").inner_text()
    assert len(trecho) <= 101 and trecho.endswith("…")
    assert tela.locator("#setor-melhores-artecon li").count() == 3
    assert tela.locator("#setor img").count() == 0 and "LEGENDA_SECRETA" not in tela.content()
    assert "Aguardando a aprovação da Meta" in tela.inner_text("#setor-hashtag")
    assert "Passo a passo no LEIAME" not in tela.inner_text("#setor-hashtag")               # o passo a passo é do administrador
    for controle in ("[data-acao=setor-atualizar]", "#setor-gerir-abrir", "#setor-gerir", "[data-acao=setor-novo]"):
        assert tela.locator(controle).count() == 0, controle
    tabela = tela.inner_text("#setor-contas")
    assert "@ana.teste" in tabela and "ok" in tabela and "poucos dados" in tabela and "cobrem só 15 dias do período" in tabela
    tela.click("[data-acao=setor-dias][data-dias='365']")
    tela.wait_for_selector("#setor-semanas >> text=Publicações por mês")


def test_sem_setor_o_leitor_ve_o_recado(tela):
    abrir_setor(tela, LEITOR_EMAIL, "#setor-vazio")
    assert "O administrador ainda não cadastrou nenhum setor." in tela.inner_text("#setor-vazio")
    assert tela.locator("[data-form=setorNovo]").count() == 0


def test_a_recusa_da_meta_aparece_em_portugues_na_tabela(tela):
    cenario(tela.db)
    tela.db.execute("""update radar_setor_contas set erro = 'conta não encontrada, privada ou que não é comercial/criador (a Meta só mostra perfis comerciais ou de criador públicos): confira o @ (Meta 110/2207013)'
                       where nome = 'bruno.exemplo'""")
    # a conta que não foi lida no período (90 dias; a última leitura é de antes dele): "—" e o recado, fora das medianas
    tela.db.execute("""insert into radar_setor_contas (setor_id, nome, seguidores, posts_total, coletada_em, tentada_em, lido_desde)
                       select setor_id, 'davi.exemplo', 800, 40, now() - interval '120 days', now() - interval '120 days', now() - interval '300 days'
                         from radar_setor_contas limit 1""")
    abrir_setor(tela, LEITOR_EMAIL, "#setor-contas")
    linha = tela.inner_text("#setor-contas tr[data-conta='bruno.exemplo']")
    assert "erro" in linha and "privada ou que não é comercial/criador" in linha
    assert "1 com erro" in tela.inner_text("#setor-situacao")
    linha = tela.inner_text("#setor-contas tr[data-conta='davi.exemplo']")
    assert "nenhuma leitura neste período" in linha and "—" in linha


# ------------------------------------------------------------------------------------- o administrador
def test_administrador_cria_inclui_edita_temas_pausa_remove_e_apaga(tela):
    db = tela.db
    abrir_setor(tela, ADMIN_EMAIL, "[data-form=setorNovo]")
    assert tela.input_value("#setor-novo-nome") == "Contabilidade"
    tela.click("[data-form=setorNovo] button.btn")
    # 120 s só nesta primeira espera: é a 1ª escrita da tela recém-aberta e, no runner carregado do CI, a resposta
    # às vezes passa dos 30 s padrão (timeouts intermitentes registrados no PR #92); o resto da suíte segue em 30 s
    tela.wait_for_selector("#setor-gerir", timeout=120000)
    sid = db.execute("select id from radar_setor_setores").fetchone()[0]
    tela.fill("#setor-incluir", "@ana.teste\nhttps://www.instagram.com/bruno.exemplo/\n#contabilidade\nhttps://www.instagram.com/p/X1/\nconta-com-hífen")
    tela.click("[data-form=setorContas] button.btn:not(.sec)")
    tela.wait_for_selector("#recado >> text=2 contas e 1 hashtag incluídas")
    assert "não reconheci os itens 4º e 5º" in tela.inner_text("#recado")
    tela.wait_for_selector("#setor-lista-contas")
    assert tela.locator("#setor-lista-contas tr[data-conta-id]").count() == 3
    assert "#contabilidade" in tela.inner_text("#setor-hashtag")                          # cadastrada, esperando a aprovação
    # temas: linha sem dois-pontos recusada na tela; salvos, entram no setor
    tela.fill("#setor-temas-texto", "Sem dois pontos aqui")
    tela.click("[data-form=setorTemas] button.btn:not(.sec)")
    tela.wait_for_selector("#recado >> text=Linha 1: falta o dois-pontos")
    tela.fill("#setor-temas-texto", "Bolo: bolo, cenoura\n\nPrazo: prazo, vencimento")
    tela.click("[data-form=setorTemas] button.btn:not(.sec)")
    tela.wait_for_selector("#recado >> text=Temas salvos")
    assert db.execute("select temas from radar_setor_setores").fetchone()[0] == [{"nome": "Bolo", "termos": ["bolo", "cenoura"]},
                                                                                  {"nome": "Prazo", "termos": ["prazo", "vencimento"]}]
    tela.wait_for_selector("#setor-temas-texto")
    tela.click("[data-acao=setor-temas-padrao]")
    assert tela.input_value("#setor-temas-texto").startswith("Reforma tributária: reforma tributária, IBS, CBS")
    # pausar, retomar e remover
    cid = db.execute("select id from radar_setor_contas where nome = 'ana.teste'").fetchone()[0]
    tela.click(f"[data-acao=setor-conta-pausar][data-id='{cid}']")
    tela.wait_for_selector("#recado >> text=Conta pausada")
    assert db.execute("select ativa from radar_setor_contas where id = %s", (cid,)).fetchone()[0] is False
    tela.click(f"[data-acao=setor-conta-retomar][data-id='{cid}']")
    tela.wait_for_selector("#recado >> text=Conta retomada")
    assert db.execute("select ativa from radar_setor_contas where id = %s", (cid,)).fetchone()[0] is True
    tela.click(f"[data-acao=setor-conta-remover][data-id='{cid}']")
    tela.wait_for_selector("#recado >> text=Conta removida")
    assert db.execute("select count(*) from radar_setor_contas").fetchone()[0] == 2
    # renomear e apagar
    tela.fill("#setor-nome", "Contabilidade SC")
    tela.click("[data-form=setorRenomear] button.btn:not(.perigo)")
    tela.wait_for_selector("#recado >> text=Setor salvo")
    assert db.execute("select nome from radar_setor_setores where id = %s", (sid,)).fetchone()[0] == "Contabilidade SC"
    # setor inativo não é lido: sem o "Atualizar a análise" e com o recado (o banco também recusa, RADAR414)
    assert tela.locator("[data-acao=setor-atualizar]").count() == 1
    tela.uncheck("[data-form=setorRenomear] input[name=ativo]")
    tela.click("[data-form=setorRenomear] button.btn:not(.perigo)")
    tela.wait_for_selector("#setor-situacao >> text=Setor inativo: não é lido")
    assert tela.locator("[data-acao=setor-atualizar]").count() == 0
    assert db.execute("select ativo from radar_setor_setores where id = %s", (sid,)).fetchone()[0] is False
    tela.click("[data-acao=setor-apagar]")
    tela.wait_for_selector("#recado >> text=Setor apagado")
    assert db.execute("select count(*) from radar_setor_setores").fetchone()[0] == 0
    tela.wait_for_selector("[data-form=setorNovo]")


def test_atualizar_a_analise_le_ate_o_fim_e_respeita_a_pausa(tela):
    cenario(tela.db)
    tela.db.execute("update radar_setor_contas set coletada_em = now() - interval '1 day', tentada_em = null")
    pedidos = []
    funcao_imitada(tela, [(200, {"versao": VERSAO_TELA, "coleta": 1, "lidas": 3, "com_erro": 1, "faltam": 1, "chamadas": 4, "contas": []}),
                          (200, {"versao": VERSAO_TELA, "coleta": 2, "lidas": 0, "com_erro": 0, "faltam": 0, "chamadas": 0, "contas": []}),
                          (200, {"versao": VERSAO_TELA, "motivo": "pausa", "pausa_ate": "2026-10-19T17:30:00Z", "pausa_motivo": "limite"}),
                          (404, {"code": "NOT_FOUND", "message": "Requested function was not found"}),
                          (400, {"message": "Ação desconhecida."})], pedidos)
    abrir_setor(tela, ADMIN_EMAIL, "#setor-resumo")
    tela.click("[data-acao=setor-atualizar]")
    tela.wait_for_selector("#recado >> text=Análise atualizada: 3 conta(s) lida(s), 1 com erro")
    assert pedidos == [{"acao": "setor_coletar"}, {"acao": "setor_coletar"}]
    assert tela.db.execute("select count(*) from radar_setor_contas where pedida_em is not null").fetchone()[0] == 4   # o banco marcou o pedido
    tela.db.execute("update radar_setor_contas set pedida_em = null")
    tela.click("[data-acao=setor-atualizar]")
    tela.wait_for_selector("#recado >> text=A Meta pediu uma pausa até 19/10 às 14:30 (Brasília)")
    tela.click("[data-acao=setor-atualizar]")
    tela.wait_for_selector("#recado >> text=A função radar-concorrentes não está instalada no Supabase")
    tela.click("[data-acao=setor-atualizar]")
    tela.wait_for_selector("#recado >> text=faça o Deploy do index.ts desta versão")
    assert len(pedidos) == 5
    # lidas há menos de 6 horas: nada a atualizar (a função nem é chamada)
    tela.db.execute("update radar_setor_contas set coletada_em = now()")
    tela.click("[data-acao=setor-atualizar]")
    tela.wait_for_selector("#recado >> text=nada a atualizar")
    assert len(pedidos) == 5


def test_incluir_a_conta_da_artecon_e_a_configuracao(tela):
    sb.novo_setor()
    pedidos = []
    funcao_imitada(tela, [(200, {"versao": VERSAO_TELA, "usuario": "artecon.teste"})], pedidos)
    abrir_setor(tela, ADMIN_EMAIL, "#setor")
    tela.click("#setor-gerir-abrir")
    tela.wait_for_selector("#setor-gerir")
    tela.click("[data-acao=setor-incluir-artecon]")
    tela.wait_for_selector("#recado >> text=A conta da Artecon (@artecon.teste) foi incluída")
    assert pedidos == [{"acao": "setor_propria"}]
    assert tela.db.execute("select nome from radar_setor_contas").fetchall() == [("artecon.teste",)]
    # ligar a busca por hashtag (depois que a Meta aprovar) muda o quadro da hashtag
    tela.wait_for_selector("#setor-gerir")
    tela.check("[data-form=setorConfig] input[name=hashtag_ligada]")
    tela.fill("#setor-posts", "30")
    tela.click("[data-form=setorConfig] button.btn")
    tela.wait_for_selector("#recado >> text=Configuração salva")
    assert tela.db.execute("select valor from radar_config where chave = 'setor'").fetchone()[0] == {
        "coleta_ligada": True, "hashtag_ligada": True, "hashtag_modo": "top", "posts_por_conta": 30}
    tela.wait_for_selector("#setor-hashtag")
    assert "Aguardando a aprovação da Meta" not in tela.inner_text("#setor-hashtag")


def test_celular_sem_rolagem_lateral(tela):
    cenario(tela.db)
    tela.set_viewport_size({"width": 390, "height": 844})
    abrir_setor(tela, ADMIN_EMAIL, "#setor-resumo")
    assert sem_rolagem_lateral(tela)
    tela.click("#setor-gerir-abrir")
    tela.wait_for_selector("#setor-gerir")
    assert sem_rolagem_lateral(tela)


# ------------------------------------------------------------------------------------- o arquivo
def test_sem_o_arquivo_ou_de_outra_versao(tela):
    tela.route("**/radar-setor.js*", lambda rota: rota.fulfill(status=404, body="não encontrado"))
    abrir_setor(tela, LEITOR_EMAIL, "#setor-sem-arquivo")
    assert "Ctrl+F5" in tela.inner_text("#setor-sem-arquivo")
    tela.unroute("**/radar-setor.js*")
    antigo = (RAIZ / "radar-setor.js").read_text(encoding="utf-8").replace(f'const SETOR_VERSAO = "{VERSAO_TELA}"', 'const SETOR_VERSAO = "0.0.1"')
    tela.route("**/radar-setor.js*", lambda rota: rota.fulfill(status=200, content_type="application/javascript", body=antigo))
    tela.reload()
    tela.wait_for_selector("nav.abas")
    tela.click("nav.abas button[data-aba=setor]")
    tela.wait_for_selector("#setor-versao")
    assert "Aperte Ctrl+F5" in tela.inner_text("#setor-versao")


def test_nomes_globais_do_radar_setor_nao_colidem_com_os_outros_scripts():
    """A mesma regra do corretor de vídeo (test_video_nomes_globais_dos_tres_scripts_nao_colidem): os scripts clássicos dividem o
    escopo global; um nome repetido troca a função do outro em silêncio ou derruba o script. Os do radar-setor.js começam por setor/SETOR."""
    def nomes(texto):
        return set(re.findall(r"(?m)^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", texto)) | set(re.findall(r"(?m)^(?:const|let|var)\s+([A-Za-z_$][\w$]*)", texto))
    html = (RAIZ / "index.html").read_text(encoding="utf-8")
    setor = nomes((RAIZ / "radar-setor.js").read_text(encoding="utf-8"))
    assert len(setor) > 30 and all(re.match(r"(?i)setor|telaSetor$", n) or n == "telaSetor" for n in setor), setor
    for outro in (nomes((RAIZ / "radar-pauta.js").read_text(encoding="utf-8")), nomes((RAIZ / "radar-video.js").read_text(encoding="utf-8")),
                  nomes(html[html.index('<script>\n"use strict";'):])):
        assert setor & outro == set()
