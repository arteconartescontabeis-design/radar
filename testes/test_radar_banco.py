"""Testes do banco: instalação, RLS por perfil, fundamentação, aprovação, publicação e auditoria."""
from __future__ import annotations

import json

import psycopg
import pytest

from conftest import ADMIN, EDITOR, LEITOR, RAIZ, REVERSAO, SEM_PERFIL, SETUP, como, conectar, psql

TEXTO_OFICIAL = ("Art. 1º Esta Instrução Normativa dispõe sobre a apuração da Contribuição Social sobre "
                 "Bens e Serviços (CBS) no período de transição. Art. 2º O contribuinte deverá destacar "
                 "a CBS no documento fiscal à alíquota de 0,9% (nove décimos por cento) a partir de "
                 "1º de janeiro de 2027. Art. 3º Esta Instrução Normativa entra em vigor na data de sua publicação.")


def nova_captura(db, slug="rfb-normas", url="https://exemplo.gov.br/in-2290", texto=TEXTO_OFICIAL):
    return db.execute(
        """insert into radar_capturas (fonte_id, url, titulo, texto, hash_conteudo, hash_titulo)
           select id, %s, 'IN RFB nº 2290', %s, md5(%s), md5('in rfb 2290') from radar_fontes where slug = %s
           returning id""", (url, texto, texto, slug)).fetchone()[0]


def novo_assunto(db, situacao="confirmado_oficialmente"):
    return db.execute("insert into radar_assuntos (titulo, situacao_confirmacao) values ('CBS na transição', %s) returning id",
                      (situacao,)).fetchone()[0]


def novo_conteudo(db, assunto, status="em_revisao"):
    return db.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo, status)
                         values (%s, 'informativo', 'CBS: o que muda', 'Texto do informativo.', %s) returning id""",
                      (assunto, status)).fetchone()[0]


def aprovar(conteudo, uid=EDITOR):
    with como("authenticated", uid) as c:
        return c.execute("update radar_conteudos set status = 'aprovado' where id = %s returning aprovado_por::text",
                         (conteudo,)).fetchone()


# ------------------------------------------------------------------ instalação
def test_instalacao_cria_20_tabelas_com_rls(db):
    linhas = db.execute("""select c.relname, c.relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace
                           where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'radar\\_%'""").fetchall()
    assert len(linhas) == 20
    assert all(rls for _, rls in linhas), [n for n, rls in linhas if not rls]


def test_toda_tabela_radar_tem_ao_menos_uma_politica(db):
    sem = db.execute("""select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
                        where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'radar\\_%'
                          and not exists (select 1 from pg_policies p where p.tablename = c.relname)""").fetchall()
    assert sem == []


def test_setup_e_idempotente(db):
    antes = db.execute("select (select count(*) from radar_fontes), (select count(*) from radar_categorias), "
                       "(select count(*) from pg_policies where tablename like 'radar\\_%'), "
                       "(select count(*) from pg_trigger t join pg_class c on c.oid = t.tgrelid "
                       " where c.relname like 'radar\\_%' and not t.tgisinternal)").fetchone()
    db.execute("update radar_fontes set frequencia_horas = 9, ativo = false where slug = 'pgfn-noticias'")
    r = psql(SETUP)
    assert r.returncode == 0, r.stderr
    depois = db.execute("select (select count(*) from radar_fontes), (select count(*) from radar_categorias), "
                        "(select count(*) from pg_policies where tablename like 'radar\\_%'), "
                        "(select count(*) from pg_trigger t join pg_class c on c.oid = t.tgrelid "
                        " where c.relname like 'radar\\_%' and not t.tgisinternal)").fetchone()
    assert antes == depois
    # ajuste feito pelo usuário NÃO é sobrescrito pela reexecução
    assert db.execute("select frequencia_horas, ativo from radar_fontes where slug = 'pgfn-noticias'").fetchone() == (9, False)
    db.execute("update radar_fontes set frequencia_horas = 6, ativo = true where slug = 'pgfn-noticias'")
    reg = db.execute("select antes, depois from radar_instalacoes order by id desc limit 1").fetchone()
    assert len(reg[0]) == 20 and len(reg[1]) == 20   # 2ª execução: já havia 20 antes


def test_fontes_do_sql_espelham_o_json_do_robo(db):
    fontes = json.loads((RAIZ / "robo" / "radar_fontes.json").read_text(encoding="utf-8"))
    banco = {s: (u, t, c) for s, u, t, c in db.execute("select slug, url, tipo_coletor, config from radar_fontes "
                                                       "where slug not like 'teste-%'")}
    assert set(banco) == {f["slug"] for f in fontes}
    for f in fontes:
        assert banco[f["slug"]] == (f["url"], f["tipo_coletor"], f["config"])


# ------------------------------------------------------------------------- RLS
def test_anonimo_nao_le_dados_internos(limpo):
    nova_captura(limpo)
    with como("anon") as c:
        for tabela in ["radar_capturas", "radar_fontes", "radar_assuntos", "radar_conteudos", "radar_evidencias",
                       "radar_auditoria", "radar_perfis", "radar_execucoes"]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(f"select * from {tabela}")
        assert c.execute("select count(*) from radar_categorias").fetchone()[0] == 8


def test_usuario_logado_sem_perfil_nao_ve_nada(limpo):
    nova_captura(limpo)
    novo_assunto(limpo)
    with como("authenticated", SEM_PERFIL) as c:
        for tabela in ["radar_capturas", "radar_fontes", "radar_assuntos", "radar_auditoria", "radar_perfis"]:
            assert c.execute(f"select count(*) from {tabela}").fetchone()[0] == 0, tabela
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into radar_assuntos (titulo) values ('x')")


def test_leitor_le_mas_nao_grava(limpo):
    nova_captura(limpo)
    a = novo_assunto(limpo)
    with como("authenticated", LEITOR) as c:
        assert c.execute("select count(*) from radar_capturas").fetchone()[0] == 1
        assert c.execute("select count(*) from radar_fontes").fetchone()[0] == 6
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into radar_assuntos (titulo) values ('x')")
        assert c.execute("update radar_assuntos set titulo = 'alterado' where id = %s", (a,)).rowcount == 0
        assert c.execute("delete from radar_assuntos where id = %s", (a,)).rowcount == 0
        assert c.execute("select count(*) from radar_auditoria").fetchone()[0] == 0
        assert c.execute("select count(*) from radar_perfis").fetchone()[0] == 1   # só o próprio


def test_editor_grava_editorial_mas_nao_mexe_em_fontes_nem_capturas(limpo):
    cap = nova_captura(limpo)
    with como("authenticated", EDITOR) as c:
        a = c.execute("insert into radar_assuntos (titulo) values ('novo') returning id").fetchone()[0]
        assert c.execute("update radar_assuntos set relevancia = 'alta' where id = %s", (a,)).rowcount == 1
        assert c.execute("delete from radar_assuntos where id = %s", (a,)).rowcount == 0      # apagar: só admin
        assert c.execute("update radar_fontes set ativo = false").rowcount == 0
        assert c.execute("update radar_capturas set texto = 'adulterado' where id = %s", (cap,)).rowcount == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into radar_capturas (fonte_id, url, titulo, hash_titulo) values (1, 'u', 't', 'h')")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into radar_perfis (user_id, nome, papel) values (%s, 'eu', 'admin')", (SEM_PERFIL,))
        assert c.execute("update radar_perfis set papel = 'admin' where user_id = %s", (EDITOR,)).rowcount == 0


def test_admin_gerencia_fontes_perfis_e_le_auditoria(limpo):
    with como("authenticated", ADMIN) as c:
        assert c.execute("update radar_fontes set frequencia_horas = 8 where slug = 'rfb-noticias'").rowcount == 1
        c.execute("update radar_fontes set frequencia_horas = 6 where slug = 'rfb-noticias'")
        assert c.execute("select count(*) from radar_perfis").fetchone()[0] == 3
        assert c.execute("select count(*) from radar_auditoria where tabela = 'radar_fontes'").fetchone()[0] == 2


def test_service_role_do_robo_grava_capturas(limpo):
    with como("service_role") as c:
        c.execute("""insert into radar_capturas (fonte_id, url, titulo, hash_titulo)
                     select id, 'https://x.gov.br/1', 'titulo', 'h' from radar_fontes where slug = 'rfb-noticias'""")
        assert c.execute("select count(*) from radar_capturas").fetchone()[0] == 1


# --------------------------------------------------------------- fundamentação
@pytest.mark.parametrize("trecho, esperado", [
    ("O contribuinte deverá destacar a CBS no documento fiscal à alíquota de 0,9%", True),
    ("o  contribuinte\ndeverá destacar a CBS   no documento fiscal", True),          # espaços e caixa
    ("O contribuinte deverá destacar a CBS no documento fiscal à alíquota de 1,5%", False),   # número trocado
    ("Art. 7º Fica instituída multa de 75% sobre o valor não destacado", False),      # dispositivo inventado
    ("Art. 2º", False),                                                              # curto demais para provar algo
])
def test_trecho_so_e_conferido_se_existir_literalmente(limpo, trecho, esperado):
    cap, a = nova_captura(limpo), novo_assunto(limpo)
    ok = limpo.execute("""insert into radar_evidencias (assunto_id, captura_id, trecho_literal)
                          values (%s, %s, %s) returning trecho_conferido""", (a, cap, trecho)).fetchone()[0]
    assert ok is esperado


def test_aspas_e_tracos_tipograficos_nao_impedem_a_conferencia(limpo):
    cap = nova_captura(limpo, texto="A norma define “estabelecimento” como o local – fixo ou não – onde se exerce a atividade.")
    a = novo_assunto(limpo)
    ok = limpo.execute("""insert into radar_evidencias (assunto_id, captura_id, trecho_literal)
                          values (%s, %s, 'define "estabelecimento" como o local - fixo ou não - onde') returning trecho_conferido""",
                       (a, cap)).fetchone()[0]
    assert ok is True


def test_ninguem_marca_trecho_como_conferido_a_mao(limpo):
    cap, a = nova_captura(limpo), novo_assunto(limpo)
    with como("authenticated", EDITOR) as c:
        e = c.execute("""insert into radar_evidencias (assunto_id, captura_id, trecho_literal, trecho_conferido)
                         values (%s, %s, 'Art. 9º Texto que não existe na norma capturada', true)
                         returning id, trecho_conferido""", (a, cap)).fetchone()
        assert e[1] is False
        assert c.execute("update radar_evidencias set trecho_conferido = true where id = %s returning trecho_conferido",
                         (e[0],)).fetchone()[0] is False
    with como("service_role") as c:
        assert c.execute("update radar_evidencias set trecho_conferido = true where id = %s returning trecho_conferido",
                         (e[0],)).fetchone()[0] is False


def test_mudanca_no_texto_oficial_guarda_versao_e_reconfere_evidencias(limpo):
    cap, a = nova_captura(limpo), novo_assunto(limpo)
    e = limpo.execute("""insert into radar_evidencias (assunto_id, captura_id, trecho_literal)
                         values (%s, %s, %s) returning id, trecho_conferido""",
                      (a, cap, "à alíquota de 0,9% (nove décimos por cento)")).fetchone()
    assert e[1] is True
    novo = TEXTO_OFICIAL.replace("0,9% (nove décimos por cento)", "1% (um por cento)")
    with como("service_role") as c:
        c.execute("update radar_capturas set texto = %s, hash_conteudo = md5(%s) where id = %s", (novo, novo, cap))
    assert limpo.execute("select versao, atualizado_em is not null from radar_capturas where id = %s", (cap,)).fetchone() == (2, True)
    v = limpo.execute("select versao, texto from radar_capturas_versoes where captura_id = %s", (cap,)).fetchall()
    assert v == [(1, TEXTO_OFICIAL)]
    assert limpo.execute("select trecho_conferido, versao_captura from radar_evidencias where id = %s", (e[0],)).fetchone() == (False, 2)


def test_visita_sem_mudanca_nao_cria_versao(limpo):
    cap = nova_captura(limpo)
    limpo.execute("update radar_capturas set verificado_em = now() where id = %s", (cap,))
    assert limpo.execute("select versao from radar_capturas where id = %s", (cap,)).fetchone()[0] == 1
    assert limpo.execute("select count(*) from radar_capturas_versoes").fetchone()[0] == 0


def test_mesma_url_na_mesma_fonte_nao_duplica(limpo):
    nova_captura(limpo)
    with pytest.raises(psycopg.errors.UniqueViolation):
        nova_captura(limpo)


# ------------------------------------------------------------------- aprovação
def test_robo_e_ia_nao_aprovam_conteudo(limpo):
    c1 = novo_conteudo(limpo, novo_assunto(limpo))
    with como("service_role") as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR020"):
            c.execute("update radar_conteudos set status = 'aprovado' where id = %s", (c1,))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR020"):
            c.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo, status, aprovado_por)
                         select assunto_id, 'flash', 't', 'c', 'aprovado', %s from radar_conteudos where id = %s""", (EDITOR, c1))
    assert limpo.execute("select status from radar_conteudos where id = %s", (c1,)).fetchone()[0] == "em_revisao"


