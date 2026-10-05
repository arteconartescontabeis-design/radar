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
def test_instalacao_cria_21_tabelas_com_rls(db):
    linhas = db.execute("""select c.relname, c.relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace
                           where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'radar\\_%'""").fetchall()
    assert len(linhas) == 21
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
    assert len(reg[0]) == 21 and len(reg[1]) == 21   # 2ª execução: já havia 21 antes


def test_fontes_do_sql_espelham_o_json_do_robo(db):
    fontes = json.loads((RAIZ / "robo" / "radar_fontes.json").read_text(encoding="utf-8"))
    banco = {s: (u, t, c) for s, u, t, c in db.execute("select slug, url, tipo_coletor, config from radar_fontes "
                                                       "where slug not like 'teste-%'")}
    assert set(banco) == {f["slug"] for f in fontes}
    for f in fontes:
        assert banco[f["slug"]] == (f["url"], f["tipo_coletor"], f["config"])


# ------------------------------------------------------------------------- RLS
def test_anonimo_nao_le_nada_do_radar(limpo):
    """v0.5.0: não há página pública. O visitante (chave anon, sem login) não lê nenhuma tabela nem visão."""
    no_ar(limpo)
    tabelas = [r[0] for r in limpo.execute("""select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
                                             where n.nspname = 'public' and c.relkind in ('r', 'v') and c.relname like 'radar\\_%'""").fetchall()]
    assert len(tabelas) == 28 and "radar_publicacoes" in tabelas and "radar_v_divulgacoes" in tabelas
    with como("anon") as c:
        for tabela in tabelas:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(f"select * from {tabela}")
        for sql in ["select titulo from radar_publicacoes", "select count(*) from radar_categorias", "select id from radar_imagens",
                    "select count(*) from radar_divulgacoes"]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)
    sobras = limpo.execute("""select grantee, table_name from information_schema.role_table_grants
                              where table_schema = 'public' and table_name like 'radar\\_%' and grantee in ('anon', 'PUBLIC')
                              union all
                              select grantee, table_name from information_schema.column_privileges
                              where table_schema = 'public' and table_name like 'radar\\_%' and grantee in ('anon', 'PUBLIC')
                              union all
                              select 'politica', policyname from pg_policies where schemaname = 'public' and 'anon' = any(roles)""").fetchall()
    assert sobras == []


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


def test_publica_quando_tudo_confere(limpo):
    _, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    pid, quem = publicar(c1)
    assert quem == EDITOR
    with como("authenticated", LEITOR) as c:
        assert c.execute("select slug from radar_publicacoes").fetchall() == [("cbs-o-que-muda",)]





def test_rascunho_de_publicacao_nao_passa_pelo_portao(limpo):
    _, c1 = cenario_publicavel(limpo)
    with como("authenticated", EDITOR) as c:   # rascunho não passa pelo portão
        pid = c.execute("insert into radar_publicacoes (conteudo_id, slug) values (%s, 'r') returning id", (c1,)).fetchone()[0]
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR030"):
            c.execute("update radar_publicacoes set status = 'publicado' where id = %s", (pid,))
    aprovar(c1)
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_publicacoes set status = 'publicado' where id = %s", (pid,))
        c.execute("update radar_publicacoes set status = 'despublicado' where id = %s", (pid,))


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





