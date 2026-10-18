"""Lembretes por e-mail ANTES do dia (v0.29.0): o banco (radar_lembretes e as funções radar_lembretes_*) e os textos do robô
(robo/radar_lembretes.py).

Quem decide o que lembrar e quando é o banco. Confere: a peça da Pauta de amanhã (e a de hoje que ainda não saiu) que não está aprovada,
a partir da hora (16:00 em ponto) e uma vez só (a peça lembrada na véspera não é lembrada de novo no dia); a peça pronta só depois de N
horas (desde que ficou pronta) e sem duplicar o lembrete da Pauta; o vídeo do reel que o corretor terminou, uma vez por resultado, até a
peça ser aprovada com ele; a notícia com erro no site ou nas redes, ou parada há mais de X horas (a da Pauta não entra); no máximo um
e-mail por tipo por dia; o "enviado" marca só o que foi no e-mail; o lote que o robô não confirmou volta o mesmo ("retomado"); o
desligado; o padrão no que estiver fora dos limites; quem pode chamar cada função; nada de nome no que vai ao e-mail; o "hoje" de
Brasília; os textos exatos dos quatro tipos; e o setup por cima do banco da v0.28.1, sem perder dados.

Nenhum teste depende da data de hoje: as funções recebem a hora (p_agora) e as datas são fixas (16:00 de Brasília de terça-feira,
03/11/2026). Nomes de mentira ("Ana Teste", "Bruno Exemplo").
"""
from __future__ import annotations

import json
import re
from datetime import datetime

import psycopg
import pytest

from conftest import ADMIN, EDITOR, LEITOR, RAIZ, SETUP, como, conectar, psql
from test_radar_banco import (IDENT, aprovar, nova_captura, nova_pessoa, novo_assunto, novo_conteudo, pauta,  # noqa: F401 (pauta: a assinatura)
                              video_pronto)

import radar_lembretes

AGORA = "2026-11-03 19:00+00"          # terça-feira, 16:00 de Brasília
HOJE, AMANHA = "2026-11-03", "2026-11-04"
DEPOIS = "2026-11-10"                   # uma semana depois: fora do lembrete da Pauta
CHAVES_DO_ITEM = {"id", "n", "data", "hora", "formato", "situacao", "quando", "canal", "desde"}
NOMES = ("Ana", "Teste", "Bruno", "Exemplo", "Bastidor", "folha", "Meta", "11.222.333", "Palhoça", "CRC-SC")
FALA = "Fala: o prazo vence no dia 20. Confira com a gente antes do vencimento para não pagar multa."


@pytest.fixture()
def cfg(limpo):
    """Configurações → Lembretes por e-mail com os padrões; no fim, a chave volta ao que era."""
    antes = limpo.execute("select valor from radar_config where chave = 'lembretes'").fetchone()
    limpo.execute("delete from radar_config where chave = 'lembretes'")
    yield limpo
    limpo.execute("delete from radar_config where chave = 'lembretes'")
    if antes:
        limpo.execute("insert into radar_config (chave, valor) values ('lembretes', %s)", (json.dumps(antes[0]),))


def configurar(db, **valor):
    db.execute("""insert into radar_config (chave, valor) values ('lembretes', %s)
                  on conflict (chave) do update set valor = excluded.valor""", (json.dumps(valor),))


def peca(db, data, situacao="planejada", tipo="bastidor", formato="imagem", hora="09:30", **campos):
    """A peça gravada direto, na situação pedida (com a marca das funções: o gatilho não muda a situação sozinho)."""
    pid = db.execute("insert into radar_pauta_pecas (data, hora, tipo, formato) values (%s, %s, %s, %s) returning id",
                     (data, hora, tipo, formato)).fetchone()[0]
    mudar(db, pid, situacao=situacao, **campos)
    return pid


def mudar(db, pid, **campos):
    if not campos:
        return
    db.execute("select set_config('radar.pauta', '1', false)")
    try:
        db.execute("update radar_pauta_pecas set " + ", ".join(f"{k} = %s" for k in campos) + " where id = %s", (*campos.values(), pid))
    finally:
        db.execute("select set_config('radar.pauta', '', false)")


def devidos(db, agora=AGORA):
    return db.execute("select radar_lembretes_devidos(%s)", (agora,)).fetchone()[0]


def lote_em(db, agora=AGORA):
    return db.execute("select radar_lembretes_lote_em(%s)", (agora,)).fetchone()[0]


def grupo(db, tipo, agora=AGORA):
    return next((g for g in lote_em(db, agora) if g["tipo"] == tipo), None)


def enviado(db, lote, aviso, ids, agora=AGORA):
    return db.execute("select radar_lembretes_enviado_em(%s::uuid, %s, %s::bigint[], %s)", (lote, aviso, list(ids), agora)).fetchone()[0]


def mandar(db, tipo, aviso=77, agora=AGORA):
    """O que o robô faz com um tipo: pega o lote e confirma o e-mail com todos os itens. Devolve os itens."""
    g = grupo(db, tipo, agora)
    assert g, f"nada de {tipo} no lote"
    assert enviado(db, g["lote"], aviso, [i["id"] for i in g["itens"]], agora) == len(g["itens"])
    return g["itens"]


def abertas(db):
    """As pendências ainda não avisadas nem resolvidas: {chave: ref}."""
    return dict(db.execute("select chave, ref from radar_lembretes where resolvido_em is null and avisado_em is null order by id").fetchall())


def observar(db, agora=AGORA):
    db.execute("select radar_lembretes_observar(%s)", (agora,))


def db_hora(valor):
    """A data e hora (com fuso) de um texto do banco ou dos testes ("2026-11-03 19:00+00", "2026-11-03T16:00:00-03:00")."""
    texto = valor.replace(" ", "T")
    return datetime.fromisoformat(texto + ":00" if re.search(r"[+-]\d\d$", texto) else texto)