def test_leitor_nao_aprova(limpo):
    c1 = novo_conteudo(limpo, novo_assunto(limpo))
    assert aprovar(c1, LEITOR) is None        # RLS: nenhuma linha alcançada
    assert limpo.execute("select status from radar_conteudos where id = %s", (c1,)).fetchone()[0] == "em_revisao"


def test_editor_aprova_e_fica_registrado_quem_aprovou(limpo):
    c1 = novo_conteudo(limpo, novo_assunto(limpo))
    assert aprovar(c1)[0] == EDITOR
    assert limpo.execute("select aprovado_em is not null from radar_conteudos where id = %s", (c1,)).fetchone()[0]


def test_nao_da_para_forjar_o_aprovador(limpo):
    c1 = novo_conteudo(limpo, novo_assunto(limpo))
    with como("authenticated", EDITOR) as c:
        quem = c.execute("update radar_conteudos set status = 'aprovado', aprovado_por = %s where id = %s "
                         "returning aprovado_por::text", (ADMIN, c1)).fetchone()[0]
    assert quem == EDITOR


def test_texto_alterado_depois_de_aprovado_volta_para_revisao(limpo):
    c1 = novo_conteudo(limpo, novo_assunto(limpo))
    aprovar(c1)
    with como("authenticated", EDITOR) as c:
        r = c.execute("update radar_conteudos set corpo = 'Texto trocado depois.' where id = %s "
                      "returning status, aprovado_por", (c1,)).fetchone()
    assert r == ("em_revisao", None)


# ------------------------------------------------------------------ publicação
def publicar(conteudo, uid=EDITOR, slug="cbs-o-que-muda", quando="now()"):
    with como("authenticated", uid) as c:
        return c.execute(f"""insert into radar_publicacoes (conteudo_id, slug, status, publicar_em)
                             values (%s, %s, 'publicado', {quando})
                             returning id, publicado_por::text""", (conteudo, slug)).fetchone()


def cenario_publicavel(db, situacao="confirmado_oficialmente", trecho="à alíquota de 0,9% (nove décimos por cento)",
                       slug_fonte="rfb-normas"):
    cap = nova_captura(db, slug=slug_fonte)
    a = novo_assunto(db, situacao)
    if trecho:
        db.execute("insert into radar_evidencias (assunto_id, captura_id, trecho_literal) values (%s, %s, %s)", (a, cap, trecho))
    c1 = novo_conteudo(db, a)
    return a, c1


def test_nao_publica_conteudo_nao_aprovado(limpo):
    _, c1 = cenario_publicavel(limpo)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR030"):
        publicar(c1)


def test_nao_publica_assunto_sem_confirmacao_oficial(limpo):
    for i, situacao in enumerate(["confirmado_fontes_confiaveis", "em_verificacao", "nao_confirmado", "divergencia_identificada"]):
        limpo.execute("truncate radar_assuntos, radar_capturas restart identity cascade")
        _, c1 = cenario_publicavel(limpo, situacao)
        aprovar(c1)
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR031"):
            publicar(c1, slug=f"s{i}")


def test_nao_publica_sem_evidencia(limpo):
    _, c1 = cenario_publicavel(limpo, trecho=None)
    aprovar(c1)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR032.*FUNDAMENTAÇÃO NÃO CONFIRMADA"):
        publicar(c1)


def test_nao_publica_com_evidencia_que_nao_confere(limpo):
    _, c1 = cenario_publicavel(limpo, trecho="Art. 7º Fica instituída multa de 75% sobre o valor não destacado")
    aprovar(c1)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR032"):
        publicar(c1)


def test_evidencia_de_fonte_nao_oficial_nao_libera_publicacao(limpo):
    limpo.execute("""insert into radar_fontes (slug, nome, orgao, oficial, tipo_coletor, url)
                     values ('teste-portal', 'Portal de notícias', 'Imprensa', false, 'rss', 'https://portal.exemplo/rss')""")
    _, c1 = cenario_publicavel(limpo, slug_fonte="teste-portal")
    aprovar(c1)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR032"):
        publicar(c1)


def test_publica_quando_tudo_confere_e_o_publico_enxerga(limpo):
    _, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    pid, quem = publicar(c1)
    assert quem == EDITOR
    with como("anon") as c:
        assert c.execute("select slug from radar_publicacoes").fetchall() == [("cbs-o-que-muda",)]


def test_publicacao_agendada_so_aparece_na_data(limpo):
    _, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    pid, _ = publicar(c1, quando="now() + interval '2 days'")
    with como("anon") as c:
        assert c.execute("select count(*) from radar_publicacoes").fetchone()[0] == 0
    with como("authenticated", LEITOR) as c:
        assert c.execute("select count(*) from radar_publicacoes").fetchone()[0] == 1   # a equipe vê
    limpo.execute("update radar_publicacoes set publicar_em = now() - interval '1 minute' where id = %s", (pid,))
    with como("anon") as c:
        assert c.execute("select count(*) from radar_publicacoes").fetchone()[0] == 1


def test_rascunho_e_despublicado_nao_aparecem_para_o_publico(limpo):
    _, c1 = cenario_publicavel(limpo)
    with como("authenticated", EDITOR) as c:   # rascunho não passa pelo portão
        pid = c.execute("insert into radar_publicacoes (conteudo_id, slug) values (%s, 'r') returning id", (c1,)).fetchone()[0]
    with como("anon") as c:
        assert c.execute("select count(*) from radar_publicacoes").fetchone()[0] == 0
    aprovar(c1)
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_publicacoes set status = 'publicado' where id = %s", (pid,))
    with como("anon") as c:
        assert c.execute("select count(*) from radar_publicacoes").fetchone()[0] == 1
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_publicacoes set status = 'despublicado' where id = %s", (pid,))
    with como("anon") as c:
        assert c.execute("select count(*) from radar_publicacoes").fetchone()[0] == 0


