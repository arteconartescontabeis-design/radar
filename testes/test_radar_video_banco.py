"""Corretor de vídeo dos reels (v0.22.0), o banco: radar_videos, radar_video_acessos, as funções radar_video_* e a amarra da aprovação.

Confere, com nomes, falas e chaves de mentira (o repositório é público):
  * a tabela só se lê pela regra (administrador e editor) e só se grava pelas funções; o papel interno não lê nem grava;
  * radar_video_criar confere, ANTES de qualquer arquivo sair: a peça (reel, não aprovada, não cancelada, não publicada), a fala para
    conferência (no roteiro, palavra por palavra e na ordem), o boletim pago, as pessoas (termo novo do corretor, menor, termo de uso de
    imagem de hoje), a cartela (identificação legal, linha de quem fala com o CRC, "contador" e "especialista"), os clipes, as quatro
    declarações, o gancho e a cota do mês; o envio novo deixa o anterior substituído;
  * o robô (pelo papel interno): pegar com trava, a recuperação do pedido parado (3 tentativas), a cota, a rodada que nunca se repete,
    o áudio, o relatório parcial, o concluir que decide de novo (divergência sem "a transcrição errou" e boletim pago → regravar) e os
    códigos transitórios do falhar;
  * a pendência do reel em radar_pauta_problemas, a aprovação amarrada ao sha256 (caixas "video" e "viu"), desaprovar, o registro manual
    sem vídeo, a prévia e o baixar (com o registro de quem viu ou baixou);
  * os ajustes do administrador, reconferir, tentar de novo, descartar e "apaguei";
  * a trilha sem a fala, a cartela, o relatório e os ajustes; a limpeza nos prazos; as peças publicadas da pessoa;
  * sql/radar-video-agenda.sql (as duas chaves no Vault, a reserva só com fila, a limpeza diária) e as reversões.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import psycopg
import pytest

from conftest import (ADMIN, CRON_SIMULADO, EDITOR, LEITOR, NET_SIMULADO, RAIZ, REVERSAO, SETUP, VAULT_SIMULADO, carregar_fontes_novas,
                      como, conectar, psql)
from test_radar_agenda import apagar_banco, chave_anon_do_config, novo_banco, sem_extensoes
from test_radar_banco import (IDENT, LEG_PECA, SHA_VIDEO, aprovar_peca, conferir, hoje, lido_peca, marcar_pronta, mudar_por_fora,  # noqa: F401
                              nova_peca, nova_pessoa, pauta, pessoa_do_corretor, video_pronto, voltar_a_data)

ROTEIRO = ("Duração: cerca de 30 segundos.\n| Tempo | Fala | Texto na tela |\n"
           "| 0 a 3 s | \"O prazo do Simples vence no dia 20.\" | PRAZO DIA 20 |\n"
           "| 3 a 20 s | \"Confira com a gente antes do vencimento para não pagar multa nem juros.\" | Fale com a Artecon |\n" + IDENT)
FALA = "O prazo do Simples vence no dia 20. Confira com a gente antes do vencimento para não pagar multa nem juros."
CONFERIDAS = [{"informacao": "O DAS do Simples vence no dia 20", "fonte": "Portal do Simples Nacional"}]
PARTES = [{"n": 1, "tipo": "video/mp4", "bytes": 1000}, {"n": 2, "tipo": "video/quicktime", "bytes": 2000}]
DECL = ["so_marcadas", "sem_fundo", "so_voz", "fala_confere"]
CRIAR = "select radar_video_criar(%s, %s, %s, %s, %s::text[], %s, %s::text[])"
SHA2 = "b" * 64
RELATORIO = {"versao": 2, "texto_final": FALA, "divergencias": [], "avisos": []}
DIVERGENCIA = {"k": 0, "id": "0123456789abcdef", "falado": "dia 25", "roteiro": "dia 20", "tipo": "numero", "regravar": True,
               "transcricao_errou": False}


def reel(db, dias=5, pessoa=None, **campos):
    """Peça reel com o roteiro do plano (tabela), a chamada (o gancho) e a Ana Teste, com o termo novo, marcada."""
    pessoa = pessoa or pessoa_do_corretor(db)
    campos = {"roteiro": ROTEIRO, "pessoas": [pessoa], "conferidas": CONFERIDAS, "chamada": "O prazo do Simples vence no dia 20", **campos}
    return nova_peca(db, dias=dias, tipo="reel", formato="reel", **campos), pessoa


def criar(pid, pessoa, uid=EDITOR, partes=PARTES, fala=FALA, cartela=(IDENT,), gancho=False, decl=DECL):
    with como("authenticated", uid) as c:
        return c.execute(CRIAR, (pid, json.dumps(partes), pessoa, fala, list(cartela), gancho, list(decl))).fetchone()[0]


def tela(sql, *args, uid=EDITOR):
    with como("authenticated", uid) as c:
        return c.execute(sql, args).fetchone()[0]


def robo(sql, *args):
    with como("service_role") as c:
        return c.execute(sql, args).fetchone()[0]


def pegar():
    return robo("select radar_video_pegar()")


def concluir(vid, t, situacao="pronto", relatorio=None, sha=SHA_VIDEO, bytes_=4000, duracao=38.4):
    return robo("select radar_video_concluir(%s, %s, %s, %s, %s, %s::bigint, %s::numeric)", vid, t, situacao, json.dumps(relatorio or RELATORIO), sha, bytes_, duracao)


def _py(x):
    """numeric → float e uuid → texto, para comparar com o que a função devolve em JSON."""
    return float(x) if isinstance(x, Decimal) else str(x) if isinstance(x, UUID) else x


def video(db, vid, campos="situacao"):
    linha = tuple(_py(x) for x in db.execute(f"select {campos} from radar_videos where id = %s", (vid,)).fetchone())
    return linha[0] if len(linha) == 1 else linha


def na_fila(db, pid, pessoa, uid=EDITOR, **kw):
    """Gravação registrada e enviada (os clipes conferidos pela função radar-video): na fila do robô."""
    vid = criar(pid, pessoa, uid=uid, **kw)["id"]
    tela("select radar_video_enviado(%s)", vid, uid=uid)
    return vid


def ate_pronto(db, pid, pessoa, relatorio=None, sha=SHA_VIDEO):
    """Na fila, pego pelo robô, transcrito e concluído: devolve (vídeo, rodada)."""
    vid = na_fila(db, pid, pessoa)
    p = pegar()
    assert p["id"] == vid
    robo("select radar_video_registrar_audio(%s, %s, %s::numeric, %s)", vid, p["tentativa"], 31.5, True)
    concluir(vid, p["tentativa"], relatorio=relatorio, sha=sha)
    return vid, p["tentativa"]


def config(db, **valores):
    db.execute("update radar_config set valor = valor || %s where chave = 'corretor_video'", (json.dumps(valores),))


@pytest.fixture()
def corretor(pauta):
    """A Pauta com o CNPJ e o CRC de mentira (fixture pauta) e as Configurações do corretor de volta ao padrão no fim."""
    antes = pauta.execute("select valor from radar_config where chave = 'corretor_video'").fetchone()[0]
    yield pauta
    pauta.execute("update radar_config set valor = %s where chave = 'corretor_video'", (json.dumps(antes),))


# ------------------------------------------------------------------ tabela e regras de acesso
def test_video_so_admin_e_editor_leem_e_ninguem_grava_direto(corretor):
    db = corretor
    pid, ana = reel(db)
    r = criar(pid, ana)
    assert r["versao"] == 1 and re.fullmatch(r"[0-9a-f-]{36}", r["id"])
    for uid in (EDITOR, ADMIN):
        with como("authenticated", uid) as c:
            assert c.execute("select situacao, fala_roteiro from radar_videos").fetchall() == [("aguardando_envio", FALA)]
    with como("authenticated", LEITOR) as c:
        assert c.execute("select count(*) from radar_videos").fetchone()[0] == 0                 # o leitor não vê a fala
    for papel, uid in (("authenticated", ADMIN), ("authenticated", EDITOR)):
        for sql in ("update radar_videos set situacao = 'pronto'", "delete from radar_videos",
                    "insert into radar_video_acessos (video_id, acao) select id, 'previa' from radar_videos",
                    f"insert into radar_videos (peca_id, partes, fala_pessoa, roteiro_hash, declaracoes) values ({pid}, '[]', 1, 'x', '{{}}')"):
            with como(papel, uid) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)
    for sql in ("select * from radar_videos", "select * from radar_video_acessos", "update radar_videos set situacao = 'pronto'"):
        for papel in ("service_role", "anon"):                                                    # a chave interna não lê nem grava
            with como(papel) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)
    # as funções do robô não são da tela, e as da tela não são do papel interno
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("select radar_video_pegar()")
    with como("service_role") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute(CRIAR, (pid, json.dumps(PARTES), ana, FALA, [IDENT], False, DECL))
    for aux in ("radar_video_pendencia(1)", "radar_video_cartela_falta('{}', 1)", "radar_video_travar(gen_random_uuid())",
                "radar_video_config()", "radar_video_segundos_mes()"):
        for papel, uid in (("authenticated", ADMIN), ("service_role", None)):
            with como(papel, uid) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute("select " + aux)


def test_criar_confere_tudo_antes_de_qualquer_arquivo_sair(corretor, request):
    db = corretor
    pid, ana = reel(db)
    with como("authenticated", LEITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR300"):
        c.execute(CRIAR, (pid, json.dumps(PARTES), ana, FALA, [IDENT], False, DECL))
    erro = lambda codigo, **kw: pytest.raises(psycopg.errors.RaiseException, match=codigo)
    # 1. a peça
    imagem = nova_peca(db, dias=9, pessoas=[ana])
    with erro("RADAR301: o corretor de vídeo é só para a peça em formato reel"):
        criar(imagem, ana)
    # 2. a fala: no roteiro, palavra por palavra e na ordem, com ao menos 10 palavras
    for ruim in (FALA.replace("dia 20", "dia 25"), "O prazo do Simples vence no dia 20.", FALA.split(". ")[1] + " " + FALA.split(". ")[0]):
        with erro("RADAR302"):
            criar(pid, ana, fala=ruim)
    # 4. as pessoas
    bruno = pessoa_do_corretor(db, "Bruno Exemplo", "Bruno", categoria="contador", crc="CRC-SC 054321/O-1")
    with erro("RADAR304: quem fala tem de estar marcada"):
        criar(pid, bruno)
    db.execute("update radar_pessoas set termo_corretor_em = null where id = %s", (ana,))
    with erro(r"RADAR304: uma pessoa da peça não pode aparecer no vídeo \(sem o termo novo, que cita o corretor de vídeo\)"):
        criar(pid, ana)
    db.execute("update radar_pessoas set termo_corretor_em = %s where id = %s", (hoje(db) + timedelta(days=1), ana))   # assinado amanhã
    with erro("RADAR304"):
        criar(pid, ana)
    db.execute("update radar_pessoas set termo_corretor_em = '2020-01-01', menor = true where id = %s", (ana,))
    with erro("RADAR304: .*menor de idade"):
        criar(pid, ana)
    db.execute("update radar_pessoas set menor = false, termo_revogado_em = %s where id = %s", (hoje(db), ana))
    with erro("RADAR304: .*termo revogado no Instagram"):
        criar(pid, ana)
    db.execute("update radar_pessoas set termo_revogado_em = null where id = %s", (ana,))
    # 5. a cartela: a identificação legal das Configurações; "contador(a)" e o CRC só na linha de quem fala, conforme o registro
    for cartela, motivo in [([], "de 1 a 4 linhas"), (["Artecon Artes Contábeis ME · CRC-SC 012345/O-9"], "falta a linha de identificação"),
                            ([IDENT, "Ana, contadora · CRC-SC 012345/O-9"], "só leva a identificação legal"),
                            ([IDENT, "Fale com a especialista"], "especialista"), ([IDENT, "Linha solta"], "só leva a identificação legal"),
                            ([IDENT] * 5, "de 1 a 4 linhas"), ([IDENT + "\n"], "de 1 a 4 linhas")]:
        with erro("RADAR305: .*" + motivo):
            criar(pid, ana, cartela=cartela)
    db.execute("update radar_pauta_pecas set pessoas = %s::bigint[] where id = %s", ([ana, bruno], pid))
    for cartela, motivo in [([IDENT], "falta a linha de quem fala"), ([IDENT, "Bruno, contador"], "registro dela no CRC"),
                            ([IDENT, "Bruno, contador · CRC-SC 099999/O-1"], "registro dela no CRC")]:
        with erro("RADAR305: .*" + motivo):
            criar(pid, bruno, cartela=cartela)
    db.execute("update radar_pessoas set categoria = 'tecnico' where id = %s", (bruno,))
    with erro("RADAR305: quem fala é técnico"):
        criar(pid, bruno, cartela=[IDENT, "Bruno, contador · CRC-SC 054321/O-1"])
    db.execute("update radar_pessoas set categoria = 'contador' where id = %s", (bruno,))
    # 6. os clipes, as declarações e o gancho
    for partes in ([], [{"n": i, "tipo": "video/mp4", "bytes": 10} for i in range(1, 14)], [{"n": 1, "tipo": "video/x-matroska", "bytes": 10}],
                   [{"n": 2, "tipo": "video/mp4", "bytes": 10}], [{"n": 1, "tipo": "video/mp4", "bytes": 0}],
                   [{"n": 1, "tipo": "video/mp4", "bytes": 10, "nome": "IMG_0001.MOV"}], ["solto"],
                   [{"n": 1, "tipo": "video/mp4", "bytes": 300 * 1024 * 1024}, {"n": 2, "tipo": "video/mp4", "bytes": 300 * 1024 * 1024}]):
        with erro("RADAR306"):
            criar(pid, ana, partes=partes)
    with erro("RADAR307"):
        criar(pid, ana, decl=DECL[:3])
    with erro("RADAR307"):
        criar(pid, ana, decl=DECL + ["outra"])
    db.execute("update radar_pauta_pecas set chamada = '' where id = %s", (pid,))
    with erro("RADAR308"):
        criar(pid, ana, gancho=True)
    db.execute("update radar_pauta_pecas set chamada = 'O prazo do Simples vence no dia 20' where id = %s", (pid,))
    # a cota do mês (Configurações → Corretor de vídeo → limite_min_mes)
    config(db, limite_min_mes=1)
    outro, _ = reel(db, dias=8, pessoa=ana)
    v0 = video_pronto(db, outro, ana)
    db.execute("update radar_videos set segundos_audio = 60, transcrito_em = now() where id = %s", (v0,))
    with erro("RADAR312"):
        criar(pid, ana)
    # o que sobra do mês não cabe a gravação (a duração que o navegador leu dos clipes): recusa antes de qualquer arquivo sair, com o
    # que sobra; sem a duração (o navegador não abriu o clipe), vale só o mês acabado — o robô confere
    db.execute("update radar_videos set segundos_audio = 30 where id = %s", (v0,))
    with como("authenticated", EDITOR) as c:
        assert c.execute("select radar_video_cota()").fetchone()[0] == {"segundos_mes": 30, "limite_s": 60}
    with como("authenticated", LEITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR300"):
        c.execute("select radar_video_cota()")
    criar_com = lambda d: tela(CRIAR.replace(")", ", %s::numeric)"), outro, json.dumps(PARTES), ana, FALA, [IDENT], False, DECL, d)
    with erro("RADAR312: a gravação tem cerca de 31 s, e o corretor só pode transcrever mais 30 s neste mês"):
        criar_com(31.2)
    assert video(db, criar_com(29.5)["id"], "situacao") == "aguardando_envio"
    config(db, limite_min_mes=60)
    # 3. o boletim pago (só sim ou não: o trecho não aparece)
    carregar_fontes_novas(db, request)
    frase = "o comitê gestor publicou nesta semana a orientação completa sobre o novo prazo de entrega das declarações mensais"
    db.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo)
                  select id, 'https://boletim.exemplo/v', 'Boletim de mentira', %s, 'h-boletim-video' from radar_fontes where slug = 'itc-email'""",
               (frase,))
    com_boletim = ROTEIRO.replace("| Fale com a Artecon |", "| " + frase + " |")
    db.execute("update radar_pauta_pecas set roteiro = %s where id = %s", (com_boletim, pid))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR303") as e:
        criar(pid, ana)
    assert "comitê" not in str(e.value)
    db.execute("update radar_pauta_pecas set roteiro = %s where id = %s", (ROTEIRO, pid))
    # deu certo: o envio novo deixa o anterior substituído (um vivo por peça)
    v1 = criar(pid, bruno, cartela=[IDENT, "Bruno, contador · CRC-SC 054321/O-1"], gancho=True)
    assert video(db, v1["id"], "situacao, gancho, cartela_linhas, partes, enviado_por::text") == (
        "aguardando_envio", "O prazo do Simples vence no dia 20", [IDENT, "Bruno, contador · CRC-SC 054321/O-1"], PARTES, EDITOR)
    v2 = criar(pid, ana, uid=ADMIN)
    assert v2["versao"] == 2 and video(db, v1["id"], "situacao, encerrado_em is not null") == ("substituido", True)
    # a peça aprovada, cancelada ou já publicada não recebe gravação
    for sql, msg in (("situacao = 'cancelada'", "cancelada"), ("situacao = 'aprovada'", "aprovada"),
                     ("situacao = 'em_producao', publicado_manual_em = current_date", "já saiu")):
        mudar_por_fora(db, pid, sql)
        with erro("RADAR301: .*" + msg):
            criar(pid, ana)
    mudar_por_fora(db, pid, "publicado_manual_em = null")