# ---------------------------------------------------------------------------------------------------------------------- Pauta
def test_pauta_na_vespera_a_partir_da_hora_um_email_por_dia(cfg):
    db = cfg
    p1 = peca(db, AMANHA)
    assert devidos(db, "2026-11-03 18:59+00") == []                                   # 15:59 de Brasília: ainda não
    assert devidos(db) == ["pauta"]                                                     # 16:00 em ponto
    [g] = lote_em(db)
    assert (g["tipo"], g["retomado"], g["horas"]) == ("pauta", False, None) and re.fullmatch(r"[0-9a-f-]{36}", g["lote"])
    [item] = g["itens"]
    assert set(item) == CHAVES_DO_ITEM                                                  # só isto vai ao robô
    assert {k: item[k] for k in ("n", "data", "hora", "formato", "situacao", "quando", "canal", "desde")} == {
        "n": p1, "data": AMANHA, "hora": "09:30", "formato": "imagem", "situacao": "planejada", "quando": "amanha", "canal": None,
        "desde": None}
    assert enviado(db, g["lote"], 77, [item["id"]]) == 1
    assert devidos(db, "2026-11-03 19:15+00") == [] and devidos(db, "2026-11-04 02:59+00") == []   # já mandou hoje (até 23:59)
    assert lote_em(db, "2026-11-03 19:15+00") == []
    ph = peca(db, HOJE)                                                                  # pendência nova depois do e-mail do dia
    assert devidos(db, "2026-11-03 19:20+00") == [] and f"peca:{ph}:{HOJE}" in abertas(db)   # um e-mail por tipo por dia: espera
    # no dia seguinte, a mesma peça ("hoje", ainda planejada) não é lembrada de novo
    assert devidos(db, "2026-11-04 19:00+00") == []
    # a peça nova de depois de amanhã entra no dia seguinte (é a de "amanhã" do dia 04)
    p2 = peca(db, "2026-11-05", situacao="em_producao", formato="reel", tipo="reel", hora="18:00")
    assert devidos(db, "2026-11-04 18:00+00") == []                                    # 15:00: observa, ainda não manda
    assert [r["situacao"] for r in abertas(db).values()] == ["em_producao"]
    mudar(db, p2, situacao="pronta")                                                     # ficou pronta: a mesma pendência, com a situação nova
    assert devidos(db, "2026-11-04 19:00+00") == ["pauta"]
    [g2] = lote_em(db, "2026-11-04 19:00+00")
    assert [(i["n"], i["quando"], i["situacao"], i["hora"]) for i in g2["itens"]] == [(p2, "amanha", "pronta", "18:00")]
    assert enviado(db, g2["lote"], 77, [g2["itens"][0]["id"]], "2026-11-04 19:00+00") == 1
    # voltar para a produção não abre outro lembrete (a chave é da peça e do dia); a aprovada sai da lista (fecha)
    mudar(db, p2, situacao="em_producao")
    observar(db, "2026-11-04 19:05+00")
    assert abertas(db) == {} and db.execute("select count(*) from radar_lembretes where chave like %s", (f"peca:{p2}:%",)).fetchone()[0] == 1
    mudar(db, p2, situacao="aprovada", aprovado_modo="agendar")
    observar(db, "2026-11-04 19:10+00")
    assert db.execute("select resolvido_em from radar_lembretes where chave = %s", (f"peca:{p2}:2026-11-05",)).fetchone()[0] == \
        db_hora("2026-11-04 19:10+00")


def test_pauta_aprovada_cancelada_sem_post_e_manual_sem_link(cfg):
    db = cfg
    p = peca(db, AMANHA, situacao="aprovada", aprovado_modo="agendar")                # aprovada para a agenda: sai sozinha
    observar(db)
    assert abertas(db) == {}
    mudar(db, p, situacao="cancelada")
    observar(db)
    assert abertas(db) == {}
    mudar(db, p, situacao="planejada", tipo="sem_post", formato="nenhum")              # dia sem post no feed
    observar(db)
    assert abertas(db) == {} and devidos(db) == []
    mudar(db, p, situacao="aprovada", aprovado_modo="manual", tipo="bastidor", formato="carrossel")   # amanhã, à mão: ainda não
    observar(db)
    assert abertas(db) == {}
    h = peca(db, HOJE, situacao="aprovada", aprovado_modo="manual", formato="carrossel")              # hoje, à mão, sem o registro
    observar(db)
    assert abertas(db) == {f"peca:{h}:{HOJE}:manual": {"n": h, "data": HOJE, "hora": "09:30", "formato": "carrossel",
                                                        "situacao": "aprovada_manual"}}
    assert [(i["quando"], i["situacao"]) for i in grupo(db, "pauta")["itens"]] == [("hoje", "aprovada_manual")]
    mudar(db, h, link_instagram="https://www.instagram.com/p/teste/")                  # registrou a publicação: fecha
    observar(db)
    assert abertas(db) == {} and devidos(db) == []


def test_pauta_a_mao_so_uma_hora_depois_da_hora_marcada(cfg):
    """v0.29.0 (revisão): a peça aprovada para publicar à mão e ainda sem o registro só é lembrada UMA HORA DEPOIS da hora marcada (antes
    disso a equipe ainda vai postar; lembrar antes gastava o único lembrete dela). A das 19:00, com o e-mail da Pauta das 16:00 já
    mandado, espera o dia seguinte e chega como "ontem"; sem e-mail da Pauta no dia, sai no mesmo dia."""
    db = cfg
    h = peca(db, HOJE, situacao="aprovada", aprovado_modo="manual", formato="carrossel", hora="19:00")
    a = peca(db, AMANHA)
    [g] = lote_em(db)                                                                    # 16:00: só a de amanhã (a das 19:00 ainda vai sair)
    assert [(i["n"], i["quando"]) for i in g["itens"]] == [(a, "amanha")]
    assert enviado(db, g["lote"], 1, [i["id"] for i in g["itens"]]) == 1
    assert devidos(db, "2026-11-03 22:59+00") == [] and f"peca:{h}:{HOJE}:manual" not in abertas(db)   # 19:59: ainda não
    observar(db, "2026-11-03 23:00+00")                                                 # 20:00: uma hora depois, guardada; o e-mail do
    assert f"peca:{h}:{HOJE}:manual" in abertas(db) and devidos(db, "2026-11-03 23:00+00") == []      # dia já saiu: espera amanhã
    assert devidos(db, "2026-11-04 18:59+00") == []                                     # 15:59 do dia seguinte: antes da hora da Pauta
    [g2] = lote_em(db, "2026-11-04 19:00+00")
    assert [(i["n"], i["quando"], i["situacao"], i["hora"]) for i in g2["itens"]] == [(h, "ontem", "aprovada_manual", "19:00")]
    assert radar_lembretes.corpo("pauta", g2).startswith(
        "**A peça da Pauta de ontem (terça-feira, 03/11) ainda não saiu.**\n\n- Ontem, 03/11 às 19:00 — Carrossel (peça nº "
        f"{h}): aprovada para publicar à mão e ainda sem o link registrado.")
    assert enviado(db, g2["lote"], 2, [i["id"] for i in g2["itens"]], "2026-11-04 19:00+00") == 1
    assert devidos(db, "2026-11-05 19:00+00") == [] and abertas(db) == {}               # uma vez só; a de anteontem já não entra
    # sem e-mail da Pauta no dia: sai no mesmo dia, uma hora depois da hora marcada (18:30 → 19:30 em ponto)
    h2 = peca(db, "2026-11-05", situacao="aprovada", aprovado_modo="manual", formato="carrossel", hora="18:30")
    assert devidos(db, "2026-11-05 22:29+00") == [] and devidos(db, "2026-11-05 22:30+00") == ["pauta"]
    assert [(i["n"], i["quando"]) for i in grupo(db, "pauta", "2026-11-05 22:30+00")["itens"]] == [(h2, "hoje")]