def test_anonimo_nao_grava_publicacao(limpo):
    _, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    pid, _ = publicar(c1)
    with como("anon") as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("update radar_publicacoes set titulo = 'invadido' where id = %s", (pid,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("delete from radar_publicacoes")


def test_errata_em_publicacao_ja_publicada_e_permitida(limpo):
    a, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    pid, _ = publicar(c1)
    limpo.execute("update radar_assuntos set situacao_confirmacao = 'divergencia_identificada' where id = %s", (a,))
    with como("authenticated", EDITOR) as c:
        assert c.execute("update radar_publicacoes set errata = 'Corrigida a alíquota.' where id = %s", (pid,)).rowcount == 1
        aprovar(c1)   # (a mudança no assunto não derruba a aprovação do texto; o que barra é o portão)
        # mas REpublicar depois de despublicar passa de novo pelo portão
        c.execute("update radar_publicacoes set status = 'despublicado' where id = %s", (pid,))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR031"):
            c.execute("update radar_publicacoes set status = 'publicado' where id = %s", (pid,))


def test_vinculo_publicacao_norma(limpo):
    _, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    pid, _ = publicar(c1)
    with como("authenticated", EDITOR) as c:
        n = c.execute("""insert into radar_normas (tipo, numero, orgao, data_norma) values ('Instrução Normativa', '2290', 'RFB', '2026-09-30')
                         returning id""").fetchone()[0]
        c.execute("insert into radar_publicacao_normas values (%s, %s)", (pid, n))
    # norma vinculada a publicação não pode ser apagada por engano
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        limpo.execute("delete from radar_normas where id = %s", (n,))


# ------------------------------------------------------------------- auditoria
def test_auditoria_registra_quem_fez_o_que(limpo):
    c1 = novo_conteudo(limpo, novo_assunto(limpo))
    aprovar(c1)
    linhas = limpo.execute("""select acao, usuario::text, antes->>'status', depois->>'status' from radar_auditoria
                              where tabela = 'radar_conteudos' order by id""").fetchall()
    assert linhas == [("INSERT", None, None, "em_revisao"), ("UPDATE", EDITOR, "em_revisao", "aprovado")]


def test_auditoria_nao_pode_ser_alterada_nem_apagada(limpo):
    novo_assunto(limpo)
    # nem o superusuário (SQL Editor) altera a trilha: o gatilho barra
    for sql in ["update radar_auditoria set acao = 'X'", "delete from radar_auditoria", "truncate radar_auditoria"]:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR010"):
            limpo.execute(sql)
    # o robô (service_role) nem chega lá: não tem permissão de escrita
    with como("service_role") as c:
        for sql in ["update radar_auditoria set acao = 'X'", "delete from radar_auditoria", "truncate radar_auditoria"]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)
    with como("authenticated", ADMIN) as c:
        assert c.execute("delete from radar_auditoria").rowcount == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into radar_auditoria (tabela, registro_id, acao) values ('x', '1', 'FORJADO')")


# -------------------------------------------------------------- saúde da fonte
def test_saude_da_fonte_acompanha_as_execucoes(limpo):
    fid = limpo.execute("select id from radar_fontes where slug = 'pgfn-noticias'").fetchone()[0]

    def saude():
        return limpo.execute("select saude, falhas_consecutivas from radar_v_saude_fontes where id = %s", (fid,)).fetchone()

    assert saude() == ("nunca_executou", 0)
    with como("service_role") as c:
        def rodar(status, erro=None):
            e = c.execute("insert into radar_execucoes (fonte_id) values (%s) returning id", (fid,)).fetchone()[0]
            c.execute("update radar_execucoes set status = %s, erro = %s, finalizado_em = now() where id = %s", (status, erro, e))
        rodar("ok")
        assert saude() == ("ok", 0)
        rodar("falha", "HTTP 503")
        assert saude() == ("instavel", 1)
        rodar("vazio_suspeito", "nenhum item reconhecido")
        rodar("falha", "HTTP 503")
        assert saude() == ("falhando", 3)
        assert limpo.execute("select ultimo_erro from radar_fontes where id = %s", (fid,)).fetchone()[0] == "HTTP 503"
        rodar("ok")
        assert saude() == ("ok", 0)
    limpo.execute("update radar_fontes set ultimo_sucesso_em = now() - interval '3 days' where id = %s", (fid,))
    assert saude()[0] == "atrasada"
    # as atualizações automáticas de saúde não poluem a trilha de auditoria
    assert limpo.execute("select count(*) from radar_auditoria where tabela = 'radar_fontes'").fetchone()[0] == 0


# -------------------------------------------------------------------- reversão
def test_reversao_remove_tudo_e_o_setup_reinstala():
    with conectar("postgres") as c:
        c.execute("drop database if exists radar_reversao with (force)")
        c.execute("create database radar_reversao")
    try:
        assert psql(RAIZ / "testes" / "supabase_simulado.sql", "radar_reversao").returncode == 0
        with conectar("radar_reversao") as c:
            c.execute("create table public.outra_tabela_do_projeto (id int)")
        assert psql(SETUP, "radar_reversao").returncode == 0
        r = psql(REVERSAO, "radar_reversao")
        assert r.returncode == 0, r.stderr
        with conectar("radar_reversao") as c:
            assert c.execute("""select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace
                                where n.nspname = 'public' and c.relname like 'radar\\_%'""").fetchone()[0] == 0
            assert c.execute("""select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                                where n.nspname = 'public' and p.proname like 'radar\\_%'""").fetchone()[0] == 0
            assert c.execute("select count(*) from pg_class where relname = 'outra_tabela_do_projeto'").fetchone()[0] == 1
        assert psql(REVERSAO, "radar_reversao").returncode == 0      # reversão também é idempotente
        r = psql(SETUP, "radar_reversao")
        assert r.returncode == 0, r.stderr
    finally:
        with conectar("postgres") as c:
            c.execute("drop database if exists radar_reversao with (force)")


# ------------------------------------------- atalhos tentados pela revisão independente
def no_ar(db):
    a, c1 = cenario_publicavel(db)
    aprovar(c1)
    pid, _ = publicar(c1)
    return a, c1, pid


def test_titulo_e_corpo_da_publicacao_vem_sempre_do_conteudo_aprovado(limpo):
    _, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    with como("authenticated", EDITOR) as c:
        linha = c.execute("""insert into radar_publicacoes (conteudo_id, slug, titulo, corpo, status)
                             values (%s, 'x', 'Qualquer coisa', '<script>alert(1)</script>', 'publicado')
                             returning titulo, corpo""", (c1,)).fetchone()
    assert linha == ("CBS: o que muda", "Texto do informativo.")


def test_publicacao_no_ar_nao_aceita_troca_de_texto_endereco_nem_conteudo(limpo):
    a, c1, pid = no_ar(limpo)
    outro = novo_conteudo(limpo, novo_assunto(limpo, "em_verificacao"), "rascunho")
    with como("authenticated", EDITOR) as c:
        for campo, valor in [("conteudo_id", outro), ("titulo", "FALSO"), ("corpo", "texto nunca aprovado"), ("slug", "outro-endereco")]:
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR034"):
                c.execute(f"update radar_publicacoes set {campo} = %s where id = %s", (valor, pid))
        # o que continua permitido no ar: errata, categoria e reagendamento
        assert c.execute("update radar_publicacoes set errata = 'x', categoria = 'federal', publicar_em = now() where id = %s", (pid,)).rowcount == 1
    assert limpo.execute("select titulo, corpo, conteudo_id from radar_publicacoes where id = %s", (pid,)).fetchone() == \
        ("CBS: o que muda", "Texto do informativo.", c1)


def test_autoria_da_publicacao_nao_pode_ser_forjada(limpo):
    _, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    with como("authenticated", EDITOR) as c:
        linha = c.execute("""insert into radar_publicacoes (conteudo_id, slug, status, criado_por, publicado_por, publicado_em)
                             values (%s, 'y', 'publicado', %s, %s, '2020-01-01')
                             returning criado_por::text, publicado_por::text, publicado_em > now() - interval '1 minute', id""",
                          (c1, ADMIN, ADMIN)).fetchone()
        assert linha[:3] == (EDITOR, EDITOR, True)
        depois = c.execute("update radar_publicacoes set criado_por = %s, publicado_por = %s, criado_em = '2020-01-01' where id = %s "
                           "returning criado_por::text, publicado_por::text, criado_em > now() - interval '1 minute'",
                           (ADMIN, ADMIN, linha[3])).fetchone()
        assert depois == (EDITOR, EDITOR, True)


def test_robo_e_ia_nao_publicam_nem_tem_permissao_na_tabela(limpo):
    _, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    with como("service_role") as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into radar_publicacoes (conteudo_id, slug, status) values (%s, 'robo', 'publicado')", (c1,))
    # mesmo quem roda SQL direto (sem usuário logado) esbarra no portão
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR033"):
        limpo.execute("insert into radar_publicacoes (conteudo_id, slug, status) values (%s, 'sql', 'publicado')", (c1,))


def test_aprovador_e_data_nao_podem_ser_forjados_depois_de_aprovado(limpo):
    c1 = novo_conteudo(limpo, novo_assunto(limpo))
    aprovar(c1)
    for papel, uid in [("authenticated", EDITOR), ("service_role", None)]:
        with como(papel, uid) as c:
            linha = c.execute("update radar_conteudos set aprovado_por = %s, aprovado_em = '2020-01-01' where id = %s "
                              "returning status, aprovado_por::text, aprovado_em > now() - interval '1 minute'", (ADMIN, c1)).fetchone()
            assert linha == ("aprovado", EDITOR, True)


def test_conteudo_nao_muda_de_assunto_e_mudar_formato_derruba_aprovacao(limpo):
    c1 = novo_conteudo(limpo, novo_assunto(limpo))
    outro = novo_assunto(limpo)
    aprovar(c1)
    for papel, uid in [("authenticated", EDITOR), ("service_role", None)]:
        with como(papel, uid) as c:
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR021"):
                c.execute("update radar_conteudos set assunto_id = %s where id = %s", (outro, c1))
    with como("authenticated", EDITOR) as c:
        assert c.execute("update radar_conteudos set formato = 'artigo' where id = %s returning status", (c1,)).fetchone()[0] == "em_revisao"


@pytest.mark.parametrize("acao, motivo", [
    ("update radar_assuntos set situacao_confirmacao = 'divergencia_identificada' where id = %(a)s", "RADAR031"),
    ("delete from radar_evidencias where assunto_id = %(a)s", "RADAR032"),
    ("update radar_capturas set texto = 'Texto oficial substituído, sem o trecho citado na evidência.' "
     "where id in (select captura_id from radar_evidencias where assunto_id = %(a)s)", "RADAR032"),
    ("update radar_fontes set oficial = false where slug = 'rfb-normas'", "RADAR032"),
    ("update radar_conteudos set status = 'rejeitado' where id = %(c)s", "voltou para revisão"),
    ("update radar_conteudos set corpo = 'Texto reescrito.' where id = %(c)s", "voltou para revisão"),
])
def test_publicacao_no_ar_e_sinalizada_quando_um_prerequisito_cai(limpo, acao, motivo):
    a, c1, pid = no_ar(limpo)
    assert limpo.execute("select requer_revisao from radar_publicacoes where id = %s", (pid,)).fetchone()[0] is False
    try:
        limpo.execute(acao, {"a": a, "c": c1})
        linha = limpo.execute("select requer_revisao, motivo_revisao, status from radar_publicacoes where id = %s", (pid,)).fetchone()
        assert linha[0] is True and motivo in linha[1]
        assert linha[2] == "publicado"       # o sistema avisa; tirar do ar é decisão humana
    finally:
        limpo.execute("update radar_fontes set oficial = true where slug = 'rfb-normas'")


def test_republicar_limpa_a_sinalizacao(limpo):
    a, c1, pid = no_ar(limpo)
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_conteudos set corpo = 'Texto corrigido.' where id = %s", (c1,))
        c.execute("update radar_publicacoes set status = 'despublicado' where id = %s", (pid,))
        c.execute("update radar_conteudos set status = 'aprovado' where id = %s", (c1,))
        linha = c.execute("update radar_publicacoes set status = 'publicado' where id = %s "
                          "returning corpo, requer_revisao, motivo_revisao", (pid,)).fetchone()
    assert linha == ("Texto corrigido.", False, None)


def test_service_role_nao_grava_auditoria_nem_apaga_historico(limpo):
    nova_captura(limpo)
    with como("service_role") as c:
        for sql in ["insert into radar_auditoria (tabela, registro_id, acao) values ('radar_conteudos', '1', 'UPDATE')",
                    "delete from radar_capturas_versoes", "delete from radar_instalacoes", "delete from radar_capturas",
                    "update radar_fontes set oficial = true", "insert into radar_perfis (user_id, nome, papel) values (gen_random_uuid(), 'x', 'admin')",
                    "delete from radar_execucoes", "truncate radar_capturas cascade"]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)


def test_hash_e_calculado_pelo_banco_e_texto_sem_hash_tambem_reconfere(limpo):
    cap, a = nova_captura(limpo), novo_assunto(limpo)
    e = limpo.execute("insert into radar_evidencias (assunto_id, captura_id, trecho_literal) values (%s, %s, %s) returning id",
                      (a, cap, "O contribuinte deverá destacar a CBS no documento fiscal")).fetchone()[0]
    with como("service_role") as c:   # muda o texto e tenta manter o hash antigo
        c.execute("update radar_capturas set texto = 'mudou sem avisar o hash, e o trecho citado sumiu daqui' where id = %s", (cap,))
    assert limpo.execute("select versao, hash_conteudo = radar_hash_texto(texto) from radar_capturas where id = %s", (cap,)).fetchone() == (2, True)
    assert limpo.execute("select trecho_conferido from radar_evidencias where id = %s", (e,)).fetchone()[0] is False


def test_hash_do_banco_e_igual_ao_do_robo(limpo):
    from radar_util import hash_conteudo, normalizar_espacos
    for bruto in ["Art. 1º  A alíquota é de 0,9%.\n\n Art. 2º\xa0Vigência — “imediata”.", "  ação\tçãõ  ÁÉÍ  ", "x"]:
        texto = normalizar_espacos(bruto)          # o robô sempre grava o texto já normalizado
        assert limpo.execute("select radar_hash_texto(%s)", (texto,)).fetchone()[0] == hash_conteudo(texto)
        assert limpo.execute("select radar_hash_texto(%s)", (bruto,)).fetchone()[0] == hash_conteudo(bruto)


def test_trecho_so_de_pontuacao_nao_confere(limpo):
    cap = nova_captura(limpo, texto="Sumário .................................... página 3. Art. 1º Texto.")
    a = novo_assunto(limpo)
    ok = limpo.execute("insert into radar_evidencias (assunto_id, captura_id, trecho_literal) values (%s, %s, %s) returning trecho_conferido",
                       (a, cap, "....................................")).fetchone()[0]
    assert ok is False