def test_enviado_fila_pegar_com_trava_e_robo_ate_o_fim(corretor):
    db = corretor
    pid, ana = reel(db)
    vid = criar(pid, ana)["id"]
    assert tela("select radar_video_para_envio(%s)", vid)["partes"] == PARTES
    assert tela("select radar_video_para_envio(%s)", vid, uid=ADMIN)["peca"] == pid                 # o administrador também continua
    assert pegar() is None                                                                           # esperando os arquivos: não vai ao robô
    assert tela("select radar_video_enviado(%s)", vid) == {"id": vid, "situacao": "na_fila"}
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR309"):
        tela("select radar_video_enviado(%s)", vid)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR309"):
        tela("select radar_video_para_envio(%s)", vid)
    p = pegar()
    assert {k: p[k] for k in ("id", "tentativa", "modo", "partes", "fala_roteiro", "cartela_linhas", "gancho", "palavras_tentativa", "restante_s")} == {
        "id": vid, "tentativa": 1, "modo": "completo", "partes": PARTES, "fala_roteiro": FALA, "cartela_linhas": [IDENT], "gancho": None,
        "palavras_tentativa": None, "restante_s": 1800}                                             # 30 minutos por padrão
    assert p["config"]["glossario"][:3] == ["eSocial", "DCTFWeb", "IBS"] and p["config"]["variantes"]["IBS"] == ["ips", "ibis"]
    assert {k: p["config"][k] for k in ("pausa_max_s", "pausa_bloco_s", "lufs", "cartela_s", "cartela_extra", "duracao_max_s")} == {
        "pausa_max_s": 1.0, "pausa_bloco_s": 0.8, "lufs": -14, "cartela_s": 3, "cartela_extra": "", "duracao_max_s": 90}
    assert "Ana" not in json.dumps(p)                                                                # nenhum nome no pedido (sem a cartela de quem fala)
    assert pegar() is None and video(db, vid, "situacao, tentativas, rodada") == ("processando", 1, 1)
    # a rodada errada (o pedido mudou de mãos) nunca grava
    for sql, args in (("select radar_video_em_curso(%s, %s)", (vid, 2)), ("select radar_video_parcial(%s, %s, '{}')", (vid, 2)),
                      ("select radar_video_falhar(%s, %s, 'storage')", (vid, 9))):
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR316"):
            robo(sql, *args)
    assert robo("select radar_video_em_curso(%s, %s)", vid, 1) == {"id": vid, "tentativa": 1, "modo": "completo", "partes": 2,
                                                                   "palavras_tentativa": None, "sha256": None}
    # o áudio transcrito conta na cota do mês; o palavras.json desta rodada passa a valer
    assert robo("select radar_video_registrar_audio(%s, %s, %s::numeric, %s)", vid, 1, 31.5, True) == {"restante_s": 1768.5}
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR316: segundos"):
        robo("select radar_video_registrar_audio(%s, %s, %s::numeric, %s)", vid, 1, 301, True)
    assert video(db, vid, "segundos_audio, palavras_tentativa, transcrito_em is not null") == (31.5, 1, True)
    assert robo("select radar_video_parcial(%s, %s, %s)", vid, 1, json.dumps({"divergencias": [DIVERGENCIA]})) is True
    assert video(db, vid, "relatorio") == {"divergencias": [DIVERGENCIA], "parcial": True}
    # o banco decide de novo: a divergência que o administrador não marcou pede regravar, ainda que o robô diga "pronto"
    rel = {**RELATORIO, "divergencias": [DIVERGENCIA]}
    assert concluir(vid, 1, "pronto", rel) == {"situacao": "regravar"}
    assert video(db, vid, "situacao, sha256, bytes, duracao_final, pego_em, antigos") == ("regravar", SHA_VIDEO, 4000, 38.4, None, False)
    assert video(db, vid, "relatorio")["parcial"] is False
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR316"):                          # depois de concluído, não é mais dele
        concluir(vid, 1)
    # o administrador ouviu e marcou "a transcrição errou": monta de novo, sem transcrever (modo montagem, com a transcrição guardada)
    errou = {"transcricao_errou": [DIVERGENCIA["id"]], "estilo": "compacta"}
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR300"):
        c.execute("select radar_video_ajustar(%s, %s, null)", (vid, json.dumps(errou)))
    assert tela("select radar_video_ajustar(%s, %s, null)", vid, json.dumps(errou), uid=ADMIN) == {"id": vid, "modo": "montagem"}
    assert video(db, vid, "situacao, tentativas, rodada, fila_em is not null") == ("na_fila", 0, 1, True)
    p = pegar()
    assert (p["tentativa"], p["modo"], p["palavras_tentativa"], p["ajustes"]) == (2, "montagem", 1, errou)
    robo("select radar_video_registrar_audio(%s, %s, %s::numeric, %s)", vid, 2, 0, False)                    # montagem: nada transcrito
    assert video(db, vid, "segundos_audio, palavras_tentativa") == (31.5, 1)
    # a marca vale pelo id da divergência, e não pela posição: na montagem o alinhamento mudou (uma variante nova tirou a divergência
    # marcada) e a que ficou na posição 0 é outra — continua pedindo regravar, ainda que o robô diga "pronto"
    outra = {**DIVERGENCIA, "id": "fedcba9876543210", "falado": "de R$ 600", "roteiro": "de R$ 500,00", "transcricao_errou": True}
    assert concluir(vid, 2, "pronto", {**rel, "divergencias": [outra]}, sha=SHA2) == {"situacao": "regravar"}
    db.execute("update radar_videos set situacao = 'na_fila', fila_em = now() where id = %s", (vid,))
    p = pegar()
    assert concluir(vid, p["tentativa"], "pronto", {**rel, "divergencias": [{**DIVERGENCIA, "transcricao_errou": True}]}, sha=SHA2) == {"situacao": "pronto"}
    assert video(db, vid, "situacao, sha256, antigos") == ("pronto", SHA2, True)                     # o sha256 anterior fica para a limpeza
    # o robô que mente ("transcricao_errou" sem o administrador marcar) não tira o regravar
    db.execute("update radar_videos set ajustes = '{}', situacao = 'na_fila', fila_em = now() where id = %s", (vid,))
    p = pegar()
    assert concluir(vid, p["tentativa"], "pronto", {**rel, "divergencias": [{**DIVERGENCIA, "transcricao_errou": True}]}, sha=SHA2) == {"situacao": "regravar"}
    for ruim in (dict(situacao="publicado"), dict(sha="X" * 64), dict(bytes_=400 * 1024 * 1024), dict(duracao=0)):
        db.execute("update radar_videos set situacao = 'processando' where id = %s", (vid,))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR316"):
            concluir(vid, p["tentativa"], **ruim)


def test_pegar_recupera_o_parado_respeita_3_tentativas_a_cota_e_a_trava(corretor):
    db = corretor
    ana = pessoa_do_corretor(db)
    vids = [na_fila(db, reel(db, dias=5 + i, pessoa=ana)[0], ana) for i in range(4)]
    db.execute("update radar_videos set fila_em = now() - make_interval(mins => (10 - n)::int) from (select id, row_number() over (order by criado_em) n "
               "from radar_videos) o where o.id = radar_videos.id")
    assert pegar()["id"] == vids[0]
    # parado há mais de 20 minutos (o robô caiu): volta à fila, no fim dela — quem esperava antes sai primeiro
    db.execute("update radar_videos set pego_em = now() - interval '21 minutes' where id = %s", (vids[0],))
    assert pegar()["id"] == vids[1] and video(db, vids[0], "situacao, tentativas, pego_em") == ("na_fila", 1, None)
    db.execute("update radar_videos set fila_em = now() - interval '1 hour' where id = %s", (vids[0],))
    p = pegar()
    assert (p["id"], p["tentativa"]) == (vids[0], 2) and video(db, vids[0], "tentativas, rodada") == (2, 2)
    # na 3ª vez parado, vira erro "tempo_esgotado"
    db.execute("update radar_videos set pego_em = now() - interval '21 minutes', tentativas = 3 where id = %s", (vids[0],))
    assert pegar()["id"] == vids[2] and video(db, vids[0], "situacao, erro_codigo") == ("erro", "tempo_esgotado")
    # falhar: o transitório volta à fila (até 3 tentativas); o resto vira erro, com o código fixo
    assert robo("select radar_video_falhar(%s, %s, %s)", vids[1], 1, "storage") == {"situacao": "na_fila"}
    assert video(db, vids[1], "situacao, erro_codigo, pego_em") == ("na_fila", "storage", None)
    assert robo("select radar_video_falhar(%s, %s, %s)", vids[2], 1, "x'; drop table radar_videos; --") == {"situacao": "erro"}
    assert video(db, vids[2], "erro_codigo") == "erro_interno"
    db.execute("update radar_videos set tentativas = 3, situacao = 'processando', rodada = 5 where id = %s", (vids[1],))
    assert robo("select radar_video_falhar(%s, %s, %s)", vids[1], 5, "azure_fora") == {"situacao": "erro"}
    assert video(db, vids[1], "erro_codigo") == "azure_fora"
    for codigo in ("transcricao_ocupada", "azure_cota", "sem_audio"):                          # a Azure ocupada por 10 min: erro (tentar de novo)
        db.execute("update radar_videos set tentativas = 1, situacao = 'processando', rodada = 6 where id = %s", (vids[1],))
        assert robo("select radar_video_falhar(%s, %s, %s)", vids[1], 6, codigo) == {"situacao": "erro"}, codigo
    # a cota do mês: sem a transcrição guardada, vira erro "cota_radar"; com ela (montagem), segue
    config(db, limite_min_mes=1)
    db.execute("update radar_videos set segundos_audio = 60, transcrito_em = now() where id = %s", (vids[0],))
    assert pegar() is None and video(db, vids[3], "situacao, erro_codigo") == ("erro", "cota_radar")
    db.execute("update radar_videos set situacao = 'na_fila', modo = 'montagem', palavras_tentativa = 1, erro_codigo = null where id = %s", (vids[3],))
    p = pegar()
    assert (p["id"], p["restante_s"]) == (vids[3], 0)
    # dois robôs ao mesmo tempo nunca pegam o mesmo pedido
    for v in vids[:2]:
        db.execute("update radar_videos set situacao = 'na_fila', tentativas = 0 where id = %s", (v,))
    config(db, limite_min_mes=60)
    with conectar(autocommit=False) as c1, conectar(autocommit=False) as c2:
        for c in (c1, c2):
            c.execute("set lock_timeout = '3s'")                                              # sem o skip locked, o 2º esperaria o 1º
            c.execute("set role service_role")
        a = c1.execute("select radar_video_pegar()").fetchone()[0]
        b = c2.execute("select radar_video_pegar()").fetchone()[0]
        assert {a["id"], b["id"]} == set(vids[:2])
        c1.rollback()
        c2.rollback()