# ----------------------------------------------------------------------------------------------------------------- aprovação
def test_aprovacao_so_depois_de_n_horas_e_nao_repete(cfg):
    db = cfg
    p = peca(db, DEPOIS, situacao="pronta")
    observar(db)
    [(chave, ref)] = abertas(db).items()
    assert chave == f"aprovacao:{p}" and ref == {"n": p, "data": DEPOIS, "hora": "09:30", "formato": "imagem"}
    db.execute("update radar_lembretes set aberto_em = %s::timestamptz - interval '23 hours 59 minutes'", (AGORA,))
    assert devidos(db) == []                                                            # pronta há 23h59: ainda não
    db.execute("update radar_lembretes set aberto_em = %s::timestamptz - interval '24 hours'", (AGORA,))
    assert devidos(db) == ["aprovacao"]                                                 # 24h em ponto
    db.execute("update radar_lembretes set aberto_em = '2026-11-01 00:00+00'")         # pronta há dias: só o horário conta
    assert devidos(db, "2026-11-03 23:01+00") == [] and devidos(db, "2026-11-03 10:59+00") == []   # 20:01 e 07:59: fora do horário
    assert devidos(db, "2026-11-03 11:00+00") == ["aprovacao"] and devidos(db, "2026-11-03 23:00+00") == ["aprovacao"]   # 08:00 e 20:00
    db.execute("update radar_lembretes set aberto_em = %s::timestamptz - interval '24 hours'", (AGORA,))
    [item] = mandar(db, "aprovacao")
    assert db_hora(item["desde"]) == db_hora("2026-11-02 19:00+00") and item["quando"] is None   # pronta desde (aberto_em)
    mudar(db, p, observacao="Rever a cor da arte")                                      # mexer no plano não é novidade: não repete
    assert devidos(db, "2026-11-04 19:00+00") == [] and abertas(db) == {}
    mudar(db, p, situacao="em_producao")                                                 # voltou para a produção: fecha
    observar(db, "2026-11-04 19:05+00")
    mudar(db, p, situacao="pronta")                                                      # pronta de novo: episódio novo
    observar(db, "2026-11-04 19:10+00")
    assert list(abertas(db)) == [f"aprovacao:{p}"]
    # v0.29.0 (revisão): o aberto_em do episódio novo vem do atualizado_em da peça, que o gatilho grava com o relógio de verdade; fixa a
    # hora em que ela voltou a ficar pronta (16:10 de 04/11) para a espera de 24 horas não depender da data em que o teste roda
    db.execute("update radar_lembretes set aberto_em = '2026-11-04 19:10+00' where resolvido_em is null and avisado_em is null")
    assert devidos(db, "2026-11-05 19:09+00") == []                                    # 23h59 depois de reaberta: ainda não
    assert devidos(db, "2026-11-05 19:10+00") == ["aprovacao"]                         # 24 horas em ponto, no dia seguinte


def test_aprovacao_de_hoje_e_amanha_fica_com_a_pauta(cfg):
    db = cfg
    p = peca(db, AMANHA, situacao="pronta")
    observar(db)
    assert set(abertas(db)) == {f"peca:{p}:{AMANHA}", f"aprovacao:{p}"}                # as duas ficam guardadas...
    db.execute("update radar_lembretes set aberto_em = %s::timestamptz - interval '2 days' where tipo = 'aprovacao'", (AGORA,))
    assert devidos(db) == ["pauta"] and devidos(db, "2026-11-03 13:00+00") == []      # ...e um lembrete só para a peça: o da Pauta
    configurar(db, pauta=False)                                                          # sem o da Pauta, a aprovação cuida dela
    assert devidos(db) == ["aprovacao"]
    # v0.29.0 (revisão): ligar e desligar a Pauta não fecha nem reabre a pendência da aprovação: lembrada, não volta
    mandar(db, "aprovacao")
    configurar(db, pauta=True)
    observar(db, "2026-11-03 19:05+00")
    configurar(db, pauta=False)
    observar(db, "2026-11-03 19:10+00")
    assert db.execute("select count(*), count(resolvido_em), count(avisado_em) from radar_lembretes where tipo = 'aprovacao'").fetchone() == (1, 0, 1)
    assert devidos(db, "2026-11-04 11:00+00") == []                                    # no dia seguinte, nada de novo


# --------------------------------------------------------------------------------------------------------------------- vídeo
def test_video_pronto_regravar_erro_uma_vez_por_rodada_e_sai_quando_amarrado(cfg, pauta):
    db = cfg
    p = peca(db, DEPOIS, situacao="em_producao", tipo="reel", formato="reel", roteiro=FALA)
    v = video_pronto(db, p, 1, fala=FALA)                                               # o corretor terminou: pronto
    observar(db)
    assert abertas(db) == {f"video:{v}:0:pronto": {"n": p, "data": DEPOIS, "formato": "reel", "situacao": "pronto"}}
    assert devidos(db) == ["video"]
    mandar(db, "video")
    assert devidos(db, "2026-11-04 19:00+00") == []                                    # o mesmo resultado: uma vez só
    db.execute("update radar_videos set situacao = 'na_fila' where id = %s", (v,))      # ajuste: de volta à fila (fecha)
    observar(db, "2026-11-04 19:01+00")
    db.execute("update radar_videos set situacao = 'regravar', rodada = 1 where id = %s", (v,))   # o resultado novo do corretor
    assert devidos(db, "2026-11-04 19:02+00") == ["video"]
    assert [i["situacao"] for i in mandar(db, "video", agora="2026-11-04 19:02+00")] == ["regravar"]
    db.execute("update radar_videos set situacao = 'erro', rodada = 2 where id = %s", (v,))
    assert devidos(db, "2026-11-04 19:30+00") == []                                    # um e-mail de vídeo por dia
    assert devidos(db, "2026-11-05 11:00+00") == ["video"]                             # no dia seguinte, às 08:00
    db.execute("update radar_videos set situacao = 'pronto', rodada = 3 where id = %s", (v,))
    mudar(db, p, situacao="aprovada", aprovado_modo="manual", video_id=v, video_sha256="a" * 64)   # aprovada com ele: fecha tudo
    assert devidos(db, "2026-11-05 11:05+00") == [] and abertas(db) == {}
    mudar(db, p, situacao="cancelada", video_id=None, video_sha256=None)                # peça cancelada também não lembra
    assert devidos(db, "2026-11-05 11:10+00") == [] and abertas(db) == {}


# ------------------------------------------------------------------------------------------------------------------- notícia
def envio_site(db, conteudo, situacao, autorizado_em, atualizado_em=None):
    """A autorização do site gravada direto (o erro tem nome, de propósito)."""
    return db.execute("""insert into radar_site_envios (conteudo_id, categoria, conteudo_lido_em, situacao, autorizado_em, atualizado_em, erro)
                         values (%s, 'Federal', now(), %s, %s, %s, case when %s = 'erro' then 'Erro do painel: Ana Teste' end)
                         returning id""", (conteudo, situacao, autorizado_em, atualizado_em or autorizado_em, situacao)).fetchone()[0]


def envio_redes(db, canal, situacao, autorizado_em, atualizado_em=None, conteudo=None, peca_id=None):
    """O envio ao Instagram ou ao Facebook gravado direto (o da Pauta tem a hora marcada); a legenda e o erro têm nome, de propósito."""
    return db.execute("""insert into radar_redes_envios (conteudo_id, peca_id, canal, legenda, conteudo_lido_em, situacao, autorizado_em,
                                                          atualizado_em, agendado_para, erro)
                         values (%s, %s, %s, 'Bruno Exemplo cuida da folha de pagamento.', now(), %s, %s, %s, %s,
                                 case when %s = 'erro' then 'Meta recusou: Bruno Exemplo' end)
                         returning id""", (conteudo, peca_id, canal, situacao, autorizado_em, atualizado_em or autorizado_em,
                                           autorizado_em if peca_id else None, situacao)).fetchone()[0]


