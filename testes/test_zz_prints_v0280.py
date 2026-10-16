# Arquivo TEMPORÁRIO (só para os prints da v0.28.0; apagado depois). Dados de mentira: "Ana Teste", "Bruno Exemplo", domínios .test.
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import test_radar_video_banco as vb
from test_radar_banco import pauta, pessoa_do_corretor  # noqa: F401
from test_radar_telas import (navegador, pagina, corretor_tela, vtela, entrar, abrir_pauta, limpar_recados, clipe,  # noqa: F401
                              video_rapido, titulo_semana, MIB)
from test_radar_video_banco import corretor  # noqa: F401

SAIDA = Path("/tmp/claude-0/-home-user-radar/c8ebb609-e4d7-50ef-90a0-664f434b87a5/scratchpad/prints-v0.28.0")


def test_prints_v0280(pagina, vtela):
    SAIDA.mkdir(parents=True, exist_ok=True)
    db, fv = vtela
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    seg = hoje - timedelta(days=hoje.weekday())
    sab, dom = seg + timedelta(days=5), seg + timedelta(days=6)
    ana = pessoa_do_corretor(db, categoria="contadora", crc="CRC-SC 012345/O-5")
    entrar(pagina, "admin@artecon.test")
    pagina.wait_for_selector("text=Painel do dia")
    video_rapido(pagina)
    abrir_pauta(pagina)
    pagina.wait_for_selector(f"#pauta-semana-titulo >> text={titulo_semana(seg.isoformat())}")
    assert pagina.locator("[data-acao=pauta-nova]").count() == sum(1 for i in range(7) if seg + timedelta(days=i) >= hoje)
    pagina.locator(".pauta-semana").scroll_into_view_if_needed()
    pagina.screenshot(path=str(SAIDA / "01-pauta-semana-com-nova-peca.png"), full_page=True)

    # sábado: Bastidor / Foto
    pagina.click(f".pauta-dia[data-dia='{sab.isoformat()}'] [data-acao=pauta-nova]")
    form = pagina.locator("#pauta-nova")
    form.wait_for()
    form.locator("[name=tipo]").select_option("bastidor")
    form.locator("[name=formato]").select_option("foto")
    form.locator("[name=assunto]").fill("Bastidor de teste: a rotina da equipe (exemplo)")
    form.locator("button", has_text="Criar a peça").click()
    pagina.wait_for_selector("form[data-form=peca]")
    pagina.click("text=← Voltar para a semana")
    pagina.wait_for_selector(".pauta-semana")

    # domingo: Reel / Reel (o formulário preenchido)
    pagina.click(f".pauta-dia[data-dia='{dom.isoformat()}'] [data-acao=pauta-nova]")
    form.wait_for()
    form.locator("[name=tipo]").select_option("reel")
    form.locator("[name=formato]").select_option("reel")
    form.locator("[name=assunto]").fill("Reel de teste: o prazo do Simples vence no dia 20 (exemplo)")
    form.locator("[name=objetivo]").fill("orientar")
    form.locator("[name=quem_aparece]").fill("Bruno")
    form.locator("[name=observacao]").fill("Peça de teste: cancelar depois")
    form.scroll_into_view_if_needed()
    pagina.screenshot(path=str(SAIDA / "02-formulario-da-nova-peca.png"), full_page=True)
    form.screenshot(path=str(SAIDA / "02b-formulario-da-nova-peca-detalhe.png"))
    pagina.set_viewport_size({"width": 375, "height": 900})
    form.scroll_into_view_if_needed()
    pagina.screenshot(path=str(SAIDA / "02c-formulario-da-nova-peca-celular.png"))
    pagina.set_viewport_size({"width": 1280, "height": 900})
    limpar_recados(pagina)
    form.locator("button", has_text="Criar a peça").click()
    pagina.wait_for_selector("form[data-form=peca]")
    pagina.wait_for_selector("#recado >> text=nada é publicado sem a aprovação do administrador")
    pagina.wait_for_selector("#video-reel")
    pid = db.execute("select id from radar_pauta_pecas where data = %s", (dom,)).fetchone()[0]
    assert db.execute("select tipo, formato, situacao from radar_pauta_pecas where id = %s", (pid,)).fetchone() == ("reel", "reel", "planejada")
    pagina.screenshot(path=str(SAIDA / "03-peca-reel-criada-pagina-inteira.png"), full_page=True)
    pagina.locator("#video-reel").scroll_into_view_if_needed()
    pagina.locator("#video-reel").screenshot(path=str(SAIDA / "03b-peca-reel-criada-quadro-do-corretor.png"))

    # Pessoas e termos: Bruno Exemplo, sócio(a), sem termo nenhum (cadastrado pela tela, com a marca)
    pagina.click("text=← Voltar para a semana")
    pagina.click("[data-acao=pauta-pessoas]")
    pagina.wait_for_selector("h1 >> text=Pessoas e termos")
    nova = pagina.locator("form[data-form=novaPessoa]")
    nova.locator("[name=nome]").fill("Bruno Exemplo")
    nova.locator("[name=nome_na_peca]").fill("Bruno")
    nova.locator("[name=area]").fill("Diretoria")
    nova.locator("[name=socio]").check()
    pagina.evaluate("() => { window.__perguntas = []; window.confirm = m => { window.__perguntas.push(m); return true; }; }")
    limpar_recados(pagina)
    nova.locator("button", has_text="Cadastrar pessoa").click()
    pagina.wait_for_selector("#recado >> text=Pessoa cadastrada.")
    assert pagina.evaluate("window.__perguntas[0]").startswith("Marcar como sócio(a) da Artecon?")
    bruno, socio, assinado, corretor_em = db.execute(
        "select id, socio, termo_assinado_em, termo_corretor_em from radar_pessoas where nome_na_peca = 'Bruno'").fetchone()
    assert (socio, assinado, corretor_em) == (True, None, None)
    fb = pagina.locator(f"form[data-form=pessoa][data-id='{bruno}']")
    assert "Sócio(a) — termos dispensados" in fb.locator("h2").inner_text()
    pagina.screenshot(path=str(SAIDA / "04-pessoas-e-termos-socio.png"), full_page=True)
    fb.scroll_into_view_if_needed()
    fb.screenshot(path=str(SAIDA / "04b-pessoas-e-termos-socio-detalhe.png"))

    # o reel de domingo, preparado (roteiro, quem aparece: o Bruno, a informação conferida), e o envio com as quatro declarações
    db.execute("select set_config('radar.pauta', '1', false)")
    db.execute("update radar_pauta_pecas set roteiro = %s, pessoas = %s::bigint[], conferidas = %s::jsonb, chamada = %s where id = %s",
               (vb.ROTEIRO, [bruno], '[{"informacao": "O DAS do Simples vence no dia 20", "fonte": "Portal do Simples Nacional"}]',
                "O prazo do Simples vence no dia 20", pid))
    db.execute("select set_config('radar.pauta', '', false)")
    pagina.click("text=← Voltar para a semana")
    pagina.wait_for_selector(".pauta-semana")
    pagina.click(f".pauta-dia[data-peca='{pid}'] [data-acao=abrir-peca]")
    pagina.wait_for_selector("#video-envio")
    assert pagina.locator("#video-pessoas-falta").count() == 0
    assert "Sócio(a) — termos dispensados" in pagina.inner_text(".peca-pessoas")
    pagina.set_input_files("#video-arquivos", [clipe("tomada-1.mp4", 2 * MIB, "video/mp4", 3), clipe("tomada-2.mp4", MIB + 500, "video/mp4", 5)])
    pagina.wait_for_selector("#video-clipes li[data-i='1']")
    decl = pagina.locator("#video-envio .video-declaracao")
    assert decl.count() == 4
    for c in decl.all():
        c.check()
    pagina.locator("#video-envio").scroll_into_view_if_needed()
    pagina.locator("#video-reel").screenshot(path=str(SAIDA / "05-corretor-socio-sem-termo-quatro-declaracoes.png"))
    limpar_recados(pagina)
    pagina.click("[data-acao=video-enviar]")
    pagina.wait_for_selector("#recado >> text=Gravação enviada: na fila do corretor.", timeout=60000)
    sit, quem, declaracoes = db.execute("select situacao, fala_pessoa, declaracoes from radar_videos where peca_id = %s", (pid,)).fetchone()
    assert (sit, quem, sorted(declaracoes)) == ("na_fila", bruno, sorted(vb.DECL))
    pagina.wait_for_timeout(600)
    pagina.screenshot(path=str(SAIDA / "06-corretor-socio-envio-aceito.png"))
    pagina.locator("#video-reel").screenshot(path=str(SAIDA / "06b-corretor-socio-envio-aceito-quadro.png"))
    # nada saiu: as duas peças de teste continuam planejadas e sem envio às redes
    assert db.execute("select count(*) from radar_redes_envios").fetchone()[0] == 0
    assert db.execute("select array_agg(situacao order by data) from radar_pauta_pecas").fetchone()[0] == ["planejada", "planejada"]