def test_pendencia_do_reel_e_aprovacao_amarrada_ao_sha256(corretor):
    db = corretor
    pid, ana = reel(db)
    assert conferir(pid) == ["Reel: envie a gravação (Corretor de vídeo)"]
    vid = criar(pid, ana)["id"]
    passos = [("aguardando_envio", "Reel: termine de enviar a gravação (Corretor de vídeo)"), ("na_fila", "Reel: o corretor ainda está trabalhando"),
              ("processando", "Reel: o corretor ainda está trabalhando")]
    for situacao, msg in passos:
        db.execute("update radar_videos set situacao = %s where id = %s", (situacao, vid))
        assert conferir(pid) == [msg], situacao
    db.execute("update radar_videos set situacao = 'erro', erro_codigo = 'sem_audio' where id = %s", (vid,))
    assert conferir(pid) == ["Reel: o corretor parou com erro (sem_audio)"]
    db.execute("update radar_videos set situacao = 'regravar', sha256 = %s, bytes = 4000, duracao_final = 38 where id = %s", (SHA_VIDEO, vid))
    assert conferir(pid) == ["Reel: o vídeo precisa ser regravado (veja o relatório)"]
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR165"):
        marcar_pronta(db, pid)
    db.execute("update radar_videos set situacao = 'pronto' where id = %s", (vid,))
    assert conferir(pid) == []
    for sql, msg in [("update radar_videos set duracao_final = 901 where id = %(v)s", "Reel: o vídeo passou de 15 minutos (o Instagram não aceita reel mais longo)"),
                     ("update radar_videos set arquivos_apagados = '{corrigido}' where id = %(v)s", "Reel: o vídeo corrigido foi apagado (prazo de guarda): envie a gravação de novo"),
                     ("update radar_videos set cartela_linhas = '{\"Só uma linha\"}' where id = %(v)s", "Reel: a cartela não confere com as Configurações ou com Pessoas e termos: refaça a cartela"),
                     ("update radar_pessoas set termo_corretor_em = null where id = %(a)s", "Reel: uma pessoa da peça não pode aparecer no vídeo (sem o termo novo, que cita o corretor de vídeo): confira em Pauta → Pessoas e termos"),
                     ("update radar_videos set fala_pessoa = %(a)s + 1000 where id = %(v)s", "Reel: quem fala não está mais marcada na peça"),
                     ("update radar_pauta_pecas set roteiro = roteiro || ' Novo trecho.' where id = %(p)s", "Reel: o roteiro mudou depois da gravação: use “Conferir com o roteiro novo” ou grave de novo")]:
        antes = db.execute("select row_to_json(v) from radar_videos v where id = %s", (vid,)).fetchone()[0]
        roteiro = db.execute("select roteiro from radar_pauta_pecas where id = %s", (pid,)).fetchone()[0]
        db.execute(sql, {"v": vid, "a": ana, "p": pid})
        assert conferir(pid) == [msg], msg
        db.execute("""update radar_videos set duracao_final = %s, arquivos_apagados = %s, cartela_linhas = %s, fala_pessoa = %s where id = %s""",
                   (antes["duracao_final"], antes["arquivos_apagados"], antes["cartela_linhas"], antes["fala_pessoa"], vid))
        db.execute("update radar_pessoas set termo_corretor_em = '2020-01-01' where id = %s", (ana,))
        db.execute("update radar_pauta_pecas set roteiro = %s where id = %s", (roteiro, pid))
    assert conferir(pid) == []
    marcar_pronta(db, pid)
    # a aprovação do reel: o vídeo pronto pelo hash, a caixa "video" e, se a pessoa pediu no termo, a caixa "viu"
    for kw, codigo in [(dict(), "RADAR313"), (dict(video="c" * 64), "RADAR313"), (dict(video=SHA_VIDEO), "RADAR314: marque “Conferi o vídeo")]:
        with pytest.raises(psycopg.errors.RaiseException, match=codigo):
            aprovar_peca(db, pid, modo="manual", artes=[], conferencias=("pessoas",), **kw)
    db.execute("update radar_pessoas set quer_ver_peca = true where id = %s", (ana,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR314: uma pessoa da peça pediu"):
        aprovar_peca(db, pid, modo="manual", artes=[], conferencias=("pessoas", "video"), video=SHA_VIDEO)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR164"):                       # o reel continua saindo à mão
        aprovar_peca(db, pid, artes=[], conferencias=("pessoas", "video", "viu"), video=SHA_VIDEO)
    aprovar_peca(db, pid, modo="manual", artes=[], conferencias=("pessoas", "video", "viu"), video=SHA_VIDEO)
    assert db.execute("select situacao, video_id::text, video_sha256, aprovado_conferencias from radar_pauta_pecas where id = %s", (pid,)).fetchone() == (
        "aprovada", vid, SHA_VIDEO, ["pessoas", "video", "viu"])
    # a amarra só muda pelas funções; nada muda o vídeo da peça aprovada
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_pauta_pecas set video_sha256 = %s, video_id = null, observacao = 'x' where id = %s", ("c" * 64, pid))
        nova = c.execute("insert into radar_pauta_pecas (data, tipo, formato, video_id, video_sha256) values (%s, 'reel', 'reel', %s, %s) returning id",
                         (hoje(db) + timedelta(days=40), vid, SHA_VIDEO)).fetchone()[0]
    assert db.execute("select video_id::text, video_sha256 from radar_pauta_pecas where id = %s", (pid,)).fetchone() == (vid, SHA_VIDEO)
    assert db.execute("select video_id, video_sha256 from radar_pauta_pecas where id = %s", (nova,)).fetchone() == (None, None)
    for sql, args, uid in [("select radar_video_ajustar(%s, '{}', null)", (vid,), ADMIN), ("select radar_video_descartar(%s)", (vid,), EDITOR),
                           ("select radar_video_reconferir(%s, %s)", (vid, FALA), EDITOR)]:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR301: a peça está aprovada"):
            tela(sql, *args, uid=uid)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR301: a peça está aprovada"):
        criar(pid, ana)
    # o registro manual do reel exige o vídeo aprovado (aprovação antiga, sem o vídeo)
    mudar_por_fora(db, pid, "video_sha256 = null")
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR317"):
        c.execute("select radar_pauta_registrar_manual(%s, 'https://www.instagram.com/reel/ABC/', null, %s)", (pid, hoje(db)))
    mudar_por_fora(db, pid, f"video_sha256 = '{SHA_VIDEO}'")
    # desfazer a aprovação solta o vídeo
    with como("authenticated", EDITOR) as c:
        c.execute("select radar_pauta_desaprovar(%s, true)", (pid,))
    assert db.execute("select situacao, video_id, video_sha256 from radar_pauta_pecas where id = %s", (pid,)).fetchone() == ("pronta", None, None)


def test_previa_e_baixar_registram_quem_e_baixar_so_o_aprovado(corretor):
    db = corretor
    pid, ana = reel(db)
    vid = criar(pid, ana)["id"]
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR309"):
        tela("select radar_video_para_previa(%s)", vid)
    with como("authenticated", LEITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR300"):
        c.execute("select radar_video_para_previa(%s)", (vid,))
    db.execute("update radar_videos set situacao = 'pronto', sha256 = %s, bytes = 4000, duracao_final = 38 where id = %s", (SHA_VIDEO, vid))
    assert tela("select radar_video_para_previa(%s)", vid) == {
        "video": f"corrigido/{vid}/{SHA_VIDEO}.mp4", "sha256": SHA_VIDEO, "quadros": [f"quadros/{vid}/{SHA_VIDEO}/q{k}.jpg" for k in range(1, 5)]}
    assert tela("select radar_video_para_baixar(%s, %s)", pid, lido_peca(db, pid)) == {
        "motivo": "Só a peça aprovada para publicar à mão pode ser copiada ou baixada."}
    marcar_pronta(db, pid)
    aprovar_peca(db, pid, modo="manual", artes=[], conferencias=("pessoas", "video"), video=SHA_VIDEO)
    assert tela("select radar_video_para_baixar(%s, %s)", pid, lido_peca(db, pid)) == {
        "ok": True, "caminho": f"corrigido/{vid}/{SHA_VIDEO}.mp4", "data": str(hoje(db) + timedelta(days=5))}
    assert tela("select radar_video_para_baixar(%s, %s)", pid, "2020-01-01T00:00:00Z")["motivo"].startswith("A peça mudou")
    db.execute("update radar_pessoas set menor = true where id = %s", (ana,))
    assert "menor de idade" in tela("select radar_video_para_baixar(%s, %s)", pid, lido_peca(db, pid))["motivo"]
    db.execute("update radar_pessoas set menor = false where id = %s", (ana,))
    db.execute("update radar_videos set sha256 = %s where id = %s", ("d" * 64, vid))           # o vídeo mudou por fora: não é o aprovado
    assert tela("select radar_video_para_baixar(%s, %s)", pid, lido_peca(db, pid)) == {
        "motivo": "O vídeo aprovado não é mais o vídeo da peça: desfaça a aprovação e confira."}
    db.execute("update radar_videos set sha256 = %s, arquivos_apagados = '{corrigido}' where id = %s", (SHA_VIDEO, vid))
    assert "prazo de guarda" in tela("select radar_video_para_baixar(%s, %s)", pid, lido_peca(db, pid))["motivo"]
    acessos = db.execute("select acao, usuario::text from radar_video_acessos where video_id = %s order by id", (vid,)).fetchall()
    assert acessos == [("previa", EDITOR), ("baixar", EDITOR)]
    with como("authenticated", EDITOR) as c:                                              # quem viu ou baixou: só o administrador lê
        assert c.execute("select count(*) from radar_video_acessos").fetchone()[0] == 0
    with como("authenticated", ADMIN) as c:
        assert c.execute("select count(*) from radar_video_acessos").fetchone()[0] == 2


def test_ajustes_reconferir_de_novo_descartar_e_apaguei(corretor):
    db = corretor
    pid, ana = reel(db)
    vid, _ = ate_pronto(db, pid, ana)
    ajustar = lambda a, cartela=None: tela("select radar_video_ajustar(%s, %s, %s::text[])", vid, json.dumps(a), cartela, uid=ADMIN)
    for ruim in [[], {"outro": 1}, {"manter": "1"}, {"manter": [1.5]}, {"manter": ["1:30"] * 201}, {"transcricao_errou": [-1]},
                 # as marcas apontam o trecho pelo que ele é (a chave do corte e o id da divergência), nunca pela posição na lista
                 {"manter": [3]}, {"manter": ["3"]}, {"manter": ["1:30; drop"]}, {"transcricao_errou": [0]}, {"transcricao_errou": ["0123"]},
                 {"transcricao_errou": ["0123456789ABCDEF"]},
                 {"legenda": "3:2"}, {"legenda": {"1:2:3": "texto"}}, {"legenda": {"3:2": "com {\\b1} comando"}}, {"legenda": {"3": ""}},
                 {"legenda": {"3": "x" * 121}}, {"legenda": {str(i): "a" for i in range(201)}}, {"estilo": "grande"}, {"sem_gancho": "sim"},
                 # a lista [[chave, texto], …], na ordem em que o robô aplica
                 {"legenda": [["3:2"]]}, {"legenda": [[3, "texto"]]}, {"legenda": [["1:2:3", "texto"]]}, {"legenda": ["3:2", "texto"]},
                 {"legenda": [["3:2", "com {\\b1} comando"]]}, {"legenda": [["3", " "]]}, {"legenda": [[str(i), "a"] for i in range(201)]}]:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR310"):
            ajustar(ruim)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR305"):
        ajustar({}, ["Só uma linha"])
    bom = {"manter": ["2:285", "1:30b"], "transcricao_errou": ["0123456789abcdef"],
           "legenda": [["12:4", "O prazo vence hoje"], ["7", "eSocial"], ["12:4", "O prazo vence já"]],
           "estilo": "compacta", "sem_gancho": True}
    assert ajustar(bom, [IDENT]) == {"id": vid, "modo": "montagem"}
    assert video(db, vid, "ajustes, situacao") == (bom, "na_fila")
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR309"):                     # na fila: não ajusta de novo
        ajustar({})
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR309: só o vídeo com erro"):
        tela("select radar_video_de_novo(%s)", vid)
    db.execute("update radar_videos set situacao = 'erro', erro_codigo = 'transcricao_ocupada', tentativas = 3 where id = %s", (vid,))
    assert tela("select radar_video_de_novo(%s)", vid) == {"id": vid, "modo": "montagem"}        # "Tentar de novo" (editor ou administrador)
    assert video(db, vid, "situacao, tentativas, erro_codigo, cartela_linhas") == ("na_fila", 0, None, [IDENT])
    # a cartela que não coube: "Tentar de novo" com as linhas de hoje (conferidas como no envio); sem elas, a de antes pararia de novo
    db.execute("update radar_videos set situacao = 'erro', erro_codigo = 'cartela_nao_cabe' where id = %s", (vid,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR305"):
        tela("select radar_video_de_novo(%s, %s::text[])", vid, ["Só uma linha"])
    nova = IDENT.replace(" · ", " — ")                                                        # a linha de hoje (outra que a do envio)
    assert tela("select radar_video_de_novo(%s, %s::text[])", vid, [nova]) == {"id": vid, "modo": "montagem"}
    assert video(db, vid, "situacao, cartela_linhas") == ("na_fila", [nova])
    db.execute("update radar_videos set cartela_linhas = %s where id = %s", ([IDENT], vid))
    db.execute("update radar_videos set situacao = 'pronto' where id = %s", (vid,))
    # o roteiro mudou só no que não é falado (o "Texto na tela"): a mesma fala, o mesmo vídeo — só o roteiro novo fica registrado, sem
    # voltar à fila, e as marcas do administrador continuam valendo
    so_tela = ROTEIRO.replace("| PRAZO DIA 20 |", "| PRAZO: DIA 20 |")
    db.execute("update radar_pauta_pecas set roteiro = %s where id = %s", (so_tela, pid))
    assert conferir(pid) == ["Reel: o roteiro mudou depois da gravação: use “Conferir com o roteiro novo” ou grave de novo"]
    rodada = video(db, vid, "rodada")
    assert tela("select radar_video_reconferir(%s, %s)", vid, FALA) == {"id": vid, "modo": None}
    assert video(db, vid, "situacao, ajustes, rodada") == ("pronto", bom, rodada) and conferir(pid) == []
    # o roteiro mudou: a fala nova tem de estar no roteiro novo; os ajustes por número saem, o estilo e o gancho ficam
    novo = ROTEIRO.replace("nem juros.", "nem juros, e fale com a gente.")
    db.execute("update radar_pauta_pecas set roteiro = %s where id = %s", (novo, pid))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR302"):
        tela("select radar_video_reconferir(%s, %s)", vid, FALA + " Fale com o fiscal.")
    assert tela("select radar_video_reconferir(%s, %s)", vid, FALA[:-1] + ", e fale com a gente.") == {"id": vid, "modo": "montagem"}
    assert video(db, vid, "ajustes, roteiro_hash = radar_hash_texto(%s)" % "'%s'" % novo.replace("'", "''")) == (
        {"estilo": "compacta", "sem_gancho": True}, True)
    # sem os clipes (prazo de guarda), nada volta ao corretor
    db.execute("update radar_videos set situacao = 'pronto', arquivos_apagados = '{bruto,trabalho}' where id = %s", (vid,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR311"):
        ajustar({})
    # sem a transcrição guardada, o ajuste é completo (transcreve de novo)
    db.execute("update radar_videos set arquivos_apagados = '{}', palavras_tentativa = null where id = %s", (vid,))
    assert ajustar({}) == {"id": vid, "modo": "completo"}
    assert tela("select radar_video_apaguei(%s)", vid) is not None
    primeiro = video(db, vid, "apagado_aparelho_em")
    tela("select radar_video_apaguei(%s)", vid, uid=ADMIN)
    assert video(db, vid, "apagado_aparelho_em, apagado_aparelho_por::text") == (primeiro, EDITOR)   # fica o primeiro registro
    assert tela("select radar_video_descartar(%s)", vid) is True
    assert video(db, vid, "situacao, encerrado_em is not null") == ("descartado", True)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR309"):
        tela("select radar_video_descartar(%s)", vid)


def test_termo_conferido_em_todo_o_caminho_do_processamento(corretor):
    """A pessoa só aparece com termo assinado: não basta conferir no envio e na aprovação. Revogado, vencido, inativa, menor ou quem fala
    desmarcada depois do envio: o robô não pega (erro "termo", antes de baixar os clipes e de mandar o áudio à Azure), e o ajuste,
    "Conferir com o roteiro novo", "Tentar de novo" e o fim do envio recusam (RADAR304)."""
    db = corretor
    pid, ana = reel(db)
    vid, _ = ate_pronto(db, pid, ana)
    db.execute("update radar_pessoas set termo_revogado_em = %s, menor = true where id = %s", (hoje(db), ana))
    for sql, args, uid in [("select radar_video_ajustar(%s, %s, null)", (vid, json.dumps({"estilo": "compacta"})), ADMIN),
                           ("select radar_video_reconferir(%s, %s)", (vid, FALA), EDITOR)]:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR304: uma pessoa da peça não pode aparecer no vídeo"):
            tela(sql, *args, uid=uid)
    db.execute("update radar_videos set situacao = 'erro', erro_codigo = 'storage' where id = %s", (vid,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR304"):
        tela("select radar_video_de_novo(%s)", vid)
    # o pedido que já estava na fila (o disparo do GitHub falhou e a reserva pega depois): erro "termo", e o robô não recebe nada
    for mudanca in ("termo_revogado_em = %(h)s", "termo_valido_ate = %(h)s::date - 1", "ativo = false", "menor = true",
                    "termo_corretor_em = null"):
        db.execute("update radar_pessoas set termo_revogado_em = null, menor = false, ativo = true, termo_valido_ate = null, "
                   "termo_corretor_em = '2020-01-01' where id = %(a)s", {"a": ana})
        db.execute(f"update radar_pessoas set {mudanca} where id = %(a)s", {"a": ana, "h": hoje(db)})
        db.execute("update radar_videos set situacao = 'na_fila', erro_codigo = null, fila_em = now() where id = %s", (vid,))
        assert pegar() is None and video(db, vid, "situacao, erro_codigo") == ("erro", "termo"), mudanca
    assert conferir(pid)[0] == "Reel: o corretor parou com erro (termo)"
    # quem fala desmarcada da peça
    db.execute("update radar_pessoas set termo_corretor_em = '2020-01-01' where id = %s", (ana,))
    bruno = pessoa_do_corretor(db, "Bruno Exemplo", "Bruno")
    mudar_por_fora(db, pid, f"pessoas = '{{{bruno}}}'")
    db.execute("update radar_videos set situacao = 'na_fila', erro_codigo = null, fila_em = now() where id = %s", (vid,))
    assert pegar() is None and video(db, vid, "situacao, erro_codigo") == ("erro", "termo")
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR304: quem fala não está mais marcada na peça"):
        tela("select radar_video_de_novo(%s)", vid)
    # o termo revogado durante o envio: os clipes chegam, mas o envio não vai para a fila
    outra, _ = reel(db, dias=6, pessoa=ana)
    novo = criar(outra, ana)["id"]
    db.execute("update radar_pessoas set termo_revogado_em = %s where id = %s", (hoje(db), ana))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR304"):
        tela("select radar_video_enviado(%s)", novo)
    assert video(db, novo, "situacao") == "aguardando_envio"
    # a limpeza da revogação passa com o robô no meio: o relatório (a fala) não volta, nenhum link novo sai; o áudio já mandado conta
    db.execute("update radar_pessoas set termo_revogado_em = null where id = %s", (ana,))
    tela("select radar_video_enviado(%s)", novo)
    t = pegar()["tentativa"]
    db.execute("update radar_videos set fala_roteiro = '', relatorio = '{}', cartela_linhas = '{}', arquivos_apagados = '{textos}' where id = %s", (novo,))
    for sql, args in [("select radar_video_parcial(%s, %s, %s)", (novo, t, json.dumps({"texto_final": FALA}))),
                      ("select radar_video_em_curso(%s, %s)", (novo, t))]:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR316: os clipes ou os textos deste pedido foram apagados"):
            robo(sql, *args)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR316"):
        concluir(novo, t)
    assert video(db, novo, "relatorio, fala_roteiro, sha256") == ({}, "", None)
    robo("select radar_video_registrar_audio(%s, %s, %s::numeric, %s)", novo, t, 12.5, False)
    assert video(db, novo, "segundos_audio") == 12.5


def test_desmarcar_quem_aparece_nao_tira_a_pessoa_do_video(corretor):
    """Ana Teste fala e Bruno Exemplo aparece, os dois com o termo. Bruno revoga o termo e o administrador, seguindo o LEIAME de antes,
    desmarca Bruno na peça: o vídeo continua sendo o dele — a pendência continua recusando, a prévia fecha, o robô não pega o pedido
    num "Tentar de novo", e a limpeza do dia seguinte leva os clipes, a transcrição, o vídeo corrigido e os textos (não espera o prazo
    de guarda)."""
    db = corretor
    ana = pessoa_do_corretor(db)
    bruno = pessoa_do_corretor(db, "Bruno Exemplo", "Bruno")
    pid, _ = reel(db, pessoa=ana, pessoas=[ana, bruno])
    vid, _ = ate_pronto(db, pid, ana)
    assert video(db, vid, "pessoas") == sorted([ana, bruno]) and conferir(pid) == []
    assert tela("select radar_video_para_previa(%s)", vid)["sha256"] == SHA_VIDEO
    db.execute("update radar_pessoas set termo_revogado_em = %s where id = %s", (hoje(db), bruno))
    recusa = ("Reel: uma pessoa da peça não pode aparecer no vídeo (termo revogado no Instagram): confira em Pauta → Pessoas e termos")
    assert recusa in conferir(pid)
    mudar_por_fora(db, pid, f"pessoas = '{{{ana}}}'")                                       # desmarcado na peça
    assert recusa in conferir(pid)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR304: uma pessoa da peça não pode aparecer no vídeo"):
        tela("select radar_video_para_previa(%s)", vid)
    db.execute("update radar_videos set situacao = 'erro', erro_codigo = 'storage' where id = %s", (vid,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR304"):
        tela("select radar_video_de_novo(%s)", vid)
    db.execute("update radar_videos set situacao = 'na_fila', erro_codigo = null, fila_em = now() where id = %s", (vid,))
    assert pegar() is None and video(db, vid, "situacao, erro_codigo") == ("erro", "termo")
    r = robo("select radar_video_limpeza()")
    assert {i["id"]: sorted(i["apagar"]) for i in r["itens"]} == {vid: ["bruto", "corrigido", "trabalho"]} and r["textos"] == 1
    assert video(db, vid, "fala_roteiro, relatorio, arquivos_apagados") == ("", {}, ["textos"])
    # as pessoas do vídeo: as marcadas no envio (Bruno, desmarcado enquanto os clipes subiam) e as marcadas quando os clipes chegaram
    db.execute("update radar_pessoas set termo_revogado_em = null where id = %s", (bruno,))
    carla = pessoa_do_corretor(db, "Carla Modelo", "Carla")
    outra, _ = reel(db, dias=6, pessoa=ana, pessoas=[ana, bruno])
    v2 = criar(outra, ana)["id"]
    mudar_por_fora(db, outra, f"pessoas = '{{{ana},{carla}}}'")
    tela("select radar_video_enviado(%s)", v2)
    assert video(db, v2, "pessoas") == sorted([ana, bruno, carla])


def test_pessoa_do_video_nao_se_apaga_e_a_apagada_conta_como_revogada(corretor):
    """Varredura geral (v0.22.0): desmarcada na peça, a pessoa continua no vídeo enviado. Apagar o cadastro dela não dá enquanto o
    vídeo guarda arquivos ou textos (RADAR174: o caminho é a revogação); e a apagada antes desta trava conta como revogada na
    limpeza (antes, o "exists" sobre radar_pessoas dava falso e os clipes dela esperavam o prazo de guarda)."""
    db = corretor
    ana = pessoa_do_corretor(db)
    bruno = pessoa_do_corretor(db, "Bruno Exemplo", "Bruno")
    pid, _ = reel(db, pessoa=ana, pessoas=[ana, bruno])
    vid, _ = ate_pronto(db, pid, ana)
    mudar_por_fora(db, pid, f"pessoas = '{{{ana}}}'")                                       # desmarcado na peça
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR174: esta pessoa está num vídeo do corretor"):
        c.execute("delete from radar_pessoas where id = %s", (bruno,))
    assert robo("select radar_video_limpeza()")["itens"] == []                              # dentro do prazo e ninguém revogou
    # apagada sem passar pela trava (como numa instalação de antes dela): a limpeza seguinte leva os arquivos e os textos
    db.execute("set session_replication_role = replica")
    try:
        db.execute("delete from radar_pessoas where id = %s", (bruno,))
    finally:
        db.execute("set session_replication_role = origin")
    r = robo("select radar_video_limpeza()")
    assert {i["id"]: sorted(i["apagar"]) for i in r["itens"]} == {vid: ["bruto", "corrigido", "trabalho"]} and r["textos"] == 1
    # com tudo apagado, o cadastro de quem estava só nesse vídeo pode sair
    robo("select radar_video_limpo(%s, %s)", vid, ["bruto", "trabalho", "corrigido"])
    carla = pessoa_do_corretor(db, "Carla Modelo", "Carla")
    db.execute("update radar_videos set pessoas = pessoas || %s::bigint where id = %s", (carla, vid))
    with como("authenticated", ADMIN) as c:
        assert c.execute("delete from radar_pessoas where id = %s", (carla,)).rowcount == 1


@pytest.mark.parametrize("mudanca, motivo", [
    ("termo_corretor_em = null", "sem o termo novo, que cita o corretor de vídeo"),             # retirou a autorização do corretor
    ("termo_corretor_em = %(h)s::date + 3", "sem o termo novo, que cita o corretor de vídeo"),
    ("menor = true", "menor de idade: o corretor de vídeo não aceita nesta versão"),
    ("termo_revogado_em = %(h)s", "termo revogado no Instagram")])
def test_previa_e_limpeza_param_quando_a_pessoa_nao_pode_mais_estar_no_video(corretor, mudanca, motivo):
    """O termo do corretor retirado (ou com data no futuro), a pessoa marcada menor de idade e o termo revogado: o processamento já
    parava (radar_video_pessoa_falta); agora a prévia também fecha na hora (o editor não recebe mais o link de 600 s do vídeo da pessoa)
    e a limpeza seguinte leva os arquivos e os textos, em vez de esperar o prazo de guarda (30 a 120 dias)."""
    db = corretor
    pid, ana = reel(db)
    vid, _ = ate_pronto(db, pid, ana)
    db.execute(f"update radar_pessoas set {mudanca} where id = %(a)s", {"a": ana, "h": hoje(db)})
    with pytest.raises(psycopg.errors.RaiseException, match=re.escape(f"RADAR304: uma pessoa da peça não pode aparecer no vídeo ({motivo}")):
        tela("select radar_video_para_previa(%s)", vid)
    assert db.execute("select count(*) from radar_video_acessos where video_id = %s", (vid,)).fetchone()[0] == 0
    r = robo("select radar_video_limpeza()")
    assert {i["id"]: sorted(i["apagar"]) for i in r["itens"]} == {vid: ["bruto", "corrigido", "trabalho"]} and r["textos"] == 1
    # o termo de imagem só vencido (pode ser renovado) para o processamento, mas não apaga nada
    pid2, _ = reel(db, dias=6, pessoa=pessoa_do_corretor(db, "Bruno Exemplo", "Bruno"))
    v2, _ = ate_pronto(db, pid2, db.execute("select pessoas[1] from radar_pauta_pecas where id = %s", (pid2,)).fetchone()[0])
    db.execute("update radar_pessoas set termo_valido_ate = %s::date - 1 where id = (select pessoas[1] from radar_pauta_pecas where id = %s)",
               (hoje(db), pid2))
    assert v2 not in {i["id"] for i in robo("select radar_video_limpeza()")["itens"]}


def test_gancho_e_texto_extra_da_cartela_conferidos_como_estao_no_video(corretor):
    """O texto do gancho gravado de 0 a 3 s é a cópia da chamada no envio, e o texto extra da cartela é o das Configurações na hora da
    montagem (o robô grava no relatório). A trava confere o que está NO VÍDEO — e não a chamada ou as Configurações de hoje —, e a
    pendência pede o vídeo em dia quando um dos dois muda depois."""
    db = corretor
    pid, ana = reel(db, chamada="O prazo do Simples vence no dia 20, com multa de R$ 300")
    bruno = pessoa_do_corretor(db, "Bruno Exemplo", "Bruno")
    vid = na_fila(db, pid, ana, gancho=True)
    t = pegar()["tentativa"]
    robo("select radar_video_registrar_audio(%s, %s, %s::numeric, %s)", vid, t, 31.5, True)
    concluir(vid, t, relatorio={**RELATORIO, "cartela_extra": ""})
    assert video(db, vid, "gancho") == "O prazo do Simples vence no dia 20, com multa de R$ 300"
    numero = lambda: [x for x in conferir(pid) if x.startswith("Números que não estão nas informações conferidas")]
    assert numero() and ": 300." in numero()[0]
    # a chamada reescrita na peça: o vídeo continua com o gancho de antes — a pendência pede o vídeo em dia, e o número do gancho gravado
    # continua travando
    db.execute("update radar_pauta_pecas set chamada = 'O prazo do Simples vence no dia 20' where id = %s", (pid,))
    assert ("Reel: o texto do gancho mudou depois da gravação (o vídeo tem o de antes): o administrador marca “Sem o texto do gancho” nos "
            "ajustes, ou envie a gravação de novo") in conferir(pid)
    assert numero() and ": 300." in numero()[0]
    db.execute("""update radar_videos set ajustes = '{"sem_gancho": true}' where id = %s""", (vid,))          # montado sem o gancho
    assert conferir(pid) == []
    # o texto extra da cartela: o gravado (no relatório) passa pelas travas; mudado nas Configurações depois, a cartela é refeita
    db.execute("""update radar_videos set relatorio = relatorio || '{"cartela_extra": "Atendimento com o Bruno"}' where id = %s""", (vid,))
    assert conferir(pid) == ["Reel: o texto extra da cartela mudou nas Configurações depois da montagem: o administrador marca “Refazer a "
                             "cartela” nos ajustes (o vídeo é montado de novo)",
                             "“Bruno” aparece no texto e não está marcada em Quem aparece"]
    config(db, cartela_extra="Atendimento com o Bruno")
    assert conferir(pid) == ["“Bruno” aparece no texto e não está marcada em Quem aparece"]
    config(db, cartela_extra="Fale com a gente")                    # as Configurações de hoje não escondem o que está gravado
    assert "“Bruno” aparece no texto e não está marcada em Quem aparece" in conferir(pid)
    db.execute("""update radar_videos set relatorio = relatorio || '{"cartela_extra": "Fale com a gente"}' where id = %s""", (vid,))
    assert conferir(pid) == [] and bruno


def test_envio_novo_so_substitui_o_video_vivo_quando_os_clipes_chegam(corretor):
    """O envio novo não leva o vídeo bom junto: o vivo continua até os clipes do novo chegarem (radar_video_enviado). O envio
    abandonado, ou que falhou no armazenamento, deixa o vídeo anterior como estava."""
    db = corretor
    pid, ana = reel(db)
    v1, _ = ate_pronto(db, pid, ana)
    assert conferir(pid) == []
    v2 = criar(pid, ana)["id"]
    assert video(db, v1, "situacao") == "pronto" and video(db, v2, "situacao") == "aguardando_envio"
    # com a gravação nova a caminho, o vídeo anterior não é aprovado por engano: termine o envio ou descarte-o
    assert conferir(pid) == ["Reel: termine de enviar a gravação (Corretor de vídeo)"]
    # outro envio no lugar do que esperava: só o que esperava os arquivos sai
    v3 = criar(pid, ana)["id"]
    assert [video(db, v, "situacao") for v in (v1, v2, v3)] == ["pronto", "substituido", "aguardando_envio"]
    # desistiu (descartar): o vídeo pronto continua valendo
    assert tela("select radar_video_descartar(%s)", v3) is True
    assert video(db, v1, "situacao") == "pronto" and conferir(pid) == []
    # a peça cancelada (ou aprovada) durante o envio: os clipes chegam, mas o envio não entra na fila
    outra, _ = reel(db, dias=6, pessoa=ana)
    w1, _ = ate_pronto(db, outra, ana)
    w2 = criar(outra, ana)["id"]
    mudar_por_fora(db, outra, "situacao = 'cancelada'")
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR301: a peça está cancelada"):
        tela("select radar_video_enviado(%s)", w2)
    mudar_por_fora(db, outra, "situacao = 'aprovada'")
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR301: a peça foi aprovada durante o envio"):
        tela("select radar_video_enviado(%s)", w2)
    assert video(db, w1, "situacao") == "pronto" and video(db, w2, "situacao") == "aguardando_envio"
    # os clipes chegam: só agora o anterior vira "substituido"
    v4 = criar(pid, ana)["id"]
    assert tela("select radar_video_enviado(%s)", v4) == {"id": v4, "situacao": "na_fila"}
    assert video(db, v1, "situacao, encerrado_em is not null") == ("substituido", True) and video(db, v4, "situacao") == "na_fila"


def test_audio_conta_uma_vez_por_rodada_e_o_robo_pode_repetir(corretor):
    db = corretor
    pid, ana = reel(db)
    vid = na_fila(db, pid, ana)
    t = pegar()["tentativa"]
    for _ in range(3):                                                                         # o robô repete a chamada que falhou no caminho
        assert robo("select radar_video_registrar_audio(%s, %s, %s::numeric, %s)", vid, t, 31.5, True) == {"restante_s": 1768.5}
    assert video(db, vid, "segundos_audio, audio_rodada, palavras_tentativa") == (31.5, t, t)
    # outra rodada completa (sem a transcrição guardada, transcreve de novo): soma
    db.execute("update radar_videos set situacao = 'na_fila', palavras_tentativa = null, modo = 'completo' where id = %s", (vid,))
    t2 = pegar()["tentativa"]
    robo("select radar_video_registrar_audio(%s, %s, %s::numeric, %s)", vid, t2, 10, False)
    robo("select radar_video_registrar_audio(%s, %s, %s::numeric, %s)", vid, t2, 10, False)
    assert video(db, vid, "segundos_audio, audio_rodada") == (41.5, t2)


def test_reserva_da_agenda_para_no_3o_acionamento_sem_o_robo_pegar(corretor):
    """A reserva (radar_video_reserva, de 10 em 10 minutos) aciona só com pedido esperando há 3 minutos, nunca enquanto o robô trabalha
    num pedido, e conta os acionamentos no pedido: no 3º sem o robô pegar, erro "robo_nao_pegou" e a reserva para. O robô pegar, o
    "Tentar de novo" e a volta à fila zeram a conta."""
    db = corretor
    reserva = lambda: db.execute("select radar_video_reserva()").fetchone()[0]
    pid, ana = reel(db)
    vid = na_fila(db, pid, ana)
    assert reserva() is False and video(db, vid, "reservas") == 0                          # na fila há menos de 3 minutos: a tela acionou
    db.execute("update radar_videos set fila_em = now() - interval '4 minutes' where id = %s", (vid,))
    trilha = lambda: db.execute("select count(*) from radar_auditoria where tabela = 'radar_videos'").fetchone()[0]
    antes = trilha()
    assert [reserva() for _ in range(3)] == [True, True, True] and video(db, vid, "reservas") == 3
    assert trilha() == antes                                                                 # a conta da reserva não vai à trilha
    assert reserva() is False and video(db, vid, "situacao, erro_codigo") == ("erro", "robo_nao_pegou")
    assert conferir(pid) == ["Reel: o corretor parou com erro (robo_nao_pegou)"]                # o aviso, na peça
    assert reserva() is False                                                                 # e a reserva parou
    # "Tentar de novo": a conta recomeça; o robô pega e zera de novo
    db.execute("update radar_videos set palavras_tentativa = 1 where id = %s", (vid,))
    tela("select radar_video_de_novo(%s)", vid)
    assert video(db, vid, "situacao, reservas") == ("na_fila", 0)
    db.execute("update radar_videos set fila_em = now() - interval '4 minutes' where id = %s", (vid,))
    assert reserva() is True and video(db, vid, "reservas") == 1
    t = pegar()["tentativa"]
    assert video(db, vid, "situacao, reservas") == ("processando", 0)
    # com o robô trabalhando (pegou há menos de 20 minutos), a reserva não aciona nem conta o pedido que espera atrás
    outra, _ = reel(db, dias=6, pessoa=ana)
    segundo = na_fila(db, outra, ana)
    db.execute("update radar_videos set fila_em = now() - interval '30 minutes' where id = %s", (segundo,))
    assert [reserva() for _ in range(4)] == [False] * 4 and video(db, segundo, "situacao, reservas") == ("na_fila", 0)
    # o falhar que devolve à fila zera a conta; o robô que caiu (parado há mais de 20 minutos) volta a contar
    assert robo("select radar_video_falhar(%s, %s, 'storage')", vid, t) == {"situacao": "na_fila"}
    assert video(db, vid, "reservas") == 0
    db.execute("update radar_videos set situacao = 'processando', pego_em = now() - interval '25 minutes' where id = %s", (vid,))
    assert reserva() is True and video(db, vid, "reservas") == 1 and video(db, segundo, "reservas") == 1


def test_concluir_com_frase_do_boletim_pago_pede_regravar_sem_mostrar_o_trecho(corretor, request):
    db = corretor
    carregar_fontes_novas(db, request)
    frase = "o comitê gestor publicou nesta semana a orientação completa sobre o novo prazo de entrega das declarações mensais"
    db.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo)
                  select id, 'https://boletim.exemplo/c', 'Boletim de mentira', %s, 'h-boletim-concluir' from radar_fontes where slug = 'itc-email'""",
               (frase,))
    pid, ana = reel(db)
    vid, t = ate_pronto(db, pid, ana, relatorio={**RELATORIO, "texto_final": FALA + " " + frase, "avisos": ["relatorio_resumido"]})
    assert video(db, vid, "situacao") == "regravar"
    assert video(db, vid, "relatorio")["avisos"] == ["relatorio_resumido", "boletim_pago"]
    probs = conferir(pid)
    assert "Reel: o vídeo precisa ser regravado (veja o relatório)" in probs
    assert "Há frase igual à do boletim pago (ITC): reescreva com palavras próprias" in probs and "comitê" not in json.dumps(probs, ensure_ascii=False)


def test_problemas_do_reel_conferem_a_fala_transcrita_e_a_cartela(corretor):
    """A fala que vai ao ar (o texto final da legenda gravada) e as linhas da cartela passam pelas travas de nome, número e contador."""
    db = corretor
    nova_pessoa(db, "Carla Modelo", "Carla")                                                  # cadastrada e não marcada
    pid, ana = reel(db)
    ate_pronto(db, pid, ana, relatorio={**RELATORIO, "texto_final": FALA + " Fale com a Carla, são 37 anos de casa."})
    assert conferir(pid) == ["Números que não estão nas informações conferidas: 37. Acrescente cada um em Informações conferidas, com a fonte (ou tire do texto)",
                             "“Carla” aparece no texto e não está marcada em Quem aparece"]
    # o texto extra da cartela (Configurações) também vai ao ar
    config(db, cartela_extra="Desde 1984 · artecon.cnt.br")
    assert any("1984" in p for p in conferir(pid))


def test_reel_aprovado_antes_da_v0_22_0_registra_o_link_sem_o_video(corretor):
    """O reel aprovado à mão na v0.21.0 (sem o corretor) e postado depois da atualização registra o link como antes: a recusa do registro
    sem o vídeo corrigido (RADAR317) vale só para a aprovação feita com a v0.22.0 (ou mais nova: v0.24.0, mesmo sem ter passado pela
    v0.22.0)."""
    db = corretor
    pid, ana = reel(db)
    ate_pronto(db, pid, ana)
    marcar_pronta(db, pid)
    aprovar_peca(db, pid, modo="manual", artes=[], conferencias=("pessoas", "video"), video=SHA_VIDEO)
    # v0.24.0: a primeira instalação da v0.22.0 ou mais nova (aqui, a da versão atual: quem pulou a v0.22.0 não tem a linha dela)
    instalada = db.execute(r"select min(executado_em) from radar_instalacoes where versao ~ '^v0\.(2[2-9]|[3-9][0-9])\.'").fetchone()[0]
    assert instalada is not None
    mudar_por_fora(db, pid, "video_sha256 = null, video_id = null")
    registrar = "select radar_pauta_registrar_manual(%s, 'https://www.instagram.com/reel/ABC123/', null, %s)"
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR317"):
        c.execute(registrar, (pid, hoje(db)))                                                # aprovado com a v0.22.0, sem o vídeo
    mudar_por_fora(db, pid, f"aprovado_em = '{instalada.isoformat()}'::timestamptz - interval '3 days'")
    with como("authenticated", EDITOR) as c:
        c.execute(registrar, (pid, hoje(db)))
    assert db.execute("select link_instagram, publicado_manual_em from radar_pauta_pecas where id = %s", (pid,)).fetchone() == (
        "https://www.instagram.com/reel/ABC123/", hoje(db))


def test_apaguei_o_video_aprovado_baixado_fica_registrado_a_parte(corretor):
    """"Apaguei do celular e da nuvem pessoal (depois de postar)", depois de baixar o vídeo aprovado: registra quem apagou o vídeo final,
    mesmo com os clipes já marcados como apagados no dia do envio."""
    db = corretor
    pid, ana = reel(db)
    vid, _ = ate_pronto(db, pid, ana)
    tela("select radar_video_apaguei(%s)", vid)                                              # os clipes, no dia do envio
    marcar_pronta(db, pid)
    aprovar_peca(db, pid, modo="manual", artes=[], conferencias=("pessoas", "video"), video=SHA_VIDEO)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR309: o vídeo aprovado não foi baixado por você"):
        tela("select radar_video_apaguei_baixado(%s)", vid, uid=ADMIN)
    assert tela("select radar_video_para_baixar(%s, %s)", pid, lido_peca(db, pid), uid=ADMIN)["ok"] is True
    em = tela("select radar_video_apaguei_baixado(%s)", vid, uid=ADMIN)
    acessos = db.execute("select acao, usuario::text, em from radar_video_acessos where video_id = %s order by id", (vid,)).fetchall()
    assert [(a, u) for a, u, _ in acessos] == [("baixar", ADMIN), ("apagou", ADMIN)] and acessos[-1][2] == em
    with como("authenticated", LEITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR300"):
        c.execute("select radar_video_apaguei_baixado(%s)", (vid,))


def test_trilha_do_video_sem_fala_cartela_relatorio_nem_ajustes(corretor):
    db = corretor
    bruno = pessoa_do_corretor(db, "Bruno Exemplo", "Bruno", categoria="contador", crc="CRC-SC 054321/O-1")
    pid, _ = reel(db, pessoa=bruno)
    vid = criar(pid, bruno, cartela=[IDENT, "Bruno, contador · CRC-SC 054321/O-1"])["id"]
    tela("select radar_video_enviado(%s)", vid)
    p = pegar()
    robo("select radar_video_parcial(%s, %s, %s)", vid, p["tentativa"], json.dumps({"texto_final": "Fala transcrita do Bruno"}))
    concluir(vid, p["tentativa"], relatorio={**RELATORIO, "texto_final": "Fala transcrita do Bruno"})
    tela("select radar_video_ajustar(%s, %s, null)", vid, json.dumps({"legenda": {"0": "Fala do Bruno"}}), uid=ADMIN)
    trilha = db.execute("select acao, antes, depois from radar_auditoria where tabela = 'radar_videos' order by id").fetchall()
    assert [a for a, *_ in trilha][:1] == ["INSERT"] and len(trilha) >= 4
    texto = json.dumps([x for _, a, d in trilha for x in (a, d)], ensure_ascii=False)
    for proibido in ("Bruno", "054321", "prazo do Simples", "Fala transcrita", "relatorio", "fala_roteiro", "cartela_linhas", "ajustes"):
        assert proibido not in texto, proibido
    assert [d["situacao"] for _, _, d in trilha] == ["aguardando_envio", "na_fila", "processando", "pronto", "na_fila"]
    # pegar de novo um parado (só as marcas do robô) não entra na trilha
    antes = len(trilha)
    db.execute("update radar_videos set fila_em = now() - interval '1 hour' where id = %s", (vid,))
    assert db.execute("select count(*) from radar_auditoria where tabela = 'radar_videos'").fetchone()[0] == antes


def test_limpeza_nos_prazos_de_guarda(corretor):
    db = corretor
    ana = pessoa_do_corretor(db)
    bruno = pessoa_do_corretor(db, "Bruno Exemplo", "Bruno")
    # 1. substituído (os clipes do envio novo chegaram): os arquivos agora; os textos depois de retencao_dias
    p1, _ = reel(db, dias=5, pessoa=ana)
    velho, _ = ate_pronto(db, p1, ana)
    novo = criar(p1, ana)["id"]                                     # (os clipes chegam lá embaixo, antes da limpeza: radar_video_enviado)
    # 2. publicado à mão: os clipes agora; o vídeo e os textos, retencao_publicado_dias depois
    p2, _ = reel(db, dias=6, pessoa=ana)
    pub, _ = ate_pronto(db, p2, ana)
    mudar_por_fora(db, p2, "publicado_manual_em = current_date - 2")
    # 3. pessoa da peça com o termo revogado: tudo, já
    p3, _ = reel(db, dias=7, pessoa=bruno)
    rev, _ = ate_pronto(db, p3, bruno)
    db.execute("update radar_pessoas set termo_revogado_em = %s where id = %s", (hoje(db), bruno))
    # 4. envio abandonado (esperando os arquivos há mais de 1 dia): vira descartado
    p4, _ = reel(db, dias=8, pessoa=ana)
    aband = criar(p4, ana)["id"]
    db.execute("update radar_videos set criado_em = now() - interval '2 days' where id = %s", (aband,))
    # 5. pronto com versões antigas do corrigido (ajuste): só as antigas
    p5, _ = reel(db, dias=9, pessoa=ana)
    atual, _ = ate_pronto(db, p5, ana)
    db.execute("update radar_videos set antigos = true where id = %s", (atual,))
    # 6. enviado há mais de retencao_dias e nunca publicado (peça cancelada, reel adiado): os clipes, o corrigido e os textos — nada
    #    fica para sempre
    p6, _ = reel(db, dias=10, pessoa=ana)
    antigo, _ = ate_pronto(db, p6, ana)
    db.execute("update radar_videos set enviado_em = now() - interval '31 days' where id = %s", (antigo,))
    # 7. aprovado e esperando o dia de postar (daqui a 40 dias), enviado há mais de retencao_dias: só os clipes; o vídeo aprovado e os
    #    textos ficam até retencao_dias depois do dia da peça
    p7, _ = reel(db, dias=40, pessoa=ana)
    aprovado, _ = ate_pronto(db, p7, ana)
    marcar_pronta(db, p7)
    aprovar_peca(db, p7, modo="manual", artes=[], conferencias=("pessoas", "video"), video=SHA_VIDEO)
    db.execute("update radar_videos set enviado_em = now() - interval '31 days' where id = %s", (aprovado,))
    assert video(db, velho, "situacao") == "pronto"                        # o envio novo esperando os arquivos não tira o vivo
    tela("select radar_video_enviado(%s)", novo)
    r = robo("select radar_video_limpeza()")
    itens = {i["id"]: (sorted(i["apagar"]), i["manter"]) for i in r["itens"]}
    assert itens == {velho: (["bruto", "corrigido", "trabalho"], None), pub: (["bruto", "trabalho"], None),
                     rev: (["bruto", "corrigido", "trabalho"], None), aband: (["bruto", "corrigido", "trabalho"], None),
                     atual: (["antigos"], SHA_VIDEO), antigo: (["bruto", "corrigido", "trabalho"], None),
                     aprovado: (["bruto", "trabalho"], None)}
    assert novo not in itens and r["textos"] == 2                                     # os textos da peça revogada e os do vídeo que venceu
    assert video(db, rev, "fala_roteiro, relatorio, ajustes, cartela_linhas, arquivos_apagados") == ("", {}, {}, [], ["textos"])
    assert video(db, antigo, "fala_roteiro, relatorio, cartela_linhas, arquivos_apagados") == ("", {}, [], ["textos"])
    assert video(db, aprovado, "length(fala_roteiro) > 0, arquivos_apagados") == (True, [])
    for vid, (grupos, _) in itens.items():
        assert robo("select radar_video_limpo(%s, %s::text[])", vid, grupos) is True
    assert video(db, aband, "situacao") == "descartado" and video(db, atual, "antigos, arquivos_apagados") == (False, [])
    assert video(db, pub, "arquivos_apagados") == ["bruto", "trabalho"]
    assert video(db, antigo, "arquivos_apagados") == ["bruto", "corrigido", "textos", "trabalho"]      # e sai do laço da limpeza
    assert robo("select radar_video_limpeza()") == {"itens": [], "textos": 0}                       # nada de novo
    assert tela("select radar_video_para_baixar(%s, %s)", p7, lido_peca(db, p7))["ok"] is True       # o vídeo aprovado continua lá
    # os prazos passam: os textos do substituído (retencao_dias) e o vídeo e os textos do publicado (retencao_publicado_dias)
    db.execute("update radar_videos set encerrado_em = now() - interval '31 days' where id = %s", (velho,))
    config(db, retencao_publicado_dias=1)
    r = robo("select radar_video_limpeza()")
    assert {i["id"]: i["apagar"] for i in r["itens"]} == {pub: ["corrigido"]} and r["textos"] == 2
    assert video(db, velho, "fala_roteiro, arquivos_apagados") == ("", ["bruto", "corrigido", "textos", "trabalho"])
    # o dia da peça aprovada passou há mais de retencao_dias e ela não saiu: o vídeo aprovado e os textos saem
    voltar_a_data(db, p7, 71)
    r = robo("select radar_video_limpeza()")
    assert {i["id"]: i["apagar"] for i in r["itens"]} == {pub: ["corrigido"], aprovado: ["corrigido"]} and r["textos"] == 1


def test_pecas_publicadas_da_pessoa_para_a_revogacao(corretor):
    db = corretor
    pid, ana = reel(db)
    outra, _ = reel(db, dias=6, pessoa=ana)
    ate_pronto(db, pid, ana)
    mudar_por_fora(db, pid, "publicado_manual_em = current_date, link_instagram = 'https://www.instagram.com/reel/ABC123/'")
    assert tela("select json_agg(x) from radar_pauta_pecas_da_pessoa(%s) x", ana, uid=ADMIN) == [
        {"peca": pid, "data": str(hoje(db) + timedelta(days=5)), "link_instagram": "https://www.instagram.com/reel/ABC123/", "link_facebook": None,
         "video_guardado": True}]
    assert outra and tela("select count(*) from radar_pauta_pecas_da_pessoa(%s)", nova_pessoa(db, "Bruno Exemplo", "Bruno"), uid=ADMIN) == 0
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR300"):
        c.execute("select * from radar_pauta_pecas_da_pessoa(%s)", (ana,))


def test_conferencia_das_chaves_do_robo_e_da_agenda_pelo_vault(db):
    with como("service_role") as c:
        assert c.execute("select radar_video_conferir_robo(%s)", ("a" * 64,)).fetchone()[0] is False      # sem Vault: nunca confere
    tinha = db.execute("select count(*) from pg_namespace where nspname = 'vault'").fetchone()[0] == 1
    if not tinha:
        db.execute(VAULT_SIMULADO)
    try:
        db.execute("insert into vault.secrets (name, secret) values ('radar_video_robo', %s), ('radar_video_agenda', %s), ('radar_redes_agenda', %s)",
                   ("r" * 64, "g" * 64, "f" * 64))
        with como("service_role") as c:
            robo_ = [c.execute("select radar_video_conferir_robo(%s)", (k,)).fetchone()[0] for k in ("r" * 64, "g" * 64, "f" * 64, "r" * 31, None)]
            agenda = [c.execute("select radar_video_conferir_agenda(%s)", (k,)).fetchone()[0] for k in ("g" * 64, "r" * 64, "f" * 64)]
        assert robo_ == [True, False, False, False, False] and agenda == [True, False, False]   # cada chave só vale para o seu lugar
        # a comparação é pelos resumos (sha256): o tempo não diz quanto do começo da chave confere
        for nome in ("radar_video_conferir_robo", "radar_video_conferir_agenda"):
            src = db.execute("select prosrc from pg_proc where proname = %s", (nome,)).fetchone()[0]
            assert "v_certa = p_chave" not in src and "sha256(convert_to(v_certa, 'UTF8')) = sha256(convert_to(p_chave, 'UTF8'))" in src, nome
        for papel, uid in (("authenticated", ADMIN), ("anon", None)):
            with como(papel, uid) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute("select radar_video_conferir_robo('x')")
    finally:
        if tinha:
            db.execute("delete from vault.secrets where name in ('radar_video_robo', 'radar_video_agenda', 'radar_redes_agenda')")
        else:
            db.execute("drop schema vault cascade")


def test_socio_grava_sem_os_termos_e_continua_com_ativa_menor_e_declaracoes(corretor):
    """v0.28.0: o(a) sócio(a) da Artecon (radar_pessoas.socio), maior de idade e ativo(a), grava o reel sem o termo de uso de imagem e sem
    o termo do corretor: o envio, o robô, a pendência e a prévia passam, e a limpeza não apaga o vídeo dele(a) antes do prazo (nem com
    "Revogado em" preenchido: para sócio(a), quem tira é "Ativa"). As quatro declarações continuam obrigatórias; menor de idade e pessoa
    inativa continuam recusados; tirar a marca faz o vídeo parar (RADAR304) e a limpeza seguinte apagar os arquivos e os textos."""
    db = corretor
    bruno = nova_pessoa(db, "Bruno Exemplo", "Bruno", assinado=None, canais=(), usos=())
    db.execute("update radar_pessoas set socio = true where id = %s", (bruno,))
    assert db.execute("select termo_assinado_em, termo_corretor_em from radar_pessoas where id = %s", (bruno,)).fetchone() == (None, None)
    pid, _ = reel(db, pessoa=bruno)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR307: marque as quatro declarações"):
        criar(pid, bruno, decl=DECL[:3])
    assert db.execute("select count(*) from radar_videos where peca_id = %s", (pid,)).fetchone()[0] == 0
    vid, _ = ate_pronto(db, pid, bruno)
    assert db.execute("select radar_video_pendencia(%s)", (pid,)).fetchone()[0] is None and conferir(pid) == []
    assert tela("select radar_video_para_previa(%s)", vid)["sha256"] == SHA_VIDEO
    limpeza = lambda: {i["id"]: sorted(i["apagar"]) for i in robo("select radar_video_limpeza()")["itens"]}
    assert vid not in limpeza()
    db.execute("update radar_pessoas set termo_revogado_em = %s where id = %s", (hoje(db), bruno))
    assert vid not in limpeza() and tela("select radar_video_para_previa(%s)", vid)["sha256"] == SHA_VIDEO
    for mudanca, motivo in [("menor = true", "menor de idade: o corretor de vídeo não aceita nesta versão"),
                            ("ativo = false", "pessoa inativa no Instagram")]:
        db.execute(f"update radar_pessoas set {mudanca} where id = %s", (bruno,))
        with pytest.raises(psycopg.errors.RaiseException, match=re.escape(f"RADAR304: uma pessoa da peça não pode aparecer no vídeo ({motivo})")):
            tela("select radar_video_para_previa(%s)", vid)
        db.execute("update radar_pessoas set menor = false, ativo = true where id = %s", (bruno,))
    # sem a marca: os termos voltam a ser pedidos, a prévia fecha e a limpeza seguinte leva os arquivos e os textos
    db.execute("update radar_pessoas set socio = false where id = %s", (bruno,))
    with pytest.raises(psycopg.errors.RaiseException,
                       match=re.escape("RADAR304: uma pessoa da peça não pode aparecer no vídeo (sem o termo novo, que cita o corretor de vídeo")):
        tela("select radar_video_para_previa(%s)", vid)
    r = robo("select radar_video_limpeza()")
    assert {i["id"]: sorted(i["apagar"]) for i in r["itens"]} == {vid: ["bruto", "corrigido", "trabalho"]} and r["textos"] == 1
    assert video(db, vid, "fala_roteiro, arquivos_apagados") == ("", ["textos"])


def test_funcoes_do_video_sem_current_date_com_caminho_e_configuracao_inicial(db):
    funcoes = db.execute("""select p.proname, p.prosrc, p.proconfig from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                            where n.nspname = 'public' and (p.proname like 'radar\\_video\\_%' or p.proname = 'radar_pauta_pecas_da_pessoa')""").fetchall()
    assert len(funcoes) == 46                                    # v0.22.0: + radar_video_cota; v0.33.0: + as 4 do editor; v0.36.0: + criar_avulso e baixar_avulso
    assert [n for n, src, _ in funcoes if "current_date" in src.lower()] == []                    # "hoje" é o de Brasília
    assert [n for n, _, cfg in funcoes if not cfg] == []
    cfg = db.execute("select valor from radar_config where chave = 'corretor_video'").fetchone()[0]
    assert cfg["limite_min_mes"] == 30 and cfg["retencao_dias"] == 30 and cfg["cartela_extra"] == "" and len(cfg["glossario"]) == 15


# ------------------------------------------------------------------ v0.33.0: a aba Vídeo (o editor do vídeo corrigido)
# O "mapa" que o robô da v0.33.0 grava no relatório (robo/video/cortes.py): a linha original (os clipes em sequência, em quadros de
# 1/30 s), a faixa de cada clipe (do 1º ao último som, com as folgas), os cortes automáticos no meio da fala (pela chave) e os trechos
# deste vídeo e as palavras ([ini, fim] em ms da linha original: a última de cada faixa termina 0,45 s antes do fim dela). Aqui: 570 + 550
# quadros nas faixas, menos 30 + 60 dos automáticos = 1030 quadros (34,33 s), sem pad (o fim da faixa já tem a folga depois da última
# palavra) → 34,33 + 3 − 0,4 = 36,9 s
MAPA = {"fps": 30, "linha_q": 1200, "faixas": [[30, 600], [630, 1180]],
        "automaticos": [{"chave": "1:282", "de": 282, "ate": 312}, {"chave": "2:900", "de": 900, "ate": 960}],
        "trechos": [[30, 282], [312, 600], [630, 900], [960, 1180]], "pad_q": 0,
        "palavras": [[1120, 4000], [4200, 9300], [10500, 15000], [15200, 19550], [21120, 29900], [32100, 35000], [35200, 38883]]}
EDICAO = {"versao": 1, "cortes": 0, "inicio_cortado_s": 0, "fim_cortado_s": 0, "tamanho": "M", "posicao": "baixo", "cor": "marinho",
          "cartela_extra_propria": False}
REL_MAPA = {**RELATORIO, "mapa": MAPA, "edicao": EDICAO, "cartela_extra": ""}
EDITAR = "select radar_video_editar(%s, %s, %s, %s::text[], %s)"
CHAVES_EDITOR = ("cortar", "inicio_q", "fim_q", "capa_q", "legenda_tamanho", "legenda_posicao", "legenda_cor", "cartela_extra")


def editar(vid, ajustes, sha=SHA_VIDEO, cartela=None, gancho=None, uid=ADMIN):
    return tela(EDITAR, vid, sha, json.dumps(ajustes), cartela, gancho, uid=uid)


def pronto_com_mapa(db, relatorio=None, **campos):
    """Peça reel com o vídeo pronto, montado pelo robô desta versão (o relatório com o mapa) e a transcrição guardada."""
    pid, ana = reel(db, **campos)
    vid, _ = ate_pronto(db, pid, ana, relatorio=relatorio or REL_MAPA)
    return pid, ana, vid


def montado(vid, relatorio=None, sha=SHA2):
    """O robô pega o pedido da fila (montagem) e conclui com o relatório do robô desta versão (com a "edicao")."""
    p = pegar()
    assert p["id"] == vid and p["modo"] == "montagem"
    return concluir(vid, p["tentativa"], relatorio=relatorio or REL_MAPA, sha=sha)["situacao"]


def _contraste(a: str, b: str) -> float:
    def lum(h):
        c = [int(h.lstrip("#")[k:k + 2], 16) / 255 for k in (0, 2, 4)]
        c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    claro, escuro = sorted((lum(a), lum(b)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


def test_paleta_da_edicao_igual_no_banco_no_robo_e_contraste(corretor):
    """A paleta da legenda é uma só: a função do banco (que a tela lê e o banco usa para conferir) e a tabela do robô (legenda.py) são
    iguais; toda cor tem contraste de leitura (WCAG AA, 4,5 ou mais) entre o texto e a caixa. Sem dado de ninguém: o leitor lê também."""
    sys.path.insert(0, str(RAIZ / "robo" / "video"))
    import legenda
    pal = tela("select radar_video_paleta()", uid=LEITOR)
    assert {c["chave"]: (c["texto"].lstrip("#"), c["caixa"].lstrip("#")) for c in pal["cores"]} == legenda.CORES
    assert {t["chave"]: t["fator"] for t in pal["tamanhos"]} == legenda.TAMANHOS
    assert tuple(p["chave"] for p in pal["posicoes"]) == legenda.POSICOES
    assert [c["chave"] for c in pal["cores"]][0] == "marinho" and pal["duracao_max_s"] == 900 and pal["fps"] == 30
    for c in pal["cores"]:
        assert re.fullmatch(r"#[0-9A-F]{6}", c["texto"]) and re.fullmatch(r"#[0-9A-F]{6}", c["caixa"])
        assert _contraste(c["texto"], c["caixa"]) >= 4.5, c
    with como("anon") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("select radar_video_paleta()")
    for funcao in ("radar_video_edicao_falta(radar_videos, jsonb)", "radar_video_edicao_duracao(radar_videos, jsonb)"):
        assert db_privilegio(corretor, funcao) == (False, False)                                # só o dono
    assert db_privilegio(corretor, "radar_video_editar(uuid, text, jsonb, text[], text)") == (False, True)


def db_privilegio(db, funcao):
    return db.execute(f"select has_function_privilege('anon', 'public.{funcao}'::regprocedure, 'execute'), "
                      f"has_function_privilege('authenticated', 'public.{funcao}'::regprocedure, 'execute')").fetchone()


def test_editar_so_o_administrador_no_video_que_ele_viu_sem_transcrever(corretor):
    db = corretor
    pid, ana, vid = pronto_com_mapa(db)
    for uid in (EDITOR, LEITOR):
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR300: só o administrador edita"):
            editar(vid, {"legenda_cor": "azul"}, uid=uid)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR318"):                       # outro vídeo que o que a tela mostrou
        editar(vid, {"legenda_cor": "azul"}, sha="c" * 64)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR318"):
        editar(vid, {"legenda_cor": "azul"}, sha=None)
    db.execute("update radar_videos set palavras_tentativa = null where id = %s", (vid,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR319: a transcrição desta gravação não ficou guardada"):
        editar(vid, {"legenda_cor": "azul"})
    db.execute("update radar_videos set palavras_tentativa = 1, situacao = 'na_fila' where id = %s", (vid,))
    with pytest.raises(psycopg.errors.RaiseException, match=r"RADAR309: só o vídeo pronto ou para regravar se edita \(situação atual: na_fila\)"):
        editar(vid, {"legenda_cor": "azul"})
    db.execute("update radar_videos set situacao = 'erro', erro_codigo = 'storage' where id = %s", (vid,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR309"):                       # com erro: "Tentar de novo" antes
        editar(vid, {"legenda_cor": "azul"})
    db.execute("update radar_videos set situacao = 'pronto', erro_codigo = null where id = %s", (vid,))
    antes = video(db, vid, "rodada")
    assert editar(vid, {"legenda_cor": "azul"}) == {"id": vid, "modo": "montagem", "duracao_s": 36.9}
    assert video(db, vid, "situacao, modo, tentativas, erro_codigo, ajustes, rodada") == ("na_fila", "montagem", 0, None, {"legenda_cor": "azul"}, antes)
    # montar de novo não transcreve: com a cota do mês esgotada, o robô pega do mesmo jeito (só a montagem)
    config(db, limite_min_mes=1)
    db.execute("update radar_videos set segundos_audio = 600 where id = %s", (vid,))
    p = pegar()
    assert (p["id"], p["modo"], p["palavras_tentativa"], p["ajustes"]) == (vid, "montagem", 1, {"legenda_cor": "azul"})
    concluir(vid, p["tentativa"], relatorio=REL_MAPA, sha=SHA2)
    assert video(db, vid, "situacao, sha256, segundos_audio") == ("pronto", SHA2, 600.0)
    # a peça cancelada ou aprovada não se edita
    mudar_por_fora(db, pid, "situacao = 'cancelada'")
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR301: a peça está cancelada"):
        editar(vid, {}, sha=SHA2)
    mudar_por_fora(db, pid, "situacao = 'em_producao'")
    marcar_pronta(db, pid)
    aprovar_peca(db, pid, modo="manual", artes=[], conferencias=("pessoas", "video"), video=SHA2)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR301: a peça está aprovada"):
        editar(vid, {}, sha=SHA2)


def test_editar_confere_cortes_comeco_fim_e_capa_na_linha_original(corretor):
    db = corretor
    pid, ana, vid = pronto_com_mapa(db)
    recusas = [({"cortar": [[1.5, 10]]}, "cortar: até 30 trechos"), ({"cortar": [[10, 10]]}, "cortar: até 30"), ({"cortar": [[20, 10]]}, "cortar: até 30"),
               ({"cortar": [[10, 12]]}, "cortar: até 30"), ({"cortar": [[k * 10, k * 10 + 5] for k in range(31)]}, "cortar: até 30"),
               ({"cortar": [[-5, 10]]}, "cortar: até 30"), ({"cortar": [["1", "9"]]}, "cortar: até 30"), ({"cortar": {"0": [1, 9]}}, "cortar: até 30"),
               ({"cortar": [[100, 200], [150, 250]]}, "o corte nº 2 está fora do vídeo, tem menos de 0,1 s ou passa por cima de outro"),
               ({"cortar": [[300, 400], [100, 200]]}, "o corte nº 2 está fora"), ({"cortar": [[1100, 1250]]}, "o corte nº 1 está fora do vídeo"),
               ({"inicio_q": 29001}, "inicio_q: um quadro do vídeo"), ({"fim_q": 2.5}, "fim_q: um quadro"), ({"capa_q": "30"}, "capa_q: um quadro"),
               ({"inicio_q": 1300}, "o começo ou o fim marcado está fora do vídeo"),
               ({"inicio_q": 500, "fim_q": 510}, "o começo marcado tem de vir pelo menos 1 s antes do fim marcado"),
               ({"inicio_q": 500, "fim_q": 400}, "pelo menos 1 s antes"),
               ({"capa_q": 290}, "a capa caiu num trecho cortado"), ({"capa_q": 610}, "a capa caiu"), ({"capa_q": 5}, "a capa caiu"),
               ({"cortar": [[400, 450]], "capa_q": 420}, "a capa caiu"), ({"inicio_q": 100, "capa_q": 90}, "a capa caiu"),
               ({"fim_q": 900, "capa_q": 900}, "a capa caiu")]
    for ajustes, msg in recusas:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR310: .*" + re.escape(msg)):
            editar(vid, ajustes)
    assert video(db, vid, "situacao, ajustes") == ("pronto", {})
    # o corte automático mantido ("Manter este trecho") volta ao vídeo: a capa pode cair nele
    bom = {"manter": ["1:282"], "cortar": [[100, 200], [400, 450]], "inicio_q": 60, "fim_q": 1150, "capa_q": 290}
    assert editar(vid, bom)["modo"] == "montagem"
    assert video(db, vid, "ajustes") == bom
    # o vídeo do robô de antes (sem o mapa): os cortes e a capa esperam a montagem desta versão; o estilo, não
    db.execute("update radar_videos set situacao = 'pronto' where id = %s", (vid,))
    pid2, ana2 = reel(db, dias=6, pessoa=pessoa_do_corretor(db, "Bruno Exemplo", "Bruno"))
    vid2, _ = ate_pronto(db, pid2, ana2)
    for ajustes in ({"cortar": [[100, 200]]}, {"capa_q": 100}, {"inicio_q": 40}, {"fim_q": 900}):
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR310: os cortes e a capa precisam do vídeo montado pelo robô desta versão"):
            editar(vid2, ajustes)
    assert editar(vid2, {"legenda_tamanho": "G", "legenda_posicao": "cima", "legenda_cor": "amarelo"}) == {"id": vid2, "modo": "montagem", "duracao_s": None}
    db.execute("update radar_videos set situacao = 'pronto' where id = %s", (vid2,))
    assert editar(vid2, {})["modo"] == "montagem"                                               # "Montar de novo para liberar os cortes e a capa"


def test_editar_duracao_estimada_entre_5_s_e_15_min_e_fala_de_2_s(corretor):
    """A duração depois de montar segue o plano do robô: a fala que fica MAIS o pad do fim (o último quadro parado: o vídeo precisa de
    0,45 s depois da última palavra que fica). Sem o fim marcado, a faixa já tem essa folga (pad 0: nada de somar 0,45 s a mais, que
    deixaria passar um vídeo abaixo de 5 s); o fim no meio de uma palavra pede o pad inteiro (14 quadros); perto do fim dela, o que falta."""
    db = corretor
    mapa = {"fps": 30, "linha_q": 1500, "faixas": [[0, 1300]], "automaticos": [{"chave": "1:500", "de": 500, "ate": 800}],
            "trechos": [[0, 500], [800, 1300]], "pad_q": 0, "palavras": [[100, 16500], [27000, 42883]]}    # quadros 3–495 e 810–1286,5
    pid, ana, vid = pronto_com_mapa(db, relatorio={**REL_MAPA, "mapa": mapa})
    dur = lambda a: db.execute("select radar_video_edicao_duracao(v, %s) from radar_videos v where id = %s", (json.dumps(a), vid)).fetchone()[0]
    assert dur({}) == Decimal("35.9")                                                            # 1000 quadros: 33,33 + 3 − 0,4
    assert dur({"manter": ["1:500"]}) == Decimal("45.9")                                        # mantido, o automático volta
    assert dur({"cortar": [[0, 100]]}) == dur({"inicio_q": 100}) == Decimal("32.6")
    # o fim no meio da 2ª palavra (pelo fim marcado ou por um corte até o fim): + 14 quadros de pad → (900 + 14) / 30 + 2,6
    assert dur({"cortar": [[1200, 1300]]}) == dur({"fim_q": 1200}) == Decimal("33.1")
    assert dur({"cortar": [[450, 850]]}) == Decimal("32.6")                                     # só conta o que não tinha saído
    # o fim 25 quadros depois da 1ª palavra (que termina no 495), com o automático mantido: a folga está lá (pad 0) → 520 / 30 + 2,6
    assert dur({"manter": ["1:500"], "fim_q": 520}) == Decimal("19.9")
    # sem o automático, o último quadro que fica é o 499: faltam 8,5 quadros de folga (pad 9) → 509 / 30 + 2,6
    assert dur({"fim_q": 520}) == Decimal("19.6")
    # sem as palavras no mapa: o último trecho sem palavra (a conta do robô sem palavra no último trecho: pad só se ele for curto)
    assert db.execute("select radar_video_edicao_duracao(jsonb_populate_record(null::radar_videos, jsonb_build_object('relatorio', %s::jsonb)), %s)",
                      (json.dumps({"mapa": {k: x for k, x in mapa.items() if k != "palavras"}}), json.dumps({"fim_q": 1200}))).fetchone()[0] == Decimal("32.6")
    assert editar(vid, {"manter": ["1:500"]})["duracao_s"] == 45.9        # v0.33.0: acima da meta é aceito (o aviso fica na tela); o teto é 900 s
    db.execute("update radar_videos set situacao = 'pronto' where id = %s", (vid,))
    assert editar(vid, {"manter": ["1:500"], "cortar": [[1200, 1300]]})["duracao_s"] == 43.1
    db.execute("update radar_videos set situacao = 'pronto' where id = %s", (vid,))
    r = editar(vid, {"cortar": [[100, 400]]})
    assert r["duracao_s"] == float(dur({"cortar": [[100, 400]]})) == 25.9
    db.execute("update radar_videos set situacao = 'pronto' where id = %s", (vid,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR310: os cortes deixam só 1,9 s de fala: o mínimo é 2 s"):
        editar(vid, {"inicio_q": 1000, "fim_q": 1057})
    assert editar(vid, {"inicio_q": 1000, "fim_q": 1060})["duracao_s"] == 5.1                  # 2 s de fala (+ o pad): passa
    db.execute("update radar_videos set situacao = 'pronto' where id = %s", (vid,))
    # o mínimo de 5 s vale pela duração de verdade: sem o fim marcado, 2,1 s de fala (e o pad 0) dão 4,7 s — recusado
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR310: o vídeo ficaria com cerca de 4,7 s: o mínimo é 5 s"):
        editar(vid, {"inicio_q": 1237})
    config(db, cartela_s=2)                                                                       # com a cartela de 2 s, o mínimo de 5 s pesa
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR310: o vídeo ficaria com cerca de 4,1 s: o mínimo é 5 s"):
        editar(vid, {"inicio_q": 1000, "fim_q": 1060})
    assert editar(vid, {"inicio_q": 1000, "fim_q": 1090})["duracao_s"] == 5.1
    # v0.33.0: o teto é o do reel do Instagram pela API (15 min = 900 s); acima dele, recusa — abaixo, mesmo bem acima da meta, passa
    db.execute("update radar_videos set situacao = 'pronto' where id = %s", (vid,))          # tira o vídeo de cima da fila
    config(db, cartela_s=3)
    longo = {"fps": 30, "linha_q": 28000, "faixas": [[0, 27500]], "automaticos": [], "trechos": [[0, 27500]], "pad_q": 0,
             "palavras": [[100, 916600]]}
    pid3, ana3, vid3 = pronto_com_mapa(db, relatorio={**REL_MAPA, "mapa": longo}, dias=11)
    with pytest.raises(psycopg.errors.RaiseException, match=r"RADAR310: o vídeo ficaria com cerca de .*: o máximo é 15 minutos \(o Instagram não aceita reel mais longo\)"):
        editar(vid3, {})
    assert editar(vid3, {"fim_q": 3000})["duracao_s"] == 103.1                                 # 100 s + o pad + a cartela − a transição: bem acima da meta, aceito


def test_editar_estilo_so_da_paleta_e_textos_sem_marcacao(corretor, request):
    db = corretor
    pid, ana, vid = pronto_com_mapa(db)
    for ajustes, msg in [({"legenda_cor": "roxo"}, "cor da legenda fora da paleta da Artecon"), ({"legenda_cor": "#FF0000"}, "cor da legenda fora"),
                         ({"legenda_cor": 1}, "cor da legenda fora"), ({"legenda_tamanho": "XG"}, "tamanho da legenda: pequena, média ou grande"),
                         ({"legenda_posicao": "lado"}, "posição da legenda: em cima, no meio ou embaixo"),
                         ({"cartela_extra": "x" * 121}, "texto extra da cartela: até 120 caracteres"), ({"cartela_extra": "com {chave}"}, "texto extra da cartela"),
                         ({"cartela_extra": "linha\nquebrada"}, "texto extra da cartela"), ({"cartela_extra": "<b>forte</b>"}, "texto extra da cartela"),
                         ({"cartela_extra": 5}, "texto extra da cartela"),
                         ({"cartela_extra": "Atendimento com especialista"}, "o texto extra da cartela não diz contador(a), técnico(a) nem especialista"),
                         ({"cartela_extra": "Fale com a contadora"}, "não diz contador(a)"), ({"cartela_extra": "Fale com a técnica"}, "não diz"),
                         ({"legenda": [["3:2", "com <b> marca"]]}, "legenda: até 200 blocos"), ({"legenda": {"3": "a > b"}}, "legenda: até 200 blocos"),
                         ({"outra": 1}, "ajuste desconhecido")]:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR310: .*" + re.escape(msg)):
            editar(vid, ajustes)
    # a legenda com marcação também é recusada nos ajustes da peça (antes da v0.33.0, só o robô e a tela recusavam < >)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR310: legenda"):
        tela("select radar_video_ajustar(%s, %s, null)", vid, json.dumps({"legenda": [["3:2", "com <b> marca"]]}), uid=ADMIN)
    # a frase do boletim pago no texto extra
    carregar_fontes_novas(db, request)
    frase = "o comitê gestor publicou nesta semana a orientação completa sobre o novo prazo de entrega das declarações"
    db.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo)
                  select id, 'https://boletim.exemplo/e', 'Boletim de mentira', %s, 'h-boletim-editar' from radar_fontes where slug = 'itc-email'""",
               (frase,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR303"):
        editar(vid, {"cartela_extra": frase[:110]})
    bom = {"legenda_tamanho": "P", "legenda_posicao": "meio", "legenda_cor": "vermelho", "cartela_extra": "Desde 2000 · (00) 0000-0000",
           "estilo": "compacta"}
    assert editar(vid, bom)["modo"] == "montagem" and video(db, vid, "ajustes") == bom
    db.execute("update radar_videos set situacao = 'pronto' where id = %s", (vid,))
    assert editar(vid, {**bom, "cartela_extra": ""})["modo"] == "montagem"                     # "Sem texto extra" (vazio)


def test_editar_gancho_muda_o_video_e_o_texto_do_gancho_da_peca(corretor, request):
    db = corretor
    pid, ana, vid = pronto_com_mapa(db)
    assert conferir(pid) == []
    marcar_pronta(db, pid)
    assert db.execute("select situacao from radar_pauta_pecas where id = %s", (pid,)).fetchone()[0] == "pronta"
    for gancho, msg in [("x" * 121, "RADAR308"), ("Prazo <b>novo</b>", "RADAR308"), ("Com {chave}", "RADAR308")]:
        with pytest.raises(psycopg.errors.RaiseException, match=msg):
            editar(vid, {}, gancho=gancho)
    assert editar(vid, {"legenda_cor": "azul"}, gancho="  Prazo novo   do Simples  ")["modo"] == "montagem"
    assert video(db, vid, "gancho, ajustes") == ("Prazo novo do Simples", {"legenda_cor": "azul"})
    assert db.execute("select chamada, situacao from radar_pauta_pecas where id = %s", (pid,)).fetchone() == ("Prazo novo do Simples", "em_producao")
    trilha = db.execute("""select depois->>'chamada' from radar_auditoria where tabela = 'radar_pauta_pecas' and registro_id = %s::text
                            order by id desc limit 1""", (pid,)).fetchone()
    assert trilha == ("Prazo novo do Simples",)
    assert montado(vid) == "pronto"
    assert conferir(pid) == []                                                                   # o gancho gravado é o da peça
    # "Sem texto do gancho" (vazio): marca sem_gancho; o gancho de antes fica guardado no vídeo
    assert editar(vid, {"legenda_cor": "azul"}, gancho="", sha=SHA2)["modo"] == "montagem"
    assert video(db, vid, "gancho, ajustes") == ("Prazo novo do Simples", {"legenda_cor": "azul", "sem_gancho": True})
    assert montado(vid, sha=SHA_VIDEO) == "pronto"
    # o texto de antes, de novo: tira o sem_gancho
    assert editar(vid, {"legenda_cor": "azul", "sem_gancho": True}, gancho="Prazo novo do Simples")["modo"] == "montagem"
    assert video(db, vid, "ajustes") == {"legenda_cor": "azul"}
    assert montado(vid) == "pronto"
    carregar_fontes_novas(db, request)
    frase = "o comitê gestor publicou nesta semana a orientação completa sobre o novo prazo de entrega"
    db.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo)
                  select id, 'https://boletim.exemplo/g', 'Boletim de mentira', %s, 'h-boletim-gancho' from radar_fontes where slug = 'itc-email'""",
               (frase,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR303"):
        editar(vid, {}, gancho=frase, sha=SHA2)


def test_ajustes_da_peca_guardam_as_mudancas_do_editor(corretor):
    """A tela da peça (mesmo a antiga, guardada no navegador) manda só as chaves de antes: as mudanças do editor ficam."""
    db = corretor
    pid, ana, vid = pronto_com_mapa(db)
    editor = {"cortar": [[100, 200]], "capa_q": 400, "legenda_cor": "amarelo", "cartela_extra": "Fale com a gente"}
    editar(vid, editor)
    montado(vid)
    assert tela("select radar_video_ajustar(%s, %s, null)", vid, json.dumps({"estilo": "compacta", "manter": ["2:900"]}), uid=ADMIN)["modo"] == "montagem"
    assert video(db, vid, "ajustes") == {**editor, "estilo": "compacta", "manter": ["2:900"]}
    montado(vid, sha=SHA_VIDEO)
    # sem "manter" no pedido, o "manter" de antes sai (é dos ajustes da peça); as do editor ficam
    tela("select radar_video_ajustar(%s, %s, null)", vid, json.dumps({}), uid=ADMIN)
    assert video(db, vid, "ajustes") == editor


def test_ajustes_da_peca_nao_aceitam_as_chaves_do_editor(corretor):
    """As chaves do editor só entram pela aba Vídeo (radar_video_editar), que confere cada uma com o vídeo: os ajustes da peça
    (radar_video_ajustar) recusam — senão o texto extra com "especialista" (NBC PG 01), o corte fora do vídeo e a capa num trecho
    cortado passariam sem conferência, e o robô gravaria a cartela com "especialista"."""
    db = corretor
    pid, ana, vid = pronto_com_mapa(db)
    for chave, valor in [("cartela_extra", "Especialistas em eSocial"), ("cortar", [[1100, 1250]]), ("capa_q", 290), ("inicio_q", 40),
                         ("fim_q", 900), ("legenda_tamanho", "G"), ("legenda_posicao", "cima"), ("legenda_cor", "azul"), ("cartela_extra", "")]:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR310: os cortes, o começo e o fim, a capa, o estilo da legenda e o texto "
                                                                "extra da cartela mudam na aba Vídeo"):
            tela("select radar_video_ajustar(%s, %s, null)", vid, json.dumps({"estilo": "compacta", chave: valor}), uid=ADMIN)
    assert video(db, vid, "situacao, ajustes") == ("pronto", {})
    for ruim in ({"cartela_extra": "Especialistas em eSocial"}, {"cortar": [[1100, 1250]]}, {"capa_q": 290}):   # a aba Vídeo confere
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR310"):
            editar(vid, ruim)
    assert video(db, vid, "situacao, ajustes") == ("pronto", {})


def test_cartela_que_nao_coube_com_o_texto_extra_do_editor_sai_do_erro(corretor):
    """O texto extra próprio da cartela (aba Vídeo) que não cabe: o endereço longo, sem espaço, é recusado antes de montar; o que só o
    robô descobre (cartela_nao_cabe) não prende o vídeo no erro — "Tentar de novo" monta com o texto extra das Configurações (a aba Vídeo
    não edita o vídeo com erro, e os ajustes da peça não tiram a chave). Os outros erros e o "sem texto extra" não mexem nele."""
    db = corretor
    pid, ana, vid = pronto_com_mapa(db)
    longo = "artecon.cnt.br/servicos/abertura-de-empresas-e-planejamento-tributario-palhoca-sc"
    with pytest.raises(psycopg.errors.RaiseException, match=re.escape("RADAR310: o texto extra da cartela tem uma palavra (ou endereço) com "
                                                                      "mais de 45 caracteres, sem espaço: não cabe na linha da cartela")):
        editar(vid, {"cartela_extra": longo})
    extra = "Atendimento presencial e online para empresas do Simples Nacional, do Lucro Presumido e do Lucro Real em SC"
    assert editar(vid, {"legenda_cor": "azul", "cartela_extra": extra})["modo"] == "montagem"
    falhar = lambda codigo: robo("select radar_video_falhar(%s, %s, %s)", vid, pegar()["tentativa"], codigo)
    assert falhar("cartela_nao_cabe") == {"situacao": "erro"}
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR309"):                       # a aba Vídeo não edita o vídeo com erro
        editar(vid, {"legenda_cor": "azul"})
    tela("select radar_video_ajustar(%s, %s, null)", vid, json.dumps({}), uid=ADMIN)            # os ajustes da peça guardam a chave
    assert video(db, vid, "ajustes") == {"legenda_cor": "azul", "cartela_extra": extra}
    assert falhar("cartela_nao_cabe") == {"situacao": "erro"}
    # "Tentar de novo" (o editor também pode): o texto extra próprio sai; o resto do editor fica
    assert tela("select radar_video_de_novo(%s, null)", vid, uid=EDITOR)["modo"] == "montagem"
    assert video(db, vid, "situacao, ajustes") == ("na_fila", {"legenda_cor": "azul"})
    assert montado(vid) == "pronto"
    # "sem texto extra" ("") e o texto extra com outro erro (que não é da cartela) ficam
    for aj, codigo in [({"cartela_extra": ""}, "cartela_nao_cabe"), ({"cartela_extra": "Fale com a gente"}, "conferencia_falhou")]:
        editar(vid, aj, sha=video(db, vid, "sha256"))
        assert falhar(codigo) == {"situacao": "erro"}
        tela("select radar_video_de_novo(%s, null)", vid)
        assert video(db, vid, "situacao, ajustes") == ("na_fila", aj)
        assert montado(vid, sha=SHA_VIDEO if video(db, vid, "sha256") == SHA2 else SHA2) == "pronto"


def test_robo_antigo_com_mudancas_do_editor_vira_erro_robo_desatualizado(corretor):
    """O robô do commit de antes (RADAR_VIDEO_COMMIT) não conhece as chaves do editor e montaria sem elas: o vídeo não é aceito."""
    db = corretor
    pid, ana, vid = pronto_com_mapa(db)
    editar(vid, {"cortar": [[100, 200]], "legenda_cor": "azul"})
    p = pegar()
    sem_edicao = {k: v for k, v in REL_MAPA.items() if k != "edicao"}
    assert concluir(vid, p["tentativa"], relatorio=sem_edicao, sha=SHA2) == {"situacao": "erro"}
    assert video(db, vid, "situacao, erro_codigo, sha256, antigos, pego_em") == ("erro", "robo_desatualizado", SHA_VIDEO, True, None)
    assert video(db, vid, "relatorio")["edicao"] == EDICAO                                       # o relatório de antes
    assert conferir(pid) == ["Reel: o corretor parou com erro (robo_desatualizado)"]
    # trocado o RADAR_VIDEO_COMMIT, "Tentar de novo": o robô desta versão monta
    assert tela("select radar_video_de_novo(%s)", vid)["modo"] == "montagem"
    assert montado(vid) == "pronto" and video(db, vid, "sha256") == SHA2
    # sem mudança do editor, o robô de antes continua valendo (os ajustes da peça)
    pid2, ana2 = reel(db, dias=6, pessoa=pessoa_do_corretor(db, "Bruno Exemplo", "Bruno"))
    vid2, _ = ate_pronto(db, pid2, ana2)
    tela("select radar_video_ajustar(%s, %s, null)", vid2, json.dumps({"estilo": "compacta"}), uid=ADMIN)
    assert montado(vid2, relatorio=RELATORIO) == "pronto"


def test_divergencia_cortada_nao_pede_regravar(corretor):
    db = corretor
    pid, ana, vid = pronto_com_mapa(db)
    editar(vid, {"cortar": [[100, 200]]})
    cortada = {**DIVERGENCIA, "regravar": False, "cortada": True}
    assert montado(vid, relatorio={**REL_MAPA, "divergencias": [cortada]}) == "pronto"
    editar(vid, {"cortar": [[100, 200]]}, sha=SHA2)
    aberta = {**DIVERGENCIA, "id": "fedcba9876543210", "k": 1}
    assert montado(vid, relatorio={**REL_MAPA, "divergencias": [cortada, aberta]}, sha=SHA_VIDEO) == "regravar"


def test_previa_e_baixar_devolvem_a_capa_do_mesmo_sha256(corretor):
    """A capa é a do relatório, pelo sha256 DELA no nome (quadros/<id>/<sha256 do vídeo>/capa-<sha256 da capa>.jpg): trocar só a capa
    monta o mesmo vídeo (o mesmo sha256), e a prévia e o baixar passam a apontar a capa nova, nunca a de antes."""
    db = corretor
    capa_a, capa_b = "e" * 64, "f" * 64
    pid, ana, vid = pronto_com_mapa(db)
    sem = tela("select radar_video_para_previa(%s)", vid)
    assert "capa" not in sem
    editar(vid, {"capa_q": 400})
    # o relatório com a capa sem o sha256 dela (ou fora do formato) não é aceito
    p = pegar()
    for ruim in ({"q": 400, "em_ms": 12300, "movida": False}, {"q": 400, "em_ms": 12300, "movida": False, "sha256": "E" * 64}, "capa.jpg"):
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR316: relatório fora do formato"):
            concluir(vid, p["tentativa"], relatorio={**REL_MAPA, "capa": ruim}, sha=SHA2)
    concluir(vid, p["tentativa"], relatorio={**REL_MAPA, "capa": {"q": 400, "em_ms": 12300, "movida": False, "sha256": capa_a}}, sha=SHA2)
    assert tela("select radar_video_para_previa(%s)", vid)["capa"] == f"quadros/{vid}/{SHA2}/capa-{capa_a}.jpg"
    # só a capa muda: o mesmo vídeo (SHA2), a capa nova
    editar(vid, {"capa_q": 450}, sha=SHA2)
    montado(vid, relatorio={**REL_MAPA, "capa": {"q": 450, "em_ms": 14000, "movida": False, "sha256": capa_b}}, sha=SHA2)
    assert tela("select radar_video_para_previa(%s)", vid)["capa"] == f"quadros/{vid}/{SHA2}/capa-{capa_b}.jpg"
    marcar_pronta(db, pid)
    aprovar_peca(db, pid, modo="manual", artes=[], conferencias=("pessoas", "video"), video=SHA2)
    r = tela("select radar_video_para_baixar(%s, %s)", pid, lido_peca(db, pid))
    assert r == {"ok": True, "caminho": f"corrigido/{vid}/{SHA2}.mp4", "data": str(hoje(db) + timedelta(days=5)),
                 "capa": f"quadros/{vid}/{SHA2}/capa-{capa_b}.jpg"}


def test_pendencia_aceita_o_texto_extra_proprio_da_cartela(corretor):
    db = corretor
    config(db, cartela_extra="Fale com a gente")
    pid, ana, vid = pronto_com_mapa(db, relatorio={**REL_MAPA, "cartela_extra": "Fale com a gente"})
    assert conferir(pid) == []
    editar(vid, {"cartela_extra": "Atendimento em Palhoça"})
    montado(vid, relatorio={**REL_MAPA, "cartela_extra": "Atendimento em Palhoça"})
    assert conferir(pid) == []                                                                   # o próprio deste vídeo, não o das Configurações
    editar(vid, {"cartela_extra": ""}, sha=SHA2)                                                   # "Sem texto extra"
    montado(vid, relatorio={**REL_MAPA, "cartela_extra": ""}, sha=SHA_VIDEO)
    assert conferir(pid) == []
    db.execute("""update radar_videos set relatorio = relatorio || '{"cartela_extra": "Fale com a gente"}' where id = %s""", (vid,))
    assert any(p.startswith("Reel: o texto extra da cartela mudou") for p in conferir(pid))


def test_reconferir_mantem_cortes_estilo_e_capa(corretor):
    """O roteiro mudou: com a fala nova, as marcas do alinhamento de antes saem (manter, a transcrição errou, a legenda); os cortes, o
    começo, o fim e a capa estão na linha ORIGINAL (a mesma gravação) e ficam, como o estilo."""
    db = corretor
    pid, ana, vid = pronto_com_mapa(db)
    editor = {"cortar": [[100, 200]], "inicio_q": 40, "capa_q": 300, "legenda_posicao": "cima", "cartela_extra": ""}
    editar(vid, {**editor, "manter": ["1:282"], "legenda": [["0:5", "O prazo do Simples vence"]]})
    montado(vid)
    novo = ROTEIRO.replace("nem juros.", "nem juros, e fale com a gente.")
    db.execute("update radar_pauta_pecas set roteiro = %s where id = %s", (novo, pid))
    assert tela("select radar_video_reconferir(%s, %s)", vid, FALA[:-1] + ", e fale com a gente.")["modo"] == "montagem"
    assert video(db, vid, "ajustes") == editor


# ------------------------------------------------------------------ sql/radar-video-agenda.sql e as reversões
AGENDA_VIDEO = RAIZ / "sql" / "radar-video-agenda.sql"
AGENDA_VIDEO_REVERSAO = RAIZ / "sql" / "radar-video-agenda-reversao.sql"
URL_VIDEO = "https://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-video"


@pytest.fixture(scope="module")
def banco_video_agenda():
    novo_banco("radar_video_agenda", com_setup=True, simulados=True)
    yield "radar_video_agenda"
    apagar_banco("radar_video_agenda")


def test_agenda_do_video_cria_as_chaves_a_reserva_so_com_fila_e_a_limpeza(banco_video_agenda, tmp_path):
    banco = banco_video_agenda
    r = psql(sem_extensoes(AGENDA_VIDEO.read_text(), tmp_path, "video.sql"), banco)
    assert r.returncode == 0, r.stderr
    with conectar(banco) as c:
        chaves = dict(c.execute("select name, decrypted_secret from vault.decrypted_secrets").fetchall())
        jobs = {n: (s, cmd) for n, s, cmd in c.execute("select jobname, schedule, command from cron.job").fetchall()}
    assert set(chaves) == {"radar_video_robo", "radar_video_agenda"} and all(re.fullmatch(r"[0-9a-f]{64}", v) for v in chaves.values())
    assert chaves["radar_video_robo"] != chaves["radar_video_agenda"]
    assert {n: s for n, (s, _) in jobs.items()} == {"radar-video-reserva": "*/10 * * * *", "radar-video-limpeza": "37 6 * * *"}
    for _, cmd in jobs.values():
        assert not any(v in cmd for v in chaves.values())                                         # as chaves são lidas do Vault na hora
        for trecho in (URL_VIDEO, "Bearer " + chave_anon_do_config(), "'x-radar-agenda'", "radar_video_agenda", "timeout_milliseconds := 150000"):
            assert trecho in cmd, trecho
    assert "public.radar_video_reserva()" in jobs["radar-video-reserva"][1] and "'acionar'" in jobs["radar-video-reserva"][1]
    assert "'limpar'" in jobs["radar-video-limpeza"][1] and "cron.job_run_details" in jobs["radar-video-limpeza"][1]
    with conectar(banco) as c:
        c.execute("truncate net.pedidos")
        c.execute(jobs["radar-video-reserva"][1])
        assert c.execute("select count(*) from net.pedidos").fetchone()[0] == 0                   # sem fila: nenhum pedido
        c.execute("select set_config('radar.pauta', '1', false)")
        pid = c.execute("insert into radar_pauta_pecas (data, tipo, formato, roteiro) values (radar_pauta_hoje() + 3, 'reel', 'reel', 'x') returning id").fetchone()[0]
        vid = c.execute("""insert into radar_videos (peca_id, situacao, partes, fala_pessoa, fala_roteiro, roteiro_hash, cartela_linhas, declaracoes, fila_em)
                           values (%s, 'na_fila', '[{"n":1,"tipo":"video/mp4","bytes":1}]', 1, 'fala de mentira com vinte letras', 'h', '{x}',
                                   '{so_marcadas,sem_fundo,so_voz,fala_confere}', now()) returning id""", (pid,)).fetchone()[0]
        c.execute(jobs["radar-video-reserva"][1])
        assert c.execute("select count(*) from net.pedidos").fetchone()[0] == 0                   # na fila há menos de 3 minutos: a tela já acionou
        c.execute("update radar_videos set fila_em = now() - interval '4 minutes' where id = %s", (vid,))
        c.execute(jobs["radar-video-reserva"][1])
        c.execute(jobs["radar-video-limpeza"][1])
        pedidos = [tuple(p) for p in c.execute("select url, body, headers from net.pedidos order by id").fetchall()]
    cab = {"Content-Type": "application/json", "Authorization": "Bearer " + chave_anon_do_config(), "x-radar-agenda": chaves["radar_video_agenda"]}
    assert pedidos == [(URL_VIDEO, {"acao": "acionar"}, cab), (URL_VIDEO, {"acao": "limpar"}, cab)]
    # o robô não pega (a chave do robô ou as variáveis do repositório privado erradas): mais 2 acionamentos da reserva e, no 4º, o
    # pedido vira erro "robo_nao_pegou" — um aviso só — e a reserva para (nada de uma execução vermelha a cada 10 minutos)
    with conectar(banco) as c:
        c.execute("truncate net.pedidos")
        for _ in range(5):
            c.execute(jobs["radar-video-reserva"][1])
        assert c.execute("select count(*) from net.pedidos").fetchone()[0] == 2
        assert c.execute("select situacao, erro_codigo, reservas from radar_videos where id = %s", (vid,)).fetchone() == ("erro", "robo_nao_pegou", 3)
    # rodar de novo não duplica nem troca as chaves; a reversão tira só os dois agendamentos (as chaves ficam)
    assert psql(sem_extensoes(AGENDA_VIDEO.read_text(), tmp_path, "video2.sql"), banco).returncode == 0
    with conectar(banco) as c:
        assert dict(c.execute("select name, decrypted_secret from vault.decrypted_secrets").fetchall()) == chaves
        c.execute("select cron.schedule('radar-redes-agenda', '*/5 * * * *', 'select 1')")
    for _ in range(2):
        r = psql(AGENDA_VIDEO_REVERSAO, banco)
        assert r.returncode == 0 and "Agenda do corretor de vídeo retirada." in r.stderr, r.stderr
    with conectar(banco) as c:
        assert [n for (n,) in c.execute("select jobname from cron.job").fetchall()] == ["radar-redes-agenda"]
        assert c.execute("select count(*) from vault.secrets").fetchone()[0] == 2


def test_agenda_do_video_recusa_chave_que_nao_e_a_anon_e_pede_o_setup(banco_video_agenda, tmp_path):
    texto, anon = AGENDA_VIDEO.read_text(), chave_anon_do_config()
    assert re.search(r"v_anon constant text := '([^']+)';", texto).group(1) == anon
    assert re.findall(r"eyJ[\w-]+\.[\w-]+\.[\w-]+", texto) == [anon] and "service_role" not in texto and not re.search(r"sb_secret_\w", texto)
    for i, ruim in enumerate(["sb_secret_testeRadar0123456789abcdef", "chave-qualquer"]):
        r = psql(sem_extensoes(texto.replace(anon, ruim), tmp_path, f"ruim{i}.sql"), banco_video_agenda)
        assert r.returncode != 0 and "não é a chave anon (pública). Nada foi agendado." in r.stderr and ruim not in r.stderr
    novo_banco("radar_video_sem", com_setup=False, simulados=True)
    try:
        r = psql(sem_extensoes(texto, tmp_path, "sem.sql"), "radar_video_sem")
        assert r.returncode != 0 and "Rode antes o radar-setup-v0.22.0.sql" in r.stderr
        with conectar("radar_video_sem") as c:
            assert c.execute("select (select count(*) from vault.secrets), (select count(*) from cron.job)").fetchone() == (0, 0)
    finally:
        apagar_banco("radar_video_sem")


def test_reversao_do_setup_tira_os_videos_e_a_agenda_do_corretor():
    sql = REVERSAO.read_text()
    for objeto in ("radar_videos", "radar_video_acessos", "radar-video-%", "radar_video_pegar()", "Storage → radar-videos"):
        assert objeto in sql, objeto
    with conectar("postgres") as c:
        c.execute("drop database if exists radar_rev22 with (force)")
        c.execute("create database radar_rev22")
    try:
        assert psql(RAIZ / "testes" / "supabase_simulado.sql", "radar_rev22").returncode == 0
        assert psql(SETUP, "radar_rev22").returncode == 0
        with conectar("radar_rev22") as c:
            c.execute(CRON_SIMULADO)
            c.execute(NET_SIMULADO)
            for nome in ("radar-video-reserva", "radar-video-limpeza", "copia-do-projeto"):
                c.execute("select cron.schedule(%s, '*/10 * * * *', 'select 1')", (nome,))
        r = psql(REVERSAO, "radar_rev22")
        assert r.returncode == 0, r.stderr
        with conectar("radar_rev22") as c:
            assert [n for (n,) in c.execute("select jobname from cron.job").fetchall()] == ["copia-do-projeto"]
            assert c.execute("select to_regclass('public.radar_videos'), to_regclass('public.radar_video_acessos')").fetchone() == (None, None)
            assert c.execute("""select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                                where n.nspname = 'public' and p.proname like 'radar\\_%'""").fetchone()[0] == 0
        assert psql(REVERSAO, "radar_rev22").returncode == 0                                           # roda de novo
    finally:
        with conectar("postgres") as c:
            c.execute("drop database if exists radar_rev22 with (force)")


# ------------------------------------------------------------------ v0.36.0: a correção avulsa (o vídeo sem peça na Pauta)
# O avulso é uma linha de radar_videos SEM peça (peca_id nulo) e COM título; a fala para conferência colada no envio É o roteiro dele;
# as pessoas ficam guardadas no próprio vídeo. As travas do dono não mudam (termo do corretor, termo de uso de imagem, menor, cartela,
# declarações, cota, boletim pago); o avulso não passa pela aprovação da peça e só o administrador baixa o vídeo PRONTO (registrado).
CRIAR_AVULSO = "select radar_video_criar_avulso(%s, %s, %s, %s::bigint[], %s, %s::text[], %s::text[])"
FALA_AVULSA = "O caderno fiscal da semana fica pronto na sexta e a equipe confere cada prazo antes do envio ao cliente."


def criar_avulso(pessoa, titulo="Aviso do caderno da semana", uid=EDITOR, partes=PARTES, fala=FALA_AVULSA, pessoas=None,
                 cartela=(IDENT,), decl=DECL):
    with como("authenticated", uid) as c:
        return c.execute(CRIAR_AVULSO, (titulo, json.dumps(partes), pessoa, [pessoa] if pessoas is None else pessoas, fala, list(cartela), list(decl))).fetchone()[0]


def avulso_na_fila(db, pessoa, **kw):
    vid = criar_avulso(pessoa, **kw)["id"]
    tela("select radar_video_enviado(%s)", vid)
    return vid


def avulso_pronto(db, pessoa, relatorio=None, sha=SHA_VIDEO, **kw):
    vid = avulso_na_fila(db, pessoa, **kw)
    p = pegar()
    assert p["id"] == vid
    robo("select radar_video_registrar_audio(%s, %s, %s::numeric, %s)", vid, p["tentativa"], 11.5, True)
    concluir(vid, p["tentativa"], relatorio=relatorio, sha=sha)
    return vid


def test_avulso_criar_confere_titulo_fala_pessoas_cartela_clipes_e_declaracoes(corretor):
    db = corretor
    ana = pessoa_do_corretor(db)
    erro = lambda codigo: pytest.raises(psycopg.errors.RaiseException, match=codigo)
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR300"):          # o leitor não envia
        criar_avulso(ana, uid=LEITOR)
    with erro("RADAR320: dê um título ao vídeo avulso"):
        criar_avulso(ana, titulo="ab")
    with erro(re.escape("RADAR320: o título do vídeo avulso não leva < > { } nem")):
        criar_avulso(ana, titulo="Aviso <b>urgente</b>")
    with erro("RADAR302: cole a fala para conferência"):
        criar_avulso(ana, fala="Prazo do Simples: dia vinte.")                             # menos de 10 palavras
    with erro("RADAR304: marque de 1 a 12 pessoas"):
        criar_avulso(ana, pessoas=[])
    bruno_sem_termo = nova_pessoa(db, "Bruno Exemplo", "Bruno")
    with erro("RADAR304: quem fala tem de estar entre as pessoas marcadas"):
        criar_avulso(ana, pessoas=[bruno_sem_termo])
    with erro(re.escape("RADAR304: uma pessoa do vídeo não pode aparecer nele (sem o termo novo, que cita o corretor de vídeo)")):
        criar_avulso(ana, pessoas=[ana, bruno_sem_termo])
    with erro("RADAR305"):
        criar_avulso(ana, cartela=("Linha sem a identificação legal",))
    with erro("RADAR306"):
        criar_avulso(ana, partes=[{"n": 2, "tipo": "video/mp4", "bytes": 1000}])
    with erro("RADAR307"):
        criar_avulso(ana, decl=DECL[:3])
    r = criar_avulso(ana, pessoas=[ana, ana])
    assert r["versao"] == 1 and re.fullmatch(r"[0-9a-f-]{36}", r["id"])
    campos = "peca_id, titulo, versao, situacao, pessoas, fala_pessoa, fala_roteiro, gancho"
    assert video(db, r["id"], campos) == (None, "Aviso do caderno da semana", 1, "aguardando_envio", [ana], ana, FALA_AVULSA, None)
    assert video(db, r["id"], "roteiro_hash") == db.execute("select radar_hash_texto(%s)", (FALA_AVULSA,)).fetchone()[0]
    # cada avulso é um envio próprio: o segundo não substitui o primeiro (nem o da peça)
    r2 = criar_avulso(ana, titulo="Outro aviso da equipe")
    assert r2["versao"] == 1 and video(db, r["id"]) == "aguardando_envio"
    # ou peça, ou título (a regra da tabela): nem o dono do banco mistura os dois
    pid, _ = reel(db, pessoa=ana)
    da_peca = criar(pid, ana)["id"]
    for sql, alvo in (("update radar_videos set titulo = 'x' where id = %s", da_peca),
                      ("update radar_videos set titulo = null where id = %s", r["id"]),
                      ("update radar_videos set peca_id = null where id = %s", da_peca)):
        with pytest.raises(psycopg.errors.CheckViolation):
            db.execute(sql, (alvo,))


def test_avulso_caminho_completo_do_envio_ao_baixar_do_administrador(corretor):
    db = corretor
    ana = pessoa_do_corretor(db)
    vid = avulso_na_fila(db, ana)
    assert video(db, vid) == "na_fila"
    p = pegar()                                                           # o pedido do robô é autossuficiente: nada muda no avulso
    assert p["id"] == vid and p["modo"] == "completo" and p["fala_roteiro"] == FALA_AVULSA
    assert p["gancho"] is None and p["cartela_linhas"] == [IDENT] and p["partes"] == PARTES
    robo("select radar_video_registrar_audio(%s, %s, %s::numeric, %s)", vid, p["tentativa"], 11.5, True)
    capa = {"sha256": "c" * 64, "em_ms": 1200}
    concluir(vid, p["tentativa"], relatorio={**RELATORIO, "texto_final": FALA_AVULSA, "capa": capa})
    assert video(db, vid) == "pronto"
    # a prévia é do editor e do administrador, como na peça; baixar é SÓ do administrador (não há aprovação de peça)
    assert tela("select radar_video_para_previa(%s)", vid)["video"] == f"corrigido/{vid}/{SHA_VIDEO}.mp4"
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR321: só o administrador baixa o vídeo avulso"):
        tela("select radar_video_baixar_avulso(%s)", vid, uid=EDITOR)
    r = tela("select radar_video_baixar_avulso(%s)", vid, uid=ADMIN)
    assert r["ok"] is True and r["caminho"] == f"corrigido/{vid}/{SHA_VIDEO}.mp4"
    assert r["data"] == str(hoje(db)) and r["capa"] == f"quadros/{vid}/{SHA_VIDEO}/capa-{'c' * 64}.jpg"
    acessos = db.execute("select usuario::text, acao from radar_video_acessos where video_id = %s order by id", (vid,)).fetchall()
    assert acessos == [(EDITOR, "previa"), (ADMIN, "baixar")]
    # o vídeo de uma peça não sai por aqui
    pid, _ = reel(db, pessoa=ana)
    da_peca, _ = ate_pronto(db, pid, ana)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR321: este vídeo não é um vídeo avulso"):
        tela("select radar_video_baixar_avulso(%s)", da_peca, uid=ADMIN)


def test_avulso_para_regravar_nao_baixa_e_a_marca_do_administrador_libera(corretor):
    db = corretor
    ana = pessoa_do_corretor(db)
    rel = {**RELATORIO, "texto_final": FALA_AVULSA, "divergencias": [DIVERGENCIA]}
    vid = avulso_pronto(db, ana, relatorio=rel)
    assert video(db, vid) == "regravar"                                   # a divergência pendente pede regravar, como na peça
    r = tela("select radar_video_baixar_avulso(%s)", vid, uid=ADMIN)
    assert r["motivo"].startswith("Só o vídeo avulso PRONTO")
    tela("select radar_video_ajustar(%s, %s, null)", vid, json.dumps({"transcricao_errou": [DIVERGENCIA["id"]]}), uid=ADMIN)
    p = pegar()
    assert p["id"] == vid and p["modo"] == "montagem"
    concluir(vid, p["tentativa"], relatorio=rel, sha=SHA2)
    assert video(db, vid) == "pronto"
    assert tela("select radar_video_baixar_avulso(%s)", vid, uid=ADMIN)["caminho"] == f"corrigido/{vid}/{SHA2}.mp4"


def test_avulso_termo_revogado_trava_o_robo_a_previa_e_o_baixar_e_a_limpeza_leva(corretor):
    db = corretor
    ana = pessoa_do_corretor(db)
    vid = avulso_na_fila(db, ana)
    db.execute("update radar_pessoas set termo_corretor_em = null where id = %s", (ana,))
    assert pegar() is None and video(db, vid, "situacao, erro_codigo") == ("erro", "termo")   # antes de qualquer clipe sair
    db.execute("update radar_pessoas set termo_corretor_em = '2020-01-01' where id = %s", (ana,))
    tela("select radar_video_de_novo(%s, null)", vid)
    p = pegar()
    robo("select radar_video_registrar_audio(%s, %s, %s::numeric, %s)", vid, p["tentativa"], 11.5, True)
    concluir(vid, p["tentativa"], relatorio={**RELATORIO, "texto_final": FALA_AVULSA})
    # o termo de uso de imagem revogado fecha a prévia e o baixar na hora, e a limpeza leva arquivos e textos (o "left join" do avulso)
    db.execute("update radar_pessoas set termo_revogado_em = radar_pauta_hoje() where id = %s", (ana,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR304"):
        tela("select radar_video_para_previa(%s)", vid)
    assert "não pode aparecer nele hoje" in tela("select radar_video_baixar_avulso(%s)", vid, uid=ADMIN)["motivo"]
    r = robo("select radar_video_limpeza()")
    assert {i["id"]: sorted(i["apagar"]) for i in r["itens"]} == {vid: ["bruto", "corrigido", "trabalho"]} and r["textos"] == 1
    assert video(db, vid, "fala_roteiro, cartela_linhas, arquivos_apagados") == ("", [], ["textos"])


def test_avulso_sem_conferir_com_roteiro_novo_e_o_gancho_do_editor_fica_so_no_video(corretor):
    db = corretor
    ana = pessoa_do_corretor(db)
    pecas_antes = db.execute("select count(*) from radar_pauta_pecas").fetchone()[0]
    vid = avulso_pronto(db, ana, relatorio={**REL_MAPA, "texto_final": FALA_AVULSA})
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR302: o vídeo avulso não tem roteiro de peça"):
        tela("select radar_video_reconferir(%s, %s)", vid, FALA_AVULSA)
    # o gancho entra pelo editor da aba Vídeo e fica SÓ no vídeo (não há chamada de peça para mudar)
    r = editar(vid, {}, gancho="O caderno fica pronto na sexta")
    assert r["modo"] == "montagem"
    assert video(db, vid, "situacao, gancho") == ("na_fila", "O caderno fica pronto na sexta")
    assert db.execute("select count(*) from radar_pauta_pecas").fetchone()[0] == pecas_antes
    assert montado(vid) == "pronto"


def test_avulso_envio_abandonado_sai_na_limpeza_de_um_dia(corretor):
    db = corretor
    ana = pessoa_do_corretor(db)
    vid = criar_avulso(ana)["id"]
    db.execute("update radar_videos set criado_em = now() - interval '2 days' where id = %s", (vid,))
    r = robo("select radar_video_limpeza()")
    assert {i["id"]: sorted(i["apagar"]) for i in r["itens"]} == {vid: ["bruto", "corrigido", "trabalho"]}
    robo("select radar_video_limpo(%s, %s::text[])", vid, ["bruto", "corrigido", "trabalho"])
    assert video(db, vid) == "descartado"
