"""v0.20.0 — termos que a publicidade contábil evita (lista inicial, a confirmar com o contador responsável): a mesma lista, e a
mesma função, na tela (index.html, que trava a legenda e a arte ou pede confirmação) e na função radar-ia (que aponta os termos nos
avisos do kit das redes). Trava só a forma de oferta, de promessa e de convite ("consulta grátis", "ganhe um brinde", "blinde seu
patrimônio", "pague menos com a Artecon"); a palavra solta que também é fato ou assunto da notícia ("emissor grátis para o MEI",
"quem ganha até R$ 5 mil pague menos", "blindar o patrimônio", "brindes", "veículos blindados", "troca de contador") é aviso."""
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
    # a oferta trava; o "grátis" de "consulta grátis" não se repete no aviso
    (["Consulta grátis, brindes e diagnóstico de graça"], {"trava": ["consulta grátis", "diagnóstico de graça"], "aviso": ["brindes"]}),
    (["GRÁTIS", "Gratis e um brinde."], {"trava": [], "aviso": ["grátis", "gratis", "brinde"]}),          # vários textos de uma vez
    (["Patrimônio blindado com a blindagem; pague menos e troque de contador"],
     {"trava": ["troque de contador"], "aviso": ["blindado", "blindagem", "pague menos"]}),
    # a oferta, a promessa e o convite travam; o "brinde" de "ganhe um brinde" não se repete no aviso
    (["Ganhe um brinde na abertura, blinde seu patrimônio e blindar a empresa; mude de contador ou troque o seu contador"],
     {"trava": ["ganhe um brinde", "blinde seu patrimônio", "mude de contador", "troque o seu contador"], "aviso": ["blindar a empresa"]}),
    (["Abertura de empresa grátis, primeiro mês de graça e orçamento grátis. Pague menos impostos com a Artecon!"],
     {"trava": ["abertura de empresa grátis", "primeiro mês de graça", "orçamento grátis", "pague menos impostos com a artecon"], "aviso": []}),
    # notícia de verdade: "grátis", "de graça", "pague menos" e "blindar o patrimônio" são fato da notícia (só aviso: não impedem)
    (["A nova faixa de isenção faz com que quem ganha até R$ 5 mil pague menos Imposto de Renda."], {"trava": [], "aviso": ["pague menos"]}),
    (["A Receita libera o emissor de NFS-e grátis para o MEI", "O certificado digital do MEI passa a ser emitido de graça"],
     {"trava": [], "aviso": ["grátis", "de graça"]}),
    (["STJ decide que holding não serve para blindar o patrimônio"], {"trava": [], "aviso": ["blindar o patrimônio"]}),
    (["Programa permite que a empresa pague menos juros e multa na transação"], {"trava": [], "aviso": ["pague menos"]}),
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
    (["Atenção: é grátis! (brinde)"], {"trava": [], "aviso": ["grátis", "brinde"]}),
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


# v0.21.0 — os termos que a Pauta não publica (TERMOS_PECA, em radar-pauta.js): na peça (que fala da Artecon, não é notícia) todos
# travam. O sentido técnico da contabilidade fica de fora: “desconto do INSS”, “desconto simplificado”, “garantia de emprego”, “mês de
# referência”, “fórmula de cálculo”. A mesma lista vai na função radar-ia (Gerar com IA da peça), onde os termos viram aviso da sugestão.
PAUTA = RAIZ / "radar-pauta.js"
INICIO_PECA = "const TERMOS_PECA = ["


def _extrair_peca(fonte: str) -> str:
    """Da declaração da lista (TERMOS_PECA) até o fim de termosPeca."""
    i = fonte.index(INICIO_PECA)
    return fonte[i:fonte.index(FIM, i) + len(FIM)]


def test_termos_da_pauta_iguais_na_tela_e_na_funcao():
    assert _extrair_peca(PAUTA.read_text(encoding="utf-8")) == _extrair_peca(FUNCAO.read_text(encoding="utf-8"))

# (textos passados a termosPeca, termos achados: em minúsculas, sem repetir, na ordem da lista e, em cada grupo, na ordem do texto)
CASOS_PECA = [
    (["Promoção de abertura com 20% de desconto e brinde"], ["promoção", "desconto", "brinde"]),
    (["O desconto do INSS e o desconto simplificado do IR; a garantia de emprego da gestante; o mês de referência; a fórmula de cálculo"], []),
    (["Desconto de 10% para novos clientes; garantia de resultado; somos referência"], ["desconto", "garantia de", "referência"]),
    # o desconto da folha (perto de INSS, IRRF, parcela, 13º, folha, salário, vale-transporte), antes ou depois, é informação
    (["A 1ª parcela não tem esses descontos.", "Os descontos da 2ª parcela: INSS e IRRF", "O desconto de 6% do vale-transporte",
      "Do salário de dezembro saem os descontos", "No 13º, sem descontos"], []),
    (["Ganhe 10% de desconto no honorário; descontos para quem paga em dia", "A parcela do seu plano.\nCom desconto!"],
     ["ganhe", "desconto", "descontos"]),
    (["Honorários a partir de R$ 199,90 por mês; R$ 300 de mensalidade"], ["honorários a partir de r$ 199,90", "r$ 300 de mensalidade"]),
    (["nº 1 em Palhoça, número 1, 100% digital e o melhor atendimento", "no 1º trimestre, a multa de 1100%"], ["nº 1", "número 1", "100%", "o melhor"]),
    (["Diferente dos outros escritórios, seu contador atual só envia guias. Mude de contador!"],
     ["diferente dos outros", "seu contador atual", "só envia guias", "mude de contador"]),
    (["Antes que seja tarde: alerta máximo, a falência e multas pesadas vão bater à sua porta"],
     ["antes que seja tarde", "alerta máximo", "falência", "multas pesadas", "bater à sua porta"]),
    (["Consultoria jurídica? Receita informa: o segredo, o truque e a maioria das empresas"],
     ["consultoria jurídica", "receita informa", "segredo", "truque", "a maioria"]),
    # vários textos de uma vez: a mercantilização antes da promessa
    (["Garantimos economia: economize e pague menos", "Sorteio de brindes por tempo limitado"],
     ["sorteio", "brindes", "por tempo limitado", "garantimos", "economize", "pague menos"]),
    (["A equipe presente na abertura; ganhe um presente"], ["ganhe", "um presente"]),
    # fronteira da palavra com acento: letra colada conta como letra
    (["gratuitamente, descontado, promoçãozinha, referências e contraoferta"], []),
    (["Atenção: é GRÁTIS! (Brinde)"], ["grátis", "brinde"]),
]


def test_termos_da_pauta_casos(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node não instalado")
    for arquivo in (PAUTA, FUNCAO):
        js = tmp_path / "termos-pauta.cjs"
        js.write_text(_extrair_peca(arquivo.read_text(encoding="utf-8")) + "\nconst casos = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
                      "console.log(JSON.stringify(casos.map((textos) => termosPeca(...textos))));\n", encoding="utf-8")
        r = subprocess.run(["node", str(js)], input=json.dumps([t for t, _ in CASOS_PECA]), capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        for (textos, esperado), obtido in zip(CASOS_PECA, json.loads(r.stdout)):
            assert obtido == esperado, (arquivo.name, textos)
