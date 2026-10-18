"""Testes do banco: instalação, RLS por perfil, fundamentação, aprovação, publicação e auditoria."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import re

import psycopg
import pytest

from conftest import (ADMIN, CRON_SIMULADO, EDITOR, LEITOR, RAIZ, REVERSAO, SEM_PERFIL, SETUP, VAULT_SIMULADO, carregar_fontes_novas,
                      como, conectar, psql)

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
def test_instalacao_cria_19_tabelas_com_rls(db):
    linhas = db.execute("""select c.relname, c.relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace
                           where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'radar\\_%'""").fetchall()
    assert len(linhas) == 30       # v0.32.0: + radar_vencimentos e radar_copias; v0.29.0: + radar_lembretes; v0.22.0: + radar_videos e radar_video_acessos; v0.21.0: + radar_pessoas e radar_pauta_pecas; v0.17.0: + radar_site_exclusoes; v0.8.0: saíram radar_publicacoes e radar_publicacao_normas; v0.10.0: + radar_site_envios; v0.12.0: + radar_itc_lidos; v0.13.0: + radar_redes_envios
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
    # v0.20.0: a assinatura de antes (sem a identificação legal) ganha "cnpj" e "crc" vazios, sem perder nada
    assinatura = db.execute("select valor from radar_config where chave = 'assinatura'").fetchone()[0]
    antiga = {k: v for k, v in assinatura.items() if k not in ("cnpj", "crc")}
    db.execute("update radar_config set valor = %s where chave = 'assinatura'", (json.dumps({**antiga, "local": "Florianópolis, SC"}),))
    r = psql(SETUP)
    assert r.returncode == 0, r.stderr
    assert db.execute("select valor from radar_config where chave = 'assinatura'").fetchone()[0] == {**antiga, "local": "Florianópolis, SC", "cnpj": "", "crc": ""}
    db.execute("update radar_config set valor = %s where chave = 'assinatura'", (json.dumps({**antiga, "cnpj": "79.876.769/0001-28"}),))
    assert psql(SETUP).returncode == 0                                       # com o CNPJ preenchido, só o CRC entra (vazio)
    assert db.execute("select valor from radar_config where chave = 'assinatura'").fetchone()[0] == {**antiga, "cnpj": "79.876.769/0001-28", "crc": ""}
    db.execute("update radar_config set valor = %s where chave = 'assinatura'", (json.dumps(assinatura),))
    # v0.29.0: os lembretes ajustados pelo administrador continuam como estão; apagada, a chave volta com os padrões
    lembretes = db.execute("select valor from radar_config where chave = 'lembretes'").fetchone()[0]
    assert lembretes == {"ligado": True, "hora": "16:00", "de": "08:00", "ate": "20:00", "aprovacao_horas": 24, "parada_horas": 3,
                         "pauta": True, "aprovacao": True, "video": True, "noticia": True,
                         "vencimento": True, "copia": True}                     # v0.32.0: os dois tipos novos
    db.execute("""update radar_config set valor = '{"ligado": false, "hora": "17:00"}' where chave = 'lembretes'""")
    assert psql(SETUP).returncode == 0
    # v0.32.0: o setup acrescenta só as chaves que faltam ("vencimento" e "copia", ligadas); o resto do ajuste fica
    assert db.execute("select valor from radar_config where chave = 'lembretes'").fetchone()[0] == {"ligado": False, "hora": "17:00",
                                                                                                "vencimento": True, "copia": True}
    db.execute("delete from radar_config where chave = 'lembretes'")
    assert psql(SETUP).returncode == 0
    assert db.execute("select valor from radar_config where chave = 'lembretes'").fetchone()[0] == lembretes
    depois = db.execute("select (select count(*) from radar_fontes), (select count(*) from radar_categorias), "
                        "(select count(*) from pg_policies where tablename like 'radar\\_%'), "
                        "(select count(*) from pg_trigger t join pg_class c on c.oid = t.tgrelid "
                        " where c.relname like 'radar\\_%' and not t.tgisinternal)").fetchone()
    assert antes == depois
    # ajuste feito pelo usuário NÃO é sobrescrito pela reexecução
    assert db.execute("select frequencia_horas, ativo from radar_fontes where slug = 'pgfn-noticias'").fetchone() == (9, False)
    db.execute("update radar_fontes set frequencia_horas = 6, ativo = true where slug = 'pgfn-noticias'")
    reg = db.execute("select antes, depois from radar_instalacoes order by id desc limit 1").fetchone()
    assert len(reg[0]) == 30 and len(reg[1]) == 30   # 2ª execução: já havia 30 antes (v0.29.0: + radar_lembretes; v0.32.0: + radar_vencimentos e radar_copias)


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
    assert len(tabelas) == 39 and "radar_publicacoes" not in tabelas and "radar_v_divulgacoes" in tabelas   # 30 tabelas e 9 visões (v0.32.0: + radar_vencimentos e radar_copias; v0.21.0: + radar_v_pauta_pessoas e radar_v_capas; v0.22.0: + radar_videos e radar_video_acessos; v0.29.0: + radar_lembretes)
    with como("anon") as c:
        for tabela in tabelas:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(f"select * from {tabela}")
        for sql in ["select titulo from radar_divulgacoes", "select count(*) from radar_categorias", "select id from radar_imagens",
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
def cenario_publicavel(db, situacao="confirmado_oficialmente", trecho="à alíquota de 0,9% (nove décimos por cento)",
                       slug_fonte="rfb-normas"):
    cap = nova_captura(db, slug=slug_fonte)
    a = novo_assunto(db, situacao)
    if trecho:
        db.execute("insert into radar_evidencias (assunto_id, captura_id, trecho_literal) values (%s, %s, %s)", (a, cap, trecho))
    c1 = novo_conteudo(db, a)
    return a, c1


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
            # v0.19.1 (opcional): a conferência da chave da radar-concorrentes, como o sql/radar-concorrentes.sql a deixa
            c.execute("""create function public.radar_concorrentes_conferir(p_chave text) returns boolean language sql stable as $$ select false $$;
                         revoke all on function public.radar_concorrentes_conferir(text) from public, anon, authenticated;
                         grant execute on function public.radar_concorrentes_conferir(text) to service_role""")
        assert psql(SETUP, "radar_reversao").returncode == 0
        with conectar("radar_reversao") as c:            # o setup revoga tudo de radar_* e devolve o acesso do papel interno a ela
            assert c.execute("""select has_function_privilege('service_role', 'public.radar_concorrentes_conferir(text)', 'execute'),
                                       has_function_privilege('authenticated', 'public.radar_concorrentes_conferir(text)', 'execute'),
                                       has_function_privilege('anon', 'public.radar_concorrentes_conferir(text)', 'execute')""").fetchone() == (True, False, False)
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
    """Conteúdo aprovado e registrado como publicado no site (v0.8.0: o registro substitui a publicação antiga)."""
    a, c1 = cenario_publicavel(db)
    aprovar(c1)
    return a, c1, registrar_site(c1)


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
                                                           'radar_incluir_texto_oficial', 'radar_ignorar_capturas', 'radar_separar_captura',
                                                           'radar_autorizar_site', 'radar_cancelar_site', 'radar_liberar_sem_fundamentacao', 'radar_converter_analise',
                                                           'radar_autorizar_rede', 'radar_dispensar_rede', 'radar_cancelar_rede',
                                                           'radar_separar_repeticao', 'radar_autorizar_copia',
                                                           'radar_autorizar_todos', 'radar_rede_marcar_excluida', 'radar_pedir_exclusao_site',
                                                           'radar_cancelar_exclusao_site',
                                                           -- v0.21.0: Pauta (cada função confere o papel)
                                                           'radar_pauta_importar', 'radar_pauta_conferir', 'radar_pauta_marcar_pronta',
                                                           'radar_pauta_aprovar', 'radar_pauta_desaprovar', 'radar_pauta_publicar_agora',
                                                           'radar_pauta_pode_copiar', 'radar_pauta_registrar_manual', 'radar_pauta_termo_ok',
                                                           'radar_agenda_situacao', 'radar_pauta_copia_paga_ia',
                                                           -- rodada 2: onde está a frase do boletim (só editor e administrador)
                                                           'radar_copia_paga_trechos',
                                                           -- v0.22.0: corretor de vídeo (cada função confere o papel)
                                                           'radar_video_criar', 'radar_video_para_envio', 'radar_video_enviado',
                                                           'radar_video_ajustar', 'radar_video_reconferir', 'radar_video_de_novo',
                                                           'radar_video_descartar', 'radar_video_apaguei', 'radar_video_apaguei_baixado',
                                                           'radar_video_para_previa', 'radar_video_para_baixar', 'radar_video_resumo',
                                                           'radar_video_cota',
                                                           'radar_pauta_pecas_da_pessoa',
                                                           -- v0.24.0: a Conferência das Diretrizes (cada função confere o papel)
                                                           'radar_registrar_conferencia', 'radar_assumir_conferencia', 'radar_conferencia_versao',
                                                           -- v0.24.0 (etapa 5): a revisão editorial (a função confere o papel)
                                                           'radar_registrar_revisao_editorial', 'radar_texto_versao',
                                                           -- v0.28.0: "+ Nova peça" (a função confere que é o administrador)
                                                           'radar_pauta_criar',
                                                           -- v0.29.0: a situação dos lembretes (a função confere que é o administrador)
                                                           'radar_lembretes_situacao',
                                                           -- v0.30.0: possível prorrogação na agenda (a função confere o perfil)
                                                           'radar_prorrogacoes',
                                                           -- v0.32.0: cada uma confere o papel ou a chave da agenda
                                                           'radar_vencimentos_conhecidos', 'radar_vencimentos_renovei',
                                                           'radar_copias_situacao', 'radar_copias_comecar', 'radar_copias_terminar',
                                                           'radar_copias_exportar',
                                                           -- v0.33.0: a aba Vídeo (o editor confere que é o administrador; a paleta
                                                           -- não tem dado de ninguém)
                                                           'radar_video_editar', 'radar_video_paleta')
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
    d = registrar_site(c1, temp)
    # enquanto a pessoa existe, ninguém apaga a autoria
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_conteudos set aprovado_por = null where id = %s", (c1,))
        c.execute("update radar_divulgacoes set registrado_por = null where id = %s", (d,))
    assert limpo.execute("select aprovado_por::text from radar_conteudos where id = %s", (c1,)).fetchone()[0] == temp
    assert limpo.execute("select registrado_por::text from radar_divulgacoes where id = %s", (d,)).fetchone()[0] == temp
    # excluir a pessoa funciona e os campos ficam nulos (a trilha de auditoria guarda quem foi)
    limpo.execute("delete from auth.users where id = %s", (temp,))
    assert limpo.execute("select status, aprovado_por from radar_conteudos where id = %s", (c1,)).fetchone() == ("aprovado", None)
    assert limpo.execute("select registrado_por from radar_divulgacoes where id = %s", (d,)).fetchone()[0] is None
    assert limpo.execute("select count(*) from radar_auditoria where usuario = %s", (temp,)).fetchone()[0] >= 2


def test_origem_do_texto_nao_se_reescreve(limpo):
    c1 = novo_conteudo(limpo, novo_assunto(limpo))
    aprovar(c1)
    with como("service_role") as c:
        linha = c.execute("update radar_conteudos set gerado_por = 'humano' where id = %s returning gerado_por, status", (c1,)).fetchone()
    assert linha == ("ia", "aprovado")


# ============================================================ v0.2.0 — apoio às telas
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
        p = c.execute("select fontes_ativas, na_fila, alta_relevancia, em_verificacao, aguardando_aprovacao, no_site "
                      "from radar_v_painel").fetchone()
        assert p == (6, 1, 1, 1, 1, 1)
        linha = c.execute("select evidencias, evidencias_conferidas, conteudos, orgaos, status "
                          "from radar_v_assuntos where id = %s", (a,)).fetchone()
        assert linha == (1, 1, 1, "Receita Federal do Brasil", "publicado")
    with como("authenticated", SEM_PERFIL) as c:
        assert c.execute("select na_fila, no_site from radar_v_painel").fetchone() == (0, 0)
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
            # v0.8.0: a publicação antiga não se perde — a tabela com registros fica guardada como arquivo
            assert c.execute("select slug, status from radar_publicacoes").fetchone() == ("antiga", "publicado")
            assert c.execute("""select count(*) from pg_constraint where conname = 'radar_publicacoes_imagem_id_fkey'""").fetchone()[0] == 0
            assert c.execute("select has_table_privilege('authenticated', 'radar_publicacoes', 'insert'), "
                             "has_table_privilege('authenticated', 'radar_publicacoes', 'select')").fetchone() == (False, True)
            assert c.execute("select count(*) from radar_v_assuntos").fetchone()[0] == 1          # a visão nova foi criada
            assert c.execute("select status, aprovado_por::text from radar_conteudos").fetchone() == ("aprovado", EDITOR)
            assert c.execute("select frequencia_horas from radar_fontes where slug = 'pgfn-noticias'").fetchone()[0] == 3
            assert c.execute("select count(*) from radar_fontes").fetchone()[0] == 5
            assert c.execute("select array_agg(versao order by id) from radar_instalacoes").fetchone()[0] == ["v0.1.0", "v0.33.0"]
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
            assert c.execute("select na_fila, no_site from radar_v_painel").fetchone() == (0, 0)
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
    with como("anon") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("select id from radar_imagens")
    with como("authenticated", SEM_PERFIL) as c:
        assert c.execute("select count(*) from radar_imagens").fetchone()[0] == 0
    with como("authenticated", LEITOR) as c:
        assert c.execute("select id from radar_imagens").fetchall() == [(usada,)]


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
    assert set(conf) == {"obrigacoes", "feriados_extras", "fale_conosco", "assinatura", "relevancia", "rascunhos", "pauta",
                         "corretor_video", "lembretes"}   # v0.9.0: rascunhos; v0.21.0: pauta; v0.22.0: corretor_video; v0.29.0: lembretes
    assert len(conf["obrigacoes"]) == 28 and conf["assinatura"]["responsavel"] == "Cleiver Gonçalves"   # v0.30.0: + o 13º e as anuais
    # v0.30.0: o 13º e as anuais vêm no fim, com o mês do vencimento ("mes") e, quando as notícias usam outro nome, os "termos"
    assert [(o["nome"], o.get("mes"), "termos" in o) for o in conf["obrigacoes"][22:]] == [
        ("13º Salário (1ª parcela)", 11, True), ("13º Salário (2ª parcela)", 12, True),
        ("DEFIS - Declaração de Informações Socioeconômicas e Fiscais", 3, False), ("DASN-SIMEI - Declaração Anual do MEI", 5, True),
        ("ECD - Escrituração Contábil Digital", 6, False), ("ECF - Escrituração Contábil Fiscal", 7, False)]
    assert all("mes" not in o and "termos" not in o for o in conf["obrigacoes"][:22])
    assert (conf["assinatura"]["cnpj"], conf["assinatura"]["crc"]) == ("", "")   # v0.20.0: identificação legal vazia até o administrador preencher
    assert all(o["regra"] in ("quinto_dia_util", "dia", "ultimo_dia_util") for o in conf["obrigacoes"])
    with como("authenticated", LEITOR) as c:
        assert c.execute("select count(*) from radar_config").fetchone()[0] == 9          # a equipe lê (v0.22.0: + corretor_video; v0.29.0: + lembretes)
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
        assert _resumo("radar_sem_tx") == (30, 6, 8, 9, 1, 0)          # v0.29.0: + radar_lembretes e a chave "lembretes"
        with conectar("radar_sem_tx") as c:
            assert c.execute("select versao, antes, jsonb_array_length(depois) from radar_instalacoes").fetchone() == ("v0.33.0", [], 30)
            # v0.31.0 (revisão): na instalação nova as seis fontes iniciais entram ligadas, a rfb-normas também (o Passo 1 da instalação
            # já roda o diagnóstico dela pelo GitHub), e o LEIAME ("Fontes iniciais") diz isso
            assert c.execute("select count(*) filter (where ativo), bool_and(ativo) from radar_fontes").fetchone() == (6, True)
        leiame = (RAIZ / "LEIAME-radar.md").read_text(encoding="utf-8")
        linha = next(l for l in leiame.splitlines() if l.startswith("| Receita Federal — Atos normativos |"))
        assert "Na instalação nova ela entra **ligada**" in linha and "se o diagnóstico der HTTP 403, desligue-a" in linha
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
        assert _resumo("radar_parcial") == (30, 6, 8, 9, 2, 0)
        with conectar("radar_parcial") as c:
            assert c.execute("select frequencia_horas from radar_fontes where slug = 'pgfn-noticias'").fetchone()[0] == 3     # ajuste preservado
            # a atualização retira o acesso público que a v0.4 concedia (página pública extinta na v0.5.0)
            assert c.execute("""select (select count(*) from information_schema.role_table_grants where table_schema = 'public' and table_name like 'radar\\_%' and grantee = 'anon')
                                     + (select count(*) from information_schema.column_privileges where table_schema = 'public' and table_name like 'radar\\_%' and grantee = 'anon')
                                     + (select count(*) from pg_policies where schemaname = 'public' and 'anon' = any(roles))""").fetchone()[0] == 0
            assert c.execute("select jsonb_array_length(antes) from radar_instalacoes order by id").fetchall() == [(20,), (30,)]     # a v0.4 tinha 20; saem as 2 vazias da publicação antiga, entram radar_site_envios (v0.10.0), radar_itc_lidos (v0.12.0), radar_redes_envios (v0.13.0), radar_site_exclusoes (v0.17.0), radar_pessoas e radar_pauta_pecas (v0.21.0), radar_videos e radar_video_acessos (v0.22.0), radar_lembretes (v0.29.0), radar_vencimentos e radar_copias (v0.32.0)
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
        assert _resumo("radar_meio") == (30, 6, 8, 9, 1, 1)        # as fontes e categorias iniciais entram na execução que conclui
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
                               ("  https://x.gov.br/a?id=1  ", "https://x.gov.br/a?id=1"), ("https://x.gov.br/a?fbclid=q", "https://x.gov.br/a"),
                               # v0.31.0: o "#/…" de uma página montada no navegador é o endereço do ato (sistema Normas da Receita); o
                               # "/vs/…" da consulta sai, como no robô; a âncora comum continua saindo
                               ("https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/154087",
                                "https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/154087"),
                               ("https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/154087/vs/MTU0MDg3LDE1NDA1/Nw==",
                                "https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/154087"),
                               ("https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/154087/", "https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/154087"),
                               ("https://x.gov.br/app#!/ato/9", "https://x.gov.br/app#!/ato/9"), ("https://x.gov.br/a/#/b#c", "https://x.gov.br/a/#/b"),
                               ("https://x.gov.br/a#secao-2", "https://x.gov.br/a")]:
            assert c.execute("select radar_url_base(%s)", (entrada,)).fetchone()[0] == saida, entrada
        # dois atos do Normas não são mais o mesmo endereço (o texto colado de um ato não vai para a captura de outro)
        assert c.execute("select radar_url_base('https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/1') <> "
                         "radar_url_base('https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/2')").fetchone()[0] is True


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
    # v0.16.0: separada pela equipe, a IA não junta de novo (nem se avaliar outra vez dizendo que é igual)
    _avaliar([{"id": c, "nota": 7, "igual_a": a}])
    assert limpo.execute("select count(*) from radar_assunto_capturas where captura_id = %s", (c,)).fetchone()[0] == 0
    assert limpo.execute("select duplicata_de from radar_capturas where id = %s", (c,)).fetchone()[0] is None
    # com evidência registrada na captura, ela não sai do assunto (juntada de novo à mão, como a IA faria)
    limpo.execute("insert into radar_assunto_capturas (assunto_id, captura_id, juntada_pela_ia_em) values (%s, %s, now())", (assunto, c))
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


def test_atualizacao_da_v0_7_0_para_a_v0_8_0_preserva_os_dados_e_aplica_duas_vezes():
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
        # a evidência mostra a versão da instalação mais nova (como texto, "v0.7.0" viria depois de "v0.24.0")
        assert [l for l in r.stdout.splitlines() if l.startswith("instalacoes concluidas|")] == ["instalacoes concluidas|3|v0.33.0||"]
        with conectar("radar_up7") as c:
            assert c.execute("select array_agg(distinct versao order by versao) from radar_instalacoes").fetchone()[0] == ["v0.33.0", "v0.7.0"]
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
            assert c.execute("select array_agg(distinct versao order by versao) from radar_instalacoes").fetchone()[0] == ["v0.33.0", "v0.6.0"]
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


def test_campo_fonte_inclui_o_portal_depois_do_orgao_oficial_e_nunca_o_boletim_pago(limpo, request):
    """v0.18.0: o conteúdo novo nasce com a Fonte = órgãos oficiais e, depois, os portais de notícia; o boletim pago não entra."""
    carregar_fontes_novas(limpo, request)
    def assunto(*slugs):
        a = novo_assunto(limpo)
        for n, slug in enumerate(slugs):
            cap = nova_captura(limpo, slug=slug, url=f"https://exemplo.gov.br/fonte-{a}-{n}")
            limpo.execute("insert into radar_assunto_capturas values (%s, %s)", (a, cap))
        return limpo.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo) values (%s, 'flash', 'T', 'Texto.')
                                returning fonte_credito""", (a,)).fetchone()[0]
    assert assunto("itc-email", "portalcontabilsc-noticias", "rfb-normas") == "Receita Federal do Brasil, Portal Contábil SC"
    assert assunto("portalcontabilsc-noticias", "itc-email") == "Portal Contábil SC"
    assert assunto("itc-email") is None
    assert assunto("rfb-normas", "rfb-noticias") == "Receita Federal do Brasil"          # o mesmo órgão, uma vez só


def test_fontes_novas_entram_desligadas_e_o_sql_pode_rodar_de_novo(limpo):
    assert psql(FONTES_NOVAS).returncode == 0
    linhas = dict((s, (a, o)) for s, a, o in limpo.execute(
        "select slug, ativo, oficial from radar_fontes where slug in "
        "('dou-destaques','econet-blog','portalcontabilsc-noticias','dou-inlabs','itc-email')").fetchall())
    assert linhas == {"dou-destaques": (False, True), "econet-blog": (False, False),
                      "portalcontabilsc-noticias": (False, False), "dou-inlabs": (False, True), "itc-email": (True, False)}
    limpo.execute("update radar_fontes set ativo = true where slug = 'econet-blog'")
    assert psql(FONTES_NOVAS).returncode == 0                   # de novo: não desfaz o que você ligou
    assert limpo.execute("select ativo from radar_fontes where slug = 'econet-blog'").fetchone()[0] is True
    # v0.9.0: dos destaques do DOU só entram os atos fiscais e as leis (o resto era quase tudo nota 0 da IA)
    padrao = re.compile(limpo.execute("select config->>'padrao_url' from radar_fontes where slug = 'dou-destaques'").fetchone()[0])
    base = "https://www.in.gov.br/web/dou/-/"
    entra = ["instrucao-normativa-rfb-n-2.300-de-2-de-outubro-de-2026-736288471", "resolucao-cgsn-n-190-de-1-de-outubro-de-2026-736000001",
             "portaria-mf-n-1.500-de-1-de-outubro-de-2026-736000002", "portaria-conjunta-rfb/pgfn-n-3-de-2026-736000003",
             "lei-complementar-n-230-de-1-de-outubro-de-2026-736000004", "lei-n-15.526-de-29-de-setembro-de-2026-735384105",
             "solucao-de-consulta-cosit-n-120-de-2026-736000005", "decreto-n-12.700-de-1-de-outubro-de-2026-736000006"]
    fica = ["instrucao-normativa-anvisa-n-474-de-2-de-outubro-de-2026-736288471", "portaria-n-3.348-de-1-de-outubro-de-2026-736038075",
            "portaria-sda/mapa-n-1.696-de-1-de-outubro-de-2026-736023109", "portaria-fcp-n-447-de-30-de-setembro-de-2026-736030690",
            "portaria-mcid-n-1.298-de-25-de-setembro-de-2026-*-736038849", "edital-mfx-n-1-de-2026-736000007"]
    assert all(padrao.search(base + u) for u in entra) and not any(padrao.search(base + u) for u in fica)
    limpo.execute("delete from radar_fontes where slug in ('dou-destaques','econet-blog',"
                  "'portalcontabilsc-noticias','dou-inlabs','itc-email')")


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
        ruim = [{"titulo": "Data no formato errado", "data": "15/10/2026"}, {"titulo": "Data impossível", "data": "2026-02-31"},
                {"titulo": "Instrução Normativa RFB nº 2.300", "data": "2026-10-02"}]
        r = limpo.execute("select radar_receber_email('itc-email', %s::jsonb)", (json.dumps(ruim),)).fetchone()[0]
        assert r["novos"] == 3                                                       # data ruim vira "sem data"; nada é perdido
        assert limpo.execute("select count(*) from radar_capturas where titulo like 'Data%%' and data_publicacao is null").fetchone()[0] == 2
        assert limpo.execute("select hash_titulo from radar_capturas where titulo like 'Instrução%%'").fetchone()[0] == hash_titulo(
            "Instrução Normativa RFB nº 2.300")                                       # "nº" igual ao robô
        with pytest.raises(Exception, match="RADAR095"):
            limpo.execute("select radar_receber_email('rfb-noticias', '[]'::jsonb)")
    finally:
        limpo.execute("delete from radar_capturas where fonte_id in (select id from radar_fontes where slug = 'itc-email')")
        limpo.execute("delete from radar_fontes where slug in ('dou-destaques','econet-blog',"
                      "'portalcontabilsc-noticias','dou-inlabs','itc-email')")


# ------------------------------------------------ v0.8.0: nota alta da IA tira a captura de "baixa"
def test_nota_da_ia_leva_baixa_para_media_e_rebaixa_alta_com_nota_baixa(limpo):
    cap = _cap(limpo, "Prefeitura de Palhoça divulga calendário do alvará")[0]
    assert limpo.execute("select relevancia from radar_capturas where id = %s", (cap,)).fetchone()[0] == "baixa"
    limpo.execute("update radar_capturas set ia_nota = 7 where id = %s", (cap,))
    assert limpo.execute("select relevancia from radar_capturas where id = %s", (cap,)).fetchone()[0] == "baixa"   # 7 < 8
    limpo.execute("select radar_gravar_avaliacao_ia(%s::jsonb)", (json.dumps([{"id": cap, "nota": 9, "motivo": "prazo municipal"}]),))
    nivel, motivos = limpo.execute("select relevancia, relevancia_motivos from radar_capturas where id = %s", (cap,)).fetchone()
    assert nivel == "media" and {"termo": "nota da IA 9", "pontos": 0} in motivos
    mista = _cap(limpo, "Leilão de bens: prazo do ICMS")[0]                     # termo negativo + positivos: continua baixa
    limpo.execute("update radar_capturas set ia_nota = 10 where id = %s", (mista,))
    assert limpo.execute("select relevancia from radar_capturas where id = %s", (mista,)).fetchone()[0] == "baixa"
    negativa = _cap(limpo, "Apreensão de cigarros na fronteira")[0]          # rebaixada por termos negativos: fica baixa
    limpo.execute("update radar_capturas set ia_nota = 10 where id = %s", (negativa,))
    assert limpo.execute("select relevancia from radar_capturas where id = %s", (negativa,)).fetchone()[0] == "baixa"
    alta = _cap(limpo, "Prazo do Simples Nacional é prorrogado")[0]
    limpo.execute("update radar_capturas set ia_nota = 4 where id = %s", (alta,))
    assert limpo.execute("select relevancia from radar_capturas where id = %s", (alta,)).fetchone()[0] == "alta"  # 4 > 3: fica
    limpo.execute("update radar_capturas set ia_nota = 0 where id = %s", (alta,))                  # v0.9.0: nota até 3 rebaixa
    nivel, motivos = limpo.execute("select relevancia, relevancia_motivos from radar_capturas where id = %s", (alta,)).fetchone()
    assert nivel == "media" and {"termo": "nota da IA 0 (rebaixada)", "pontos": 0} in motivos
    limpo.execute("update radar_capturas set ia_nota = null where id = %s", (alta,))               # sem nota: só as palavras
    assert limpo.execute("select relevancia from radar_capturas where id = %s", (alta,)).fetchone()[0] == "alta"
    limpo.execute("update radar_capturas set ia_nota = 2 where id = %s", (alta,))
    antes = limpo.execute("select valor from radar_config where chave = 'relevancia'").fetchone()[0]
    try:                                                                   # regras salvas de novo: a promoção continua valendo
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(dict(antes, quantidade=12)),))
        assert limpo.execute("select relevancia from radar_capturas where id = %s", (cap,)).fetchone()[0] == "media"
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(dict(antes, nota_promove=11)),))
        assert limpo.execute("select relevancia from radar_capturas where id = %s", (cap,)).fetchone()[0] == "baixa"   # 11 desliga
        assert limpo.execute("select relevancia from radar_capturas where id = %s", (alta,)).fetchone()[0] == "media"
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(dict(antes, nota_rebaixa=-1)),))
        assert limpo.execute("select relevancia from radar_capturas where id = %s", (alta,)).fetchone()[0] == "alta"   # -1 desliga
    finally:
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(antes),))


# ------------------------------------------------ v0.9.0: a fila não acumula
def test_robo_tira_da_fila_o_que_ficou_velho_e_sem_importancia(limpo):
    velha_baixa = _cap(limpo, "Nota sobre o atendimento na próxima semana")[0]
    velha_nota1 = _cap(limpo, "Receita prorroga prazo de adesão ao Simples Nacional")[0]
    velha_boa = _cap(limpo, "Comitê Gestor do IBS publica orientação sobre a CBS")[0]
    nova_baixa = _cap(limpo, "Receita Federal agora está no Instagram")[0]
    repetida = _cap(limpo, "Nota sobre o atendimento da próxima semana")[0]
    limpo.execute("update radar_capturas set duplicata_de = %s where id = %s", (velha_baixa, repetida))
    origem_baixa = _cap(limpo, "Portal comenta a semana")[0]                     # baixa, mas a repetição dela é importante
    rep_alta = _cap(limpo, "Receita prorroga prazo do Simples Nacional para 2027")[0]
    limpo.execute("update radar_capturas set duplicata_de = %s where id = %s", (origem_baixa, rep_alta))
    limpo.execute("update radar_capturas set capturado_em = now() - interval '11 days' where id in (%s, %s)", (origem_baixa, rep_alta))
    limpo.execute("update radar_capturas set ia_nota = 1 where id = %s", (velha_nota1,))
    limpo.execute("update radar_capturas set ia_nota = 5 where id = %s", (velha_boa,))
    limpo.execute("update radar_capturas set capturado_em = now() - interval '11 days' where id in (%s, %s, %s, %s)",
                  (velha_baixa, velha_nota1, velha_boa, repetida))
    for papel, uid in (("authenticated", ADMIN), ("authenticated", EDITOR), ("anon", None)):
        with como(papel, uid) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select radar_arquivar_fila()")
    with como("service_role") as c:
        assert c.execute("select radar_arquivar_fila()").fetchone()[0] == 3          # a repetição vai junto com a origem
        assert c.execute("select radar_arquivar_fila()").fetchone()[0] == 0
    na_fila = {r[0] for r in limpo.execute("select id from radar_v_fila").fetchall()}
    assert velha_boa in na_fila and nova_baixa in na_fila and not {velha_baixa, velha_nota1, repetida} & na_fila
    assert origem_baixa in na_fila                                                # a repetição relevante segura o grupo na fila
    assert {r[0] for r in limpo.execute("""select distinct a.status from radar_assuntos a join radar_assunto_capturas ac
                                           on ac.assunto_id = a.id where ac.captura_id in (%s, %s, %s)""",
                                        (velha_baixa, velha_nota1, repetida)).fetchall()} == {"ignorado"}
    antes = limpo.execute("select valor from radar_config where chave = 'relevancia'").fetchone()[0]
    try:                                                                  # 0 desliga; prazo e nota configuráveis
        limpo.execute("update radar_capturas set capturado_em = now() - interval '30 days' where id = %s", (nova_baixa,))
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(dict(antes, arquivar_dias=0)),))
        with como("service_role") as c:
            assert c.execute("select radar_arquivar_fila()").fetchone()[0] == 0
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'",
                      (json.dumps(dict(antes, arquivar_dias=40, arquivar_nota=5)),))
        with como("service_role") as c:
            assert c.execute("select radar_arquivar_fila()").fetchone()[0] == 0          # 30 dias < 40
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'",
                      (json.dumps(dict(antes, arquivar_dias=5, arquivar_nota=5)),))
        with como("service_role") as c:
            assert c.execute("select radar_arquivar_fila()").fetchone()[0] == 2          # a baixa e a de nota 5
    finally:
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(antes),))


# ------------------------------------------------ v0.10.0: autorização de publicação no site
def test_so_o_administrador_autoriza_a_publicacao_e_o_robo_so_marca_o_andamento(limpo):
    a, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    lido = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (c1,)).fetchone()[0]
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR110"):
        c.execute("select radar_autorizar_site(%s, 'Tributário', %s)", (c1, lido))
    with como("authenticated", ADMIN) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR114"):                 # texto mudou depois de aberto
            c.execute("select radar_autorizar_site(%s, 'Tributário', now())", (c1,))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR115"):
            c.execute("select radar_autorizar_site(%s, ' ', %s)", (c1, lido))
        envio = c.execute("select radar_autorizar_site(%s, 'Tributário', %s)", (c1, lido)).fetchone()[0]
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR116"):                 # uma autorização em aberto por vez
            c.execute("select radar_autorizar_site(%s, 'Tributário', %s)", (c1, lido))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):                            # a tela não grava direto
            c.execute("update radar_site_envios set situacao = 'publicado' where id = %s", (envio,))
    linha = limpo.execute("select situacao, categoria, autorizado_por::text from radar_site_envios where id = %s", (envio,)).fetchone()
    assert linha == ("autorizado", "Tributário", ADMIN)
    with como("authenticated", LEITOR) as c:                                                  # a equipe vê o andamento
        assert c.execute("select count(*) from radar_site_envios").fetchone()[0] == 1
    with como("service_role") as c:
        assert c.execute("update radar_site_envios set situacao = 'enviando' where id = %s returning id", (envio,)).fetchone()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into radar_site_envios (conteudo_id, categoria, conteudo_lido_em) values (%s, 'x', now())", (c1,))
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR118"):
        c.execute("select radar_cancelar_site(%s)", (envio,))                                 # o robô já começou: não cancela


def test_autorizacao_exige_assunto_pronto_e_cai_se_o_conteudo_mudar(limpo):
    c1 = novo_conteudo(limpo, novo_assunto(limpo, "em_verificacao"))
    aprovar(c1)
    lido = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (c1,)).fetchone()[0]
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR031"):
        c.execute("select radar_autorizar_site(%s, 'Tributário', %s)", (c1, lido))
    rascunho = novo_conteudo(limpo, cenario_publicavel(limpo)[0], "rascunho")
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR112"):
        c.execute("select radar_autorizar_site(%s, 'Tributário', now())", (rascunho,))
    a, c2 = cenario_publicavel(limpo, slug_fonte="rfb-noticias")
    aprovar(c2)
    lido = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (c2,)).fetchone()[0]
    with como("authenticated", ADMIN) as c:
        envio = c.execute("select radar_autorizar_site(%s, 'Simples Nacional', %s)", (c2, lido)).fetchone()[0]
    with como("authenticated", EDITOR) as c:                                                  # texto mexido depois de autorizado
        c.execute("update radar_conteudos set titulo = 'Outro título' where id = %s", (c2,))
    situacao, erro = limpo.execute("select situacao, erro from radar_site_envios where id = %s", (envio,)).fetchone()
    assert situacao == "cancelado" and "o conteúdo mudou" in erro
    aprovar(c2)
    lido = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (c2,)).fetchone()[0]
    with como("authenticated", ADMIN) as c:                                                   # autoriza de novo e cancela
        envio = c.execute("select radar_autorizar_site(%s, 'Simples Nacional', %s)", (c2, lido)).fetchone()[0]
        assert c.execute("select radar_cancelar_site(%s)", (envio,)).fetchone()[0] is True
    assert limpo.execute("select situacao, cancelado_por::text from radar_site_envios where id = %s", (envio,)).fetchone() == ("cancelado", ADMIN)


# ------------------------------------------------ v0.11.0: notícia com mais de 5 dias é baixa
def test_noticia_com_mais_de_cinco_dias_desce_para_baixa_e_nao_e_arquivada_por_isso(limpo):
    antes = limpo.execute("select valor from radar_config where chave = 'relevancia'").fetchone()[0]
    titulo = "Receita prorroga prazo do Simples Nacional para 2027"
    try:
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(dict(antes, dias_baixa=5)),))
        nova = _cap(limpo, titulo)
        assert nova[1] == "alta"
        velha = _cap(limpo, titulo + " (antiga)")[0]
        limpo.execute("update radar_capturas set data_publicacao = (now() at time zone 'America/Sao_Paulo')::date - 6 where id = %s", (velha,))
        sem_data = _cap(limpo, titulo + " (sem data)")[0]
        limpo.execute("update radar_capturas set capturado_em = now() - interval '11 days' where id = %s", (sem_data,))
        cinco = _cap(limpo, titulo + " (cinco dias)")[0]
        limpo.execute("update radar_capturas set data_publicacao = (now() at time zone 'America/Sao_Paulo')::date - 5 where id = %s", (cinco,))
        with como("service_role") as c:
            assert c.execute("select radar_arquivar_fila()").fetchone()[0] == 0          # reavalia, mas baixa pela idade não sai
        rel = dict(limpo.execute("select id, relevancia from radar_capturas").fetchall())
        assert rel == {nova[0]: "alta", velha: "baixa", sem_data: "baixa", cinco: "alta"}  # 5 dias ainda vale; 6 já é velha
        motivo = limpo.execute("select relevancia_motivos from radar_capturas where id = %s", (velha,)).fetchone()[0]
        assert {"termo": "notícia com mais de 5 dias", "pontos": 0, "idade": True, "antes": "alta"} in motivo
        assert velha not in {r[0] for r in limpo.execute("select id from radar_v_em_alta").fetchall()}
        assert {velha, sem_data} <= {r[0] for r in limpo.execute("select id from radar_v_fila").fetchall()}   # continuam na triagem
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(dict(antes, dias_baixa=0)),))
        assert limpo.execute("select relevancia from radar_capturas where id = %s", (velha,)).fetchone()[0] == "alta"   # 0 desliga
    finally:
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(antes),))


def test_texto_para_analise_nao_se_aprova_nem_vai_ao_site_e_a_idade_nao_passa_ao_assunto(limpo):
    a, _ = cenario_publicavel(limpo)
    c1 = limpo.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo, gerado_por, modelo_ia, status, avisos_ia, fora_do_site)
                          values (%s, 'flash', 'Para análise', 'Texto para análise.', 'ia', 'm', 'em_revisao',
                                  '["TEXTO PARA ANÁLISE, escrito a partir de fonte NÃO oficial (ITC)."]', true) returning id""", (a,)).fetchone()[0]
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR023"):
        c.execute("update radar_conteudos set status = 'aprovado' where id = %s", (c1,))
    # a idade rebaixa a captura na triagem, mas o assunto aberto dela guarda a relevância do conteúdo
    antes = limpo.execute("select valor from radar_config where chave = 'relevancia'").fetchone()[0]
    try:
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(dict(antes, dias_baixa=5)),))
        cap = _cap(limpo, "Receita prorroga prazo do Simples Nacional para 2027")[0]
        limpo.execute("update radar_capturas set data_publicacao = current_date - 9 where id = %s", (cap,))   # a data mudou: recalcula
        assert limpo.execute("select relevancia from radar_capturas where id = %s", (cap,)).fetchone()[0] == "baixa"
        with como("authenticated", EDITOR) as c:
            novo = c.execute("select radar_abrir_assunto(%s)", (cap,)).fetchone()[0]
        assert limpo.execute("select relevancia from radar_assuntos where id = %s", (novo,)).fetchone()[0] == "alta"
        # já é assunto: uma nova versão do texto não a rebaixa
        limpo.execute("update radar_capturas set data_publicacao = current_date where id = %s", (cap,))
        limpo.execute("update radar_capturas set data_publicacao = current_date - 20, texto = 'novo texto' where id = %s", (cap,))
        assert limpo.execute("select relevancia from radar_capturas where id = %s", (cap,)).fetchone()[0] == "alta"
        # a coleta só rebaixa as que passaram da idade; a que ficou velha demais (3x o prazo da fila) sai
        velha = _cap(limpo, "Receita prorroga prazo do Simples Nacional — outra")[0]
        limpo.execute("update radar_capturas set data_publicacao = current_date - 40, capturado_em = now() - interval '31 days' where id = %s", (velha,))
        with como("service_role") as c:
            assert c.execute("select radar_arquivar_fila()").fetchone()[0] == 1
        assert velha not in {r[0] for r in limpo.execute("select id from radar_v_fila").fetchall()}
    finally:
        limpo.execute("update radar_config set valor = %s where chave = 'relevancia'", (json.dumps(antes),))


# ------------------------------------------------ v0.11.1: boletim não oficial nunca esconde a captura oficial
def _boletim(db):
    return db.execute("""insert into radar_fontes (slug, nome, orgao, oficial, tipo_coletor, url)
                         values ('teste-boletim', 'Boletim', 'Consultoria', false, 'rss', 'https://boletim.exemplo/') returning id""").fetchone()[0]


def _cap_em(db, slug, url, h, dup=None):
    return db.execute("""insert into radar_capturas (fonte_id, url, titulo, hash_titulo, duplicata_de)
                         select id, %s, 'Prazo do Simples prorrogado', %s, %s from radar_fontes where slug = %s returning id""",
                      (url, h, dup, slug)).fetchone()[0]


def test_captura_oficial_nunca_fica_atras_de_boletim_nao_oficial(limpo):
    _boletim(limpo)
    dup = lambda i: limpo.execute("select duplicata_de from radar_capturas where id = %s", (i,)).fetchone()[0]
    # boletim chegou antes; o robô (versão antiga) grava a oficial como repetição dele: o banco inverte
    b1 = _cap_em(limpo, "teste-boletim", "https://boletim.exemplo/?radar=1", "h1")
    b1r = _cap_em(limpo, "teste-boletim", "https://boletim.exemplo/?radar=1b", "h1x", dup=b1)
    o1 = _cap_em(limpo, "rfb-noticias", "https://www.gov.br/receitafederal/o1", "h1", dup=b1)
    assert (dup(o1), dup(b1), dup(b1r)) == (None, o1, o1)
    # oficial grava sem repetição, mas o boletim com o mesmo título estava na fila: vai para trás dela
    b2 = _cap_em(limpo, "teste-boletim", "https://boletim.exemplo/?radar=2", "h2")
    o2 = _cap_em(limpo, "rfb-noticias", "https://www.gov.br/receitafederal/o2", "h2")
    assert (dup(o2), dup(b2)) == (None, o2)
    # boletim que chega depois da oficial entra como repetição dela
    o3 = _cap_em(limpo, "rfb-noticias", "https://www.gov.br/receitafederal/o3", "h3")
    b3 = _cap_em(limpo, "teste-boletim", "https://boletim.exemplo/?radar=3", "h3")
    assert (dup(o3), dup(b3)) == (None, o3)
    # boletim que já virou assunto não sai do lugar; a oficial fica com cartão próprio
    b4 = _cap_em(limpo, "teste-boletim", "https://boletim.exemplo/?radar=4", "h4")
    with como("authenticated", EDITOR) as c:
        c.execute("select radar_abrir_assunto(%s)", (b4,))
    o4 = _cap_em(limpo, "rfb-noticias", "https://www.gov.br/receitafederal/o4", "h4")
    assert (dup(o4), dup(b4)) == (None, None)
    # ...mas se o robô ou a IA dizem que a oficial é o mesmo fato do boletim que já é assunto, o vínculo fica (aviso na triagem)
    o4b = _cap_em(limpo, "rfb-normas", "https://www.gov.br/receitafederal/o4b", "h4b", dup=b4)
    assert dup(o4b) == b4
    # oficial repetição de oficial continua valendo
    o5 = _cap_em(limpo, "rfb-normas", "https://www.gov.br/receitafederal/o5", "h5", dup=o3)
    assert dup(o5) == o3
    principais = {r[0] for r in limpo.execute("select id from radar_v_fila where principal").fetchall()}
    assert {o1, o2, o3, o4, o4b} <= principais and not {b1, b2, b3} & principais     # o4b: a origem está em assunto


def test_ia_que_junta_oficial_a_boletim_poe_o_boletim_atras_da_oficial(limpo):
    _boletim(limpo)
    b = _cap_em(limpo, "teste-boletim", "https://boletim.exemplo/?radar=9", "h9")
    o = _cap_em(limpo, "rfb-noticias", "https://www.gov.br/receitafederal/o9", "outro-titulo")
    with como("service_role") as c:
        r = c.execute("select radar_gravar_avaliacao_ia(%s::jsonb)", (json.dumps([{"id": o, "nota": 8, "igual_a": b}]),)).fetchone()[0]
    assert r["gravadas"] == 1 and r["repetidas"] == 0
    assert limpo.execute("select id, duplicata_de from radar_capturas order by id").fetchall() == [(b, o), (o, None)]


def test_consumo_de_ia_do_mes_conta_o_mes_de_brasilia(limpo):
    limpo.execute("insert into radar_ia_uso (acao, modelo, tokens_entrada) values ('gerar', 'm', 100), ('gerar', 'm', 7)")
    limpo.execute("""update radar_ia_uso set em = (date_trunc('month', now() at time zone 'America/Sao_Paulo')
                                                   + case when tokens_entrada = 100 then interval '30 minutes' else interval '-2 hours' end)
                                                  at time zone 'America/Sao_Paulo'""")     # o registro sempre grava "agora"
    # 22h do último dia do mês passado em Brasília já é dia 1º em UTC: não entra no mês
    with como("authenticated", EDITOR) as c:
        assert c.execute("select tokens from radar_v_ia_mes").fetchone()[0] == 100


def test_oficial_igual_a_boletim_que_ja_e_assunto_entra_no_assunto_e_separacao_da_equipe_vale(limpo):
    _boletim(limpo)
    b = _cap_em(limpo, "teste-boletim", "https://boletim.exemplo/?radar=7", "h7")
    with como("authenticated", EDITOR) as c:
        a = c.execute("select radar_abrir_assunto(%s)", (b,)).fetchone()[0]
    o = _cap_em(limpo, "rfb-noticias", "https://www.gov.br/receitafederal/o7", "outro-7")
    with como("service_role") as c:
        r = c.execute("select radar_gravar_avaliacao_ia(%s::jsonb)", (json.dumps([{"id": o, "nota": 8, "igual_a": b}]),)).fetchone()[0]
    assert (r["repetidas"], r["juntadas_a_assunto"]) == (1, 1)            # o texto oficial chega ao assunto aberto pelo boletim
    assert limpo.execute("select count(*) from radar_assunto_capturas where assunto_id = %s", (a,)).fetchone()[0] == 2
    # a equipe diz "não é o mesmo fato" para um boletim agrupado atrás de uma oficial: outra oficial igual não o reagrupa
    b2 = _cap_em(limpo, "teste-boletim", "https://boletim.exemplo/?radar=8", "h8")
    o8 = _cap_em(limpo, "rfb-noticias", "https://www.gov.br/receitafederal/o8", "h8")
    assert limpo.execute("select duplicata_de from radar_capturas where id = %s", (b2,)).fetchone()[0] == o8
    with como("authenticated", EDITOR) as c:
        a8 = c.execute("select radar_abrir_assunto(%s)", (o8,)).fetchone()[0]
        c.execute("select radar_separar_captura(%s, %s)", (a8, b2))
    _cap_em(limpo, "rfb-normas", "https://www.gov.br/receitafederal/o8b", "h8")
    assert limpo.execute("select duplicata_de from radar_capturas where id = %s", (b2,)).fetchone()[0] is None


# ------------------------------------------------ v0.12.0: boletim da ITC lido pela função radar-itc
def test_funcoes_do_boletim_so_para_o_robo_e_lista_de_lidos_so_para_o_admin(limpo):
    limpo.execute("truncate radar_itc_lidos")
    with como("service_role") as c:
        c.execute("select radar_itc_marcar_lido('m1', %s, now(), 3, 2)", ("x" * 300,))
        c.execute("select radar_itc_marcar_lido('m1', 'de novo', now(), 9, 9)")          # o mesmo e-mail não duplica nem muda
        assert c.execute("select radar_itc_ja_lidos(array['m1','m2'])").fetchone()[0] == ["m1"]
        assert c.execute("select radar_itc_conferir_agenda(%s)", ("a" * 64,)).fetchone()[0] is False   # sem Vault: nunca confere
    assert limpo.execute("select materias, novas, length(assunto) from radar_itc_lidos").fetchall() == [(3, 2, 200)]
    for papel, uid in [("authenticated", EDITOR), ("authenticated", ADMIN), ("anon", None)]:
        with como(papel, uid) as c:
            for sql in ["select radar_itc_ja_lidos(array['m1'])", "select radar_itc_marcar_lido('m3', 'a', now(), 1, 1)",
                        "select radar_itc_conferir_agenda('x')", "select radar_receber_email('itc-email', '[]')"]:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    c.execute(sql)
    with como("authenticated", ADMIN) as c:
        assert c.execute("select count(*) from radar_itc_lidos").fetchone()[0] == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into radar_itc_lidos (message_id) values ('m4')")
    with como("authenticated", EDITOR) as c:
        assert c.execute("select count(*) from radar_itc_lidos").fetchone()[0] == 0          # editor não vê
    limpo.execute("truncate radar_itc_lidos")


def test_publicar_mesmo_assim_so_o_administrador_com_motivo_e_o_texto_para_analise_continua_barrado(limpo):
    a = limpo.execute("insert into radar_assuntos (titulo) values ('Sem fundamentação') returning id").fetchone()[0]
    with como("service_role") as c:
        assert c.execute("select radar_pendencia_assunto(%s)", (a,)).fetchone()[0].startswith("RADAR031")
    with como("authenticated", EDITOR) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR120"):
            c.execute("select radar_liberar_sem_fundamentacao(%s, 'motivo qualquer longo')", (a,))
        # a equipe edita o assunto, mas não consegue se liberar pela tabela
        c.execute("update radar_assuntos set liberado_sem_base_em = now(), liberado_sem_base_motivo = 'tentativa direta' where id = %s", (a,))
    assert limpo.execute("select liberado_sem_base_em from radar_assuntos where id = %s", (a,)).fetchone()[0] is None
    with como("authenticated", ADMIN) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR121"):
            c.execute("select radar_liberar_sem_fundamentacao(%s, 'curto')", (a,))
        c.execute("select radar_liberar_sem_fundamentacao(%s, 'Notícia da ITC confirmada por telefone com a Receita')", (a,))
    por, motivo = limpo.execute("select liberado_sem_base_por, liberado_sem_base_motivo from radar_assuntos where id = %s", (a,)).fetchone()
    assert str(por) == ADMIN and motivo.startswith("Notícia da ITC")
    with como("service_role") as c:
        assert c.execute("select radar_pendencia_assunto(%s)", (a,)).fetchone()[0] is None
    # aprovado e liberado: a autorização do site passa; texto para análise continua barrado
    c1 = limpo.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo, gerado_por, status)
                          values (%s, 'flash', 'Liberado', 'Texto da equipe.', 'humano', 'em_revisao') returning id""", (a,)).fetchone()[0]
    aprovar(c1, ADMIN)
    lido = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (c1,)).fetchone()[0]
    with como("authenticated", ADMIN) as c:
        assert c.execute("select radar_autorizar_site(%s, 'Notícias', %s)", (c1, lido)).fetchone()[0] > 0
        c.execute("select radar_liberar_sem_fundamentacao(%s, null)", (a,))                # desfazer
    with como("service_role") as c:
        assert c.execute("select radar_pendencia_assunto(%s)", (a,)).fetchone()[0].startswith("RADAR031")


def test_texto_para_analise_vira_texto_para_publicar_so_com_a_publicacao_liberada(limpo):
    a = limpo.execute("insert into radar_assuntos (titulo) values ('Só do boletim') returning id").fetchone()[0]
    c = limpo.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo, gerado_por, modelo_ia, status, avisos_ia, fora_do_site)
                         values (%s, 'flash', 'Boletim', 'Texto da IA [VERIFICAR: prazo].', 'ia', 'm', 'rascunho',
                                 '["TEXTO PARA ANÁLISE, escrito a partir de fonte NÃO oficial (ITC).", "O texto tem 1 ponto(s) marcados com [VERIFICAR]"]', true)
                         returning id""", (a,)).fetchone()[0]
    with como("authenticated", EDITOR) as k, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR123"):
        k.execute("select radar_converter_analise(%s)", (c,))
    with como("authenticated", ADMIN) as k:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR125"):          # sem liberar, não converte
            k.execute("select radar_converter_analise(%s)", (c,))
        k.execute("select radar_liberar_sem_fundamentacao(%s, 'Autorizado pelo responsável técnico')", (a,))
        novo = k.execute("select radar_converter_analise(%s)", (c,)).fetchone()[0]
    st, fora, avisos, corpo = limpo.execute("select status, fora_do_site, avisos_ia, corpo from radar_conteudos where id = %s", (novo,)).fetchone()
    assert (st, fora, corpo) == ("rascunho", False, "Texto da IA [VERIFICAR: prazo].")
    assert avisos[0].startswith("Feito a partir do texto para análise") and "[VERIFICAR]" in avisos[1] and len(avisos) == 2
    limpo.execute("update radar_conteudos set status = 'em_revisao' where id = %s", (novo,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR139"):                      # v0.14.3: com a marca, não aprova
        aprovar(novo, ADMIN)
    limpo.execute("update radar_conteudos set corpo = 'Texto da IA, prazo conferido.' where id = %s", (novo,))
    assert aprovar(novo, ADMIN) is not None                                                 # resolvida a marca, aprova normalmente
    lido = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (novo,)).fetchone()[0]
    with como("authenticated", ADMIN) as k:
        assert k.execute("select radar_autorizar_site(%s, 'Notícias', %s)", (novo, lido)).fetchone()[0] > 0
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR124"):          # a cópia não é texto para análise
            k.execute("select radar_converter_analise(%s)", (novo,))
    assert limpo.execute("select fora_do_site from radar_conteudos where id = %s", (c,)).fetchone()[0] is True   # original fica


# ------------------------------------------------ v0.13.0: Instagram e Facebook
IMG = "data:image/jpeg;base64," + "A" * 200
LEGENDA = "Prazo do Simples prorrogado. Leia no site da Artecon."


def _lido(db, c1):
    return db.execute("select atualizado_em from radar_conteudos where id = %s", (c1,)).fetchone()[0]


def test_redes_so_o_administrador_autoriza_depois_do_site_e_uma_vez_por_canal(limpo):
    a, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    lido = _lido(limpo, c1)
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR130"):
        c.execute("select radar_autorizar_rede(%s, 'instagram', %s, %s, %s)", (c1, LEGENDA, IMG, lido))
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR133"):
        c.execute("select radar_autorizar_rede(%s, 'instagram', %s, %s, %s)", (c1, LEGENDA, IMG, lido))   # ainda não está no site
    registrar_site(c1)
    lido = _lido(limpo, c1)
    with como("authenticated", ADMIN) as c:
        for args, erro in [(("tiktok", LEGENDA, IMG, lido), "RADAR131"), (("instagram", "curta", IMG, lido), "RADAR134"),
                           (("instagram", LEGENDA, "data:image/png;base64,AAAA", lido), "RADAR135"),
                           (("instagram", LEGENDA, IMG, datetime.now(timezone.utc)), "RADAR114")]:
            with pytest.raises(psycopg.errors.RaiseException, match=erro):
                c.execute("select radar_autorizar_rede(%s, %s, %s, %s, %s)", (c1, *args))
        envio = c.execute("select radar_autorizar_rede(%s, 'instagram', %s, %s, %s)", (c1, LEGENDA, IMG, lido)).fetchone()[0]
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR136"):              # uma vez por canal
            c.execute("select radar_autorizar_rede(%s, 'instagram', %s, %s, %s)", (c1, LEGENDA, IMG, lido))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):                           # a tela não grava direto
            c.execute("update radar_redes_envios set situacao = 'publicado' where id = %s", (envio,))
        assert c.execute("select radar_dispensar_rede(%s, 'facebook')", (c1,)).fetchone()[0]
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR136"):
            c.execute("select radar_autorizar_rede(%s, 'facebook', %s, %s, %s)", (c1, LEGENDA, IMG, lido))
    with como("authenticated", LEITOR) as c:                                               # a equipe vê o andamento
        assert c.execute("select count(*) from radar_redes_envios").fetchone()[0] == 2
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("select radar_rede_iniciar(%s)", (envio,))                               # só a função radar-redes envia


def test_redes_a_funcao_envia_uma_vez_e_o_conteudo_alterado_derruba_a_autorizacao(limpo):
    a, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    registrar_site(c1)
    with como("authenticated", ADMIN) as c:
        envio = c.execute("select radar_autorizar_rede(%s, 'instagram', %s, %s, %s)", (c1, LEGENDA, IMG, _lido(limpo, c1))).fetchone()[0]
    with como("service_role") as c:
        r = c.execute("select radar_rede_iniciar(%s)", (envio,)).fetchone()[0]
        assert (r["canal"], r["legenda"], r["imagem"]) == ("instagram", LEGENDA, IMG)
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR138"):              # já está saindo: não envia de novo
            c.execute("select radar_rede_iniciar(%s)", (envio,))
        assert c.execute("select radar_rede_concluir(%s, false, null, null, 'https://x.supabase.co/storage/v1/object/public/radar-redes/1.jpg', 'Meta recusou')", (envio,)).fetchone()[0]
    sit, erro, img, img_url = limpo.execute("select situacao, erro, imagem, imagem_url from radar_redes_envios where id = %s", (envio,)).fetchone()
    assert (sit, erro, img) == ("erro", "Meta recusou", None) and img_url.endswith("/1.jpg")   # a imagem fica só no armazenamento
    with como("service_role") as c:                                                         # nova tentativa usa o link já enviado
        r = c.execute("select radar_rede_iniciar(%s)", (envio,)).fetchone()[0]
        assert r["imagem"] is None and r["imagem_url"].endswith("/1.jpg")
        assert c.execute("select radar_rede_concluir(%s, true, '1789', 'https://www.instagram.com/p/abc/', null, null)", (envio,)).fetchone()[0]
    assert limpo.execute("select situacao, post_id, url from radar_redes_envios where id = %s", (envio,)).fetchone() == \
        ("publicado", "1789", "https://www.instagram.com/p/abc/")
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR137"):
        c.execute("select radar_cancelar_rede(%s)", (envio,))                               # já saiu: não cancela
    # Facebook autorizado e o texto muda antes de sair: a autorização cai sozinha
    with como("authenticated", ADMIN) as c:
        fb = c.execute("select radar_autorizar_rede(%s, 'facebook', %s, %s, %s)", (c1, LEGENDA, IMG, _lido(limpo, c1))).fetchone()[0]
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_conteudos set titulo = 'Outro título' where id = %s", (c1,))
    sit, erro = limpo.execute("select situacao, erro from radar_redes_envios where id = %s", (fb,)).fetchone()
    assert sit == "cancelado" and "o conteúdo mudou" in erro
    with como("service_role") as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR138"):
        c.execute("select radar_rede_iniciar(%s)", (fb,))


def test_redes_cancelar_e_dispensado_desfeito(limpo):
    a, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    registrar_site(c1)
    with como("authenticated", ADMIN) as c:
        d = c.execute("select radar_dispensar_rede(%s, 'instagram')", (c1,)).fetchone()[0]
        assert c.execute("select radar_cancelar_rede(%s)", (d,)).fetchone()[0] is True     # desfaz o "não publicar"
        envio = c.execute("select radar_autorizar_rede(%s, 'instagram', %s, %s, %s)", (c1, LEGENDA, IMG, _lido(limpo, c1))).fetchone()[0]
    with como("service_role") as c:
        c.execute("select radar_rede_iniciar(%s)", (envio,))
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR137"):
        c.execute("select radar_cancelar_rede(%s)", (envio,))                               # saindo agora: não cancela
    limpo.execute("update radar_redes_envios set enviado_em = now() - interval '11 minutes' where id = %s", (envio,))
    with como("authenticated", ADMIN) as c:                                                 # parada há mais de 10 min: cancela
        assert c.execute("select radar_cancelar_rede(%s)", (envio,)).fetchone()[0] is True
    assert limpo.execute("select situacao, imagem from radar_redes_envios where id = %s", (envio,)).fetchone() == ("cancelado", None)
    # varredura geral (v0.22.0): cancelada no meio do envio, pode ter saído (a Meta publicou e o registro não entrou). Autorizar de
    # novo o mesmo canal pede a caixa "Conferi no Instagram: não saiu" (RADAR166), na rede e no "Publicar em todos"
    assert "Cancelada no meio do envio" in limpo.execute("select erro from radar_redes_envios where id = %s", (envio,)).fetchone()[0]
    with como("authenticated", ADMIN) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR166: a publicação deste conteúdo no Instagram foi cancelada"):
            c.execute("select radar_autorizar_rede(%s, 'instagram', %s, %s, %s)", (c1, LEGENDA, IMG, _lido(limpo, c1)))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR166"):
            c.execute("select radar_autorizar_rede(%s, 'instagram', %s, %s, %s, false)", (c1, LEGENDA, IMG, _lido(limpo, c1)))
    limpo.execute("delete from radar_divulgacoes where conteudo_id = %s", (c1,))
    with como("authenticated", ADMIN) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR166"):
            c.execute("select radar_autorizar_todos(%s, 'Tributário', %s, %s, %s, null)", (c1, _lido(limpo, c1), IMG, LEGENDA))
        r = c.execute("select radar_autorizar_todos(%s, 'Tributário', %s, %s, %s, null, true)", (c1, _lido(limpo, c1), IMG, LEGENDA)).fetchone()[0]
        c.execute("select radar_cancelar_site(%s)", (r["site"],))                           # (as redes caem junto)
    registrar_site(c1)
    with como("authenticated", ADMIN) as c:
        de_novo = c.execute("select radar_autorizar_rede(%s, 'instagram', %s, %s, %s, true)", (c1, LEGENDA, IMG, _lido(limpo, c1))).fetchone()[0]
        assert de_novo and c.execute("select radar_cancelar_rede(%s)", (de_novo,)).fetchone()[0] is True
        assert c.execute("select radar_autorizar_rede(%s, 'facebook', %s, %s, %s)", (c1, LEGENDA, IMG, _lido(limpo, c1))).fetchone()[0]   # o outro canal, não
        c.execute("select radar_cancelar_rede(r.id) from radar_redes_envios r where r.conteudo_id = %s and r.canal = 'facebook' and r.situacao = 'autorizado'", (c1,))
    # depois que uma publicação do canal sai de fato, a cancelada de antes não pede mais a caixa
    limpo.execute("""insert into radar_redes_envios (conteudo_id, canal, legenda, situacao, conteudo_lido_em, enviado_em, publicado_em, post_id,
                                                     excluido_em, excluido_como)
                     values (%s, 'instagram', 'Publicada e excluída depois.', 'excluido', now(), now(), now(), '99', now(), 'api')""", (c1,))
    with como("authenticated", ADMIN) as c:
        assert c.execute("select radar_autorizar_rede(%s, 'instagram', %s, %s, %s)", (c1, LEGENDA, IMG, _lido(limpo, c1))).fetchone()[0]
    # a imagem (até 3 MB) não vai para a trilha de auditoria; quem autorizou e a legenda vão
    trilha = limpo.execute("select antes, depois from radar_auditoria where tabela = 'radar_redes_envios'").fetchall()
    assert trilha and all("imagem" not in (x or {}) for par in trilha for x in par)
    assert any((d or {}).get("legenda") == LEGENDA for _, d in trilha)
    # link da imagem inválido (longo demais) não apaga a imagem guardada
    with como("authenticated", ADMIN) as c:
        outro = c.execute("select radar_autorizar_rede(%s, 'facebook', %s, %s, %s, true)", (c1, LEGENDA, IMG, _lido(limpo, c1))).fetchone()[0]
    with como("service_role") as c:
        c.execute("select radar_rede_iniciar(%s)", (outro,))
        c.execute("select radar_rede_concluir(%s, false, null, null, %s, 'falhou')", (outro, "https://x.co/" + "a" * 600))
    assert limpo.execute("select imagem, imagem_url from radar_redes_envios where id = %s", (outro,)).fetchone() == (IMG, None)


# ------------------------------------------------ v0.14.0: verificação em fontes oficiais e textos sem aviso de origem
def test_transformar_analise_tira_o_aviso_de_fonte_nao_oficial_do_texto(limpo):
    a = limpo.execute("insert into radar_assuntos (titulo) values ('Boletim com aviso') returning id").fetchone()[0]
    corpo = ("*Este informativo é baseado em material de fonte não oficial e precisa ser conferido.*\n\n"
             "O prazo foi prorrogado.\n***\nFonte NÃO-oficial: boletim ITC\n\n\nBoletos de fontes não oficiais são golpe.\n\nEsta notícia alerta para boletos de fontes não oficiais.\n\n## Análise Artecon\nOrganize os documentos.")
    c = limpo.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo, gerado_por, modelo_ia, status, avisos_ia, fora_do_site)
                         values (%s, 'flash', 'Boletim', %s, 'ia', 'm', 'rascunho', '["TEXTO PARA ANÁLISE, escrito a partir de fonte NÃO oficial (ITC)."]', true)
                         returning id""", (a, corpo)).fetchone()[0]
    with como("authenticated", ADMIN) as k:
        k.execute("select radar_liberar_sem_fundamentacao(%s, 'Autorizado pelo responsável técnico')", (a,))
        novo = k.execute("select radar_converter_analise(%s)", (c,)).fetchone()[0]
    copia = limpo.execute("select corpo from radar_conteudos where id = %s", (novo,)).fetchone()[0]
    assert copia == ("O prazo foi prorrogado.\n***\n\nBoletos de fontes não oficiais são golpe.\n\nEsta notícia alerta para boletos de fontes não oficiais."
                     "\n\n## Análise Artecon\nOrganize os documentos.")
    assert limpo.execute("select corpo from radar_conteudos where id = %s", (c,)).fetchone()[0] == corpo   # o original fica como estava


def test_verificacao_fica_no_assunto_e_a_equipe_le(limpo):
    a = limpo.execute("insert into radar_assuntos (titulo) values ('Verificado') returning id").fetchone()[0]
    with como("authenticated", EDITOR) as c:                                    # a função de IA grava com o token de quem pediu
        c.execute("""update radar_assuntos set verificacao = '{"situacao": "confirmada", "fontes": []}', verificado_em = now() where id = %s""", (a,))
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute("update radar_assuntos set verificacao = '[1, 2]' where id = %s", (a,))
    with como("authenticated", LEITOR) as c:
        assert c.execute("select verificacao->>'situacao' from radar_assuntos where id = %s", (a,)).fetchone()[0] == "confirmada"


# ------------------------------------------------ v0.14.3: ponto marcado com [VERIFICAR] não é aprovado nem publicado
MARCADO = "O governo não publicou, até [VERIFICAR: sexta-feira, dia 2 de outubro de 2026], a MP. Falta ainda [verificar a alíquota]."


def test_marca_verificar_trava_a_aprovacao_e_a_mensagem_lista_cada_marca(limpo):
    a, c1 = cenario_publicavel(limpo)
    limpo.execute("update radar_conteudos set corpo = %s where id = %s", (MARCADO, c1))
    with como("authenticated", EDITOR) as c, pytest.raises(
            psycopg.errors.RaiseException,
            match=r"RADAR139: resolva antes de liberar: 2 ponto\(s\) .*\"\[VERIFICAR: sexta-feira, dia 2 de outubro de 2026\]\"; \"\[verificar a alíquota\]\""):
        c.execute("update radar_conteudos set status = 'aprovado' where id = %s", (c1,))
    # no título também conta
    limpo.execute("update radar_conteudos set corpo = 'Texto conferido do informativo.', titulo = 'Prazo [VERIFICAR data] prorrogado' where id = %s", (c1,))
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.RaiseException, match=r"RADAR139: .*1 ponto\(s\).*\[VERIFICAR data\]"):
        c.execute("update radar_conteudos set status = 'aprovado' where id = %s", (c1,))
    # colchete que não é marca não atrapalha
    limpo.execute("update radar_conteudos set titulo = 'Prazo prorrogado', corpo = 'Veja o art. 5º [revogado] e o anexo [I].' where id = %s", (c1,))
    assert aprovar(c1) == (EDITOR,)


def test_conteudo_aprovado_com_marca_nao_vai_ao_site_nem_as_redes(limpo):
    a, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    registrar_site(c1)
    # aprovado antes da trava, com a marca no texto (o gatilho fica de fora só para montar o cenário antigo)
    limpo.execute("set session_replication_role = replica")
    limpo.execute("update radar_conteudos set corpo = %s where id = %s", (MARCADO, c1))
    limpo.execute("set session_replication_role = origin")
    lido = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (c1,)).fetchone()[0]
    with como("authenticated", ADMIN) as c:
        with pytest.raises(psycopg.errors.RaiseException, match=r"RADAR139: .*2 ponto\(s\)"):
            c.execute("select radar_autorizar_rede(%s, 'facebook', %s, %s, %s)", (c1, LEGENDA, IMG, lido))
    limpo.execute("set session_replication_role = replica")
    limpo.execute("update radar_conteudos set corpo = 'Texto conferido do informativo.' where id = %s", (c1,))
    limpo.execute("set session_replication_role = origin")
    lido = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (c1,)).fetchone()[0]
    with como("authenticated", ADMIN) as c:
        with pytest.raises(psycopg.errors.RaiseException, match=r"RADAR139: .*\[VERIFICAR: link\]"):   # a legenda também
            c.execute("select radar_autorizar_rede(%s, 'facebook', %s, %s, %s)", (c1, LEGENDA + " [VERIFICAR: link]", IMG, lido))
        assert c.execute("select radar_autorizar_rede(%s, 'facebook', %s, %s, %s)", (c1, LEGENDA, IMG, lido)).fetchone()[0]
    assert limpo.execute("select count(*) from radar_redes_envios where conteudo_id = %s", (c1,)).fetchone()[0] == 1


def test_site_nao_aceita_autorizacao_de_conteudo_com_marca(limpo):
    a, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    limpo.execute("set session_replication_role = replica")
    limpo.execute("update radar_conteudos set titulo = 'Prazo [VERIFICAR] prorrogado' where id = %s", (c1,))
    limpo.execute("set session_replication_role = origin")
    lido = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (c1,)).fetchone()[0]
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match=r"RADAR139: .*\[VERIFICAR\]"):
        c.execute("select radar_autorizar_site(%s, 'Tributário', %s)", (c1, lido))
    assert limpo.execute("select count(*) from radar_site_envios where conteudo_id = %s", (c1,)).fetchone()[0] == 0


def test_autorizacao_antiga_com_marca_nao_sai_na_nova_tentativa(limpo):
    a, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    registrar_site(c1)
    with como("authenticated", ADMIN) as c:
        envio = c.execute("select radar_autorizar_rede(%s, 'facebook', %s, %s, %s)", (c1, LEGENDA, IMG, _lido(limpo, c1))).fetchone()[0]
    # autorizada antes da trava, com a marca na legenda (cenário montado por fora)
    limpo.execute("update radar_redes_envios set legenda = legenda || ' [VERIFICAR: prazo]' where id = %s", (envio,))
    with como("service_role") as c:
        r = c.execute("select radar_rede_iniciar(%s)", (envio,)).fetchone()[0]
    assert r["erro"].startswith("RADAR139:") and "[VERIFICAR: prazo]" in r["erro"]
    assert limpo.execute("select situacao from radar_redes_envios where id = %s", (envio,)).fetchone()[0] == "erro"


def test_marca_com_espaco_especial_tambem_conta(limpo):
    assert limpo.execute("select radar_marcas_verificar(%s)", ("Prazo [\u00a0VERIFICAR data] ok",)).fetchone()[0].startswith("RADAR139")
    assert limpo.execute("select radar_marcas_verificar('Texto [verificado] e [Verificação] ok')").fetchone()[0] is None


# ------------------------------------------------ v0.15.0: fundamentação legal citada no texto capturado
def _base(db, titulo, texto=None, resumo=None):
    return db.execute("select radar_base_legal(%s, %s, %s)", (titulo, resumo, texto)).fetchone()[0]


@pytest.mark.parametrize("texto, normas", [
    ("A Lei Complementar nº 214, de 16 de janeiro de 2025, regulamenta o IBS. Ver também a LC 214/2025, art. 12.",
     ["Lei Complementar nº 214/2025"]),                                                       # a mesma norma escrita de dois jeitos
    ("Conforme a IN RFB nº 2.229/2024 e a Instrução Normativa nº 2229.", ["Instrução Normativa RFB nº 2.229/2024"]),
    ("Leis nºs 10.637/2002 e 10.833/2003; Decreto-Lei nº 1.598/1977; Decreto nº 9.580, de 22 de novembro de 2018",
     ["Lei nº 10.637/2002", "Lei nº 10.833/2003", "Decreto-Lei nº 1.598/1977", "Decreto nº 9.580/2018"]),
    ("Resolução CGSN nº 140/2018 e Resolução CGIBS nº 6/2026", ["Resolução CGSN nº 140/2018", "Resolução CGIBS nº 6/2026"]),
    ("Portaria MF nº 12 e Portaria RFB nº 12", ["Portaria MF nº 12", "Portaria RFB nº 12"]),                 # órgãos diferentes
    ("MP 1.303/2025 e Medida Provisória nº 1.303, de 11 de junho de 2025", ["Medida Provisória nº 1.303/2025"]),
    ("Convênio ICMS 52/17, Ajuste SINIEF nº 7/2005 e Protocolo ICMS 41/08",
     ["Convênio ICMS nº 52/2017", "Ajuste SINIEF nº 7/2005", "Protocolo ICMS nº 41/2008"]),                  # ano com 4 dígitos
    ("LEI COMPLEMENTAR Nº 123, DE 14 DE DEZEMBRO DE 2006", ["Lei Complementar nº 123/2006"]),
    ("Lei n.º 12.546/2011, Lei n° 12.973/14 e Parecer Normativo Cosit nº 1/2018",
     ["Lei nº 12.546/2011", "Lei nº 12.973/2014", "Parecer Normativo Cosit nº 1/2018"]),
    ("art. 150 da Constituição Federal, art. 3º do CTN e o RIR/2018",
     ["Constituição Federal", "Código Tributário Nacional (CTN)", "Regulamento do Imposto de Renda (RIR/2018)"]),
    ("Opção pelo Simei permanece em janeiro", []),
    ("O MP 2 de Santa Catarina, o leilão da Receita, a eleição e a lei 2 vezes citada", []),     # nada disso é norma
    ("O decreto de 5 de março e a resolução de conflitos", []),                                 # sem número não é citação
    # o que a varredura da v0.15.0 achou
    ("a Lei estadual nº 17.763/2019, o Decreto estadual nº 48.123, de 2025, e a Portaria conjunta RFB/PGFN nº 1/2025",
     ["Lei estadual nº 17.763/2019", "Decreto estadual nº 48.123/2025", "Portaria conjunta RFB/PGFN nº 1/2025"]),
    ("o Projeto de Lei nº 1.087/2025, o Projeto de Lei Complementar (PLP) nº 108/2024, a PROPOSTA DE EMENDA CONSTITUCIONAL Nº 45 "
     "e a minuta de Instrução Normativa nº 2.400", []),                                         # ainda não são norma
    ("LEI NO 9.430/1996; Decreto Número 9.580/2018; IN RFB No 2.229/2024 e IN RFB nº 2.229/2024",
     ["Lei nº 9.430/1996", "Decreto nº 9.580/2018", "Instrução Normativa RFB nº 2.229/2024"]),
    ("Lei Kandir 25 anos depois; Decreto Altera 3 Regras; Compensações da Lei Kandir 2025; Portaria MF 12", ["Portaria MF nº 12"]),
    ("o decreto no 1º dia útil; a lei no 2º turno; as portarias nos 30 dias; a resolução no 3º trimestre", []),
    ("A denúncia do MP no 2º grau, o MP Eleitoral 2, LC nº 87, EC nº 42 e IN RFB nº 20",
     ["Lei Complementar nº 87", "Emenda Constitucional nº 42", "Instrução Normativa RFB nº 20"]),
    ("Resolução CGSN nº 140/2018 e a Resolução do CGSN nº 140; Portaria Conjunta RFB/PGFN nº 1/2025 e Portaria Conjunta nº 1/2025",
     ["Resolução CGSN nº 140/2018", "Portaria Conjunta RFB/PGFN nº 1/2025"]),
    ("Resolução CGIBS nº 1/2025 e Resolução CGIBS nº 1/2026; Convênio ICMS 52/2017 e Convênio ICMS 52/17; Resolução CGIBS nº 1",
     ["Resolução CGIBS nº 1/2025", "Resolução CGIBS nº 1/2026", "Convênio ICMS nº 52/2017"]),        # o ano separa
    ("Convênios ICMS nºs 52/17 e 53/17; Súmulas CARF nºs 10 e 11; Lei Geral de Proteção de Dados (LGPD) nº 13.709/2018",
     ["Convênio ICMS nº 52/2017", "Convênio ICMS nº 53/2017", "Súmula CARF nº 10", "Súmula CARF nº 11",
      "Lei Geral de Proteção de Dados nº 13.709/2018"]),
    ("RIR/2018 e RIR/18; RICMS/SP e RICMS-SP", ["Regulamento do Imposto de Renda (RIR/2018)", "RICMS/SP"]),
    ("fere o art. 195 da CF e o art. 150, VI, da Constituição; a Constituição Estadual e a constituição da empresa",
     ["Constituição Federal"]),
    # o que a conferência nas capturas reais achou
    ("Altera o Ato COTEPE/ICMS nº 23, de 27 de março de 2018, e o Ato COTEPE/PMPF nº 27/2026",
     ["Ato COTEPE/ICMS nº 23/2018", "Ato COTEPE/PMPF nº 27/2026"]),
    ("as Leis nºs 14.596, de 14 de junho de 2023, 14.597, de 14 de junho de 2023 (Lei Geral do Esporte), e 15.421, de 1º de junho "
     "de 2026; LEI Nº 12.973, DE 2014; Portaria SEF nº 164, de 2004",
     ["Lei nº 14.596/2023", "Lei nº 14.597/2023", "Lei nº 15.421/2026", "Lei nº 12.973/2014", "Portaria SEF nº 164/2004"]),
    # o que a segunda varredura achou
    ("O art. 3º da Lei nº 9.718/1998 (com a redação dada pela Lei nº 12.973/2014); a LC nº 214/2025 (alterada pela LC 227/2026)",
     ["Lei nº 9.718/1998", "Lei nº 12.973/2014", "Lei Complementar nº 214/2025", "Lei Complementar nº 227/2026"]),
    ("A CLT foi aprovada pelo Decreto-Lei nº 5.452, de 1º de maio de 1943. O art. 457 do DL 5.452/43 trata da remuneração.",
     ["Decreto-Lei nº 5.452/1943"]),                    # "/43" é 1943; a CLT é o próprio Decreto-Lei 5.452, não se repete
    ("as Leis nºs 10.637 e 10.833, de 2002 e 2003, respectivamente; as Leis 14.973 e 15.270 e 12 outras normas",
     ["Lei nº 10.637", "Lei nº 10.833", "Lei nº 14.973", "Lei nº 15.270"]),
    ("A Resolução do Comitê Gestor do Simples Nacional nº 183, de 2026; PORTARIA DO MINISTRO DE ESTADO DA FAZENDA Nº 12, DE 1º DE "
     "OUTUBRO DE 2026; Portaria da Procuradoria-Geral da Fazenda Nacional nº 6.757, de 29 de julho de 2022",
     ["Resolução do Comitê Gestor do Simples Nacional nº 183/2026", "Portaria do Ministro de Estado da Fazenda nº 12/2026",
      "Portaria da Procuradoria-Geral da Fazenda Nacional nº 6.757/2022"]),
    ("A Receita editou 15 instruções normativas nos 100 primeiros dias; as leis nos 5.568 municípios", []),
    ("o CF-e-SAT; Receita Simplifica a Constituição de Empresas; a Proposta de Emenda à Constituição nº 45; na Constituição catarinense", []),
    ("Decreto 1.866, de 05.07.2022 e Decreto 1.866, de 10.10.2008", ["Decreto nº 1.866/2022", "Decreto nº 1.866/2008"]),
    ("Lei do IRPF 2026: veja as faixas; Portaria MEI 2026 traz novidades; RECEITA PUBLICA PORTARIA COM 12 NOVAS REGRAS; "
     "DECRETO DE 2 DE OUTUBRO DE 2026", []),
    ("Nova portaria A Portaria RFB nº 5, de 2026, altera as regras. Governo edita decreto O Decreto nº 12.500, de 2026.",
     ["Portaria RFB nº 5/2026", "Decreto nº 12.500/2026"]),
    # o que a conferência nas capturas reais (Receita, PGFN, CGIBS) achou
    ("aprovada pela Res. Gecex nº 272, de 2021, pelo Dec. nº 11.158, de 2022, e pelo Decreto. nº 435, de 27 de janeiro 1992",
     ["Resolução Gecex nº 272/2021", "Decreto nº 11.158/2022", "Decreto nº 435/1992"]),
    ("Ato Técnico Conjunto Sufis CGIBS nº 8, de 01/10/2026; Ato Conjunto RFB/CGIBS nº 4, de 30 de julho de 2026",
     ["Ato Técnico Conjunto Sufis CGIBS nº 8/2026", "Ato Conjunto RFB/CGIBS nº 4/2026"]),
    ("Edital de Transação PGFN/RFB nº 5/2026; Edital PGDAU nº 6/2026; o edital 3 dias depois",
     ["Edital de Transação PGFN/RFB nº 5/2026", "Edital PGDAU nº 6/2026"]),
    ("Atos Declaratórios Executivos Corat nº 63, de 26 de agosto de 2026, e nº 78, de 28 de setembro de 2026",
     ["Ato Declaratório Executivo Corat nº 63/2026", "Ato Declaratório Executivo Corat nº 78/2026"]),
    ("Lei nº 5.172, de 1966 (Código Tributário Nacional), art. 138; CTN; Decreto nº 9.580/2018 (RIR/2018)",
     ["Lei nº 5.172/1966", "Decreto nº 9.580/2018"]),                                      # o CTN é a própria Lei 5.172
    ("IN RFB nº 1.187, 29 de agosto de 2011; IN RFB nº 2342/2026 e IN RFB nº 2.342",
     ["Instrução Normativa RFB nº 1.187/2011", "Instrução Normativa RFB nº 2.342/2026"]),
    # (SEF/SC, Simples Nacional, Econet)
    ("Atos Diat 29/09/2026 ATO DIAT Nº 061/2026 Altera o RICMS. Portarias 06/10/2026 PORTARIA SEF N° 317/2026",
     ["Ato DIAT nº 061/2026", "Portaria SEF nº 317/2026", "RICMS"]),                  # a data do cabeçalho não é norma
    ("às Leis Complementares nº 214, de 2025, e nº 227, de 2026; Lei federal nº 5.172 , de 25 de outubro de 1966 (Código Tributário Nacional)",
     ["Lei Complementar nº 214/2025", "Lei Complementar nº 227/2026", "Lei federal nº 5.172/1966"]),
    ("A Resposta à Consulta Tributária nº 33.130/2026 da Sefaz-SP; o Regulamento do ICMS",
     ["Resposta à Consulta Tributária nº 33.130/2026", "RICMS"]),
    # o que a terceira varredura achou
    ("Os Convênios ICMS 142/18, 52/17 e 190/17; as Leis Complementares nºs 123/2006 e 87/1996; as Leis 14.973 e 15.270 e 12 outras",
     ["Convênio ICMS nº 142/2018", "Convênio ICMS nº 52/2017", "Convênio ICMS nº 190/2017", "Lei Complementar nº 123/2006",
      "Lei Complementar nº 87/1996", "Lei nº 14.973", "Lei nº 15.270"]),
    ("A Resolução do Comitê Gestor do Simples Nacional (CGSN) nº 140, de 22 de maio de 2018, e a Resolução CGSN nº 140/2018; "
     "Portaria PGFN/MF nº 2.970/2026 e Portaria PGFN nº 2.970/2026; Ato Declaratório Executivo Coana nº 140, de 2026, e o Ato "
     "Declaratório Coana nº 140/2026",
     ["Resolução do Comitê Gestor do Simples Nacional nº 140/2018", "Portaria PGFN/MF nº 2.970/2026",
      "Ato Declaratório Executivo Coana nº 140/2026"]),                                     # o órgão por extenso, com sufixo ou com parte
    ("A Resolução CGIBS nº 1/2026 (alterada pela Resolução do Comitê Gestor do IBS nº 2/2026)",
     ["Resolução CGIBS nº 1/2026", "Resolução do Comitê Gestor do IBS nº 2/2026"]),
    ("As LCs 214/2025 e 227/2026; As MPs 1.303/2025 e 1.304/2025; O Dec.-Lei nº 1.598/77; a Medida Provisória nº 2.158-35, de 2001",
     ["Lei Complementar nº 214/2025", "Lei Complementar nº 227/2026", "Medida Provisória nº 1.303/2025", "Medida Provisória nº 1.304/2025",
      "Decreto-Lei nº 1.598/1977", "Medida Provisória nº 2.158-35/2001"]),
    ("A Receita publicou o Edital nº 1/2026 do concurso; o Edital de Licitação nº 12/2026; o Edital de Transação por Adesão nº "
     "25/2024 e, depois, o Edital nº 25/2024", ["Edital de Transação nº 25/2024"]),
    ("Portaria SEF 03.10.2026 altera o regulamento; Resolução CGSN 25/09/2026: novas regras; Governo Edita 15 Portarias Nos 100 Dias", []),
    ("O Regulamento do Imposto de Renda (RIR/2018), aprovado pelo Decreto nº 9.580/2018; o Regulamento do ICMS de SC (RICMS/SC)",
     ["Decreto nº 9.580/2018", "RICMS/SC"]),
    ("A imunidade (CF, art. 150, VI, d); conforme o art. 128 do ADCT",
     ["Constituição Federal", "Ato das Disposições Constitucionais Transitórias (ADCT)"]),
    ("LEIS NºS 10.637/2002 E 10.833/2003; a Portaria do Ministério do Trabalho e Emprego nº 671, de 8 de novembro de 2021",
     ["Lei nº 10.637/2002", "Lei nº 10.833/2003", "Portaria do Ministério do Trabalho e Emprego nº 671/2021"]),
    ("As Portarias SEF nºs 250 e 251, de 2026; da Lei n º 9.782, de 26 de janeiro de 1999; PORTARIA CONJUNTA RFB/PGFN Nº 1, DE 2025",
     ["Portaria SEF nº 250/2026", "Portaria SEF nº 251/2026", "Lei nº 9.782/1999", "Portaria Conjunta RFB/PGFN nº 1/2025"]),
])
def test_fundamentacao_legal_le_as_normas_citadas(limpo, texto, normas):
    b = _base(limpo, "Notícia", texto)
    assert b["normas"] == normas and b["total"] == len(normas) and b["ato"] is None


def test_fundamentacao_legal_reconhece_a_captura_que_e_o_proprio_ato(limpo):
    b = _base(limpo, "Solução de Consulta Cosit nº 190, de 30/09/2026", "Assunto: IRPJ. Dispositivos: Lei nº 9.430, de 1996, art. 1º.")
    assert b == {"ato": "Solução de Consulta Cosit nº 190/2026", "total": 2,
                 "normas": ["Solução de Consulta Cosit nº 190/2026", "Lei nº 9.430/1996"]}
    assert _base(limpo, "ATO DIAT Nº 063/2026")["ato"] == "Ato DIAT nº 063/2026"
    assert _base(limpo, "Receita publica a Instrução Normativa RFB nº 2.300")["ato"] is None   # notícia sobre o ato não é o ato
    assert _base(limpo, "Lei nº 15.270/2025: o que muda no Imposto de Renda")["ato"] is None
    assert _base(limpo, "LC 87 completa 30 anos", "Lei Complementar nº 87, de 13 de setembro de 1996")["ato"] is None
    assert _base(limpo, "Decreto nº 12.955, de 2026 - Regulamenta a CBS")["ato"] == "Decreto nº 12.955/2026"
    assert _base(limpo, "PORTARIA RFB Nº 1, DE 2 DE OUTUBRO DE 2026")["ato"] == "Portaria RFB nº 1/2026"
    assert _base(limpo, "Ato COTEPE/PMPF nº 27/2026 (DOU DE 29/09/2026)")["ato"] == "Ato COTEPE/PMPF nº 27/2026"
    assert _base(limpo, "Lei nº 15.270/2025 – entenda o que muda no Imposto de Renda")["ato"] is None   # travessão de notícia
    assert _base(limpo, "INSTRUÇÃO NORMATIVA RFB Nº 2.300, DE 7 DE OUTUBRO DE 2026 - DISPÕE SOBRE A CBS")["ato"] == \
        "Instrução Normativa RFB nº 2.300/2026"
    # o título casa o fim, mas não é citação de norma
    assert _base(limpo, "LC 87", "Lei Complementar nº 87, de 13 de setembro de 1996")["ato"] is None
    assert _base(limpo, "Portaria 12 - altera prazos", "Conforme a Portaria MF nº 12/2025")["ato"] is None


def test_fundamentacao_legal_avisa_quando_o_texto_capturado_esta_cortado(limpo):
    b = _base(limpo, "Área Federal", "A Receita informou que o prazo do parcelamento foi prorrogado e que as empresas devem...")
    assert b == {"ato": None, "total": 0, "normas": [], "cortado": True}
    assert "cortado" not in _base(limpo, "Notícia", "Texto inteiro, sem norma.")
    assert _base(limpo, "Notícia", "O prazo foi prorrogado. Leia mais:")["cortado"] is True
    # a matéria do boletim da ITC é gravada como texto parcial: sem norma, também fica "cortado"
    with como("service_role") as c:
        cap = c.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo, metadados)
                           select id, 'https://x.gov.br/parcial', 'Prazo da DCTFWeb', 'O prazo foi prorrogado.', 'h', '{"texto_parcial": true}'
                             from radar_fontes where slug = 'rfb-noticias' returning id""").fetchone()[0]
        assert c.execute("select base_legal->>'cortado' from radar_capturas where id = %s", (cap,)).fetchone()[0] == "true"
    assert _base(limpo, "Lei nº 15.270/2025")["ato"] == "Lei nº 15.270/2025"           # espaço especial


def test_fundamentacao_legal_nao_passa_de_uma_parte_para_outra_e_aceita_acento_separado(limpo):
    # o título termina com "portaria" e o resumo começa pela IN: a IN não vira "Portaria Instrução Normativa..."
    assert _base(limpo, "Receita publica portaria", resumo="Instrução Normativa RFB nº 2.300/2026 altera a CBS.")["normas"] == \
        ["Instrução Normativa RFB nº 2.300/2026"]
    nfd = limpo.execute("select normalize('Conforme a Resolução CGSN nº 140/2018 e a Constituição Federal', NFD)").fetchone()[0]
    assert _base(limpo, "Notícia", nfd)["normas"] == ["Resolução CGSN nº 140/2018", "Constituição Federal"]


def test_fundamentacao_legal_guarda_ate_12_e_conta_todas(limpo):
    texto = "; ".join(f"Portaria RFB nº {n}" for n in range(101, 121))
    b = _base(limpo, "Notícia", texto)
    assert b["total"] == 20 and len(b["normas"]) == 12 and b["normas"][0] == "Portaria RFB nº 101"
    # a Constituição e o CTN não ficam escondidos no "e mais"
    b = _base(limpo, "Notícia", "Com base no art. 195 da Constituição Federal e no CTN; " + texto)
    assert b["total"] == 22 and len(b["normas"]) == 12 and b["normas"][-2:] == ["Constituição Federal", "Código Tributário Nacional (CTN)"]
    # o "…" de um endereço encurtado no fim não é texto cortado
    assert "cortado" not in _base(limpo, "Notícia", "Acesse: https://www.gov.br/receitafederal/pt-br/programas-e-atividade…")


def test_fundamentacao_legal_em_texto_grande_e_rapida(limpo):
    texto = ("Considerando o disposto no art. 5º da Lei nº 9.430, de 27 de dezembro de 1996, e na Instrução Normativa RFB nº 2.229, "
             "de 2024, resolve: " + "Parágrafo sem norma nenhuma, com números 1.234,56 e datas 01/02/2026. " * 80) * 12
    assert len(texto) > 60000
    t0 = datetime.now(timezone.utc)
    b = _base(limpo, "Portaria do DOU", texto)
    assert (datetime.now(timezone.utc) - t0).total_seconds() < 5
    assert b["normas"] == ["Lei nº 9.430/1996", "Instrução Normativa RFB nº 2.229/2024"]
    # muitas normas diferentes (um regulamento consolidado): o tempo cresce na proporção das citações, não com o quadrado
    def tempo(n):
        texto = " ".join(f"Art. {i}. Altera a Lei nº {1000 + i}, de 2020, e o Decreto nº {5000 + i}/2021." for i in range(1, n + 1))
        t0 = datetime.now(timezone.utc)
        b = _base(limpo, "Regulamento", texto)
        return (datetime.now(timezone.utc) - t0).total_seconds(), b
    tempo(10)                                                            # a 1ª chamada monta as expressões
    t300, b = tempo(300)
    assert b["total"] == 600 and len(b["normas"]) == 12
    t1500, b = tempo(1500)
    assert b["total"] > 2900                                             # só os primeiros 100 mil caracteres do texto são lidos
    assert t1500 < max(t300, 0.2) * 12 and t1500 < 15, (t300, t1500)     # 5 vezes as citações: bem menos que 25 vezes o tempo


def test_fundamentacao_legal_e_calculada_pelo_banco_na_captura(limpo):
    with como("service_role") as c:
        cap = c.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo)
                           select id, 'https://x.gov.br/bl', 'Prazo do Simei', 'Sem norma citada.', 'h' from radar_fontes
                            where slug = 'rfb-noticias' returning id""").fetchone()[0]
        assert c.execute("select base_legal from radar_capturas where id = %s", (cap,)).fetchone()[0] == {"normas": [], "total": 0, "ato": None}
        # o texto mudou: lê de novo
        c.execute("update radar_capturas set texto = 'Conforme a Resolução CGSN nº 140/2018.' where id = %s", (cap,))
        assert c.execute("select base_legal->'normas' from radar_capturas where id = %s", (cap,)).fetchone()[0] == ["Resolução CGSN nº 140/2018"]
        # ninguém marca à mão: o valor gravado por fora é ignorado
        c.execute("""update radar_capturas set base_legal = '{"normas": ["Lei nº 1"], "total": 1, "ato": null}' where id = %s""", (cap,))
        assert c.execute("select base_legal->'normas' from radar_capturas where id = %s", (cap,)).fetchone()[0] == ["Resolução CGSN nº 140/2018"]
        assert c.execute("select base_legal->>'total' from radar_v_fila where id = %s", (cap,)).fetchone()[0] == "1"
        assert c.execute("select versao from radar_capturas where id = %s", (cap,)).fetchone()[0] == 2   # só a mudança de texto contou
        # o título e o resumo também são lidos de novo quando mudam
        c.execute("update radar_capturas set titulo = 'Resolução CGSN nº 183/2026 prorroga prazo' where id = %s", (cap,))
        assert "Resolução CGSN nº 183/2026" in c.execute("select base_legal->'normas' from radar_capturas where id = %s", (cap,)).fetchone()[0]
        c.execute("update radar_capturas set resumo_fonte = 'Conforme a Lei nº 9.430/1996.' where id = %s", (cap,))
        assert "Lei nº 9.430/1996" in c.execute("select base_legal->'normas' from radar_capturas where id = %s", (cap,)).fetchone()[0]
    with como("authenticated", LEITOR) as c:                         # a equipe vê pela fila; "Em alta" tem a mesma coluna
        assert "Resolução CGSN nº 140/2018" in c.execute("select base_legal->'normas' from radar_v_fila where id = %s", (cap,)).fetchone()[0]
        assert "base_legal" in [d.name for d in c.execute("select * from radar_v_em_alta limit 0").description]


def test_recalcular_fundamentacao_legal_le_as_capturas_que_ja_estavam(limpo):
    cap = nova_captura(limpo, texto="Art. 1º Fica alterada a Lei Complementar nº 123, de 14 de dezembro de 2006.")
    velha = nova_captura(limpo, url="https://exemplo.gov.br/velha", texto="Conforme a Lei nº 9.430/1996.")
    limpo.execute("set session_replication_role = replica")          # captura de antes da v0.15.0, ainda sem a leitura,
    limpo.execute("update radar_capturas set base_legal = null where id = %s", (cap,))
    limpo.execute("""update radar_capturas set base_legal = '{"normas": [], "total": 0, "ato": null}' where id = %s""", (velha,))
    limpo.execute("set session_replication_role = origin")             # e outra lida por uma regra mais antiga
    relev = limpo.execute("select relevancia, relevancia_pontos, versao, atualizado_em from radar_capturas where id = %s", (cap,)).fetchone()
    assert limpo.execute("select radar_recalcular_base_legal()").fetchone()[0] == 2
    assert limpo.execute("select radar_recalcular_base_legal()").fetchone()[0] == 0          # nada mudou na segunda vez
    assert limpo.execute("select base_legal->'normas' from radar_capturas where id = %s", (velha,)).fetchone()[0] == \
        ["Instrução Normativa RFB nº 2290", "Lei nº 9.430/1996"]
    assert limpo.execute("select base_legal->'normas' from radar_capturas where id = %s", (cap,)).fetchone()[0] == \
        ["Instrução Normativa RFB nº 2290", "Lei Complementar nº 123/2006"]
    assert limpo.execute("select relevancia, relevancia_pontos, versao, atualizado_em from radar_capturas where id = %s", (cap,)).fetchone() == relev
    # a matéria parcial do boletim continua "cortada" no recálculo, e o gatilho lê de novo quando ela passa a ser parcial
    parcial = limpo.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo, metadados)
                               select id, 'https://x.gov.br/parcial2', 'Prazo da DCTFWeb', 'O prazo foi prorrogado.', 'h', '{"texto_parcial": true}'
                                 from radar_fontes where slug = 'rfb-noticias' returning id""").fetchone()[0]
    limpo.execute("set session_replication_role = replica")
    limpo.execute("update radar_capturas set base_legal = null where id = %s", (parcial,))
    limpo.execute("set session_replication_role = origin")
    limpo.execute("select radar_recalcular_base_legal()")
    assert limpo.execute("select base_legal->>'cortado' from radar_capturas where id = %s", (parcial,)).fetchone()[0] == "true"
    limpo.execute("""update radar_capturas set metadados = '{}' where id = %s""", (parcial,))
    assert limpo.execute("select base_legal->>'cortado' from radar_capturas where id = %s", (parcial,)).fetchone()[0] is None
    with como("service_role") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("select radar_recalcular_base_legal()")


def test_instalacao_le_a_fundamentacao_das_capturas_que_ja_estavam(db, limpo):
    cap = nova_captura(limpo, texto="Conforme a Resolução CGSN nº 140/2018.")
    limpo.execute("set session_replication_role = replica")          # como ficam as capturas de antes da v0.15.0
    limpo.execute("update radar_capturas set base_legal = null")
    limpo.execute("set session_replication_role = origin")
    r = psql(SETUP)
    assert r.returncode == 0, r.stderr
    assert limpo.execute("select count(*) from radar_capturas where base_legal is null").fetchone()[0] == 0
    assert "Resolução CGSN nº 140/2018" in limpo.execute("select base_legal->'normas' from radar_capturas where id = %s", (cap,)).fetchone()[0]


def test_fila_mostra_a_fundamentacao_de_outra_captura_do_mesmo_fato(limpo):
    def cap(url, titulo, texto):
        return limpo.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo)
                                select id, %s, %s, %s, md5(%s) from radar_fontes where slug = 'rfb-noticias' returning id""",
                             (url, titulo, texto, url)).fetchone()[0]
    a = cap("https://x.gov.br/a", "Receita prorroga prazo", "A Receita prorrogou o prazo.")
    r1 = cap("https://x.gov.br/r1", "Prazo prorrogado", "O prazo foi prorrogado.")                     # repetição sem norma
    r2 = cap("https://x.gov.br/r2", "CGSN prorroga prazo", "Conforme a Resolução CGSN nº 183, de 1º de outubro de 2026.")
    limpo.execute("update radar_capturas set duplicata_de = %s where id in (%s, %s)", (a, r1, r2))
    fila = dict(limpo.execute("select id, base_legal_repeticao->'normas' from radar_v_fila").fetchall())
    assert limpo.execute("select base_legal->>'total' from radar_capturas where id = %s", (a,)).fetchone()[0] == "0"
    assert fila[a] == ["Resolução CGSN nº 183/2026"]                   # a principal mostra a da repetição que cita (não a da R1)
    assert fila[r1] == ["Resolução CGSN nº 183/2026"]                  # a repetição sem norma mostra a da irmã
    assert fila[r2] is None                                            # quem cita mostra a sua
    limpo.execute("insert into radar_assunto_capturas values (%s, %s)", (novo_assunto(limpo), r2))   # a que cita saiu da fila
    assert limpo.execute("select base_legal_repeticao from radar_v_fila where id = %s", (a,)).fetchone()[0] is None
    # a repetição sem norma, cuja principal cita, mostra a da principal
    p = cap("https://x.gov.br/p", "CGSN publica resolução do Simples", "Conforme a Resolução CGSN nº 183, de 1º de outubro de 2026.")
    q = cap("https://x.gov.br/q", "Receita prorroga prazo do Simples", "A Receita Federal informou que o prazo foi prorrogado.")
    limpo.execute("update radar_capturas set duplicata_de = %s where id = %s", (p, q))
    assert limpo.execute("select base_legal_repeticao->'normas' from radar_v_fila where id = %s", (q,)).fetchone()[0] == ["Resolução CGSN nº 183/2026"]


# ------------------------------------------------ v0.16.0: "Autorizar mesmo assim", pontos a conferir, ilustração e repetição
def test_autorizar_copia_so_pela_funcao_com_motivo_e_cai_quando_o_texto_muda(limpo):
    c1 = novo_conteudo(limpo, novo_assunto(limpo), status="rascunho")
    lido = limpo.execute("select atualizado_em from radar_conteudos where id = %s", (c1,)).fetchone()[0]
    for papel, uid in (("authenticated", LEITOR), ("authenticated", SEM_PERFIL), ("anon", None)):
        with como(papel, uid) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select radar_autorizar_copia(%s, 'transcrição da lei', %s)", (c1, lido))
    with como("authenticated", EDITOR) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR143"):
            c.execute("select radar_autorizar_copia(%s, ' ok ', %s)", (c1, lido))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR144"):          # tela velha
            c.execute("select radar_autorizar_copia(%s, 'transcrição da lei', now() - interval '1 day')", (c1,))
        # direto na tabela, nada muda
        c.execute("update radar_conteudos set copia_autorizada_em = now(), copia_autorizada_por = %s, copia_autorizada_motivo = 'x' where id = %s", (EDITOR, c1))
        assert c.execute("select copia_autorizada_em, copia_autorizada_por, copia_autorizada_motivo from radar_conteudos where id = %s",
                         (c1,)).fetchone() == (None, None, None)
        lido = c.execute("select atualizado_em from radar_conteudos where id = %s", (c1,)).fetchone()[0]
        assert c.execute("select radar_autorizar_copia(%s, '  transcrição do art. 2º da IN, com a fonte  ', %s)", (c1, lido)).fetchone()[0] is not None
        assert c.execute("select copia_autorizada_por::text, copia_autorizada_motivo from radar_conteudos where id = %s", (c1,)).fetchone() == \
            (EDITOR, "transcrição do art. 2º da IN, com a fonte")
        c.execute("update radar_conteudos set titulo = 'CBS: o que muda em 2027' where id = %s", (c1,))         # título: a autorização fica
        assert c.execute("select copia_autorizada_em is not null from radar_conteudos where id = %s", (c1,)).fetchone()[0]
        c.execute("update radar_conteudos set corpo = corpo || ' Mais um parágrafo.' where id = %s", (c1,))     # texto: cai
        assert c.execute("select copia_autorizada_em, copia_autorizada_por, copia_autorizada_motivo from radar_conteudos where id = %s",
                         (c1,)).fetchone() == (None, None, None)
        nova = c.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo, copia_autorizada_em, copia_autorizada_motivo)
                            select assunto_id, 'flash', 't', 'c', now(), 'forjada' from radar_conteudos where id = %s returning id""", (c1,)).fetchone()[0]
        assert c.execute("select copia_autorizada_em, copia_autorizada_motivo from radar_conteudos where id = %s", (nova,)).fetchone() == (None, None)
    assert limpo.execute("""select count(*) from radar_auditoria where tabela = 'radar_conteudos' and registro_id = %s
                            and antes->>'copia_autorizada_motivo' is null
                            and depois->>'copia_autorizada_motivo' = 'transcrição do art. 2º da IN, com a fonte'""", (str(c1),)).fetchone()[0] == 1   # quem e por quê, na trilha


def test_pontos_a_conferir_so_crescem(limpo):
    a = novo_assunto(limpo)
    c1 = limpo.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo, gerado_por, modelo_ia, avisos_ia)
                          values (%s, 'flash', 't', 'c', 'ia', 'm', '["um", "dois"]') returning id""", (a,)).fetchone()[0]
    def avisos():
        return limpo.execute("select avisos_ia from radar_conteudos where id = %s", (c1,)).fetchone()[0]
    with como("authenticated", EDITOR) as c:
        for ruim in ('[]', '["um"]', '["dois", "um"]', '["um", "dois", 3]', '["um", "dois", {"a": 1}]', '{"a": 1}',
                     json.dumps(["um", "dois"] + ["x"] * 11), json.dumps(["um", "dois", "y" * 2001])):
            c.execute("update radar_conteudos set avisos_ia = %s::jsonb where id = %s", (ruim, c1))
            assert avisos() == ["um", "dois"], ruim
        c.execute("""update radar_conteudos set avisos_ia = avisos_ia || '["Ficou fora do texto: prazo."]' where id = %s""", (c1,))
    assert avisos() == ["um", "dois", "Ficou fora do texto: prazo."]


def test_ilustracao_guardada_nao_some_na_limpeza_e_sai_junto_com_o_conteudo(limpo):
    cid = novo_conteudo(limpo, novo_assunto(limpo))
    capa, ilus, ilus2 = (nova_imagem() for _ in range(3))
    limpo.execute("update radar_conteudos set imagem_id = %s, ilustracao_id = %s where id = %s", (capa, ilus, cid))
    limpo.execute("update radar_imagens set criado_em = now() - interval '3 days'")
    with como("service_role") as c:
        assert c.execute("select radar_limpar_imagens_sem_uso()").fetchone()[0] == 1          # só a ilus2, que ninguém usa
    assert {r[0] for r in limpo.execute("select id from radar_imagens").fetchall()} == {capa, ilus}
    nova = nova_imagem()
    limpo.execute("update radar_conteudos set ilustracao_id = %s where id = %s", (nova, cid))  # trocar a ilustração apaga a antiga
    assert {r[0] for r in limpo.execute("select id from radar_imagens").fetchall()} == {capa, nova}
    limpo.execute("update radar_conteudos set imagem_id = %s where id = %s", (nova, cid))      # a mesma imagem nos dois campos
    assert {r[0] for r in limpo.execute("select id from radar_imagens").fetchall()} == {nova}
    limpo.execute("update radar_conteudos set imagem_id = null where id = %s", (cid,))          # ainda é a ilustração: fica
    assert {r[0] for r in limpo.execute("select id from radar_imagens").fetchall()} == {nova}
    limpo.execute("delete from radar_conteudos where id = %s", (cid,))
    assert limpo.execute("select count(*) from radar_imagens").fetchone()[0] == 0
    assert ilus2 not in {r[0] for r in limpo.execute("select id from radar_imagens").fetchall()}


def test_separar_repeticao_na_fila(limpo):
    def cap(url, titulo):
        return limpo.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo)
                                select id, %s, %s, 'texto', md5(%s) from radar_fontes where slug = 'rfb-noticias' returning id""",
                             (url, titulo, url)).fetchone()[0]
    origem = cap("https://x.gov.br/o", "Subvenção: crédito presumido de ICMS na base do IRPJ e da CSLL")
    rep = cap("https://x.gov.br/r", "Créditos presumidos de ICMS ficam fora da base do PIS e da Cofins, decide o STF")
    outra = cap("https://x.gov.br/s", "Outra")
    limpo.execute("update radar_capturas set duplicata_de = %s where id = %s", (origem, rep))
    assert limpo.execute("select repetidas from radar_v_fila where id = %s", (origem,)).fetchone()[0] == 1
    for papel, uid in (("authenticated", LEITOR), ("authenticated", SEM_PERFIL), ("anon", None)):
        with como(papel, uid) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select radar_separar_repeticao(%s)", (rep,))
    with como("authenticated", EDITOR) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR142"):
            c.execute("select radar_separar_repeticao(%s)", (outra,))
        c.execute("select radar_separar_repeticao(%s)", (rep,))
    dup, separada = limpo.execute("select duplicata_de, metadados ? 'separada_em' from radar_capturas where id = %s", (rep,)).fetchone()
    assert dup is None and separada
    assert limpo.execute("select repetidas from radar_v_fila where id = %s", (origem,)).fetchone()[0] == 0
    assert limpo.execute("select principal from radar_v_fila where id = %s", (rep,)).fetchone()[0] is True
    assert limpo.execute("""select usuario::text, antes->>'duplicata_de', depois->>'motivo' from radar_auditoria
                            where tabela = 'radar_capturas' and registro_id = %s""", (str(rep),)).fetchone() == \
        (EDITOR, str(origem), "não é o mesmo fato (separada na triagem)")
    # a que já está num assunto separa-se pela tela do assunto
    limpo.execute("update radar_capturas set duplicata_de = %s where id = %s", (origem, outra))
    limpo.execute("insert into radar_assunto_capturas values (%s, %s)", (novo_assunto(limpo), outra))
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR141"):
        c.execute("select radar_separar_repeticao(%s)", (outra,))


def test_separada_na_triagem_nao_volta_a_ser_juntada(limpo):
    def cap(url, titulo, slug="rfb-noticias"):
        return limpo.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo)
                                select id, %s, %s, 'texto', md5(%s) from radar_fontes where slug = %s returning id""",
                             (url, titulo, url, slug)).fetchone()[0]
    origem = cap("https://x.gov.br/o", "Crédito presumido de ICMS na base do IRPJ e da CSLL")
    b = cap("https://x.gov.br/b", "Créditos presumidos de ICMS ficam fora da base do PIS e da Cofins, decide o STF")
    limpo.execute("update radar_capturas set duplicata_de = %s where id = %s", (origem, b))
    with como("authenticated", EDITOR) as c:
        c.execute("select radar_separar_repeticao(%s)", (b,))
    # o robô regrava o texto e os metadados da captura (a fonte mudou a matéria): a decisão da equipe fica
    with como("service_role") as c:
        c.execute("update radar_capturas set texto = 'texto novo da fonte', titulo = titulo || ' (atualizado)', metadados = '{}' where id = %s", (b,))
    assert limpo.execute("select metadados ? 'separada_em' from radar_capturas where id = %s", (b,)).fetchone()[0]
    # a IA avalia de novo e diz que é igual à origem: não volta a ser juntada
    with como("service_role") as c:
        r = c.execute("select radar_gravar_avaliacao_ia(%s)", (json.dumps([{"id": b, "nota": 7, "igual_a": origem}]),)).fetchone()[0]
    assert r["gravadas"] == 1 and r["repetidas"] == 0
    assert limpo.execute("select duplicata_de, ia_nota from radar_capturas where id = %s", (b,)).fetchone() == (None, 7)


def test_separada_tambem_nao_e_juntada_pelo_outro_lado(limpo):
    def cap(url, titulo):
        return limpo.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo)
                                select id, %s, %s, 'texto', md5(%s) from radar_fontes where slug = 'rfb-noticias' returning id""",
                             (url, titulo, url)).fetchone()[0]
    o = cap("https://x.gov.br/o2", "Crédito presumido de ICMS na base do IRPJ e da CSLL")
    b = cap("https://x.gov.br/b2", "Créditos presumidos de ICMS ficam fora da base do PIS e da Cofins, decide o STF")
    with como("service_role") as c:
        c.execute("select radar_gravar_avaliacao_ia(%s)", (json.dumps([{"id": b, "nota": 8, "igual_a": o}]),))
    with como("authenticated", EDITOR) as c:
        c.execute("select radar_separar_repeticao(%s)", (b,))
    assert limpo.execute("select metadados->'separada_de' from radar_capturas where id = %s", (b,)).fetchone()[0] == [o]
    assert limpo.execute("select metadados->'separada_de' from radar_capturas where id = %s", (o,)).fetchone()[0] == [b]
    # a origem é avaliada de novo e a IA diz que ela é igual à separada: não junta pelo outro lado
    with como("service_role") as c:
        r = c.execute("select radar_gravar_avaliacao_ia(%s)", (json.dumps([{"id": o, "nota": 7, "igual_a": b}]),)).fetchone()[0]
    assert r["repetidas"] == 0 and limpo.execute("select duplicata_de from radar_capturas where id = %s", (o,)).fetchone()[0] is None
    # separada do assunto: lembra da origem e das outras capturas do assunto
    x, y, z = (cap(f"https://x.gov.br/a{i}", f"Receita prorroga prazo — fonte {i}") for i in range(3))
    with como("service_role") as c:
        c.execute("select radar_gravar_avaliacao_ia(%s)", (json.dumps([{"id": x, "nota": 9}, {"id": y, "nota": 8, "igual_a": x}]),))
    with como("authenticated", EDITOR) as c:
        assunto = c.execute("select radar_abrir_assunto(%s)", (x,)).fetchone()[0]
    with como("service_role") as c:
        c.execute("select radar_gravar_avaliacao_ia(%s)", (json.dumps([{"id": z, "nota": 7, "igual_a": x}]),))
    with como("authenticated", EDITOR) as c:
        c.execute("select radar_separar_captura(%s, %s)", (assunto, z))
    assert sorted(limpo.execute("select metadados->'separada_de' from radar_capturas where id = %s", (z,)).fetchone()[0]) == sorted([x, y])
    assert limpo.execute("select metadados->'separada_de' from radar_capturas where id = %s", (x,)).fetchone()[0] == [z]


# ------------------------------------------------------------------- v0.17.0: "Publicar em todos" e exclusão
LEG_IG = "Prazo do Simples prorrogado. Leia no site da Artecon (link na bio)."
LEG_FB = "Prazo do Simples prorrogado. Leia a matéria completa: {LINK DO SITE}"


def test_publicar_em_todos_espera_o_site_e_sai_com_o_link(limpo):
    a, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    lido = _lido(limpo, c1)
    todos = "select radar_autorizar_todos(%s, 'Tributário', %s, %s, %s, %s)"
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR110"):
        c.execute(todos, (c1, lido, IMG, LEG_IG, LEG_FB))
    with como("authenticated", ADMIN) as c:
        for args, erro in [((IMG, None, "  "), "RADAR153"), ((IMG, "curta", LEG_FB), "RADAR154"), ((IMG, "x" * 2001, None), "RADAR154"),
                           (("data:image/png;base64,AAAA", LEG_IG, LEG_FB), "RADAR135"), ((IMG, LEG_IG + " [VERIFICAR: ano]", None), "RADAR139")]:
            with pytest.raises(psycopg.errors.RaiseException, match=erro):
                c.execute(todos, (c1, lido, *args))
        r = c.execute(todos, (c1, lido, IMG, LEG_IG, LEG_FB)).fetchone()[0]
        assert set(r) == {"site", "instagram", "facebook"}
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR136"):                # não autoriza duas vezes
            c.execute(todos, (c1, lido, IMG, LEG_IG, LEG_FB))
    assert limpo.execute("select situacao from radar_site_envios where id = %s", (r["site"],)).fetchone()[0] == "autorizado"
    assert limpo.execute("select array_agg(distinct situacao), bool_and(junto_com_site) from radar_redes_envios where conteudo_id = %s",
                         (c1,)).fetchone() == (["aguardando_site"], True)
    with como("service_role") as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR138"):
        c.execute("select radar_rede_iniciar(%s)", (r["instagram"],))                       # antes do site, as redes não saem
    # o robô publica no site e registra o link: as redes ficam prontas, com o link no lugar de {LINK DO SITE}
    with como("service_role") as c:
        c.execute("update radar_site_envios set situacao = 'enviando' where id = %s", (r["site"],))
        c.execute("insert into radar_divulgacoes (conteudo_id, url, publicado_em) values (%s, 'https://artecon.cnt.br/news/view/prazo', current_date)", (c1,))
    fb, ig = (limpo.execute("select situacao, legenda from radar_redes_envios where id = %s", (r[k],)).fetchone() for k in ("facebook", "instagram"))
    assert fb == ("autorizado", "Prazo do Simples prorrogado. Leia a matéria completa: https://artecon.cnt.br/news/view/prazo")
    assert ig == ("autorizado", LEG_IG)
    with como("service_role") as c:
        assert c.execute("select radar_rede_iniciar(%s)", (r["facebook"],)).fetchone()[0]["legenda"].endswith("/news/view/prazo")


def test_publicar_em_todos_so_libera_as_redes_com_o_link_do_site_registrado_pelo_robo(limpo):
    """Varredura geral (v0.22.0): o registro da publicação troca o {LINK DO SITE} e libera as redes do "Publicar em todos". Um
    registro à mão antes do robô (o link da fonte colado por engano) ou com link de outro endereço não libera nada: as redes que
    esperavam o site caem, com o motivo, e a legenda nunca leva um link que o administrador não viu."""
    a, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    todos = "select radar_autorizar_todos(%s, 'Tributário', %s, %s, %s, %s)"
    redes = lambda: limpo.execute("select situacao, legenda, erro from radar_redes_envios where conteudo_id = %s and canal = 'facebook' "
                                  "order by id desc limit 1", (c1,)).fetchone()
    with como("authenticated", ADMIN) as c:
        r = c.execute(todos, (c1, _lido(limpo, c1), IMG, LEG_IG, LEG_FB)).fetchone()[0]
    # o editor registra à mão enquanto o robô ainda não publicou: recusado (o robô registra o link sozinho)
    for uid in (EDITOR, ADMIN):
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR145"):
            registrar_site(c1, uid=uid, url="https://golpe.example/pix")
    assert redes()[0] == "aguardando_site"
    # o registro com link de outro endereço (mesmo vindo do robô) não libera: as redes caem com o motivo
    with como("service_role") as c:
        c.execute("update radar_site_envios set situacao = 'enviando' where id = %s", (r["site"],))
        c.execute("insert into radar_divulgacoes (conteudo_id, url, publicado_em) values (%s, 'https://golpe.example/pix', current_date)", (c1,))
    situacao, legenda, erro = redes()
    assert situacao == "cancelado" and "golpe" not in legenda and "{LINK DO SITE}" in legenda and "não é do site da Artecon" in erro
    assert limpo.execute("select count(*) from radar_redes_envios where conteudo_id = %s and situacao in ('autorizado','aguardando_site')",
                         (c1,)).fetchone()[0] == 0
    # o site saiu, mas o registro do robô não entrou: a pessoa registra depois do "publicado" com o link do site — aí libera
    limpo.execute("delete from radar_divulgacoes where conteudo_id = %s", (c1,))
    limpo.execute("update radar_site_envios set situacao = 'cancelado' where id = %s", (r["site"],))
    with como("authenticated", ADMIN) as c:
        r = c.execute(todos, (c1, _lido(limpo, c1), IMG, LEG_IG, LEG_FB)).fetchone()[0]
    with como("service_role") as c:
        c.execute("update radar_site_envios set situacao = 'publicado', url = 'https://artecon.cnt.br/news/view/prazo' where id = %s", (r["site"],))
    registrar_site(c1, url="https://www.Artecon.cnt.br/news/view/prazo")
    assert redes()[:2] == ("autorizado", "Prazo do Simples prorrogado. Leia a matéria completa: https://www.Artecon.cnt.br/news/view/prazo")
    # o domínio: sem usuário, porta e "www."; um domínio que só começa igual não é o do site
    assert limpo.execute("select radar_url_host('https://user@WWW.artecon.cnt.br:443/x'), radar_url_host('https://artecon.cnt.br.golpe.example/'), "
                         "radar_site_host()").fetchone() == ("artecon.cnt.br", "artecon.cnt.br.golpe.example", "artecon.cnt.br")


def test_noticia_com_frase_do_boletim_pago_nao_se_autoriza_nem_se_aprova_nem_sai(limpo, request):
    """Varredura geral (v0.22.0): a trava do boletim pago da notícia estava só na tela (que ainda oferecia "Autorizar mesmo
    assim"). No banco: autorizar a cópia, aprovar e publicar no site, no Instagram e no Facebook recusam (RADAR146), sem mostrar o
    trecho. A janela que também está numa captura livre do assunto (o artigo da lei que o boletim copiou) não conta."""
    a, c1 = cenario_publicavel(limpo)
    carregar_fontes_novas(limpo, request)
    paga = "o comitê gestor publicou nesta semana a orientação completa sobre o novo prazo de entrega das declarações mensais"
    boletim = lambda texto, h: limpo.execute(
        """insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo, capturado_em)
           select id, 'https://boletim.exemplo/' || %s, 'Boletim de mentira', %s, %s, now() - interval '200 days'
             from radar_fontes where slug = 'itc-email'""", (h, texto, h))
    boletim("Boletim: " + TEXTO_OFICIAL + " E mais: " + paga + ".", "h-noticia-1")       # o boletim também copiou a IN
    limpo.execute("update radar_conteudos set corpo = %s where id = %s",
                  ("Segundo a Receita Federal, " + TEXTO_OFICIAL[:300] + "\n\nTexto próprio da Artecon.", c1))
    assert aprovar(c1) is not None                                                         # o trecho da IN também está na fonte oficial
    limpo.execute("update radar_conteudos set status = 'em_revisao' where id = %s", (c1,))
    limpo.execute("update radar_conteudos set corpo = corpo || %s where id = %s", ("\n\nResumo: " + paga.upper() + ".", c1))
    lido = _lido(limpo, c1)
    with como("authenticated", EDITOR) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR146") as e:
            c.execute("select radar_autorizar_copia(%s, 'transcrição do boletim, com a fonte citada', %s)", (c1, lido))
        assert "comitê" not in str(e.value)                                                # só sim ou não: o trecho não sai
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR146"):
        aprovar(c1)
    # aprovado antes de o boletim chegar (ou por um caminho antigo): o site, as redes e o envio que já estava autorizado não saem
    limpo.execute("update radar_conteudos set corpo = replace(corpo, %s, 'Resumo próprio.') where id = %s", ("Resumo: " + paga.upper() + ".", c1))
    aprovar(c1)
    registrar_site(c1)
    leg = "Prazo novo para as declarações. " + paga + ". Leia no site."
    with como("authenticated", ADMIN) as c:
        ig = c.execute("select radar_autorizar_rede(%s, 'instagram', %s, %s, %s)", (c1, LEGENDA, IMG, _lido(limpo, c1))).fetchone()[0]
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR146"):
            c.execute("select radar_autorizar_rede(%s, 'facebook', %s, %s, %s)", (c1, leg, IMG, _lido(limpo, c1)))
    limpo.execute("delete from radar_divulgacoes where conteudo_id = %s", (c1,))
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR146"):
        c.execute("select radar_autorizar_todos(%s, 'Tributário', %s, %s, null, %s)", (c1, _lido(limpo, c1), IMG, leg))
    # sem a captura livre no assunto (o administrador liberou sem fundamentação), o trecho da IN que está no boletim conta
    limpo.execute("delete from radar_evidencias where assunto_id = %s", (a,))
    limpo.execute("delete from radar_assunto_capturas where assunto_id = %s", (a,))
    with como("authenticated", ADMIN) as c:
        c.execute("select radar_liberar_sem_fundamentacao(%s, 'teste da trava do boletim')", (a,))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR146"):
            c.execute("select radar_autorizar_site(%s, 'Tributário', %s)", (c1, _lido(limpo, c1)))
    with como("service_role") as c:
        r = c.execute("select radar_rede_iniciar(%s)", (ig,)).fetchone()[0]
    assert r["erro"].startswith("RADAR146") and "comitê" not in r["erro"]
    assert limpo.execute("select situacao from radar_redes_envios where id = %s", (ig,)).fetchone()[0] == "erro"


def test_onde_esta_a_frase_do_boletim_que_o_banco_recusa_e_a_ementa_do_ato_oficial_nao_conta(limpo, request):
    """Rodada 2 da varredura geral. (1) A trava do banco (RADAR146) compara com TODAS as capturas do boletim; a tela, só com as do
    assunto: radar_copia_paga_trechos diz ONDE, no texto da própria notícia, está o que o banco recusaria (só as posições, nada do
    boletim), com a mesma regra e o mesmo desconto das capturas livres do assunto; só o editor e o administrador. (2) A matéria do
    boletim que é o próprio ato ("Lei nº … (DOU DE …)", texto = a ementa oficial) fica fora da base paga."""
    a, c1 = cenario_publicavel(limpo)
    carregar_fontes_novas(limpo, request)
    paga = "o comitê gestor publicou nesta semana a orientação completa sobre o novo prazo de entrega das declarações mensais"
    ementa = ("Altera a Instrução Normativa RFB nº 2.005, de 29 de janeiro de 2021, que dispõe sobre a Declaração de Débitos e "
              "Créditos Tributários Federais Previdenciários e de Outras Entidades e Fundos")
    boletim = lambda titulo, texto, h: limpo.execute(
        """insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo)
           select id, 'https://boletim.exemplo/' || %s, %s, %s, %s from radar_fontes where slug = 'itc-email'""", (h, titulo, texto, h))
    trechos = lambda textos, uid=EDITOR, assunto=a: _como_trechos(uid, assunto, textos)
    assert trechos(["Texto qualquer com " + paga]) == [[]]                                # sem boletim no banco: nada
    # a matéria do boletim fica na fila (não está no assunto); ela também copiou a IN da fonte oficial do assunto
    boletim("Boletim de mentira", "Boletim: " + TEXTO_OFICIAL + " E mais: " + paga + ".", "h-trechos-1")
    corpo = ("📌 Segundo a Receita Federal, " + TEXTO_OFICIAL[:300] + "\n\nTexto próprio da Artecon.\n\nResumo: "
             + paga.upper().replace(" GESTOR ", " gestor,\n") + ".")
    titulo = "CBS: " + paga                                                                  # o título também é conferido
    limpo.execute("update radar_conteudos set titulo = %s, corpo = %s where id = %s", (titulo, corpo, c1))
    r = trechos([titulo, corpo])
    assert r == [[[5, 5 + len(paga)]], [[corpo.index("O COMITÊ"), len(corpo) - 1]]], r     # a IN (livre no assunto) não entra
    assert corpo[r[1][0][0]:r[1][0][1]] == paga.upper().replace(" GESTOR ", " gestor,\n")  # posição em letras, com o emoji
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR146"):                    # e o banco recusa o mesmo texto
        aprovar(c1)
    # duas faixas separadas; 11 palavras não bastam
    onze, doze = " ".join(paga.split()[:11]), " ".join(paga.split()[:12])
    r = trechos([onze + ". Outra coisa. " + doze + ". Fim e mais " + doze])
    assert len(r[0]) == 2 and r[0][0][0] == len(onze) + len(". Outra coisa. ")
    # só quem edita; nada sai do boletim
    for uid in (LEITOR, SEM_PERFIL):
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR147"):
            trechos([corpo], uid)
    with como("anon") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("select radar_copia_paga_trechos(%s, %s)", (a, [corpo]))
    # (2) a ementa oficial que o boletim lista ("Legislação Federal") não é frase do boletim: nem na notícia, nem na Pauta
    boletim("Instrução Normativa RFB nº 2.300/2026 (DOU DE 07/10/2026)", ementa, "h-trechos-ato")
    limpo.execute("update radar_conteudos set titulo = 'DCTFWeb muda', corpo = %s where id = %s",
                  ("Segundo o Diário Oficial da União, a norma nova " + ementa.lower() + ".\n\nTexto próprio da Artecon.", c1))
    assert trechos(["DCTFWeb muda", ementa]) == [[], []]
    assert aprovar(c1) is not None
    assert limpo.execute("select radar_pauta_copia_paga(%s)", ([ementa],)).fetchone()[0] is False
    # a mesma frase numa matéria comum do boletim (texto da ITC) conta
    boletim("Receita muda a DCTFWeb", "Na avaliação da consultoria: " + ementa, "h-trechos-noticia")
    assert limpo.execute("select radar_pauta_copia_paga(%s)", ([ementa],)).fetchone()[0] is True
    assert trechos([ementa]) == [[[0, len(ementa)]]]
    for titulo_ato, e_ato in [("Lei nº 15526/2026 (DOU DE 30/09/2026)", True), ("Ato COTEPE/PMPF nº 27/2026 (DOU DE 29/09/2026)", True),
                              ("Portaria SEF nº 250/2026 (DOE-SC de 01/10/2026)", True), ("DECRETO Nº 12.955, DE 1º DE OUTUBRO DE 2026 (DOU de 02/10/2026).", True),
                              ("Resolução CGSN nº 183/2026 (DOU - Edição Extra de 30/09/2026)", True),
                              ("Receita prorroga o prazo da DCTFWeb (DOU de 01/10/2026)", False), ("Lei nº 15.270/2025: o que muda no IR", False),
                              ("Leilão da Receita (DOU de 01/10/2026)", False), ("Nota ITC (Doença ocupacional de 01/10/2026)", False),
                              ("Lei nº 15.270/2025 (Lei do IR)", False), (None, False)]:
        assert limpo.execute("select radar_copia_paga_ato_oficial(%s)", (titulo_ato,)).fetchone()[0] is e_ato, titulo_ato


def _como_trechos(uid, assunto, textos):
    with como("authenticated", uid) as c:
        return c.execute("select radar_copia_paga_trechos(%s, %s)", (assunto, textos)).fetchone()[0]


def test_publicar_em_todos_cai_junto_se_o_site_nao_sair(limpo):
    a, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    todos = "select radar_autorizar_todos(%s, 'Tributário', %s, %s, %s, %s)"
    situacoes = lambda: limpo.execute("select situacao, erro from radar_redes_envios where conteudo_id = %s order by id desc limit 1", (c1,)).fetchone()
    with como("authenticated", ADMIN) as c:                                                  # só o Instagram, e o administrador cancela o site
        r = c.execute(todos, (c1, _lido(limpo, c1), IMG, LEG_IG, None)).fetchone()[0]
        assert "facebook" not in r
        c.execute("select radar_cancelar_site(%s)", (r["site"],))
    assert situacoes()[0] == "cancelado" and "autorização cancelada" in situacoes()[1]
    with como("authenticated", ADMIN) as c:                                                  # o robô não consegue publicar
        r = c.execute(todos, (c1, _lido(limpo, c1), IMG, LEG_IG, None)).fetchone()[0]
    with como("service_role") as c:
        c.execute("update radar_site_envios set situacao = 'erro', erro = 'categoria sumiu' where id = %s", (r["site"],))
    assert situacoes()[0] == "cancelado" and "o robô não conseguiu" in situacoes()[1]
    with como("authenticated", ADMIN) as c:                                                  # o texto muda antes de sair
        r = c.execute(todos, (c1, _lido(limpo, c1), IMG, LEG_IG, None)).fetchone()[0]
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_conteudos set titulo = 'Outro título' where id = %s", (c1,))
    assert situacoes()[0] == "cancelado"
    with como("authenticated", ADMIN) as c:                                                  # e o administrador pode cancelar só a rede
        aprovar(c1)
        r = c.execute(todos, (c1, _lido(limpo, c1), IMG, None, LEG_FB)).fetchone()[0]
        assert c.execute("select radar_cancelar_rede(%s)", (r["facebook"],)).fetchone()[0] is True
    assert limpo.execute("select situacao from radar_site_envios where id = %s", (r["site"],)).fetchone()[0] == "autorizado"


def test_exclusao_da_publicacao_no_site_e_nas_redes(limpo):
    a, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR151"):
        c.execute("select radar_pedir_exclusao_site(%s)", (c1,))                               # nada no site ainda
    registrar_site(c1)
    with como("authenticated", ADMIN) as c:
        ig = c.execute("select radar_autorizar_rede(%s, 'instagram', %s, %s, %s)", (c1, LEGENDA, IMG, _lido(limpo, c1))).fetchone()[0]
    with como("service_role") as c:
        c.execute("select radar_rede_iniciar(%s)", (ig,))
        c.execute("select radar_rede_concluir(%s, true, '1789', 'https://www.instagram.com/p/abc/', null, null)", (ig,))
    # Instagram: só o administrador registra a exclusão (a função radar-redes depois da Meta, ou ele mesmo, se apagou à mão)
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR130"):
        c.execute("select radar_rede_marcar_excluida(%s, 'manual')", (ig,))
    with como("authenticated", ADMIN) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR155"):
            c.execute("select radar_rede_marcar_excluida(%s, 'qualquer')", (ig,))
        assert c.execute("select radar_rede_marcar_excluida(%s, 'manual')", (ig,)).fetchone()[0] is True
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR156"):
            c.execute("select radar_rede_marcar_excluida(%s, 'manual')", (ig,))
        # excluída, pode publicar de novo no mesmo canal
        assert c.execute("select radar_autorizar_rede(%s, 'instagram', %s, %s, %s)", (c1, LEGENDA, IMG, _lido(limpo, c1))).fetchone()[0]
    assert limpo.execute("select situacao, excluido_como, excluido_por::text from radar_redes_envios where id = %s", (ig,)).fetchone() == \
        ("excluido", "manual", ADMIN)
    # site: pedido do administrador, o robô exclui e conclui; o registro em "Publicações no site" sai
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR150"):
        c.execute("select radar_pedir_exclusao_site(%s)", (c1,))
    with como("authenticated", ADMIN) as c:
        x = c.execute("select radar_pedir_exclusao_site(%s)", (c1,)).fetchone()[0]
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR152"):
            c.execute("select radar_pedir_exclusao_site(%s)", (c1,))
        assert c.execute("select radar_cancelar_exclusao_site(%s)", (x,)).fetchone()[0] is True
        x = c.execute("select radar_pedir_exclusao_site(%s)", (c1,)).fetchone()[0]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):                              # a tela não grava direto
            c.execute("update radar_site_exclusoes set situacao = 'excluido' where id = %s", (x,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select radar_site_exclusao_concluir(%s, true, null)", (x,))           # só o robô conclui
    assert limpo.execute("select url, titulo from radar_site_exclusoes where id = %s", (x,)).fetchone() == \
        ("https://artecon.cnt.br/news/cgsn-prorroga-prazo", limpo.execute("select titulo from radar_conteudos where id = %s", (c1,)).fetchone()[0])
    with como("service_role") as c:
        assert c.execute("update radar_site_exclusoes set situacao = 'excluindo', iniciado_em = now() where id = %s returning id", (x,)).fetchone()
        assert c.execute("select radar_site_exclusao_concluir(%s, true, null)", (x,)).fetchone()[0] is True
        assert c.execute("select radar_site_exclusao_concluir(%s, true, null)", (x,)).fetchone()[0] is False   # já concluída
    assert limpo.execute("select count(*) from radar_divulgacoes where conteudo_id = %s", (c1,)).fetchone()[0] == 0
    assert limpo.execute("select situacao from radar_site_exclusoes where id = %s", (x,)).fetchone()[0] == "excluido"
    assert limpo.execute("select status from radar_assuntos where id = %s", (a,)).fetchone()[0] == "aprovado"   # volta a "em andamento"
    with como("authenticated", LEITOR) as c:                                                  # a equipe vê o histórico
        assert c.execute("select count(*) from radar_site_exclusoes").fetchone()[0] == 2
    # exclusão que não deu certo: fica "erro", com o motivo, e o administrador pode desistir
    registrar_site(c1)
    with como("authenticated", ADMIN) as c:
        x = c.execute("select radar_pedir_exclusao_site(%s)", (c1,)).fetchone()[0]
    with como("service_role") as c:
        c.execute("select radar_site_exclusao_concluir(%s, false, 'há 2 notícias com este título')", (x,))
    assert limpo.execute("select situacao, erro from radar_site_exclusoes where id = %s", (x,)).fetchone() == ("erro", "há 2 notícias com este título")
    assert limpo.execute("select count(*) from radar_divulgacoes where conteudo_id = %s", (c1,)).fetchone()[0] == 1
    with como("authenticated", ADMIN) as c:
        assert c.execute("select radar_cancelar_exclusao_site(%s)", (x,)).fetchone()[0] is True


# ------------------------------------------------------------------- v0.20.0: kit das redes feito pela IA (kit_ia)
KIT = {"versao": 1, "gerado_em": "2026-10-11T14:00:00Z", "modelo": "claude-sonnet-4-6",
       "arte": {"chamada": "CBS no documento fiscal a partir de 2027", "apoio": "Quem emite nota fiscal destaca a alíquota de 0,9%."},
       "instagram": {"texto": "A CBS entra no documento fiscal em 2027.\n\nLeia a matéria completa no site (link na bio).",
                     "hashtags": ["#cbs", "#reformatributaria", "#notafiscal"]},
       "facebook": {"texto": "A CBS entra no documento fiscal em 2027.\n\nLeia a matéria completa: {LINK DO SITE}", "hashtags": ["#cbs"]},
       "reel": {"gancho": "Sua nota fiscal muda em 2027.", "duracao": 36,
                "cenas": [{"de": 0, "ate": 3, "fala": "Sua nota fiscal muda em 2027.", "texto_tela": "CBS na nota"},
                          {"de": 3, "ate": 36, "fala": "A CBS passa a ser destacada à alíquota de 0,9%.", "texto_tela": "0,9% de CBS"}],
                "chamada_final": "Leia a matéria completa no site.", "legenda": "A CBS na nota fiscal. Link na bio."},
       "avisos": []}


def _kit(db, c1):
    return db.execute("select kit_ia from radar_conteudos where id = %s", (c1,)).fetchone()[0]


def test_kit_ia_nao_muda_a_data_nem_derruba_autorizacoes(limpo):
    """Gravar o kit (como a função radar-ia faz: PATCH só de kit_ia, com o atualizado_em lido) não é alteração do texto: a data,
    a aprovação e as autorizações do site e das redes ficam como estavam (sem isso, RADAR114, a autorização cancelada sozinha e o
    robô do site recusando "o conteúdo mudou depois de autorizado")."""
    a, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    lido = _lido(limpo, c1)
    with como("authenticated", ADMIN) as c:
        r = c.execute("select radar_autorizar_todos(%s, 'Tributário', %s, %s, %s, %s)", (c1, lido, IMG, LEG_IG, LEG_FB)).fetchone()[0]
    gravar = "update radar_conteudos set kit_ia = %s where id = %s and atualizado_em = %s"
    with como("authenticated", EDITOR) as c:
        assert c.execute(gravar, (json.dumps(KIT), c1, lido)).rowcount == 1
    assert limpo.execute("select atualizado_em, status, aprovado_por::text from radar_conteudos where id = %s", (c1,)).fetchone() == \
        (lido, "aprovado", EDITOR)
    assert _kit(limpo, c1) == KIT
    assert limpo.execute("select situacao, conteudo_lido_em from radar_site_envios where id = %s", (r["site"],)).fetchone() == ("autorizado", lido)
    assert limpo.execute("select array_agg(situacao order by id) from radar_redes_envios where conteudo_id = %s", (c1,)).fetchone()[0] == \
        ["aguardando_site", "aguardando_site"]
    # quem gravou o kit fica na trilha
    assert limpo.execute("""select usuario::text from radar_auditoria where tabela = 'radar_conteudos' and acao = 'UPDATE'
                            and antes->'kit_ia' is distinct from depois->'kit_ia'""").fetchall() == [(EDITOR,)]
    # o site sai; o kit é refeito; as redes saem com a versão do texto que foi autorizada
    with como("service_role") as c:
        c.execute("update radar_site_envios set situacao = 'enviando' where id = %s", (r["site"],))
        c.execute("insert into radar_divulgacoes (conteudo_id, url, publicado_em) values (%s, 'https://artecon.cnt.br/news/view/cbs', current_date)", (c1,))
    with como("authenticated", ADMIN) as c:
        assert c.execute(gravar, (json.dumps({**KIT, "gerado_em": "2026-10-11T15:00:00Z"}), c1, lido)).rowcount == 1
    assert _lido(limpo, c1) == lido
    assert limpo.execute("select array_agg(situacao order by id) from radar_redes_envios where conteudo_id = %s", (c1,)).fetchone()[0] == \
        ["autorizado", "autorizado"]
    with como("service_role") as c:
        assert c.execute("select radar_rede_iniciar(%s)", (r["instagram"],)).fetchone()[0]["legenda"] == LEG_IG
    # o título muda: aí sim a data muda, o texto volta à revisão e a autorização que faltava sair cai
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_conteudos set titulo = 'CBS: o que muda na nota' where id = %s", (c1,))
    assert _lido(limpo, c1) > lido
    assert limpo.execute("select status from radar_conteudos where id = %s", (c1,)).fetchone()[0] == "em_revisao"
    assert limpo.execute("select situacao from radar_redes_envios where id = %s", (r["facebook"],)).fetchone()[0] == "cancelado"


def test_kit_ia_fica_desatualizado_quando_o_texto_muda(limpo):
    """O texto mudou e o kit não veio junto: o kit fica marcado como desatualizado (as legendas e o roteiro saem do texto). Só o título
    mudar não marca: escolher outro título sugerido é o passo seguinte ao “Gerar com IA” (o kit guarda o título e a tela avisa)."""
    c1 = novo_conteudo(limpo, novo_assunto(limpo))
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_conteudos set corpo = corpo || ' Ainda sem kit.' where id = %s", (c1,))
        assert _kit(limpo, c1) == {}                                                         # kit vazio não é marcado
        c.execute("update radar_conteudos set kit_ia = %s where id = %s", (json.dumps(KIT), c1))
        assert "desatualizado" not in _kit(limpo, c1)
        c.execute("update radar_conteudos set titulo = 'CBS: o que muda na nota' where id = %s", (c1,))
        assert _kit(limpo, c1) == KIT                                                        # só o título: o kit continua valendo
        c.execute("update radar_conteudos set corpo = corpo || ' Mais um parágrafo.' where id = %s", (c1,))
        assert _kit(limpo, c1) == {**KIT, "desatualizado": True}                            # nada se perde: só ganha a marca
        c.execute("update radar_conteudos set kit_ia = %s where id = %s", (json.dumps(KIT), c1))   # kit gerado de novo
        assert "desatualizado" not in _kit(limpo, c1)
        c.execute("update radar_conteudos set titulo = 'CBS: a nota muda', corpo = corpo || ' E outro.' where id = %s", (c1,))
        assert _kit(limpo, c1)["desatualizado"] is True
        c.execute("update radar_conteudos set kit_ia = %s where id = %s", (json.dumps(KIT), c1))
        # texto e kit novos juntos (o kit veio com o texto): não marca
        c.execute("update radar_conteudos set corpo = corpo || ' O texto novo.', kit_ia = %s where id = %s",
                  (json.dumps({**KIT, "modelo": "outro"}), c1))
        assert _kit(limpo, c1) == {**KIT, "modelo": "outro"}
        # o resto do conteúdo não mexe no kit
        c.execute("update radar_conteudos set autor = 'Equipe Artecon', fonte_credito = 'Receita Federal' where id = %s", (c1,))
        assert "desatualizado" not in _kit(limpo, c1)
    # aprovado: o título muda e o texto volta à revisão, com o kit valendo; o texto muda e o kit fica desatualizado
    aprovar(c1)
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_conteudos set titulo = 'CBS na nota fiscal em 2027' where id = %s", (c1,))
    assert limpo.execute("select status, kit_ia->'desatualizado' from radar_conteudos where id = %s", (c1,)).fetchone() == ("em_revisao", None)
    aprovar(c1)
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_conteudos set corpo = corpo || ' Parágrafo novo.' where id = %s", (c1,))
    assert limpo.execute("select status, kit_ia->'desatualizado' from radar_conteudos where id = %s", (c1,)).fetchone() == ("em_revisao", True)
    # kit no limite de tamanho (só escrito à mão): a marca não impede a edição do texto
    grande = {"x": "a" * 19985}
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_conteudos set kit_ia = %s where id = %s", (json.dumps(grande), c1))
        assert c.execute("select length(kit_ia::text) from radar_conteudos where id = %s", (c1,)).fetchone()[0] <= 20000
        assert c.execute("update radar_conteudos set corpo = corpo || ' Mais.' where id = %s", (c1,)).rowcount == 1
    assert _kit(limpo, c1) == {"desatualizado": True}


def test_kit_ia_formato_tamanho_e_quem_grava(limpo):
    c1 = novo_conteudo(limpo, novo_assunto(limpo))
    assert _kit(limpo, c1) == {}                                                             # conteúdo novo nasce sem kit
    gravar = "update radar_conteudos set kit_ia = %s where id = %s"
    with como("authenticated", EDITOR) as c:
        for ruim in ["[]", '"texto"', "1", "null", json.dumps({"instagram": {"texto": "a" * 20000}})]:   # só objeto, até 20.000
            with pytest.raises(psycopg.errors.CheckViolation, match="radar_conteudos_kit_ia"):
                c.execute(gravar, (ruim, c1))
        with pytest.raises(psycopg.errors.NotNullViolation):
            c.execute(gravar, (None, c1))
    for uid in (LEITOR, SEM_PERFIL):                                                           # quem não edita não grava
        with como("authenticated", uid) as c:
            assert c.execute(gravar, (json.dumps(KIT), c1)).rowcount == 0
    with como("anon") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute(gravar, (json.dumps(KIT), c1))
    assert _kit(limpo, c1) == {}
    with como("authenticated", EDITOR) as c:                                                  # o editor grava (a função usa o token dele)
        assert c.execute(gravar, (json.dumps(KIT), c1)).rowcount == 1
    with como("authenticated", LEITOR) as c:                                                  # e a equipe lê
        assert c.execute("select kit_ia from radar_conteudos where id = %s", (c1,)).fetchone()[0] == KIT


# ------------------------------------------------------------------- v0.21.0: Pauta (peças das redes) e publicação agendada
# Nomes, CNPJ e CRC de mentira (o repositório é público): nunca os da equipe.
ASSINATURA_PAUTA = {"empresa": "Artecon Artes Contábeis ME", "cnpj": "11.222.333/0001-81", "crc": "CRC-SC 012345/O-9"}
IDENT = "Artecon Artes Contábeis ME · CNPJ 11.222.333/0001-81 · CRC-SC 012345/O-9"
LEG_PECA = "Conheça quem cuida da folha de pagamento da sua empresa.\n\n" + IDENT + "\n\n#Contabilidade #Palhoça"
LAMINA = "data:image/jpeg;base64," + "B" * 400
URL_INTERNA = "https://projeto.supabase.co/storage/v1/object/radar-pauta/p-0b1c2d3e-0000-4000-8000-000000000001.jpg"
APROVAR = "select radar_pauta_aprovar(%s, %s, %s::text[], %s, %s::bigint[], %s, %s::text[])"
APROVAR_REEL = "select radar_pauta_aprovar(%s, %s, %s::text[], %s, %s::bigint[], %s, %s::text[], %s)"     # v0.22.0: + o sha256 do vídeo
ACRESCENTE = "Acrescente cada um em Informações conferidas, com a fonte (ou tire do texto)"


@pytest.fixture()
def pauta(limpo):
    """A assinatura com o CNPJ e o CRC (de mentira) preenchidos, como a Pauta exige; no fim, as Configurações voltam ao que eram."""
    antes = dict(limpo.execute("select chave, valor from radar_config where chave in ('assinatura', 'pauta')").fetchall())
    limpo.execute("update radar_config set valor = valor || %s where chave = 'assinatura'", (json.dumps(ASSINATURA_PAUTA),))
    yield limpo
    for chave, valor in antes.items():
        limpo.execute("update radar_config set valor = %s where chave = %s", (json.dumps(valor), chave))


def hoje(db):
    return db.execute("select radar_pauta_hoje()").fetchone()[0]


def nova_pessoa(db, nome="Ana Teste", na_peca="Ana", categoria="", crc="", assinado="2020-01-01", ate=None, revogado=None,
                canais=("instagram", "facebook"), usos=("equipe", "orientacao", "datas", "captacao"), ativo=True):
    return db.execute("""insert into radar_pessoas (nome, nome_na_peca, area, categoria, crc, termo_assinado_em, termo_valido_ate,
                                                    termo_revogado_em, termo_canais, termo_usos, ativo)
                         values (%s, %s, 'Departamento Pessoal', %s, %s, %s, %s, %s, %s::text[], %s::text[], %s) returning id""",
                      (nome, na_peca, categoria, crc, assinado, ate, revogado, list(canais), list(usos), ativo)).fetchone()[0]


def nova_peca(db, dias=2, tipo="bastidor", formato="imagem", hora="09:30", data=None, **campos):
    """Peça daqui a `dias` dias (de Brasília), como a tela deixa depois de preparada: chamada, apoio, a legenda do Instagram com a
    identificação legal e uma informação conferida (e o que vier em `campos`)."""
    data = data or hoje(db) + timedelta(days=dias)
    pid = db.execute("insert into radar_pauta_pecas (data, hora, tipo, formato) values (%s, %s, %s, %s) returning id",
                     (data, hora, tipo, formato)).fetchone()[0]
    valores = {"chamada": "Quem cuida da sua folha de pagamento", "apoio": "Uma conversa com a equipe da Artecon.",
               "legenda_instagram": LEG_PECA, "conferidas": [{"informacao": "A Artecon atende empresas de Palhoça", "fonte": "Site da Artecon"}],
               **campos}
    tipos = {"conferidas": "::jsonb", "cartoes": "::jsonb", "ia": "::jsonb", "pessoas": "::bigint[]", "fotos": "::bigint[]"}
    db.execute("update radar_pauta_pecas set " + ", ".join(f"{k} = %s{tipos.get(k, '')}" for k in valores) + " where id = %s",
               (*[json.dumps(v) if k in ("conferidas", "cartoes", "ia") else v for k, v in valores.items()], pid))
    return pid


def lamina(uid=ADMIN, largura=1080, altura=1350, dados=LAMINA):
    """Lâmina desenhada na tela de quem aprova e guardada em radar_imagens (como a tela faz antes de aprovar)."""
    with como("authenticated", uid) as c:
        return c.execute("insert into radar_imagens (dados, largura, altura) values (%s, %s, %s) returning id", (dados, largura, altura)).fetchone()[0]


def lido_peca(db, pid):
    return db.execute("select atualizado_em from radar_pauta_pecas where id = %s", (pid,)).fetchone()[0]


def marcar_pronta(db, pid, uid=EDITOR):
    with como("authenticated", uid) as c:
        return c.execute("select radar_pauta_marcar_pronta(%s, %s)", (pid, lido_peca(db, pid))).fetchone()[0]


def aprovar_peca(db, pid, modo="agendar", canais=("instagram",), conferencias=("pessoas", "datas"), artes=None, ident=IDENT, uid=ADMIN,
                 video=None):
    """v0.22.0: video = o sha256 do vídeo corrigido que a tela mostrou (o reel)."""
    artes = [lamina(uid)] if artes is None else artes
    with como("authenticated", uid) as c:
        if video is not None:
            return c.execute(APROVAR_REEL, (pid, lido_peca(db, pid), list(canais), modo, artes, ident, list(conferencias), video)).fetchone()[0]
        return c.execute(APROVAR, (pid, lido_peca(db, pid), list(canais), modo, artes, ident, list(conferencias))).fetchone()[0]


def peca_aprovada(db, dias=2, canais=("instagram",), **campos):
    """Peça preparada, pronta e aprovada para sair pela agenda (no futuro, às 09:30 de Brasília). Devolve (peça, resposta)."""
    campos.setdefault("legenda_facebook", LEG_PECA if "facebook" in canais else "")
    pid = nova_peca(db, dias=dias, **campos)
    marcar_pronta(db, pid)
    return pid, aprovar_peca(db, pid, canais=canais)


# v0.22.0: o reel só fica pronto com o vídeo corrigido pronto (radar_video_pendencia). Nomes e falas de mentira.
SHA_VIDEO = "a" * 64
FALA_REEL = "Fala: o prazo vence no dia 20. Confira com a gente antes do vencimento para não pagar multa."


def pessoa_do_corretor(db, nome="Ana Teste", na_peca="Ana", **campos):
    """Pessoa com o termo novo, que cita o corretor de vídeo (termo_corretor_em)."""
    pid = nova_pessoa(db, nome, na_peca, **campos)
    db.execute("update radar_pessoas set termo_corretor_em = '2020-01-01' where id = %s", (pid,))
    return pid


def video_pronto(db, peca, pessoa, sha=SHA_VIDEO, situacao="pronto", cartela=(IDENT,), relatorio=None, fala=None):
    """O vídeo como o robô deixa depois de concluir, gravado direto (o fluxo inteiro está em test_radar_video_banco.py)."""
    fala = fala or db.execute("select left(btrim(roteiro), 200) from radar_pauta_pecas where id = %s", (peca,)).fetchone()[0]
    return db.execute("""insert into radar_videos (peca_id, versao, situacao, partes, fala_pessoa, fala_roteiro, roteiro_hash, cartela_linhas,
                                                   declaracoes, sha256, bytes, duracao_final, relatorio, enviado_em)
                         select p.id, coalesce((select max(versao) from radar_videos where peca_id = p.id), 0) + 1, %s,
                                '[{"n": 1, "tipo": "video/mp4", "bytes": 1000}]', %s, %s, radar_hash_texto(p.roteiro), %s::text[],
                                '{so_marcadas,sem_fundo,so_voz,fala_confere}', %s, 4000, 38.5, %s, now()
                           from radar_pauta_pecas p where p.id = %s returning id""",
                      (situacao, pessoa, fala, list(cartela), sha, json.dumps(relatorio or {"texto_final": ""}), peca)).fetchone()[0]


def iniciar(envio):
    with como("service_role") as c:
        return c.execute("select radar_pauta_iniciar(%s)", (envio,)).fetchone()[0]


def vencer(db, envio, minutos=1):
    db.execute("update radar_redes_envios set agendado_para = now() - make_interval(mins => %s) where id = %s", (minutos, envio))


def vencidas(db, limite=2):
    """O que o comando da agenda do banco (pg_cron) recebe: só o dono chama."""
    return [x for (x,) in db.execute("select * from radar_agenda_vencidas(%s)", (limite,)).fetchall()]


def situacao_envio(db, envio):
    return db.execute("select situacao, erro from radar_redes_envios where id = %s", (envio,)).fetchone()


def conferir(pid, canais=None, uid=EDITOR):
    with como("authenticated", uid) as c:
        return c.execute("select radar_pauta_conferir(%s, %s::text[])", (pid, canais)).fetchone()[0]["problemas"]


def mudar_por_fora(db, pid, sql):
    """Muda a peça direto no banco, com a marca das funções (como uma função faria): a versão que vai ao ar muda."""
    db.execute("select set_config('radar.pauta', '1', false)")
    try:
        db.execute(f"update radar_pauta_pecas set {sql} where id = %s", (pid,))
    finally:
        db.execute("select set_config('radar.pauta', '', false)")


def voltar_a_data(db, pid, dias):
    """Recua a data da peça sem mudar a versão aprovada (o gatilho fica desligado só nesta mudança): a agenda da semana fica velha."""
    db.execute("alter table radar_pauta_pecas disable trigger radar_tg_pauta_peca")
    try:
        db.execute("update radar_pauta_pecas set data = data - %s where id = %s", (dias, pid))
    finally:
        db.execute("alter table radar_pauta_pecas enable trigger radar_tg_pauta_peca")


def _linha(n, data, tipo="bastidor", formato="foto", **extra):
    return {"linha": n, "data": data, "tipo": tipo, "formato": formato, "assunto": "Bastidor da equipe", "quem_aparece": "Ana Teste",
            "objetivo": "aproximar", "observacao": "", **extra}


def importar(linhas, uid=EDITOR):
    with como("authenticated", uid) as c:
        return c.execute("select radar_pauta_importar(%s)", (json.dumps(linhas),)).fetchone()[0]


def test_pauta_configuracao_inicial_e_honorario_fora_da_agenda_das_redes(limpo):
    conf = dict(limpo.execute("select chave, valor from radar_config").fetchall())
    assert conf["pauta"] == {"agenda_ligada": True, "hora_padrao": "09:30", "janela_horas": 6, "hashtags": ["#Contabilidade", "#Palhoça"]}
    obrig = conf["obrigacoes"]
    assert [o["nome"] for o in obrig if o.get("redes") is False] == ["Honorário contábil"]
    # na instalação que já existe, o item ganha "redes": false sem mexer no resto; se o administrador já decidiu, fica como está
    sem = [{k: v for k, v in o.items() if k != "redes"} for o in obrig] + [{"nome": "Extra do escritório", "regra": "dia", "dia": 5}]
    try:
        limpo.execute("update radar_config set valor = %s where chave = 'obrigacoes'", (json.dumps(sem),))
        assert psql(SETUP).returncode == 0
        assert limpo.execute("select valor from radar_config where chave = 'obrigacoes'").fetchone()[0] == \
            obrig + [{"nome": "Extra do escritório", "regra": "dia", "dia": 5}]
        decidido = [dict(o, redes=True) if o["nome"] == "Honorário contábil" else o for o in sem]
        limpo.execute("update radar_config set valor = %s where chave = 'obrigacoes'", (json.dumps(decidido),))
        assert psql(SETUP).returncode == 0
        assert limpo.execute("select valor from radar_config where chave = 'obrigacoes'").fetchone()[0] == decidido
    finally:
        limpo.execute("update radar_config set valor = %s where chave = 'obrigacoes'", (json.dumps(obrig),))


def test_pauta_importar_cria_atualiza_so_planejadas_e_recusa_linha_errada_sem_conteudo(pauta):
    db = pauta
    linhas = [_linha(2, "2026-10-26", "reel", "reel"), _linha(3, "2026-10-27", "noticia", "imagem"), _linha(4, "2026-10-28", "quem_cuida", "foto")]
    assert importar(linhas) == {"novas": 3, "alteradas": 0, "iguais": 0, "mantidas": 0}
    assert db.execute("""select count(*), min(situacao), max(situacao), min(hora)::text, bool_and(criado_por = %s), max(quem_aparece)
                         from radar_pauta_pecas""", (EDITOR,)).fetchone() == (3, "planejada", "planejada", "09:30:00", True, "Ana Teste")
    assert db.execute("select count(*) from radar_pauta_pecas where cardinality(pessoas) > 0").fetchone()[0] == 0   # "quem aparece" não liga ninguém
    assert importar(linhas) == {"novas": 0, "alteradas": 0, "iguais": 3, "mantidas": 0}                          # importar de novo não duplica
    versao = db.execute("select versao_publicavel from radar_pauta_pecas where data = '2026-10-28'").fetchone()[0]
    # a peça que entrou em produção fica como está; a planejada é atualizada e continua planejada (a importação não a leva à produção)
    db.execute("update radar_pauta_pecas set chamada = 'Começou a produção' where data = '2026-10-26'")
    db.execute("""update radar_config set valor = valor || '{"hora_padrao": "08:15"}' where chave = 'pauta'""")
    linhas[0]["assunto"] = linhas[2]["assunto"] = "Outro assunto do plano"
    linhas[2]["formato"] = "carrossel_fotos"
    assert importar(linhas + [_linha(5, "2026-10-29", "educativo", "carrossel")], ADMIN) == {"novas": 1, "alteradas": 1, "iguais": 1, "mantidas": 1}
    assert db.execute("select situacao, assunto from radar_pauta_pecas where data = '2026-10-26'").fetchone() == ("em_producao", "Bastidor da equipe")
    s, f, a, v = db.execute("select situacao, formato, assunto, versao_publicavel from radar_pauta_pecas where data = '2026-10-28'").fetchone()
    assert (s, f, a) == ("planejada", "carrossel_fotos", "Outro assunto do plano") and v > versao
    assert db.execute("select hora::text from radar_pauta_pecas where data = '2026-10-29'").fetchone()[0] == "08:15:00"
    # o arquivo inteiro é conferido antes de gravar: o erro diz a linha e o campo, nunca o conteúdo
    antes = db.execute("select count(*), max(atualizado_em) from radar_pauta_pecas").fetchone()
    for ruim, msg in [([_linha(7, "2026-11-01"), _linha(8, "2026-11-02", tipo="Segredo <b>da equipe</b>")], "linha 8: tipo inválido"),
                      ([_linha(9, "2026-02-30")], "linha 9: data inválido"),
                      ([_linha(10, "01/11/2026")], "linha 10: data inválido"),
                      ([_linha(11, "2026-11-03", formato="tiktok")], "linha 11: formato inválido"),
                      ([_linha(12, "2026-11-04", assunto="Segredo " * 200)], "linha 12: assunto inválido"),
                      ([_linha(13, "2026-11-05", quem_aparece=["Segredo"])], "linha 13: quem_aparece inválido"),
                      ([_linha(14, "2026-11-06"), _linha(15, "2026-11-06")], "linha 15: data repetida"),
                      ([{"linha": 16, "data": "1999-12-31", "tipo": "reel", "formato": "reel"}], "linha 16: data inválido"),
                      (["Segredo solto"], "linha 1: linha inválido"),
                      ([_linha(17, "2026-11-07")] * 401, "de 1 a 400 linhas"), ([], "de 1 a 400 linhas")]:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR173") as erro:
            importar(ruim)
        assert msg in str(erro.value) and "Segredo" not in str(erro.value), str(erro.value)
    assert db.execute("select count(*), max(atualizado_em) from radar_pauta_pecas").fetchone() == antes          # nada foi gravado
    with como("authenticated", LEITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR159"):
        c.execute("select radar_pauta_importar(%s)", (json.dumps(linhas),))


def test_pauta_insert_e_patch_do_editor_nao_forjam_aprovacao_nem_links(pauta):
    db = pauta
    img = lamina(EDITOR)
    with como("authenticated", EDITOR) as c:
        r = c.execute("""insert into radar_pauta_pecas (data, tipo, formato, situacao, aprovado_por, aprovado_em, aprovado_modo,
                                                        aprovado_conferencias, artes, arte_identificacao, link_instagram, publicado_manual_em,
                                                        publicado_manual_por, versao_publicavel, criado_por, criado_em)
                         values ('2026-11-10', 'bastidor', 'foto', 'aprovada', %s, now(), 'agendar', '{pessoas}', %s::bigint[], 'x',
                                 'https://www.instagram.com/p/forjado/', '2026-11-10', %s, '2020-01-01', %s, '2020-01-01')
                         returning id, situacao, aprovado_por, aprovado_modo, aprovado_conferencias, artes, link_instagram, publicado_manual_em,
                                   publicado_manual_por, versao_publicavel > now() - interval '1 minute', criado_por::text,
                                   criado_em > now() - interval '1 minute'""", (ADMIN, [img], ADMIN, ADMIN)).fetchone()
        pid = r[0]
        assert r[1:] == ("planejada", None, None, [], [], None, None, None, True, EDITOR, True)
        antes = db.execute("select situacao, versao_publicavel, atualizado_em from radar_pauta_pecas where id = %s", (pid,)).fetchone()
        c.execute("""update radar_pauta_pecas set aprovado_por = %s, aprovado_em = now(), aprovado_modo = 'manual', artes = %s::bigint[],
                     arte_identificacao = 'x', link_facebook = 'https://www.facebook.com/forjado', publicado_manual_em = '2026-11-10',
                     publicado_manual_por = %s, versao_publicavel = '2020-01-01', criado_por = %s, criado_em = '2020-01-01' where id = %s""",
                  (ADMIN, [img], ADMIN, ADMIN, pid))
        assert db.execute("""select aprovado_por, aprovado_em, aprovado_modo, artes, arte_identificacao, link_facebook, publicado_manual_em,
                                    publicado_manual_por, criado_por::text, situacao, versao_publicavel from radar_pauta_pecas where id = %s""",
                          (pid,)).fetchone() == (None, None, None, [], None, None, None, None, EDITOR, "planejada", antes[1])
        for sit in ("pronta", "aprovada", "em_producao"):                                  # só as funções da Pauta fazem
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR159"):
                c.execute("update radar_pauta_pecas set situacao = %s where id = %s", (sit, pid))
        assert c.execute("delete from radar_pauta_pecas where id = %s", (pid,)).rowcount == 0     # apagar: só o administrador
    with como("authenticated", LEITOR) as c:
        assert c.execute("select count(*) from radar_pauta_pecas").fetchone()[0] == 1          # o leitor vê a Pauta, sem gravar
        assert c.execute("update radar_pauta_pecas set chamada = 'x' where id = %s", (pid,)).rowcount == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into radar_pauta_pecas (data, tipo, formato) values ('2026-11-11', 'bastidor', 'foto')")
    with como("authenticated", ADMIN) as c:
        assert c.execute("delete from radar_pauta_pecas where id = %s", (pid,)).rowcount == 1


def test_pauta_transicoes_permitidas_e_recusadas(pauta):
    db = pauta
    pid = db.execute("insert into radar_pauta_pecas (data, tipo, formato) values (%s, 'bastidor', 'imagem') returning id",
                     (hoje(db) + timedelta(days=3),)).fetchone()[0]
    sit = lambda: db.execute("select situacao from radar_pauta_pecas where id = %s", (pid,)).fetchone()[0]
    versao = lambda: db.execute("select versao_publicavel from radar_pauta_pecas where id = %s", (pid,)).fetchone()[0]
    v0 = versao()
    with como("authenticated", EDITOR) as c:
        upd = lambda sql: c.execute(f"update radar_pauta_pecas set {sql} where id = %s", (pid,))
        upd("assunto = 'só o plano', objetivo = 'aproximar'")
        assert (sit(), versao()) == ("planejada", v0)                                       # o plano não vai ao ar
        c.execute("update radar_pauta_pecas set chamada = 'Quem cuida da sua folha de pagamento', apoio = 'Uma conversa com a equipe.', "
                  "legenda_instagram = %s, conferidas = %s where id = %s",
                  (LEG_PECA, json.dumps([{"informacao": "A Artecon atende empresas", "fonte": "Site da Artecon"}]), pid))
        assert sit() == "em_producao" and versao() > v0                                      # mexeu no que vai ao ar: em produção
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR159"):
            upd("situacao = 'planejada'")
        upd("situacao = 'cancelada'")
        for sql, erro in [("chamada = 'Outra'", "RADAR162"), ("hora = '10:00'", "RADAR162"), ("situacao = 'em_producao'", "RADAR159")]:
            with pytest.raises(psycopg.errors.RaiseException, match=erro):
                upd(sql)
        upd("observacao = 'o plano e a sugestão mudam na cancelada', ia = '{\"versao\": 1}'")
        upd("situacao = 'planejada'")                                                       # Reabrir
        assert sit() == "planejada"
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR161"):
            c.execute("select radar_pauta_marcar_pronta(%s, now())", (pid,))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR160"):
            c.execute("select radar_pauta_marcar_pronta(999999, now())")
    marcar_pronta(db, pid)
    assert sit() == "pronta"
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR164"):
        marcar_pronta(db, pid)
    with como("authenticated", EDITOR) as c:
        upd = lambda sql: c.execute(f"update radar_pauta_pecas set {sql} where id = %s", (pid,))
        upd("hora = '11:00'")
        assert sit() == "pronta"                                                            # a hora não muda o conteúdo
        upd("apoio = 'Outro apoio da arte.'")
        assert sit() == "em_producao"
    marcar_pronta(db, pid)
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_pauta_pecas set situacao = 'em_producao' where id = %s", (pid,))   # "Voltar para produção"
        assert sit() == "em_producao"
    marcar_pronta(db, pid, ADMIN)
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_pauta_pecas set situacao = 'cancelada' where id = %s", (pid,))
        assert sit() == "cancelada"
    with como("authenticated", LEITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR159"):
        c.execute("select radar_pauta_marcar_pronta(%s, now())", (pid,))
    # com problema não fica pronta: a lista volta pela tela (radar_pauta_conferir), o erro só conta
    db.execute("update radar_pauta_pecas set situacao = 'planejada' where id = %s", (pid,))
    db.execute("update radar_pauta_pecas set legenda_instagram = 'Sem a linha legal, só o texto da legenda.' where id = %s", (pid,))
    with pytest.raises(psycopg.errors.RaiseException, match=r"RADAR165: há 1 ponto\(s\) a resolver"):
        marcar_pronta(db, pid)
    assert sit() == "em_producao"


def test_pauta_aprovada_nao_se_edita_mas_plano_e_ia_sim_sem_mudar_a_versao_publicavel(pauta):
    db = pauta
    pid, r = peca_aprovada(db)
    versao, lido = db.execute("select versao_publicavel, atualizado_em from radar_pauta_pecas where id = %s", (pid,)).fetchone()
    with como("authenticated", EDITOR) as c:
        for sql in ["chamada = 'Outra chamada'", "legenda_instagram = legenda_instagram || ' mais'", "hora = '07:00'", "data = data + 1",
                    "situacao = 'cancelada'", "situacao = 'pronta'", "conferidas = '[]'"]:
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR162"):
                c.execute(f"update radar_pauta_pecas set {sql} where id = %s", (pid,))
        c.execute("update radar_pauta_pecas set assunto = 'plano novo', observacao = 'lembrete', quem_aparece = 'Equipe' where id = %s", (pid,))
        novo = lido_peca(db, pid)
        assert c.execute("update radar_pauta_pecas set ia = %s where id = %s and atualizado_em = %s",
                         (json.dumps({"versao": 1, "arte": {"chamada": "Sugestão"}}), pid, novo)).rowcount == 1
    assert novo > lido                                                   # o plano muda a versão da tela, não a que vai ao ar
    assert db.execute("select situacao, versao_publicavel, atualizado_em, ia->'arte'->>'chamada' from radar_pauta_pecas where id = %s",
                      (pid,)).fetchone() == ("aprovada", versao, novo, "Sugestão")   # gravar a sugestão da IA não muda nem a versão da tela
    assert situacao_envio(db, r["envios"]["instagram"]) == ("autorizado", None)
    assert db.execute("select radar_pauta_pode_sair(%s)", (r["envios"]["instagram"],)).fetchone()[0] is None   # a aprovação vale


def test_pauta_desaprovar_editor_e_admin_cancela_envios_e_recusa_enviando_ou_publicado(pauta):
    db = pauta
    pid, r = peca_aprovada(db, canais=("instagram", "facebook"))
    with como("authenticated", LEITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR159"):
        c.execute("select radar_pauta_desaprovar(%s)", (pid,))
    with como("authenticated", EDITOR) as c:
        em = c.execute("select radar_pauta_desaprovar(%s)", (pid,)).fetchone()[0]
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR164"):                # já não está aprovada
            c.execute("select radar_pauta_desaprovar(%s)", (pid,))
    assert db.execute("""select situacao, aprovado_por, aprovado_em, aprovado_modo, aprovado_conferencias, artes, arte_identificacao, atualizado_em
                         from radar_pauta_pecas where id = %s""", (pid,)).fetchone() == ("pronta", None, None, None, [], [], None, em)
    assert db.execute("select situacao, erro, imagem, cancelado_por::text from radar_redes_envios where peca_id = %s order by id",
                      (pid,)).fetchall() == [("cancelado", "Aprovação desfeita na Pauta.", None, EDITOR)] * 2
    # aprovada de novo (o que caiu antes de sair não pede a caixa da rede): começou a sair, não desfaz; saiu, também não
    r = aprovar_peca(db, pid, canais=("instagram", "facebook"))
    ig, fb = r["envios"]["instagram"], r["envios"]["facebook"]
    vencer(db, ig)
    iniciar(ig)
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR169"):
        c.execute("select radar_pauta_desaprovar(%s)", (pid,))
    with como("service_role") as c:
        assert c.execute("select radar_rede_concluir(%s, true, '1789', 'https://www.instagram.com/p/abc/', %s, null)", (ig, URL_INTERNA)).fetchone()[0]
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR170"):
        c.execute("select radar_pauta_desaprovar(%s)", (pid,))
    # excluída da rede, desfaz: o Facebook que esperava a hora é cancelado; o Instagram fica como excluído
    with como("authenticated", ADMIN) as c:
        c.execute("select radar_rede_marcar_excluida(%s, 'manual')", (ig,))
        c.execute("select radar_pauta_desaprovar(%s)", (pid,))
    assert [situacao_envio(db, e)[0] for e in (ig, fb)] == ["excluido", "cancelado"]


def test_pauta_aprovar_so_admin_confere_versao_artes_conferencias_e_hora(pauta):
    db = pauta
    ana = nova_pessoa(db)
    pid = nova_peca(db, pessoas=[ana])
    marcar_pronta(db, pid)
    lido, boa = lido_peca(db, pid), lamina()
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR159"):
        c.execute(APROVAR, (pid, lido, ["instagram"], "agendar", [lamina(EDITOR)], IDENT, ["pessoas"]))
    velha = lamina()
    db.execute("update radar_imagens set criado_em = now() - interval '3 hours' where id = %s", (velha,))
    casos = [((999999, lido, ["instagram"], "agendar", [boa], IDENT, ["pessoas"]), "RADAR160"),
             ((pid, datetime.now(timezone.utc), ["instagram"], "agendar", [boa], IDENT, ["pessoas"]), "RADAR161"),
             ((pid, lido, ["instagram"], "depois", [boa], IDENT, ["pessoas"]), "RADAR164"),
             ((pid, lido, ["facebook"], "agendar", [boa], IDENT, ["pessoas"]), "RADAR165"),          # sem a legenda do Facebook
             ((pid, lido, [], "agendar", [boa], IDENT, ["pessoas"]), "RADAR165"),
             ((pid, lido, ["instagram"], "agendar", [boa], IDENT, ["datas"]), "RADAR166"),          # tem pessoa: falta a caixa
             ((pid, lido, ["instagram"], "agendar", [], IDENT, ["pessoas"]), "RADAR163"),
             ((pid, lido, ["instagram"], "agendar", [boa, lamina()], IDENT, ["pessoas"]), "RADAR163"),
             ((pid, lido, ["instagram"], "agendar", [lamina(EDITOR)], IDENT, ["pessoas"]), "RADAR163"),       # de outra pessoa
             ((pid, lido, ["instagram"], "agendar", [lamina(altura=1080)], IDENT, ["pessoas"]), "RADAR163"),  # não é 1080×1350
             ((pid, lido, ["instagram"], "agendar", [lamina(dados=PIXEL)], IDENT, ["pessoas"]), "RADAR163"),  # não é JPEG
             ((pid, lido, ["instagram"], "agendar", [velha], IDENT, ["pessoas"]), "RADAR163"),                # de mais de 2 horas
             ((pid, lido, ["instagram"], "agendar", [999999], IDENT, ["pessoas"]), "RADAR163"),
             ((pid, lido, ["instagram"], "agendar", [boa], "Artecon · CNPJ 99.999.999/0001-99", ["pessoas"]), "RADAR163")]
    with como("authenticated", ADMIN) as c:
        for args, erro in casos:
            with pytest.raises(psycopg.errors.RaiseException, match=erro):
                c.execute(APROVAR, args)
        r = c.execute(APROVAR, (pid, lido, ["instagram", "instagram"], "agendar", [boa], IDENT, ["pessoas", "datas", "outra"])).fetchone()[0]
    assert set(r) == {"agendado_para", "envios"} and set(r["envios"]) == {"instagram"}
    assert db.execute("""select situacao, aprovado_por::text, aprovado_modo, aprovado_conferencias, artes, arte_identificacao
                         from radar_pauta_pecas where id = %s""", (pid,)).fetchone() == ("aprovada", ADMIN, "agendar", ["datas", "pessoas"], [boa], IDENT)
    e = db.execute("""select e.peca_id, e.conteudo_id, e.canal, e.legenda, e.imagem, e.conteudo_lido_em = p.versao_publicavel, e.situacao,
                             e.autorizado_por::text, e.agendado_para = (p.data + p.hora) at time zone 'America/Sao_Paulo', e.junto_com_site, e.disparos
                      from radar_redes_envios e join radar_pauta_pecas p on p.id = e.peca_id where e.id = %s""", (r["envios"]["instagram"],)).fetchone()
    assert e == (pid, None, "instagram", LEG_PECA, LAMINA, True, "autorizado", ADMIN, True, False, 0)
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR164"):   # aprovada: não aprova de novo
        c.execute(APROVAR, (pid, lido_peca(db, pid), ["instagram"], "agendar", [lamina()], IDENT, ["pessoas"]))
    # a hora: passou há pouco, sai na próxima rodada; passou da janela, ou fica longe demais, não aprova
    agora = db.execute("select (now() at time zone 'America/Sao_Paulo') - interval '1 hour'").fetchone()[0]
    p2 = nova_peca(db, data=agora.date(), hora=agora.time())
    marcar_pronta(db, p2)
    assert db.execute("select %s::timestamptz > now() - interval '1 minute'", (aprovar_peca(db, p2)["agendado_para"],)).fetchone()[0]
    for dias, erro in [(-3, "RADAR167"), (130, "RADAR167")]:
        p3 = nova_peca(db, dias=dias)
        marcar_pronta(db, p3)
        with pytest.raises(psycopg.errors.RaiseException, match=erro):
            aprovar_peca(db, p3)
    p4 = nova_peca(db, dias=-2, tipo="agenda", conferidas=[{"informacao": "10/11 (ter) · ICMS", "fonte": "Agenda Tributária da Receita Federal"}])
    marcar_pronta(db, p4)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR168"):
        aprovar_peca(db, p4)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR166"):                      # a agenda pede "Conferi as datas"
        aprovar_peca(db, p4, modo="manual", conferencias=("pessoas",))
    # carrossel e reel saem à mão nesta versão
    p5 = nova_peca(db, dias=5, tipo="educativo", formato="carrossel", cartoes=[{"titulo": "Um", "texto": "Primeiro passo."}, {"titulo": "Dois", "texto": "Segundo passo."}])
    marcar_pronta(db, p5)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR164"):
        aprovar_peca(db, p5, artes=[lamina(), lamina(), lamina()])
    # já há publicação aberta no canal (só pelo SQL): não abre outra
    p6 = nova_peca(db, dias=6)
    marcar_pronta(db, p6)
    db.execute("""insert into radar_redes_envios (peca_id, canal, legenda, conteudo_lido_em, agendado_para)
                  values (%s, 'instagram', 'Legenda aberta por fora.', now(), now() + interval '1 day')""", (p6,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR170"):
        aprovar_peca(db, p6)
    assert db.execute("select situacao from radar_pauta_pecas where id = %s", (p6,)).fetchone()[0] == "pronta"    # nada ficou pela metade
    # o canal que caiu no meio do envio (pode ter saído) só volta com a caixa "Conferi no Instagram e no Facebook: não saiu"
    db.execute("update radar_redes_envios set situacao = 'cancelado', enviado_em = now() - interval '1 hour' where peca_id = %s", (p6,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR166"):
        aprovar_peca(db, p6)
    assert aprovar_peca(db, p6, conferencias=("rede", "pessoas"))["envios"]["instagram"]


def test_pauta_problemas_identificacao_marcas_confirmar_fonte_numeros_e_copia_paga(pauta, request):
    db = pauta
    pid = nova_peca(db)
    assert conferir(pid) == []
    assert conferir(pid, ["instagram", "facebook"]) == [
        "Legenda do Facebook: de 10 a 2.200 caracteres",
        "Legenda do Facebook: falta a linha de identificação (empresa, CNPJ e CRC de Configurações → Assinatura)"]
    db.execute("update radar_pauta_pecas set legenda_instagram = 'Sem a linha legal, só o texto da legenda.' where id = %s", (pid,))
    assert conferir(pid) == ["Legenda do Instagram: falta a linha de identificação (empresa, CNPJ e CRC de Configurações → Assinatura)"]
    db.execute("""update radar_config set valor = valor || '{"crc": ""}' where chave = 'assinatura'""")
    assert conferir(pid, ["instagram", "facebook"])[-1:] == ["Identificação legal incompleta: preencha o CNPJ e o CRC em Configurações → Assinatura"]
    db.execute("update radar_config set valor = valor || %s where chave = 'assinatura'", (json.dumps(ASSINATURA_PAUTA),))
    # varredura geral (v0.22.0): o registro no CRC inteiro (UF, número e categoria), não só os algarismos em qualquer ponto
    falta = "falta a linha de identificação (empresa, CNPJ e CRC de Configurações → Assinatura)"
    ident_sem_crc = "Artecon Artes Contábeis ME · CNPJ 11.222.333/0001-81 · "
    for texto, ok in [(IDENT, True), (ident_sem_crc + "CRC/SC 012345 / o-9", True), (ident_sem_crc + "crc sc-012345/O-9.", True),
                      (ident_sem_crc + "CRC-PR 012345/O-9", False), (ident_sem_crc + "CRC-SC 012345/0-9", False),
                      (ident_sem_crc + "CRC-SC 012345/O-5", False), (ident_sem_crc + "CRC-SC 012345/O-91", False),
                      (ident_sem_crc + "Fone 0123459", False), (ident_sem_crc + "CRC-SC 9012345/O-9", False)]:
        assert db.execute("select radar_pauta_identificacao_falta(%s)", (texto,)).fetchone()[0] == (None if ok else falta), texto
    for crc, padrao in [("CRC-SC 012345/O-9", "CRC-SC 012345/O-9"), ("SC-012345/0-9", "CRC-SC 012345/O-9"), ("012345/o-9", "CRC-SC 012345/O-9"),
                        ("1SC012345/0-9", "CRC 1SC012345/O-9"), ("CRC-SC 012345", "CRC-SC 012345")]:
        assert db.execute("select %s ~ radar_crc_padrao(%s)", (padrao, crc)).fetchone()[0], crc
    # rodada 2: o CRC das Configurações com letra acentuada (a tela aceita e escreve a linha como está) casa com a linha no texto,
    # com e sem o acento e com o acento separado da letra (NFD, colado do Mac); antes, "ORIGINÁRIO" virava "ORIGIN" + "RIO"
    db.execute("""update radar_config set valor = valor || '{"crc": "CRC-SC 012345/O-9 (Originário)"}' where chave = 'assinatura'""")
    for texto, ok in [(ident_sem_crc + "CRC-SC 012345/O-9 (Originário)", True), (ident_sem_crc + "CRC-SC 012345/O-9 (ORIGINARIO)", True),
                      (ident_sem_crc + "CRC-SC 012345/O-9 (Originário)", True), (ident_sem_crc + "CRC-SC 012345/O-9", False)]:
        assert db.execute("select radar_pauta_identificacao_falta(%s)", (texto,)).fetchone()[0] == (None if ok else falta), texto
    db.execute("update radar_config set valor = valor || %s where chave = 'assinatura'", (json.dumps(ASSINATURA_PAUTA),))
    # marca da IA, {confirmar}, fonte do boletim, informação sem texto e número que não está nas informações conferidas
    db.execute("""update radar_pauta_pecas set legenda_instagram = %s, apoio = 'O prazo vence [VERIFICAR: dia 20]', chamada = 'Atendemos 37 empresas',
                  conferidas = %s where id = %s""",
               (LEG_PECA + "\nPrazo: {confirmar data}", json.dumps([{"informacao": "Prazo do DAS no dia 20", "fonte": "Boletim ITC de outubro"},
                                                                   {"informacao": " ", "fonte": "Receita Federal"}]), pid))
    probs = conferir(pid)
    assert len(probs) == 5, probs
    assert probs[0].startswith("resolva antes de liberar: 1 ponto(s) marcado(s) com [VERIFICAR]")
    assert probs[1:] == ["Há {confirmar …} no texto: troque pela informação conferida (ou tire o trecho)",
                         "Informação conferida nº 1: use a fonte oficial (o boletim pago da ITC não é fonte)",
                         "Informação conferida nº 2: escreva a informação e a fonte (até 300 caracteres cada)",
                         "Números que não estão nas informações conferidas: 37. " + ACRESCENTE]    # o 20 está nelas; o CNPJ e o CRC da linha legal não contam
    db.execute("update radar_pauta_pecas set chamada = 'Atendemos 1.037 empresas desde 05/1984' where id = %s", (pid,))
    db.execute("update radar_pauta_pecas set apoio = '', legenda_instagram = %s, conferidas = %s where id = %s",
               (LEG_PECA, json.dumps([{"informacao": "1037 empresas atendidas desde 1984", "fonte": "Cadastro da Artecon (mês 5)"}]), pid))
    assert conferir(pid) == []                                       # 1.037 = 1037, 05 = 5
    # frase igual à do boletim pago (só sim ou não: o trecho não aparece); 11 palavras iguais não bastam
    carregar_fontes_novas(db, request)
    frase = "o comitê gestor publicou nesta semana a orientação completa sobre o novo prazo de entrega das declarações mensais"
    db.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo)
                  select id, 'https://boletim.exemplo/1', 'Boletim de mentira', %s, 'h-boletim-pauta' from radar_fontes where slug = 'itc-email'""",
               ("Texto de mentira do boletim: " + frase + ". Fim.",))
    palavras = frase.split()
    db.execute("update radar_pauta_pecas set legenda_instagram = %s where id = %s", ("Resumo: " + " ".join(palavras[:11]).upper() + "\n\n" + IDENT, pid))
    assert conferir(pid) == []
    db.execute("update radar_pauta_pecas set legenda_instagram = %s where id = %s", ("Resumo: " + " ".join(palavras[:12]).upper() + "\n\n" + IDENT, pid))
    probs = conferir(pid)
    assert probs == ["Há frase igual à do boletim pago (ITC): reescreva com palavras próprias"] and "comitê" not in json.dumps(probs, ensure_ascii=False)
    # varredura geral (v0.22.0): o boletim de mais de 90 dias também conta (antes, a frase de um boletim antigo passava sem aviso)
    db.execute("update radar_capturas set capturado_em = now() - interval '200 days' where hash_titulo = 'h-boletim-pauta'")
    assert conferir(pid) == ["Há frase igual à do boletim pago (ITC): reescreva com palavras próprias"]
    db.execute("update radar_pauta_pecas set legenda_instagram = %s, chamada = 'Quem cuida da sua folha', conferidas = %s where id = %s",
               (LEG_PECA, json.dumps([{"informacao": frase, "fonte": "Receita Federal"}]), pid))
    assert conferir(pid) == ["Há frase igual à do boletim pago (ITC): reescreva com palavras próprias"]   # nas conferidas também
    # a conferência que a radar-ia faz antes de chamar a IA (o plano e as conferidas): só sim ou não, só para quem edita a Pauta
    with como("authenticated", EDITOR) as c:
        assert c.execute("select radar_pauta_copia_paga_ia(%s)", (["Resumo: " + " ".join(palavras[:12])],)).fetchone()[0] is True
        assert c.execute("select radar_pauta_copia_paga_ia(%s)", (["Resumo: " + " ".join(palavras[:11])],)).fetchone()[0] is False
    for uid in (LEITOR, SEM_PERFIL):
        with como("authenticated", uid) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR159"):
            c.execute("select radar_pauta_copia_paga_ia(%s)", (["Resumo: " + " ".join(palavras[:12])],))
    # "(conferir)": a marca provisória de que falta conferir não vai ao ar, nem na fonte, nem no texto ("Fonte: …" no fim da legenda)
    regra = "Regra de vencimento das Configurações (conferir)"
    db.execute("update radar_pauta_pecas set legenda_instagram = %s, conferidas = %s where id = %s",
               (LEG_PECA, json.dumps([{"informacao": "O DAS vence no dia 20", "fonte": regra}]), pid))
    assert conferir(pid) == ["Informação conferida nº 1: troque “(conferir)” pela fonte oficial em que a informação foi conferida"]
    db.execute("update radar_pauta_pecas set legenda_instagram = %s where id = %s", ("O DAS vence no dia 20.\n\nFonte: " + regra + "\n\n" + IDENT, pid))
    assert conferir(pid) == ["Há “(conferir)” no texto: confira na fonte oficial e tire a marca",
                             "Informação conferida nº 1: troque “(conferir)” pela fonte oficial em que a informação foi conferida"]
    db.execute("update radar_pauta_pecas set legenda_instagram = %s, conferidas = %s where id = %s",
               ("O DAS vence no dia 20.\n\nFonte: Agenda Tributária da Receita Federal\n\n" + IDENT,
                json.dumps([{"informacao": "O DAS vence no dia 20", "fonte": "Agenda Tributária da Receita Federal"}]), pid))
    assert conferir(pid) == []
    # o carrossel de fotos: o cartão que passa do número de fotos não aparece em lâmina nenhuma
    fotos = [nova_imagem(), nova_imagem()]
    tres = [{"titulo": "", "texto": "Primeira foto."}, {"titulo": "", "texto": "Segunda foto."}, {"titulo": "", "texto": "Sem foto."}]
    car = nova_peca(db, dias=9, tipo="bastidor", formato="carrossel_fotos", fotos=fotos, cartoes=tres)
    assert conferir(car) == ["Carrossel de fotos: o cartão nº 3 não tem foto (a peça tem 2): tire o cartão ou envie mais uma foto"]
    db.execute("update radar_pauta_pecas set cartoes = %s where id = %s", (json.dumps(tres[:2]), car))
    assert conferir(car) == []
    # o que cada tipo e formato pede
    for i, (tipo, formato, extra, msg) in enumerate([
            ("noticia", "imagem", {}, "Dia de notícia: publique por Assuntos ou Publicações"),
            ("sem_post", "story", {}, "Sem publicação pela Pauta nesta versão"),
            ("quem_cuida", "imagem", {}, "Quem cuida: marque a pessoa em Quem aparece"),
            ("bastidor", "foto", {}, "Foto: envie a foto da peça"),
            ("educativo", "carrossel", {"cartoes": [{"titulo": "Um", "texto": "Só um cartão."}]}, "Carrossel: escreva de 2 a 9 cartões"),
            ("educativo", "carrossel", {"cartoes": [{"titulo": "Um"}, "texto solto"]}, "Cartão nº 2: título e texto em formato inválido"),
            ("bastidor", "carrossel_fotos", {}, "Carrossel de fotos: envie de 2 a 10 fotos"),
            ("reel", "reel", {}, "Reel: cole o roteiro"),
            ("agenda", "imagem", {"conferidas": []}, "Agenda da semana: calcule a agenda e confira as datas (Informações conferidas)")]):
        assert msg in conferir(nova_peca(db, dias=10 + i, tipo=tipo, formato=formato, **extra)), (tipo, formato)
    with como("authenticated", LEITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR159"):
        c.execute("select radar_pauta_conferir(%s, null)", (pid,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR160"):
        conferir(999999)


def test_pauta_termo_sem_futuro_vencido_revogado_canal_uso_e_inativa(pauta):
    db = pauta
    d = date(2026, 11, 10)
    casos = {"pessoa não cadastrada": 999999,
             "pessoa inativa": nova_pessoa(db, "Inativa Teste", "Inativa", ativo=False),
             "sem termo assinado": nova_pessoa(db, "Semtermo Teste", "Semtermo", assinado=None),
             "termo assinado depois desta data": nova_pessoa(db, "Futuro Teste", "Futuro", assinado="2026-11-11"),
             "termo revogado": nova_pessoa(db, "Revogada Teste", "Revogada", revogado="2026-11-10"),
             "termo vencido": nova_pessoa(db, "Vencida Teste", "Vencida", ate="2026-11-09"),
             "canal não autorizado no termo": nova_pessoa(db, "Canal Teste", "Canal", canais=("facebook",)),
             "finalidade não autorizada no termo": nova_pessoa(db, "Finalidade Teste", "Finalidade", usos=("orientacao",))}
    olga = nova_pessoa(db, "Certa Teste", "Certa", revogado="2026-11-11", ate="2026-11-10")      # revogada só depois; vale até o dia
    with como("authenticated", EDITOR) as c:
        termo = lambda pessoa, tipo="bastidor", canal="instagram": c.execute("select radar_pauta_termo_ok(%s, %s, %s, %s)",
                                                                             (pessoa, tipo, canal, d)).fetchone()[0]
        assert {motivo: termo(pessoa) for motivo, pessoa in casos.items()} == {motivo: motivo for motivo in casos}
        assert termo(olga) is None and termo(olga, canal="facebook") is None
        assert termo(casos["finalidade não autorizada no termo"], tipo="educativo") is None   # orientação: autorizada no termo
        assert termo(olga, tipo="sem_post") == "finalidade não autorizada no termo" and termo(olga, canal="tiktok") == "canal não autorizado no termo"
    with como("authenticated", LEITOR) as c:                                                 # o leitor não lê as pessoas
        assert c.execute("select radar_pauta_termo_ok(%s, 'bastidor', 'instagram', %s)", (olga, d)).fetchone()[0] == "pessoa não cadastrada"
    vera = casos["termo vencido"]
    pid = nova_peca(db, data=d, pessoas=[olga, vera])
    with como("authenticated", EDITOR) as c:
        assert c.execute("""select pessoa_id, nome_na_peca, motivo_instagram, motivo_facebook from radar_v_pauta_pessoas where peca_id = %s
                            order by pessoa_id""", (pid,)).fetchall() == sorted([(vera, "Vencida", "termo vencido", "termo vencido"), (olga, "Certa", None, None)])
    with como("authenticated", LEITOR) as c:
        assert c.execute("select count(*) from radar_v_pauta_pessoas").fetchone()[0] == 0
    for papel in ("service_role", "anon"):
        with como(papel) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select * from radar_v_pauta_pessoas")
    assert "“Vencida” (Instagram): termo vencido" in conferir(pid)
    # pessoa nova na peça: cadastrada, ativa e uma vez só; a foto existe. Quem já estava fica, mesmo inativa (a lista avisa)
    for sql, args in [("pessoas = pessoas || %s::bigint", casos["pessoa inativa"]), ("pessoas = pessoas || %s::bigint", 999999),
                      ("pessoas = pessoas || %s::bigint", olga), ("fotos = array[%s::bigint]", 999999)]:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR176"):
            db.execute(f"update radar_pauta_pecas set {sql} where id = %s", (args, pid))
    db.execute("update radar_pessoas set ativo = false where id = %s", (olga,))
    db.execute("update radar_pauta_pecas set chamada = 'Quem cuida da sua folha' where id = %s", (pid,))
    assert "“Certa” (Instagram): pessoa inativa" in conferir(pid)


def test_pauta_nome_sem_marcar_sobrenome_nao_autorizado_e_contador_sem_registro(pauta):
    db = pauta
    ana = nova_pessoa(db, "Ana Teste", "Ana")                                                    # sem registro
    bruno = nova_pessoa(db, "Bruno Exemplo", "Bruno Exemplo", categoria="contador", crc="CRC-SC 054321/O-1")
    carla = nova_pessoa(db, "Carla Modelo", "Carla", categoria="tecnica", crc="CRC-SC 067890/T-2")
    nova_pessoa(db, "Élio D'Exemplo (Teste)", "Élio", ativo=False)                                  # inativo e com sinais no nome
    pid = nova_peca(db, pessoas=[ana])

    def com(texto, pessoas=None):
        db.execute("update radar_pauta_pecas set apoio = %s, pessoas = coalesce(%s::bigint[], pessoas) where id = %s", (texto, pessoas, pid))
        return conferir(pid)
    assert com("Uma conversa com a Ana, do Departamento Pessoal.") == []
    assert com("Uma conversa com a Ana Teste.") == ["O termo autoriza só “Ana”: tire o sobrenome"]
    assert com("A Ana conversa com o Bruno.") == ["“Bruno” aparece no texto e não está marcada em Quem aparece"]
    assert com("A Ana conversa com o Élio.") == ["“Élio” aparece no texto e não está marcada em Quem aparece"]   # inativo também
    assert com("A Ana fala dos Brunoni e o bruno da história.") == []                                         # palavra inteira, com a maiúscula
    assert com("A Ana, nossa contadora, explica.") == \
        ["“Ana” não tem registro no CRC (Pauta → Pessoas e termos): não chame de contador(a) nem de técnico(a)"]
    assert com("Técnica em contabilidade, a Ana explica.") == \
        ["“Ana” não tem registro no CRC (Pauta → Pessoas e termos): não chame de contador(a) nem de técnico(a)"]
    assert com("A Ana explica como funciona a folha de pagamento da sua empresa, e a contadora responsável confere.") == []   # longe do nome
    assert com("A Carla, contadora da equipe, explica.", [ana, carla]) == ["“Carla” é técnico(a) em contabilidade: não chame de contador(a)"]
    assert com("A Carla, técnica em contabilidade, explica.") == []
    assert com("O Bruno Exemplo, contador, explica.", [ana, bruno]) == []
    assert com("O Bruno Exemplo é especialista em folha.") == \
        ["“especialista” perto de “Bruno Exemplo”: não há título de especialista registrado, tire a palavra"]



def test_pauta_nome_sem_acento_em_caixa_alta_ou_nfd_tambem_trava(pauta):
    """O nome cadastrado é achado no texto sem diferença de acento, de forma Unicode (o texto colado do Mac vem em NFD) e também em
    caixa alta (a chamada da arte): na pessoa não marcada, no sobrenome que o termo não autoriza e no "contador" de quem não tem
    registro. O nome em minúsculas (uma palavra comum) não trava: para isso, a aprovação pede sempre a caixa das pessoas."""
    import unicodedata
    db = pauta
    nova_pessoa(db, "Lúcia Exemplo", "Lúcia", revogado="2026-01-01")                           # termo revogado, não marcada
    bruno = nova_pessoa(db, "Bruno Silvano", "Bruno")                                           # sem registro; o termo autoriza só "Bruno"
    pid = nova_peca(db, dias=3, tipo="educativo", formato="imagem")

    def com(texto, pessoas=()):
        db.execute("update radar_pauta_pecas set apoio = %s, pessoas = %s::bigint[] where id = %s", (texto, list(pessoas), pid))
        return conferir(pid)
    lucia = ["“Lúcia” aparece no texto e não está marcada em Quem aparece"]
    for texto in ["Dica da Lúcia: confira o prazo.", "Dica da Lucia: confira o prazo.", "DICA DA LÚCIA: CONFIRA O PRAZO.",
                  "DICA DA LUCIA", unicodedata.normalize("NFD", "Dica da Lúcia: confira o prazo.")]:
        assert com(texto) == lucia, texto
    assert com("Dica da lúcia: confira o prazo.") == []                                         # minúscula: palavra comum
    assert com("A Luciana explica o prazo.") == []                                               # palavra inteira
    sobrenome = ["O termo autoriza só “Bruno”: tire o sobrenome"]
    for texto in ["Conheça o Bruno Silvano.", "CONHEÇA O BRUNO SILVANO", "Conheça o Bruno Sílvano."]:
        assert com(texto, [bruno]) == sobrenome, texto
    contador = ["“Bruno” não tem registro no CRC (Pauta → Pessoas e termos): não chame de contador(a) nem de técnico(a)"]
    for texto in ["Conheça o Bruno, contador da Artecon.", "CONHEÇA O BRUNO, CONTADOR DA ARTECON", "conheça o bruno, contador da artecon",
                  unicodedata.normalize("NFD", "TÉCNICO EM CONTABILIDADE, O BRÚNO EXPLICA")]:
        assert com(texto, [bruno]) == contador, texto
    # a aprovação pede a caixa "Conferi: … só aparecem as pessoas marcadas" em toda peça, mesmo sem pessoa marcada e sem foto
    com("Dica da lúcia: confira o prazo.")
    marcar_pronta(db, pid)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR166"):
        aprovar_peca(db, pid, conferencias=())
    assert aprovar_peca(db, pid, conferencias=("pessoas",))["envios"]["instagram"]


def test_pauta_numeros_aceitam_o_crc_da_pessoa_o_telefone_e_os_fatos_fixos(pauta):
    """O número que já está conferido fora da peça não precisa virar informação conferida: o registro no CRC da pessoa marcada (ao lado
    de "contador"), os telefones do Fale Conosco e os "fatos_fixos" da Pauta (com a fonte). O resto aparece como está escrito, com o
    que fazer."""
    db = pauta
    bruno = nova_pessoa(db, "Bruno Exemplo", "Bruno Exemplo", categoria="contador", crc="CRC-SC 054321/O-1")
    leg = ("Conheça o Bruno Exemplo, contador · CRC-SC 054321/O-1.\nA Artecon atende empresas desde 1984.\n"
           "Fale com a gente: (48) 3242-0530.\n\n" + IDENT + "\n\n#Contabilidade")
    pid = nova_peca(db, dias=3, pessoas=[bruno], legenda_instagram=leg)
    fale = db.execute("select valor from radar_config where chave = 'fale_conosco'").fetchone()[0]
    db.execute("""update radar_config set valor = '{"setores": [{"rotulo": "Geral", "telefones": [{"numero": "48-3242-0530", "whatsapp": true}],
                  "emails": [], "equipe": []}]}' where chave = 'fale_conosco'""")
    try:
        assert conferir(pid) == ["Números que não estão nas informações conferidas: 1984. " + ACRESCENTE]
        fixos = [{"informacao": "A Artecon atende empresas desde 1984", "fonte": "Contrato social da Artecon"}]
        db.execute("update radar_config set valor = valor || %s where chave = 'pauta'", (json.dumps({"fatos_fixos": fixos}),))
        assert conferir(pid) == []
        db.execute("""update radar_config set valor = valor || '{"fatos_fixos": [{"informacao": "desde 1984", "fonte": " "}, "1984"]}'
                      where chave = 'pauta'""")                                                  # sem a fonte, não vale
        assert conferir(pid) == ["Números que não estão nas informações conferidas: 1984. " + ACRESCENTE]
        db.execute("update radar_config set valor = valor || %s where chave = 'pauta'", (json.dumps({"fatos_fixos": fixos}),))
        # o telefone que não está no Fale Conosco aparece como está escrito (com o zero à esquerda); o do responsável vale
        db.execute("""update radar_config set valor = '{"setores": [{"rotulo": "Geral", "telefones": ["48-3033-4978"], "emails": [], "equipe": []}]}'
                      where chave = 'fale_conosco'""")
        assert conferir(pid) == ["Números que não estão nas informações conferidas: 0530, 3242. " + ACRESCENTE]
        db.execute("""update radar_config set valor = '{"setores": [{"rotulo": "Contábil", "telefones": [], "emails": [], "equipe": [],
                      "responsaveis": [{"nome": "Responsável de mentira", "telefone": "(48) 3242-0530"}]}]}' where chave = 'fale_conosco'""")
        assert conferir(pid) == []
        # o CRC só vale da pessoa marcada
        db.execute("update radar_pauta_pecas set pessoas = '{}' where id = %s", (pid,))
        assert "Números que não estão nas informações conferidas: 054321. " + ACRESCENTE in conferir(pid)
    finally:
        db.execute("update radar_config set valor = %s where chave = 'fale_conosco'", (json.dumps(fale),))


def test_pauta_marcador_do_modelo_entre_chaves_trava_em_todo_texto_e_na_saida(pauta):
    """Os modelos do plano têm marcadores entre chaves ({formação}, {ano de entrada}, {frase da pessoa}); esquecido, iria ao ar escrito
    assim. Trava na lista (legendas, chamada, apoio, cartões, roteiro), ao publicar agora, antes de sair pela agenda e ao copiar à mão."""
    db = pauta
    msg = "Há marcador do modelo entre chaves ({…}): troque pelo texto ou tire"
    for i, (campo, valor) in enumerate([("legenda_instagram", "Formação: {formação}.\n\n" + IDENT), ("chamada", "Desde {ano de entrada} na Artecon"),
                                        ("apoio", "Uma frase de {PESSOA2}."), ("cartoes", [{"titulo": "{tarefa 1 — ex.: abertura}", "texto": "x"}]),
                                        ("roteiro", "| 0 a 3 s | {frase do Bruno} |")]):
        assert conferir(nova_peca(db, dias=20 + i, **{campo: valor})) == [msg], campo
    pid = nova_peca(db, dias=3)
    db.execute("update radar_pauta_pecas set apoio = 'Prazo: {confirmar data}' where id = %s", (pid,))   # o {confirmar} tem a mensagem dele
    assert conferir(pid) == ["Há {confirmar …} no texto: troque pela informação conferida (ou tire o trecho)"]
    db.execute("update radar_pauta_pecas set apoio = 'Chaves vazias, {}, não são marcador' where id = %s", (pid,))
    assert conferir(pid) == []
    # depois de aprovada (a legenda congelada no envio, mudada por fora): não sai pela agenda, nem pelo Publicar agora
    p2, r2 = peca_aprovada(db, dias=4)
    e2 = r2["envios"]["instagram"]
    db.execute("update radar_redes_envios set legenda = legenda || ' {formação}' where id = %s", (e2,))
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR165: .*marcador entre chaves"):
        c.execute("select radar_pauta_publicar_agora(%s, false)", (p2,))
    vencer(db, e2)
    motivo = "A legenda tem ponto marcado com [VERIFICAR], {confirmar} ou outro marcador entre chaves: desfaça a aprovação e corrija."
    assert iniciar(e2) == {"erro": motivo}
    # à mão: a cópia da legenda e do roteiro confere de novo
    ana = pessoa_do_corretor(db)                                                 # v0.22.0: o reel sai com o vídeo corrigido
    p3 = nova_peca(db, dias=5, tipo="reel", formato="reel", roteiro=FALA_REEL + "\n" + IDENT, pessoas=[ana],
                   conferidas=[{"informacao": "O prazo vence no dia 20", "fonte": "Receita Federal"}])
    video_pronto(db, p3, ana)
    marcar_pronta(db, p3)
    aprovar_peca(db, p3, modo="manual", artes=[], conferencias=("pessoas", "video"), video=SHA_VIDEO)
    with como("authenticated", EDITOR) as c:
        assert c.execute("select radar_pauta_pode_copiar(%s, %s, null)", (p3, lido_peca(db, p3))).fetchone()[0]["ok"] is True
    mudar_por_fora(db, p3, "roteiro = roteiro || ' {nome}', legenda_instagram = legenda_instagram || ' {Nome}'")
    copiar = "O texto aprovado tem ponto marcado com [VERIFICAR], {confirmar} ou outro marcador entre chaves: desfaça a aprovação e corrija."
    with como("authenticated", EDITOR) as c:
        for canal in (None, "instagram"):
            assert c.execute("select radar_pauta_pode_copiar(%s, %s, %s)", (p3, lido_peca(db, p3), canal)).fetchone()[0] == {"motivo": copiar}


def test_pauta_roteiro_sem_as_marcacoes_de_tempo_e_lista_da_agenda_conferida(pauta):
    """O roteiro do reel colado como o plano manda (a tabela com o tempo de cada cena e a duração) fica pronto: as marcações de tempo
    não são fato. Na Agenda da semana em Imagem 4:5, a lista desenhada na lâmina (a informação de cada conferida) vai ao ar e passa
    pelas travas de [VERIFICAR], {confirmar}, chaves e nome."""
    db = pauta
    roteiro = ("Duração: cerca de 44 segundos (cerca de 110 palavras).\nGancho (0 a 3 s)\n| Tempo | Fala | Texto na tela |\n"
               "| 0 a 3 s | \"Sexta tem prazo.\" | PRAZO ATÉ SEXTA, 30/10 |\n| 3 a 12 s | \"Toda segunda, um assunto.\" | Tarja |\n"
               "| 12–32s | \"Quem pediu tem até sexta, dia 30.\" | 0:15 a 0:32 |\n| 32 a 44 s | \"Fale com a gente.\" | cartela |\n" + IDENT)
    pid = nova_peca(db, dias=3, tipo="reel", formato="reel", roteiro=roteiro,
                    conferidas=[{"informacao": "Prazo da opção até 30/10", "fonte": "Portal do Simples Nacional"}])
    sem_video = "Reel: envie a gravação (Corretor de vídeo)"                     # v0.22.0: o reel só fica pronto com o vídeo
    assert conferir(pid) == [sem_video]
    db.execute("update radar_pauta_pecas set roteiro = roteiro || %s where id = %s", ("\n| 44 a 50 s | \"São 2 sócios e 15 dias.\" | |", pid))
    assert conferir(pid) == [sem_video, "Números que não estão nas informações conferidas: 15, 2. " + ACRESCENTE]
    # a lista da agenda: a pessoa cadastrada e não marcada, a marca e as chaves
    nova_pessoa(db, "Márcia Exemplo", "Márcia", revogado="2026-01-01")
    lista = [{"informacao": "10/11 (ter) · ICMS [VERIFICAR: data]", "fonte": "Agenda Tributária da Receita Federal"},
             {"informacao": "11/11 (qua) · Aniversário da Márcia {confirmar}", "fonte": "Agenda Tributária da Receita Federal"},
             {"informacao": "12/11 (qui) · Entrega da {obrigação}", "fonte": "Agenda Tributária da Receita Federal"}]
    ag = nova_peca(db, dias=4, tipo="agenda", formato="imagem", conferidas=lista)
    probs = conferir(ag)
    assert probs[0].startswith("resolva antes de liberar: 1 ponto(s) marcado(s) com [VERIFICAR]"), probs
    assert probs[1:] == ["Há {confirmar …} no texto: troque pela informação conferida (ou tire o trecho)",
                         "Há marcador do modelo entre chaves ({…}): troque pelo texto ou tire",
                         "“Márcia” aparece no texto e não está marcada em Quem aparece"]
    db.execute("update radar_pauta_pecas set formato = 'foto', fotos = array[%s::bigint] where id = %s", (nova_imagem(), ag))
    assert conferir(ag) == []                                                                     # na foto, a lista não é desenhada


def test_pauta_iniciar_na_hora_uma_vez_e_problemas_viram_erro_sem_nome(pauta):
    db = pauta
    pid, r = peca_aprovada(db)
    ig = r["envios"]["instagram"]
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR172"):                       # ainda não é a hora: nada muda
        iniciar(ig)
    assert situacao_envio(db, ig) == ("autorizado", None)
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("select radar_pauta_iniciar(%s)", (ig,))                                       # só a função radar-redes (papel interno)
    vencer(db, ig)
    e = iniciar(ig)
    assert (e["canal"], e["peca_id"], e["conteudo_id"], e["legenda"], e["imagem"], e["imagem_url"]) == ("instagram", pid, None, LEG_PECA, LAMINA, None)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR138"):                       # já está saindo: nunca duas vezes
        iniciar(ig)
    with como("service_role") as c:
        assert c.execute("select radar_rede_concluir(%s, false, null, null, %s, 'Meta recusou')", (ig, URL_INTERNA)).fetchone()[0]
    assert db.execute("select situacao, imagem, imagem_url from radar_redes_envios where id = %s", (ig,)).fetchone() == ("erro", None, URL_INTERNA)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR138"):                       # "erro" só volta pelo administrador
        iniciar(ig)
    with como("authenticated", ADMIN) as c:
        assert c.execute("select radar_pauta_publicar_agora(%s, true)", (pid,)).fetchone()[0] == [ig]
    e = iniciar(ig)
    assert e["imagem"] is None and e["imagem_url"] == URL_INTERNA                              # a nova tentativa usa o endereço interno
    with como("service_role") as c:
        assert c.execute("select radar_rede_concluir(%s, true, '1789', 'https://www.instagram.com/p/abc/', %s, null)", (ig, URL_INTERNA)).fetchone()[0]
    assert db.execute("select situacao, url, imagem_url from radar_redes_envios where id = %s", (ig,)).fetchone() == \
        ("publicado", "https://www.instagram.com/p/abc/", URL_INTERNA)
    # o que impede vira "erro" (contado e avisado), com o motivo e sem nome
    ana = nova_pessoa(db, "Ana Teste", "Ana")
    p2, r2 = peca_aprovada(db, dias=3)
    e2 = r2["envios"]["instagram"]
    db.execute("update radar_redes_envios set agendado_para = now() - interval '7 hours' where id = %s", (e2,))
    p3, r3 = peca_aprovada(db, dias=4)
    e3 = r3["envios"]["instagram"]
    vencer(db, e3)
    mudar_por_fora(db, p3, "chamada = 'Mudou por fora'")
    p4, r4 = peca_aprovada(db, dias=5, pessoas=[ana])
    e4 = r4["envios"]["instagram"]
    vencer(db, e4)
    db.execute("update radar_pessoas set termo_revogado_em = radar_pauta_hoje() where id = %s", (ana,))
    p5, r5 = peca_aprovada(db, dias=1, tipo="agenda", conferidas=[{"informacao": "10/11 (ter) · ICMS", "fonte": "Agenda Tributária da Receita Federal"}])
    e5 = r5["envios"]["instagram"]
    vencer(db, e5)
    voltar_a_data(db, p5, 3)
    p6, r6 = peca_aprovada(db, dias=6)
    e6 = r6["envios"]["instagram"]
    vencer(db, e6)
    db.execute("update radar_redes_envios set imagem = null where id = %s", (e6,))
    esperado = {e2: "Passaram mais de 6 horas da hora marcada: a publicação não sai atrasada sozinha. Use Publicar agora ou desfaça a aprovação.",
                e3: "A peça mudou depois de aprovada: confira e aprove de novo.",
                e4: "O termo de uso de imagem de uma pessoa da peça não vale em " + hoje(db).strftime("%d/%m/%Y") +
                    " (termo revogado): confira em Pauta → Pessoas e termos.",
                e5: "A agenda da semana ficou velha (passou a segunda-feira).",
                e6: "A imagem da publicação se perdeu: desfaça a aprovação e aprove de novo."}
    for envio, motivo in esperado.items():
        assert iniciar(envio) == {"erro": motivo}
        assert situacao_envio(db, envio) == ("erro", motivo)
    assert db.execute("select count(*) from radar_redes_envios where erro like '%Ana%'").fetchone()[0] == 0


def test_iniciar_antigo_recusa_envio_da_pauta_sem_mudar_nada(pauta):
    db = pauta
    pid, r = peca_aprovada(db)
    ig = r["envios"]["instagram"]
    vencer(db, ig)
    estado = "select situacao, disparos, erro, enviado_em, atualizado_em from radar_redes_envios where id = %s"
    antes = db.execute(estado, (ig,)).fetchone()
    with como("service_role") as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR171"):
        c.execute("select radar_rede_iniciar(%s)", (ig,))                                         # a radar-redes de antes da v0.21.0
    assert db.execute(estado, (ig,)).fetchone() == antes
    # a notícia continua saindo pelo caminho de antes, e nunca pelo início da Pauta
    a, c1 = cenario_publicavel(db)
    aprovar(c1)
    registrar_site(c1)
    with como("authenticated", ADMIN) as c:
        envio = c.execute("select radar_autorizar_rede(%s, 'instagram', %s, %s, %s)", (c1, LEGENDA, IMG, _lido(db, c1))).fetchone()[0]
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR138"):
        iniciar(envio)
    with como("service_role") as c:
        assert c.execute("select radar_rede_iniciar(%s)", (envio,)).fetchone()[0]["conteudo_id"] == c1


def test_agenda_vencidas_espera_10_min_3_tentativas_janela_e_confere_antes_de_disparar(pauta):
    db = pauta
    pid, r = peca_aprovada(db, canais=("instagram", "facebook"))
    ig, fb = r["envios"]["instagram"], r["envios"]["facebook"]
    assert vencidas(db) == []                                                                  # ainda não é a hora
    vencer(db, ig, 5)
    vencer(db, fb, 1)
    assert vencidas(db, 1) == [ig]                                                             # a mais antiga primeiro, até o limite
    assert vencidas(db) == [fb]                                                                # a outra: a primeira foi chamada há pouco
    assert vencidas(db) == []                                                                  # espera 10 minutos entre as chamadas
    assert db.execute("select disparos, disparado_em > now() - interval '1 minute', situacao from radar_redes_envios where id = %s",
                      (ig,)).fetchone() == (1, True, "autorizado")
    for _ in range(2):
        db.execute("update radar_redes_envios set disparado_em = now() - interval '11 minutes' where id = %s", (ig,))
        assert vencidas(db) == [ig]
    db.execute("update radar_redes_envios set disparado_em = now() - interval '11 minutes' where id = %s", (ig,))
    assert vencidas(db) == []                                                                  # 3 chamadas sem publicar: vira "erro"
    sit, erro = situacao_envio(db, ig)
    assert sit == "erro" and erro.startswith("A publicação agendada não saiu: o Radar chamou a função radar-redes 3 vezes, de 10 em 10 minutos")
    # "erro" e "enviando" nunca são pegos de novo
    db.execute("update radar_redes_envios set disparado_em = now() - interval '11 minutes' where id = %s", (fb,))
    iniciar(fb)
    db.execute("update radar_redes_envios set disparado_em = now() - interval '1 hour' where peca_id = %s", (pid,))
    assert vencidas(db, 10) == []
    # o que não pode sair vira "erro" antes de qualquer pedido à função (aqui: a peça mudou por fora)
    p2, r2 = peca_aprovada(db, dias=3)
    e2 = r2["envios"]["instagram"]
    vencer(db, e2)
    mudar_por_fora(db, p2, "chamada = 'Mudou por fora'")
    assert vencidas(db) == [] and situacao_envio(db, e2) == ("erro", "A peça mudou depois de aprovada: confira e aprove de novo.")
    assert db.execute("select disparos from radar_redes_envios where id = %s", (e2,)).fetchone()[0] == 0
    # a notícia autorizada nunca é pega pela agenda
    a, c1 = cenario_publicavel(db)
    aprovar(c1)
    registrar_site(c1)
    with como("authenticated", ADMIN) as c:
        c.execute("select radar_autorizar_rede(%s, 'instagram', %s, %s, %s)", (c1, LEGENDA, IMG, _lido(db, c1)))
    assert vencidas(db, 10) == []
    # ninguém além do dono (o comando do pg_cron) chama
    for papel, uid in (("authenticated", ADMIN), ("service_role", None), ("anon", None)):
        with como(papel, uid) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select * from radar_agenda_vencidas(2)")


def test_agenda_vencidas_duas_conexoes_nao_pegam_o_mesmo_envio(pauta):
    import threading
    db = pauta
    envios = [peca_aprovada(db, dias=2 + d)[1]["envios"]["instagram"] for d in range(4)]
    for e in envios:
        vencer(db, e)
    largada, pegos, erros = threading.Barrier(2), [], []

    def rodada():
        c = conectar(autocommit=False)
        try:
            ids = [x for (x,) in c.execute("select * from radar_agenda_vencidas(2)").fetchall()]
            largada.wait(timeout=10)              # as duas rodadas pegam antes de qualquer uma confirmar
            c.commit()
            pegos.append(ids)
        except Exception as e:                    # pragma: no cover
            c.rollback()
            erros.append(repr(e))
        finally:
            c.close()
    fios = [threading.Thread(target=rodada) for _ in range(2)]
    [f.start() for f in fios]
    [f.join(timeout=30) for f in fios]
    assert erros == [] and len(pegos) == 2 and all(len(p) == 2 for p in pegos)
    assert sorted(pegos[0] + pegos[1]) == sorted(envios)                                       # nenhum envio nas duas rodadas
    assert db.execute("select array_agg(disparos order by id) from radar_redes_envios where id = any(%s)", (envios,)).fetchone()[0] == [1] * 4
    # o limite fica entre 1 e 10
    db.execute("update radar_redes_envios set disparado_em = null where id = any(%s)", (envios,))
    assert len(vencidas(db, 0)) == 1 and len(vencidas(db, 99)) == 3


def test_agenda_pausada_nas_configuracoes_nao_dispara(pauta):
    db = pauta
    _, r = peca_aprovada(db)
    e = r["envios"]["instagram"]
    vencer(db, e)
    db.execute("""update radar_config set valor = valor || '{"agenda_ligada": false}' where chave = 'pauta'""")
    assert vencidas(db) == []
    assert db.execute("select disparos, disparado_em, situacao from radar_redes_envios where id = %s", (e,)).fetchone() == (0, None, "autorizado")
    with como("authenticated", ADMIN) as c:
        assert c.execute("select radar_agenda_situacao()").fetchone()[0] == {"instalada": False, "agenda_ligada": False}
    db.execute("""update radar_config set valor = valor || '{"agenda_ligada": true}' where chave = 'pauta'""")
    assert vencidas(db) == [e]


def test_publicar_agora_remarca_erro_so_com_conferi_na_rede_e_recusa_agenda_velha(pauta):
    db = pauta
    pid, r = peca_aprovada(db, dias=5)
    ig = r["envios"]["instagram"]
    agora = "select radar_pauta_publicar_agora(%s, %s)"
    with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR159"):
        c.execute(agora, (pid, False))
    with como("authenticated", ADMIN) as c:
        assert c.execute(agora, (pid, False)).fetchone()[0] == [ig]                           # só remarca a hora
    assert db.execute("select agendado_para <= now(), disparos, disparado_em, situacao from radar_redes_envios where id = %s",
                      (ig,)).fetchone() == (True, 0, None, "autorizado")
    assert vencidas(db) == [ig]
    iniciar(ig)
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR169"):
        c.execute(agora, (pid, False))
    with como("service_role") as c:
        c.execute("select radar_rede_concluir(%s, false, null, null, %s, 'Meta recusou')", (ig, URL_INTERNA))
    with como("authenticated", ADMIN) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR166"):                 # "Tentar de novo" pede a caixa
            c.execute(agora, (pid, False))
        assert c.execute(agora, (pid, True)).fetchone()[0] == [ig]
    assert situacao_envio(db, ig) == ("autorizado", None)
    # o termo de hoje e as marcas da legenda congelada
    ana = nova_pessoa(db)
    p2, _ = peca_aprovada(db, dias=6, pessoas=[ana])
    db.execute("update radar_pessoas set termo_revogado_em = radar_pauta_hoje() where id = %s", (ana,))
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR165") as erro:
        c.execute(agora, (p2, False))
    assert "termo revogado" in str(erro.value) and "Ana" not in str(erro.value)
    p3, r3 = peca_aprovada(db, dias=7)
    db.execute("update radar_redes_envios set legenda = legenda || ' [VERIFICAR: dia]' where id = %s", (r3["envios"]["instagram"],))
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR165"):
        c.execute(agora, (p3, False))
    # a agenda da semana velha não sai; a peça à mão não passa por aqui; sem nada esperando, recusa
    p4, _ = peca_aprovada(db, dias=1, tipo="agenda", conferidas=[{"informacao": "10/11 (ter) · ICMS", "fonte": "Agenda Tributária da Receita Federal"}])
    voltar_a_data(db, p4, 3)
    p5 = nova_peca(db, dias=8)
    marcar_pronta(db, p5)
    aprovar_peca(db, p5, modo="manual")
    with como("authenticated", ADMIN) as c:
        for peca, erro in [(p4, "RADAR168"), (p5, "RADAR164")]:
            with pytest.raises(psycopg.errors.RaiseException, match=erro):
                c.execute(agora, (peca, False))
    vencer(db, ig)
    iniciar(ig)
    with como("service_role") as c:
        c.execute("select radar_rede_concluir(%s, true, '1789', 'https://www.instagram.com/p/abc/', %s, null)", (ig, URL_INTERNA))
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR164"):
        c.execute(agora, (pid, False))


def test_pode_copiar_e_registrar_manual_conferem_modo_termo_de_hoje_e_links(pauta):
    db = pauta
    ana = nova_pessoa(db)
    cartoes = [{"titulo": "Primeiro", "texto": "Separe as notas do mês."}, {"titulo": "Depois", "texto": "Envie para a equipe."}]
    pid = nova_peca(db, tipo="educativo", formato="carrossel", cartoes=cartoes, pessoas=[ana], legenda_facebook=LEG_PECA)
    marcar_pronta(db, pid)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR163"):                       # capa + uma lâmina por cartão
        aprovar_peca(db, pid, modo="manual", artes=[lamina(), lamina()])
    artes = [lamina(), lamina(), lamina()]
    assert aprovar_peca(db, pid, modo="manual", artes=artes, canais=("facebook", "instagram")) == {"agendado_para": None, "envios": {}}   # à mão: nenhum envio
    assert db.execute("select count(*) from radar_redes_envios where peca_id = %s", (pid,)).fetchone()[0] == 0
    copiar = "select radar_pauta_pode_copiar(%s, %s)"
    with como("authenticated", EDITOR) as c:
        assert c.execute(copiar, (pid, lido_peca(db, pid))).fetchone()[0] == {"ok": True, "artes": artes, "canais": ["instagram", "facebook"]}
        assert c.execute(copiar, (pid, datetime.now(timezone.utc))).fetchone()[0] == {"motivo": "A peça mudou depois que a tela foi aberta: recarregue e confira."}
        assert c.execute(copiar, (999999, None)).fetchone()[0] == {"motivo": "Peça não encontrada."}
    with como("authenticated", LEITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR159"):
        c.execute(copiar, (pid, lido_peca(db, pid)))
    db.execute("update radar_pessoas set termo_valido_ate = radar_pauta_hoje() - 1 where id = %s", (ana,))
    with como("authenticated", EDITOR) as c:
        assert c.execute(copiar, (pid, lido_peca(db, pid))).fetchone()[0] == \
            {"motivo": "O termo de uso de imagem de uma pessoa da peça não vale hoje no Instagram (termo vencido): confira em Pauta → Pessoas e termos."}
    db.execute("update radar_pessoas set termo_valido_ate = null where id = %s", (ana,))
    p2, _ = peca_aprovada(db, dias=3)
    with como("authenticated", EDITOR) as c:                                                  # aprovada para a agenda: não se copia
        assert c.execute(copiar, (p2, lido_peca(db, p2))).fetchone()[0] == {"motivo": "Só a peça aprovada para publicar à mão pode ser copiada ou baixada."}
    # registro do que foi postado à mão
    reg = "select radar_pauta_registrar_manual(%s, %s, %s, %s)"
    h = hoje(db)
    with como("authenticated", EDITOR) as c:
        for args, msg in [((pid, None, " ", h), "cole o link"), ((pid, "http://www.instagram.com/p/x/", None, h), "Instagram"),
                          ((pid, "https://instagram.com.golpe.exemplo/p/x", None, h), "Instagram"),
                          ((pid, None, "https://facebook.com.golpe.exemplo/x", h), "Facebook"),
                          ((pid, "https://www.instagram.com/p/abc/", None, h - timedelta(days=1)), "dia da aprovação"),
                          ((pid, "https://www.instagram.com/p/abc/", None, h + timedelta(days=1)), "dia da aprovação"),
                          ((p2, "https://www.instagram.com/p/abc/", None, h), "à mão")]:
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR175") as erro:
                c.execute(reg, args)
            assert msg in str(erro.value)
        assert c.execute(reg, (pid, "https://www.instagram.com/p/abc/", None, h)).fetchone()[0] == \
            {"link_instagram": "https://www.instagram.com/p/abc/", "link_facebook": None, "publicado_manual_em": h.isoformat()}
        r = c.execute(reg, (pid, "https://www.instagram.com/p/outro/", "https://fb.watch/xyz/", h)).fetchone()[0]
        assert (r["link_instagram"], r["link_facebook"]) == ("https://www.instagram.com/p/abc/", "https://fb.watch/xyz/")   # completa, não troca
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR170"):                   # já saiu: não desfaz
            c.execute("select radar_pauta_desaprovar(%s)", (pid,))
    assert db.execute("select publicado_manual_por::text from radar_pauta_pecas where id = %s", (pid,)).fetchone()[0] == EDITOR



def test_desfazer_aprovacao_a_mao_pede_conferi_na_rede_e_a_nova_aprovacao_tambem(pauta):
    """A peça aprovada à mão pode ter sido postada sem o link registrado (o editor copiou a legenda, baixou a lâmina e postou). Desfazer
    a aprovação pede a caixa "Conferi no Instagram e no Facebook: não foi postada à mão"; a próxima aprovação, em qualquer modo, pede
    "Conferi … não saiu" (senão a agenda publicaria de novo o que já saiu à mão). A marca não se apaga pela tela e sai na aprovação."""
    db = pauta
    pid = nova_peca(db, dias=4)
    marcar_pronta(db, pid)
    aprovar_peca(db, pid, modo="manual")
    with como("authenticated", EDITOR) as c:
        assert c.execute("select radar_pauta_pode_copiar(%s, %s)", (pid, lido_peca(db, pid))).fetchone()[0]["ok"] is True
        for args in [(pid,), (pid, False), (pid, None)]:
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR166") as erro:
                c.execute("select radar_pauta_desaprovar(%s" + ", %s" * (len(args) - 1) + ")", args)
            assert "Conferi no Instagram e no Facebook: não foi postada à mão" in str(erro.value)
        assert db.execute("select situacao from radar_pauta_pecas where id = %s", (pid,)).fetchone()[0] == "aprovada"
        c.execute("select radar_pauta_desaprovar(%s, true)", (pid,))
        c.execute("update radar_pauta_pecas set manual_desfeita_em = null where id = %s", (pid,))       # a tela não apaga a marca
    assert db.execute("select situacao, aprovado_canais, manual_desfeita_em is not null from radar_pauta_pecas where id = %s",
                      (pid,)).fetchone() == ("pronta", [], True)
    for modo in ("agendar", "manual"):
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR166") as erro:
            aprovar_peca(db, pid, modo=modo, conferencias=("pessoas",))
        assert "não foi postada" in str(erro.value)
    assert db.execute("select count(*) from radar_redes_envios where peca_id = %s", (pid,)).fetchone()[0] == 0     # nada foi agendado
    r = aprovar_peca(db, pid, modo="agendar", conferencias=("rede", "pessoas"))
    assert db.execute("select aprovado_conferencias, manual_desfeita_em from radar_pauta_pecas where id = %s", (pid,)).fetchone() == (["pessoas", "rede"], None)
    # aprovada para a agenda: desfaz sem a caixa (nada saiu à mão) e a próxima aprovação não pede mais a conferência
    with como("authenticated", EDITOR) as c:
        c.execute("select radar_pauta_desaprovar(%s)", (pid,))
    assert situacao_envio(db, r["envios"]["instagram"])[0] == "cancelado"
    assert aprovar_peca(db, pid, modo="agendar", conferencias=("pessoas",))["envios"]["instagram"]


def test_peca_a_mao_so_sai_nos_canais_aprovados(pauta):
    """Os canais que o administrador marca na aprovação ficam na peça (aprovado_canais): copiar a legenda, conferir o termo e registrar o
    link valem só neles. A pessoa que tirou o Facebook do termo depois da aprovação não impede copiar a peça aprovada só para o Instagram.
    Desfazer limpa os canais."""
    db = pauta
    ana = nova_pessoa(db)
    pid = nova_peca(db, dias=3, pessoas=[ana], legenda_facebook=LEG_PECA)
    marcar_pronta(db, pid)
    aprovar_peca(db, pid, modo="manual", canais=("instagram",), conferencias=("pessoas",))
    artes = db.execute("select artes from radar_pauta_pecas where id = %s", (pid,)).fetchone()[0]
    assert db.execute("select aprovado_canais from radar_pauta_pecas where id = %s", (pid,)).fetchone()[0] == ["instagram"]
    copiar = "select radar_pauta_pode_copiar(%s, %s, %s)"
    reg = "select radar_pauta_registrar_manual(%s, %s, %s, %s)"
    with como("authenticated", EDITOR) as c:
        lido = lido_peca(db, pid)
        assert c.execute(copiar, (pid, lido, "facebook")).fetchone()[0] == \
            {"motivo": "O Facebook não foi aprovado para esta peça: ela sai só no canal marcado na aprovação."}
        for ig, fb in [(None, "https://www.facebook.com/artecon/posts/1"), ("https://www.instagram.com/p/abc/", "https://www.facebook.com/artecon/posts/1")]:
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR175: o Facebook não foi aprovado para esta peça"):
                c.execute(reg, (pid, ig, fb, hoje(db)))
        assert db.execute("select link_instagram, link_facebook, publicado_manual_em from radar_pauta_pecas where id = %s", (pid,)).fetchone() == (None, None, None)
        c.execute("update radar_pauta_pecas set aprovado_canais = '{instagram,facebook}' where id = %s", (pid,))   # a tela não muda os canais
        assert c.execute(copiar, (pid, lido_peca(db, pid), "facebook")).fetchone()[0]["motivo"].startswith("O Facebook não foi aprovado")
    db.execute("update radar_pessoas set termo_canais = '{instagram}' where id = %s", (ana,))
    with como("authenticated", EDITOR) as c:
        lido = lido_peca(db, pid)
        assert c.execute(copiar, (pid, lido, "instagram")).fetchone()[0] == {"ok": True, "artes": artes, "canais": ["instagram"]}
        assert c.execute(copiar, (pid, lido, None)).fetchone()[0]["ok"] is True          # baixar as lâminas: o termo do canal aprovado
        c.execute("select radar_pauta_desaprovar(%s, true)", (pid,))
    assert db.execute("select aprovado_canais from radar_pauta_pecas where id = %s", (pid,)).fetchone()[0] == []
    with como("authenticated", EDITOR) as c:                                             # a peça nova nasce sem canal aprovado
        nova = c.execute("insert into radar_pauta_pecas (data, tipo, formato, aprovado_canais) values (%s, 'bastidor', 'imagem', '{instagram}') "
                         "returning aprovado_canais", (hoje(db) + timedelta(days=40),)).fetchone()[0]
    assert nova == []


def test_pauta_desiste_de_um_canal_com_o_outro_ja_publicado(pauta):
    """O Instagram saiu e o Facebook deu erro (ou ainda espera a hora): desfazer a aprovação não dá (o Instagram saiu), e o administrador
    desiste só do outro canal (radar_cancelar_rede, o botão "Não publicar neste canal" da peça). A peça continua aprovada, o Instagram
    continua publicado e a falha sai do painel (o aviso do robô fecha). O recado de quando está publicando manda cancelar na Pauta."""
    db = pauta

    def falhas():
        with como("authenticated", LEITOR) as c:
            return c.execute("select pauta_falhas from radar_v_painel").fetchone()[0]
    for situacao_fb in ("erro", "autorizado"):
        pid, r = peca_aprovada(db, dias=2 if situacao_fb == "erro" else 3, canais=("instagram", "facebook"))
        ig, fb = r["envios"]["instagram"], r["envios"]["facebook"]
        vencer(db, ig)
        iniciar(ig)
        with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.RaiseException, match="RADAR169") as erro:
            c.execute("select radar_pauta_desaprovar(%s)", (pid,))
        assert "cancela na própria peça, na Pauta" in str(erro.value) and "Publicações" not in str(erro.value)
        with como("service_role") as c:
            c.execute("select radar_rede_concluir(%s, true, '1789', 'https://www.instagram.com/p/abc/', %s, null)", (ig, URL_INTERNA))
        if situacao_fb == "erro":
            vencer(db, fb)
            iniciar(fb)
            with como("service_role") as c:
                c.execute("select radar_rede_concluir(%s, false, null, null, %s, 'A Meta recusou (190)')", (fb, URL_INTERNA))
            assert falhas() == 1
        else:
            vencer(db, fb)                                                             # chegou a hora: a agenda pegaria na próxima rodada
        with como("authenticated", ADMIN) as c:
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR170"):
                c.execute("select radar_pauta_desaprovar(%s)", (pid,))
            assert c.execute("select radar_cancelar_rede(%s)", (fb,)).fetchone()[0] is True
        assert falhas() == 0
        assert db.execute("select situacao from radar_pauta_pecas where id = %s", (pid,)).fetchone()[0] == "aprovada"
        assert [situacao_envio(db, e)[0] for e in (ig, fb)] == ["publicado", "cancelado"]
        assert vencidas(db) == []                                                      # a agenda não publica mais o Facebook
        with como("authenticated", EDITOR) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):   # só o administrador desiste
            c.execute("select radar_cancelar_rede(%s)", (ig,))

def test_redes_conferir_agenda_sem_vault_nunca_confere(db):
    with como("service_role") as c:
        assert c.execute("select radar_redes_conferir_agenda(%s)", ("a" * 64,)).fetchone()[0] is False   # sem Vault: nunca confere
    for papel, uid in (("authenticated", ADMIN), ("anon", None)):
        with como(papel, uid) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select radar_redes_conferir_agenda('x')")
    tinha = db.execute("select count(*) from pg_namespace where nspname = 'vault'").fetchone()[0] == 1
    if not tinha:
        db.execute(VAULT_SIMULADO)
    try:                                                  # com o Vault (de mentira): só a chave certa, com 32 caracteres ou mais
        db.execute("insert into vault.secrets (name, secret) values ('radar_redes_agenda', %s)", ("f" * 64,))
        db.execute("insert into vault.secrets (name, secret) values ('radar_itc_agenda', %s)", ("e" * 64,))
        with como("service_role") as c:
            assert [c.execute("select radar_redes_conferir_agenda(%s)", (k,)).fetchone()[0] for k in ("f" * 64, "e" * 64, "f" * 31, None)] == \
                [True, False, False, False]                # a chave da ITC não vale para a Pauta
    finally:
        if tinha:
            db.execute("delete from vault.secrets where name in ('radar_redes_agenda', 'radar_itc_agenda')")
        else:
            db.execute("drop schema vault cascade")


def test_limpeza_de_imagens_nao_apaga_foto_nem_arte_da_pauta(pauta):
    db = pauta
    foto, solta = nova_imagem(), nova_imagem()
    pid = nova_peca(db, formato="foto", fotos=[foto])
    marcar_pronta(db, pid)
    arte = lamina()
    aprovar_peca(db, pid, artes=[arte], conferencias=("pessoas",))
    db.execute("update radar_imagens set criado_em = now() - interval '3 days'")
    with como("service_role") as c:
        assert c.execute("select radar_limpar_imagens_sem_uso()").fetchone()[0] == 1
    assert {i for (i,) in db.execute("select id from radar_imagens").fetchall()} == {foto, arte}
    # a capa trocada de um conteúdo, que também é foto de uma peça, fica
    cid = novo_conteudo(db, novo_assunto(db))
    db.execute("update radar_conteudos set imagem_id = %s where id = %s", (foto, cid))
    db.execute("update radar_conteudos set imagem_id = null where id = %s", (cid,))
    assert db.execute("select count(*) from radar_imagens where id = %s", (foto,)).fetchone()[0] == 1
    assert solta not in {i for (i,) in db.execute("select id from radar_imagens").fetchall()}


def test_auditoria_sem_plano_nem_nome_nem_crc_nem_ia(pauta):
    db = pauta
    with como("authenticated", ADMIN) as c:
        bruno = c.execute("""insert into radar_pessoas (nome, nome_na_peca, area, categoria, crc, termo_assinado_em, termo_canais, termo_usos)
                             values ('Bruno Exemplo', 'Bruno', 'Contábil', 'contador', 'CRC-SC 054321/O-1', '2020-01-01', '{instagram}', '{equipe}')
                             returning id""").fetchone()[0]
        c.execute("update radar_pessoas set termo_canais = '{instagram,facebook}' where id = %s", (bruno,))
        c.execute("update radar_pessoas set nome = 'Bruno Exemplo Filho', area = 'Fiscal' where id = %s", (bruno,))   # só o que não vai à trilha
    with como("authenticated", EDITOR) as c:
        pid = c.execute("""insert into radar_pauta_pecas (data, tipo, formato, assunto, quem_aparece, objetivo, observacao)
                           values (%s, 'quem_cuida', 'foto', 'Plano com Bruno Exemplo', 'Bruno Exemplo', 'apresentar', 'lembrete do plano')
                           returning id""", (hoje(db) + timedelta(days=4),)).fetchone()[0]
        c.execute("update radar_pauta_pecas set assunto = 'Outro plano com Bruno', ia = %s where id = %s",
                  (json.dumps({"versao": 1, "instagram": {"texto": "Sugestão com Bruno"}}), pid))
        c.execute("update radar_pauta_pecas set pessoas = %s::bigint[], chamada = 'Quem cuida da sua contabilidade' where id = %s", ([bruno], pid))
    trilha = db.execute("""select tabela, acao, usuario::text, antes, depois from radar_auditoria
                           where tabela in ('radar_pessoas', 'radar_pauta_pecas') order by id""").fetchall()
    assert [(t, a, u) for t, a, u, _, _ in trilha] == [("radar_pessoas", "INSERT", ADMIN), ("radar_pessoas", "UPDATE", ADMIN),
                                                       ("radar_pauta_pecas", "INSERT", EDITOR), ("radar_pauta_pecas", "UPDATE", EDITOR)]
    texto = json.dumps([x for *_, a, d in trilha for x in (a, d)], ensure_ascii=False)
    for proibido in ("Bruno", "054321", "Contábil", "Fiscal", "lembrete", "apresentar", "Sugestão"):
        assert proibido not in texto, proibido
    pessoa = trilha[1][4]
    assert (pessoa["termo_canais"], pessoa["termo_assinado_em"], pessoa["categoria"], pessoa["ativo"]) == (["instagram", "facebook"], "2020-01-01", "contador", True)
    peca = trilha[3][4]
    assert peca["pessoas"] == [bruno] and peca["chamada"] == "Quem cuida da sua contabilidade" and "ia" not in peca and "assunto" not in peca
    # as marcas da agenda do banco (de 5 em 5 minutos) também não entram
    _, r = peca_aprovada(db, dias=6)
    vencer(db, r["envios"]["instagram"])
    antes = db.execute("select count(*) from radar_auditoria where tabela = 'radar_redes_envios'").fetchone()[0]
    assert vencidas(db) == [r["envios"]["instagram"]]
    assert db.execute("select count(*) from radar_auditoria where tabela = 'radar_redes_envios'").fetchone()[0] == antes


def test_pessoas_so_admin_grava_editor_le_leitor_e_robo_nao_leem(pauta):
    db = pauta
    with como("authenticated", ADMIN) as c:
        ana = c.execute("insert into radar_pessoas (nome, nome_na_peca) values ('Ana Teste', 'Ana') returning id").fetchone()[0]
        assert c.execute("update radar_pessoas set area = 'Fiscal' where id = %s", (ana,)).rowcount == 1
    with como("authenticated", EDITOR) as c:
        assert c.execute("select nome, area from radar_pessoas").fetchall() == [("Ana Teste", "Fiscal")]
        assert c.execute("update radar_pessoas set ativo = false where id = %s", (ana,)).rowcount == 0
        assert c.execute("delete from radar_pessoas where id = %s", (ana,)).rowcount == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into radar_pessoas (nome, nome_na_peca) values ('Bruno Exemplo', 'Bruno')")
    for uid in (LEITOR, SEM_PERFIL):
        with como("authenticated", uid) as c:
            assert c.execute("select count(*) from radar_pessoas").fetchone()[0] == 0
    for papel in ("service_role", "anon"):
        for tabela in ("radar_pessoas", "radar_pauta_pecas"):
            with como(papel) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(f"select count(*) from {tabela}")
    with como("authenticated", ADMIN) as c:
        for campos, restricao in [("categoria = 'contador'", "radar_pessoas_categoria_crc"), ("crc = '12345'", "radar_pessoas_crc_check"),
                                  ("categoria = 'especialista', crc = 'CRC-SC 012345'", "radar_pessoas_categoria_check"),
                                  ("termo_assinado_em = '2026-10-10', termo_valido_ate = '2026-10-01'", "radar_pessoas_termo_prazo"),
                                  ("termo_valido_ate = '2026-10-01'", "radar_pessoas_termo_prazo"),
                                  ("termo_canais = '{tiktok}'", "radar_pessoas_termo_canais_check"),
                                  ("termo_usos = '{propaganda}'", "radar_pessoas_termo_usos_check"), ("nome = 'A'", "radar_pessoas_nome_check")]:
            with pytest.raises(psycopg.errors.CheckViolation, match=restricao):
                c.execute(f"update radar_pessoas set {campos} where id = %s", (ana,))
        c.execute("update radar_pessoas set categoria = 'contadora', crc = 'CRC-SC 012345/O-9' where id = %s", (ana,))
        assert c.execute("delete from radar_pessoas where id = %s", (ana,)).rowcount == 1



def test_chave_do_robo_e_leitor_nao_leem_as_fotos_as_laminas_nem_as_legendas_da_pauta(pauta):
    """A chave do robô (segredo do GitHub Actions de um repositório público) não lê onde ficam as fotos e os nomes: radar_imagens (a
    capa do conteúdo vem por radar_v_capas), a auditoria e, nos envios, a legenda, a imagem e o erro (lê só o andamento, como o robô e
    a radar-redes pedem). O leitor não lê as fotos nem as lâminas da Pauta (v0.22.0: só as imagens ligadas a um conteúdo); o editor lê
    todas."""
    db = pauta
    foto, capa, solta = nova_imagem(), nova_imagem(), nova_imagem()
    pid, r = peca_aprovada(db, dias=3, formato="foto", fotos=[foto])
    arte = db.execute("select artes[1] from radar_pauta_pecas where id = %s", (pid,)).fetchone()[0]
    c1 = novo_conteudo(db, novo_assunto(db))
    db.execute("update radar_conteudos set imagem_id = %s where id = %s", (capa, c1))
    with como("service_role") as c:
        for sql in ["select id from radar_imagens", "select legenda from radar_redes_envios", "select imagem from radar_redes_envios",
                    "select erro from radar_redes_envios", "select * from radar_redes_envios", "select count(*) from radar_auditoria",
                    "select count(*) from radar_pauta_pecas", "select count(*) from radar_pessoas"]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(sql)
        # o que o robô (radar_banco.py, radar_site_publicar.py, radar-site-publicar.yml) e a radar-redes leem continua legível
        assert c.execute("""select id, canal, situacao, agendado_para is not null, enviado_em from radar_redes_envios
                            where peca_id is not null and situacao in ('erro','enviando','autorizado') order by agendado_para, id""").fetchall() == \
            [(r["envios"]["instagram"], "instagram", "autorizado", True, None)]
        assert c.execute("""select canal, situacao, junto_com_site, peca_id, post_id, url from radar_redes_envios where id = %s""",
                         (r["envios"]["instagram"],)).fetchone() == ("instagram", "autorizado", False, pid, None, None)
        assert c.execute("select id, dados from radar_v_capas").fetchall() == [(capa, PIXEL)]
    for papel in ("anon", "authenticated"):
        with como(papel, EDITOR if papel == "authenticated" else None) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select * from radar_v_capas")
    with como("authenticated", LEITOR) as c:
        # varredura geral (v0.22.0): o leitor lê só a imagem ligada a um conteúdo; a solta (a foto tirada da peça, a lâmina de uma
        # aprovação recusada ou desfeita, antes da faxina de 24 horas) não
        assert sorted(x for (x,) in c.execute("select id from radar_imagens").fetchall()) == [capa]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):                              # nem a cópia da lâmina no envio
            c.execute("select imagem from radar_redes_envios")
        assert c.execute("select canal, situacao from radar_redes_envios where peca_id = %s", (pid,)).fetchall() == [("instagram", "autorizado")]
    with como("authenticated", EDITOR) as c:
        assert {foto, arte, capa, solta} <= {x for (x,) in c.execute("select id from radar_imagens").fetchall()}
    # a foto tirada da peça e a lâmina da aprovação desfeita deixam de estar numa peça: o leitor continua sem vê-las
    mudar_por_fora(db, pid, "fotos = '{}', artes = '{}'")
    db.execute("update radar_conteudos set ilustracao_id = %s where id = %s", (solta, c1))
    with como("authenticated", LEITOR) as c:
        assert sorted(x for (x,) in c.execute("select id from radar_imagens").fetchall()) == sorted([capa, solta])


def test_pessoa_em_uso_nao_se_apaga(pauta):
    db = pauta
    ana, bruno = nova_pessoa(db), nova_pessoa(db, "Bruno Exemplo", "Bruno")
    pid = nova_peca(db, pessoas=[ana, bruno])
    with como("authenticated", ADMIN) as c:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR174"):
            c.execute("delete from radar_pessoas where id = %s", (ana,))
        assert c.execute("update radar_pessoas set ativo = false where id = %s", (ana,)).rowcount == 1   # o caminho é desmarcar "Ativa"
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_pauta_pecas set situacao = 'cancelada' where id = %s", (pid,))
    with como("authenticated", ADMIN) as c:
        assert c.execute("delete from radar_pessoas where id = %s", (ana,)).rowcount == 1
    assert db.execute("select pessoas, situacao from radar_pauta_pecas where id = %s", (pid,)).fetchone() == ([bruno], "cancelada")


def test_envio_da_pauta_regra_e_fora_do_robo_do_site(pauta):
    db = pauta
    pid, r = peca_aprovada(db)
    ig = r["envios"]["instagram"]
    a, c1 = cenario_publicavel(db)
    inserir = """insert into radar_redes_envios (conteudo_id, peca_id, canal, legenda, conteudo_lido_em, agendado_para, junto_com_site)
                 values (%s, %s, %s, 'Legenda de teste.', now(), %s, %s)"""
    amanha = datetime.now(timezone.utc) + timedelta(days=1)
    for args, restricao in [((c1, pid, "facebook", amanha, False), "radar_redes_envios_origem_ck"),       # da notícia OU da peça
                            ((None, None, "facebook", amanha, False), "radar_redes_envios_origem_ck"),
                            ((None, pid, "facebook", None, False), "radar_redes_envios_peca_ck"),          # a peça tem hora
                            ((None, pid, "facebook", amanha, True), "radar_redes_envios_peca_ck")]:        # e nunca espera o site
        with pytest.raises(psycopg.errors.CheckViolation, match=restricao):
            db.execute(inserir, args)
    with pytest.raises(psycopg.errors.UniqueViolation, match="radar_redes_envios_peca_uk"):            # uma em aberto por peça e canal
        db.execute(inserir, (None, pid, "instagram", amanha, False))
    with como("authenticated", ADMIN) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute(inserir, (None, pid, "facebook", amanha, False))
    # o robô do site (radar_site_publicar.py e o workflow) só procura o que foi autorizado junto com o site
    vencer(db, ig)
    with como("service_role") as c:
        assert c.execute("select count(*) from radar_redes_envios where situacao = 'autorizado' and junto_com_site").fetchone()[0] == 0
        assert c.execute("select count(*) from radar_redes_envios where situacao = 'autorizado'").fetchone()[0] == 1
    with como("authenticated", ADMIN) as c:                                                    # cancelado, abre de novo
        c.execute("select radar_cancelar_rede(%s)", (ig,))
    db.execute(inserir, (None, pid, "instagram", amanha, False))


def test_painel_avisa_quando_o_robo_de_coleta_para(limpo, request):
    """Rodada 2 da varredura geral: no repositório público, o GitHub desliga sozinho os robôs agendados depois de 60 dias sem
    atividade, e só os números do Painel mudavam. O painel diz a última rodada do robô de coleta e se ela passou de 12 horas (com
    fonte ativa que o robô coleta: a do e-mail não passa por ele)."""
    db = limpo
    carregar_fontes_novas(db, request)                                                     # com a fonte do e-mail (itc-email)
    painel = lambda: _painel_coleta()
    fonte = db.execute("select id from radar_fontes where slug = 'rfb-normas'").fetchone()[0]
    assert db.execute("select count(*) from radar_fontes where config->>'origem' = 'email'").fetchone()[0] == 1
    ativas = [i for (i,) in db.execute("select id from radar_fontes where ativo").fetchall()]
    try:
        db.execute("update radar_fontes set ativo = (id = %s)", (fonte,))
        assert painel() == (None, True)                                                    # nunca rodou
        db.execute("insert into radar_execucoes (fonte_id, iniciado_em) values (%s, now() - interval '13 hours')", (fonte,))
        ultima, atrasada = painel()
        assert ultima is not None and atrasada is True
        db.execute("insert into radar_execucoes (fonte_id, iniciado_em) values (%s, now() - interval '5 hours')", (fonte,))
        assert painel()[1] is False                                                        # rodou há 5 h: em dia
        db.execute("update radar_execucoes set iniciado_em = iniciado_em - interval '1 day'")
        assert painel()[1] is True
        db.execute("update radar_fontes set ativo = false")                                # sem fonte ativa: nada a avisar
        assert painel()[1] is False
        db.execute("""update radar_fontes set ativo = true where config->>'origem' = 'email'""")   # só a do e-mail (não passa pelo robô)
        assert painel()[1] is False
    finally:
        db.execute("update radar_fontes set ativo = (id = any(%s))", (ativas,))


def _painel_coleta():
    with como("authenticated", LEITOR) as c:
        return c.execute("select ultima_coleta, coleta_atrasada from radar_v_painel").fetchone()


def test_painel_conta_falhas_da_pauta(pauta):
    db = pauta

    def falhas():
        with como("authenticated", LEITOR) as c:
            return c.execute("select pauta_falhas from radar_v_painel").fetchone()[0]
    _, r1 = peca_aprovada(db, dias=2)
    e1 = r1["envios"]["instagram"]
    assert falhas() == 0                                                                       # agendada para depois
    vencer(db, e1, 10)
    assert falhas() == 0                                                                       # passou há pouco: a agenda ainda pega
    vencer(db, e1, 25)
    assert falhas() == 1                                                                       # passou há mais de 20 min: parada
    _, r2 = peca_aprovada(db, dias=3)
    e2 = r2["envios"]["instagram"]
    vencer(db, e2)
    iniciar(e2)
    assert falhas() == 1                                                                       # saindo agora não conta
    db.execute("update radar_redes_envios set enviado_em = now() - interval '16 minutes' where id = %s", (e2,))
    assert falhas() == 2                                                                       # parada em "enviando"
    with como("service_role") as c:
        c.execute("select radar_rede_concluir(%s, false, null, null, null, 'Meta recusou')", (e2,))
    assert falhas() == 2                                                                       # com erro
    with como("authenticated", ADMIN) as c:
        c.execute("select radar_pauta_publicar_agora((select peca_id from radar_redes_envios where id = %s), true)", (e2,))
    assert falhas() == 1


def test_hoje_e_de_brasilia_e_nenhuma_funcao_nova_usa_current_date(db):
    with conectar() as c:
        c.execute("set timezone = 'Pacific/Kiritimati'")                    # o servidor noutro fuso (UTC+14) não muda o "hoje" da Pauta
        assert c.execute("select radar_pauta_hoje() = (now() at time zone 'America/Sao_Paulo')::date").fetchone()[0] is True
    novas = db.execute("""select p.proname, p.prosrc from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                          where n.nspname = 'public' and (p.proname like 'radar\\_pauta\\_%' or p.proname like 'radar\\_agenda\\_%'
                                or p.proname in ('radar_redes_conferir_agenda', 'radar_fn_pauta_peca', 'radar_fn_pessoa_apagar'))""").fetchall()
    # v0.22.0: + radar_pauta_pecas_da_pessoa; v0.28.0: + radar_pauta_criar, radar_pauta_linha_invalida e radar_pauta_hora_padrao
    assert len(novas) == 33
    assert [n for n, src in novas if "current_date" in src.lower()] == []


def test_setup_nao_cria_os_esquemas_cron_nem_net(db):
    assert db.execute("select count(*) from pg_namespace where nspname in ('cron', 'net')").fetchone()[0] == 0
    # o setup só cita o pg_cron e o Vault dentro de "execute" (com exceção): roda no Postgres comum dos testes
    linhas = [re.sub(r"--.*$", "", l) for l in SETUP.read_text().splitlines()]
    assert [l for l in linhas if re.search(r"\b(cron|net|vault)\.", l) and "execute '" not in l] == []
    assert "create extension" not in SETUP.read_text().lower()
    with como("authenticated", ADMIN) as c:
        assert c.execute("select radar_agenda_situacao()").fetchone()[0] == {"instalada": False, "agenda_ligada": True}
    for uid in (EDITOR, LEITOR):                                            # os dados da agenda são só do administrador
        with como("authenticated", uid) as c:
            assert c.execute("select radar_agenda_situacao()").fetchone()[0] == {}


def test_reversao_tira_a_agenda_e_as_tabelas_da_pauta():
    sql = REVERSAO.read_text()
    for objeto in ("radar_pauta_pecas", "radar_pessoas", "radar_v_pauta_pessoas", "radar-redes-agenda%", "radar_agenda_vencidas(int)",
                   "radar_lembretes,", "radar_lembretes_observar(timestamptz)", "radar_lembretes_situacao()", "Disable workflow"):   # v0.29.0
        assert objeto in sql, objeto
    # varredura geral (v0.22.0): o cabeçalho (e o LEIAME) mandam esvaziar antes também o bucket privado radar-pauta (as lâminas com
    # foto e nome da equipe ficariam sem dono depois que as tabelas saem)
    cabecalho = sql.split("\nbegin;")[0]
    desfazer = (RAIZ / "LEIAME-radar.md").read_text(encoding="utf-8").split("**Para desfazer a versão**")[1][:1500]
    assert "radar-videos" in cabecalho and "radar-pauta" in cabecalho and "`radar-pauta`" in desfazer
    with conectar("postgres") as c:
        c.execute("drop database if exists radar_rev21 with (force)")
        c.execute("create database radar_rev21")
    try:
        assert psql(RAIZ / "testes" / "supabase_simulado.sql", "radar_rev21").returncode == 0
        assert psql(SETUP, "radar_rev21").returncode == 0
        with conectar("radar_rev21") as c:                       # o pg_cron (de mentira) com a agenda da Pauta, a da ITC e outras
            c.execute(CRON_SIMULADO)
            for nome in ("radar-redes-agenda", "radar-redes-agenda-limpeza", "radar-redes-agenda-lembretes", "radar-itc", "radar-outra",
                         "copia-do-projeto"):
                c.execute("select cron.schedule(%s, '*/5 * * * *', 'select 1')", (nome,))
        r = psql(REVERSAO, "radar_rev21")
        assert r.returncode == 0, r.stderr
        assert "Sobrou agendamento do Radar no pg_cron" in r.stderr
        with conectar("radar_rev21") as c:
            assert sorted(n for (n,) in c.execute("select jobname from cron.job").fetchall()) == ["copia-do-projeto", "radar-outra"]
            assert c.execute("select to_regclass('public.radar_pauta_pecas'), to_regclass('public.radar_pessoas'), "
                             "to_regclass('public.radar_lembretes')").fetchone() == (None, None, None)
            assert c.execute("""select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                                where n.nspname = 'public' and p.proname like 'radar\\_%'""").fetchone()[0] == 0
    finally:
        with conectar("postgres") as c:
            c.execute("drop database if exists radar_rev21 with (force)")


# ------------------------------------------------ v0.24.0: Conferência das Diretrizes e texto Informativo
LISTA_OK = [{"item": n, "situacao": "atende", "motivo": f"Critério {n} atendido."} for n in range(1, 11)]


def lido_de(db, conteudo):
    return db.execute("select atualizado_em from radar_conteudos where id = %s", (conteudo,)).fetchone()[0]


def registrar_conferencia(conteudo, itens=LISTA_OK, uid=EDITOR, lido=None):
    """Grava a lista da IA como a função radar-ia grava (com o login de quem pediu)."""
    with como("authenticated", uid) as c:
        if lido is None:
            lido = c.execute("select atualizado_em from radar_conteudos where id = %s", (conteudo,)).fetchone()[0]
        return c.execute("select radar_registrar_conferencia(%s, %s, %s, 'claude-sonnet-4-6')", (conteudo, lido, json.dumps(itens))).fetchone()[0]


def com_item(n, situacao, motivo="Motivo de teste."):
    return [x if x["item"] != n else {"item": n, "situacao": situacao, "motivo": motivo} for x in LISTA_OK]


def test_aprovacao_pede_a_conferencia_das_diretrizes_da_versao_do_texto(limpo, conferencia_de_verdade):
    """v0.24.0 (Diretriz 7): sem a Conferência das Diretrizes do texto que está no conteúdo, nem o editor nem o administrador aprovam
    (RADAR181); com critério que não atende, também não (RADAR182, com os números); com os 10 atendidos (ou "não se aplica"), aprova.
    Mudou o título, o texto, a fonte ou a capa, a conferência deixa de valer. Gravar a conferência não muda a data do conteúdo, e ela
    só muda pelas funções: nem o UPDATE direto nem o INSERT a forjam."""
    a, c1 = cenario_publicavel(limpo)
    for uid in (EDITOR, ADMIN):
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR181: falta a Conferência das Diretrizes deste texto"):
            aprovar(c1, uid)
    antes = lido_de(limpo, c1)
    conf = registrar_conferencia(c1, com_item(7, "nao_atende", "O título promete mais que o texto."))
    assert lido_de(limpo, c1) == antes                                           # a data do conteúdo não muda
    assert [(x["item"], x["situacao"]) for x in conf["itens"] if x["situacao"] != "atende"] == [(6, "nao_se_aplica"), (7, "nao_atende")]
    gravada = limpo.execute("select conferencia from radar_conteudos where id = %s", (c1,)).fetchone()[0]
    assert gravada["versao"] == limpo.execute("select radar_conferencia_versao(c) from radar_conteudos c where id = %s", (c1,)).fetchone()[0]
    assert gravada["por"] == EDITOR and gravada["modelo"] == "claude-sonnet-4-6" and len(gravada["itens"]) == 10
    with pytest.raises(psycopg.errors.RaiseException, match=r"RADAR182: a Conferência das Diretrizes tem critério que não atende \(7\)"):
        aprovar(c1)
    # a editora não tira o ✗ gravando outra lista para o mesmo texto (nem pela API): ele fica, com o motivo de antes
    conf = registrar_conferencia(c1, com_item(5, "nao_se_aplica", "Sem citação literal."))
    assert conf["itens"][6] == {"item": 7, "situacao": "nao_atende", "motivo": "O título promete mais que o texto."} and conf["itens"][4]["situacao"] == "nao_se_aplica"
    with pytest.raises(psycopg.errors.RaiseException, match=r"RADAR182: .*\(7\)"):
        aprovar(c1)
    # a lista do administrador (o "Revisar com IA" pedido por ele) vale inteira
    registrar_conferencia(c1, com_item(5, "nao_se_aplica", "Sem citação literal."), uid=ADMIN)
    assert aprovar(c1) == (EDITOR,)
    # o texto mudou: volta para revisão e a conferência anterior não vale mais
    limpo.execute("update radar_conteudos set corpo = 'Texto alterado depois da conferência.' where id = %s", (c1,))
    assert limpo.execute("select status from radar_conteudos where id = %s", (c1,)).fetchone()[0] == "em_revisao"
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR181"):
        aprovar(c1)
    # o título, a capa e a fonte também fazem parte da versão
    registrar_conferencia(c1)
    limpo.execute("update radar_conteudos set titulo = 'Título trocado depois da conferência' where id = %s", (c1,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR181"):
        aprovar(c1)
    registrar_conferencia(c1)
    limpo.execute("update radar_conteudos set fonte_credito = 'Outra fonte' where id = %s", (c1,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR181"):
        aprovar(c1)
    registrar_conferencia(c1)
    limpo.execute("update radar_conteudos set imagem_id = %s where id = %s", (nova_imagem(), c1))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR181"):
        aprovar(c1)
    # ninguém forja a conferência por fora: o UPDATE direto e o INSERT não a gravam
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_conteudos set conferencia = %s where id = %s",
                  (json.dumps({"versao": "x", "itens": LISTA_OK}), c1))
        n = c.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo, status, conferencia)
                         values (%s, 'flash', 'Novo', 'Texto novo.', 'em_revisao', %s) returning id""",
                      (a, json.dumps({"versao": "x", "itens": LISTA_OK}))).fetchone()[0]
    assert limpo.execute("select conferencia->>'versao' from radar_conteudos where id = %s", (c1,)).fetchone()[0] != "x"
    assert limpo.execute("select conferencia from radar_conteudos where id = %s", (n,)).fetchone()[0] == {}
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR181"):
        aprovar(n)


def test_lista_da_conferencia_e_validada_e_so_editor_ou_administrador_grava(limpo, conferencia_de_verdade):
    """v0.24.0: a lista tem os 10 critérios, cada um uma vez, com a situação ("atende", "nao_atende", "nao_se_aplica") e o motivo (até
    300 caracteres) (RADAR185); vale para o texto que foi à IA (RADAR184); o leitor não grava (RADAR183)."""
    _, c1 = cenario_publicavel(limpo)
    ruins = [LISTA_OK[:9], LISTA_OK[:9] + [LISTA_OK[0]], com_item(3, "talvez"), com_item(4, "atende", ""), com_item(4, "atende", "x" * 301),
             [dict(x, item=11) if x["item"] == 10 else x for x in LISTA_OK], {"itens": LISTA_OK}]
    for itens in ruins:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR185"):
            registrar_conferencia(c1, itens)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR184"):
        registrar_conferencia(c1, lido="2020-01-01T00:00:00+00:00")
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR183"):
        registrar_conferencia(c1, uid=LEITOR)
    with como("authenticated", SEM_PERFIL) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR183"):
            c.execute("select radar_registrar_conferencia(%s, now(), %s)", (c1, json.dumps(LISTA_OK)))
    assert limpo.execute("select conferencia from radar_conteudos where id = %s", (c1,)).fetchone()[0] == {}


def test_banco_confere_sozinho_o_que_da_por_codigo(limpo, conferencia_de_verdade, request):
    """v0.24.0: o que dá para conferir por código vale por cima da lista da IA: [VERIFICAR] (2 e 8), norma citada sem a linha "Fonte
    oficial" com link oficial (2; etapa 5: a seção "Fundamentação legal" dos textos de antes também vale), Informativo sem a fonte (3),
    frase do boletim pago (4) e a capa (6: padrão ou foto da equipe atende; ilustração da IA só com o aviso escrito; sem imagem, não se
    aplica)."""
    a, c1 = cenario_publicavel(limpo)
    situacao = lambda conf: {x["item"]: x["situacao"] for x in conf["itens"]}
    conf = registrar_conferencia(c1)
    assert situacao(conf) == {**{n: "atende" for n in range(1, 11)}, 6: "nao_se_aplica"} and conf["itens"][5]["motivo"] == "Sem imagem de capa."
    limpo.execute("update radar_conteudos set corpo = 'O prazo vai até [VERIFICAR: data] de outubro.' where id = %s", (c1,))
    conf = registrar_conferencia(c1)
    assert situacao(conf)[2] == situacao(conf)[8] == "nao_atende" and "[VERIFICAR]" in conf["itens"][1]["motivo"]
    sem_secao = "Conforme a IN RFB nº 2.290, art. 2º, a CBS vai destacada na nota fiscal."
    limpo.execute("update radar_conteudos set corpo = %s where id = %s", (sem_secao, c1))
    conf = registrar_conferencia(c1)
    assert situacao(conf)[2] == "nao_atende" and "“Fonte oficial”" in conf["itens"][1]["motivo"] and situacao(conf)[8] == "atende"
    # etapa 5: a linha curta "Fonte oficial: <norma> — <link>" (também em negrito ou como item); a seção de antes continua valendo
    for corpo, esperado in [(sem_secao + "\n\nFonte oficial: IN RFB nº 2.290, art. 2º — https://normas.receita.fazenda.gov.br/in-2290", "atende"),
                            (sem_secao + "\n\n**Fonte oficial:** IN RFB nº 2.290 — https://www.gov.br/receita/in-2290.", "atende"),
                            (sem_secao + "\n\n- Fonte oficial: IN RFB nº 2.290 — https://normas.receita.fazenda.gov.br/in-2290", "atende"),
                            (sem_secao + "\n\nFonte oficial: IN RFB nº 2.290 (link a conferir)", "nao_atende"),
                            (sem_secao + "\n\nFonte oficial: IN RFB nº 2.290 — https://www.portal-contabil.test/in-2290", "nao_atende"),
                            (sem_secao + " A fonte oficial: https://www.gov.br/receita/in-2290 fica no meio da frase.", "nao_atende"),
                            (sem_secao + "\n\n## Fundamentação legal\n- IN RFB nº 2.290 (link a conferir)", "nao_atende"),
                            (sem_secao + "\n\n## Fundamentação legal\n- IN RFB nº 2.290 — https://normas.receita.fazenda.gov.br/in-2290", "atende"),
                            ("Texto sem norma nenhuma.", "atende")]:
        limpo.execute("update radar_conteudos set corpo = %s where id = %s", (corpo, c1))
        assert situacao(registrar_conferencia(c1))[2] == esperado, corpo
    # a capa: a da equipe atende; a ilustração da IA, só com o aviso no texto
    limpo.execute("update radar_conteudos set imagem_id = %s where id = %s", (nova_imagem(), c1))
    assert situacao(registrar_conferencia(c1))[6] == "atende"
    limpo.execute("update radar_conteudos set ilustracao_id = imagem_id where id = %s", (c1,))
    conf = registrar_conferencia(c1)
    assert situacao(conf)[6] == "nao_atende" and "Imagem ilustrativa gerada por IA" in conf["itens"][5]["motivo"]
    limpo.execute("update radar_conteudos set corpo = corpo || E'\n\nImagem ilustrativa gerada por IA.' where id = %s", (c1,))
    assert situacao(registrar_conferencia(c1))[6] == "atende"
    # o Informativo sem a fonte citada (o campo Fonte, que sai no fim da notícia com o link)
    i = limpo.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo, status, gerado_por, avisos_ia)
                         values (%s, 'flash', 'Informativo', 'Texto informativo de teste.', 'em_revisao', 'ia', %s) returning id""",
                      (a, json.dumps(["INFORMATIVO (sem fundamentação legal específica): só vai ao site depois da autorização."]))).fetchone()[0]
    limpo.execute("update radar_conteudos set fonte_credito = null where id = %s", (i,))          # a equipe apagou a fonte que veio preenchida
    conf = registrar_conferencia(i)
    assert situacao(conf)[3] == "nao_atende" and "preencha o campo Fonte" in conf["itens"][2]["motivo"]
    limpo.execute("update radar_conteudos set fonte_credito = 'Portal Contábil SC' where id = %s", (i,))
    assert situacao(registrar_conferencia(i))[3] == "atende"
    # o Informativo não tem a seção "Fundamentação legal": a norma que ele só menciona (atribuída à fonte) não leva ✗ no 2 por código
    limpo.execute("update radar_conteudos set corpo = %s where id = %s",
                  ("Segundo o Portal Teste, a Lei Complementar nº 214/2025 trouxe mudanças para as empresas do comércio.", i))
    assert limpo.execute("select radar_cita_norma(corpo) from radar_conteudos where id = %s", (i,)).fetchone()[0] is True
    assert situacao(registrar_conferencia(i))[2] == "atende"
    assert situacao(registrar_conferencia(i, com_item(2, "nao_atende", "Apresenta obrigação legal.")))[2] == "nao_atende"   # a IA ainda reprova
    # a frase do boletim pago (4), mesmo que a lista diga que atende
    carregar_fontes_novas(limpo, request)
    boletim = ("Na nossa avaliação a mudança exige atenção redobrada dos departamentos fiscais que ainda não revisaram os cadastros "
               "de produtos antes da virada do ano.")
    limpo.execute("""insert into radar_capturas (fonte_id, url, titulo, texto, hash_titulo) select id, 'https://www.itcnet.com.br/?radar=conf',
                     'Matéria do boletim', %s, md5('conf') from radar_fontes where slug = 'itc-email'""", (boletim,))
    limpo.execute("update radar_conteudos set corpo = %s where id = %s", ("Resumo: " + boletim, i))
    assert situacao(registrar_conferencia(i))[4] == "nao_atende"


def test_criterio_6_reconhece_a_imagem_da_ia_com_o_aviso_e_a_guardada_fora_da_publicacao(limpo, conferencia_de_verdade):
    """v0.25.0 (etapa 6): a imagem da IA desta versão é a imagem da publicação inteira, em 3:2, com o aviso desenhado pela tela, e fica
    guardada como a ilustração (imagem_id = ilustracao_id): o critério 6 atende sem o aviso escrito no texto. Trocada pela capa padrão ou
    pela foto da equipe, ela continua guardada (ilustracao_id) e o critério continua atendendo. A capa montada antes da v0.25.0 com a
    ilustração crua (1200×630) ao fundo continua pedindo o aviso no texto (✗ sem ele), também se a crua for posta como imagem."""
    _, c1 = cenario_publicavel(limpo)
    def imagem(largura, altura):
        with como("authenticated", EDITOR) as c:
            return c.execute("insert into radar_imagens (dados, largura, altura) values (%s, %s, %s) returning id", (PIXEL, largura, altura)).fetchone()[0]
    def criterio(imagem_id, ilustracao_id):
        limpo.execute("update radar_conteudos set imagem_id = %s, ilustracao_id = %s where id = %s", (imagem_id, ilustracao_id, c1))
        item = registrar_conferencia(c1)["itens"][5]
        return item["situacao"], item["motivo"]
    # (a imagem que fica sem uso sai do banco sozinha: cada passo usa imagens novas)
    ia = imagem(1500, 1000)
    assert criterio(ia, ia) == ("atende", "Imagem gerada por IA, inteira, com o aviso “Imagem ilustrativa gerada por IA” no canto (colocado pelo Radar).")
    versao = limpo.execute("select radar_conferencia_versao(c) from radar_conteudos c where id = %s", (c1,)).fetchone()[0]
    for tamanho in ((1200, 630), (900, 600)):                             # a capa padrão ou a foto no lugar: a da IA continua guardada
        assert criterio(imagem(*tamanho), ia) == ("atende", "Capa padrão da Artecon ou imagem enviada pela equipe (a imagem da IA está guardada, fora da publicação).")
        assert limpo.execute("select radar_conferencia_versao(c) from radar_conteudos c where id = %s", (c1,)).fetchone()[0] == versao
    assert criterio(imagem(1200, 630), None)[0] == "atende"
    crua, montada = imagem(1200, 630), imagem(1200, 630)
    situacao, motivo = criterio(montada, crua)                            # a capa antiga, montada com a ilustração crua
    assert situacao == "nao_atende" and "“Usar a imagem da IA de novo”" in motivo and "escreva o aviso no fim do texto" in motivo
    limpo.execute("update radar_conteudos set corpo = corpo || E'\n\nImagem ilustrativa gerada por IA.' where id = %s", (c1,))
    assert criterio(montada, crua)[0] == "atende"                         # o aviso escrito no texto, como antes
    limpo.execute("update radar_conteudos set corpo = replace(corpo, E'\n\nImagem ilustrativa gerada por IA.', '') where id = %s", (c1,))
    assert criterio(crua, crua)[0] == "nao_atende"                        # a crua (sem aviso) como imagem: não dá para garantir o aviso


def test_revisei_e_assumo_so_o_administrador_com_motivo_e_fica_no_historico(limpo, conferencia_de_verdade):
    """v0.24.0: com critério que não atende (ou sem a lista da IA), só o administrador libera a aprovação ("Revisei e assumo"), com o
    motivo (10 a 500 caracteres), para a versão do texto que estava na tela; fica na conferência e na trilha de auditoria. Não passa por
    cima das travas de antes: [VERIFICAR] continua impedindo."""
    _, c1 = cenario_publicavel(limpo)
    registrar_conferencia(c1, com_item(8, "nao_atende", "O prazo citado já venceu."))
    lido = lido_de(limpo, c1)
    with como("authenticated", EDITOR) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR186: só o administrador"):
            c.execute("select radar_assumir_conferencia(%s, 'Conferi o prazo no site da Receita.', %s)", (c1, lido))
    with como("authenticated", ADMIN) as c:
        for curto in (None, "", "ok", "  curto   "):
            with pytest.raises(psycopg.errors.RaiseException, match="RADAR187"):
                c.execute("select radar_assumir_conferencia(%s, %s, %s)", (c1, curto, lido))
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR184"):
            c.execute("select radar_assumir_conferencia(%s, 'Conferi o prazo no site da Receita.', '2020-01-01')", (c1,))
        conf = c.execute("select radar_assumir_conferencia(%s, '  Conferi o prazo no site da Receita.  ', %s)", (c1, lido)).fetchone()[0]
    assert conf["assumida"]["por"] == ADMIN and conf["assumida"]["motivo"] == "Conferi o prazo no site da Receita."
    assert lido_de(limpo, c1) == lido
    trilha = limpo.execute("""select usuario::text, depois->'conferencia'->'assumida'->>'motivo' from radar_auditoria
                              where tabela = 'radar_conteudos' and acao = 'UPDATE' order by id desc limit 1""").fetchone()
    assert trilha == (ADMIN, "Conferi o prazo no site da Receita.")
    assert aprovar(c1) == (EDITOR,)                                              # liberado: a editora aprova
    # o texto mudou: o "Revisei e assumo" era daquela versão
    limpo.execute("update radar_conteudos set corpo = 'Texto novo [VERIFICAR: prazo].' where id = %s", (c1,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR139"):       # a trava do [VERIFICAR] vem antes e continua
        aprovar(c1)
    with como("authenticated", ADMIN) as c:
        c.execute("select radar_assumir_conferencia(%s, 'Assumo a conferência deste texto.', %s)", (c1, lido_de(limpo, c1)))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR139"):
        aprovar(c1)
    limpo.execute("update radar_conteudos set corpo = 'Texto novo, sem marca.' where id = %s", (c1,))
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR181"):
        aprovar(c1)


def test_informativo_so_e_aprovado_depois_da_autorizacao_do_administrador(limpo):
    """v0.24.0 (decisão do dono): o texto INFORMATIVO (o primeiro aviso começa com "INFORMATIVO") não é aprovado, nem pela API, enquanto
    o administrador não autoriza a publicação do assunto (RADAR180); a autorização é o "Publicar mesmo assim" (só ele, com o motivo,
    gravado no assunto e na trilha). O aviso não sai do texto: os pontos a conferir só crescem."""
    a = novo_assunto(limpo, situacao="em_verificacao")
    marca = "INFORMATIVO (sem fundamentação legal específica), escrito a partir de fonte NÃO oficial (Portal): só vai ao site depois da autorização."
    i = limpo.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo, status, gerado_por, avisos_ia)
                         values (%s, 'flash', 'Informativo', 'Texto informativo de teste.', 'em_revisao', 'ia', %s) returning id""",
                      (a, json.dumps([marca]))).fetchone()[0]
    for uid in (EDITOR, ADMIN):
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR180: texto Informativo"):
            aprovar(i, uid)
    with como("authenticated", EDITOR) as c:                                     # tirar o aviso por fora não adianta
        c.execute("update radar_conteudos set avisos_ia = '[]' where id = %s", (i,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR120"):
            c.execute("select radar_liberar_sem_fundamentacao(%s, 'Liberado pela editora sem o administrador')", (a,))
    assert limpo.execute("select avisos_ia->>0 from radar_conteudos where id = %s", (i,)).fetchone()[0] == marca
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR180"):
        aprovar(i)
    with como("authenticated", ADMIN) as c:
        c.execute("select radar_liberar_sem_fundamentacao(%s, 'Informativo conferido e autorizado')", (a,))
    assert limpo.execute("select liberado_sem_base_por::text, liberado_sem_base_motivo from radar_assuntos where id = %s",
                         (a,)).fetchone() == (ADMIN, "Informativo conferido e autorizado")
    assert limpo.execute("""select count(*) from radar_auditoria where tabela = 'radar_assuntos' and usuario = %s
                            and depois->>'liberado_sem_base_motivo' = 'Informativo conferido e autorizado'""", (ADMIN,)).fetchone()[0] == 1
    assert aprovar(i) == (EDITOR,)
    # desfeita a liberação, o Informativo aprovado volta para a revisão (e o texto normal aprovado do assunto, não)
    n = novo_conteudo(limpo, a)
    assert aprovar(n) == (EDITOR,)
    with como("authenticated", ADMIN) as c:
        c.execute("select radar_liberar_sem_fundamentacao(%s, null)", (a,))
    assert limpo.execute("select id, status from radar_conteudos where id in (%s, %s) order by id", (i, n)).fetchall() == [(i, "em_revisao"), (n, "aprovado")]
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR180"):
        aprovar(i)


def test_setup_de_novo_mantem_a_conferencia_e_a_trava(limpo, conferencia_de_verdade):
    """v0.24.0: o setup roda de novo sem perder a conferência gravada (etapa 5: nem a revisão editorial) nem a trava da aprovação."""
    _, c1 = fundamentado(limpo)
    registrar_conferencia(c1)
    registrar_editorial(c1)
    _, c2 = fundamentado(limpo)
    r = psql(SETUP)
    assert r.returncode == 0, r.stderr
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR181"):
        aprovar(c2)
    assert limpo.execute("select conferencia->'editorial'->>'feita' from radar_conteudos where id = %s", (c1,)).fetchone()[0] == "true"
    assert aprovar(c1) == (EDITOR,)


# ------------------------------------------------ v0.24.0 (etapa 5): revisão editorial automática
PERGUNTAS_OK = [{"n": n, "situacao": "ok", "motivo": f"Pergunta {n} sem problema."} for n in range(1, 11)]


def registrar_editorial(conteudo, revisao=None, uid=EDITOR, lido=None):
    """Grava a revisão editorial como a função radar-ia grava (com o login de quem pediu)."""
    revisao = revisao if revisao is not None else {"feita": True, "perguntas": PERGUNTAS_OK, "reescritos": [], "modelo": "claude-sonnet-4-6"}
    with como("authenticated", uid) as c:
        if lido is None:
            lido = c.execute("select atualizado_em from radar_conteudos where id = %s", (conteudo,)).fetchone()[0]
        return c.execute("select radar_registrar_revisao_editorial(%s, %s, %s)", (conteudo, lido, json.dumps(revisao))).fetchone()[0]


def test_revisao_editorial_gravada_validada_e_so_informativa(limpo, conferencia_de_verdade):
    """v0.24.0 (etapa 5): a revisão editorial da IA (as 10 perguntas, cada uma "ok" ou "ajustado" com o motivo, e os trechos reescritos;
    ou "não feita", com o motivo) fica no conteúdo (conferencia->'editorial') só pela função, com a versão do corpo do texto, quando e quem;
    as chaves de fora não ficam; gravar não muda a data do conteúdo. É validada (RADAR189), só o editor e o administrador gravam (RADAR188)
    e só para o texto que foi à IA (RADAR190); o UPDATE direto e o INSERT não a forjam. Não trava nem libera a aprovação (quem trava é a
    Conferência das Diretrizes), e gravar a Conferência ou o "Revisei e assumo" depois não a apaga. Mudou o corpo, a versão muda (a tela
    avisa que a revisão era da versão anterior); só o título, não."""
    _, c1 = fundamentado(limpo)
    lido = lido_de(limpo, c1)
    ajustada = [dict(x, situacao="ajustado", motivo="Abertura genérica reescrita.") if x["n"] == 1 else x for x in PERGUNTAS_OK]
    e = registrar_editorial(c1, {"feita": True, "perguntas": list(reversed(ajustada)), "modelo": "claude-sonnet-4-6", "extra": "fora",
                                 "reescritos": [{"antes": "Nesse cenário, a CBS muda.", "depois": "A CBS muda em 2027."},
                                                {"antes": "Frase que sobrava.", "depois": ""}]})
    versao = limpo.execute("select radar_texto_versao(c), md5(c.corpo) from radar_conteudos c where id = %s", (c1,)).fetchone()
    assert e["feita"] is True and e["versao"] == versao[0] == versao[1] and e["por"] == EDITOR and e["modelo"] == "claude-sonnet-4-6"
    assert [x["n"] for x in e["perguntas"]] == list(range(1, 11)) and e["perguntas"][0] == {"n": 1, "situacao": "ajustado", "motivo": "Abertura genérica reescrita."}
    assert e["reescritos"] == [{"antes": "Nesse cenário, a CBS muda.", "depois": "A CBS muda em 2027."}, {"antes": "Frase que sobrava.", "depois": ""}]
    assert "extra" not in e and set(e) == {"feita", "versao", "em", "por", "modelo", "perguntas", "reescritos"}
    conf = limpo.execute("select conferencia from radar_conteudos where id = %s", (c1,)).fetchone()[0]
    assert conf == {"editorial": e} and lido_de(limpo, c1) == lido                     # não muda a data do conteúdo
    # só informativa: sem a Conferência, a aprovação continua travada; com ela, aprova mesmo com a revisão "não feita"
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR181"):
        aprovar(c1)
    nao = registrar_editorial(c1, {"feita": False, "motivo": "  Não coube no tempo do pedido. O texto ficou como estava.  "})
    assert nao["feita"] is False and nao["motivo"] == "Não coube no tempo do pedido. O texto ficou como estava." and "perguntas" not in nao
    registrar_conferencia(c1)
    assert limpo.execute("select conferencia->'editorial' from radar_conteudos where id = %s", (c1,)).fetchone()[0] == nao   # a Conferência não a apaga
    with como("authenticated", ADMIN) as c:
        c.execute("select radar_assumir_conferencia(%s, 'Conferi e assumo este texto.', %s)", (c1, lido_de(limpo, c1)))
    assert limpo.execute("select conferencia->'editorial' from radar_conteudos where id = %s", (c1,)).fetchone()[0] == nao
    assert aprovar(c1) == (EDITOR,)
    # validação: as 10 perguntas, cada uma uma vez, "ok" ou "ajustado", o motivo até 300; até 12 trechos; "não feita" com o motivo
    _, c2 = fundamentado(limpo)
    ruins = [{"feita": True, "perguntas": PERGUNTAS_OK[:9]}, {"feita": True, "perguntas": PERGUNTAS_OK[:9] + [PERGUNTAS_OK[0]]},
             {"feita": True, "perguntas": [dict(x, situacao="talvez") if x["n"] == 3 else x for x in PERGUNTAS_OK]},
             {"feita": True, "perguntas": [dict(x, motivo=" ") if x["n"] == 4 else x for x in PERGUNTAS_OK]},
             {"feita": True, "perguntas": [dict(x, motivo="x" * 301) if x["n"] == 4 else x for x in PERGUNTAS_OK]},
             {"feita": True, "perguntas": [dict(x, n=11) if x["n"] == 10 else x for x in PERGUNTAS_OK]},
             {"feita": True, "perguntas": PERGUNTAS_OK, "reescritos": [{"antes": "a", "depois": "b"}] * 13},
             {"feita": True, "perguntas": PERGUNTAS_OK, "reescritos": [{"antes": "", "depois": "b"}]},
             {"feita": True, "perguntas": PERGUNTAS_OK, "reescritos": [{"antes": "a", "depois": "b" * 401}]},
             {"feita": True, "perguntas": PERGUNTAS_OK, "reescritos": {"antes": "a"}},
             {"feita": False}, {"feita": False, "motivo": ""}, {"feita": "sim", "perguntas": PERGUNTAS_OK}, [PERGUNTAS_OK],
             {"feita": True, "perguntas": PERGUNTAS_OK, "reescritos": [{"antes": "x" * 400, "depois": "y" * 400}] * 12, "modelo": "m" * 4000}]
    for ruim in ruins:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR189"):
            registrar_editorial(c2, ruim)
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR190"):
        registrar_editorial(c2, lido="2020-01-01T00:00:00+00:00")
    for uid in (LEITOR, SEM_PERFIL):
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR188"):
            registrar_editorial(c2, uid=uid, lido=lido_de(limpo, c2))
    with como("authenticated", EDITOR) as c:                                         # ninguém forja por fora
        c.execute("update radar_conteudos set conferencia = conferencia || %s where id = %s", (json.dumps({"editorial": {"feita": True}}), c2))
        a = c.execute("select assunto_id from radar_conteudos where id = %s", (c2,)).fetchone()[0]
        n = c.execute("""insert into radar_conteudos (assunto_id, formato, titulo, corpo, status, conferencia)
                         values (%s, 'flash', 'Novo', 'Texto novo.', 'em_revisao', %s) returning id""",
                      (a, json.dumps({"editorial": {"feita": True, "perguntas": PERGUNTAS_OK}}))).fetchone()[0]
    assert limpo.execute("select conferencia from radar_conteudos where id in (%s, %s) order by id", (c2, n)).fetchall() == [({},), ({},)]
    # a versão é a do corpo: o título novo (escolhido entre as sugestões) não a muda; o texto editado à mão, sim
    registrar_editorial(c2)
    guardada = limpo.execute("select conferencia->'editorial'->>'versao' from radar_conteudos where id = %s", (c2,)).fetchone()[0]
    limpo.execute("update radar_conteudos set titulo = 'Outro título sugerido' where id = %s", (c2,))
    assert limpo.execute("select radar_texto_versao(c) from radar_conteudos c where id = %s", (c2,)).fetchone()[0] == guardada
    limpo.execute("update radar_conteudos set corpo = corpo || ' Frase escrita à mão.' where id = %s", (c2,))
    assert limpo.execute("select radar_texto_versao(c) from radar_conteudos c where id = %s", (c2,)).fetchone()[0] != guardada
    assert limpo.execute("select conferencia->'editorial'->>'versao' from radar_conteudos where id = %s", (c2,)).fetchone()[0] == guardada
    assert limpo.execute("""select count(*) from radar_auditoria where tabela = 'radar_conteudos' and registro_id = %s and acao = 'UPDATE'
                            and usuario = %s and depois->'conferencia'->'editorial'->>'feita' = 'true'""", (str(c2), EDITOR)).fetchone()[0] == 1


# ------------------------------------------------------------------- v0.28.0: "+ Nova peça" e "Sócio(a) da Artecon"
def criar_peca(peca, uid=ADMIN):
    """A "+ Nova peça" da Pauta (radar_pauta_criar), como a tela chama."""
    with como("authenticated", uid) as c:
        return c.execute("select radar_pauta_criar(%s)", (json.dumps(peca),)).fetchone()[0]


def test_pauta_criar_so_admin_dia_livre_de_hoje_em_diante_e_mesma_conferencia_da_importacao(pauta):
    """v0.28.0: "+ Nova peça". Só o administrador cria; o dia é de hoje em diante (de Brasília) e sem peça nenhuma (uma peça por dia: a
    cancelada também ocupa o dia); os campos passam pela mesma conferência da importação do calendário, com o assunto obrigatório, e o
    erro diz o campo, nunca o conteúdo. A peça nasce planejada, na hora padrão, sem pessoas, sem aprovação e sem envio (o que vier a mais
    no pedido não conta), e vai à trilha como a importada (sem o plano)."""
    db = pauta
    d = hoje(db)
    dia = lambda n: (d + timedelta(days=n)).isoformat()
    db.execute("""update radar_config set valor = valor || '{"hora_padrao": "08:15"}' where chave = 'pauta'""")
    pid = criar_peca({"data": dia(1), "tipo": "bastidor", "formato": "foto", "assunto": "  Bastidor da equipe \n", "objetivo": " aproximar ",
                      "quem_aparece": "Ana Teste", "observacao": "lembrete do plano",
                      # o que a tela não manda e o banco não aceita daqui: a situação, a hora, as pessoas, a aprovação
                      "situacao": "aprovada", "hora": "03:00", "pessoas": [1], "aprovado_modo": "agendar"})
    assert db.execute("""select data, situacao, hora::text, criado_por::text, pessoas, assunto, objetivo, quem_aparece, observacao,
                                aprovado_por, aprovado_modo, aprovado_canais from radar_pauta_pecas where id = %s""", (pid,)).fetchone() == \
        (d + timedelta(days=1), "planejada", "08:15:00", ADMIN, [], "Bastidor da equipe", "aproximar", "Ana Teste", "lembrete do plano",
         None, None, [])
    assert db.execute("select count(*) from radar_redes_envios").fetchone()[0] == 0                # não publica nem agenda nada
    trilha = db.execute("select acao, usuario::text, depois from radar_auditoria where tabela = 'radar_pauta_pecas'").fetchall()
    assert [(a, u) for a, u, _ in trilha] == [("INSERT", ADMIN)]
    assert not {"assunto", "objetivo", "observacao", "quem_aparece"} & set(trilha[0][2])
    assert "Ana" not in json.dumps(trilha[0][2], ensure_ascii=False) and "lembrete" not in json.dumps(trilha[0][2], ensure_ascii=False)
    # hoje (de Brasília) pode; ontem, não
    reel = criar_peca({"data": dia(0), "tipo": "reel", "formato": "reel", "assunto": "Reel de hoje"})
    with pytest.raises(psycopg.errors.RaiseException, match="RADAR192: esse dia já passou"):
        criar_peca({"data": dia(-1), "tipo": "bastidor", "formato": "foto", "assunto": "Ontem"})
    # uma peça por dia, também com a peça cancelada (Reabrir é o caminho)
    cancelada = criar_peca({"data": dia(2), "tipo": "educativo", "formato": "carrossel", "assunto": "Educativo"})
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_pauta_pecas set situacao = 'cancelada' where id = %s", (cancelada,))
    for n in (1, 2):
        with pytest.raises(psycopg.errors.RaiseException, match=re.escape(f"RADAR193: já existe uma peça em {(d + timedelta(days=n)).strftime('%d/%m/%Y')}: "
                                                                          "é uma peça por dia (abra a peça desse dia; se ela estiver cancelada, use Reabrir)")):
            criar_peca({"data": dia(n), "tipo": "bastidor", "formato": "foto", "assunto": "Outra no mesmo dia"})
    # a corrida: a peça gravada direto por outra tela (o INSERT do editor, que não passa pela trava da importação) e ainda não
    # confirmada; a "+ Nova peça" espera e, quando a outra confirma, devolve o recado (e não o erro cru da chave única)
    import threading
    import time
    outra, resultado = conectar(autocommit=False), []
    def tentar():
        try:
            resultado.append(criar_peca({"data": dia(5), "tipo": "reel", "formato": "reel", "assunto": "Corrida"}))
        except Exception as e:                                                                 # noqa: BLE001 (o teste confere o tipo)
            resultado.append(e)
    try:
        outra.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"role": "authenticated", "sub": EDITOR}),))
        outra.execute("set local role authenticated")
        outra.execute("insert into radar_pauta_pecas (data, tipo, formato) values (%s, 'bastidor', 'foto')", (d + timedelta(days=5),))
        fio = threading.Thread(target=tentar)
        fio.start()
        for _ in range(100):                                                                   # até a "+ Nova peça" esperar a outra
            if db.execute("select count(*) from pg_stat_activity where wait_event_type = 'Lock' and query like '%radar_pauta_criar%'").fetchone()[0]:
                break
            time.sleep(0.05)
        else:
            pytest.fail("a + Nova peça não esperou a outra gravação")
        outra.commit()
        fio.join(timeout=10)
    finally:
        outra.close()
    assert len(resultado) == 1 and isinstance(resultado[0], psycopg.errors.RaiseException), resultado
    assert f"RADAR193: já existe uma peça em {(d + timedelta(days=5)):%d/%m/%Y}: é uma peça por dia (recarregue a página)" in str(resultado[0])
    assert db.execute("select count(*), min(criado_por::text) from radar_pauta_pecas where data = %s", (d + timedelta(days=5),)).fetchone() == (1, EDITOR)
    # só o administrador: o editor (que importa o calendário) e o leitor, não; o visitante e a chave do robô nem chamam
    base = {"data": dia(6), "tipo": "bastidor", "formato": "foto", "assunto": "Bastidor"}
    for uid in (EDITOR, LEITOR, SEM_PERFIL):
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="RADAR191: só o administrador cria peça nova"):
            criar_peca(base, uid)
    for papel in ("anon", "service_role"):
        with como(papel) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select radar_pauta_criar(%s)", (json.dumps(base),))
    # a mesma conferência da importação (radar_pauta_linha_invalida), mais o assunto obrigatório: nada é gravado
    antes = db.execute("select count(*), max(atualizado_em) from radar_pauta_pecas").fetchone()
    for ruim, msg in [(dict(base, tipo="Segredo <b>da equipe</b>"), "confira o campo “tipo”"), (dict(base, formato="tiktok"), "“formato”"),
                      (dict(base, data="2026-02-30"), "“dia”"), (dict(base, data="17/10/2026"), "“dia”"), (dict(base, data="1999-12-31"), "“dia”"),
                      (dict(base, data="2101-01-01"), "“dia”"), (dict(base, assunto="Segredo " * 200), "“assunto”"),
                      (dict(base, quem_aparece=["Segredo"]), "“quem aparece”"), (dict(base, objetivo="Segredo " * 30), "“objetivo”"),
                      (dict(base, observacao="Segredo " * 200), "“observação”"), (dict(base, assunto="   "), "escreva o assunto"),
                      (dict(base, assunto=" \n\t "), "escreva o assunto"), ({k: v for k, v in base.items() if k != "assunto"}, "escreva o assunto"),
                      (["Segredo solto"], "envie o dia, o tipo, o formato e o assunto")]:
        with pytest.raises(psycopg.errors.RaiseException, match="RADAR192") as erro:
            criar_peca(ruim)
        assert msg in str(erro.value) and "Segredo" not in str(erro.value), str(erro.value)
    assert db.execute("select count(*), max(atualizado_em) from radar_pauta_pecas").fetchone() == antes
    # o reel novo abre como qualquer reel: falta o roteiro e a gravação (o quadro do corretor de vídeo)
    falta = conferir(reel, uid=ADMIN)
    assert "Reel: cole o roteiro" in falta and "Reel: envie a gravação (Corretor de vídeo)" in falta


def test_importar_depois_de_peca_criada_a_mao(pauta):
    """v0.28.0: a importação do calendário trata a peça criada à mão como qualquer outra do mesmo dia: ainda planejada, recebe o tipo, o
    formato e o plano do arquivo (a hora fica); já em produção, fica como está. Nunca duplica o dia nem apaga peça."""
    db = pauta
    d = hoje(db)
    dia = lambda n: (d + timedelta(days=n)).isoformat()
    p1 = criar_peca({"data": dia(10), "tipo": "bastidor", "formato": "foto", "assunto": "Peça feita à mão"})
    p2 = criar_peca({"data": dia(11), "tipo": "reel", "formato": "reel", "assunto": "Reel feito à mão"})
    with como("authenticated", ADMIN) as c:
        c.execute("update radar_pauta_pecas set hora = '11:00' where id = %s", (p1,))            # a hora não leva para a produção
    with como("authenticated", EDITOR) as c:
        c.execute("update radar_pauta_pecas set roteiro = 'Fala: o prazo vence no dia 20.' where id = %s", (p2,))
    assert db.execute("select array_agg(situacao order by id) from radar_pauta_pecas").fetchone()[0] == ["planejada", "em_producao"]
    linhas = [_linha(2, dia(10), "quem_cuida", "foto"), _linha(3, dia(11), "educativo", "carrossel"), _linha(4, dia(12), "captacao", "imagem")]
    assert importar(linhas) == {"novas": 1, "alteradas": 1, "iguais": 0, "mantidas": 1}
    assert db.execute("""select tipo, formato, assunto, quem_aparece, objetivo, hora::text, situacao, criado_por::text
                         from radar_pauta_pecas where id = %s""", (p1,)).fetchone() == \
        ("quem_cuida", "foto", "Bastidor da equipe", "Ana Teste", "aproximar", "11:00:00", "planejada", ADMIN)
    assert db.execute("select tipo, formato, assunto, situacao from radar_pauta_pecas where id = %s", (p2,)).fetchone() == \
        ("reel", "reel", "Reel feito à mão", "em_producao")
    assert db.execute("select count(*), count(distinct data) from radar_pauta_pecas").fetchone() == (3, 3)


def test_socio_dispensa_os_termos_mas_nao_ativa_nem_menor(pauta):
    """v0.28.0: o(a) sócio(a) da Artecon (radar_pessoas.socio), maior de idade e ativo(a), não precisa do termo de uso de imagem (nenhuma
    data, canal ou finalidade, nem a revogação) em nenhum tipo de peça: a peça fica pronta, é aprovada e sai. Continuam valendo "Ativa" e
    a idade (menor: o termo volta a ser pedido). Tirar a marca faz o termo voltar. Só o administrador marca; a marca vai à trilha sem o
    nome; o leitor e a chave do robô continuam sem ler as pessoas."""
    db = pauta
    with como("authenticated", ADMIN) as c:
        bruno = c.execute("insert into radar_pessoas (nome, nome_na_peca) values ('Bruno Exemplo', 'Bruno') returning id").fetchone()[0]
        assert c.execute("update radar_pessoas set socio = true where id = %s", (bruno,)).rowcount == 1
    trilha = db.execute("select acao, usuario::text, antes, depois from radar_auditoria where tabela = 'radar_pessoas' order by id").fetchall()
    assert [(a, u) for a, u, _, _ in trilha] == [("INSERT", ADMIN), ("UPDATE", ADMIN)]
    assert (trilha[1][2]["socio"], trilha[1][3]["socio"]) == (False, True)
    assert not re.search("Bruno|Exemplo", json.dumps([x for *_, a, b in trilha for x in (a, b)], ensure_ascii=False))
    with como("authenticated", EDITOR) as c:                                                   # o editor lê, mas não marca nem desmarca
        assert c.execute("select socio from radar_pessoas where id = %s", (bruno,)).fetchone()[0] is True
        assert c.execute("update radar_pessoas set socio = false where id = %s", (bruno,)).rowcount == 0
    d = hoje(db) + timedelta(days=3)
    tipos = ["noticia", "reel", "quem_cuida", "agenda", "bastidor", "educativo", "captacao", "data_equipe", "sem_post"]
    def termo(tipo="bastidor", canal="instagram", uid=EDITOR):
        with como("authenticated", uid) as c:
            return c.execute("select radar_pauta_termo_ok(%s, %s, %s, %s)", (bruno, tipo, canal, d)).fetchone()[0]
    assert {(t, canal): termo(t, canal) for t in tipos for canal in ("instagram", "facebook")} == \
        {(t, canal): None for t in tipos for canal in ("instagram", "facebook")}             # sem termo nenhum: dispensado
    pid = nova_peca(db, dias=3, pessoas=[bruno])
    vista = lambda: db.execute("""select termos_dispensados, motivo_instagram, motivo_facebook from radar_v_pauta_pessoas
                                  where peca_id = %s and pessoa_id = %s""", (pid, bruno)).fetchone()
    assert vista() == (True, None, None)
    assert conferir(pid) == []                                                                  # nenhum item de termo
    marcar_pronta(db, pid)
    r = aprovar_peca(db, pid)
    ig = r["envios"]["instagram"]
    vencer(db, ig)
    assert iniciar(ig)["peca_id"] == pid                                                       # e sai pela agenda
    outra = nova_peca(db, dias=4, pessoas=[bruno])
    # o sobrenome no texto continua barrado, com o recado do "Nome na peça" do cadastro (sócio(a) não tem termo)
    apoio = lambda texto: db.execute("update radar_pauta_pecas set apoio = %s where id = %s", (texto, outra))
    apoio("Uma conversa com o Bruno Exemplo.")
    assert conferir(outra) == ["O “Nome na peça” do(a) sócio(a) é só “Bruno”: tire o sobrenome (ou mude o Nome na peça em Pessoas e termos)"]
    # inativo(a): a marca não passa por cima de "Ativa"
    db.execute("update radar_pessoas set ativo = false where id = %s", (bruno,))
    assert termo() == "pessoa inativa" and vista() == (True, "pessoa inativa", "pessoa inativa")
    db.execute("update radar_pessoas set ativo = true where id = %s", (bruno,))
    # menor de idade: a dispensa não vale
    db.execute("update radar_pessoas set menor = true where id = %s", (bruno,))
    assert termo() == "sem termo assinado" and vista() == (False, "sem termo assinado", "sem termo assinado")
    assert "O termo autoriza só “Bruno”: tire o sobrenome" in conferir(outra)                 # e o recado do sobrenome volta a ser o do termo
    db.execute("update radar_pessoas set menor = false where id = %s", (bruno,))
    apoio("Uma conversa com o Bruno.")
    assert conferir(outra) == []
    # a revogação também não conta para sócio(a): quem tira da Pauta é "Ativa"
    db.execute("update radar_pessoas set termo_revogado_em = %s where id = %s", (hoje(db) - timedelta(days=1), bruno))
    assert termo() is None and termo("captacao", "facebook") is None
    # sem a marca, o termo volta a ser pedido
    db.execute("update radar_pessoas set socio = false where id = %s", (bruno,))
    assert "“Bruno” (Instagram): sem termo assinado" in conferir(outra)
    assert vista() == (False, "sem termo assinado", "sem termo assinado")
    # o leitor continua sem ler as pessoas; a chave do robô e o visitante nem a tabela
    db.execute("update radar_pessoas set socio = true where id = %s", (bruno,))
    assert termo(uid=LEITOR) == "pessoa não cadastrada"
    with como("authenticated", LEITOR) as c:
        assert c.execute("select count(*) from radar_pessoas").fetchone()[0] == 0
        assert c.execute("select count(*) from radar_v_pauta_pessoas").fetchone()[0] == 0
    for papel in ("service_role", "anon"):
        with como(papel) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("select socio from radar_pessoas")


def test_setup_v0_28_0_sobre_o_banco_da_v0_27_0_mantem_os_dados(pauta):
    """v0.28.0: o setup é aplicado em produção rodando o arquivo inteiro de novo. Sobre o banco da v0.27.0 (o setup v0.25.0: sem a
    coluna socio, sem a termos_dispensados na vista e sem as três funções novas), ele roda sem erro, duas vezes, e não perde nada: as
    pessoas (com socio = false), as peças e o vídeo pronto ficam como estavam, e a "+ Nova peça" passa a funcionar."""
    db = pauta
    ana = pessoa_do_corretor(db, "Ana Teste", "Ana")
    pid = nova_peca(db, dias=5, tipo="reel", formato="reel", roteiro=FALA_REEL, pessoas=[ana])
    vid = video_pronto(db, pid, ana)
    contar = lambda: db.execute("""select (select count(*) from radar_pessoas), (select count(*) from radar_pauta_pecas),
                                          (select count(*) from radar_videos), (select count(*) from radar_auditoria)""").fetchone()
    estado = lambda: db.execute("""select v.situacao, v.sha256, v.arquivos_apagados, p.situacao, p.versao_publicavel, pe.termo_corretor_em
                                   from radar_videos v join radar_pauta_pecas p on p.id = v.peca_id join radar_pessoas pe on pe.id = %s
                                   where v.id = %s""", (ana, vid)).fetchone()
    try:
        # o banco como a v0.27.0 deixou (a vista de antes, sem a coluna nova)
        db.execute("drop view radar_v_pauta_pessoas")
        db.execute("alter table radar_pessoas drop column socio")
        db.execute("""create view radar_v_pauta_pessoas with (security_invoker = true) as
                      select p.id as peca_id, p.data, pe.id as pessoa_id, pe.nome_na_peca,
                             radar_pauta_termo_ok(pe.id, p.tipo, 'instagram', p.data) as motivo_instagram,
                             radar_pauta_termo_ok(pe.id, p.tipo, 'facebook',  p.data) as motivo_facebook
                      from radar_pauta_pecas p cross join lateral unnest(p.pessoas) as u(pessoa_id) join radar_pessoas pe on pe.id = u.pessoa_id""")
        for f in ("radar_pauta_criar(jsonb)", "radar_pauta_linha_invalida(jsonb)", "radar_pauta_hora_padrao()"):
            db.execute(f"drop function {f}")
        antes, como_estava = contar(), estado()
        for _ in range(2):
            r = psql(SETUP)
            assert r.returncode == 0, r.stderr
            assert contar() == antes and estado() == como_estava
        assert db.execute("select socio from radar_pessoas where id = %s", (ana,)).fetchone()[0] is False
        assert db.execute("select termos_dispensados from radar_v_pauta_pessoas where pessoa_id = %s", (ana,)).fetchone()[0] is False
        # (o setup registra a versão dele: v0.33.0, que traz junto os da v0.28.0 a v0.32.0)
        assert db.execute("select versao from radar_instalacoes order by id desc limit 2").fetchall() == [("v0.33.0",), ("v0.33.0",)]
        assert criar_peca({"data": (hoje(db) + timedelta(days=9)).isoformat(), "tipo": "bastidor", "formato": "foto", "assunto": "Depois do setup"})
    finally:
        assert psql(SETUP).returncode == 0                                                     # o banco dos testes volta inteiro


# ------------------------------------------------- v0.30.0: possível prorrogação na agenda de obrigações
def casa(db, texto, obrigacoes=None):
    """As obrigações que a regra do aviso de prorrogação acha no texto (radar_prorrogacao_obrigacoes, só do dono); sem a lista, a
    agenda que está no banco (a padrão)."""
    if obrigacoes is None:
        obrigacoes = db.execute("select valor from radar_config where chave = 'obrigacoes'").fetchone()[0]
    return db.execute("select radar_prorrogacao_obrigacoes(%s, %s)", (texto, json.dumps(obrigacoes))).fetchone()[0]


TREZE = ["13º Salário (1ª parcela)", "13º Salário (2ª parcela)"]
DEFIS = "DEFIS - Declaração de Informações Socioeconômicas e Fiscais"
DASN = "DASN-SIMEI - Declaração Anual do MEI"
IRRF = ["IRRF (Rendimento Serviço Prestado Cód. 1708)", "IRRF (Rendimento de Trabalhador Cód. 0561)"]


@pytest.mark.parametrize("texto,esperado", [
    ("Receita prorroga o prazo de pagamento da primeira parcela do 13° salário", TREZE),        # 13° (grau) = 13º; as duas parcelas
    ("Adiada a entrega da DASN SIMEI do ano-calendário de 2026", [DASN]),                      # sem o traço
    ("Novo prazo para a Escrituração Contábil Digital", ["ECD - Escrituração Contábil Digital"]),  # a parte depois do traço
    ("Receita posterga o vencimento do FGTS de março", ["FGTS - Fundo de Garantia Por Tempo de Serviço"]),   # a sigla antes do traço
    ("PRORROGAÇÃO DO PRAZO DE ENTREGA DA DEFIS", [DEFIS]),                                      # maiúsculas com acento
    ("prorrogacao do prazo de entrega da defis", [DEFIS]),                                      # sem acento
    ("Prorrogado o prazo de recolhimento do IRRF", IRRF),                                       # a sigla antes dos parênteses
    ("Receita adia o prazo da DASN", [DASN]),                                                   # só pelos "termos"
    ("Gratificação natalina: governo adia o prazo de pagamento", TREZE),                        # idem
    ("Adiantamento do 13º salário: o prazo de pagamento vai até 30 de novembro", []),            # "adiantamento" não é adiamento
    ("Decreto prorroga benefício fiscal do ICMS na importação. Este Decreto entra em vigor na data de sua publicação.", []),   # sem prazo
    ("Receita prorroga o prazo para a empresa atualizar o cadastro", []),                      # "empresa" é de "GPS (Empresa)"
    ("Prorrogado o prazo da 1ª parcela do acordo", []),                                         # "1ª parcela" é do 13º, entre parênteses
    ("Prorrogado o prazo de entrega da ECDX", []),                                              # só palavra inteira
    ("Simples Nacional: prazo de opção vai até 31 de janeiro", []),                             # sem palavra de prorrogação
    # v0.30.0 (revisão): o que parece prorrogação de prazo e não é
    ("Convênio ICMS 10/26 - Prorroga o prazo de vigência das disposições do Convênio ICMS 100/97", []),   # vigência não é vencimento
    ("Decreto SC prorroga até 2027 o prazo de vigência de benefícios fiscais do ICMS", []),
    ("Caixa prorroga o prazo de validade do Certificado de Regularidade do FGTS", []),          # validade da certidão
    ("Lei prorroga a desoneração da folha de pagamento e reduz a contribuição ao INSS", []),   # "folha de pagamento" não é prazo
    ("Portaria disciplina o parcelamento do ICMS. O contribuinte terá prazo de 30 dias, prorrogável por igual período, para apresentar "
     "documentos.", []),                                                                       # "prorrogável": só a possibilidade
    ("O prazo de recolhimento do ICMS poderá ser prorrogado pela Secretaria", []),            # "poderá ser prorrogado": idem
    ("INSS prorroga prazo da prova de vida dos aposentados", []),                             # INSS: sigla de órgão, não da obrigação
    ("Governo prorroga prazo para pagamento de salários de servidores estaduais", []),        # "Salários - …": a parte não é sigla
    ("Transação: PGFN prorroga prazo de adesão para débitos do Simples Nacional", ["Simples Nacional"]),   # e não o Parcelamento Especial
    # …e o que continua casando
    ("Prorroga o prazo de vigência do benefício e o prazo de recolhimento do ICMS", ["ICMS"]),  # o outro prazo conta
    ("Fica prorrogado o prazo de recolhimento do ICMS de março", ["ICMS"]),
    ("Prorrogado o prazo de pagamento do PERT", ["PERT – Programa Esp. Regularização Tributária"]),       # sigla antes do travessão
    ("Prorrogado o prazo de pagamento do Programa Esp. Regularização Tributária", ["PERT – Programa Esp. Regularização Tributária"]),
    ("Receita adia o prazo da GPS", ["GPS (Empresa)"]),                                        # o nome sem os parênteses
])
def test_prorrogacao_casa_nome_sigla_termos_e_palavras(limpo, texto, esperado):
    """v0.30.0: a regra do aviso de possível prorrogação (uma só, no banco, para a tela e o robô) precisa de uma palavra de prorrogação
    (lista fechada), de um contexto de prazo e de um termo da obrigação da agenda: o nome inteiro, cada parte do nome sem o que está entre
    parênteses (separada por " - ", " – " ou " — ") ou um dos "termos"; só palavra inteira, sem diferença de maiúscula, acento ou traço."""
    assert casa(limpo, texto) == esperado


def test_prorrogacao_agenda_malformada_nao_quebra_e_nao_repete(limpo):
    texto = "Receita prorroga o prazo de entrega da DEFIS"
    assert casa(limpo, texto, {"a": 1}) == [] and casa(limpo, texto, "texto") == [] and casa(limpo, None, []) == []
    lista = [1, "x", None, {"regra": "dia"}, {"nome": ""}, {"nome": "   "}, {"nome": 7}, {"nome": "DEFIS", "termos": "não é lista"},
             {"nome": "DEFIS"}, {"nome": "Outra", "termos": [3, None, "de", "DEFIS"]}]
    assert casa(limpo, texto, lista) == ["DEFIS", "Outra"]                                       # o mesmo nome uma vez só
    assert casa(limpo, texto, [{"nome": "Obrigação X", "termos": ["DE"]}]) == []                 # termo com menos de 3 letras não conta
    # v0.30.0 (revisão): o termo conta em letras e números, sem acento e sem pontuação ("13º" vira "13", com 2), como na tela
    assert casa(limpo, "Receita prorroga o prazo de pagamento do 13º", [{"nome": "Gratificação X", "termos": ["13º"]}]) == []
    assert casa(limpo, "Receita prorroga o prazo de pagamento do 13º", [{"nome": "Gratificação X", "termos": ["13º X"]}]) == []
    assert casa(limpo, "Receita prorroga o prazo do I.R. de pessoa física", [{"nome": "Obrigação Y", "termos": ["I.R."]}]) == []   # "ir": 2
    assert casa(limpo, "Receita prorroga o prazo de pagamento do 13º salário", [{"nome": "Gratificação X", "termos": ["13º salário"]}]) == ["Gratificação X"]
    # a sigla de um nome com outra sigla de órgão na frente ("INSS - …", "PGFN - …") não vale sozinha; a de obrigação, sim
    assert casa(limpo, "Prorrogado o prazo de pagamento do INSS", [{"nome": "INSS - Parcelamento X"}, {"nome": "PGFN - Transação Y"}]) == []
    assert casa(limpo, "Prorrogado o prazo de entrega da DCTFWeb", [{"nome": "DCTFWeb - Declaração de Débitos"}]) == ["DCTFWeb - Declaração de Débitos"]


def test_radar_prorrogacoes_janela_repeticao_conferida_e_papeis(limpo):
    """v0.30.0: radar_prorrogacoes devolve as capturas dos últimos 30 dias (p_dias de 1 a 90) que casam com uma obrigação da agenda,
    sem as repetições (um aviso por fato), da mais nova para a mais antiga, com o assunto (se já virou um), se é do boletim pago (ITC) e
    se o administrador já conferiu (radar_config.prorrogacoes_conferidas; o que não for número de captura não conta). A equipe com perfil
    ativo e o robô (service_role) leem; o logado sem perfil ativo recebe nada; o visitante não executa. Agenda malformada: lista vazia."""
    db = limpo
    db.execute("""insert into radar_fontes (slug, nome, orgao, oficial, tipo_coletor, url, config)
                  values ('teste-itc-ficticia', 'Boletim fictício de teste', 'Consultoria fictícia', false, 'rss', 'https://boletim.exemplo/rss',
                          '{"origem": "email"}')""")

    def cap(titulo, horas, slug="rfb-noticias", dup=None, texto=None, n=[0]):
        n[0] += 1
        return db.execute("""insert into radar_capturas (fonte_id, url, titulo, hash_titulo, texto, duplicata_de, capturado_em)
                             select id, %s, %s, md5(%s), %s, %s, now() - make_interval(hours => %s) from radar_fontes where slug = %s
                             returning id""", (f"https://exemplo.gov.br/prorroga-{n[0]}", titulo, titulo + str(n[0]), texto, dup, horas, slug)).fetchone()[0]

    try:
        a = cap("Receita prorroga o prazo de entrega da DEFIS", 1)
        repeticao = cap("Prazo da DEFIS é prorrogado", 1, dup=a)                              # o mesmo fato: não repete
        itc = cap("Boletim: adiado o vencimento do FGTS", 2, slug="teste-itc-ficticia")
        no_texto = cap("Comunicado da Receita", 3, texto="Fica prorrogado o prazo de entrega da ECF para 31 de agosto.")   # o começo do texto conta
        cap("Receita publica o calendário da DEFIS", 4)                                         # sem prorrogação
        cap("Fica prorrogado o prazo do Simples Nacional", 24 * 40)                             # 40 dias: fora dos 30
        cap("Fica prorrogado o prazo do Simples Nacional, de novo", 24 * 100)                   # 100 dias: fora até do máximo (90)
        longo = cap("Título longo " + "palavra " * 120 + "prorrogado o prazo da ECD", 5)      # no título, conta inteiro
        longe = cap("Comunicado longo", 6, texto="Texto. " * 120 + "Fica prorrogado o prazo de entrega da ECD.")   # depois dos 600 caracteres
        assert repeticao and longe and longo
        ler = lambda c, dias=30: c.execute("select * from radar_prorrogacoes(%s)", (dias,)).fetchall()
        with como("service_role") as c:
            linhas = ler(c)
            cols = [d.name for d in c.execute("select * from radar_prorrogacoes(30)").description]
        assert cols == ["captura_id", "titulo", "url", "fonte", "do_email", "oficial", "capturado_em", "data_publicacao", "assunto_id",
                        "assunto_status", "obrigacoes", "conferida"]
        por_id = {l[0]: l for l in linhas}
        assert [l[0] for l in linhas] == [a, itc, no_texto, longo]                         # da mais nova para a mais antiga
        assert por_id[a][3:6] == ("Receita Federal — Notícias", False, True) and por_id[a][8:] == (None, None, [DEFIS], False)
        assert por_id[itc][3:6] == ("Boletim fictício de teste", True, False)
        assert por_id[itc][10] == ["FGTS - Fundo de Garantia Por Tempo de Serviço"] and por_id[no_texto][10] == ["ECF - Escrituração Contábil Fiscal"]
        with como("service_role") as c:
            assert len(ler(c, 45)) == 5 and len(ler(c, 1000)) == 5 and len(ler(c, 0)) == 4 and len(ler(c, None)) == 4   # 90 no máximo; 1 no mínimo
        # o assunto aberto da captura e o "Conferido" do administrador (o que não é número de captura não conta)
        with como("authenticated", EDITOR) as c:
            assunto = c.execute("select radar_abrir_assunto(%s)", (a,)).fetchone()[0]
        db.execute("insert into radar_config (chave, valor) values ('prorrogacoes_conferidas', %s)", (json.dumps([itc, "x", 1.5, -3, None]),))
        papeis = {}
        for nome, uid in [("leitor", LEITOR), ("editor", EDITOR), ("admin", ADMIN)]:
            with como("authenticated", uid) as c:
                papeis[nome] = ler(c)
        assert papeis["leitor"] == papeis["editor"] == papeis["admin"]
        por_id = {l[0]: l for l in papeis["admin"]}
        assert por_id[a][8:10] == (assunto, "capturado") and por_id[a][11] is False and por_id[itc][11] is True
        assert [l[11] for l in papeis["admin"]] == [False, True, False, False]
        with como("authenticated", SEM_PERFIL) as c:
            assert ler(c) == []
        db.execute("update radar_perfis set ativo = false where user_id = %s", (LEITOR,))
        try:
            with como("authenticated", LEITOR) as c:
                assert ler(c) == []                                                             # perfil desativado: nada
        finally:
            db.execute("update radar_perfis set ativo = true where user_id = %s", (LEITOR,))
        with como("anon") as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            ler(c)
        for papel, uid in [("authenticated", ADMIN), ("service_role", None)]:                   # a regra de casamento é só do dono
            with como(papel, uid) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute("select radar_prorrogacao_obrigacoes('x', '[]')")
        # agenda malformada: lista vazia, sem erro (e a lista volta com a agenda certa)
        original = db.execute("select valor from radar_config where chave = 'obrigacoes'").fetchone()[0]
        try:
            for ruim in ({"nome": "DEFIS"}, "texto", [None, 3]):
                db.execute("update radar_config set valor = %s where chave = 'obrigacoes'", (json.dumps(ruim),))
                with como("service_role") as c:
                    assert ler(c) == []
        finally:
            db.execute("update radar_config set valor = %s where chave = 'obrigacoes'", (json.dumps(original),))
        with como("service_role") as c:
            assert len(ler(c)) == 4
    finally:
        db.execute("delete from radar_config where chave = 'prorrogacoes_conferidas'")
        db.execute("delete from radar_capturas where fonte_id = (select id from radar_fontes where slug = 'teste-itc-ficticia')")
        db.execute("delete from radar_fontes where slug = 'teste-itc-ficticia'")


# ------------------------------------------------- v0.31.0: fontes oficiais que faltavam
FONTES_V031 = RAIZ / "sql" / "radar-fontes-novas-v0.31.0.sql"
SLUGS_V031 = ("dou-presidencia", "dou-confaz", "dou-trabalho-previdencia", "dou-fazenda-ministro", "esocial-noticias",
              "fgts-digital-comunicados", "previdencia-noticias", "inss-noticias", "domsc-palhoca-leis", "domsc-palhoca-decretos",
              "domsc-saojose-leis", "domsc-saojose-decretos")
NORMAS_ANTIGA = ("http://normas.receita.fazenda.gov.br/sijut2consulta/consulta.action?tipoData=2&dt_inicio={inicio}&dt_fim={fim}"
                 "&optOrdem=Publicacao_DESC&p={p}")


def test_fontes_da_v0310_so_com_o_robo_novo_ligadas_as_conferidas_e_o_sql_pode_rodar_de_novo(limpo):
    """O SQL das fontes novas para no começo enquanto o robô da v0.31.0 não coletou (o robô antigo ignoraria o filtro de tema e traria
    tudo); depois cadastra as fontes (ligadas só as conferidas), troca o endereço da rfb-normas (que continua desligada) e pode rodar
    de novo sem desfazer nada do que o administrador mudou."""
    setup = limpo.execute("select url, config, ativo from radar_fontes where slug = 'rfb-normas'").fetchone()
    lista = "(" + ",".join(f"'{s}'" for s in SLUGS_V031) + ")"
    try:
        r = psql(FONTES_V031)
        assert r.returncode != 0 and "rode este SQL depois de publicar a v0.31.0" in r.stderr and "Nada foi alterado" in r.stderr
        fid = limpo.execute("select id from radar_fontes where slug = 'rfb-noticias'").fetchone()[0]
        limpo.execute("insert into radar_execucoes (fonte_id, versao_robo, status) values (%s, '0.21.0', 'ok'), (%s, '0.4.0', 'ok'), "
                      "(%s, '0.31.0-teste', 'ok'), (%s, null, 'falha')", (fid, fid, fid, fid))
        r = psql(FONTES_V031)                                   # o robô antigo (0.21.0; "0.4.0" não passa por ordem de texto) e versão estranha
        assert r.returncode != 0 and "rode este SQL depois" in r.stderr
        assert limpo.execute(f"select count(*) from radar_fontes where slug in {lista}").fetchone()[0] == 0
        limpo.execute("insert into radar_execucoes (fonte_id, versao_robo, status) values (%s, '0.31.0', 'ok')", (fid,))
        # em produção, a rfb-normas ainda tem o endereço da consulta antiga e está desligada
        limpo.execute("update radar_fontes set url = %s, config = '{\"sem_pagina_de_texto\": true}', ativo = false where slug = 'rfb-normas'",
                      (NORMAS_ANTIGA,))
        r = psql(FONTES_V031)
        assert r.returncode == 0, r.stderr
        linhas = {s: (a, o, c, t, ab) for s, a, o, c, t, ab in limpo.execute(
            f"select slug, ativo, oficial, categoria_padrao, tipo_coletor, abrangencia from radar_fontes where slug in {lista}").fetchall()}
        assert {s: v[0] for s, v in linhas.items()} == {
            "dou-presidencia": True, "dou-confaz": True, "dou-trabalho-previdencia": True, "dou-fazenda-ministro": False,
            "esocial-noticias": True, "fgts-digital-comunicados": True, "previdencia-noticias": True, "inss-noticias": False,
            "domsc-palhoca-leis": False, "domsc-palhoca-decretos": False, "domsc-saojose-leis": False, "domsc-saojose-decretos": False}
        assert all(v[1] for v in linhas.values())                                        # todas oficiais
        assert (linhas["dou-confaz"][2], linhas["dou-trabalho-previdencia"][2], linhas["esocial-noticias"][2],
                linhas["domsc-palhoca-leis"][2], linhas["dou-presidencia"][2]) == ("santa-catarina", "trabalhista", "trabalhista",
                                                                                   "santa-catarina", "federal")
        assert linhas["domsc-saojose-decretos"][3:] == ("rss", "municipal") and linhas["dou-confaz"][3] == "inlabs"
        palavras = limpo.execute("select config->'palavras' from radar_fontes where slug = 'dou-presidencia'").fetchone()[0]
        assert "\\bPIS\\b" in palavras and "contribuiç" in palavras                       # a barra invertida e o acento chegam inteiros
        # a rfb-normas: a pesquisa nova, as opções iguais às da carga inicial (e às do robo/radar_fontes.json) e continua desligada
        assert limpo.execute("select url, config, ativo from radar_fontes where slug = 'rfb-normas'").fetchone() == (setup[0], setup[1], False)
        assert "dou-presidencia|Diário Oficial da União — leis, decretos e medidas provisórias (INLABS)|ligada" in r.stdout
        assert "domsc-palhoca-leis|Palhoça — leis sobre tributos (Diário Oficial dos Municípios)|desligada" in r.stdout
        # de novo: o que o administrador ligou, desligou ou ajustou fica
        limpo.execute("update radar_fontes set ativo = false where slug = 'esocial-noticias'")
        limpo.execute("update radar_fontes set ativo = true where slug = 'domsc-palhoca-decretos'")
        limpo.execute("""update radar_fontes set config = config || '{"excluir_orgao": "^(SRRF|DRF|DISIT)"}', ativo = true where slug = 'rfb-normas'""")
        assert psql(FONTES_V031).returncode == 0
        assert dict(limpo.execute("select slug, ativo from radar_fontes where slug in ('esocial-noticias', 'domsc-palhoca-decretos', 'rfb-normas')")
                    .fetchall()) == {"esocial-noticias": False, "domsc-palhoca-decretos": True, "rfb-normas": True}
        assert limpo.execute("select config->>'excluir_orgao' from radar_fontes where slug = 'rfb-normas'").fetchone()[0] == "^(SRRF|DRF|DISIT)"
        assert limpo.execute(f"select count(*) from radar_fontes where slug in {lista}").fetchone()[0] == 12
    finally:
        limpo.execute(f"delete from radar_fontes where slug in {lista}")
        limpo.execute("update radar_fontes set url = %s, config = %s, ativo = %s where slug = 'rfb-normas'",
                      (setup[0], json.dumps(setup[1]), setup[2]))


def test_texto_oficial_de_um_ato_do_normas_vai_para_a_captura_desse_ato(limpo):
    """v0.31.0: a radar_url_base tirava o "#/…" do endereço dos atos do Normas, e todos viravam o mesmo endereço: o texto colado de um
    ato ia para a captura de OUTRO ato da fonte. Agora vai para a do próprio ato (com ou sem o "/vs/…" da consulta), e um ato que o robô
    ainda não viu entra como captura nova da fonte (o domínio da consulta externa está em "dominios")."""
    base = "https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/"
    outro = nova_captura(limpo, url=base + "154087")                                     # já tem texto
    fid = limpo.execute("select id from radar_fontes where slug = 'rfb-normas'").fetchone()[0]
    sem_texto = limpo.execute("insert into radar_capturas (fonte_id, url, titulo, hash_titulo) values (%s, %s, 'Portaria Coana nº 214', 'h') "
                              "returning id", (fid, base + "154126")).fetchone()[0]
    a = novo_assunto(limpo)
    r = incluir_texto(a, fonte="rfb-normas", url=base + "154126/vs/MTU0MTI2LDE1NDExNA==", titulo="Portaria Coana nº 214")
    assert (r["captura_id"], r["ja_existia"], r["texto_incluido"]) == (sem_texto, True, True)
    assert limpo.execute("select texto from radar_capturas where id = %s", (outro,)).fetchone()[0] == TEXTO_OFICIAL      # o outro ato não muda
    r = incluir_texto(a, fonte="rfb-normas", url=base + "154999", titulo="Ato que o robô não viu")
    assert r["ja_existia"] is False and limpo.execute("select url from radar_capturas where id = %s", (r["captura_id"],)).fetchone()[0] == base + "154999"


def test_consulta_do_leiame_acha_o_texto_do_normas_que_a_versao_anterior_ligou_ao_ato_errado(limpo):
    """v0.31.0 (revisão): na v0.30.0, a radar_url_base guardava só o site de todo ato do Normas (tirava o "#/consulta/externa/N"): o 1º
    ato colado virava uma captura com esse endereço, e o 2º ato colado era ligado à captura do 1º (e o texto dele não era guardado).
    A versão nova não desfaz isso sozinha; a consulta do LEIAME (passo 1 de "Da v0.30.0 para a v0.31.0", só de leitura) acha essas
    ligações para o dono conferir, e não acusa o ato colado já na v0.31.0 (que tem o endereço do ato)."""
    leiame = (RAIZ / "LEIAME-radar.md").read_text(encoding="utf-8")
    passo1 = leiame[leiame.index("**Da v0.30.0 para a v0.31.0**"):leiame.index("\n2. Publique a versão no repositório (`main`): o robô da coleta")]
    consulta = re.search(r"```sql\n(.*?)```", passo1, re.S).group(1)
    assert re.fullmatch(r"(?:\s*--[^\n]*\n)*\s*select\b[^;]*;\s*", consulta, re.S)           # só lê: um select, nada mais
    atual = re.search(r"create or replace function public\.radar_url_base\(p_url text\).*?\n\$\$;", SETUP.read_text(encoding="utf-8"), re.S).group(0)
    antiga = r"""create or replace function public.radar_url_base(p_url text) returns text
language sql immutable set search_path = public as $$
  select regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(btrim(coalesce(p_url, '')),
           '#.*$', ''), '([?&])(utm_[a-z_]+|fbclid|gclid)=[^&]*', '\1', 'gi'), '([?&])&+', '\1', 'g'), '[?&]+$', ''), '(.)/+$', '\1');
$$;"""
    base = "https://normasinternet2.receita.fazenda.gov.br/#/consulta/externa/"
    a1, a2, a3 = novo_assunto(limpo), novo_assunto(limpo), novo_assunto(limpo)
    try:
        limpo.execute(antiga)                                                  # o banco da v0.30.0
        r1 = incluir_texto(a1, fonte="rfb-normas", url=base + "154126", titulo="Portaria Coana nº 214")
        r2 = incluir_texto(a2, fonte="rfb-normas", url=base + "154087", titulo="Solução de Consulta Cosit nº 196")
        assert (r2["captura_id"], r2["texto_incluido"]) == (r1["captura_id"], False)        # o erro: o 2º ato foi para a captura do 1º
    finally:
        limpo.execute(atual)
    r3 = incluir_texto(a3, fonte="rfb-normas", url=base + "154087", titulo="Solução de Consulta Cosit nº 196")    # já na v0.31.0
    assert r3["captura_id"] != r1["captura_id"] and r3["ja_existia"] is False
    linhas = limpo.execute(consulta).fetchall()
    assert [l[:4] for l in linhas] == [(r1["captura_id"], "Portaria Coana nº 214", "https://normasinternet2.receita.fazenda.gov.br", a1),
                                       (r1["captura_id"], "Portaria Coana nº 214", "https://normasinternet2.receita.fazenda.gov.br", a2)]
    assert limpo.execute("select count(*) from radar_capturas where id = %s and url = %s", (r3["captura_id"], base + "154087")).fetchone()[0] == 1