def test_evidencia_vincula_a_captura_ao_assunto(limpo):
    cap, a = nova_captura(limpo), novo_assunto(limpo)
    limpo.execute("insert into radar_evidencias (assunto_id, captura_id, trecho_literal) values (%s, %s, 'qualquer trecho com mais de vinte')", (a, cap))
    assert limpo.execute("select count(*) from radar_assunto_capturas where assunto_id = %s and captura_id = %s", (a, cap)).fetchone()[0] == 1


def test_publico_nao_recebe_colunas_internas_da_publicacao(limpo):
    no_ar(limpo)
    with como("anon") as c:
        assert c.execute("select slug, titulo, corpo, categoria, errata from radar_publicacoes").fetchone()[:3] == \
            ("cbs-o-que-muda", "CBS: o que muda", "Texto do informativo.")
        for coluna in ["criado_por", "publicado_por", "conteudo_id", "requer_revisao", "motivo_revisao"]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(f"select {coluna} from radar_publicacoes")


def test_funcoes_nao_ficam_expostas_ao_publico(db):
    abertas = db.execute("""select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                            where n.nspname = 'public' and p.proname like 'radar\\_%'
                              and (has_function_privilege('anon', p.oid, 'execute')
                                   or (p.proname not in ('radar_papel', 'radar_abrir_assunto', 'radar_admin_usuarios',
                                                           'radar_registrar_uso_ia', 'radar_registrar_evidencia_ia')
                                       and has_function_privilege('authenticated', p.oid, 'execute')))""").fetchall()
    assert abertas == []
    semcaminho = db.execute("""select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                               where n.nspname = 'public' and p.proname like 'radar\\_%' and p.proconfig is null""").fetchall()
    assert semcaminho == []


def test_visao_de_saude_nao_e_acessivel_ao_publico(db):
    with como("anon") as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select * from radar_v_saude_fontes")
    assert db.execute("select has_table_privilege('anon', 'radar_v_saude_fontes', 'insert') "
                      "or has_table_privilege('authenticated', 'radar_v_saude_fontes', 'update')").fetchone()[0] is False


def test_setup_nao_mexe_em_sequencias_de_outros_apps():
    with conectar("postgres") as c:
        c.execute("drop database if exists radar_seq with (force)")
        c.execute("create database radar_seq")
    try:
        with conectar("radar_seq") as c:
            c.execute("create role outro_app nologin") if not c.execute("select 1 from pg_roles where rolname = 'outro_app'").fetchone() else None
            c.execute("create sequence public.outro_seq")
        assert psql(RAIZ / "testes" / "supabase_simulado.sql", "radar_seq").returncode == 0
        assert psql(SETUP, "radar_seq").returncode == 0
        with conectar("radar_seq") as c:
            assert c.execute("select has_sequence_privilege('authenticated', 'public.outro_seq', 'usage')").fetchone()[0] is False
    finally:
        with conectar("postgres") as c:
            c.execute("drop database if exists radar_seq with (force)")


def test_fonte_apagada_nao_volta_ao_reexecutar_o_setup(db):
    db.execute("update radar_fontes set ativo = true")
    with conectar("postgres") as c:
        c.execute("drop database if exists radar_m5 with (force)")
        c.execute("create database radar_m5")
    try:
        assert psql(RAIZ / "testes" / "supabase_simulado.sql", "radar_m5").returncode == 0
        assert psql(SETUP, "radar_m5").returncode == 0
        with conectar("radar_m5") as c:
            assert c.execute("select count(*) from radar_fontes").fetchone()[0] == 6
            c.execute("delete from radar_fontes where slug = 'cgibs-noticias'")
            c.execute("delete from radar_categorias where slug = 'informativos'")
        assert psql(SETUP, "radar_m5").returncode == 0
        with conectar("radar_m5") as c:
            assert c.execute("select count(*) from radar_fontes").fetchone()[0] == 5
            assert c.execute("select count(*) from radar_categorias").fetchone()[0] == 7
    finally:
        with conectar("postgres") as c:
            c.execute("drop database if exists radar_m5 with (force)")


# ------------------------------------------------ pontos da segunda revisão independente
def test_evidencia_e_captura_nao_mudam_de_dono(limpo):
    cap, a = nova_captura(limpo), novo_assunto(limpo)
    outro = novo_assunto(limpo)
    e = limpo.execute("insert into radar_evidencias (assunto_id, captura_id, trecho_literal) values (%s, %s, %s) returning id",
                      (a, cap, "O contribuinte deverá destacar a CBS no documento fiscal")).fetchone()[0]
    limpo.execute("insert into radar_fontes (slug, nome, orgao, oficial, tipo_coletor, url) values ('teste-portal', 'p', 'i', false, 'rss', 'u')")
    with como("service_role") as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR022"):
            c.execute("update radar_evidencias set assunto_id = %s where id = %s", (outro, e))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR011"):
            c.execute("update radar_capturas set fonte_id = (select id from radar_fontes where slug = 'teste-portal') where id = %s", (cap,))


def test_numero_da_versao_nao_e_gravavel_por_fora(limpo):
    cap = nova_captura(limpo)
    with como("service_role") as c:
        c.execute("update radar_capturas set texto = 'segunda redação do texto oficial' where id = %s", (cap,))
        c.execute("update radar_capturas set versao = 1 where id = %s", (cap,))
        c.execute("update radar_capturas set texto = 'terceira redação do texto oficial' where id = %s", (cap,))
        c.execute("""insert into radar_capturas (fonte_id, url, titulo, hash_titulo, versao)
                     select fonte_id, 'https://x.gov.br/v', 't', 'h', 99 from radar_capturas where id = %s""", (cap,))
    assert limpo.execute("select versao from radar_capturas order by id").fetchall() == [(3,), (1,)]
    assert limpo.execute("select versao, texto from radar_capturas_versoes order by versao").fetchall() == \
        [(1, TEXTO_OFICIAL), (2, "segunda redação do texto oficial")]


def test_sequencias_radar_nao_ficam_abertas(db):
    abertas = db.execute("""select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
                            where n.nspname = 'public' and c.relkind = 'S' and c.relname like 'radar\\_%'
                              and (has_sequence_privilege('anon', c.oid, 'usage, select, update')
                                   or has_sequence_privilege('authenticated', c.oid, 'usage, select, update')
                                   or has_sequence_privilege('service_role', c.oid, 'usage, select, update'))""").fetchall()
    assert abertas == []
    with como("service_role") as c:      # e o robô continua inserindo normalmente
        c.execute("insert into radar_execucoes (fonte_id) select id from radar_fontes limit 1")
    db.execute("delete from radar_execucoes")


def test_excluir_usuario_nao_trava_nem_deixa_autoria_orfa(limpo):
    temp = "00000000-0000-0000-0000-0000000000f1"
    limpo.execute("insert into auth.users (id, email) values (%s, 't')", (temp,))
    limpo.execute("insert into radar_perfis (user_id, nome, papel) values (%s, 'Temporária', 'editor')", (temp,))
    _, c1 = cenario_publicavel(limpo)
    aprovar(c1, temp)
    pid, quem = publicar(c1, temp)
    assert quem == temp
    # enquanto a pessoa existe, ninguém apaga a autoria
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_conteudos set aprovado_por = null where id = %s", (c1,))
        c.execute("update radar_publicacoes set criado_por = null, publicado_por = null where id = %s", (pid,))
    assert limpo.execute("select aprovado_por::text from radar_conteudos where id = %s", (c1,)).fetchone()[0] == temp
    assert limpo.execute("select criado_por::text, publicado_por::text from radar_publicacoes where id = %s", (pid,)).fetchone() == (temp, temp)
    # excluir a pessoa funciona e os campos ficam nulos (a trilha de auditoria guarda quem foi)
    limpo.execute("delete from auth.users where id = %s", (temp,))
    assert limpo.execute("select status, aprovado_por from radar_conteudos where id = %s", (c1,)).fetchone() == ("aprovado", None)
    assert limpo.execute("select status, criado_por, publicado_por from radar_publicacoes where id = %s", (pid,)).fetchone() == ("publicado", None, None)
    assert limpo.execute("select count(*) from radar_auditoria where usuario = %s", (temp,)).fetchone()[0] >= 2


def test_origem_do_texto_nao_se_reescreve(limpo):
    c1 = novo_conteudo(limpo, novo_assunto(limpo))
    aprovar(c1)
    with como("service_role") as c:
        linha = c.execute("update radar_conteudos set gerado_por = 'humano' where id = %s returning gerado_por, status", (c1,)).fetchone()
    assert linha == ("ia", "aprovado")


def test_logado_sem_perfil_nao_ve_publicacoes_por_dentro(limpo):
    no_ar(limpo)
    with como("authenticated", SEM_PERFIL) as c:
        assert c.execute("select count(*) from radar_publicacoes").fetchone()[0] == 0
    with como("authenticated", LEITOR) as c:
        assert c.execute("select count(*) from radar_publicacoes").fetchone()[0] == 1


# ============================================================ v0.2.0 — apoio às telas
def test_endereco_e_gerado_do_titulo_higienizado_e_nao_repete(limpo):
    a, c1 = cenario_publicavel(limpo)
    limpo.execute("update radar_conteudos set titulo = 'CBS: o que muda — transição (2027)!' where id = %s", (c1,))
    c2 = novo_conteudo(limpo, a)
    limpo.execute("update radar_conteudos set titulo = 'CBS: o que muda — transição (2027)!' where id = %s", (c2,))
    c3 = novo_conteudo(limpo, a)
    c4 = novo_conteudo(limpo, a)
    limpo.execute("update radar_conteudos set titulo = %s where id = %s", ("Título muito comprido " * 8, c4))
    with como("authenticated", EDITOR) as c:
        s1 = c.execute("insert into radar_publicacoes (conteudo_id) values (%s) returning slug, id", (c1,)).fetchone()
        s2 = c.execute("insert into radar_publicacoes (conteudo_id) values (%s) returning slug, id", (c2,)).fetchone()
        s3 = c.execute("insert into radar_publicacoes (conteudo_id, slug) values (%s, ' Meu Endereço <b>/../x ') returning slug", (c3,)).fetchone()
        s4 = c.execute("insert into radar_publicacoes (conteudo_id) values (%s) returning slug", (c4,)).fetchone()
        assert s1[0] == "cbs-o-que-muda-transicao-2027"
        assert s2[0] == f"cbs-o-que-muda-transicao-2027-{s2[1]}"
        assert s3[0] == "meu-endereco-b-x"
        assert len(s4[0]) <= 80 and not s4[0].endswith("-")
        # endereço não muda depois de criado, nem em rascunho
        assert c.execute("update radar_publicacoes set slug = 'outro' where id = %s returning slug", (s1[1],)).fetchone()[0] == s1[0]


def test_endereco_nao_colide_nem_em_caso_armado(limpo):
    a, c1 = cenario_publicavel(limpo)
    c2, c3 = novo_conteudo(limpo, a), novo_conteudo(limpo, a)
    with como("authenticated", EDITOR) as c:
        c.execute("insert into radar_publicacoes (conteudo_id, slug) values (%s, 'colide')", (c1,))
        prox = c.execute("select max(id) + 2 from radar_publicacoes").fetchone()[0]
        c.execute("insert into radar_publicacoes (conteudo_id, slug) values (%s, %s)", (c2, f"colide-{prox}"))
        s3 = c.execute("insert into radar_publicacoes (conteudo_id, slug) values (%s, 'colide') returning slug, id", (c3,)).fetchone()
    assert s3[1] == prox and s3[0].startswith(f"colide-{prox}-")