def conteudo_aprovado(db):
    """Um conteúdo aprovado, com o trecho conferido na fonte oficial (cada um com o seu endereço de captura)."""
    cap = nova_captura(db, url=f"https://exemplo.gov.br/in-2290-lembrete-{next(_SEQ)}")
    a = novo_assunto(db)
    db.execute("insert into radar_evidencias (assunto_id, captura_id, trecho_literal) values (%s, %s, %s)",
               (a, cap, "à alíquota de 0,9% (nove décimos por cento)"))
    c = novo_conteudo(db, a)
    aprovar(c)
    return c


_SEQ = iter(range(1, 10_000))


def test_noticia_site_erro_parada_redes_e_a_pauta_nao_entra(cfg):
    db = cfg
    c1, c2, c3 = conteudo_aprovado(db), conteudo_aprovado(db), conteudo_aprovado(db)
    erro = envio_site(db, c1, "erro", "2026-11-03 13:12+00", "2026-11-03 13:20+00")       # autorizada às 10:12 de Brasília
    envio_site(db, c2, "erro", "2026-10-26 12:00+00", "2026-10-26 12:30+00")               # erro de 8 dias: fica de fora
    ig = envio_redes(db, "instagram", "erro", "2026-11-03 12:40+00", "2026-11-03 12:41+00", conteudo=c3)
    fb = envio_redes(db, "facebook", "autorizado", "2026-11-03 12:40+00", "2026-11-03 16:01+00", conteudo=c3)   # parada há 2h59
    pp = peca(db, DEPOIS, situacao="aprovada", aprovado_modo="agendar")
    envio_redes(db, "instagram", "erro", "2026-11-03 12:00+00", "2026-11-03 12:30+00", peca_id=pp)                # da Pauta: não entra
    observar(db)
    # v0.29.0 (revisão): a parada fica guardada desde quando ficou autorizada (13:01 de Brasília) e só pode ser lembrada com
    # "parada_horas" (radar_lembretes_madura): mudar o número depois não fecha nem reabre a pendência
    assert set(abertas(db)) == {f"site:{erro}:erro", f"redes:{ig}:erro", f"redes:{fb}:parada"}
    assert db.execute("select aberto_em from radar_lembretes where chave = %s", (f"redes:{fb}:parada",)).fetchone()[0] == \
        db_hora("2026-11-03 16:01+00")
    assert devidos(db) == ["noticia"]
    # autorizada de novo: o erro antigo fecha; a autorização nova fica guardada desde as 13:01; parada há 2h59 ainda não, há 3h00 sim
    novo = envio_site(db, c1, "autorizado", "2026-11-03 16:01+00")
    observar(db)
    assert set(abertas(db)) == {f"redes:{ig}:erro", f"redes:{fb}:parada", f"site:{novo}:parada"}
    g = grupo(db, "noticia")                                                             # 16:00: as duas paradas há 2h59
    assert g["horas"] == 3 and [(i["n"], i["situacao"]) for i in g["itens"]] == [(ig, "erro")]
    g = grupo(db, "noticia", "2026-11-03 19:01+00")                                      # 16:01: há 3h00 (o mesmo lote, retomado)
    assert g["retomado"] is True
    assert [(i["n"], i["canal"], i["situacao"], db_hora(i["desde"])) for i in g["itens"]] == [          # a mais antiga antes
        (ig, "instagram", "erro", db_hora("2026-11-03 12:40+00")), (fb, "facebook", "parada", db_hora("2026-11-03 12:40+00")),
        (novo, "site", "parada", db_hora("2026-11-03 16:01+00"))]
    # saiu, foi cancelada ou o conteúdo deixou de ir ao site: fecha
    db.execute("update radar_site_envios set situacao = 'publicado' where id = %s", (novo,))
    db.execute("update radar_redes_envios set situacao = 'cancelado' where id in (%s, %s)", (ig, fb))
    observar(db)
    assert abertas(db) == {}
    erro2 = envio_site(db, c3, "erro", "2026-11-03 18:00+00")
    observar(db)
    assert set(abertas(db)) == {f"site:{erro2}:erro"}
    db.execute("update radar_conteudos set fora_do_site = true where id = %s", (c3,))
    observar(db)
    assert abertas(db) == {}


def test_mudar_as_configuracoes_nao_lembra_de_novo_a_mesma_pendencia(cfg):
    """v0.29.0 (revisão): "parada_horas" vale na hora de lembrar (radar_lembretes_madura), não na de observar. Subir e baixar o número
    depois do lembrete não fecha a pendência, e ela não volta como episódio novo (lembrada de novo); a autorização nova espera as horas
    novas."""
    db = cfg
    c = conteudo_aprovado(db)
    e = envio_site(db, c, "autorizado", "2026-11-03 14:00+00")                          # 11:00 de Brasília
    assert devidos(db, "2026-11-03 16:59+00") == []                                     # parada há 2h59
    [g] = lote_em(db, "2026-11-03 17:00+00")                                            # há 3 horas: lembrada
    assert [(i["n"], i["situacao"]) for i in g["itens"]] == [(e, "parada")]
    assert enviado(db, g["lote"], 1, [i["id"] for i in g["itens"]], "2026-11-03 17:00+00") == 1
    configurar(db, parada_horas=10)
    observar(db, "2026-11-03 18:00+00")
    configurar(db, parada_horas=1)
    observar(db, "2026-11-03 18:05+00")
    assert devidos(db, "2026-11-04 11:00+00") == [] and devidos(db, "2026-11-04 14:00+00") == []
    assert db.execute("select count(*), count(resolvido_em), count(avisado_em) from radar_lembretes").fetchone() == (1, 0, 1)
    configurar(db, parada_horas=10)
    e2 = envio_site(db, conteudo_aprovado(db), "autorizado", "2026-11-04 12:00+00")    # 09:00 de 04/11
    assert devidos(db, "2026-11-04 21:59+00") == [] and devidos(db, "2026-11-04 22:00+00") == ["noticia"]   # 10 horas depois
    assert [i["n"] for i in grupo(db, "noticia", "2026-11-04 22:00+00")["itens"]] == [e2]


