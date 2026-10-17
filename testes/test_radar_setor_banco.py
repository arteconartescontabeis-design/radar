"""Aba Setor (v0.34.0): o banco. As quatro tabelas novas (setores, contas, publicações lidas e rodadas) com RLS, as funções radar_setor_*
(quem executa cada uma, o que recusam e com que código), os temas por palavras, a semana de leitura (segunda 04:00 de Brasília), as
contas devidas, a rodada (iniciar, gravar, concluir, a pausa da Meta) e o painel calculado à mão (cenário P: as medianas, a cobertura das
50 publicações, a série por semana, dias e horários em Brasília, temas e as publicações de maior engajamento, no máximo 3 por conta e com
só um trecho de 100 caracteres da legenda).

Dados de mentira: "ana.teste", "bruno.exemplo", "carla.ficticia" e a "artecon.teste" (a conta da Artecon de mentira); nada real. Cada
teste limpa as tabelas radar_setor_* e a linha "setor" de radar_config, antes e depois (o conftest não mexe nelas).
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

import psycopg
import pytest

from conftest import ADMIN, EDITOR, LEITOR, RAIZ, SEM_PERFIL, SETUP, como, psql

TABELAS = ("radar_setor_setores", "radar_setor_contas", "radar_setor_posts", "radar_setor_coletas")
DA_TELA = {"radar_setor_salvar", "radar_setor_apagar", "radar_setor_conta_incluir", "radar_setor_conta_mudar", "radar_setor_conta_remover",
           "radar_setor_pedir", "radar_setor_configurar", "radar_setor_painel", "radar_setor_situacao"}
DA_FUNCAO = {"radar_setor_iniciar", "radar_setor_gravar", "radar_setor_concluir"}
COMUNS = {"das", "ir", "de", "da", "do", "para", "com", "time", "case", "mes", "ate", "nos", "sim"}
SECRETA = "LEGENDA_SECRETA"


def limpar(db):
    db.execute("truncate radar_setor_setores, radar_setor_coletas restart identity cascade")
    db.execute("delete from radar_config where chave = 'setor'")


@pytest.fixture()
def setor(limpo):
    limpar(limpo)
    yield limpo
    limpar(limpo)


def chamar(uid, sql, args=()):
    with como("authenticated", uid) as c:
        return c.execute(sql, args).fetchone()[0]


def novo_setor(nome="Contabilidade", uid=ADMIN):
    return chamar(uid, "select radar_setor_salvar(null, %s, null, true)", (nome,))


def incluir(setor_id, texto, uid=ADMIN):
    return chamar(uid, "select radar_setor_conta_incluir(%s, %s)", (setor_id, texto))


# ------------------------------------------------------------------------------------- o cenário P
def legenda_longa():
    """300 caracteres: os 100 primeiros falam do prazo do Simples; LEGENDA_SECRETA vem depois do 100º (nunca pode aparecer na tela)."""
    comeco = ("Prazo do Simples Nacional: o que muda para a sua empresa neste mês e como se preparar sem correria. " * 2)[:110]
    return (comeco + " " + SECRETA + " " + "x" * 300)[:300]


def cenario_p(db, hoje: date, coletada: str):
    """As quatro contas do cenário P, com as datas contadas a partir de "hoje" (as horas são de Brasília). Devolve o id do setor."""
    sid = db.execute("insert into radar_setor_setores (nome, temas) values ('Contabilidade', radar_setor_temas_padrao()) returning id").fetchone()[0]
    seq = iter(range(1, 1000))

    def conta(nome, seg, total, propria=False):
        return db.execute("""insert into radar_setor_contas (setor_id, nome, seguidores, posts_total, propria, coletada_em, tentada_em, meta_id)
                             values (%s, %s, %s, %s, %s, %s, %s, %s) returning id""",
                          (sid, nome, seg, total, propria, coletada, coletada, str(17841400000000100 + next(seq)))).fetchone()[0]

    def post(cid, dias, hora, formato, curtidas, comentarios=0, legenda="Publicação de teste do setor."):
        tipo, produto = {"reel": ("VIDEO", "REELS"), "foto": ("IMAGE", "FEED"), "carrossel": ("CAROUSEL_ALBUM", "FEED")}[formato]
        n = next(seq)
        quando = f"{(hoje + timedelta(days=dias)).isoformat()} {hora}-03"
        db.execute("""insert into radar_setor_posts (conta_id, midia_id, publicado_em, tipo, produto, curtidas, comentarios, seguidores, legenda,
                                                     temas, link)
                      select %s, %s, %s, %s, %s, %s, %s, c.seguidores, %s, radar_setor_temas_de(%s, '{}', radar_setor_temas_padrao()), %s
                        from radar_setor_contas c where c.id = %s""",
                   (cid, f"1790000000{n:04d}", quando, tipo, produto, curtidas, comentarios, legenda, legenda,
                    f"https://www.instagram.com/p/Teste{n}/", cid))

    ana = conta("ana.teste", 1000, 6)
    post(ana, -4, "09:30", "reel", 30, legenda="Dica rápida: como funciona o MEI na prática.")
    post(ana, -11, "09:15", "foto", 10, legenda="Feliz Dia do Contador!")
    post(ana, -18, "19:00", "carrossel", 20, legenda="Entenda a reforma tributária: IBS e CBS.")
    post(ana, -25, "12:00", "foto", None, 5)
    post(ana, -2, "23:30", "reel", 40, legenda="Declaração do Imposto de Renda: o que separar.")
    post(ana, -22, "06:00", "foto", 5)
    bruno = conta("bruno.exemplo", 2000, 100)
    post(bruno, -14, "10:00", "foto", 20)
    post(bruno, -10, "10:00", "foto", 40, legenda="Nossa equipe na confraternização.")
    post(bruno, -8, "15:00", "reel", 100, legenda=legenda_longa())
    post(bruno, -6, "10:00", "carrossel", 30, 10, legenda="Simples Nacional: fator R explicado.")
    post(bruno, -1, "10:00", "foto", 10)
    carla = conta("carla.ficticia", 50, 5)
    for d in (-23, -16, -9, -7, -3):
        post(carla, d, "10:00", "foto", 5)
    art = conta("artecon.teste", 1500, 3, propria=True)
    post(art, -17, "10:00", "foto", 15)
    post(art, -10, "10:00", "foto", 30)
    post(art, -3, "10:00", "reel", 45, legenda="Prazo do MEI: DASN-SIMEI até 31/05.")
    return sid


HOJE_P = date(2026, 10, 17)
AGORA_P = "2026-10-17 12:00-03"


def painel_p(db, dias=30):
    sid = cenario_p(db, HOJE_P, "2026-10-17 08:00-03")
    with db.cursor() as cur:
        cur.execute("set timezone = 'Pacific/Kiritimati'")                    # o servidor noutro fuso não muda o dia de Brasília
        r = cur.execute("select radar_setor_painel_em(%s, %s, %s)", (sid, dias, AGORA_P)).fetchone()[0]
        cur.execute("reset timezone")
    return sid, r


# ------------------------------------------------------------------------------------- tabelas e acesso
def test_tabelas_com_rls_e_so_a_equipe_le_setores_e_contas(setor):
    for t in TABELAS:
        assert setor.execute("select relrowsecurity from pg_class where relname = %s", (t,)).fetchone()[0] is True, t
        assert setor.execute("select count(*) from pg_policies where tablename = %s", (t,)).fetchone()[0] >= 1, t
    sid = novo_setor()
    incluir(sid, "@ana.teste")
    with como("anon") as c:
        for t in TABELAS:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(f"select * from {t}")
    for uid in (LEITOR, EDITOR, ADMIN):
        with como("authenticated", uid) as c:
            assert c.execute("select count(*) from radar_setor_setores").fetchone()[0] == 1
            assert c.execute("select count(*) from radar_setor_contas").fetchone()[0] == 1
    with como("authenticated", SEM_PERFIL) as c:                           # logado sem perfil: nenhuma linha
        assert c.execute("select count(*) from radar_setor_setores").fetchone()[0] == 0
    # ninguém lê as publicações nem as rodadas pela API (a tela recebe os números prontos), nem o administrador nem a chave interna
    for papel, uid in (("authenticated", ADMIN), ("authenticated", LEITOR), ("service_role", None)):
        for t in ("radar_setor_posts", "radar_setor_coletas"):
            with como(papel, uid) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(f"select * from {t}")
    # e ninguém grava direto: só pelas funções
    for papel, uid in (("authenticated", ADMIN), ("service_role", None), ("anon", None)):
        for sql in ("insert into radar_setor_setores (nome) values ('Outro')", "update radar_setor_setores set nome = 'X'",
                    "delete from radar_setor_setores", f"insert into radar_setor_contas (setor_id, nome) values ({sid}, 'bruno.exemplo')",
                    "update radar_setor_contas set ativa = false", "delete from radar_setor_contas",
                    "insert into radar_setor_coletas (origem) values ('admin')", "delete from radar_setor_posts"):
            with como(papel, uid) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)


def test_funcoes_quem_executa_e_nenhuma_usa_o_relogio_do_servidor(setor):
    funcoes = setor.execute("""select p.proname, p.prosecdef, p.proconfig is not null, p.prosrc,
                                      has_function_privilege('anon', p.oid, 'execute'), has_function_privilege('authenticated', p.oid, 'execute'),
                                      has_function_privilege('service_role', p.oid, 'execute')
                                 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                                where n.nspname = 'public' and p.proname like 'radar\\_setor\\_%'""").fetchall()
    nomes = {f[0] for f in funcoes}
    assert DA_TELA | DA_FUNCAO <= nomes and len(funcoes) >= 25
    for nome, definer, caminho, fonte, anon, aut, serv in funcoes:
        assert caminho, nome                                                       # search_path fixo
        assert not anon, nome
        assert aut == (nome in DA_TELA), nome
        assert serv == (nome in DA_FUNCAO), nome
        assert definer == (nome in DA_TELA | DA_FUNCAO), nome                      # as internas rodam como quem chama
        assert not re.search(r"current_date|localtime", fonte, re.I), nome         # o dia é sempre o de Brasília


# ------------------------------------------------------------------------------------- setores e temas
def test_salvar_setor_so_o_administrador_com_os_temas_padrao_e_o_historico(setor):
    for uid in (EDITOR, LEITOR):
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR400"):
            novo_setor(uid=uid)
    sid = novo_setor()
    temas = setor.execute("select temas from radar_setor_setores where id = %s", (sid,)).fetchone()[0]
    assert temas == setor.execute("select radar_setor_temas_padrao()").fetchone()[0] and len(temas) == 16
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR401"):
        novo_setor("  contabilidade ")                                           # o mesmo nome com outra caixa e espaços
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR413"):
        novo_setor("X")
    for i in range(9):
        novo_setor(f"Setor {i}")
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR402"):        # o 11º
        novo_setor("Mais um")
    for temas, numero in [([{"nome": "Sem palavras", "termos": []}], "Tema 1"), ([{"nome": f"T{i:02d}", "termos": ["ab"]} for i in range(21)], "20 temas"),
                          ([{"nome": "Ok", "termos": ["ab"]}, {"nome": "Curta", "termos": ["x"]}], "Tema 2"),
                          ([{"nome": "Prazo", "termos": ["ab"]}, {"nome": "PRAZO", "termos": ["cd"]}], "Tema 2"),
                          ([{"nome": "Outros", "termos": ["ab"]}], "Tema 1"), ([{"termos": ["ab"]}], "Tema 1")]:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR403") as e:
            chamar(ADMIN, "select radar_setor_salvar(%s, null, %s, null)", (sid, json.dumps(temas)))
        assert numero in str(e.value), (temas, str(e.value))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR412"):
        chamar(ADMIN, "select radar_setor_salvar(999999, 'Outro nome', null, null)")
    assert chamar(ADMIN, "select radar_setor_salvar(%s, 'Contabilidade SC', null, false)", (sid,)) == sid
    assert setor.execute("select nome, ativo from radar_setor_setores where id = %s", (sid,)).fetchone() == ("Contabilidade SC", False)
    # o Histórico registra criar e renomear (sem o administrador escrever nada à mão)
    assert setor.execute("select count(*) from radar_auditoria where tabela = 'radar_setor_setores' and registro_id = %s", (str(sid),)).fetchone()[0] >= 2


@pytest.mark.parametrize("legenda, hashtags, esperado", [
    ("Declaração do Imposto de Renda 2027", [], ["Imposto de Renda"]),
    ("Sem palavra nenhuma aqui", ["impostoderenda"], ["Imposto de Renda"]),
    ("Reforma Tributária: o que muda com o IBS", [], ["Reforma tributária"]),
    ("Cuidar do meio ambiente", [], []),                                           # "meio" não é MEI
    ("Prazo do MEI: DASN-SIMEI até 31/05", [], ["MEI", "Prazos e obrigações"]),
    ("Feliz Dia do Contador!", [], ["Datas comemorativas"]),
    ("Atendimento das 8h às 18h", [], []),                                         # "das" não é sigla de nada
    ("", [], []),
    ("Emita a nf-e hoje", [], ["Notas e impostos"]),
    ("Qualquer coisa", ["NFe"], ["Notas e impostos"]),
    ("ATENÇÃO À DECLARAÇÃO DO IR", [], ["Imposto de Renda", "Dicas e explicações"]),
])
def test_temas_por_palavras(setor, legenda, hashtags, esperado):
    assert setor.execute("select radar_setor_temas_de(%s, %s, radar_setor_temas_padrao())", (legenda, hashtags)).fetchone()[0] == esperado


def test_lista_padrao_de_temas_e_a_mesma_da_tela(setor):
    padrao = setor.execute("select radar_setor_temas_padrao()").fetchone()[0]
    assert len(padrao) == 16 and setor.execute("select radar_setor_temas_validar(radar_setor_temas_padrao())").fetchone()[0] is None
    termos = [setor.execute("select radar_setor_sem_acento(%s)", (t,)).fetchone()[0] for tema in padrao for t in tema["termos"]]
    assert not COMUNS & set(termos), COMUNS & set(termos)
    # o botão "Voltar aos temas padrão" (radar-setor.js) preenche a caixa com a mesma lista
    js = (RAIZ / "radar-setor.js").read_text(encoding="utf-8")
    bloco = js[js.index("const SETOR_TEMAS_PADRAO = ["):js.index("]];", js.index("const SETOR_TEMAS_PADRAO = [")) + 2]
    tela = [(n, [t.strip() for t in ts.split(",")]) for n, ts in re.findall(r'\["([^"]+)", "([^"]+)"\]', bloco)]
    assert tela == [(t["nome"], t["termos"]) for t in padrao]


def test_salvar_temas_reclassifica_so_as_publicacoes_daquele_setor(setor):
    a, b = novo_setor("Setor A"), novo_setor("Setor B")
    incluir(a, "@ana.teste")
    incluir(b, "@ana.teste")
    for sid in (a, b):
        setor.execute("""insert into radar_setor_posts (conta_id, midia_id, publicado_em, tipo, legenda, temas)
                         select id, '1', now() - interval '1 day', 'IMAGE', 'Hoje tem bolo de cenoura', '{}' from radar_setor_contas where setor_id = %s""", (sid,))
    chamar(ADMIN, "select radar_setor_salvar(%s, null, %s, null)", (a, json.dumps([{"nome": "Comida", "termos": ["bolo", "cenoura"]}])))
    temas = dict(setor.execute("select c.setor_id, p.temas from radar_setor_posts p join radar_setor_contas c on c.id = p.conta_id").fetchall())
    assert temas == {a: ["Comida"], b: []}


# ------------------------------------------------------------------------------------- contas
def test_incluir_contas_reconhece_arroba_link_e_hashtag_e_respeita_os_limites(setor):
    sid = novo_setor()
    texto = "@Ana.Teste, https://www.instagram.com/bruno.exemplo/ \n #Contabilidade ; https://www.instagram.com/p/X1/ conta-com-hífen"
    assert incluir(sid, texto) == {"contas": 2, "hashtags": 1, "repetidas": 0, "invalidas": [4, 5]}
    assert incluir(sid, texto) == {"contas": 0, "hashtags": 0, "repetidas": 3, "invalidas": [4, 5]}
    contas = setor.execute("select tipo, nome, pedida_em is not null, criado_por::text from radar_setor_contas order by id").fetchall()
    assert contas == [("conta", "ana.teste", True, ADMIN), ("conta", "bruno.exemplo", True, ADMIN), ("hashtag", "contabilidade", True, ADMIN)]
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR400"):
        incluir(sid, "@carla.ficticia", uid=EDITOR)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR410"):
        incluir(sid, " ".join(f"@conta{i}" for i in range(51)))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR410"):
        incluir(sid, " , ; \n")
    # 30 contas por setor (nada entra quando passa)
    incluir(sid, "\n".join(f"@s1.conta{i}" for i in range(28)))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR404"):
        incluir(sid, "@ultima.a @ultima.b")
    assert setor.execute("select count(*) from radar_setor_contas where setor_id = %s and tipo = 'conta'", (sid,)).fetchone()[0] == 30
    # 60 contas ativas no Radar, contando a mesma @ uma vez
    s2, s3 = novo_setor("Setor dois"), novo_setor("Setor três")
    incluir(s2, "\n".join(f"@s2.conta{i}" for i in range(30)))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR405"):
        incluir(s3, "@nova.conta")
    assert incluir(s3, "@ana.teste")["contas"] == 1                            # a mesma @ de outro setor não conta de novo
    # 5 hashtags por setor
    incluir(sid, "#um #dois #tres #quatro")
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR406"):
        incluir(sid, "#cinco")


def test_pausar_retomar_e_remover_conta(setor):
    sid = novo_setor()
    incluir(sid, "@ana.teste")
    cid = setor.execute("select id from radar_setor_contas").fetchone()[0]
    setor.execute("update radar_setor_contas set falhas_consecutivas = 3, erro = 'conta não encontrada', pedida_em = null")
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR400"):
        chamar(EDITOR, "select radar_setor_conta_mudar(%s, false)", (cid,))
    chamar(ADMIN, "select radar_setor_conta_mudar(%s, false)", (cid,))
    assert setor.execute("select ativa from radar_setor_contas").fetchone()[0] is False
    chamar(ADMIN, "select radar_setor_conta_mudar(%s, true)", (cid,))
    assert setor.execute("select ativa, falhas_consecutivas, erro, pedida_em is not null from radar_setor_contas").fetchone() == (True, 0, None, True)
    setor.execute("""insert into radar_setor_posts (conta_id, midia_id, publicado_em, tipo) values (%s, '1', now(), 'IMAGE'), (%s, '2', now(), 'IMAGE')""", (cid, cid))
    assert chamar(ADMIN, "select radar_setor_conta_remover(%s)", (cid,)) == 2
    assert setor.execute("select count(*) from radar_setor_posts").fetchone()[0] == 0
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR412"):
        chamar(ADMIN, "select radar_setor_conta_remover(%s)", (cid,))
    assert chamar(ADMIN, "select radar_setor_apagar(%s)", (sid,)) == 0
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR412"):
        chamar(ADMIN, "select radar_setor_apagar(%s)", (sid,))


# ------------------------------------------------------------------------------------- a semana de leitura e as devidas
def test_corte_da_semana_e_segunda_04h_de_brasilia(setor):
    with setor.cursor() as c:
        c.execute("set timezone = 'Pacific/Kiritimati'")
        for agora, corte in (("2026-10-19 06:59Z", "2026-10-12 07:00Z"), ("2026-10-19 07:00Z", "2026-10-19 07:00Z"),
                             ("2026-10-25 23:00Z", "2026-10-19 07:00Z")):
            assert c.execute("select radar_setor_corte(%s) = %s::timestamptz", (agora, corte)).fetchone()[0] is True, agora
        c.execute("reset timezone")


def devidas(db, agora, origem="agenda"):
    return [tuple(r) for r in db.execute("select tipo, nome, cardinality(ids) from radar_setor_devidas_em(%s, %s)", (agora, origem)).fetchall()]


def test_contas_devidas_uma_vez_por_semana(setor):
    sid = novo_setor()
    incluir(sid, "@ana.teste @bruno.exemplo @carla.ficticia #contabilidade")
    setor.execute("update radar_setor_contas set pedida_em = null")
    seg = "2026-10-19 07:00Z"                                                      # segunda, 04:00 de Brasília
    setor.execute("update radar_setor_contas set coletada_em = '2026-10-18 20:00Z' where nome = 'ana.teste'")    # domingo, antes do corte
    setor.execute("update radar_setor_contas set coletada_em = '2026-10-19 07:30Z' where nome = 'bruno.exemplo'")  # depois do corte
    assert devidas(setor, "2026-10-19 08:00Z") == [("conta", "carla.ficticia", 1), ("conta", "ana.teste", 1)]   # nunca lida antes
    assert devidas(setor, "2026-10-19 06:00Z") == [("conta", "carla.ficticia", 1)]                              # domingo: ana já leu
    # 3 falhas seguidas: fora da agenda, mas o pedido do administrador entra
    setor.execute("update radar_setor_contas set falhas_consecutivas = 3, tentada_em = '2026-10-10Z' where nome = 'carla.ficticia'")
    assert ("conta", "carla.ficticia", 1) not in devidas(setor, seg)
    setor.execute("update radar_setor_contas set pedida_em = '2026-10-19 07:55Z' where nome = 'carla.ficticia'")
    assert ("conta", "carla.ficticia", 1) in devidas(setor, "2026-10-19 08:00Z", "admin")
    assert ("conta", "carla.ficticia", 1) not in devidas(setor, "2026-10-19 08:00Z")                          # pedido há 5 minutos: o botão
    assert ("conta", "carla.ficticia", 1) in devidas(setor, "2026-10-19 08:06Z")                              # há 11: o botão não terminou
    # setor inativo ou conta pausada: fora
    setor.execute("update radar_setor_contas set ativa = false where nome = 'ana.teste'")
    assert ("conta", "ana.teste", 1) not in devidas(setor, "2026-10-19 08:00Z")
    setor.execute("update radar_setor_setores set ativo = false")
    assert devidas(setor, "2026-10-19 08:00Z") == [] and devidas(setor, "2026-10-19 08:00Z", "admin") == []
    setor.execute("update radar_setor_setores set ativo = true; update radar_setor_contas set ativa = true")
    # hashtag: só com a busca ligada; sem número, só com menos de 30 buscadas em 7 dias
    assert all(t != "hashtag" for t, *_ in devidas(setor, "2026-10-19 08:00Z"))
    setor.execute("""insert into radar_config (chave, valor) values ('setor', '{"hashtag_ligada": true}')""")
    assert ("hashtag", "contabilidade", 1) in devidas(setor, "2026-10-19 08:00Z")
    outro = novo_setor("Outro")
    setor.execute("""insert into radar_setor_coletas (origem, iniciada_em, terminada_em, buscas)
                     values ('agenda', '2026-10-18Z', '2026-10-18Z', array(select 'tag' || i from generate_series(1, 30) i))""")
    assert ("hashtag", "contabilidade", 1) not in devidas(setor, "2026-10-19 08:00Z")
    setor.execute("update radar_setor_contas set meta_id = '17843853986012965' where nome = 'contabilidade'")
    assert ("hashtag", "contabilidade", 1) in devidas(setor, "2026-10-19 08:00Z")                             # já tem o número
    # a mesma @ em dois setores: um item com as duas linhas
    incluir(outro, "@ana.teste")
    setor.execute("update radar_setor_contas set pedida_em = null, coletada_em = null where nome = 'ana.teste'")
    assert ("conta", "ana.teste", 2) in devidas(setor, "2026-10-19 08:00Z")


def test_ha_devidas_diz_nao_com_pausa_rodada_aberta_ou_desligada(setor):
    sid = novo_setor()
    incluir(sid, "@ana.teste")
    agora = "2026-10-19 08:00Z"
    ha = lambda: setor.execute("select radar_setor_ha_devidas_em(%s)", (agora,)).fetchone()[0]
    assert ha() is True
    setor.execute("insert into radar_setor_coletas (origem, iniciada_em) values ('agenda', '2026-10-19 07:59Z')")      # aberta há 1 minuto
    assert ha() is False
    setor.execute("update radar_setor_coletas set terminada_em = iniciada_em, pausa_ate = '2026-10-19 09:00Z', pausa_motivo = 'limite'")
    assert ha() is False
    setor.execute("update radar_setor_coletas set pausa_ate = '2026-10-19 07:59Z'")
    assert ha() is True
    setor.execute("""insert into radar_config (chave, valor) values ('setor', '{"coleta_ligada": false}')""")
    assert ha() is False
    assert setor.execute("select radar_setor_ha_devidas()").fetchone()[0] is False


# ------------------------------------------------------------------------------------- a rodada
def iniciar(db, origem="agenda", limite=12, agora=None):
    """A rodada começa agora (o relógio do banco) ou na hora pedida."""
    if agora is None:
        return db.execute("select radar_setor_iniciar_em(%s, %s, now())", (origem, limite)).fetchone()[0]
    return db.execute("select radar_setor_iniciar_em(%s, %s, %s)", (origem, limite, agora)).fetchone()[0]


def test_iniciar_a_rodada(setor):
    sid = novo_setor()
    assert iniciar(setor) == {"motivo": "nada"} and setor.execute("select count(*) from radar_setor_coletas").fetchone()[0] == 0
    incluir(sid, " ".join(f"@conta{i:02d}" for i in range(13)))
    with como("service_role") as c:                                              # a função radar-concorrentes, pela chave interna
        r = c.execute("select radar_setor_iniciar('admin', 50)").fetchone()[0]
    assert len(r["contas"]) == 12 and r["posts"] == 50 and r["hashtag_modo"] == "top"
    assert r["contas"][0] == {"tipo": "conta", "nome": "conta00", "meta_id": None}
    assert iniciar(setor) == {"motivo": "em_andamento"}
    # a rodada que ficou aberta há mais de 4 minutos é fechada com o recado, e a nova começa
    setor.execute("update radar_setor_coletas set iniciada_em = now() - interval '5 minutes'")
    r = iniciar(setor)
    assert len(r["contas"]) == 12
    assert setor.execute("select terminada_em is not null, geral from radar_setor_coletas order by id limit 1").fetchone() == (True, "não terminou (a função parou no meio)")
    setor.execute("update radar_setor_coletas set terminada_em = iniciada_em")
    # a pausa de limite recusa o botão e a agenda; a de configuração, só a agenda
    setor.execute("update radar_setor_coletas set pausa_ate = now() + interval '1 hour', pausa_motivo = 'limite' where id = (select max(id) from radar_setor_coletas)")
    for origem in ("agenda", "admin"):
        r = iniciar(setor, origem)
        assert r["motivo"] == "pausa" and r["pausa_motivo"] == "limite", origem
    setor.execute("update radar_setor_coletas set pausa_motivo = 'configuracao'")
    assert iniciar(setor, "agenda")["motivo"] == "pausa"
    assert len(iniciar(setor, "admin")["contas"]) == 12
    setor.execute("update radar_setor_coletas set terminada_em = iniciada_em, pausa_ate = null, pausa_motivo = null")
    setor.execute("""insert into radar_config (chave, valor) values ('setor', '{"coleta_ligada": false}')""")
    assert iniciar(setor, "agenda") == {"motivo": "desligada"}
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        chamar(ADMIN, "select radar_setor_iniciar('admin', 12)")


def post_meta(i, **x):
    return {"id": f"1790000000{i:04d}", "data": "2026-10-10T12:00:00Z", "tipo": "IMAGE", "produto": "FEED", "curtidas": 10, "comentarios": 1,
            "legenda": f"Publicação {i} sobre o MEI", "hashtags": ["#MEI", "contabilidade"], "link": f"https://www.instagram.com/p/T{i}/"} | x


def gravar(coleta, nome, dados, tipo="conta"):
    with como("service_role") as c:
        return c.execute("select radar_setor_gravar(%s, %s, %s, %s)", (coleta, tipo, nome, json.dumps(dados))).fetchone()[0]


def test_gravar_a_leitura_de_uma_conta(setor):
    a, b = novo_setor("Setor A"), novo_setor("Setor B")
    incluir(a, "@ana.teste")
    incluir(b, "@ana.teste")
    chamar(ADMIN, "select radar_setor_salvar(%s, null, %s, null)", (b, json.dumps([{"nome": "Contabilidade", "termos": ["contabilidade"]}])))
    k = iniciar(setor, "admin")["coleta"]
    longa = "começo " + "x" * 600
    tags = [f"#Tag{i}" for i in range(25)] + ["#tag0"]
    posts = [post_meta(1), post_meta(2, legenda=longa, hashtags=tags), post_meta(3, curtidas=None),
             post_meta(4, link="https://evil.test/p/1/"), post_meta(5, id="1 2"), post_meta(6, data="ontem"), post_meta(7, data="2099-01-01T00:00:00Z"),
             post_meta(8, tipo="STORY"), post_meta(9, curtidas=-1), post_meta(1), post_meta(10, data="2020-01-01T00:00:00Z")]
    dados = {"ok": True, "meta_id": "17841400000000001", "propria": True, "seguidores": 1200, "posts_total": 80, "aviso": "vieram 11 dos 50 posts", "posts": posts}
    assert gravar(k, "ana.teste", dados) == {"gravados": 4, "ignorados": 7}
    linhas = setor.execute("""select c.setor_id, p.midia_id, p.curtidas, p.seguidores, char_length(p.legenda), cardinality(p.hashtags), p.hashtags[1], p.temas, p.formato
                                from radar_setor_posts p join radar_setor_contas c on c.id = p.conta_id order by 1, 2""").fetchall()
    assert len(linhas) == 6                                                      # 3 em cada setor (a de 2020 saiu pela guarda de 400 dias)
    por_setor = {(s, m): (cur, seg, n, nh, h1, t, f) for s, m, cur, seg, n, nh, h1, t, f in linhas}
    assert por_setor[(a, "17900000000001")] == (10, 1200, len("Publicação 1 sobre o MEI"), 2, "mei", ["MEI"], "foto")
    assert por_setor[(b, "17900000000001")][5] == ["Contabilidade"]              # os temas são os do setor de cada linha
    assert por_setor[(a, "17900000000002")][2:5] == (300, 20, "tag0")           # legenda cortada; 20 hashtags, minúsculas, sem # e sem repetir
    assert por_setor[(a, "17900000000003")][0] is None                          # curtidas ocultas
    conta = setor.execute("""select seguidores, posts_total, meta_id, propria, coletada_em is not null, pedida_em, erro, aviso, falhas_consecutivas
                               from radar_setor_contas where setor_id = %s""", (a,)).fetchone()
    assert conta == (1200, 80, "17841400000000001", True, True, None, None, "vieram 11 dos 50 posts", 0)
    # até onde a leitura chegou: a mais antiga recebida (a de 2020, mesmo sem ser guardada), porque vieram menos que as 80 da conta
    assert setor.execute("select lido_desde = '2020-01-01Z' from radar_setor_contas where setor_id = %s", (a,)).fetchone()[0] is True
    # a 2ª leitura atualiza as curtidas sem duplicar
    gravar(k, "ana.teste", dados | {"posts": [post_meta(1, curtidas=99)]})
    assert setor.execute("select count(*), max(curtidas) from radar_setor_posts p join radar_setor_contas c on c.id = p.conta_id where c.setor_id = %s and midia_id = '17900000000001'", (a,)).fetchone() == (1, 99)
    # recusa da conta: conta falha, sai do pedido e as publicações antigas ficam
    setor.execute("update radar_setor_contas set pedida_em = now()")
    gravar(k, "ana.teste", {"ok": False, "erro": "conta não encontrada, privada ou que não é comercial/criador (Meta 110/2207013)", "codigo": "110/2207013", "geral": False})
    assert setor.execute("select falhas_consecutivas, pedida_em, erro_codigo from radar_setor_contas where setor_id = %s", (a,)).fetchone() == (1, None, "110/2207013")
    assert setor.execute("select count(*) from radar_setor_posts").fetchone()[0] == 6
    # recusa geral (token, limite): não conta falha e a conta continua pedida
    setor.execute("update radar_setor_contas set pedida_em = now()")
    gravar(k, "ana.teste", {"ok": False, "erro": "limite de chamadas da Meta atingido", "codigo": "4", "geral": True})
    assert setor.execute("select falhas_consecutivas, pedida_em is not null, erro from radar_setor_contas where setor_id = %s", (a,)).fetchone() == (1, True, "limite de chamadas da Meta atingido")
    gravar(k, "ana.teste", dados)                                                # sucesso zera as falhas
    assert setor.execute("select falhas_consecutivas, erro from radar_setor_contas where setor_id = %s", (a,)).fetchone() == (0, None)
    assert setor.execute("select lidas, com_erro, posts from radar_setor_coletas where id = %s", (k,)).fetchone() == (3, 2, 9)
    # conta que não existe (removida no meio): nada
    assert gravar(k, "outra.conta", dados) == {"gravados": 0, "ignorados": 0}
    # rodada fechada: recusa
    setor.execute("update radar_setor_coletas set terminada_em = now()")
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR409"):
        gravar(k, "ana.teste", dados)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        chamar(ADMIN, "select radar_setor_gravar(1, 'conta', 'ana.teste', '{}')")


def test_concluir_a_rodada_e_a_pausa(setor):
    sid = novo_setor()
    incluir(sid, "@ana.teste @bruno.exemplo")
    agora = "2026-10-19 08:00Z"
    for minutos, esperado in ((10, 30), (90, 90), (5000, 1440), (0, None)):
        k = iniciar(setor, "admin", agora=agora)["coleta"]
        r = setor.execute("select radar_setor_concluir_em(%s, %s, %s)", (k, json.dumps({"chamadas": 3, "uso_max": 85, "codigos": "4", "pausa_minutos": minutos,
                                                                                        "pausa_motivo": "limite"}), agora)).fetchone()[0]
        assert r["faltam"] == 2                                                   # as duas continuam pedidas
        ate = setor.execute("select extract(epoch from pausa_ate - %s::timestamptz) / 60, chamadas, uso_max, codigos from radar_setor_coletas where id = %s",
                            (agora, k)).fetchone()
        assert (None if ate[0] is None else int(ate[0])) == esperado and ate[1:] == (3, 85, "4"), minutos
        setor.execute("update radar_setor_coletas set pausa_ate = null, pausa_motivo = null")
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR409"):
        setor.execute("select radar_setor_concluir_em(%s, '{}', now())", (k,))
    # a pausa de configuração cai quando uma rodada lê alguma conta sem pedir pausa
    setor.execute("update radar_setor_coletas set pausa_ate = %s::timestamptz + interval '6 hours', pausa_motivo = 'configuracao' where id = %s", (agora, k))
    k2 = iniciar(setor, "admin", agora=agora)["coleta"]
    setor.execute("update radar_setor_coletas set lidas = 1 where id = %s", (k2,))
    setor.execute("select radar_setor_concluir_em(%s, '{}', %s)", (k2, agora))
    assert setor.execute("select count(*) from radar_setor_pausa_em(%s)", (agora,)).fetchone()[0] == 0
    # ficam as 200 rodadas mais novas
    setor.execute("insert into radar_setor_coletas (origem, terminada_em) select 'agenda', now() from generate_series(1, 230)")
    k3 = iniciar(setor, "admin", agora=agora)["coleta"]
    setor.execute("select radar_setor_concluir_em(%s, '{}', %s)", (k3, agora))
    assert setor.execute("select count(*), max(id) from radar_setor_coletas").fetchone() == (200, k3)


def test_pedir_num_setor_inativo_recusa(setor):
    """Revisão da v0.34.0: o setor inativo não é lido; o "Atualizar a análise" dele é recusado (antes marcava as contas e a tela dizia
    "Nada a ler agora")."""
    sid = novo_setor()
    incluir(sid, "@ana.teste @bruno.exemplo")
    setor.execute("update radar_setor_contas set pedida_em = null")
    chamar(ADMIN, "select radar_setor_salvar(%s, null, null, false)", (sid,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR414") as e:
        chamar(ADMIN, "select radar_setor_pedir(%s)", (sid,))
    assert "inativo" in str(e.value) and "Setor ativo" in str(e.value)
    assert setor.execute("select count(*) from radar_setor_contas where pedida_em is not null").fetchone()[0] == 0
    chamar(ADMIN, "select radar_setor_salvar(%s, null, null, true)", (sid,))
    assert chamar(ADMIN, "select radar_setor_pedir(%s)", (sid,)) == {"pedidas": 2, "recentes": 0}


def test_pedir_a_atualizacao(setor):
    sid = novo_setor()
    incluir(sid, "@ana.teste @bruno.exemplo #contabilidade")
    setor.execute("update radar_setor_contas set pedida_em = null")
    setor.execute("update radar_setor_contas set coletada_em = now() - interval '1 hour' where nome = 'ana.teste'")
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR400"):
        chamar(EDITOR, "select radar_setor_pedir(%s)", (sid,))
    assert chamar(ADMIN, "select radar_setor_pedir(%s)", (sid,)) == {"pedidas": 1, "recentes": 1}   # a hashtag (desligada) fica fora
    assert setor.execute("select nome from radar_setor_contas where pedida_em is not null").fetchall() == [("bruno.exemplo",)]
    setor.execute("insert into radar_setor_coletas (origem, terminada_em, pausa_ate, pausa_motivo) values ('agenda', now(), now() + interval '2 hours', 'limite')")
    hora = setor.execute("select to_char(pausa_ate at time zone 'America/Sao_Paulo', 'HH24:MI') from radar_setor_coletas").fetchone()[0]
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR407") as e:
        chamar(ADMIN, "select radar_setor_pedir(%s)", (sid,))
    assert hora in str(e.value) and "Brasília" in str(e.value)


def test_configurar(setor):
    assert setor.execute("select radar_setor_cfg()").fetchone()[0] == {"coleta_ligada": True, "hashtag_ligada": False, "hashtag_modo": "top", "posts_por_conta": 50}
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR400"):
        chamar(EDITOR, "select radar_setor_configurar('{}')")
    for ruim, chave in (({"outra": 1}, "outra"), ({"posts_por_conta": 5}, "posts_por_conta"), ({"posts_por_conta": "50"}, "posts_por_conta"),
                        ({"hashtag_modo": "todos"}, "hashtag_modo"), ({"hashtag_ligada": "sim"}, "hashtag_ligada")):
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR411") as e:
            chamar(ADMIN, "select radar_setor_configurar(%s)", (json.dumps(ruim),))
        assert chave in str(e.value)
    r = chamar(ADMIN, "select radar_setor_configurar(%s)", (json.dumps({"hashtag_ligada": True, "posts_por_conta": 30}),))
    assert r == {"coleta_ligada": True, "hashtag_ligada": True, "hashtag_modo": "top", "posts_por_conta": 30}
    assert setor.execute("select count(*) from radar_auditoria where tabela = 'radar_config' and registro_id = 'setor'").fetchone()[0] == 1
    setor.execute("""update radar_config set valor = '{"posts_por_conta": 999, "hashtag_modo": 3, "coleta_ligada": false}' where chave = 'setor'""")
    assert setor.execute("select radar_setor_cfg()").fetchone()[0] == {"coleta_ligada": False, "hashtag_ligada": False, "hashtag_modo": "top", "posts_por_conta": 50}


def test_hashtags_buscadas_contam_mesmo_removidas_e_so_cabem_as_30(setor):
    """Revisão da v0.34.0: a conta das 30 hashtags diferentes em 7 dias (a regra da Meta) vem das rodadas, não da linha da hashtag:
    remover a hashtag ou apagar o setor não "devolve" a busca; das hashtags novas, só entram as que cabem no que sobrou."""
    setor.execute("""insert into radar_config (chave, valor) values ('setor', '{"hashtag_ligada": true}')""")
    sid = novo_setor()
    incluir(sid, "#um #dois")
    k = iniciar(setor, "admin")["coleta"]
    gravar(k, "um", {"ok": True, "meta_id": "17843853986010001", "buscada": True, "posts": []}, tipo="hashtag")
    # o número veio e a leitura das publicações falhou depois: a busca conta igual e o número fica (não busca de novo)
    gravar(k, "dois", {"ok": False, "erro": "a Meta recusou (Meta 100)", "codigo": "100", "geral": False, "buscada": True,
                       "meta_id": "17843853986010002"}, tipo="hashtag")
    gravar(k, "dois", {"ok": False, "erro": "de novo", "codigo": "100", "geral": False, "buscada": True}, tipo="hashtag")   # a mesma: 1 vez
    setor.execute("select radar_setor_concluir_em(%s, '{}', now())", (k,))
    assert setor.execute("select radar_setor_buscadas_em(now())").fetchone()[0] == 2
    assert setor.execute("select meta_id from radar_setor_contas where nome = 'dois'").fetchone()[0] == "17843853986010002"
    for (cid,) in setor.execute("select id from radar_setor_contas where nome = 'um'").fetchall():
        chamar(ADMIN, "select radar_setor_conta_remover(%s)", (cid,))
    chamar(ADMIN, "select radar_setor_apagar(%s)", (sid,))
    assert setor.execute("select radar_setor_buscadas_em(now())").fetchone()[0] == 2
    assert chamar(ADMIN, "select radar_setor_situacao()")["hashtags_7d"] == 2
    assert setor.execute("select radar_setor_buscadas_em(now() + interval '7 days 1 minute')").fetchone()[0] == 0
    # com 28 buscadas em 7 dias, das hashtags sem número só entram 2 (na ordem); a que já tem número entra sempre
    setor.execute("update radar_setor_coletas set buscas = buscas || array(select 'velha' || g from generate_series(1, 26) g) where id = %s", (k,))
    s2 = novo_setor("Outro")
    incluir(s2, "#nova1 #nova2 #nova3 #nova4")
    setor.execute("update radar_setor_contas set meta_id = '17843853986010009' where nome = 'nova4'")
    assert [n for (n,) in setor.execute("select nome from radar_setor_devidas_em(now(), 'admin')").fetchall()] == ["nova1", "nova2", "nova4"]
    # as rodadas com busca dos últimos 8 dias ficam, mesmo passando das 200
    setor.execute("insert into radar_setor_coletas (origem, terminada_em) select 'agenda', now() from generate_series(1, 230)")
    k2 = iniciar(setor, "admin")["coleta"]
    setor.execute("select radar_setor_concluir_em(%s, '{}', now())", (k2,))
    assert setor.execute("select count(*) from radar_setor_coletas where id = %s", (k,)).fetchone()[0] == 1
    assert setor.execute("select radar_setor_buscadas_em(now())").fetchone()[0] == 28


def test_guarda_dos_400_dias_vale_para_todas_as_contas(setor):
    """Revisão da v0.34.0: a publicação com mais de 400 dias sai de todas as contas — também da pausada, da que falhou 3 vezes e da de
    setor inativo, que nunca mais passam pela gravação —, no começo de qualquer rodada (até a que não acha nada para ler) e pela
    guarda diária (radar_setor_guardar_em, do sql/radar-setor-agenda.sql)."""
    sid, inativo = novo_setor(), novo_setor("Inativo")
    incluir(sid, "@ana.teste @bruno.exemplo @carla.ficticia")
    incluir(inativo, "@davi.exemplo")
    chamar(ADMIN, "select radar_setor_salvar(%s, null, null, false)", (inativo,))
    carla = setor.execute("select id from radar_setor_contas where nome = 'carla.ficticia'").fetchone()[0]
    chamar(ADMIN, "select radar_setor_conta_mudar(%s, false)", (carla,))
    setor.execute("update radar_setor_contas set pedida_em = null, coletada_em = now()")
    setor.execute("update radar_setor_contas set falhas_consecutivas = 3, erro = 'conta não encontrada' where nome = 'bruno.exemplo'")

    def guardar_velhas():
        setor.execute("""insert into radar_setor_posts (conta_id, midia_id, publicado_em, tipo, legenda)
                         select c.id, x.m, now() - x.d, 'IMAGE', 'LEGENDA_DE_TERCEIRO' from radar_setor_contas c
                          cross join (values ('velha', interval '500 days'), ('nova', interval '10 days')) x(m, d)
                         on conflict do nothing""")
    guardar_velhas()
    assert iniciar(setor, "admin") == {"motivo": "nada"}                          # nada a ler, mas a guarda rodou
    assert setor.execute("select count(*) filter (where midia_id = 'velha'), count(*) filter (where midia_id = 'nova') from radar_setor_posts").fetchone() == (0, 4)
    guardar_velhas()
    assert setor.execute("select radar_setor_guardar_em(now())").fetchone()[0] == 4
    assert setor.execute("select radar_setor_guardar_em(now() + interval '391 days')").fetchone()[0] == 4      # as "novas", 391 dias depois


def test_painel_cobertura_vai_ate_a_ultima_leitura(setor):
    """Revisão da v0.34.0: (1) os dias entre a última leitura e hoje não contam como "zero publicação" (duas contas que publicam todo
    dia, lidas em dias diferentes, dão o mesmo número); (2) a conta sem leitura no período fica sem o número e fora das medianas e de
    "com dados"; (4) a guarda dos 400 dias não faz a conta parecer cortada (lido_desde guarda até onde a leitura chegou)."""
    sid = setor.execute("insert into radar_setor_setores (nome, temas) values ('Contabilidade', '[]') returning id").fetchone()[0]

    def conta(nome, lida, erro=None, lido_desde=None):
        return setor.execute("""insert into radar_setor_contas (setor_id, nome, seguidores, posts_total, coletada_em, tentada_em, erro,
                                                               falhas_consecutivas, lido_desde)
                                values (%s, %s, 1000, 500, %s, %s, %s, %s, %s) returning id""",
                             (sid, nome, lida, lida, erro, 3 if erro else 0, lido_desde)).fetchone()[0]

    def diario(cid, ultimo):                                                       # uma publicação por dia, 60 dias, até "ultimo"
        setor.execute("""insert into radar_setor_posts (conta_id, midia_id, publicado_em, tipo, curtidas, comentarios, seguidores)
                         select %s, %s || g, %s::timestamptz - make_interval(days => g), 'IMAGE', 10, 0, 1000 from generate_series(0, 59) g""",
                      (cid, f"c{cid}x", ultimo))
    diario(conta("ana.teste", "2026-10-12 23:00-03"), "2026-10-12 10:00-03")     # lida na segunda passada à noite
    diario(conta("bruno.exemplo", "2026-10-18 11:00-03"), "2026-10-18 10:00-03")  # lida hoje (domingo)
    diario(conta("carla.ficticia", "2026-09-09 04:17-03", "conta não encontrada, privada ou que não é comercial/criador"), "2026-09-08 10:00-03")
    r = setor.execute("select radar_setor_painel_em(%s, 30, '2026-10-18 12:00-03')", (sid,)).fetchone()[0]
    c = {x["nome"]: x for x in r["contas"]}
    assert (c["ana.teste"]["posts_semana"], c["ana.teste"]["dias_cobertos"], c["ana.teste"]["truncado"]) == (7.0, 24, False)
    assert (c["bruno.exemplo"]["posts_semana"], c["bruno.exemplo"]["dias_cobertos"]) == (7.0, 30)
    assert (c["carla.ficticia"]["posts_semana"], c["carla.ficticia"]["dias_cobertos"], c["carla.ficticia"]["situacao"]) == (None, None, "erro")
    assert (r["resumo"]["contas"], r["resumo"]["com_dados"], r["resumo"]["setor_posts_semana"]) == (3, 2, 7.0)
    # (4) pela gravação: 10 publicações nos últimos 20 dias e 40 com mais de 500 dias (não guardadas): a leitura chegou ao começo
    sb2 = novo_setor("Setor B")
    incluir(sb2, "@davi.exemplo @eva.exemplo")
    k = iniciar(setor, "admin")["coleta"]
    hoje = setor.execute("select (now() at time zone 'America/Sao_Paulo')::date").fetchone()[0]
    dia = lambda n: f"{(hoje - timedelta(days=n)).isoformat()}T12:00:00-03:00"
    recentes = [post_meta(i, data=dia(2 * i)) for i in range(10)]
    velhas = [post_meta(100 + i, data=dia(500 + i)) for i in range(40)]
    assert gravar(k, "davi.exemplo", {"ok": True, "seguidores": 1000, "posts_total": 200, "posts": recentes + velhas})["gravados"] == 50
    # e uma que publica muito: as 50 lidas cobrem só os últimos 10 dias (essa, sim, cortada)
    muitas = [post_meta(200 + i, data=dia(i // 5)) for i in range(50)]
    gravar(k, "eva.exemplo", {"ok": True, "seguidores": 1000, "posts_total": 900, "posts": muitas})
    setor.execute("select radar_setor_concluir_em(%s, '{}', now())", (k,))
    r = setor.execute("select radar_setor_painel_em(%s, 30, now())", (sb2,)).fetchone()[0]
    c = {x["nome"]: x for x in r["contas"]}
    assert setor.execute("select count(*) from radar_setor_posts p join radar_setor_contas c on c.id = p.conta_id where c.nome = 'davi.exemplo'").fetchone()[0] == 10
    assert (c["davi.exemplo"]["n"], c["davi.exemplo"]["dias_cobertos"], c["davi.exemplo"]["truncado"], c["davi.exemplo"]["posts_semana"]) == (10, 30, False, 2.3333)
    assert (c["eva.exemplo"]["truncado"], c["eva.exemplo"]["dias_cobertos"], c["eva.exemplo"]["posts_semana"]) == (True, 10, 35.0)
    # leu todas (recebeu o total da conta): cobre desde sempre
    setor.execute("update radar_setor_contas set pedida_em = now() where nome = 'eva.exemplo'")
    k = iniciar(setor, "admin")["coleta"]
    gravar(k, "eva.exemplo", {"ok": True, "seguidores": 1000, "posts_total": 3, "posts": muitas[:3]})
    assert setor.execute("select lido_desde = '-infinity' from radar_setor_contas where nome = 'eva.exemplo'").fetchone()[0] is True


# ------------------------------------------------------------------------------------- o painel (cenário P)
def test_painel_cenario_p_por_conta(setor):
    _, r = painel_p(setor)
    assert r["periodo"] == {"dias": 30, "inicio": "2026-09-18", "fim": "2026-10-17", "agrupado": "semana"} and r["artecon"] is True
    contas = {c["nome"]: c for c in r["contas"]}
    ana, bruno, carla, art = (contas[n] for n in ("ana.teste", "bruno.exemplo", "carla.ficticia", "artecon.teste"))
    assert (ana["n"], ana["posts_semana"], ana["engajamento"], ana["n_engajamento"], ana["ocultas"], ana["elegivel"], ana["truncado"]) == (6, 1.4, 2.0, 5, 1, True, False)
    assert ana["formatos"] == {"reel": 2, "carrossel": 1, "foto": 3, "video": 0} and ana["situacao"] == "ok"
    assert (bruno["truncado"], bruno["dias_cobertos"], bruno["posts_semana"], bruno["engajamento"]) == (True, 15, 2.3333, 2.0)
    assert (carla["posts_semana"], carla["elegivel"], carla["situacao"]) == (1.1667, False, "poucos_dados")
    assert (art["posts_semana"], art["engajamento"], art["propria"]) == (0.7, 2.0, True)
    assert "tipico" not in ana and r["contas"][0]["nome"] == "artecon.teste"     # a Artecon primeiro; o número interno não sai


def test_painel_cenario_p_setor_formatos_e_serie(setor):
    _, r = painel_p(setor)
    res = r["resumo"]
    assert (res["contas"], res["com_dados"], res["elegiveis"], res["posts"]) == (3, 3, 2, 16)
    assert (res["setor_posts_semana"], res["setor_engajamento"], res["artecon_posts_semana"], res["artecon_engajamento"]) == (1.4, 2.0, 0.7, 2.0)
    assert res["formato_mais_usado"] == {"formato": "foto", "pct": 68.8}
    assert r["formatos"]["setor"] == {"foto": {"n": 11, "pct": 68.8}, "reel": {"n": 3, "pct": 18.8}, "carrossel": {"n": 2, "pct": 12.5}, "video": {"n": 0, "pct": 0.0}}
    assert r["formatos"]["artecon"]["reel"] == {"n": 1, "pct": 33.3}
    assert r["engajamento_formato"] == [{"formato": "reel", "mediana": 4.0, "n": 3}, {"formato": "carrossel", "mediana": 2.0, "n": 2},
                                        {"formato": "foto", "mediana": 1.0, "n": 5}, {"formato": "video", "mediana": None, "n": 0}]
    assert r["reel_vs_foto"] == {"acima": 0, "contas": 0}
    assert [(s["inicio"], s["setor"], s["contas"], s["artecon"], s["em_andamento"]) for s in r["series"]] == [
        ("2026-09-21", 1.5, 2, 0, False), ("2026-09-28", 1.0, 2, 1, False), ("2026-10-05", 2.0, 3, 1, False), ("2026-10-12", 1.3333, 3, 1, True)]


def test_painel_cenario_p_dias_horas_temas_e_melhores(setor):
    _, r = painel_p(setor)
    celulas = {(c["dia"], c["faixa"]): c for c in r["dias_horas"]["celulas"]}
    assert celulas[(4, 6)] == {"dia": 4, "faixa": 6, "n": 1, "rel": None}        # o reel das 23:30 de quinta (02:30 UTC de sexta)
    assert all(c["rel"] is None for c in celulas.values() if c["n"] < 5)
    assert [x for x in r["dias_horas"]["faixas"] if x["faixa"] == 2][0] == {"faixa": 2, "n": 6, "rel": 0.75}
    melhores = [(m["conta"], m["data"][:10], m["engajamento"]) for m in r["melhores"]]
    assert melhores == [("bruno.exemplo", "2026-10-09", 5.0), ("ana.teste", "2026-10-15", 4.0), ("ana.teste", "2026-10-13", 3.0),
                        ("bruno.exemplo", "2026-10-11", 2.0), ("bruno.exemplo", "2026-10-07", 2.0), ("ana.teste", "2026-09-29", 2.0)]
    assert r["melhores"][0]["rel"] == 2.5 and r["melhores"][1]["data"] == "2026-10-15T23:30"
    trecho = r["melhores"][0]["trecho"]
    assert len(trecho) == 101 and trecho.endswith("…") and SECRETA not in json.dumps(r, ensure_ascii=False)
    assert r["melhores"][0]["link"].startswith("https://www.instagram.com/p/")
    assert r["melhores_artecon"][0]["engajamento"] == 3.0 and r["melhores_artecon"][0]["rel"] == 1.5 and len(r["melhores_artecon"]) == 3
    temas = {t["tema"]: t for t in r["temas"]}
    assert temas["Outros"]["n"] == 9 and temas["MEI"]["artecon_pct"] == 33.3 and temas["Simples Nacional"]["n"] == 2
    assert temas["Imposto de Renda"] == {"tema": "Imposto de Renda", "n": 1, "pct": 6.3, "rel": 2.0, "artecon_pct": 0.0}
    assert r["temas"][0]["tema"] == "Outros" and r["hashtags"] == []


def test_painel_quem_le_e_os_casos_de_borda(setor):
    sid, _ = painel_p(setor)
    assert setor.execute("select radar_setor_painel_em(%s, 45, now())->'periodo'->>'dias'", (sid,)).fetchone()[0] == "90"
    assert setor.execute("select radar_setor_painel_em(%s, 365, now())->'periodo'->>'agrupado'", (sid,)).fetchone()[0] == "mes"
    for uid in (LEITOR, EDITOR, ADMIN):
        assert chamar(uid, "select radar_setor_painel(%s, 30)", (sid,))["setor"]["nome"] == "Contabilidade"
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR408"):
        chamar(SEM_PERFIL, "select radar_setor_painel(%s, 30)", (sid,))
    with como("anon") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("select radar_setor_painel(%s, 30)", (sid,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR412"):
        chamar(LEITOR, "select radar_setor_painel(999999, 30)")
    vazio = novo_setor("Vazio")
    r = chamar(LEITOR, "select radar_setor_painel(%s, 90)", (vazio,))
    assert r["resumo"]["com_dados"] == 0 and r["contas"] == [] and r["melhores"] == [] and r["resumo"]["formato_mais_usado"] is None
    assert 12 <= len(r["series"]) <= 13 and all(s["setor"] is None for s in r["series"])
    s = chamar(LEITOR, "select radar_setor_situacao()")
    assert set(s) >= {"cfg", "ultima", "pausa_ate", "em_andamento", "proxima", "hashtags_7d"} and "agenda" not in s
    assert chamar(ADMIN, "select radar_setor_situacao()")["agenda"] == {"instalada": False}       # sem o pg_cron
    assert chamar(SEM_PERFIL, "select radar_setor_situacao()") == {}


def test_setup_de_novo_nao_duplica_nem_mexe_na_configuracao(setor):
    sid = novo_setor()
    chamar(ADMIN, "select radar_setor_configurar('{\"coleta_ligada\": false}')")
    antes = setor.execute("""select (select count(*) from radar_setor_setores), (select count(*) from pg_policies where tablename like 'radar\\_setor\\_%'),
                                    (select count(*) from pg_trigger t join pg_class c on c.oid = t.tgrelid where c.relname like 'radar\\_setor\\_%' and not t.tgisinternal)""").fetchone()
    for _ in range(2):
        r = psql(SETUP)
        assert r.returncode == 0, r.stderr
    depois = setor.execute("""select (select count(*) from radar_setor_setores), (select count(*) from pg_policies where tablename like 'radar\\_setor\\_%'),
                                     (select count(*) from pg_trigger t join pg_class c on c.oid = t.tgrelid where c.relname like 'radar\\_setor\\_%' and not t.tgisinternal)""").fetchone()
    assert antes == depois == (1, 4, 2)
    assert setor.execute("select valor from radar_config where chave = 'setor'").fetchone()[0]["coleta_ligada"] is False
    assert chamar(ADMIN, "select radar_setor_painel(%s, 30)", (sid,))["setor"]["id"] == sid      # os privilégios voltam depois do laço geral