def test_um_conteudo_tem_uma_unica_publicacao_e_ela_nao_troca_de_conteudo(limpo):
    a, c1 = cenario_publicavel(limpo)
    outro = novo_conteudo(limpo, a)
    aprovar(c1)
    pid, _ = publicar(c1)
    with como("authenticated", EDITOR) as c:
        with pytest.raises(psycopg.errors.UniqueViolation):
            c.execute("insert into radar_publicacoes (conteudo_id, status) values (%s, 'publicado')", (c1,))
        c.execute("update radar_publicacoes set status = 'despublicado' where id = %s", (pid,))
        with pytest.raises(psycopg.errors.UniqueViolation):
            c.execute("insert into radar_publicacoes (conteudo_id) values (%s)", (c1,))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR035"):
            c.execute("update radar_publicacoes set conteudo_id = %s where id = %s", (outro, pid))


def test_tirar_do_ar_devolve_o_assunto_e_voltar_ao_ar_o_marca_publicado(limpo):
    a, c1, pid = no_ar(limpo)
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_publicacoes set errata = 'errata da versão antiga' where id = %s", (pid,))
        c.execute("update radar_publicacoes set status = 'despublicado' where id = %s", (pid,))
        assert c.execute("select status from radar_assuntos where id = %s", (a,)).fetchone()[0] == "aprovado"
        c.execute("update radar_publicacoes set status = 'publicado' where id = %s", (pid,))
        assert c.execute("select status from radar_assuntos where id = %s", (a,)).fetchone()[0] == "publicado"


def test_vinculo_de_normas_segue_so_evidencia_oficial_e_e_refeito_ao_republicar(limpo):
    limpo.execute("insert into radar_fontes (slug, nome, orgao, oficial, tipo_coletor, url) values ('teste-portal', 'p', 'i', false, 'rss', 'u')")
    cap_of, cap_nao = nova_captura(limpo), nova_captura(limpo, slug="teste-portal", url="https://portal.exemplo/x")
    a = novo_assunto(limpo)
    n1 = limpo.execute("insert into radar_normas (tipo, numero, orgao) values ('IN', '1', 'RFB') returning id").fetchone()[0]
    n2 = limpo.execute("insert into radar_normas (tipo, numero, orgao) values ('IN', '2', 'RFB') returning id").fetchone()[0]
    trecho = "O contribuinte deverá destacar a CBS no documento fiscal"
    e1 = limpo.execute("insert into radar_evidencias (assunto_id, captura_id, norma_id, trecho_literal) values (%s, %s, %s, %s) returning id",
                       (a, cap_of, n1, trecho)).fetchone()[0]
    limpo.execute("insert into radar_evidencias (assunto_id, captura_id, norma_id, trecho_literal) values (%s, %s, %s, %s)", (a, cap_nao, n2, trecho))
    c1 = novo_conteudo(limpo, a)
    aprovar(c1)
    pid, _ = publicar(c1)
    assert limpo.execute("select norma_id from radar_publicacao_normas where publicacao_id = %s", (pid,)).fetchall() == [(n1,)]
    limpo.execute("update radar_evidencias set norma_id = null where id = %s", (e1,))
    limpo.execute("insert into radar_evidencias (assunto_id, captura_id, norma_id, trecho_literal) values (%s, %s, %s, %s)",
                  (a, cap_of, n2, "Esta Instrução Normativa entra em vigor na data"))
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_publicacoes set status = 'despublicado' where id = %s", (pid,))
        c.execute("update radar_publicacoes set status = 'publicado' where id = %s", (pid,))
    assert limpo.execute("select norma_id from radar_publicacao_normas where publicacao_id = %s", (pid,)).fetchall() == [(n2,)]


def test_radar_nao_fica_sem_administrador(limpo):
    with como("authenticated", ADMIN) as c:
        for sql in ["update radar_perfis set papel = 'leitor' where user_id = %s", "update radar_perfis set ativo = false where user_id = %s",
                    "delete from radar_perfis where user_id = %s"]:
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR042"):
                c.execute(sql, (ADMIN,))
        # com um segundo administrador, a troca é permitida
        c.execute("update radar_perfis set papel = 'admin' where user_id = %s", (EDITOR,))
        assert c.execute("update radar_perfis set papel = 'leitor' where user_id = %s", (ADMIN,)).rowcount == 1
    limpo.execute("update radar_perfis set papel = 'admin' where user_id = %s", (ADMIN,))
    limpo.execute("update radar_perfis set papel = 'editor' where user_id = %s", (EDITOR,))


def test_abrir_assunto_simultaneo_nao_duplica(limpo):
    import threading
    cap = nova_captura(limpo)
    ids, erros = [], []

    def abrir():
        try:
            with como("authenticated", EDITOR) as c:
                ids.append(c.execute("select radar_abrir_assunto(%s)", (cap,)).fetchone()[0])
        except Exception as e:      # pragma: no cover
            erros.append(e)

    fios = [threading.Thread(target=abrir) for _ in range(8)]
    [f.start() for f in fios]
    [f.join() for f in fios]
    assert erros == [] and len(set(ids)) == 1
    assert limpo.execute("select count(*) from radar_assuntos").fetchone()[0] == 1


def test_painel_separa_no_ar_de_agendadas(limpo):
    a, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    publicar(c1, quando="now() + interval '3 days'")
    assert limpo.execute("select no_ar, agendadas from radar_v_painel").fetchone() == (0, 1)


def test_publicacao_congela_a_fundamentacao_conferida_e_o_publico_a_le(limpo):
    cap = nova_captura(limpo)
    a = novo_assunto(limpo)
    limpo.execute("update radar_assuntos set categoria = 'reforma-tributaria' where id = %s", (a,))
    n = limpo.execute("insert into radar_normas (tipo, numero, orgao) values ('Instrução Normativa', '2290', 'RFB') returning id").fetchone()[0]
    limpo.execute("insert into radar_evidencias (assunto_id, captura_id, norma_id, dispositivo, trecho_literal) values (%s, %s, %s, 'art. 2º', %s)",
                  (a, cap, n, "à alíquota de 0,9% (nove décimos por cento)"))
    limpo.execute("insert into radar_evidencias (assunto_id, captura_id, trecho_literal) values (%s, %s, 'Art. 9º dispositivo inventado que não existe')", (a, cap))
    c1 = novo_conteudo(limpo, a)
    aprovar(c1)
    pid, _ = publicar(c1)
    with como("anon") as c:
        formato, categoria, fund = c.execute("select formato, categoria, fundamentacao from radar_publicacoes").fetchone()
    assert (formato, categoria) == ("informativo", "reforma-tributaria")
    assert len(fund) == 1                                   # a evidência não conferida fica de fora
    assert fund[0]["trecho"] == "à alíquota de 0,9% (nove décimos por cento)" and fund[0]["dispositivo"] == "art. 2º"
    assert fund[0]["orgao"] == "Receita Federal do Brasil" and fund[0]["url"] == "https://exemplo.gov.br/in-2290"
    assert fund[0]["norma"] == "Instrução Normativa nº 2290 — RFB"
    # efeitos: assunto publicado e norma vinculada à publicação
    assert limpo.execute("select status from radar_assuntos where id = %s", (a,)).fetchone()[0] == "publicado"
    assert limpo.execute("select norma_id from radar_publicacao_normas where publicacao_id = %s", (pid,)).fetchall() == [(n,)]
    # mexer nas evidências depois não altera o que está no ar; forjar a coluna também não
    limpo.execute("update radar_evidencias set trecho_literal = 'Art. 3º Esta Instrução Normativa entra em vigor' where assunto_id = %s", (a,))
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_publicacoes set fundamentacao = '[{\"trecho\": \"forjado\"}]'::jsonb, formato = 'flash' where id = %s", (pid,))
    assert limpo.execute("select fundamentacao, formato from radar_publicacoes where id = %s", (pid,)).fetchone() == (fund, "informativo")


def test_fundamentacao_nao_pode_ser_informada_em_rascunho(limpo):
    _, c1 = cenario_publicavel(limpo)
    with como("authenticated", EDITOR) as c:
        linha = c.execute("""insert into radar_publicacoes (conteudo_id, fundamentacao) values (%s, '[{"trecho": "forjado"}]'::jsonb)
                             returning fundamentacao, id""", (c1,)).fetchone()
        assert linha[0] == []
        assert c.execute("update radar_publicacoes set fundamentacao = '[{\"trecho\": \"x\"}]'::jsonb where id = %s returning fundamentacao",
                         (linha[1],)).fetchone()[0] == []


def test_abrir_assunto_a_partir_da_captura_e_fila_de_triagem(limpo):
    c1 = nova_captura(limpo, slug="sefsc-legislacao", url="https://x.gov.br/1")
    c2 = nova_captura(limpo, url="https://x.gov.br/2")
    c3 = nova_captura(limpo, url="https://x.gov.br/3")
    with como("authenticated", EDITOR) as c:
        assert c.execute("select count(*) from radar_v_fila").fetchone()[0] == 3
        a = c.execute("select radar_abrir_assunto(%s)", (c1,)).fetchone()[0]
        assert c.execute("select radar_abrir_assunto(%s)", (c1,)).fetchone()[0] == a          # não duplica
        ign = c.execute("select radar_abrir_assunto(%s, true)", (c2,)).fetchone()[0]
        assert c.execute("select titulo, categoria, abrangencia, status from radar_assuntos where id = %s", (a,)).fetchone() == \
            ("IN RFB nº 2290", "santa-catarina", "estadual_sc", "capturado")
        assert c.execute("select status from radar_assuntos where id = %s", (ign,)).fetchone()[0] == "ignorado"
        assert c.execute("select id from radar_v_fila").fetchall() == [(c3,)]
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR041"):
            c.execute("select radar_abrir_assunto(999999)")
    with como("authenticated", LEITOR) as c:
        assert c.execute("select count(*) from radar_v_fila").fetchone()[0] == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select radar_abrir_assunto(%s)", (c3,))
    with como("anon") as c:
        for sql in ["select radar_abrir_assunto(1)", "select * from radar_v_fila", "select * from radar_v_assuntos",
                    "select * from radar_v_painel", "select * from radar_admin_usuarios()"]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)


def test_lista_de_usuarios_so_para_o_administrador(limpo):
    with como("authenticated", ADMIN) as c:
        linhas = c.execute("select user_id::text, papel from radar_admin_usuarios()").fetchall()
        assert (ADMIN, "admin") in linhas and (SEM_PERFIL, None) in linhas
    for uid in (EDITOR, LEITOR, SEM_PERFIL):
        with como("authenticated", uid) as c:
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR040"):
                c.execute("select * from radar_admin_usuarios()")