# ----------------------------------------------------------------------------------------------------- lote, enviado e retomado
def test_enviado_marca_so_os_ids_do_lote(cfg):
    db = cfg
    c = conteudo_aprovado(db)
    e1 = envio_redes(db, "instagram", "erro", "2026-11-03 12:00+00", conteudo=c)
    e2 = envio_redes(db, "facebook", "erro", "2026-11-03 12:00+00", conteudo=c)
    g = grupo(db, "noticia")
    ids = {i["n"]: i["id"] for i in g["itens"]}
    assert set(ids) == {e1, e2}
    c2 = conteudo_aprovado(db)
    e3 = envio_site(db, c2, "erro", "2026-11-03 18:30+00")                                 # chega depois do lote
    observar(db)
    assert enviado(db, g["lote"], 80, [ids[e1]]) == 1                                      # só o que foi no e-mail
    linhas = {ch: tuple(r) for ch, *r in db.execute("select chave, avisado_em is not null, aviso, lote is null from radar_lembretes").fetchall()}
    assert linhas == {f"redes:{e1}:erro": (True, 80, True), f"redes:{e2}:erro": (False, None, True), f"site:{e3}:erro": (False, None, True)}
    assert devidos(db, "2026-11-03 19:30+00") == []                                        # o resto fica para amanhã
    assert sorted((i["canal"], i["n"]) for i in grupo(db, "noticia", "2026-11-04 11:00+00")["itens"]) == [("facebook", e2), ("site", e3)]
    assert enviado(db, g["lote"], 80, [ids[e2]]) == 0                                      # o lote velho não marca mais nada
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR340"):
        enviado(db, g["lote"], 0, [ids[e2]])


def test_lote_parado_volta_com_o_mesmo_lote_retomado(cfg):
    db = cfg
    c = conteudo_aprovado(db)
    e1 = envio_redes(db, "instagram", "erro", "2026-11-03 12:00+00", conteudo=c)
    g1 = grupo(db, "noticia")
    assert g1["retomado"] is False and [i["n"] for i in g1["itens"]] == [e1]
    e2 = envio_redes(db, "facebook", "erro", "2026-11-03 12:00+00", conteudo=c)            # o robô caiu; chegou outra
    g2 = grupo(db, "noticia", "2026-11-03 19:20+00")
    assert g2["retomado"] is True and g2["lote"] == g1["lote"] and [i["n"] for i in g2["itens"]] == [e1, e2]
    assert db.execute("select count(distinct lote), count(*) from radar_lembretes").fetchone() == (1, 2)
    mandar(db, "noticia", agora="2026-11-03 19:20+00")
    assert db.execute("select count(*) from radar_lembretes where lote is not null or avisado_em is null").fetchone()[0] == 0


def test_um_email_por_dia_conta_pela_reserva_e_nao_pela_confirmacao(cfg):
    """v0.29.0 (revisão): o dia do e-mail é o da reserva do lote (o robô reserva e comenta em seguida), não o da confirmação. Reservado
    às 23:55 e confirmado às 00:01: o e-mail é do dia anterior, e o lembrete da véspera do dia seguinte sai. O lote retomado no dia
    seguinte, com o comentário já feito (o robô acha a marca e só confirma), conta no dia em que saiu: o dia novo continua livre."""
    db = cfg
    p1 = peca(db, AMANHA)
    [g] = lote_em(db, "2026-11-04 02:55+00")                                            # 23:55 de 03/11: o robô reserva e comenta...
    assert enviado(db, g["lote"], 1, [i["id"] for i in g["itens"]], "2026-11-04 03:01+00") == 1   # ...e confirma às 00:01 de 04/11
    assert db.execute("select avisado_em from radar_lembretes where chave = %s", (f"peca:{p1}:{AMANHA}",)).fetchone()[0] == \
        db_hora("2026-11-04 02:55+00")
    p2 = peca(db, "2026-11-05")                                                          # a peça de amanhã do dia 04/11
    assert devidos(db, "2026-11-04 19:00+00") == ["pauta"]                              # 16:00 de 04/11: o lembrete da véspera sai
    [g2] = lote_em(db, "2026-11-04 19:00+00")
    assert [(i["n"], i["quando"]) for i in g2["itens"]] == [(p2, "amanha")]
    # o comentário saiu em 04/11 e a confirmação falhou; em 05/11 o robô retoma o lote, acha a marca e só confirma o que foi nele
    p3 = peca(db, "2026-11-06")
    g3 = grupo(db, "pauta", "2026-11-05 19:00+00")
    assert g3["retomado"] is True and g3["lote"] == g2["lote"]
    assert enviado(db, g3["lote"], 1, [i["id"] for i in g2["itens"]], "2026-11-05 19:00+00") == 1
    assert devidos(db, "2026-11-05 19:30+00") == ["pauta"]                              # conta em 04/11: o dia 05 continua livre
    [g4] = lote_em(db, "2026-11-05 19:30+00")
    assert [(i["n"], i["quando"]) for i in g4["itens"]] == [(p3, "amanha")]


# --------------------------------------------------------------------------------------------------------- Configurações
def test_desligado_e_tipo_desligado(cfg):
    db = cfg
    peca(db, AMANHA)
    p = peca(db, DEPOIS, situacao="pronta")
    configurar(db, ligado=False)
    assert devidos(db) == [] and lote_em(db) == []
    assert db.execute("select count(*) from radar_lembretes").fetchone()[0] == 0          # desligado: nada é observado
    configurar(db, pauta=False)
    observar(db)
    db.execute("update radar_lembretes set aberto_em = '2026-11-01 00:00+00' where chave = %s", (f"aprovacao:{p}",))
    assert devidos(db) == ["aprovacao"]                                                    # sem a Pauta, só ela
    configurar(db, pauta=True, aprovacao=False)
    assert devidos(db) == ["pauta"]
    configurar(db, ligado=True, pauta=True, aprovacao=True, video=False, noticia=False)
    assert devidos(db) == ["pauta", "aprovacao"]


def test_cfg_fora_dos_limites_usa_o_padrao(cfg):
    db = cfg
    ler = lambda: db.execute("select radar_lembretes_cfg()").fetchone()[0]
    padrao = {"ligado": True, "hora": "16:00", "de": "08:00", "ate": "20:00", "aprovacao_horas": 24, "parada_horas": 3,
              "pauta": True, "aprovacao": True, "video": True, "noticia": True, "vencimento": True, "copia": True}   # v0.32.0: + 2 tipos
    assert ler() == padrao                                                                 # sem a chave
    configurar(db, ligado="sim", hora="25:00", de="21:00", ate="07:00", aprovacao_horas=0, parada_horas=2.5, pauta=None, video=1)
    assert ler() == padrao
    configurar(db, hora="9:30", de="8:00", ate=20, aprovacao_horas=169, parada_horas=49)
    assert ler() == padrao
    configurar(db, de="21:00")                                                             # depois do "ate" padrão: os dois padrões
    assert ler() == padrao
    configurar(db, ligado=False, hora="07:05", de="06:00", ate="22:30", aprovacao_horas=168, parada_horas=48, noticia=False)
    assert ler() == {**padrao, "ligado": False, "hora": "07:05", "de": "06:00", "ate": "22:30", "aprovacao_horas": 168,
                     "parada_horas": 48, "noticia": False}
    configurar(db, aprovacao_horas=1, parada_horas=1.0)
    assert ler() == {**padrao, "aprovacao_horas": 1, "parada_horas": 1}
    # v0.29.0 (revisão): a agenda confere de 15 em 15 minutos. "hora" depois das 23:45, ou menos de 15 minutos entre "de" e "ate":
    # nenhuma rodada alcançaria o lembrete (ele nunca sairia); vale o padrão
    configurar(db, hora="23:50", de="08:05", ate="08:10")
    assert ler() == padrao
    configurar(db, hora="23:46", de="08:00", ate="08:14")
    assert ler() == padrao
    configurar(db, hora="23:45", de="08:00", ate="08:15")                                 # o limite: alcançados
    assert ler() == {**padrao, "hora": "23:45", "de": "08:00", "ate": "08:15"}
    peca(db, AMANHA)
    assert devidos(db, "2026-11-04 02:44+00") == [] and devidos(db, "2026-11-04 02:45+00") == ["pauta"]   # 23:45, a última rodada
    db.execute("update radar_config set valor = '[1, 2]' where chave = 'lembretes'")       # nem objeto é
    assert ler() == padrao