def test_funcoes_nao_ficam_expostas_ao_publico(db):
    abertas = db.execute("""select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                            where n.nspname = 'public' and p.proname like 'radar\\_%'
                              and (has_function_privilege('anon', p.oid, 'execute')
                                   or (p.proname not in ('radar_papel', 'radar_abrir_assunto', 'radar_admin_usuarios',
                                                           'radar_registrar_uso_ia', 'radar_registrar_evidencia_ia',
                                                           'radar_incluir_texto_oficial', 'radar_ignorar_capturas', 'radar_separar_captura')
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
    limpo.execute("insert into radar_fontes (slug, nome, orgao, oficial, tipo_coletor, url) values ('teste-portal', 'Portal de notícias', 'Imprensa', false, 'rss', 'https://portal.exemplo/rss')")
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
    limpo.execute("insert into radar_fontes (slug, nome, orgao, oficial, tipo_coletor, url) values ('teste-portal', 'Portal de notícias', 'Imprensa', false, 'rss', 'https://portal.exemplo/rss')")
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


def test_publicacao_congela_a_fundamentacao_conferida(limpo):
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
    with como("authenticated", LEITOR) as c:
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
            assert c.execute("select array_agg(versao order by id) from radar_instalacoes").fetchone()[0] == ["v0.1.0", "v0.7.1"]
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
    limpo.execute("insert into radar_fontes (slug, nome, orgao, oficial, tipo_coletor, url) values ('teste-portal', 'Portal de notícias', 'Imprensa', false, 'rss', 'https://portal.exemplo/rss')")
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


def test_imagem_so_e_lida_pela_equipe(limpo):
    a, _ = cenario_publicavel(limpo)
    c1 = novo_conteudo(limpo, a)
    usada = nova_imagem()
    limpo.execute("update radar_conteudos set imagem_id = %s, autor = 'Marcos Vinicius', fonte_credito = 'Receita Federal' where id = %s", (usada, c1))
    aprovar(c1)
    publicar(c1)
    with como("anon") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("select id from radar_imagens")
    with como("authenticated", SEM_PERFIL) as c:
        assert c.execute("select count(*) from radar_imagens").fetchone()[0] == 0
    with como("authenticated", LEITOR) as c:
        assert c.execute("select id from radar_imagens").fetchall() == [(usada,)]
        assert c.execute("select imagem_id, autor, fonte_credito from radar_publicacoes").fetchone() == (usada, "Marcos Vinicius", "Receita Federal")


def test_imagem_autor_e_fonte_da_publicacao_vem_do_conteudo_e_nao_mudam_no_ar(limpo):
    a, _ = cenario_publicavel(limpo)
    c1 = novo_conteudo(limpo, a)
    img, outra = nova_imagem(), nova_imagem()
    limpo.execute("update radar_conteudos set imagem_id = %s, autor = 'Equipe Fiscal' where id = %s", (img, c1))
    aprovar(c1)
    with como("authenticated", EDITOR) as c:        # tentar informar outros valores na publicação não adianta
        pid = c.execute("""insert into radar_publicacoes (conteudo_id, slug, status, imagem_id, autor, fonte_credito)
                           values (%s, 'x', 'publicado', %s, 'Forjado', 'Forjada') returning id""", (c1, outra)).fetchone()[0]
        assert c.execute("select imagem_id, autor, fonte_credito from radar_publicacoes where id = %s", (pid,)).fetchone() == (img, "Equipe Fiscal", "Receita Federal do Brasil")   # v0.7.0: a fonte já vem preenchida com o órgão da captura oficial
        c.execute("update radar_publicacoes set imagem_id = %s, autor = 'Outro', fonte_credito = 'Outra' where id = %s", (outra, pid))
        assert c.execute("select imagem_id, autor, fonte_credito from radar_publicacoes where id = %s", (pid,)).fetchone() == (img, "Equipe Fiscal", "Receita Federal do Brasil")   # v0.7.0: a fonte já vem preenchida com o órgão da captura oficial
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
    assert set(conf) == {"obrigacoes", "feriados_extras", "fale_conosco", "assinatura", "relevancia"}
    assert len(conf["obrigacoes"]) == 22 and conf["assinatura"]["responsavel"] == "Cleiver Gonçalves"
    assert all(o["regra"] in ("quinto_dia_util", "dia", "ultimo_dia_util") for o in conf["obrigacoes"])
    with como("authenticated", LEITOR) as c:
        assert c.execute("select count(*) from radar_config").fetchone()[0] == 5          # a equipe lê
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


# ============================================================ v0.4.1 — instalação sem depender da transação do editor
def _sem_transacao(origem, destino):
    """Cópia do script sem BEGIN/COMMIT: cada instrução é confirmada à parte (como um editor que não mantém a transação)."""
    destino.write_text("\n".join(l for l in origem.read_text().splitlines() if l.strip() not in ("begin;", "commit;")))
    return destino


def _resumo(banco):
    with conectar(banco) as c:
        return c.execute("""select (select count(*) from pg_class k join pg_namespace n on n.oid = k.relnamespace
                                    where n.nspname = 'public' and k.relkind = 'r' and k.relname like 'radar\\_%' and k.relrowsecurity),
                                   (select count(*) from radar_fontes), (select count(*) from radar_categorias), (select count(*) from radar_config),
                                   (select count(*) from radar_instalacoes where depois is not null),
                                   (select count(*) from radar_instalacoes where depois is null)""").fetchone()


def test_setup_instala_mesmo_sem_a_transacao_do_editor(tmp_path):
    with conectar("postgres") as c:
        c.execute("drop database if exists radar_sem_tx with (force)")
        c.execute("create database radar_sem_tx")
    try:
        assert psql(RAIZ / "testes" / "supabase_simulado.sql", "radar_sem_tx").returncode == 0
        r = psql(_sem_transacao(SETUP, tmp_path / "setup.sql"), "radar_sem_tx")
        assert r.returncode == 0, r.stderr
        assert _resumo("radar_sem_tx") == (21, 6, 8, 5, 1, 0)
        with conectar("radar_sem_tx") as c:
            assert c.execute("select versao, antes, jsonb_array_length(depois) from radar_instalacoes").fetchone() == ("v0.7.1", [], 21)
    finally:
        with conectar("postgres") as c:
            c.execute("drop database if exists radar_sem_tx with (force)")


def test_setup_conclui_por_cima_da_instalacao_que_parou_no_erro_da_v0_4_0(tmp_path):
    """Reproduz o erro visto no Supabase (relation "_radar_antes" does not exist) e mostra que a v0.4.1 conclui por cima."""
    with conectar("postgres") as c:
        c.execute("drop database if exists radar_parcial with (force)")
        c.execute("create database radar_parcial")
    try:
        assert psql(RAIZ / "testes" / "supabase_simulado.sql", "radar_parcial").returncode == 0
        r = psql(_sem_transacao(RAIZ / "testes" / "radar-setup-v0.4.0-referencia.sql", tmp_path / "v040.sql"), "radar_parcial")
        assert r.returncode != 0 and 'relation "_radar_antes" does not exist' in r.stderr
        with conectar("radar_parcial") as c:                     # ficou tudo criado, menos o registro da instalação
            assert c.execute("select count(*) from radar_instalacoes").fetchone()[0] == 0
            c.execute("update radar_fontes set frequencia_horas = 3 where slug = 'pgfn-noticias'")
        for script in (SETUP, _sem_transacao(SETUP, tmp_path / "setup.sql")):          # com e sem transação
            r = psql(script, "radar_parcial")
            assert r.returncode == 0, r.stderr
        assert _resumo("radar_parcial") == (21, 6, 8, 5, 2, 0)
        with conectar("radar_parcial") as c:
            assert c.execute("select frequencia_horas from radar_fontes where slug = 'pgfn-noticias'").fetchone()[0] == 3     # ajuste preservado
            # a atualização retira o acesso público que a v0.4 concedia (página pública extinta na v0.5.0)
            assert c.execute("""select (select count(*) from information_schema.role_table_grants where table_schema = 'public' and table_name like 'radar\\_%' and grantee = 'anon')
                                     + (select count(*) from information_schema.column_privileges where table_schema = 'public' and table_name like 'radar\\_%' and grantee = 'anon')
                                     + (select count(*) from pg_policies where schemaname = 'public' and 'anon' = any(roles))""").fetchone()[0] == 0
            assert c.execute("select jsonb_array_length(antes) from radar_instalacoes order by id").fetchall() == [(20,), (21,)]
    finally:
        with conectar("postgres") as c:
            c.execute("drop database if exists radar_parcial with (force)")


def test_execucao_interrompida_fica_registrada_e_nao_conta_como_instalada(tmp_path):
    with conectar("postgres") as c:
        c.execute("drop database if exists radar_meio with (force)")
        c.execute("create database radar_meio")
    try:
        assert psql(RAIZ / "testes" / "supabase_simulado.sql", "radar_meio").returncode == 0
        linhas = _sem_transacao(SETUP, tmp_path / "setup.sql").read_text().splitlines()
        corte = next(i for i, l in enumerate(linhas) if l.startswith("-- 5. RLS"))
        (tmp_path / "meio.sql").write_text("\n".join(linhas[:corte]) + "\nselect 1/0;\n")       # para no meio, antes das fontes iniciais
        assert psql(tmp_path / "meio.sql", "radar_meio").returncode != 0
        with conectar("radar_meio") as c:
            assert c.execute("select count(*), count(depois) from radar_instalacoes").fetchone() == (1, 0)
        r = psql(SETUP, "radar_meio")
        assert r.returncode == 0, r.stderr
        assert _resumo("radar_meio") == (21, 6, 8, 5, 1, 1)        # as fontes e categorias iniciais entram na execução que conclui
    finally:
        with conectar("postgres") as c:
            c.execute("drop database if exists radar_meio with (force)")


# ============================================================ v0.5.0 — registro do que foi publicado no site da Artecon
_seq = iter(range(1, 100000))


def fundamentado(db, status="em_revisao"):
    """Assunto confirmado oficialmente, com trecho conferido em fonte oficial, e um conteúdo."""
    cap = nova_captura(db, url=f"https://exemplo.gov.br/in-2290-{next(_seq)}")
    a = novo_assunto(db)
    db.execute("insert into radar_evidencias (assunto_id, captura_id, dispositivo, trecho_literal) values (%s, %s, 'art. 2º', %s)",
               (a, cap, "à alíquota de 0,9% (nove décimos por cento)"))
    return a, novo_conteudo(db, a, status)


def registrar_site(conteudo, uid=EDITOR, url="https://artecon.cnt.br/news/cgsn-prorroga-prazo", quando="2026-10-02"):
    with como("authenticated", uid) as c:
        return c.execute("insert into radar_divulgacoes (conteudo_id, url, publicado_em) values (%s, %s, %s) returning id",
                         (conteudo, url, quando)).fetchone()[0]


def test_registro_no_site_so_de_conteudo_aprovado(limpo):
    a, c1 = fundamentado(limpo)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR070"):
        registrar_site(c1)                                       # em revisão: ainda não
    aprovar(c1)
    d = registrar_site(c1)
    linha = limpo.execute("select titulo, corpo, registrado_por::text, publicado_em::text from radar_divulgacoes where id = %s", (d,)).fetchone()
    assert linha == ("CBS: o que muda", "Texto do informativo.", EDITOR, "2026-10-02")       # cópia do texto aprovado
    assert limpo.execute("select status from radar_assuntos where id = %s", (a,)).fetchone()[0] == "publicado"
    assert limpo.execute("select acao, usuario::text from radar_auditoria where tabela = 'radar_divulgacoes'").fetchall() == [("INSERT", EDITOR)]
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR070"):
        registrar_site(999999)


def test_registro_no_site_guarda_o_texto_que_saiu_e_so_link_data_e_observacao_mudam(limpo):
    a, c1 = fundamentado(limpo)
    aprovar(c1)
    with como("authenticated", EDITOR) as c:        # tentar forjar a cópia, o autor ou a data do registro não adianta
        d = c.execute("""insert into radar_divulgacoes (conteudo_id, url, titulo, corpo, registrado_por, registrado_em)
                         values (%s, 'https://artecon.cnt.br/news/x', 'Forjado', 'Forjado', %s, '2020-01-01') returning id""", (c1, ADMIN)).fetchone()[0]
        assert c.execute("select titulo, registrado_por::text, registrado_em > '2026-01-01' from radar_divulgacoes").fetchone() == ("CBS: o que muda", EDITOR, True)
        c.execute("""update radar_divulgacoes set titulo = 'Outro', corpo = 'Outro', conteudo_id = 999, registrado_por = null,
                     url = 'https://artecon.cnt.br/news/y', publicado_em = '2026-09-30', observacao = 'link corrigido' where id = %s""", (d,))
        assert c.execute("select titulo, corpo, conteudo_id, registrado_por::text, url, publicado_em::text, observacao from radar_divulgacoes").fetchone() == \
            ("CBS: o que muda", "Texto do informativo.", c1, EDITOR, "https://artecon.cnt.br/news/y", "2026-09-30", "link corrigido")
        # o conteúdo muda depois: o registro continua com o texto que saiu e a visão aponta a diferença
        assert c.execute("select texto_mudou, conteudo_status from radar_v_divulgacoes").fetchone() == (False, "aprovado")
        c.execute("update radar_conteudos set corpo = 'Texto novo.' where id = %s", (c1,))
        assert c.execute("select texto_mudou, conteudo_status from radar_v_divulgacoes").fetchone() == (True, "em_revisao")
        assert c.execute("select corpo from radar_divulgacoes").fetchone()[0] == "Texto do informativo."
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.ForeignKeyViolation):
        c.execute("delete from radar_conteudos where id = %s", (c1,))            # conteúdo já divulgado não se apaga


def test_registro_no_site_recusa_endereco_que_nao_e_link(limpo):
    a, c1 = fundamentado(limpo)
    aprovar(c1)
    for ruim in ["javascript:alert(1)", "data:text/html,x", "ftp://x.com/a", "//x.com/a", "artecon.cnt.br/news/x", "https://artecon.cnt.br/a b",
                 'https://x.com/"><script>', "https://x.com/a'b", "https://x.com/a`b", "", "https://x.com/" + "a" * 500, "https://x.com/a\n",
                 "https://x.com/a\u00a0b", "https://x.com/a\u200bb", "https://x.com/\u202egpj.exe", "https://x.com/a\x01", "https://x.com/a\x7f", "https://"]:
        with pytest.raises(psycopg.errors.CheckViolation):
            registrar_site(c1, url=ruim)
    assert registrar_site(c1, url="http://artecon.cnt.br/news/x?a=1&b=%20#topo")
    for data_ruim in ("2099-12-31", "0001-01-01"):
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR072"):
            registrar_site(c1, quando=data_ruim)
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR072"):
        c.execute("update radar_divulgacoes set publicado_em = '2099-01-01'")


def test_registro_no_site_quem_pode(limpo):
    a, c1 = fundamentado(limpo)
    aprovar(c1)
    for uid in (LEITOR, SEM_PERFIL):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            registrar_site(c1, uid)
    with como("anon") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("insert into radar_divulgacoes (conteudo_id, url) values (%s, 'https://artecon.cnt.br/x')", (c1,))
    # v0.8.0: o robô (service_role) inclui o registro que achou no site, mas não altera nem apaga
    with como("service_role") as c:
        robo = c.execute("insert into radar_divulgacoes (conteudo_id, url) values (%s, 'https://artecon.cnt.br/x') returning id", (c1,)).fetchone()[0]
    for sql in ("update radar_divulgacoes set url = 'https://x.com/y' where id = %s", "delete from radar_divulgacoes where id = %s"):
        with como("service_role") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(sql, (robo,))
    limpo.execute("delete from radar_divulgacoes where id = %s", (robo,))
    d = registrar_site(c1)
    with como("authenticated", LEITOR) as c:
        assert c.execute("select count(*) from radar_divulgacoes").fetchone()[0] == 1          # a equipe consulta
        assert c.execute("update radar_divulgacoes set url = 'https://x.com/y' where id = %s returning id", (d,)).fetchone() is None
    with como("authenticated", SEM_PERFIL) as c:
        assert c.execute("select count(*) from radar_divulgacoes").fetchone()[0] == 0
        assert c.execute("select count(*) from radar_v_divulgacoes").fetchone()[0] == 0
    with como("authenticated", EDITOR) as c:
        assert c.execute("delete from radar_divulgacoes where id = %s returning id", (d,)).fetchone() is None   # só o administrador exclui
    with como("authenticated", ADMIN) as c:
        assert c.execute("delete from radar_divulgacoes where id = %s returning id", (d,)).fetchone() == (d,)
    assert limpo.execute("select status from radar_assuntos where id = %s", (a,)).fetchone()[0] == "aprovado"   # volta a "em andamento"


def test_painel_conta_aprovados_a_publicar_e_publicados_no_site(limpo):
    a, c1 = fundamentado(limpo)
    c2, c3 = novo_conteudo(limpo, a), novo_conteudo(limpo, a, "rascunho")
    aprovar(c1), aprovar(c2)
    with como("authenticated", LEITOR) as c:
        assert c.execute("select no_site, aprovados_sem_site from radar_v_painel").fetchone() == (0, 2)
    registrar_site(c1)
    registrar_site(c1, url="https://artecon.cnt.br/news/republicado")          # o mesmo conteúdo pode ter mais de um registro
    with como("authenticated", LEITOR) as c:
        assert c.execute("select no_site, aprovados_sem_site from radar_v_painel").fetchone() == (1, 1)     # conta conteúdos, não links
    # conteúdo que não vai ao site (só Informativo Mensal) sai da fila sem deixar de estar aprovado nem mudar de data
    antes = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (c2,)).fetchone()[0]
    with como("authenticated", EDITOR) as c:
        assert c.execute("update radar_conteudos set fora_do_site = true where id = %s returning status, atualizado_em", (c2,)).fetchone() == ("aprovado", antes)
    with como("authenticated", LEITOR) as c:
        assert c.execute("select no_site, aprovados_sem_site from radar_v_painel").fetchone() == (1, 0)
        assert c.execute("update radar_conteudos set fora_do_site = false where id = %s returning id", (c2,)).fetchone() is None      # leitor não muda
    assert c3


def test_excluir_usuario_que_registrou_publicacao_no_site_funciona(limpo):
    temp = "00000000-0000-0000-0000-0000000000f3"
    limpo.execute("insert into auth.users (id, email) values (%s, 't3')", (temp,))
    limpo.execute("insert into radar_perfis (user_id, nome, papel) values (%s, 'Temporária', 'editor')", (temp,))
    a, c1 = fundamentado(limpo)
    aprovar(c1, temp)
    d = registrar_site(c1, temp)
    limpo.execute("delete from auth.users where id = %s", (temp,))
    assert limpo.execute("select registrado_por, titulo from radar_divulgacoes where id = %s", (d,)).fetchone() == (None, "CBS: o que muda")


def test_registro_no_site_so_vale_para_o_texto_que_estava_na_tela(limpo):
    a, c1 = fundamentado(limpo)
    aprovar(c1)
    lido = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (c1,)).fetchone()[0]
    with como("authenticated", ADMIN) as c:              # um colega altera e aprova de novo
        c.execute("update radar_conteudos set corpo = 'TEXTO B que o editor nunca viu' where id = %s", (c1,))
        c.execute("update radar_conteudos set status = 'aprovado' where id = %s", (c1,))
    with como("authenticated", EDITOR) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR071"):
            c.execute("insert into radar_divulgacoes (conteudo_id, url, conteudo_lido_em) values (%s, 'https://artecon.cnt.br/x', %s)", (c1, lido))
        atual = c.execute("select atualizado_em from radar_conteudos where id = %s", (c1,)).fetchone()[0]
        d = c.execute("insert into radar_divulgacoes (conteudo_id, url, conteudo_lido_em) values (%s, 'https://artecon.cnt.br/x', %s) returning id", (c1, atual)).fetchone()[0]
        c.execute("update radar_divulgacoes set conteudo_lido_em = '2020-01-01' where id = %s", (d,))
        assert c.execute("select corpo, conteudo_lido_em from radar_divulgacoes").fetchone() == ("TEXTO B que o editor nunca viu", atual)


def test_registro_antigo_vira_versao_anterior_quando_ha_registro_do_texto_atual(limpo):
    a, c1 = fundamentado(limpo)
    aprovar(c1)
    d1 = registrar_site(c1)
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_conteudos set corpo = 'Texto corrigido.' where id = %s", (c1,))
        assert c.execute("select texto_mudou, versao_anterior from radar_v_divulgacoes").fetchone() == (True, False)       # alerta
        c.execute("update radar_conteudos set status = 'aprovado' where id = %s", (c1,))
    d2 = registrar_site(c1, url="https://artecon.cnt.br/news/corrigido")
    with como("authenticated", LEITOR) as c:
        assert c.execute("select id, texto_mudou, versao_anterior from radar_v_divulgacoes order by id").fetchall() == [(d1, True, True), (d2, False, False)]


def test_registro_no_site_nao_ressuscita_assunto_arquivado_ou_ignorado(limpo):
    for status in ("arquivado", "ignorado"):
        a, c1 = fundamentado(limpo)
        aprovar(c1)
        limpo.execute("update radar_assuntos set status = %s where id = %s", (status, a))
        d = registrar_site(c1)
        assert limpo.execute("select status from radar_assuntos where id = %s", (a,)).fetchone()[0] == status
        with como("authenticated", ADMIN) as c:
            c.execute("delete from radar_divulgacoes where id = %s", (d,))
        assert limpo.execute("select status from radar_assuntos where id = %s", (a,)).fetchone()[0] == status


def test_registro_no_site_exige_assunto_confirmado_e_trecho_conferido_em_fonte_oficial(limpo):
    """A regra da antiga publicação continua valendo: o que mudou na v0.5.0 foi só o destino (o site da Artecon)."""
    # assunto criado pela equipe, sem captura nem evidência
    a = novo_assunto(limpo, "em_verificacao")
    c1 = novo_conteudo(limpo, a)
    aprovar(c1)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR031"):
        registrar_site(c1)
    limpo.execute("update radar_assuntos set situacao_confirmacao = 'confirmado_oficialmente' where id = %s", (a,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR032"):
        registrar_site(c1)
    # trecho que NÃO está no texto oficial não conta
    cap = nova_captura(limpo, url="https://exemplo.gov.br/x1")
    limpo.execute("insert into radar_evidencias (assunto_id, captura_id, trecho_literal) values (%s, %s, 'Art. 9º dispositivo inventado que não existe')", (a, cap))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR032"):
        registrar_site(c1)
    # trecho conferido, mas de fonte marcada como não oficial, também não conta
    limpo.execute("insert into radar_evidencias (assunto_id, captura_id, trecho_literal) values (%s, %s, %s)", (a, cap, "à alíquota de 0,9% (nove décimos por cento)"))
    limpo.execute("update radar_fontes set oficial = false where slug = 'rfb-normas'")
    try:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR032"):
            registrar_site(c1)
    finally:
        limpo.execute("update radar_fontes set oficial = true where slug = 'rfb-normas'")
    d = registrar_site(c1)
    fund = limpo.execute("select fundamentacao from radar_divulgacoes where id = %s", (d,)).fetchone()[0]
    assert len(fund) == 1 and fund[0]["trecho"] == "à alíquota de 0,9% (nove décimos por cento)" and fund[0]["url"] == "https://exemplo.gov.br/x1"
    assert fund[0]["orgao"] == "Receita Federal do Brasil" and fund[0]["manual"] is False
    # a fundamentação registrada é fotografia: não se forja nem muda depois
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_divulgacoes set fundamentacao = '[]' where id = %s", (d,))
        d2 = c.execute("""insert into radar_divulgacoes (conteudo_id, url, fundamentacao)
                          values (%s, 'https://artecon.cnt.br/y', '[{"trecho": "forjado"}]') returning id""", (c1,)).fetchone()[0]
    limpo.execute("delete from radar_evidencias where assunto_id = %s", (a,))
    assert [r[0] for r in limpo.execute("select fundamentacao from radar_divulgacoes order by id").fetchall()] == [fund, fund]
    assert d2
    # o Informativo Mensal continua exigindo só o conteúdo aprovado
    i = novo_informativo()
    with como("authenticated", EDITOR) as c:
        c.execute("insert into radar_informativo_itens (informativo_id, conteudo_id) values (%s, %s)", (i, c1))


# ---------------------------------------------------------- texto oficial incluído pela equipe
TEXTO_COLADO = ("Art. 1º Fica prorrogado até 15 de outubro de 2026 o prazo para opção pelo Simples Nacional. "
                "Art. 2º Esta Resolução entra em vigor na data de sua publicação.")


def incluir_texto(assunto, uid=EDITOR, fonte="simples-noticias", url="https://www8.receita.fazenda.gov.br/SimplesNacional/x", titulo="Resolução CGSN nº 194",
                  data="2026-09-30", texto=TEXTO_COLADO):
    with como("authenticated", uid) as c:
        fid = c.execute("select id from radar_fontes where slug = %s", (fonte,)).fetchone()
        return c.execute("select radar_incluir_texto_oficial(%s, %s, %s, %s, %s, %s)", (assunto, fid[0] if fid else 999999, url, titulo, data, texto)).fetchone()[0]


def test_texto_oficial_incluido_pela_equipe_fundamenta_o_assunto_e_fica_marcado(limpo):
    a = novo_assunto(limpo)
    c1 = novo_conteudo(limpo, a)
    aprovar(c1)
    r = incluir_texto(a)
    assert r["ja_existia"] is False
    cap = r["captura_id"]
    linha = limpo.execute("select titulo, data_publicacao::text, texto, metadados, versao, hash_conteudo is not null from radar_capturas where id = %s", (cap,)).fetchone()
    assert linha[0] == "Resolução CGSN nº 194" and linha[1] == "2026-09-30" and linha[2] == TEXTO_COLADO and linha[4] == 1 and linha[5]
    assert linha[3]["manual"] is True and linha[3]["incluido_por"] == EDITOR
    assert limpo.execute("select captura_id from radar_assunto_capturas where assunto_id = %s", (a,)).fetchall() == [(cap,)]
    aud = limpo.execute("select usuario::text, depois->>'url', (depois->>'manual')::boolean from radar_auditoria where tabela = 'radar_capturas'").fetchall()
    assert aud == [(EDITOR, "https://www8.receita.fazenda.gov.br/SimplesNacional/x", True)]
    # a conferência do trecho continua sendo do banco: literal entra, inventado não
    with como("authenticated", EDITOR) as c:
        ok = c.execute("insert into radar_evidencias (assunto_id, captura_id, trecho_literal) values (%s, %s, %s) returning trecho_conferido",
                       (a, cap, "prorrogado até 15 de outubro de 2026 o prazo")).fetchone()[0]
        ruim = c.execute("insert into radar_evidencias (assunto_id, captura_id, trecho_literal) values (%s, %s, %s) returning trecho_conferido",
                         (a, cap, "prorrogado até 30 de novembro de 2026 o prazo")).fetchone()[0]
    assert (ok, ruim) == (True, False)
    d = registrar_site(c1)
    assert limpo.execute("select fundamentacao->0->>'manual' from radar_divulgacoes where id = %s", (d,)).fetchone()[0] == "true"
    # não aparece na fila de triagem (já está vinculada ao assunto)
    assert limpo.execute("select count(*) from radar_v_fila").fetchone()[0] == 0


def test_texto_oficial_manual_nao_substitui_captura_existente_do_mesmo_endereco(limpo):
    cap = nova_captura(limpo, url="https://exemplo.gov.br/in-2290")                # capturada pelo robô
    a = novo_assunto(limpo)
    r = incluir_texto(a, fonte="rfb-normas", url="https://exemplo.gov.br/in-2290", texto="Texto adulterado " * 10)
    assert r == {"captura_id": cap, "ja_existia": True, "texto_incluido": False}
    assert limpo.execute("select texto, metadados from radar_capturas where id = %s", (cap,)).fetchone() == (TEXTO_OFICIAL, {})
    assert limpo.execute("select count(*) from radar_capturas").fetchone()[0] == 1
    assert limpo.execute("select count(*) from radar_assunto_capturas where assunto_id = %s and captura_id = %s", (a, cap)).fetchone()[0] == 1
    # incluir duas vezes o mesmo endereço não duplica
    b = novo_assunto(limpo)
    r1 = incluir_texto(b)
    r2 = incluir_texto(b, texto="Outro texto colado depois, bem diferente do primeiro, com mais de cinquenta caracteres.")
    assert r2 == {"captura_id": r1["captura_id"], "ja_existia": True, "texto_incluido": False}
    assert limpo.execute("select texto from radar_capturas where id = %s", (r1["captura_id"],)).fetchone()[0] == TEXTO_COLADO
    # variações do mesmo endereço (barra no fim, âncora, parâmetro de rastreio) e outra fonte: continua sendo a mesma captura
    for variacao in ("https://exemplo.gov.br/in-2290/", "https://exemplo.gov.br/in-2290#art2", "https://exemplo.gov.br/in-2290?utm_source=x",
                     "https://exemplo.gov.br/in-2290/?utm_medium=y&fbclid=z"):
        for fonte in ("rfb-normas", "rfb-noticias"):
            assert incluir_texto(b, fonte=fonte, url=variacao, texto="Texto forjado " * 10) == {"captura_id": cap, "ja_existia": True, "texto_incluido": False}
    assert limpo.execute("select count(*) from radar_capturas").fetchone()[0] == 2
    assert limpo.execute("select texto from radar_capturas where id = %s", (cap,)).fetchone()[0] == TEXTO_OFICIAL


def test_texto_oficial_manual_so_vale_para_endereco_do_site_da_fonte(limpo):
    a = novo_assunto(limpo)
    # fonte "Receita Federal — Notícias" (www.gov.br): outro domínio é recusado; subdomínio de gov.br é aceito
    for ruim in ("https://evil.example.com/c", "https://www.gov.br.evil.com/x", "https://evilgov.br/x", "https://gov.br.attacker.io/"):
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR086"):
            incluir_texto(a, fonte="rfb-noticias", url=ruim)
    assert incluir_texto(a, fonte="rfb-noticias", url="https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026/x")["texto_incluido"]
    assert incluir_texto(a, fonte="rfb-noticias", url="https://www.in.gov.br/web/dou/-/ato-1")["texto_incluido"]
    # fonte cujo site não é "www.": só o próprio endereço e os subdomínios dele
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR086"):
        incluir_texto(a, fonte="simples-noticias", url="https://www.gov.br/outra")
    # o administrador pode liberar outros domínios da mesma fonte em "outras opções" (dominios)
    limpo.execute("""update radar_fontes set config = config || '{"dominios": ["planalto.gov.br"]}'::jsonb where slug = 'simples-noticias'""")
    try:
        assert incluir_texto(a, fonte="simples-noticias", url="https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm")["texto_incluido"]
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR086"):
            incluir_texto(a, fonte="simples-noticias", url="https://planalto.gov.br.evil.com/x")
    finally:
        limpo.execute("update radar_fontes set config = config - 'dominios' where slug = 'simples-noticias'")
    assert limpo.execute("select count(*) from radar_capturas").fetchone()[0] == 3


def test_texto_oficial_manual_completa_captura_que_o_robo_deixou_sem_texto(limpo):
    cap = limpo.execute("""insert into radar_capturas (fonte_id, url, titulo, hash_titulo, metadados)
                           select id, 'https://exemplo.gov.br/portaria.pdf', 'Portaria em PDF', 'h', '{"erro_texto": "PDF"}' from radar_fontes where slug = 'rfb-normas'
                           returning id""").fetchone()[0]
    a = novo_assunto(limpo)
    r = incluir_texto(a, fonte="rfb-noticias", url="https://exemplo.gov.br/portaria.pdf/")
    assert r == {"captura_id": cap, "ja_existia": True, "texto_incluido": True}
    texto, meta, versao, fonte = limpo.execute("""select c.texto, c.metadados, c.versao, f.slug from radar_capturas c join radar_fontes f on f.id = c.fonte_id
                                                  where c.id = %s""", (cap,)).fetchone()
    assert texto == TEXTO_COLADO and meta["manual"] is True and meta["incluido_por"] == EDITOR and meta["erro_texto"] == "PDF"
    assert versao == 1 and fonte == "rfb-normas"                                   # continua na fonte em que o robô registrou
    assert limpo.execute("select acao, usuario::text from radar_auditoria where tabela = 'radar_capturas'").fetchall() == [("UPDATE", EDITOR)]
    # colar de novo não troca o texto que já entrou
    assert incluir_texto(a, url="https://exemplo.gov.br/portaria.pdf", texto="Outro texto " * 10)["texto_incluido"] is False
    assert limpo.execute("select texto from radar_capturas where id = %s", (cap,)).fetchone()[0] == TEXTO_COLADO


def test_texto_oficial_manual_quem_pode_e_validacoes(limpo):
    a = novo_assunto(limpo)
    for uid in (LEITOR, SEM_PERFIL):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            incluir_texto(a, uid)
    for papel in ("anon", "service_role"):
        with como(papel) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select radar_incluir_texto_oficial(%s, 1, 'https://x.gov.br/a', 'Título de teste', null, %s)", (a, TEXTO_COLADO))
    for kwargs, codigo in [({"fonte": "nao-existe"}, "RADAR081"), ({"url": "javascript:alert(1)"}, "RADAR082"), ({"url": "https://x.gov.br/a b"}, "RADAR082"),
                           ({"url": 'https://x.gov.br/"><script>'}, "RADAR082"), ({"titulo": "abc"}, "RADAR083"), ({"texto": "curto"}, "RADAR084"),
                           ({"texto": "   " * 100}, "RADAR084"), ({"data": "2099-01-01"}, "RADAR085")]:
        with pytest.raises(psycopg.errors.RaiseException, match=codigo):
            incluir_texto(a, **kwargs)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR080"):
        incluir_texto(999999)
    assert limpo.execute("select count(*) from radar_capturas").fetchone()[0] == 0
    # editor continua sem gravar capturas diretamente: só pela função, que marca a origem
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo) select id, 'https://x.gov.br/z', 'T', 'x', 'h' from radar_fontes limit 1")
    assert incluir_texto(a, data=None)["ja_existia"] is False                         # a data é opcional


def test_robo_que_captura_depois_o_mesmo_endereco_gera_nova_versao_e_reconfere(limpo):
    a = novo_assunto(limpo)
    cap = incluir_texto(a)["captura_id"]
    with como("authenticated", EDITOR) as c:
        c.execute("insert into radar_evidencias (assunto_id, captura_id, trecho_literal) values (%s, %s, 'prorrogado até 15 de outubro de 2026 o prazo')", (a, cap))
    with como("service_role") as c:              # o robô lê a página de verdade e o texto é outro (ele regrava os metadados)
        c.execute("""update radar_capturas set texto = 'Art. 1º Fica prorrogado até 30 de outubro de 2026 o prazo para opção.',
                     metadados = '{"data_iso": "2026-09-30"}' where id = %s""", (cap,))
    versao, meta = limpo.execute("select versao, metadados from radar_capturas where id = %s", (cap,)).fetchone()
    assert versao == 2 and "manual" not in meta and meta["data_iso"] == "2026-09-30"          # o texto atual já não é o colado…
    assert meta["origem_manual"]["por"] == EDITOR and meta["origem_manual"]["versao"] == 1 and meta["origem_manual"]["texto_igual"] is False   # …mas a origem fica
    with como("service_role") as c:              # nova passagem do robô não apaga a origem
        c.execute("update radar_capturas set metadados = '{}' where id = %s", (cap,))
    assert limpo.execute("select metadados->'origem_manual'->>'por' from radar_capturas where id = %s", (cap,)).fetchone()[0] == EDITOR
    assert limpo.execute("select texto from radar_capturas_versoes where captura_id = %s", (cap,)).fetchone()[0] == TEXTO_COLADO
    assert limpo.execute("select trecho_conferido from radar_evidencias where captura_id = %s", (cap,)).fetchone()[0] is False


# ---------------------------------------------------------- cadastro de fontes pela tela
def test_administrador_cadastra_altera_e_exclui_fonte_e_o_formato_e_conferido(limpo):
    nova = ("teste-prefeitura", "Prefeitura de Palhoça — Notícias", "Prefeitura de Palhoça", "municipal", "html_links",
            "https://www.palhoca.sc.gov.br/noticias", '{"padrao_url": "/noticias/\\\\d+", "janela_dias": 30}')
    sql = "insert into radar_fontes (slug, nome, orgao, abrangencia, tipo_coletor, url, config) values (%s, %s, %s, %s, %s, %s, %s::jsonb) returning id, validada, ativo, oficial"
    for uid in (EDITOR, LEITOR, SEM_PERFIL):
        with como("authenticated", uid) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(sql, nova)
    with como("authenticated", ADMIN) as c:
        fid, validada, ativo, oficial = c.execute(sql, nova).fetchone()
        assert (validada, ativo, oficial) == (False, True, True)              # entra "a validar"
        for campo, ruim in [("url", "javascript:alert(1)"), ("url", "www.palhoca.sc.gov.br"), ("url", "https://x.gov.br/a b"), ("nome", "ab"), ("orgao", " "),
                            ("slug", "Com Espaço"), ("tipo_coletor", "inventado"), ("abrangencia", "mundial"), ("frequencia_horas", 0)]:
            with pytest.raises(psycopg.errors.CheckViolation):
                c.execute(f"update radar_fontes set {campo} = %s where id = %s", (ruim, fid))
        for ruim in ('[]', '"texto"', '{"x": "' + "a" * 20000 + '"}'):
            with pytest.raises(psycopg.errors.CheckViolation):
                c.execute("update radar_fontes set config = %s::jsonb where id = %s", (ruim, fid))
        with pytest.raises(psycopg.errors.UniqueViolation):
            c.execute(sql, nova)
        c.execute("update radar_fontes set nome = 'Prefeitura de Palhoça — Últimas notícias', frequencia_horas = 24 where id = %s", (fid,))
    # fonte antiga fora do formato (gravada antes desta regra): o robô continua atualizando a saúde dela e a execução fecha
    limpo.execute("alter table radar_fontes disable trigger radar_tg_fonte_formato")
    limpo.execute("update radar_fontes set url = 'https://www.palhoca.sc.gov.br/notícias antigas' where id = %s", (fid,))
    limpo.execute("alter table radar_fontes enable trigger radar_tg_fonte_formato")
    with como("service_role") as c:
        ex = c.execute("insert into radar_execucoes (fonte_id, status) values (%s, 'em_andamento') returning id", (fid,)).fetchone()[0]
        c.execute("update radar_execucoes set status = 'ok', finalizado_em = now() where id = %s", (ex,))
    assert limpo.execute("select ultimo_sucesso_em is not null from radar_fontes where id = %s", (fid,)).fetchone()[0]
    with como("authenticated", ADMIN) as c:
        c.execute("update radar_fontes set frequencia_horas = 12, ativo = false where id = %s", (fid,))      # mudar o que não é cadastro também passa
        with pytest.raises(psycopg.errors.CheckViolation, match="RADAR090"):
            c.execute("update radar_fontes set nome = 'ab' where id = %s", (fid,))                          # mexeu no cadastro: tem de corrigir o endereço
        c.execute("update radar_fontes set url = 'https://www.palhoca.sc.gov.br/noticias', frequencia_horas = 24, ativo = true where id = %s", (fid,))
    limpo.execute("delete from radar_execucoes where fonte_id = %s", (fid,))
    aud = limpo.execute("select acao, usuario::text from radar_auditoria where tabela = 'radar_fontes' and registro_id = %s and usuario is not null order by id", (str(fid),)).fetchall()
    assert aud[0] == ("INSERT", ADMIN) and set(aud[1:]) == {("UPDATE", ADMIN)}
    # fonte com captura não se exclui (desativa-se); sem captura, o administrador exclui
    cap = limpo.execute("insert into radar_capturas (fonte_id, url, titulo, hash_titulo) values (%s, 'https://www.palhoca.sc.gov.br/noticias/1', 'N', 'h') returning id", (fid,)).fetchone()[0]
    with como("authenticated", ADMIN) as c:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            c.execute("delete from radar_fontes where id = %s", (fid,))
    limpo.execute("delete from radar_capturas where id = %s", (cap,))
    with como("authenticated", EDITOR) as c:
        assert c.execute("delete from radar_fontes where id = %s returning id", (fid,)).fetchone() is None
    with como("authenticated", ADMIN) as c:
        assert c.execute("delete from radar_fontes where id = %s returning id", (fid,)).fetchone() == (fid,)
    assert limpo.execute("select count(*) from radar_fontes").fetchone()[0] == 6


def test_registro_no_site_mostra_a_fundamentacao_e_avisa_quando_a_base_cai(limpo):
    a, c1 = fundamentado(limpo)
    aprovar(c1)
    d = registrar_site(c1)
    with como("authenticated", LEITOR) as c:
        fund, caiu = c.execute("select fundamentacao, base_caiu from radar_v_divulgacoes where id = %s", (d,)).fetchone()
    assert len(fund) == 1 and fund[0]["dispositivo"] == "art. 2º" and caiu is False
    limpo.execute("update radar_assuntos set situacao_confirmacao = 'nao_confirmado' where id = %s", (a,))
    assert limpo.execute("select base_caiu from radar_v_divulgacoes").fetchone()[0] is True
    limpo.execute("update radar_assuntos set situacao_confirmacao = 'confirmado_oficialmente' where id = %s", (a,))
    assert limpo.execute("select base_caiu from radar_v_divulgacoes").fetchone()[0] is False
    limpo.execute("delete from radar_evidencias where assunto_id = %s", (a,))
    fund2, caiu = limpo.execute("select fundamentacao, base_caiu from radar_v_divulgacoes").fetchone()
    assert caiu is True and fund2 == fund                       # o registro guarda o que valia quando foi feito


def test_endereco_em_forma_unica():
    with conectar() as c:
        for entrada, saida in [("https://x.gov.br/a/", "https://x.gov.br/a"), ("https://x.gov.br/a#b", "https://x.gov.br/a"), ("https://x.gov.br/", "https://x.gov.br"),
                               ("https://x.gov.br/a?id=1&utm_source=z", "https://x.gov.br/a?id=1"), ("https://x.gov.br/a?utm_source=z&id=1", "https://x.gov.br/a?id=1"),
                               ("  https://x.gov.br/a?id=1  ", "https://x.gov.br/a?id=1"), ("https://x.gov.br/a?fbclid=q", "https://x.gov.br/a")]:
            assert c.execute("select radar_url_base(%s)", (entrada,)).fetchone()[0] == saida, entrada


# ----------------------------------------------------------------------- relevância das capturas (v0.6.0)
def _cap(db, titulo, resumo="", n=[0]):
    n[0] += 1
    return db.execute("""insert into radar_capturas (fonte_id, url, titulo, hash_titulo, resumo_fonte)
                         select id, %s, %s, md5(%s), %s from radar_fontes where slug = 'rfb-noticias'
                         returning id, relevancia, relevancia_pontos, relevancia_motivos""",
                      (f"https://www.gov.br/receitafederal/rel-{n[0]}", titulo, titulo + str(n[0]), resumo)).fetchone()


@pytest.mark.parametrize("titulo,esperado", [
    ("Receita prorroga prazo de adesão ao Simples Nacional", "alta"),
    ("Comitê Gestor do IBS publica orientação sobre a CBS", "alta"),
    ("Instrução Normativa altera regras da DCTFWeb", "alta"),
    ("Receita Federal apreende 2 toneladas de maconha no porto de Itajaí", "baixa"),
    ("Leilão de mercadorias apreendidas tem lances até sexta", "baixa"),
    ("Receita Federal agora está no Instagram", "baixa"),
    ("Nota sobre o atendimento na próxima semana", "baixa"),
    ("Receita publica novo guia para o cidadão", "media"),
])
def test_relevancia_calculada_na_captura(limpo, titulo, esperado):
    assert _cap(limpo, titulo)[1] == esperado


def test_relevancia_titulo_vale_o_dobro_palavra_inteira_e_sem_acento(limpo):
    _, nivel, pontos, motivos = _cap(limpo, "Novidade no ICMS")                 # título: 4 x 2
    assert (nivel, pontos) == ("alta", 8) and motivos == [{"termo": "ICMS", "pontos": 8}]
    _, nivel, pontos, _ = _cap(limpo, "Comunicado geral", resumo="Trata do icms de SC")   # só no resumo: 4
    assert (nivel, pontos) == ("media", 4)
    assert _cap(limpo, "O meio de transporte foi alterado")[2] == 0             # "MEI" não casa com "meio"
    assert _cap(limpo, "SUBSTITUICAO TRIBUTARIA sem acento e em maiúsculas")[2] >= 8
    assert _cap(limpo, "Reunião sobre a NFS-e hoje")[2] == 8                    # termo com hífen


def test_relevancia_aceita_termo_com_pontuacao_nas_pontas(limpo):
    antes = limpo.execute("select valor from radar_config where chave = 'relevancia'").fetchone()[0]
    novo = dict(antes, termos=antes["termos"] + [{"termo": "S.A.", "pontos": 5}, {"termo": "Ltda.", "pontos": 3}, {"termo": ".gov", "pontos": 2}])
    nossos = {"S.A.", "Ltda.", ".gov"}
    casou = lambda titulo: [m for m in _cap(limpo, titulo)[3] if m["termo"] in nossos]   # só os termos deste teste
    try:
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(novo),))
        assert casou("Petrobras S.A. anuncia mudança") == [{"termo": "S.A.", "pontos": 10}]
        assert casou("Comunicado da Petrobras S.A., hoje") == [{"termo": "S.A.", "pontos": 10}]     # pontuação colada depois
        assert casou("Mercado Ltda. muda de endereço") == [{"termo": "Ltda.", "pontos": 6}]
        assert casou("Portal www.exemplo.gov fora do ar") == [{"termo": ".gov", "pontos": 4}]
        assert casou("Sigla SS.A. não é a mesma coisa") == []                 # "S.A." precisa começar como palavra
        assert casou("Empresa Ltdax sem ponto") == []
    finally:
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(antes),))


def test_relevancia_fila_painel_e_assunto_herdam(limpo):
    alta = _cap(limpo, "Prazo do Simples Nacional é prorrogado")[0]
    baixa = _cap(limpo, "Apreensão de cigarros na fronteira")[0]
    with como("authenticated", EDITOR) as c:
        fila = dict(c.execute("select id, relevancia from radar_v_fila").fetchall())
        assert fila == {alta: "alta", baixa: "baixa"}
        assert c.execute("select na_fila, na_fila_alta, na_fila_baixa from radar_v_painel").fetchone() == (1, 1, 1)
        a = c.execute("select radar_abrir_assunto(%s)", (alta,)).fetchone()[0]
        assert c.execute("select relevancia from radar_assuntos where id = %s", (a,)).fetchone()[0] == "alta"


def test_relevancia_mudar_as_regras_reavalia_a_fila_e_so_admin_muda(limpo):
    cap = _cap(limpo, "Prefeitura de Palhoça divulga calendário do alvará")[0]
    assert limpo.execute("select relevancia from radar_capturas where id = %s", (cap,)).fetchone()[0] == "baixa"
    antes = limpo.execute("select valor from radar_config where chave = 'relevancia'").fetchone()[0]
    novo = dict(antes, termos=antes["termos"] + [{"termo": "alvará", "pontos": 6}])
    try:
        with como("authenticated", EDITOR) as c:
            c.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(novo),))
            assert c.execute("select valor = %s::jsonb from radar_config where chave = 'relevancia'", (json.dumps(antes),)).fetchone()[0]
        with como("authenticated", ADMIN) as c:
            c.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(novo),))
        assert limpo.execute("select relevancia, relevancia_pontos from radar_capturas where id = %s", (cap,)).fetchone() == ("alta", 12)
    finally:
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(antes),))
    assert limpo.execute("select relevancia from radar_capturas where id = %s", (cap,)).fetchone()[0] == "baixa"


def test_relevancia_regras_malformadas_nao_travam_a_coleta(limpo):
    antes = limpo.execute("select valor from radar_config where chave = 'relevancia'").fetchone()[0]
    try:
        for ruim in ['{"termos": "x"}', '[]', '{"termos": [{"termo": "(", "pontos": 5}, {"termo": "a+*[", "pontos": 5}, 7, {"termo": "x"}, {"termo": "prazo", "pontos": "3"}]}']:
            limpo.execute("update radar_config set valor = %s::jsonb where chave = 'relevancia'", (ruim,))
            assert _cap(limpo, "Prazo ( com a+*[ no título")[1] in ("alta", "media", "baixa")
        # números absurdos são contidos: a coleta do robô não trava e salvar não dá erro
        limpo.execute("""update radar_config set valor = '{"limite_alta": 1e30, "limite_media": -1e30, "termos": [{"termo": "prazo", "pontos": 1500000000}]}'::jsonb where chave = 'relevancia'""")
        with como("service_role") as c:
            c.execute("""insert into radar_capturas (fonte_id, url, titulo, hash_titulo) select id, 'https://www.gov.br/receitafederal/absurdo', 'Prazo novo', 'x1' from radar_fontes where slug = 'rfb-noticias'""")
        assert limpo.execute("select relevancia, relevancia_pontos from radar_capturas where titulo = 'Prazo novo'").fetchone() == ("media", 2000)
        limpo.execute("delete from radar_config where chave = 'relevancia'")
        assert _cap(limpo, "Apreensão de cigarros")[1] == "media"               # sem regras, nada é escondido
    finally:
        limpo.execute("insert into radar_config (chave, valor) values ('relevancia', %s) on conflict (chave) do update set valor = excluded.valor", (json.dumps(antes),))


def test_ignorar_capturas_em_lote(limpo):
    ids = [_cap(limpo, f"Apreensão de cigarros número {i}")[0] for i in range(4)]
    with como("authenticated", LEITOR) as c:
        with pytest.raises(psycopg.Error):
            c.execute("select radar_ignorar_capturas(%s)", (ids,))
    with como("authenticated", EDITOR) as c:
        a = c.execute("select radar_abrir_assunto(%s)", (ids[0],)).fetchone()[0]                    # já tem assunto: fica como está
        assert c.execute("select radar_ignorar_capturas(%s)", (ids + [ids[1]],)).fetchone()[0] == 3
        assert c.execute("select count(*) from radar_v_fila").fetchone()[0] == 0
        assert c.execute("select status from radar_assuntos where id = %s", (a,)).fetchone()[0] == "capturado"
        assert c.execute("select count(*) from radar_assuntos where status = 'ignorado'").fetchone()[0] == 3
        with pytest.raises(psycopg.Error, match="RADAR043"):
            c.execute("select radar_ignorar_capturas(%s)", (list(range(1, 502)),))
    with como("anon") as c:
        with pytest.raises(psycopg.Error):
            c.execute("select radar_ignorar_capturas(%s)", (ids,))


def test_reavaliacao_so_mexe_na_fila_e_nao_gera_auditoria_nem_versao(limpo):
    triada = _cap(limpo, "Calendário do alvará — já triada")[0]
    fila = _cap(limpo, "Calendário do alvará — na fila")[0]
    with como("authenticated", EDITOR) as c:
        c.execute("select radar_abrir_assunto(%s)", (triada,))
    antes = limpo.execute("select valor from radar_config where chave = 'relevancia'").fetchone()[0]
    aud = limpo.execute("select count(*) from radar_auditoria where tabela = 'radar_capturas'").fetchone()[0]
    try:
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'",
                      (json.dumps(dict(antes, termos=antes["termos"] + [{"termo": "alvará", "pontos": 6}])),))
        assert dict(limpo.execute("select id, relevancia from radar_capturas").fetchall()) == {triada: "baixa", fila: "alta"}
        assert limpo.execute("select count(*) from radar_capturas_versoes").fetchone()[0] == 0
        assert limpo.execute("select count(*) from radar_auditoria where tabela = 'radar_capturas'").fetchone()[0] == aud
    finally:
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(antes),))


def test_imagem_trocada_ou_de_conteudo_apagado_nao_fica_sobrando(limpo):
    a = novo_assunto(limpo)
    with como("authenticated", EDITOR) as c:
        img = [c.execute("insert into radar_imagens (dados, largura, altura) values ('data:image/jpeg;base64,' || repeat('A', 200), 10, 10) returning id").fetchone()[0] for _ in range(3)]
        c1 = c.execute("insert into radar_conteudos (assunto_id, formato, titulo, corpo, imagem_id) values (%s, 'flash', 'Um', 'Texto do conteúdo um.', %s) returning id", (a, img[0])).fetchone()[0]
        c2 = c.execute("insert into radar_conteudos (assunto_id, formato, titulo, corpo, imagem_id) values (%s, 'flash', 'Dois', 'Texto do conteúdo dois.', %s) returning id", (a, img[0])).fetchone()[0]
        c.execute("update radar_conteudos set imagem_id = %s where id = %s", (img[1], c1))          # a antiga ainda é usada pelo outro
        assert c.execute("select count(*) from radar_imagens").fetchone()[0] == 3
        c.execute("update radar_conteudos set imagem_id = %s where id = %s", (img[2], c2))          # agora ninguém usa a primeira
        assert [r[0] for r in c.execute("select id from radar_imagens order by id").fetchall()] == img[1:]
        c.execute("update radar_conteudos set imagem_id = null where id = %s", (c1,))
        assert [r[0] for r in c.execute("select id from radar_imagens order by id").fetchall()] == img[2:]
        c.execute("update radar_conteudos set titulo = 'Dois, revisto' where id = %s", (c2,))        # mexer em outro campo não apaga nada
        assert c.execute("select count(*) from radar_imagens").fetchone()[0] == 1
    with como("authenticated", ADMIN) as c:
        c.execute("delete from radar_conteudos where id = %s", (c2,))
        assert c.execute("select count(*) from radar_imagens").fetchone()[0] == 0


# ----------------------------------------------------------------------- v0.7.0: avaliação da IA, repetições e "em alta"
def _avaliar(itens, papel="service_role", uid=None):
    with como(papel, uid) as c:
        return c.execute("select radar_gravar_avaliacao_ia(%s::jsonb)", (json.dumps(itens),)).fetchone()[0]


def test_avaliacao_da_ia_so_o_robo_grava_e_itens_ruins_sao_pulados(limpo):
    a = _cap(limpo, "Receita prorroga prazo do Simples Nacional")[0]
    b = _cap(limpo, "Prazo do Simples Nacional é prorrogado, diz Receita")[0]
    for papel, uid in (("anon", None), ("authenticated", EDITOR), ("authenticated", ADMIN)):
        with pytest.raises(psycopg.Error):
            _avaliar([{"id": a, "nota": 9}], papel, uid)
    r = _avaliar([{"id": a, "nota": 9.4, "motivo": "  prazo novo para optantes  ", "tema": "prazo simples nacional"},
                  {"id": b, "nota": 99, "motivo": "x" * 500, "tema": "prazo simples nacional", "igual_a": a},
                  {"id": 999999, "nota": 5}, {"id": a}, "lixo", {"id": "1; drop", "nota": 1}, {"id": b, "nota": 1e40}])
    assert r == {"gravadas": 3, "repetidas": 1, "juntadas_a_assunto": 0, "puladas": 4}      # a nota absurda (1e40) é contida em 10
    assert limpo.execute("select id, ia_nota, ia_motivo, ia_tema, duplicata_de, ia_avaliado_em is not null from radar_capturas order by id").fetchall() == [
        (a, 9, "prazo novo para optantes", "prazo simples nacional", None, True), (b, 10, None, None, a, True)]        # a segunda avaliação do mesmo item substitui a primeira; a repetição marcada fica
    with pytest.raises(psycopg.Error, match="RADAR044"):
        _avaliar({"id": a, "nota": 1})
    with pytest.raises(psycopg.Error, match="RADAR044"):
        _avaliar([{"id": a, "nota": 1}] * 201)
    # a avaliação não mexe na nota por palavras, não cria versão nem auditoria da captura
    assert limpo.execute("select relevancia from radar_capturas where id = %s", (a,)).fetchone()[0] == "alta"
    assert limpo.execute("select count(*) from radar_capturas_versoes").fetchone()[0] == 0


def test_repeticao_nao_aponta_para_si_nem_forma_ciclo_e_sobe_ate_a_origem(limpo):
    a, b, c = (_cap(limpo, f"Notícia do Simples Nacional {i}")[0] for i in range(3))
    _avaliar([{"id": b, "nota": 7, "igual_a": a}])
    _avaliar([{"id": c, "nota": 7, "igual_a": b}])                    # repetição de repetição: aponta para a origem
    _avaliar([{"id": a, "nota": 7, "igual_a": c}, {"id": a, "nota": 7, "igual_a": a}])   # a origem não vira repetição de quem depende dela
    assert dict(limpo.execute("select id, duplicata_de from radar_capturas").fetchall()) == {a: None, b: a, c: a}
    with como("authenticated", EDITOR) as k:
        assert dict(k.execute("select id, repetidas from radar_v_fila").fetchall()) == {a: 2, b: 0, c: 0}


def test_abrir_ou_ignorar_leva_as_repeticoes_junto_e_a_repeticao_tardia_entra_no_mesmo_assunto(limpo):
    a, b, c, d = (_cap(limpo, f"Receita prorroga prazo do Simples — fonte {i}")[0] for i in range(4))
    outro = _cap(limpo, "IBS: novo regulamento publicado")[0]
    _avaliar([{"id": a, "nota": 9}, {"id": b, "nota": 9, "igual_a": a}, {"id": outro, "nota": 8}])
    with como("authenticated", EDITOR) as k:
        assunto = k.execute("select radar_abrir_assunto(%s)", (b,)).fetchone()[0]           # abre pela repetição: a origem vem junto
        assert sorted(x[0] for x in k.execute("select captura_id from radar_assunto_capturas where assunto_id = %s", (assunto,)).fetchall()) == [a, b]
        assert sorted(x[0] for x in k.execute("select id from radar_v_fila").fetchall()) == [c, d, outro]
    # o robô encontra depois outra fonte com o mesmo fato: entra no mesmo assunto e não volta à triagem
    assert _avaliar([{"id": c, "nota": 9, "igual_a": b}])["juntadas_a_assunto"] == 1
    assert limpo.execute("select assunto_id from radar_assunto_capturas where captura_id = %s", (c,)).fetchone()[0] == assunto
    assert limpo.execute("select juntada_pela_ia_em is not null from radar_assunto_capturas where captura_id = %s", (c,)).fetchone()[0]
    aud = limpo.execute("select depois from radar_auditoria where tabela = 'radar_assunto_capturas' and registro_id = %s", (f"{assunto}:{c}",)).fetchone()[0]
    assert aud["juntada_pela_ia"] is True and aud["repeticao_de"] == a
    # origem ignorada: a repetição NÃO some sozinha — fica na triagem, como principal, avisando de que assunto parece ser
    with como("authenticated", EDITOR) as k:
        ign = k.execute("select radar_abrir_assunto(%s, true)", (outro,)).fetchone()[0]
    assert _avaliar([{"id": d, "nota": 8, "igual_a": outro}])["juntadas_a_assunto"] == 0
    assert limpo.execute("select count(*) from radar_assunto_capturas where captura_id = %s", (d,)).fetchone()[0] == 0
    with como("authenticated", EDITOR) as k:
        fila = k.execute("select id, principal, origem_assunto_id, origem_assunto from radar_v_fila").fetchall()
        assert fila == [(d, True, ign, "IBS: novo regulamento publicado (ignorado)")] and ign != assunto
        assert [x[0] for x in k.execute("select id from radar_v_em_alta").fetchall()] == [d]


def test_nao_e_o_mesmo_fato_devolve_a_captura_para_a_triagem(limpo):
    a, b, c = (_cap(limpo, f"Receita prorroga prazo do Simples — fonte {i}")[0] for i in range(3))
    _avaliar([{"id": a, "nota": 9}, {"id": b, "nota": 8, "igual_a": a}])
    with como("authenticated", EDITOR) as k:
        assunto = k.execute("select radar_abrir_assunto(%s)", (a,)).fetchone()[0]
    _avaliar([{"id": c, "nota": 7, "igual_a": a}])
    for papel, uid in (("anon", None), ("authenticated", LEITOR), ("service_role", None)):
        with como(papel, uid) as k:
            with pytest.raises(psycopg.Error):
                k.execute("select radar_separar_captura(%s, %s)", (assunto, c))
    with como("authenticated", EDITOR) as k:
        # só desfaz o que entrou como repetição: "a" foi a captura que a pessoa abriu
        with pytest.raises(psycopg.Error, match="RADAR045"):
            k.execute("select radar_separar_captura(%s, %s)", (assunto, a))
    with como("authenticated", EDITOR) as k:
        k.execute("select radar_separar_captura(%s, %s)", (assunto, c))
        assert k.execute("select id, principal, duplicata_de from radar_v_fila").fetchall() == [(c, True, None)]
        # a que veio junto na abertura do assunto ("b") também pode ser separada
        k.execute("select radar_separar_captura(%s, %s)", (assunto, b))
        assert sorted(x[0] for x in k.execute("select id from radar_v_fila").fetchall()) == [b, c]
    assert limpo.execute("select acao, usuario::text, antes->>'motivo' from radar_auditoria where tabela = 'radar_assunto_capturas' and registro_id = %s order by id desc limit 1",
                         (f"{assunto}:{c}",)).fetchone() == ("DELETE", EDITOR, "não é o mesmo fato")
    # com evidência registrada na captura, ela não sai do assunto
    _avaliar([{"id": c, "nota": 7, "igual_a": a}])
    assert limpo.execute("select count(*) from radar_assunto_capturas where captura_id = %s and juntada_pela_ia_em is not null", (c,)).fetchone()[0] == 1
    limpo.execute("update radar_capturas set texto = 'O prazo fica prorrogado até 31 de março.' where id = %s", (c,))
    limpo.execute("insert into radar_evidencias (assunto_id, captura_id, trecho_literal) values (%s, %s, 'O prazo fica prorrogado até 31 de março.')", (assunto, c))
    with como("authenticated", EDITOR) as k:
        with pytest.raises(psycopg.Error, match="RADAR046"):
            k.execute("select radar_separar_captura(%s, %s)", (assunto, c))


def test_repeticao_escondida_so_enquanto_a_origem_esta_na_fila_e_a_nota_do_grupo_e_a_maior(limpo):
    a, b = (_cap(limpo, f"Receita prorroga prazo do Simples — fonte {i}")[0] for i in range(2))
    _avaliar([{"id": a, "nota": 4}, {"id": b, "nota": 9, "igual_a": a}])
    with como("authenticated", EDITOR) as k:
        assert k.execute("select id, principal, nota_grupo from radar_v_fila order by id").fetchall() == [(a, True, 9), (b, False, 9)]
        assert [x[0] for x in k.execute("select id from radar_v_em_alta").fetchall()] == [a]      # entra pela nota da repetição
        assert k.execute("select na_fila, na_fila_principal, em_alta from radar_v_painel").fetchone() == (2, 1, 1)
        # ignorar em lote devolve quantas saíram da triagem (a repetição vai junto)
        assert k.execute("select radar_ignorar_capturas(%s)", ([a],)).fetchone()[0] == 2
        assert k.execute("select count(*) from radar_v_fila").fetchone()[0] == 0


def test_so_vai_junto_o_que_a_tela_mostra_recolhido(limpo):
    a, b, c, d, e = (_cap(limpo, f"Receita prorroga prazo do Simples — fonte {i}")[0] for i in range(5))
    _avaliar([{"id": a, "nota": 5}, {"id": b, "nota": 2, "igual_a": a}, {"id": c, "nota": 9, "igual_a": a}])
    with como("authenticated", EDITOR) as k:
        # ignorar a repetição recolhida ignora só ela: a origem e a outra repetição continuam na triagem
        assert k.execute("select radar_ignorar_capturas(%s)", ([b],)).fetchone()[0] == 1
        assert k.execute("select id, repetidas, principal from radar_v_fila where id in (%s, %s) order by id", (a, c)).fetchall() == [(a, 1, True), (c, 0, False)]
        ign = k.execute("select radar_abrir_assunto(%s, true)", (a,)).fetchone()[0]        # ignorar o cartão principal leva a recolhida
        assert sorted(x[0] for x in k.execute("select captura_id from radar_assunto_capturas where assunto_id = %s", (ign,)).fetchall()) == [a, c]
    # duas repetições de uma origem já ignorada têm, cada uma, o seu cartão: abrir uma não leva a outra
    _avaliar([{"id": d, "nota": 8, "igual_a": a}, {"id": e, "nota": 4, "igual_a": a}])
    with como("authenticated", EDITOR) as k:
        assert k.execute("select id, principal, repetidas from radar_v_fila order by id").fetchall() == [(d, True, 0), (e, True, 0)]
        novo = k.execute("select radar_abrir_assunto(%s)", (d,)).fetchone()[0]
        assert k.execute("select captura_id from radar_assunto_capturas where assunto_id = %s", (novo,)).fetchall() == [(d,)]
        # a que sobrou é avisada do assunto EM ANDAMENTO do mesmo fato (e não do ignorado)
        assert k.execute("select id, origem_assunto_id from radar_v_fila").fetchall() == [(e, novo)]
    # e a próxima repetição que chegar entra sozinha nesse assunto em andamento, mesmo com a origem ignorada
    f = _cap(limpo, "Receita prorroga prazo do Simples — fonte 5")[0]
    assert _avaliar([{"id": f, "nota": 7, "igual_a": d}])["juntadas_a_assunto"] == 1
    assert limpo.execute("select assunto_id from radar_assunto_capturas where captura_id = %s", (f,)).fetchone()[0] == novo
    # ninguém marca à mão um vínculo comum como "juntado pela IA" para poder removê-lo
    with como("authenticated", EDITOR) as k:
        with pytest.raises(psycopg.Error):
            k.execute("update radar_assunto_capturas set juntada_pela_ia_em = now() where captura_id = %s", (d,))


def test_titulo_alterado_pede_nova_avaliacao_da_ia(limpo):
    a = _cap(limpo, "Receita prorroga prazo do Simples Nacional")[0]
    _avaliar([{"id": a, "nota": 9}])
    limpo.execute("update radar_capturas set resumo_fonte = 'outro resumo' where id = %s", (a,))
    assert limpo.execute("select ia_avaliado_em is not null from radar_capturas where id = %s", (a,)).fetchone()[0]
    limpo.execute("update radar_capturas set titulo = 'Receita revoga prorrogação do Simples Nacional' where id = %s", (a,))
    assert limpo.execute("select ia_avaliado_em, ia_nota from radar_capturas where id = %s", (a,)).fetchone() == (None, 9)


def test_em_alta_mostra_so_os_melhores_sem_repeticao_e_respeita_a_configuracao(limpo):
    ids = [_cap(limpo, f"Receita altera prazo do Simples Nacional — caso {i}")[0] for i in range(14)]
    baixa = _cap(limpo, "Apreensão de cigarros na fronteira")[0]
    _avaliar([{"id": i, "nota": n} for i, n in zip(ids, [10, 9, 9, 8, 8, 8, 7, 7, 7, 6, 6, 5, 3, 0])] + [{"id": baixa, "nota": 10}])
    _avaliar([{"id": ids[1], "nota": 9, "igual_a": ids[0]}])
    sem_nota = _cap(limpo, "ICMS: novo decreto de Santa Catarina")[0]
    with como("authenticated", EDITOR) as k:
        alta = k.execute("select id, ia_nota from radar_v_em_alta").fetchall()
        # 10 itens: nota ≥ 6 em ordem, sem a repetição, sem a de baixa relevância; a ainda não avaliada entra no fim
        assert [x[0] for x in alta] == [ids[n] for n in (0, 2, 5, 4, 3, 8, 7, 6, 10, 9)]        # no empate, a mais recente primeiro
        assert k.execute("select em_alta, sem_avaliacao_ia from radar_v_painel").fetchone() == (10, 1)
    antes = limpo.execute("select valor from radar_config where chave = 'relevancia'").fetchone()[0]
    try:
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(dict(antes, nota_corte=8, quantidade=20)),))
        with como("authenticated", LEITOR) as k:
            assert [x[0] for x in k.execute("select id from radar_v_em_alta").fetchall()] == [ids[0], ids[2], ids[5], ids[4], ids[3], sem_nota]
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(dict(antes, nota_corte="x", quantidade=-5)),))
        with como("authenticated", LEITOR) as k:
            assert len(k.execute("select id from radar_v_em_alta").fetchall()) == 1            # quantidade mínima 1; corte inválido = padrão
    finally:
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(antes),))
    with como("anon") as k:
        with pytest.raises(psycopg.Error):
            k.execute("select * from radar_v_em_alta")


def test_fonte_do_conteudo_ja_vem_com_o_orgao_da_captura_oficial(limpo):
    cap = nova_captura(limpo)
    a = novo_assunto(limpo)
    limpo.execute("insert into radar_assunto_capturas values (%s, %s)", (a, cap))
    with como("authenticated", EDITOR) as c:
        cid = c.execute("insert into radar_conteudos (assunto_id, formato, titulo, corpo) values (%s, 'flash', 'T', 'Texto do conteúdo.') returning id", (a,)).fetchone()[0]
        assert c.execute("select fonte_credito from radar_conteudos where id = %s", (cid,)).fetchone()[0] == "Receita Federal do Brasil"
        # o que a pessoa informou é respeitado; apagar depois também
        c2 = c.execute("insert into radar_conteudos (assunto_id, formato, titulo, corpo, fonte_credito) values (%s, 'flash', 'T2', 'Texto do conteúdo.', 'Portal X') returning id", (a,)).fetchone()[0]
        assert c.execute("select fonte_credito from radar_conteudos where id = %s", (c2,)).fetchone()[0] == "Portal X"
        c.execute("update radar_conteudos set fonte_credito = null where id = %s", (cid,))
        assert c.execute("select fonte_credito from radar_conteudos where id = %s", (cid,)).fetchone()[0] is None
        # assunto criado pela equipe, sem captura: fica vazio
        solto = c.execute("insert into radar_assuntos (titulo) values ('Sem captura') returning id").fetchone()[0]
        c3 = c.execute("insert into radar_conteudos (assunto_id, formato, titulo, corpo) values (%s, 'flash', 'T3', 'Texto do conteúdo.') returning id", (solto,)).fetchone()[0]
        assert c.execute("select fonte_credito from radar_conteudos where id = %s", (c3,)).fetchone()[0] is None


def test_imagens_sem_uso_sao_apagadas_so_pelo_robo_e_so_as_antigas(limpo):
    usada = limpo.execute("insert into radar_imagens (dados) values (%s) returning id", (PIXEL,)).fetchone()[0]
    antiga = limpo.execute("insert into radar_imagens (dados) values (%s) returning id", (PIXEL,)).fetchone()[0]
    recente = limpo.execute("insert into radar_imagens (dados) values (%s) returning id", (PIXEL,)).fetchone()[0]
    limpo.execute("update radar_imagens set criado_em = now() - interval '3 days' where id in (%s, %s)", (usada, antiga))
    cid = novo_conteudo(limpo, novo_assunto(limpo))
    limpo.execute("update radar_conteudos set imagem_id = %s where id = %s", (usada, cid))
    for papel, uid in (("authenticated", ADMIN), ("authenticated", EDITOR), ("anon", None)):
        with como(papel, uid) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select radar_limpar_imagens_sem_uso()")
    with como("service_role") as c:
        assert c.execute("select radar_limpar_imagens_sem_uso()").fetchone()[0] == 1
        assert c.execute("select radar_limpar_imagens_sem_uso(0)").fetchone()[0] == 0        # nunca menos de 1 hora
    restantes = {r[0] for r in limpo.execute("select id from radar_imagens").fetchall()}
    assert restantes == {usada, recente}                    # a usada e a recém-enviada ficam


def test_atualizacao_da_v0_7_0_para_a_v0_7_1_preserva_os_dados_e_aplica_duas_vezes():
    with conectar("postgres") as c:
        c.execute("drop database if exists radar_up7 with (force)")
        c.execute("create database radar_up7")
    try:
        assert psql(RAIZ / "testes" / "supabase_simulado.sql", "radar_up7").returncode == 0
        r = psql(RAIZ / "testes" / "radar-setup-v0.7.0-referencia.sql", "radar_up7")
        assert r.returncode == 0, r.stderr
        with conectar("radar_up7") as c:
            cap = nova_captura(c)
            a = novo_assunto(c)
            c.execute("insert into radar_assunto_capturas values (%s, %s)", (a, cap))
            cid = novo_conteudo(c, a)
            img = c.execute("insert into radar_imagens (dados) values (%s) returning id", (PIXEL,)).fetchone()[0]
            c.execute("update radar_conteudos set imagem_id = %s where id = %s", (img, cid))
            antes = c.execute("select count(*) from radar_capturas").fetchone()[0]
        for _ in range(2):
            r = psql(SETUP, "radar_up7")
            assert r.returncode == 0, r.stderr
        with conectar("radar_up7") as c:
            assert c.execute("select array_agg(distinct versao order by versao) from radar_instalacoes").fetchone()[0] == ["v0.7.0", "v0.7.1"]
            assert c.execute("select count(*) from radar_capturas").fetchone()[0] == antes
            assert c.execute("select imagem_id from radar_conteudos where id = %s", (cid,)).fetchone()[0] == img
            assert c.execute("select to_regprocedure('public.radar_limpar_imagens_sem_uso(int)')").fetchone()[0] is not None
            assert c.execute("select count(*) from radar_instalacoes where depois is null").fetchone()[0] == 0
    finally:
        with conectar("postgres") as c:
            c.execute("drop database if exists radar_up7 with (force)")


def test_atualizacao_da_v0_6_0_para_a_versao_atual_preserva_os_dados_e_aplica_duas_vezes():
    with conectar("postgres") as c:
        c.execute("drop database if exists radar_up6 with (force)")
        c.execute("create database radar_up6")
    try:
        assert psql(RAIZ / "testes" / "supabase_simulado.sql", "radar_up6").returncode == 0
        r = psql(RAIZ / "testes" / "radar-setup-v0.6.0-referencia.sql", "radar_up6")
        assert r.returncode == 0, r.stderr
        with conectar("radar_up6") as c:
            c.execute("insert into auth.users (id, email) values (%s, 'e')", (EDITOR,))
            c.execute("insert into radar_perfis (user_id, nome, papel) values (%s, 'E', 'editor')", (EDITOR,))
            cap = nova_captura(c)
            solta = _cap(c, "Receita prorroga prazo do Simples Nacional")[0]
            a = novo_assunto(c)
            c.execute("insert into radar_assunto_capturas values (%s, %s)", (a, cap))
            cid = novo_conteudo(c, a)
        for _ in range(2):
            r = psql(SETUP, "radar_up6")
            assert r.returncode == 0, r.stderr
        with conectar("radar_up6") as c:
            assert c.execute("select array_agg(distinct versao order by versao) from radar_instalacoes").fetchone()[0] == ["v0.6.0", "v0.7.1"]
            assert c.execute("select ia_nota, ia_avaliado_em, duplicata_de from radar_capturas where id = %s", (solta,)).fetchone() == (None, None, None)
            assert c.execute("select juntada_pela_ia_em from radar_assunto_capturas where captura_id = %s", (cap,)).fetchone()[0] is None
            assert c.execute("select fonte_credito from radar_conteudos where id = %s", (cid,)).fetchone()[0] is None   # conteúdo antigo não é mexido
            assert c.execute("select id, principal, nota_grupo from radar_v_fila").fetchall() == [(solta, True, None)]
            assert c.execute("select em_alta, sem_avaliacao_ia, na_fila_principal from radar_v_painel").fetchone() == (1, 1, 1)
        assert psql(REVERSAO, "radar_up6").returncode == 0
        with conectar("radar_up6") as c:
            assert c.execute("select to_regprocedure('public.radar_separar_captura(bigint,bigint)'), to_regclass('public.radar_v_em_alta')").fetchone() == (None, None)
    finally:
        with conectar("postgres") as c:
            c.execute("drop database if exists radar_up6 with (force)")


# ------------------------------------------------ fontes novas (outubro/2026) e boletim por e-mail
FONTES_NOVAS = RAIZ / "sql" / "radar-fontes-novas-2026-10.sql"


def test_fontes_novas_entram_desligadas_e_o_sql_pode_rodar_de_novo(limpo):
    assert psql(FONTES_NOVAS).returncode == 0
    linhas = dict((s, (a, o)) for s, a, o in limpo.execute(
        "select slug, ativo, oficial from radar_fontes where slug in "
        "('dou-destaques','econet-blog','portalcontabilsc-noticias','itc-email')").fetchall())
    assert linhas == {"dou-destaques": (False, True), "econet-blog": (False, False),
                      "portalcontabilsc-noticias": (False, False), "itc-email": (True, False)}
    limpo.execute("update radar_fontes set ativo = true where slug = 'econet-blog'")
    assert psql(FONTES_NOVAS).returncode == 0                   # de novo: não desfaz o que você ligou
    assert limpo.execute("select ativo from radar_fontes where slug = 'econet-blog'").fetchone()[0] is True
    limpo.execute("delete from radar_fontes where slug in ('dou-destaques','econet-blog',"
                  "'portalcontabilsc-noticias','itc-email')")


def test_boletim_por_email_grava_cada_materia_uma_vez(limpo):
    assert psql(FONTES_NOVAS).returncode == 0
    try:
        itens = [{"titulo": "SIMPLES NACIONAL: PRAZO DE OPÇÃO PARA 2027 É PRORROGADO", "data": "2026-09-29",
                  "area": "Área Federal", "texto": "O prazo de opção foi prorrogado até 15 de outubro.", "assunto_email": "ITCNET Mail"},
                 {"titulo": "Simples Nacional - prazo de opção para 2027 é prorrogado", "data": "2026-09-29",
                  "area": "Área Federal", "texto": "Repetida no outro boletim.", "assunto_email": "Legislação & Tribunais"},
                 {"titulo": "ESOCIAL: ALTERAÇÕES NOS EVENTOS S-2410 E S-2416", "data": "2026-09-30", "area": "Trabalhista"},
                 {"titulo": "x", "data": "2026-09-30"}]                                       # título curto: ignorado
        r = limpo.execute("select radar_receber_email('itc-email', %s::jsonb)", (json.dumps(itens),)).fetchone()[0]
        assert r == {"recebidos": 2, "novos": 2, "ja_existiam": 0}
        r = limpo.execute("select radar_receber_email('itc-email', %s::jsonb)", (json.dumps(itens[:1]),)).fetchone()[0]
        assert r == {"recebidos": 1, "novos": 0, "ja_existiam": 1}                         # no dia seguinte, de novo
        linhas = limpo.execute("""select c.url, c.metadados->>'origem', c.hash_titulo from radar_capturas c
                                  join radar_fontes f on f.id = c.fonte_id where f.slug = 'itc-email' order by c.id""").fetchall()
        assert len(linhas) == 2 and all(u.startswith("https://www.itcnet.com.br/?radar=") and o == "email" for u, o, _ in linhas)
        from radar_util import hash_titulo                                                 # o mesmo hash do robô
        assert hash_titulo(itens[2]["titulo"]) in {h for _, _, h in linhas}
        assert limpo.execute("select ultimo_sucesso_em is not null from radar_fontes where slug = 'itc-email'").fetchone()[0]
        with pytest.raises(Exception, match="RADAR095"):
            limpo.execute("select radar_receber_email('rfb-noticias', '[]'::jsonb)")
    finally:
        limpo.execute("delete from radar_capturas where fonte_id in (select id from radar_fontes where slug = 'itc-email')")
        limpo.execute("delete from radar_fontes where slug in ('dou-destaques','econet-blog',"
                      "'portalcontabilsc-noticias','itc-email')")