def test_painel_e_lista_de_assuntos_trazem_os_numeros_certos(limpo):
    a, c1, pid = no_ar(limpo)
    nova_captura(limpo, url="https://x.gov.br/na-fila")
    outro = novo_assunto(limpo, "em_verificacao")
    limpo.execute("update radar_assuntos set relevancia = 'alta' where id = %s", (outro,))
    novo_conteudo(limpo, outro)
    with como("authenticated", LEITOR) as c:
        p = c.execute("select fontes_ativas, na_fila, alta_relevancia, em_verificacao, aguardando_aprovacao, no_ar, requer_revisao "
                      "from radar_v_painel").fetchone()
        assert p == (6, 1, 1, 1, 1, 1, 0)
        assert c.execute("select agendadas from radar_v_painel").fetchone()[0] == 0
        linha = c.execute("select evidencias, evidencias_conferidas, conteudos, publicacoes_no_ar, orgaos, status "
                          "from radar_v_assuntos where id = %s", (a,)).fetchone()
        assert linha == (1, 1, 1, 1, "Receita Federal do Brasil", "publicado")
    with como("authenticated", SEM_PERFIL) as c:
        assert c.execute("select na_fila, no_ar from radar_v_painel").fetchone() == (0, 0)
        assert c.execute("select count(*) from radar_v_assuntos").fetchone()[0] == 0


def test_atualizacao_da_v0_1_0_para_a_v0_2_0_preserva_os_dados():
    with conectar("postgres") as c:
        c.execute("drop database if exists radar_up with (force)")
        c.execute("create database radar_up")
    try:
        assert psql(RAIZ / "testes" / "supabase_simulado.sql", "radar_up").returncode == 0
        r = psql(RAIZ / "testes" / "radar-setup-v0.1.0-referencia.sql", "radar_up")
        assert r.returncode == 0, r.stderr
        with conectar("radar_up") as c:
            c.execute("insert into auth.users (id, email) values (%s, 'e')", (EDITOR,))
            c.execute("insert into radar_perfis (user_id, nome, papel) values (%s, 'E', 'editor')", (EDITOR,))
            c.execute("update radar_fontes set frequencia_horas = 3 where slug = 'pgfn-noticias'")
            c.execute("delete from radar_fontes where slug = 'cgibs-noticias'")
            cap = nova_captura(c)
            a = novo_assunto(c)
            c.execute("insert into radar_evidencias (assunto_id, captura_id, trecho_literal) values (%s, %s, %s)",
                      (a, cap, "à alíquota de 0,9% (nove décimos por cento)"))
            c1 = novo_conteudo(c, a)
            c.execute("select set_config('request.jwt.claims', %s, false)", (json.dumps({"role": "authenticated", "sub": EDITOR}),))
            c.execute("set role authenticated")
            c.execute("update radar_conteudos set status = 'aprovado' where id = %s", (c1,))
            c.execute("insert into radar_publicacoes (conteudo_id, slug, status) values (%s, 'antiga', 'publicado')", (c1,))
        r = psql(SETUP, "radar_up")
        assert r.returncode == 0, r.stderr
        with conectar("radar_up") as c:
            assert c.execute("select slug, status, titulo, corpo, fundamentacao, publicado_por::text from radar_publicacoes").fetchone() == \
                ("antiga", "publicado", "CBS: o que muda", "Texto do informativo.", [], EDITOR)
            assert c.execute("select status, aprovado_por::text from radar_conteudos").fetchone() == ("aprovado", EDITOR)
            assert c.execute("select frequencia_horas from radar_fontes where slug = 'pgfn-noticias'").fetchone()[0] == 3
            assert c.execute("select count(*) from radar_fontes").fetchone()[0] == 5
            assert c.execute("select array_agg(versao order by id) from radar_instalacoes").fetchone()[0] == ["v0.1.0", "v0.4.0"]
            assert c.execute("select count(*) from radar_v_painel").fetchone()[0] == 1
    finally:
        with conectar("postgres") as c:
            c.execute("drop database if exists radar_up with (force)")


# ------------------------------------------------ pontos da reverificação das telas
def test_dois_rebaixamentos_simultaneos_nao_deixam_o_radar_sem_administrador(limpo):
    import threading
    limpo.execute("update radar_perfis set papel = 'admin' where user_id = %s", (EDITOR,))
    largada, resultados = threading.Barrier(2), []

    def rebaixar(uid, sql):
        c = conectar(autocommit=False)
        try:
            c.execute(sql, (uid,))            # ainda não confirmado: a outra transação não enxerga
            largada.wait(timeout=5)
            c.commit()
            resultados.append("ok")
        except Exception as e:
            c.rollback()
            resultados.append("RADAR042" if "RADAR042" in str(e) else repr(e))
        finally:
            c.close()

    fios = [threading.Thread(target=rebaixar, args=(ADMIN, "update radar_perfis set papel = 'leitor' where user_id = %s")),
            threading.Thread(target=rebaixar, args=(EDITOR, "update radar_perfis set ativo = false where user_id = %s"))]
    [f.start() for f in fios]
    [f.join(timeout=20) for f in fios]
    try:
        assert limpo.execute("select count(*) from radar_perfis where papel = 'admin' and ativo").fetchone()[0] >= 1, resultados
    finally:
        limpo.execute("update radar_perfis set papel = 'admin', ativo = true where user_id = %s", (ADMIN,))
        limpo.execute("update radar_perfis set papel = 'editor', ativo = true where user_id = %s", (EDITOR,))


def test_abrir_assunto_com_numero_enorme_da_mensagem_clara(limpo):
    with como("authenticated", EDITOR) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR041"):
            c.execute("select radar_abrir_assunto(3000000000)")


def test_errata_so_some_quando_o_texto_republicado_e_outro(limpo):
    a, c1, pid = no_ar(limpo)
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_publicacoes set errata = 'correção 1' where id = %s", (pid,))
        c.execute("update radar_publicacoes set status = 'despublicado' where id = %s", (pid,))
        # mesmo texto volta ao ar: a errata continua valendo
        assert c.execute("update radar_publicacoes set status = 'publicado' where id = %s returning errata", (pid,)).fetchone()[0] == "correção 1"
        # texto novo aprovado volta ao ar: a errata antiga sai; uma errata nova informada junto fica
        c.execute("update radar_publicacoes set status = 'despublicado' where id = %s", (pid,))
        c.execute("update radar_conteudos set corpo = 'Texto novo.' where id = %s", (c1,))
        c.execute("update radar_conteudos set status = 'aprovado' where id = %s", (c1,))
        assert c.execute("update radar_publicacoes set status = 'publicado' where id = %s returning errata, corpo", (pid,)).fetchone() == (None, "Texto novo.")


def test_setup_atualiza_visao_do_painel_de_uma_copia_intermediaria():
    with conectar("postgres") as c:
        c.execute("drop database if exists radar_vp with (force)")
        c.execute("create database radar_vp")
    try:
        assert psql(RAIZ / "testes" / "supabase_simulado.sql", "radar_vp").returncode == 0
        assert psql(SETUP, "radar_vp").returncode == 0
        with conectar("radar_vp") as c:
            c.execute("drop view radar_v_painel")
            c.execute("create view radar_v_painel as select 1 as fontes_ativas, 2 as requer_revisao")
        r = psql(SETUP, "radar_vp")
        assert r.returncode == 0, r.stderr
        with conectar("radar_vp") as c:
            assert c.execute("select no_ar, agendadas from radar_v_painel").fetchone() == (0, 0)
            assert c.execute("select has_table_privilege('authenticated', 'radar_v_painel', 'select'), "
                             "has_table_privilege('anon', 'radar_v_painel', 'select')").fetchone() == (True, False)
    finally:
        with conectar("postgres") as c:
            c.execute("drop database if exists radar_vp with (force)")


# ============================================================ v0.3.0 — registro de uso da IA
def test_uso_da_ia_so_e_registrado_pela_funcao_do_banco_com_valores_limitados(limpo):
    a = novo_assunto(limpo)
    with como("authenticated", EDITOR) as c:
        c.execute("select radar_registrar_uso_ia('gerar', 'm', 100, 50, %s)", (a,))
        c.execute("select radar_registrar_uso_ia('classificar', %s, 2147483647, -5, 999999)", ("x" * 300,))   # exagero e assunto inexistente
        linhas = c.execute("select usuario::text, acao, length(modelo), tokens_entrada, tokens_saida, assunto_id, em > now() - interval '1 minute' "
                           "from radar_ia_uso order by id").fetchall()
        assert linhas == [(EDITOR, "gerar", 1, 100, 50, a, True), (EDITOR, "classificar", 80, 5000000, 0, None, True)]
        # direto na tabela, nada: nem inserir linha falsa, nem alterar, nem apagar
        for sql in ["insert into radar_ia_uso (acao, modelo, tokens_entrada, tokens_saida) values ('gerar', 'm', 2147483647, 2147483647)",
                    "update radar_ia_uso set tokens_entrada = 0", "delete from radar_ia_uso"]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)
        assert c.execute("select chamadas, tokens_entrada, tokens_saida, tokens from radar_v_ia_mes").fetchone() == (2, 5000100, 50, 5000150)
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute("select radar_registrar_uso_ia('apagar', 'm', 1, 1, null)")
    with como("authenticated", LEITOR) as c:
        assert c.execute("select tokens from radar_v_ia_mes").fetchone()[0] == 5000150
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR050"):
            c.execute("select radar_registrar_uso_ia('gerar', 'm', 1, 1, null)")
    with como("anon") as c:
        for sql in ["select * from radar_ia_uso", "select * from radar_v_ia_mes", "select radar_registrar_uso_ia('gerar', 'm', 1, 1, null)",
                    "select radar_registrar_evidencia_ia(1, 1, 'x', null)"]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)
    # nem com valores no teto a soma do mês estoura
    limpo.execute("alter table radar_ia_uso disable trigger user")
    limpo.execute("insert into radar_ia_uso (acao, modelo, tokens_entrada, tokens_saida) select 'gerar', 'm', 5000000, 5000000 from generate_series(1, 500)")
    limpo.execute("alter table radar_ia_uso enable trigger user")
    assert limpo.execute("select tokens from radar_v_ia_mes").fetchone()[0] == 5005000150
    with pytest.raises(psycopg.errors.CheckViolation):
        limpo.execute("insert into radar_ia_uso (acao, modelo, tokens_entrada) values ('gerar', 'm', 5000001)")


def test_evidencia_da_ia_so_e_gravada_se_o_banco_conferir(limpo):
    limpo.execute("insert into radar_fontes (slug, nome, orgao, oficial, tipo_coletor, url) values ('teste-portal', 'p', 'i', false, 'rss', 'u')")
    cap = nova_captura(limpo)
    fino = nova_captura(limpo, url="https://x.gov.br/espaco-fino", texto="O limite passa a ser de R$\u202f4.800.000,00 por ano-calendário para todos.")
    blog = nova_captura(limpo, slug="teste-portal", url="https://portal.exemplo/x")
    solta = nova_captura(limpo, url="https://x.gov.br/de-outro-assunto")
    a = novo_assunto(limpo)
    for c_ in (cap, fino, blog):
        limpo.execute("insert into radar_assunto_capturas values (%s, %s)", (a, c_))
    bom = "O contribuinte deverá destacar a CBS no documento fiscal"
    with como("authenticated", EDITOR) as c:
        chamar = lambda captura, trecho, disp=None: c.execute("select radar_registrar_evidencia_ia(%s, %s, %s, %s)", (a, captura, trecho, disp)).fetchone()[0]
        assert chamar(cap, "Art. 9º Fica instituída multa de 75% sobre o valor") is None          # inventado
        assert chamar(blog, bom) is None                                                           # fonte não oficial
        assert chamar(solta, bom) is None                                                          # captura de outro assunto
        assert chamar(fino, "O limite passa a ser de R$ 4.800.000,00 por ano-calendário") is None  # espaço diferente do oficial
        assert chamar(999999, bom) is None
        assert c.execute("select count(*) from radar_evidencias").fetchone()[0] == 0               # nada "não conferido" fica para trás
        eid = chamar(cap, bom, "  art. 2º  ")
        assert c.execute("select trecho_conferido, dispositivo, natureza from radar_evidencias where id = %s", (eid,)).fetchone() == (True, "art. 2º", "fato_oficial")
    assert limpo.execute("select usuario::text from radar_auditoria where tabela = 'radar_evidencias'").fetchall() == [(EDITOR,)]
    with como("authenticated", LEITOR) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR050"):
            c.execute("select radar_registrar_evidencia_ia(%s, %s, %s, null)", (a, cap, bom))