# ---------------------------------------------------------------------------------------------------------------- permissões
def test_permissoes_dos_lembretes(cfg):
    db = cfg
    peca(db, AMANHA)
    observar(db)
    for sql in ["select radar_lembretes_observar(now())", "select radar_lembretes_devidos(now())", "select radar_lembretes_acionar()",
                "select radar_lembretes_lote_em(now())", "select radar_lembretes_enviado_em(gen_random_uuid(), 1, '{}', now())",
                "select radar_lembretes_cfg()", "select radar_lembretes_situacao()", "select * from radar_lembretes",
                "select radar_lembretes_madura('pauta', 'peca:1:2026-11-04', '{}', now(), '{}', now())"]:
        with como("service_role") as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)
    with como("authenticated", ADMIN) as c:
        s = c.execute("select radar_lembretes_situacao()").fetchone()[0]
        assert set(s) == {"agenda", "tipos", "esperando"} and s["agenda"] == {"instalada": False} and s["esperando"] == 1
        assert s["tipos"] == {"pauta": None, "aprovacao": None, "video": None, "noticia": None, "vencimento": None, "copia": None}
        with pytest.raises(psycopg.errors.InsufficientPrivilege):                          # v0.29.0 (revisão): nem o administrador
            c.execute("select count(*) from radar_lembretes")                               # lê a tabela (a tela usa a situação)
        for sql in ["select radar_lembretes_lote()", "select radar_lembretes_ha_envio()", "select radar_lembretes_acionar()",
                    "select radar_lembretes_enviado(gen_random_uuid(), 1, '{}')"]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("update radar_lembretes set avisado_em = now()")
    for uid in (EDITOR, LEITOR):
        with como("authenticated", uid) as c:
            assert c.execute("select radar_lembretes_situacao()").fetchone()[0] == {}
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute("select count(*) from radar_lembretes")
    with como("anon") as c:
        for sql in ["select radar_lembretes_situacao()", "select * from radar_lembretes", "select radar_lembretes_lote()"]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)
    with como("service_role") as c:                                                        # o robô: só as três do lote
        assert c.execute("select radar_lembretes_ha_envio()").fetchone()[0] in (True, False)
        assert isinstance(c.execute("select radar_lembretes_lote()").fetchone()[0], list)
        assert c.execute("select radar_lembretes_enviado(gen_random_uuid(), 1, '{}')").fetchone()[0] == 0
    # v0.29.0 (revisão): "security definer" só nas quatro que outros papéis chamam; as internas rodam com os direitos de quem chama
    definer = {n for (n,) in db.execute("""select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                                           where n.nspname = 'public' and p.proname like 'radar\\_lembretes\\_%' and p.prosecdef""")}
    assert definer == {"radar_lembretes_ha_envio", "radar_lembretes_lote", "radar_lembretes_enviado", "radar_lembretes_situacao"}


# ------------------------------------------------------------------------------------------------------------ nada de nome
def test_nada_de_nome_no_ref_nem_no_lote(cfg, pauta):
    db = cfg
    ana = nova_pessoa(db, nome="Ana Teste", na_peca="Ana")
    p = peca(db, AMANHA, assunto="Bastidor com Ana Teste", quem_aparece="Ana Teste", observacao="Ana Teste, da folha",
             chamada="Ana cuida da folha", legenda_instagram="Ana Teste cuida da folha. " + IDENT, pessoas=[ana])
    r = peca(db, DEPOIS, situacao="em_producao", tipo="reel", formato="reel", roteiro=FALA, assunto="Reel com Bruno Exemplo",
             quem_aparece="Bruno Exemplo")
    video_pronto(db, r, ana, fala=FALA, relatorio=dict(texto_final="Ana Teste fala da folha"))
    c = conteudo_aprovado(db)
    envio_site(db, c, "erro", "2026-11-03 18:00+00")
    envio_redes(db, "instagram", "erro", "2026-11-03 18:00+00", conteudo=c)
    lote = lote_em(db)
    assert sorted(g["tipo"] for g in lote) == ["noticia", "pauta", "video"]
    refs = db.execute("select ref from radar_lembretes").fetchall()
    for texto in [json.dumps(lote, ensure_ascii=False), json.dumps([x for (x,) in refs], ensure_ascii=False)] + \
                 [radar_lembretes.corpo(g["tipo"], g) for g in lote]:
        for nome in NOMES:
            assert nome not in texto, (nome, texto)
    assert all(set(i) == CHAVES_DO_ITEM for g in lote for i in g["itens"]) and p in [i["n"] for g in lote for i in g["itens"]]


# -------------------------------------------------------------------------------------------------- "hoje" é o de Brasília
def test_hoje_de_brasilia_e_sem_current_date(cfg):
    db = cfg
    p = peca(db, AMANHA)
    with conectar() as c:
        c.execute("set timezone = 'Pacific/Kiritimati'")                                   # o servidor noutro fuso (UTC+14)
        agora = "2026-11-04 02:30+00"                                                      # 23:30 de 03/11 em Brasília; 04/11 no UTC
        assert c.execute("select radar_lembretes_devidos(%s)", (agora,)).fetchone()[0] == ["pauta"]
        [g] = c.execute("select radar_lembretes_lote_em(%s)", (agora,)).fetchone()[0]
        assert [(i["n"], i["quando"]) for i in g["itens"]] == [(p, "amanha")]             # amanhã de Brasília, não "hoje"
        assert c.execute("select radar_lembretes_enviado_em(%s::uuid, 5, %s::bigint[], %s)",
                         (g["lote"], [g["itens"][0]["id"]], agora)).fetchone()[0] == 1
        assert c.execute("select radar_lembretes_devidos('2026-11-04 02:45+00')").fetchone()[0] == []   # ainda 03/11 em Brasília
    funcoes = db.execute("""select p.proname, p.prosrc from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                            where n.nspname = 'public' and p.proname like 'radar\\_lembretes\\_%'""").fetchall()
    assert len(funcoes) == 11
    assert [n for n, src in funcoes if "current_date" in src.lower() or "localtime" in src.lower()] == []


# ------------------------------------------------------------------------------------------------------- os textos do robô
LOTE = "0b1c2d3e-0000-4000-8000-000000000029"
RODAPE = ("Cada pendência é lembrada uma vez só. Horário e liga/desliga: Radar → Configurações → Lembretes por e-mail (só o administrador). "
          "Nada é publicado por este lembrete.")


