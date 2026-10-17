"""v0.32.0 — o título que vai ao site da Artecon (17/10/2026): o site monta o endereço da notícia com o título e não abre a página
quando ele tem "º" ("…/news/view/salario-maternidade-lei-nº-154152026-…" responde 404). Decisão do dono: no título que vai ao site,
"Lei nº 15.415/2026" vira "Lei 15.415/2026" e o "º"/"ª"/"°" depois de número sai; no Radar, no Instagram e no Facebook o título não
muda. A regra está no robô (radar_site.titulo_para_o_site, usada no campo do título do cadastro) e na tela (tituloParaOSite, no
index.html, para o aviso na autorização do site): as duas dão o mesmo resultado nos mesmos casos."""
from __future__ import annotations

import json
import random
import re
import shutil
import subprocess

import pytest

import radar_site
import radar_site_publicar as pub
from conftest import RAIZ

TELA = RAIZ / "index.html"

# (título escrito no Radar, título que vai ao site)
CASOS = [
    # o caso real de 17/10/2026
    ("Salário-maternidade: Lei nº 15.415/2026 garante concessão em até 30 dias pela Previdência Social",
     "Salário-maternidade: Lei 15.415/2026 garante concessão em até 30 dias pela Previdência Social"),
    # as formas do "número" antes de número: fica só o número
    ("Instrução Normativa RFB Nº 2.290 muda o prazo da DCTFWeb", "Instrução Normativa RFB 2.290 muda o prazo da DCTFWeb"),
    ("Portaria n.º 45/2026 do Ministério do Trabalho", "Portaria 45/2026 do Ministério do Trabalho"),
    ("Resolução CGSN N.º 183 altera o PGDAS-D", "Resolução CGSN 183 altera o PGDAS-D"),
    ("Decreto n° 12.345 regulamenta a reforma", "Decreto 12.345 regulamenta a reforma"),
    ("Lei Complementar nº. 214/2025: o que muda", "Lei Complementar 214/2025: o que muda"),
    ("Leis nºs 15.100 e 15.101 entram em vigor", "Leis 15.100 e 15.101 entram em vigor"),
    ("Convênio ICMS nº190/2017 (sem espaço)", "Convênio ICMS 190/2017 (sem espaço)"),
    ("Nº 1 da lista: a DCTFWeb", "1 da lista: a DCTFWeb"),
    # o "º"/"ª"/"°" depois de número
    ("13º salário: 1ª parcela vence em 30 de novembro", "13 salário: 1 parcela vence em 30 de novembro"),
    ("eSocial: prazo no 2º dia útil", "eSocial: prazo no 2 dia útil"),
    ("Art. 1.º da IN e a 3.ª semana", "Art. 1 da IN e a 3 semana"),
    ("Câmaras frias a 25° no 1º trimestre", "Câmaras frias a 25 no 1 trimestre"),
    # o "º"/"ª" solto também sai; os espaços que ficam dobrados viram um
    ("Recibo: o nº ainda não saiu", "Recibo: o n ainda não saiu"),
    ("Agenda ª e º soltos", "Agenda e soltos"),
    ("Lei nº  15.415  garante o prazo", "Lei 15.415 garante o prazo"),
    ("  1ª parcela do 13º  ", "1 parcela do 13"),
    # o "no" (palavra) e o "n" dentro de palavra não são o "nº"
    ("Prazo no 1º dia e o plano nº 3", "Prazo no 1 dia e o plano 3"),
    ("Anº 5 e Ano 2026", "An 5 e Ano 2026"),
    # v0.32.0 (revisão): os espaços "diferentes" contam igual na tela (JS) e no robô (Python): o BOM (U+FEFF, comum em texto colado),
    # o NEL (U+0085, o "…" do cp1252 lido errado) e os separadores U+001C a U+001F
    ("Lei nº 15.415/2026\ufeff", "Lei 15.415/2026"),
    ("\ufeffLei nº 15.415/2026", "Lei 15.415/2026"),
    ("Lei nº\x8515.415", "Lei 15.415"),
    ("Lei nº 1 e\x1c2º", "Lei 1 e 2"),
    ("1ª parcela\x85", "1 parcela"),
    ("\x1f13º\u2028salário\u00a0\x1d", "13 salário"),
    # sem esses sinais, o título vai exatamente como está (nem os espaços mudam)
    ("Prazo de opção pelo Simples Nacional vai até 31 de janeiro de 2027", "Prazo de opção pelo Simples Nacional vai até 31 de janeiro de 2027"),
    ("Título  com  espaços dobrados e no 2 de março", "Título  com  espaços dobrados e no 2 de março"),
    ("", ""),
]


def test_titulo_para_o_site_casos_reais():
    for titulo, esperado in CASOS:
        assert radar_site.titulo_para_o_site(titulo) == esperado, titulo
        assert pub.titulo_para_o_site(titulo) == esperado, titulo          # o mesmo que o robô põe no campo do título
        assert not re.search("[ºª°]", esperado)
    assert radar_site.titulo_para_o_site(None) == ""


def _funcao_da_tela() -> str:
    """A função da tela e a lista dos espaços que ela usa (ESPACOS_DO_SITE, logo acima dela)."""
    html = TELA.read_text(encoding="utf-8")
    i, j = html.index("const ESPACOS_DO_SITE = "), html.index("function tituloParaOSite(")
    assert 0 < j - i < 1500                                              # a constante logo acima da função
    return html[i:html.index("\n}\n", j) + 3]


def _na_tela(titulos: list[str], tmp_path) -> list[str]:
    js = tmp_path / "titulo-site.cjs"
    js.write_text(_funcao_da_tela() + "\nconst casos = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
                  "console.log(JSON.stringify(casos.map(tituloParaOSite)));\n", encoding="utf-8")
    r = subprocess.run(["node", str(js)], input=json.dumps(titulos), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_regra_da_tela_e_do_robo_dao_o_mesmo_resultado(tmp_path):
    """A função do index.html, rodada no Node com os mesmos casos, dá o que o robô dá; e também em 3.000 títulos montados ao acaso com
    os sinais, os números, o "n"/"N", o ponto, a barra e os espaços (inclusive o espaço sem quebra e, desde a revisão, o BOM, o NEL,
    os separadores U+001C a U+001F, o U+2028 e o espaço ideográfico, que o \\s do JS e o do Python não tratam igual)."""
    if shutil.which("node") is None:
        pytest.skip("node não instalado")
    assert _na_tela([t for t, _ in CASOS], tmp_path) == [e for _, e in CASOS]
    sorteio = random.Random(32)
    pecas = ["n", "N", "º", "ª", "°", ".", "s", "1", "15", "2026", "/", " ", "  ", " ", "\t", "Lei", "ã", "Ano", "no", ":", "-", "a",
             "\ufeff", "\x85", "\x1c", "\x1f", "\u2028", "\u3000"]
    titulos = ["".join(sorteio.choice(pecas) for _ in range(sorteio.randint(1, 14))) for _ in range(3000)]
    tela = _na_tela(titulos, tmp_path)
    assert tela == [radar_site.titulo_para_o_site(t) for t in titulos]