def test_consumo_do_mes_nao_soma_meses_anteriores(limpo):
    limpo.execute("alter table radar_ia_uso disable trigger user")
    limpo.execute("insert into radar_ia_uso (acao, modelo, tokens_entrada, tokens_saida, em) values ('gerar', 'm', 999, 1, now() - interval '40 days')")
    limpo.execute("alter table radar_ia_uso enable trigger user")
    assert limpo.execute("select chamadas, tokens from radar_v_ia_mes").fetchone() == (0, 0)


def test_avisos_e_origem_do_texto_da_ia_nao_se_apagam(limpo):
    a = novo_assunto(limpo)
    with como("authenticated", EDITOR) as c:
        cid = c.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo, gerado_por, modelo_ia, avisos_ia)
                           values (%s, 'flash', 't', 'c', 'ia', 'gpt-x', '["conferir a alíquota"]'::jsonb) returning id""", (a,)).fetchone()[0]
        c.execute("update radar_conteudos set avisos_ia = '[]'::jsonb, gerado_por = 'humano', modelo_ia = null, corpo = 'editado' where id = %s", (cid,))
        assert c.execute("select avisos_ia, gerado_por, modelo_ia, corpo from radar_conteudos where id = %s", (cid,)).fetchone() == \
            (["conferir a alíquota"], "ia", "gpt-x", "editado")
        # texto escrito pela equipe não carrega avisos nem modelo
        humano = c.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo, gerado_por, modelo_ia, avisos_ia)
                              values (%s, 'flash', 't', 'c', 'humano', 'gpt-x', '["x"]'::jsonb) returning modelo_ia, avisos_ia""", (a,)).fetchone()
        assert humano == (None, [])


# ============================================================ v0.4.0 — imagens, configurações e Informativo Mensal
PIXEL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def nova_imagem(uid=EDITOR, dados=PIXEL):
    with como("authenticated", uid) as c:
        return c.execute("insert into radar_imagens (dados, largura, altura) values (%s, 1, 1) returning id", (dados,)).fetchone()[0]


def test_imagem_so_aceita_data_uri_de_imagem_dentro_do_limite(limpo):
    assert nova_imagem() > 0
    for ruim in ["https://site.com/foto.jpg", "data:text/html;base64,PHNjcmlwdD4=", "data:image/svg+xml;base64,PHN2Zz4=",
                 "data:image/png;base64,AAAA\"><script>", "data:image/jpeg;base64," + "A" * 900000,
                 "data:image/png;base64,====", "data:image/png;base64,", "data:image/PNG;base64," + "A" * 60, "data:image/png;base64," + "A" * 50 + "\n" + "A" * 50]:
        with pytest.raises(psycopg.errors.CheckViolation):
            nova_imagem(dados=ruim)


def test_imagem_com_dimensoes_absurdas_e_recusada(limpo):
    with como("authenticated", EDITOR) as c:
        for larg, alt in ((-5, 10), (10, 2000000000), (0, 0)):
            with pytest.raises(psycopg.errors.CheckViolation):
                c.execute("insert into radar_imagens (dados, largura, altura) values (%s, %s, %s)", (PIXEL, larg, alt))


def test_imagem_registra_quem_enviou_nao_se_altera_e_leitor_nao_envia(limpo):
    with como("authenticated", EDITOR) as c:
        i, autor = c.execute("insert into radar_imagens (dados, criado_por) values (%s, %s) returning id, criado_por::text",
                             (PIXEL, ADMIN)).fetchone()
        assert autor == EDITOR                                     # o autor não se forja
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("update radar_imagens set dados = %s where id = %s", (PIXEL, i))
        assert c.execute("delete from radar_imagens where id = %s returning id", (i,)).fetchone() is None   # só admin apaga
    for papel, uid in (("authenticated", LEITOR), ("authenticated", SEM_PERFIL)):
        with como(papel, uid) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into radar_imagens (dados) values (%s)", (PIXEL,))
    for papel in ("anon", "service_role"):
        with como(papel) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into radar_imagens (dados) values (%s)", (PIXEL,))


def test_publico_so_baixa_imagem_de_publicacao_no_ar(limpo):
    a, _ = cenario_publicavel(limpo)
    c1 = novo_conteudo(limpo, a)
    usada, solta = nova_imagem(), nova_imagem()
    limpo.execute("update radar_conteudos set imagem_id = %s, autor = 'Marcos Vinicius', fonte_credito = 'Receita Federal' where id = %s", (usada, c1))
    aprovar(c1)
    with como("anon") as c:
        assert c.execute("select count(*) from radar_imagens").fetchone()[0] == 0         # nada no ar ainda
    pid, _ = publicar(c1)
    with como("anon") as c:
        assert c.execute("select id from radar_imagens").fetchall() == [(usada,)]          # a solta não aparece
        assert c.execute("select imagem_id, autor, fonte_credito from radar_publicacoes").fetchone() == (usada, "Marcos Vinicius", "Receita Federal")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select criado_por from radar_imagens")                             # quem enviou não é público
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_publicacoes set status = 'despublicado' where id = %s", (pid,))
    with como("anon") as c:
        assert c.execute("select count(*) from radar_imagens").fetchone()[0] == 0
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_publicacoes set status = 'publicado', publicar_em = now() + interval '2 days' where id = %s", (pid,))
    with como("anon") as c:
        assert c.execute("select count(*) from radar_imagens").fetchone()[0] == 0         # agendada: ainda não
    assert solta


def test_imagem_autor_e_fonte_da_publicacao_vem_do_conteudo_e_nao_mudam_no_ar(limpo):
    a, _ = cenario_publicavel(limpo)
    c1 = novo_conteudo(limpo, a)
    img, outra = nova_imagem(), nova_imagem()
    limpo.execute("update radar_conteudos set imagem_id = %s, autor = 'Equipe Fiscal' where id = %s", (img, c1))
    aprovar(c1)
    with como("authenticated", EDITOR) as c:        # tentar informar outros valores na publicação não adianta
        pid = c.execute("""insert into radar_publicacoes (conteudo_id, slug, status, imagem_id, autor, fonte_credito)
                           values (%s, 'x', 'publicado', %s, 'Forjado', 'Forjada') returning id""", (c1, outra)).fetchone()[0]
        assert c.execute("select imagem_id, autor, fonte_credito from radar_publicacoes where id = %s", (pid,)).fetchone() == (img, "Equipe Fiscal", None)
        c.execute("update radar_publicacoes set imagem_id = %s, autor = 'Outro', fonte_credito = 'Outra' where id = %s", (outra, pid))
        assert c.execute("select imagem_id, autor, fonte_credito from radar_publicacoes where id = %s", (pid,)).fetchone() == (img, "Equipe Fiscal", None)
    # imagem usada por publicação não pode ser apagada nem pelo administrador
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.ForeignKeyViolation):
        c.execute("delete from radar_imagens where id = %s", (img,))


def test_trocar_imagem_autor_ou_fonte_de_conteudo_aprovado_volta_para_revisao(limpo):
    a = novo_assunto(limpo)
    for campo, valor in (("imagem_id", None), ("autor", "Novo autor"), ("fonte_credito", "Nova fonte")):
        c1 = novo_conteudo(limpo, a)
        aprovar(c1)
        if campo == "imagem_id":
            valor = nova_imagem()
        with como("authenticated", EDITOR) as c:
            assert c.execute(f"update radar_conteudos set {campo} = %s where id = %s returning status", (valor, c1)).fetchone()[0] == "em_revisao"


def test_configuracoes_iniciais_e_quem_pode_alterar(limpo):
    conf = dict(limpo.execute("select chave, valor from radar_config").fetchall())
    assert set(conf) == {"obrigacoes", "feriados_extras", "fale_conosco", "assinatura"}
    assert len(conf["obrigacoes"]) == 22 and conf["assinatura"]["responsavel"] == "Cleiver Gonçalves"
    assert all(o["regra"] in ("quinto_dia_util", "dia", "ultimo_dia_util") for o in conf["obrigacoes"])
    with como("authenticated", LEITOR) as c:
        assert c.execute("select count(*) from radar_config").fetchone()[0] == 4          # a equipe lê
    with como("authenticated", EDITOR) as c:
        assert c.execute("update radar_config set valor = '[]' where chave = 'feriados_extras' returning chave").fetchone() is None
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into radar_config (chave, valor) values ('nova', '1')")
    with como("authenticated", SEM_PERFIL) as c:
        assert c.execute("select count(*) from radar_config").fetchone()[0] == 0          # logado sem perfil: nenhuma linha
    with como("anon") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("select count(*) from radar_config")                                    # visitante: sem acesso à tabela
    try:
        with como("authenticated", ADMIN) as c:
            assert c.execute("""update radar_config set valor = '["2026-12-24"]' where chave = 'feriados_extras' returning valor""").fetchone()[0] == ["2026-12-24"]
        # reexecutar o setup NÃO desfaz o ajuste do administrador
        assert psql(SETUP).returncode == 0
        assert limpo.execute("select valor from radar_config where chave = 'feriados_extras'").fetchone()[0] == ["2026-12-24"]
        aud = limpo.execute("select acao, usuario::text, registro_id from radar_auditoria where tabela = 'radar_config' order by id desc limit 1").fetchone()
        assert aud == ("UPDATE", ADMIN, "feriados_extras")
    finally:
        limpo.execute("update radar_config set valor = '[]' where chave = 'feriados_extras'")


def novo_informativo(uid=EDITOR, numero=10, ano=2026, mes="2026-10-01"):
    with como("authenticated", uid) as c:
        return c.execute("""insert into radar_informativos (numero, ano, mes, agenda)
                            values (%s, %s, %s, '[{"data": "2026-10-06", "obrigacoes": ["Salário"]}]') returning id""",
                         (numero, ano, mes)).fetchone()[0]