def test_textos_exatos_dos_quatro_tipos():
    corpo = radar_lembretes.corpo
    pauta2 = {"lote": LOTE, "itens": [
        {"id": 5, "n": 412, "data": "2026-10-28", "hora": "09:30", "formato": "reel", "situacao": "em_producao", "quando": "amanha"},
        {"id": 6, "n": 410, "data": "2026-10-27", "hora": "09:30", "formato": "carrossel", "situacao": "aprovada_manual", "quando": "hoje"}]}
    assert corpo("pauta", pauta2) == (
        "**A Pauta tem 2 peças pendentes: a de amanhã e a de hoje.**\n\n"
        "- Amanhã, 28/10 às 09:30 — Reel (peça nº 412): em produção. Falta terminar, clicar em “Salvar e marcar como pronta” e o "
        "administrador aprovar.\n"
        "- Hoje, 27/10 às 09:30 — Carrossel (peça nº 410): aprovada para publicar à mão e ainda sem o link registrado. Depois de postar "
        "no Instagram e no Facebook, use “Registrar a publicação” na peça.\n\n"
        "O que fazer: abra o Radar → **Pauta**, vá à semana da peça e clique em **Abrir**. A peça só sai depois da aprovação do "
        "administrador.\n\n" + RODAPE + f"\n\n<!-- radar-lembrete: lote {LOTE} itens 5 6 -->")
    um = lambda **i: {"lote": LOTE, "itens": [{"id": 1, "n": 9, "hora": "09:30", "formato": "imagem", **i}]}
    assert corpo("pauta", um(data="2026-10-28", situacao="planejada", quando="amanha")).startswith(
        "**A peça da Pauta de amanhã (quarta-feira, 28/10) ainda não está aprovada.**\n\n- Amanhã, 28/10 às 09:30 — Imagem 4:5 (peça nº 9): "
        "planejada, ainda não começou. Falta preparar, clicar em “Salvar e marcar como pronta” e o administrador aprovar.\n\n")
    assert corpo("pauta", um(data="2026-10-26", situacao="aprovada_manual", quando="ontem")).startswith(      # v0.29.0 (revisão)
        "**A peça da Pauta de ontem (segunda-feira, 26/10) ainda não saiu.**\n\n- Ontem, 26/10 às 09:30 — Imagem 4:5 (peça nº 9): "
        "aprovada para publicar à mão e ainda sem o link registrado.")
    tres = {"lote": LOTE, "itens": [{**pauta2["itens"][0]}, {**pauta2["itens"][1], "situacao": "pronta"},
                                    {"id": 7, "n": 409, "data": "2026-10-26", "hora": "19:00", "formato": "reel", "situacao": "aprovada_manual",
                                     "quando": "ontem"}]}
    assert corpo("pauta", tres).startswith("**A Pauta tem 3 peças pendentes: a de amanhã, a de hoje e a de ontem.**\n\n")
    assert corpo("pauta", {**tres, "itens": [tres["itens"][0], tres["itens"][2]]}).startswith(
        "**A Pauta tem 2 peças pendentes: a de amanhã e a de ontem.**\n\n- Amanhã, 28/10 às 09:30 — Reel (peça nº 412)")
    assert corpo("pauta", um(data="2026-10-27", situacao="pronta", quando="hoje")).startswith(
        "**A peça da Pauta de hoje (terça-feira, 27/10) ainda não saiu.**\n\n- Hoje, 27/10 às 09:30 — Imagem 4:5 (peça nº 9): pronta. "
        "Falta o administrador conferir e aprovar.\n\n")
    aprov = {"lote": LOTE, "horas": 24, "itens": [{"id": 7, "n": 415, "data": "2026-11-05", "formato": "imagem",
                                                   "desde": "2026-11-03T13:00:00+00:00"}]}
    assert corpo("aprovacao", aprov) == (
        "**1 peça da Pauta está pronta esperando a aprovação do administrador há mais de 24 horas.**\n\n"
        "- Quinta-feira, 05/11 — Imagem 4:5 (peça nº 415): pronta desde 03/11 às 10:00.\n\n"
        "O que fazer: o administrador abre o Radar → **Pauta**, abre a peça, confere e clica em **Aprovar**. Se precisar mudar algo, quem "
        "edita a peça a devolve para a produção.\n\n" + RODAPE + f"\n\n<!-- radar-lembrete: lote {LOTE} itens 7 -->")
    aprov3 = {**aprov, "horas": 1, "itens": aprov["itens"] * 2 + [{"id": 8, "n": 416, "data": "2026-11-06", "formato": "carrossel_fotos",
                                                                   "desde": "2026-11-03T02:30:00Z"}]}
    texto = corpo("aprovacao", aprov3)
    assert texto.startswith("**3 peças da Pauta estão prontas esperando a aprovação do administrador há mais de 1 hora.**")
    assert "- Sexta-feira, 06/11 — Carrossel de fotos (peça nº 416): pronta desde 02/11 às 23:30." in texto   # de Brasília
    video = {"lote": LOTE, "itens": [{"id": 11, "n": 420, "data": "2026-10-29", "formato": "reel", "situacao": "pronto"},
                                     {"id": 12, "n": 425, "data": "2026-10-31", "formato": "reel", "situacao": "regravar"},
                                     {"id": 13, "n": 430, "data": "2026-11-02", "formato": "reel", "situacao": "erro"}]}
    assert corpo("video", video) == (
        "**O corretor de vídeo terminou 3 reels que ainda não foram aprovados.**\n\n"
        "- Reel de quinta-feira, 29/10 (peça nº 420): Vídeo corrigido pronto. Veja a prévia e o relatório; conferido, o administrador "
        "aprova a peça.\n"
        "- Reel de sábado, 31/10 (peça nº 425): Precisa regravar. O relatório mostra o bloco a regravar; os outros clipes vão de novo como "
        "estão.\n"
        "- Reel de segunda-feira, 02/11 (peça nº 430): O corretor parou. O motivo e o que fazer estão no quadro do vídeo.\n\n"
        "O que fazer: abra o Radar → **Pauta** → a peça do reel → quadro **Corretor de vídeo**.\n\n" + RODAPE +
        f"\n\n<!-- radar-lembrete: lote {LOTE} itens 11 12 13 -->")
    assert corpo("video", {**video, "itens": video["itens"][:1]}).startswith("**O corretor de vídeo terminou 1 reel que ainda não foi aprovado.**")
    noticia = {"lote": LOTE, "horas": 3, "itens": [
        {"id": 21, "n": 31, "canal": "site", "situacao": "erro", "desde": "2026-10-26T13:12:00+00:00"},
        {"id": 22, "n": 32, "canal": "site", "situacao": "parada", "desde": "2026-10-26T11:05:00+00:00"},
        {"id": 23, "n": 77, "canal": "instagram", "situacao": "erro", "desde": "2026-10-26T12:40:00+00:00"},
        {"id": 24, "n": 78, "canal": "facebook", "situacao": "parada", "desde": "2026-10-26T12:40:00+00:00"}]}
    assert corpo("noticia", noticia) == (
        "**4 publicações de notícia não saíram.**\n\n"
        "- Site, autorizada em 26/10 às 10:12: o envio deu erro (envio nº 31).\n"
        "- Site, autorizada em 26/10 às 08:05: parada há mais de 3 horas, esperando o robô do site (envio nº 32).\n"
        "- Instagram, autorizada em 26/10 às 09:40: o envio deu erro (envio nº 77).\n"
        "- Facebook, autorizada em 26/10 às 09:40: parada há mais de 3 horas, sem sair (envio nº 78).\n\n"
        "O que fazer: abra o Radar → **Publicações**: a notícia aparece como “Não concluída” ou “Autorizado — aguardando o robô”. No site "
        "parado, clique em “Acionar o robô agora” (o robô do site depende do GitHub, que às vezes atrasa). No que deu erro, abra o assunto "
        "(passo **3. Publicar**): o motivo está lá, e só sai de novo com nova autorização do administrador.\n\n" + RODAPE +
        f"\n\n<!-- radar-lembrete: lote {LOTE} itens 21 22 23 24 -->")
    assert corpo("noticia", {**noticia, "itens": noticia["itens"][:1]}).startswith("**1 publicação de notícia não saiu.**")
    # mais de 15: "e mais N", e a marca leva todos (os que foram contados no e-mail também ficam avisados)
    muitos = {**noticia, "itens": [{**noticia["itens"][0], "id": 100 + k, "n": k} for k in range(17)]}
    texto = corpo("noticia", muitos)
    assert texto.count("\n- Site, autorizada") == 15 and "\n- … e mais 2 (a lista inteira está no Radar).\n\n" in texto
    assert texto.endswith("itens " + " ".join(str(100 + k) for k in range(17)) + " -->")
    assert radar_lembretes.MARCA.search(texto).group(1) == LOTE
    # o título de cada tipo começa com o prefixo dos lembretes, que não é nenhum dos avisos do radar_alertas (eles nunca o fecham)
    import radar_alertas
    assert all(t.startswith(radar_lembretes.PREFIXO_LEMBRETE) and not t.startswith(radar_alertas.PREFIXOS_PADRAO)
               for t in radar_lembretes.TITULOS.values())
    assert sorted(radar_lembretes.TITULOS) == ["aprovacao", "copia", "noticia", "pauta", "vencimento", "video"]   # v0.32.0: + 2


