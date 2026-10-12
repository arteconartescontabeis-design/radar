"""v0.20.0 — termos que a publicidade contábil evita (lista inicial, a confirmar com o contador responsável): a mesma lista, e a
mesma função, na tela (index.html, que trava a legenda e a arte ou pede confirmação) e na função radar-ia (que aponta os termos nos
avisos do kit das redes). Trava só a oferta, a promessa e o convite; a palavra que também nomeia assunto da notícia ("brindes",
"veículos blindados", "troca de contador") é aviso."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from conftest import RAIZ

FUNCAO = RAIZ / "supabase" / "functions" / "radar-ia" / "index.ts"
TELA = RAIZ / "index.html"
INICIO, FIM = "const TERMOS_PUBLICIDADE = [", "return r; };"


def _extrair(fonte: str) -> str:
    """Da declaração da lista (TERMOS_PUBLICIDADE) até o fim de termosPublicidade."""
    i = fonte.index(INICIO)
    return fonte[i:fonte.index(FIM, i) + len(FIM)]


def test_termos_de_publicidade_iguais_na_tela_e_na_funcao():
    assert _extrair(TELA.read_text(encoding="utf-8")) == _extrair(FUNCAO.read_text(encoding="utf-8"))


# (textos passados a termosPublicidade, resultado esperado)
CASOS = [
    (["Garantimos o resultado e a ECONOMIA GARANTIDA. Garantimos!"], {"trava": ["garantimos", "economia garantida"], "aviso": []}),
    (["Consulta grátis, brindes e diagnóstico de graça"], {"trava": ["grátis", "de graça"], "aviso": ["brindes"]}),
    (["GRÁTIS", "Gratis e um brinde."], {"trava": ["grátis", "gratis"], "aviso": ["brinde"]}),          # vários textos de uma vez
    (["Patrimônio blindado com a blindagem; pague menos e troque de contador"],
     {"trava": ["pague menos", "troque de contador"], "aviso": ["blindado", "blindagem"]}),
    # a oferta e o convite travam; o "brinde" de "ganhe um brinde" não se repete no aviso
    (["Ganhe um brinde na abertura, blinde seu patrimônio e blindar a empresa; mude de contador ou troque o seu contador"],
     {"trava": ["ganhe um brinde", "blinde seu patrimônio", "blindar a empresa", "mude de contador", "troque o seu contador"], "aviso": []}),
    # assunto legítimo da notícia: só aviso (não impede a publicação)
    (["ICMS na distribuição de brindes, IPVA de veículos blindados, troca de contador e como pagar menos imposto"],
     {"trava": [], "aviso": ["brindes", "blindados", "pagar menos imposto", "troca de contador"]}),
    (["Isenção de 100% (ou 100 %, cem por cento) e decisão definitiva"], {"trava": [], "aviso": ["100%", "100 %", "cem por cento", "definitiva"]}),
    (["O melhor escritório e os melhores preços, a melhor opção", "definitivamente"],
     {"trava": [], "aviso": ["o melhor", "os melhores", "a melhor", "definitivamente"]}),
    # o que não casa: outra palavra com o mesmo começo, "garantia" sem "de resultado", número maior que 100
    (["A garantia do crédito, a melhoria do sistema, o prazo indefinido, a gratuidade do serviço e a multa de 1100%."], {"trava": [], "aviso": []}),
    # fronteira da palavra com acento: letra acentuada colada conta como letra (o \b do JavaScript não entende acento)
    (["brindesção, ãgrátis e definitivoé"], {"trava": [], "aviso": []}),
    (["Atenção: é grátis! (brinde)"], {"trava": ["grátis"], "aviso": ["brinde"]}),
]


def test_termos_de_publicidade_casos(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node não instalado")
    for arquivo in (FUNCAO, TELA):
        js = tmp_path / "termos.cjs"
        js.write_text(_extrair(arquivo.read_text(encoding="utf-8")) + "\nconst casos = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
                      "console.log(JSON.stringify(casos.map((textos) => termosPublicidade(...textos))));\n", encoding="utf-8")
        r = subprocess.run(["node", str(js)], input=json.dumps([t for t, _ in CASOS]), capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        for (textos, esperado), obtido in zip(CASOS, json.loads(r.stdout)):
            assert obtido == esperado, (arquivo.name, textos)