def test_informativo_so_recebe_conteudo_aprovado(limpo):
    a = novo_assunto(limpo, "em_verificacao")            # assunto criado pela equipe, sem captura nem fonte oficial
    rascunho, aprovado = novo_conteudo(limpo, a, "rascunho"), novo_conteudo(limpo, a)
    aprovar(aprovado)
    i = novo_informativo()
    with como("authenticated", EDITOR) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR060"):
            c.execute("insert into radar_informativo_itens (informativo_id, conteudo_id) values (%s, %s)", (i, rascunho))
        c.execute("insert into radar_informativo_itens (informativo_id, conteudo_id, ordem) values (%s, %s, 10)", (i, aprovado))
        with pytest.raises(psycopg.errors.UniqueViolation):
            c.execute("insert into radar_informativo_itens (informativo_id, conteudo_id) values (%s, %s)", (i, aprovado))
        assert c.execute("select criado_por::text from radar_informativos where id = %s", (i,)).fetchone()[0] == EDITOR
    # conteúdo que está em um informativo não pode ser apagado por baixo dele
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.ForeignKeyViolation):
        c.execute("delete from radar_conteudos where id = %s", (aprovado,))


def test_informativo_numero_nao_repete_no_ano_e_mes_e_sempre_dia_primeiro(limpo):
    novo_informativo()
    with pytest.raises(psycopg.errors.UniqueViolation):
        novo_informativo()
    assert novo_informativo(numero=10, ano=2027, mes="2027-10-01")
    with pytest.raises(psycopg.errors.CheckViolation):
        novo_informativo(numero=11, mes="2026-10-15")
    with pytest.raises(psycopg.errors.CheckViolation):
        novo_informativo(numero=0)


def test_informativo_fechado_nao_muda_e_so_administrador_reabre(limpo):
    a = novo_assunto(limpo)
    c1, c2 = novo_conteudo(limpo, a), novo_conteudo(limpo, a)
    aprovar(c1), aprovar(c2)
    i = novo_informativo()
    with como("authenticated", EDITOR) as c:
        c.execute("insert into radar_informativo_itens (informativo_id, conteudo_id) values (%s, %s)", (i, c1))
        c.execute("update radar_informativos set status = 'fechado' where id = %s", (i,))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR061"):
            c.execute("update radar_informativos set numero = 11 where id = %s", (i,))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR061"):
            c.execute("insert into radar_informativo_itens (informativo_id, conteudo_id) values (%s, %s)", (i, c2))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR061"):
            c.execute("update radar_informativo_itens set ordem = 1 where informativo_id = %s", (i,))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR061"):
            c.execute("delete from radar_informativo_itens where informativo_id = %s", (i,))
        assert c.execute("select fechado_em is not null from radar_informativos where id = %s", (i,)).fetchone()[0]
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR062"):
            c.execute("update radar_informativos set status = 'rascunho' where id = %s", (i,))
    with como("authenticated", ADMIN) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR061"):
            c.execute("delete from radar_informativo_itens where informativo_id = %s", (i,))
        c.execute("update radar_informativos set status = 'rascunho' where id = %s", (i,))
        assert c.execute("select fechado_em from radar_informativos where id = %s", (i,)).fetchone()[0] is None
        c.execute("update radar_informativos set numero = 11 where id = %s", (i,))
        assert c.execute("delete from radar_informativo_itens where informativo_id = %s returning conteudo_id", (i,)).fetchall() == [(c1,)]
    aud = limpo.execute("select acao, usuario::text from radar_auditoria where tabela = 'radar_informativos' order by id").fetchall()
    assert aud[0] == ("INSERT", EDITOR) and aud[-1] == ("UPDATE", ADMIN)


def test_informativo_nao_fecha_com_conteudo_que_deixou_de_estar_aprovado(limpo):
    a = novo_assunto(limpo)
    c1 = novo_conteudo(limpo, a)
    aprovar(c1)
    i = novo_informativo()
    with como("authenticated", EDITOR) as c:
        c.execute("insert into radar_informativo_itens (informativo_id, conteudo_id) values (%s, %s)", (i, c1))
        c.execute("update radar_conteudos set corpo = 'Texto alterado depois de aprovado.' where id = %s", (c1,))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR063"):
            c.execute("update radar_informativos set status = 'fechado' where id = %s", (i,))
        c.execute("update radar_conteudos set status = 'aprovado' where id = %s", (c1,))
        c.execute("update radar_informativos set status = 'fechado' where id = %s", (i,))


def test_informativo_leitor_consulta_e_quem_esta_de_fora_nao_ve_nem_grava(limpo):
    i = novo_informativo()
    with como("authenticated", LEITOR) as c:
        assert c.execute("select count(*) from radar_informativos").fetchone()[0] == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into radar_informativos (numero, ano, mes) values (12, 2026, '2026-12-01')")
        assert c.execute("update radar_informativos set numero = 99 where id = %s returning id", (i,)).fetchone() is None
    with como("authenticated", SEM_PERFIL) as c:
        assert c.execute("select count(*) from radar_informativos").fetchone()[0] == 0
    for papel in ("anon", "service_role"):
        with como(papel) as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute("insert into radar_informativos (numero, ano, mes) values (12, 2026, '2026-12-01')")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute("insert into radar_config (chave, valor) values ('x', '1')")
    with como("anon") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("select * from radar_informativos")
    with como("authenticated", EDITOR) as c:
        assert c.execute("delete from radar_informativos where id = %s returning id", (i,)).fetchone() is None   # só admin exclui


def test_administrador_exclui_informativo_fechado_com_os_itens(limpo):
    a = novo_assunto(limpo)
    c1 = novo_conteudo(limpo, a)
    aprovar(c1)
    i = novo_informativo()
    with como("authenticated", EDITOR) as c:
        c.execute("insert into radar_informativo_itens (informativo_id, conteudo_id) values (%s, %s)", (i, c1))
        c.execute("update radar_informativos set status = 'fechado' where id = %s", (i,))
    with como("authenticated", ADMIN) as c:
        assert c.execute("delete from radar_informativos where id = %s returning id", (i,)).fetchone() == (i,)
    assert limpo.execute("select count(*) from radar_informativo_itens").fetchone()[0] == 0
    assert limpo.execute("select count(*) from radar_conteudos where id = %s", (c1,)).fetchone()[0] == 1   # o conteúdo fica


def test_reversao_remove_tambem_os_objetos_da_v0_4_0():
    sql = REVERSAO.read_text()
    for objeto in ("radar_imagens", "radar_config", "radar_informativos", "radar_informativo_itens",
                   "radar_fn_informativo", "radar_fn_informativo_item", "radar_fn_imagem"):
        assert objeto in sql, objeto


def test_artigo_nao_sai_de_edicao_fechada_trocando_de_edicao(limpo):
    a = novo_assunto(limpo)
    c1, c2 = novo_conteudo(limpo, a), novo_conteudo(limpo, a)
    aprovar(c1), aprovar(c2)
    fechada, aberta = novo_informativo(numero=9, mes="2026-09-01"), novo_informativo(numero=10)
    with como("authenticated", EDITOR) as c:
        c.execute("insert into radar_informativo_itens (informativo_id, conteudo_id) values (%s, %s), (%s, %s)", (fechada, c1, aberta, c2))
        c.execute("update radar_informativos set status = 'fechado' where id = %s", (fechada,))
        for sql, args in (("update radar_informativo_itens set informativo_id = %s where informativo_id = %s", (aberta, fechada)),
                          ("update radar_informativo_itens set informativo_id = %s where informativo_id = %s", (fechada, aberta)),
                          ("update radar_informativo_itens set conteudo_id = %s where informativo_id = %s", (c1, aberta))):
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR064"):
                c.execute(sql, args)
        c.execute("update radar_informativo_itens set ordem = 5 where informativo_id = %s", (aberta,))          # a ordem muda
        # quem monta a edição também remove o artigo dela (enquanto aberta)
        assert c.execute("delete from radar_informativo_itens where informativo_id = %s returning conteudo_id", (aberta,)).fetchall() == [(c2,)]
    assert limpo.execute("select informativo_id, conteudo_id from radar_informativo_itens").fetchall() == [(fechada, c1)]
    with como("authenticated", LEITOR) as c:       # leitor não remove nada (nem de edição aberta)
        assert c.execute("delete from radar_informativo_itens returning conteudo_id").fetchall() == []
    assert limpo.execute("select count(*) from radar_informativo_itens").fetchone()[0] == 1


def test_informativo_nasce_em_montagem_e_o_banco_marca_o_fechamento(limpo):
    with como("authenticated", EDITOR) as c:
        i, status, fechado = c.execute("""insert into radar_informativos (numero, ano, mes, status, fechado_em)
                                          values (3, 2026, '2026-03-01', 'fechado', '2020-01-01') returning id, status, fechado_em""").fetchone()
        assert (status, fechado) == ("rascunho", None)
        c.execute("update radar_informativos set fechado_em = '2020-01-01' where id = %s", (i,))
        assert c.execute("select fechado_em from radar_informativos where id = %s", (i,)).fetchone()[0] is None      # não se forja
        em = c.execute("update radar_informativos set status = 'fechado', fechado_em = '2020-01-01' where id = %s returning fechado_em", (i,)).fetchone()[0]
        assert em.year >= 2026
        for ruim in ("{}", "\"texto\"", "[" + ",".join(["\"" + "x" * 1000 + "\""] * 120) + "]"):
            with pytest.raises(psycopg.errors.CheckViolation):
                c.execute("insert into radar_informativos (numero, ano, mes, agenda) values (4, 2026, '2026-04-01', %s::jsonb)", (ruim,))


def test_excluir_usuario_que_criou_edicao_fechada_funciona(limpo):
    temp = "00000000-0000-0000-0000-0000000000f2"
    limpo.execute("insert into auth.users (id, email) values (%s, 't2')", (temp,))
    limpo.execute("insert into radar_perfis (user_id, nome, papel) values (%s, 'Temporária', 'editor')", (temp,))
    i = novo_informativo(uid=temp)
    with como("authenticated", temp) as c:
        c.execute("update radar_informativos set status = 'fechado' where id = %s", (i,))
    with como("authenticated", EDITOR) as c:       # enquanto a pessoa existe, a autoria não se apaga nem a edição fechada muda
        c.execute("update radar_informativos set criado_por = null where id = %s", (i,))
    assert limpo.execute("select criado_por::text from radar_informativos where id = %s", (i,)).fetchone()[0] == temp
    limpo.execute("delete from auth.users where id = %s", (temp,))
    assert limpo.execute("select status, criado_por from radar_informativos where id = %s", (i,)).fetchone() == ("fechado", None)


def test_quem_esta_sem_perfil_nao_sonda_conteudos_pelo_informativo(limpo):
    a = novo_assunto(limpo)
    rascunho, aprovado = novo_conteudo(limpo, a, "rascunho"), novo_conteudo(limpo, a)
    aprovar(aprovado)
    i = novo_informativo()
    for uid in (SEM_PERFIL, LEITOR):
        with como("authenticated", uid) as c:
            for conteudo in (rascunho, aprovado, 999999):          # a resposta é a mesma, exista ou não, aprovado ou não
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    c.execute("insert into radar_informativo_itens (informativo_id, conteudo_id) values (%s, %s)", (i, conteudo))


def test_texto_do_conteudo_tem_tamanho_maximo(limpo):
    a = novo_assunto(limpo)
    c1 = novo_conteudo(limpo, a, "rascunho")
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_conteudos set corpo = %s where id = %s", ("x" * 60000, c1))
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute("update radar_conteudos set corpo = %s where id = %s", ("x" * 60001, c1))
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute("update radar_conteudos set titulo = %s where id = %s", ("x" * 301, c1))