# ------------------------------------------------------------------------------------- o setup por cima do banco da v0.28.1
SEM_OS_LEMBRETES = """
drop table public.radar_lembretes;
drop function public.radar_lembretes_cfg(), public.radar_lembretes_madura(text, text, jsonb, timestamptz, jsonb, timestamptz),
  public.radar_lembretes_observar(timestamptz), public.radar_lembretes_devidos(timestamptz), public.radar_lembretes_acionar(),
  public.radar_lembretes_ha_envio(), public.radar_lembretes_lote_em(timestamptz), public.radar_lembretes_lote(),
  public.radar_lembretes_enviado_em(uuid, int, bigint[], timestamptz), public.radar_lembretes_enviado(uuid, int, bigint[]),
  public.radar_lembretes_situacao();
delete from public.radar_config where chave = 'lembretes';
"""


def _contagens(banco):
    with conectar(banco) as c:
        tabelas = [t for (t,) in c.execute("""select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
                                              where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'radar\\_%'
                                              order by 1""").fetchall()]
        return {t: c.execute(f"select count(*) from public.{t}").fetchone()[0] for t in tabelas}


def test_setup_por_cima_do_banco_sem_os_lembretes_nao_perde_dados():
    """O banco da v0.28.1 (o setup desta versão sem a tabela, as funções e a chave dos lembretes), com dados de mentira: o setup desta
    versão (v0.33.0, que traz junto os da v0.29.0 a v0.32.0) roda duas vezes seguidas sem erro, nada some, a chave "lembretes" entra com os padrões
    e, ajustada, não é sobrescrita."""
    banco = "radar_lembretes_cima"
    with conectar("postgres") as c:
        c.execute(f"drop database if exists {banco} with (force)")
        c.execute(f"create database {banco}")
    try:
        assert psql(RAIZ / "testes" / "supabase_simulado.sql", banco).returncode == 0
        assert psql(SETUP, banco).returncode == 0
        with conectar(banco) as c:
            c.execute(SEM_OS_LEMBRETES)
            assert c.execute("select to_regclass('public.radar_lembretes')").fetchone()[0] is None
            c.execute("insert into radar_pessoas (nome, nome_na_peca, area) values ('Ana Teste', 'Ana', 'Fiscal')")
            c.execute("insert into radar_pauta_pecas (data, tipo, formato, assunto) values ('2026-11-04', 'bastidor', 'foto', 'Bastidor')")
            c.execute("insert into radar_assuntos (titulo) values ('Assunto de teste')")
            c.execute("update radar_config set valor = valor || '{\"janela_horas\": 4}' where chave = 'pauta'")
        antes = _contagens(banco)
        for vez in (1, 2):
            r = psql(SETUP, banco)
            assert r.returncode == 0, (vez, r.stderr)
        depois = _contagens(banco)
        assert {t: n for t, n in depois.items() if t not in ("radar_config", "radar_instalacoes", "radar_lembretes", "radar_auditoria")} == \
               {t: n for t, n in antes.items() if t not in ("radar_config", "radar_instalacoes", "radar_auditoria")}
        assert depois["radar_config"] == antes["radar_config"] + 1 and depois["radar_instalacoes"] == antes["radar_instalacoes"] + 2
        assert depois["radar_lembretes"] == 0 and len(depois) == 30                          # v0.32.0: + 2 tabelas
        with conectar(banco) as c:
            assert c.execute("select valor from radar_config where chave = 'lembretes'").fetchone()[0] == {
                "ligado": True, "hora": "16:00", "de": "08:00", "ate": "20:00", "aprovacao_horas": 24, "parada_horas": 3,
                "pauta": True, "aprovacao": True, "video": True, "noticia": True, "vencimento": True, "copia": True}
            assert c.execute("select valor->>'janela_horas' from radar_config where chave = 'pauta'").fetchone()[0] == "4"
            c.execute("""update radar_config set valor = '{"ligado": false, "hora": "17:30"}' where chave = 'lembretes'""")
            assert c.execute("select versao from radar_instalacoes where depois is not null order by id desc limit 1").fetchone()[0] == "v0.33.0"
        assert psql(SETUP, banco).returncode == 0
        with conectar(banco) as c:                                                         # o ajuste do administrador fica
            assert c.execute("select valor from radar_config where chave = 'lembretes'").fetchone()[0] == {
                "ligado": False, "hora": "17:30", "vencimento": True, "copia": True}            # v0.32.0: só as chaves que faltavam
            assert c.execute("select count(*) from radar_pessoas where nome = 'Ana Teste'").fetchone()[0] == 1
    finally:
        with conectar("postgres") as c:
            c.execute(f"drop database if exists {banco} with (force)")
