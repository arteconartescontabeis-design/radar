"""v0.22.0 — corretor de vídeo, o alinhamento com o roteiro (robo/video/: numeros.py, alinhar.py, cortes.py e relatorio.py).

Roteiros FICTÍCIOS no formato do plano (tabela Tempo | Fala | Texto na tela) e no do kit, com nomes fictícios ("Ana Teste", "Bruno
Exemplo"), e transcrições SIMULADAS na forma léxica do F0 (minúsculas, sem dígitos e sem pontuação, os números por extenso), escritas
à mão. Nada de gravação, transcrição ou roteiro real. Só o último teste usa o ffmpeg: um vídeo sintético com um "ééé" sem palavra e um
"hum" entre palavras, que saem da montagem, e a legenda na grafia do roteiro.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from decimal import Decimal

import pytest

from conftest import RAIZ

ROBO = RAIZ / "robo" / "video"
sys.path.insert(0, str(ROBO))

import radar_video_sintetico as sint  # noqa: E402

import alinhar  # noqa: E402
import cortes  # noqa: E402
import numeros  # noqa: E402
import relatorio  # noqa: E402
import segredo  # noqa: E402

GLOSSARIO = ["eSocial", "DCTFWeb", "IBS", "CBS", "Simples Nacional", "MEI", "CNPJ", "DAS", "DARF", "FGTS", "Cofins", "PIS",
             "PGDAS-D", "Artecon", "Palhoça"]
VARIANTES = {"eSocial": ["e social", "é social"], "DCTFWeb": ["dctf web"], "IBS": ["ips", "ibis"], "CBS": ["cps"], "DARF": ["dar f"],
             "FGTS": ["fgt s"], "Cofins": ["confins"], "PIS": ["piz"], "CNPJ": ["cnp j"], "PGDAS-D": ["pg das d", "pgdasd"],
             "Artecon": ["arte com", "artcon"]}
CFG = {"glossario": GLOSSARIO, "variantes": VARIANTES, "pausa_max_s": 1.0, "pausa_bloco_s": 0.8, "lufs": -14, "cartela_s": 3,
       "duracao_max_s": 45}

# ------------------------------------------------------------------ roteiros fictícios (formato do plano e do kit)
ROTEIROS = {
    "simples": ("tabela", '''**Fala completa**

| Tempo | Fala | Texto na tela |
|---|---|---|
| 0 a 3 s | "Pediu o Simples para 2027? Sexta tem prazo." | SIMPLES 2027: PRAZO ATÉ SEXTA, 30/10 |
| 3 a 10 s | "Sou Ana Teste, do setor Fiscal da Artecon. Toda segunda, um assunto da sua empresa." | Tarja: Ana Teste · Departamento Fiscal |
| 10 a 30 s | "Quem ficou com pendência tem até sexta, dia 30, para regularizar. E quem é do Simples Nacional decide se paga o IBS e a CBS fora do DAS no 1º semestre." | "PENDÊNCIA: ATÉ 30/10" → "IBS E CBS FORA DO DAS?" |
| 30 a 40 s | "É caso a caso. Ficou com dúvida? Fale com a gente." | cartela final |

**Cena**
- Onde: mesa do setor, sem tela ligada ao fundo.''',
                "pediu o simples para dois mil e vinte e sete sexta tem prazo sou ana teste do setor fiscal da artecon toda segunda um "
                "assunto da sua empresa quem ficou com pendência tem até sexta dia trinta para regularizar e quem é do simples nacional "
                "decide se paga o ibs e a cbs fora do das no primeiro semestre é caso a caso ficou com dúvida fale com a gente"),
    "opcao": ("tabela", '''| Tempo | Fala | Texto na tela |
|---|---|---|
| 0 a 3 s | "Entrar no Simples em janeiro? O prazo já passou." | OPÇÃO PELO SIMPLES SAIU DE JANEIRO |
| 3 a 15 s | "Sou Bruno Exemplo, contador aqui da Artecon. A opção pelo Simples passou para setembro. Para 2027, o prazo final foi 15 de outubro." | Tarja: Bruno Exemplo, contador · CRC-SC 000000/O-0 |
| 15 a 35 s | "O cancelamento vai de hoje até 20/12, que é domingo. A empresa aberta entre 16/10 e 31/12 faz a opção na inscrição do CNPJ. E o MEI tem regra própria." | "CANCELAR: 03/11 A 20/12" → "MEI: REGRA PRÓPRIA" |
| 35 a 45 s | "Perdeu o prazo? A próxima opção é em setembro. Fale com a gente." | "PRÓXIMA OPÇÃO: SETEMBRO/2027" → cartela final |''',
              "entrar no simples em janeiro o prazo já passou sou bruno exemplo contador aqui da artecon a opção pelo simples passou para "
              "setembro para dois mil e vinte e sete o prazo final foi quinze de outubro o cancelamento vai de hoje até vinte de dezembro "
              "que é domingo a empresa aberta entre dezesseis de outubro e trinta e um de dezembro faz a opção na inscrição do cnpj e o mei "
              "tem regra própria perdeu o prazo a próxima opção é em setembro fale com a gente"),
    "decimo": ("tabela", '''| Tempo | Fala | Texto na tela |
|---|---|---|
| 0 a 3 s | "Tem funcionário? O 13º tem duas datas." | 13º SALÁRIO: AS DUAS DATAS |
| 3 a 10 s | "Eu sou Ana Teste, da Artecon. A 1ª parcela vence em 2 semanas." | Tarja: Ana Teste · Departamento Pessoal |
| 10 a 33 s | "Ela vai até 30 de novembro e é metade do salário. A 2ª vai até sexta, dia 18. O INSS e o imposto de renda são descontados na 2ª parcela." | "1ª PARCELA: ATÉ 30/11" → "2ª PARCELA: ATÉ 18/12" |
| 33 a 42 s | "E tem o FGTS de cada parcela. Fale com a gente." | cartela final |''',
               "tem funcionário o décimo terceiro tem duas datas eu sou ana teste da artecon a primeira parcela vence em duas semanas ela "
               "vai até trinta de novembro e é metade do salário a segunda vai até sexta dia dezoito o inss e o imposto de renda são "
               "descontados na segunda parcela e tem o fgts de cada parcela fale com a gente"),
    "lucro": ("tabela", '''| Tempo | Fala | Texto na tela |
|---|---|---|
| 0 a 3 s | "Vai distribuir lucro no fim do ano? A regra mudou." | LUCRO ACIMA DE R$ 50 MIL NO MÊS |
| 3 a 15 s | "Sou Bruno Exemplo, do Contábil da Artecon. Quando a empresa paga a um mesmo sócio mais de R$ 50 mil de lucro no mês, ela retém 10% de imposto de renda." | "ACIMA DE R$ 50 MIL: RETENÇÃO DE 10%" |
| 15 a 35 s | "E os 10% são sobre o total do mês, não só sobre o que passa de R$ 50.000,00. Há exceção para lucros apurados até 2025." | "10% SOBRE O TOTAL DO MÊS" |
| 35 a 45 s | "Então, planeje mês a mês. Fale com a gente." | cartela final |''',
              "vai distribuir lucro no fim do ano a regra mudou sou bruno exemplo do contábil da artecon quando a empresa paga a um mesmo "
              "sócio mais de cinquenta mil reais de lucro no mês ela retém dez por cento de imposto de renda e os dez por cento são sobre "
              "o total do mês não só sobre o que passa de cinquenta mil reais há exceção para lucros apurados até dois mil e vinte e cinco "
              "então planeje mês a mês fale com a gente"),
    "reforma": ("tabela", '''| Tempo | Fala | Texto na tela |
|---|---|---|
| 0 a 3 s | "Em 1º de janeiro, o PIS e a Cofins deixam de existir." | 2027: CBS NO LUGAR DE PIS/COFINS |
| 3 a 12 s | "Sou Ana Teste, do Fiscal da Artecon. Em 2027, a CBS passa a ser cobrada." | "CBS COBRADA A PARTIR DE 01/01/2027" |
| 12 a 33 s | "O IBS continua em teste, com 0,1% no total. O ICMS e o ISS continuam iguais em 2027 e 2028." | "IBS: 0,1% DE TESTE" |
| 33 a 45 s | "Revise os preços e os contratos. Fale com a gente." | cartela final |''',
                "em primeiro de janeiro o pis e a cofins deixam de existir sou ana teste do fiscal da artecon em dois mil e vinte e sete a "
                "cbs passa a ser cobrada o ibs continua em teste com zero vírgula um por cento no total o icms e o iss continuam iguais em "
                "dois mil e vinte e sete e dois mil e vinte e oito revise os preços e os contratos fale com a gente"),
    "abrir": ("kit", '''Roteiro do reel (40 s)

Gancho: Vai abrir empresa até dezembro?

0–3 s — Fala: Vai abrir empresa até dezembro? Sua escolha já vale para 2027. | Na tela: ABRIR EMPRESA ATÉ 31/12?

3–15 s — Fala: Sou Bruno Exemplo, do Societário da Artecon. Quem abre CNPJ entre 16 de outubro e 31 de dezembro escolhe o Simples na inscrição. | Na tela: CNPJ de 16/10 a 31/12

15–35 s — Fala: Nas inscrições a partir de 31/10, também se decide se o IBS e a CBS ficam dentro ou fora do DAS. | Na tela: IBS E CBS: DENTRO OU FORA DO DAS

Chamada final: Fale com a gente pelo telefone.''',
              "vai abrir empresa até dezembro sua escolha já vale para dois mil e vinte e sete sou bruno exemplo do societário da artecon "
              "quem abre cnpj entre dezesseis de outubro e trinta e um de dezembro escolhe o simples na inscrição nas inscrições a partir "
              "de trinta e um de outubro também se decide se o ibs e a cbs ficam dentro ou fora do das"),
}


def falas(lexica: str, inicio: float = 0.5, dur: float = 0.26, passo: float = 0.36, pausas: dict | None = None) -> list[dict]:
    """A transcrição simulada do F0: cada palavra da forma léxica com 0,26 s, uma a cada 0,36 s; pausas: {índice: s a mais antes}."""
    out, t = [], inicio
    for k, w in enumerate(lexica.split()):
        t += (pausas or {}).get(k, 0.0)
        out.append({"texto": w, "inicio": round(t, 3), "fim": round(t + dur, 3), "confianca": 0.9})
        t += passo
    return out


def com_tempos(lista: list[tuple[str, float, float]]) -> list[dict]:
    return [{"texto": w, "inicio": a, "fim": b, "confianca": 0.9} for w, a, b in lista]


def fala_de(nome: str) -> str:
    return alinhar.extrair_fala(ROTEIROS[nome][1])[0]


def troca_lexica(nome: str, velho: str, novo: str) -> str:
    lex = ROTEIROS[nome][2]
    assert lex.count(velho) == 1, velho
    return lex.replace(velho, novo)


def silencios(voz: list[tuple[float, float]], dur: float) -> list[tuple[float, float]]:
    """O que o silencedetect acharia: o complemento da voz, em trechos de 0,25 s ou mais."""
    out, t = [], 0.0
    for a, b in sorted(voz):
        if a - t >= 0.25:
            out.append((t, a))
        t = max(t, b)
    if dur - t >= 0.25:
        out.append((t, dur))
    return out


def parte(dur: float) -> list[dict]:
    return [{"n": 1, "inicio_q": 0, "quadros": int(round(dur * 30))}]


def ficou(plano: dict, a: float, b: float) -> bool:
    return cortes.remapear(plano, a)[1] and cortes.remapear(plano, b)[1] and \
        cortes.remapear(plano, b)[0] - cortes.remapear(plano, a)[0] == pytest.approx(b - a, abs=1e-6)


# ------------------------------------------------------------------ numeros.py
@pytest.mark.parametrize("n, masc, fem", [
    (0, "zero", "zero"), (1, "um", "uma"), (2, "dois", "duas"), (16, "dezesseis", "dezesseis"), (21, "vinte e um", "vinte e uma"),
    (100, "cem", "cem"), (101, "cento e um", "cento e uma"), (200, "duzentos", "duzentas"), (1100, "mil e cem", "mil e cem"),
    (1741, "mil setecentos e quarenta e um", "mil setecentas e quarenta e uma"), (2027, "dois mil e vinte e sete", None),
    (15270, "quinze mil duzentos e setenta", None), (50000, "cinquenta mil", None), (97200, "noventa e sete mil e duzentos", None),
    (1000000, "um milhão", None), (2500000, "dois milhões e quinhentos mil", None), (3000000000, "três bilhões", None)])
def test_numero_por_extenso(n, masc, fem):
    assert numeros.por_extenso(n) == masc
    if fem:
        assert numeros.por_extenso(n, feminino=True) == fem


def test_numeros_de_volta_das_palavras_em_toda_a_faixa():
    """palavras → número: o inverso exato de por_extenso (masculino e feminino) de 0 a 20.000 e em números grandes."""
    erros = []
    for v in [*range(0, 20001), 99999, 100001, 1000001, 2500000, 81000000, 123456789, 999999999]:
        for fem in (False, True):
            ws = [numeros.letras(w) for w in numeros.por_extenso(v, fem).split()]
            r = numeros._numero(ws, 0, um_livre=True)
            if not r or r[0] != v or r[1] != len(ws):
                erros.append((v, fem))
    assert erros == []


@pytest.mark.parametrize("roteiro, lexica, chave, exibe", [
    ("2027", "dois mil e vinte e sete", "#ano:2027", "2027"),
    ("30/10", "trinta de outubro", "#data:30/10", "30/10"),
    ("1º/01/2027", "primeiro de janeiro de dois mil e vinte e sete", "#data:1/1/2027", "01/01/2027"),
    ("1º de janeiro", "um de janeiro", "#data:1/1", "01/01"),
    ("R$ 50.000,00", "cinquenta mil reais", "#valor:50000", "R$ 50.000"),
    ("R$ 50 mil", "cinquenta mil reais", "#valor:50000", "R$ 50.000"),
    ("R$ 1 milhão", "um milhão de reais", "#valor:1000000", "R$ 1.000.000"),
    ("R$ 10,50", "dez reais e cinquenta centavos", "#valor:10.5", "R$ 10,50"),
    ("10%", "dez por cento", "#pct:10", "10%"),
    ("0,1%", "zero vírgula um por cento", "#pct:0.1", "0,1%"),
    ("13º", "décimo terceiro", "#ord:13", "13º"),
    ("1ª", "primeira", "#ord:1", "1ª"),
    ("2 semanas", "duas semanas", "#num:2", "2"),
    ("março/2027", "março de dois mil e vinte e sete", "#mes:3/2027", "março de 2027"),
    ("dezembro", "dezembro", "#mes:12", "dezembro"),
    ("e-Social", "é social", "esocial", "eSocial"),
    ("DCTFWeb", "dctf web", "dctfweb", "DCTFWeb"),
    ("PGDAS-D", "pg das d", "pgdasd", "PGDAS-D"),
])
def test_ficha_do_roteiro_e_da_forma_lexica_e_a_mesma(roteiro, lexica, chave, exibe):
    gl = numeros.glossario(GLOSSARIO)
    r, f = numeros.analisar(roteiro.split(), gl), numeros.analisar(lexica.split(), gl)
    assert [x["chave"] for x in r] [0] == [x["chave"] for x in f][0] == chave, (r, f)
    assert numeros.exibir(f[0]) == exibe


def test_um_e_uma_so_sao_numero_antes_de_mil_milhao_reais_ou_por_cento():
    gl = numeros.glossario(GLOSSARIO)
    tipos = lambda t: [(x["tipo"], x["chave"]) for x in numeros.analisar(t.split(), gl)]
    assert tipos("um salário mínimo") == [("palavra", "um"), ("palavra", "salario"), ("palavra", "minimo")]
    assert tipos("a um mesmo sócio")[1] == ("palavra", "um") and tipos("uma parcela")[0] == ("palavra", "uma")
    assert tipos("um milhão")[0] == ("num", "#num:1000000") and tipos("um real")[0] == ("valor", "#valor:1")
    assert tipos("um por cento")[0] == ("pct", "#pct:1") and tipos("um vírgula cinco")[0] == ("num", "#num:1.5")
    assert tipos("vinte e um")[0] == ("num", "#num:21")
    # o "1" do roteiro vira "um" e fica palavra do mesmo jeito: "1 salário" casa com "um salário"
    assert tipos("1 salário")[0] == ("palavra", "um")
    # dois números seguidos não se juntam; "segundo a lei" é preposição; "DAS" só em maiúsculas é termo
    assert [c for _, c in tipos("quinze vinte")] == ["#num:15", "#num:20"]
    assert [c for _, c in tipos("2027 e 2028")] == ["#ano:2027", "e", "#ano:2028"]
    assert tipos("segundo a lei")[0] == ("palavra", "segundo") and tipos("de segunda a sexta")[1] == ("ord", "#ord:2")
    assert tipos("fora do DAS das empresas")[2:4] == [("termo", "das"), ("palavra", "das")]
    # e a pontuação de fim de frase fica na ficha
    fs = numeros.analisar("vence dia 30/10. Fale".split(), gl)
    assert [f["fim_frase"] for f in fs] == [False, False, True, False]


def test_numeros_do_roteiro_viram_palavras():
    exp = lambda t: " ".join(w for w, _, _ in numeros.expandir(t.split()))
    assert exp("Lei 15.270/2025") == "lei quinze mil duzentos e setenta de dois mil e vinte e cinco"
    assert exp("art. 18-A, nº 19/2024") == "artigo dezoito a número dezenove de dois mil e vinte e quatro"
    assert exp("até 30/10, R$ 0,50 e 10h30") == ("até trinta de outubro cinquenta centavos e dez horas e trinta minutos")
    assert exp("2ª parcela do 13º") == "segunda parcela do décimo terceiro"
    # o "R$" e o número são um valor só, preso aos dois pedaços (a legenda mostra "R$ 50 mil" inteiro)
    (v,) = numeros.analisar("R$ 50 mil".split(), numeros.glossario())
    assert (v["tipo"], v["t0"], v["t1"]) == ("valor", 0, 2)


# ------------------------------------------------------------------ a fala do roteiro
@pytest.mark.parametrize("nome", list(ROTEIROS))
def test_fala_do_roteiro_so_com_o_que_e_falado(nome):
    formato, roteiro, _ = ROTEIROS[nome]
    fala, f = alinhar.extrair_fala(roteiro)
    assert f == formato
    for fora in ("Tarja", "Na tela", "Chamada final", "Gancho", "cartela", "Departamento", "CRC-SC", "Texto na tela", "Tempo",
                 "Onde:", "|", "**", "→", "pelo telefone"):
        assert fora not in fala, fora
    assert not re.search(r'(^|\s)["“”]|["“”](\s|$)', fala)                      # sem as aspas da célula
    assert fala == " ".join(fala.split()) and fala.endswith((".", "?"))
    texto = alinhar.extrair_fala("Bom dia. Hoje o assunto é o prazo do eSocial.")
    assert texto == ("Bom dia. Hoje o assunto é o prazo do eSocial.", "texto")


# ------------------------------------------------------------------ fala igual ao roteiro
@pytest.mark.parametrize("nome", list(ROTEIROS))
def test_fala_igual_ao_roteiro_da_zero_divergencias_e_a_legenda_e_o_roteiro(nome):
    fala = fala_de(nome)
    al = alinhar.alinhar(fala, falas(ROTEIROS[nome][2]), [], CFG)
    assert (al["divergencias"], al["fora_do_roteiro"], al["omitido"], al["remover"], al["avisos"]) == ([], [], [], [], [])
    assert al["cobertura"] == 1.0
    # a legenda é o roteiro, com a grafia e a pontuação dele (números em algarismos, termos do glossário)
    assert al["texto_final"] == fala
    assert all(u["fim"] > u["ini"] for u in al["legenda"]) and [u["u"] for u in al["legenda"]] == list(range(len(al["legenda"])))
    # cada palavra da transcrição sabe a que ficha do roteiro se alinhou, em ordem
    rots = [w["rot_de"] for w in al["palavras"]]
    assert None not in rots and rots == sorted(rots)


@pytest.mark.parametrize("nome", ["simples", "lucro", "reforma"])
def test_transcricao_ja_na_forma_de_exibicao_tambem_alinha(nome):
    """A troca futura pelo serviço pago (AZURE_FALA_MODO=rapido) devolve as palavras na forma de exibição — algarismos, pontuação
    e maiúsculas: o mesmo alinhamento serve."""
    fala = fala_de(nome)
    ws = [{"texto": w, "inicio": 0.5 + 0.4 * k, "fim": 0.8 + 0.4 * k} for k, w in enumerate(fala.split())]
    al = alinhar.alinhar(fala, ws, [], CFG)
    assert (al["divergencias"], al["fora_do_roteiro"], al["omitido"], al["cobertura"]) == ([], [], [], 1.0)
    assert al["texto_final"] == fala and al["trocas"] == []
    # cada unidade da legenda é um pedaço inteiro da fala, no tempo dos pedaços ditos
    for u in al["legenda"]:
        ks = [k for k, w in enumerate(fala.split()) if ws[k]["inicio"] >= u["ini"] and ws[k]["fim"] <= u["fim"]]
        assert " ".join(fala.split()[ks[0]:ks[-1] + 1]) == u["texto"], u


def test_numero_em_algarismo_na_legenda_no_tempo_das_palavras_ditas():
    al = alinhar.alinhar(fala_de("simples"), falas(ROTEIROS["simples"][2]), [], CFG)
    ws = falas(ROTEIROS["simples"][2])
    (u,) = [u for u in al["legenda"] if u["texto"] == "2027?"]
    assert (u["ini"], u["fim"]) == (ws[4]["inicio"], ws[9]["fim"])                          # "dois" … "sete"
    assert [u["texto"] for u in al["legenda"] if re.search(r"\d", u["texto"])] == ["2027?", "30,", "1º"]
    # a frase fecha na pontuação do roteiro: é o que os cortes usam para a pausa entre frases
    fecha = [w["texto"] for w in al["palavras"] if w["fim_frase"]]
    assert fecha == ["sete", "prazo", "artecon", "empresa", "regularizar", "semestre", "caso", "dúvida", "gente"]


def test_30_de_outubro_contra_30_10_e_50_mil_reais_contra_r_50_000():
    al = alinhar.alinhar("O prazo vence em 30/10. O limite é R$ 50.000,00 por mês.",
                         falas("o prazo vence em trinta de outubro o limite é cinquenta mil reais por mês"), [], CFG)
    assert al["divergencias"] == [] and al["texto_final"] == "O prazo vence em 30/10. O limite é R$ 50.000,00 por mês."
    al = alinhar.alinhar("O prazo vence em 30 de outubro, até 50 mil reais.",
                         falas("o prazo vence em trinta de outubro até cinquenta mil reais"), [], CFG)
    assert al["divergencias"] == [] and al["texto_final"] == "O prazo vence em 30 de outubro, até 50 mil reais."


def test_decimal_com_mil_milhao_ou_bilhao_vale_o_numero_inteiro():
    """"R$ 4,8 milhões" é 4.800.000, e não R$ 4,80: o mil, o milhão e o bilhão depois das casas decimais multiplicam o número (antes
    eles entravam nas casas e sumiam, e "4,8 mil", "4,8 milhões" e "4,8 bilhões" davam a mesma ficha)."""
    gl = numeros.glossario(GLOSSARIO)
    chave = lambda t: [x["chave"] for x in numeros.analisar(t.split(), gl) if x["tipo"] in numeros.SENTIDO]
    for texto, esperado in [("R$ 4,8 milhões", "#valor:4800000"), ("quatro milhões e oitocentos mil reais", "#valor:4800000"),
                            ("quatro vírgula oito milhões de reais", "#valor:4800000"), ("quatro vírgula oito mil reais", "#valor:4800"),
                            ("R$ 4,8 mil", "#valor:4800"), ("R$ 2,5 bilhões", "#valor:2500000000"), ("R$ 1,5 milhão", "#valor:1500000"),
                            ("um milhão e meio de reais", "#valor:1500000"), ("2,5 milhões", "#num:2500000"),
                            ("dois vírgula cinco milhões", "#num:2500000"),
                            # o que não tem multiplicador não muda
                            ("1,5%", "#pct:1.5"), ("R$ 75,90", "#valor:75.9"), ("zero vírgula zero cinco", "#num:0.05"),
                            ("zero vírgula vinte e cinco", "#num:0.25")]:
        assert chave(texto) == [esperado], texto
    roteiro = "O teto do Simples Nacional é de R$ 4,8 milhões por ano."
    # dito certo, de outro jeito: sem divergência, e a legenda na grafia do roteiro
    for dito in ("o teto do simples nacional é de quatro milhões e oitocentos mil reais por ano",
                 "o teto do simples nacional é de quatro vírgula oito milhões de reais por ano"):
        al = alinhar.alinhar(roteiro, falas(dito), [], CFG)
        assert al["divergencias"] == [] and al["texto_final"] == roteiro, dito
    # dito mil vezes menor: divergência (regravar), e a legenda mostra o que foi dito
    al = alinhar.alinhar(roteiro, falas("o teto do simples nacional é de quatro vírgula oito mil reais por ano"), [], CFG)
    (d,) = al["divergencias"]
    assert (d["tipo"], d["regravar"]) == ("numero", True) and "4.800" in d["falado"] and "4,8 milhões" in d["roteiro"], d
    assert "4,8 milhões" not in al["texto_final"]
    # fora do roteiro, o valor sai em algarismos, inteiro
    al = alinhar.alinhar("O prazo vence hoje.", falas("o prazo de quatro vírgula oito milhões de reais vence hoje"), [], CFG)
    assert "R$ 4.800.000" in al["texto_final"] and "R$ 4,80" not in al["texto_final"]


# ------------------------------------------------------------------ divergências (regravar)
def test_dia_15_contra_dia_25_pede_regravar_e_a_transcricao_errou_volta_o_roteiro():
    fala = "O prazo vence dia 25. Fale com a gente."
    ws = falas("o prazo vence dia quinze fale com a gente")
    al = alinhar.alinhar(fala, ws, [], CFG)
    (d,) = al["divergencias"]
    assert {k: d[k] for k in ("k", "falado", "roteiro", "tipo", "regravar", "transcricao_errou")} == \
        {"k": 0, "falado": "dia 15", "roteiro": "dia 25", "tipo": "numero", "regravar": True, "transcricao_errou": False}
    assert d["t"] == ws[4]["inicio"] and d["confianca"] == 0.9 and re.fullmatch(r"[0-9a-f]{16}", d["id"])
    # a legenda mostra o que foi dito (nunca o 25 do roteiro), com o número em algarismo
    assert al["texto_final"] == "O prazo vence dia 15 Fale com a gente." and "25" not in al["texto_final"]
    assert relatorio.situacao({"divergencias": al["divergencias"]}) == "regravar"
    # a marca é o id da divergência, e não a posição na lista: o número 0 não marca nada
    assert alinhar.alinhar(fala, ws, [], CFG, {"transcricao_errou": [0]})["divergencias"][0]["transcricao_errou"] is False
    # o administrador ouviu "25": "A transcrição errou (vale o roteiro)" — a legenda passa a ser a do roteiro naquele trecho
    ok = alinhar.alinhar(fala, ws, [], CFG, {"transcricao_errou": [d["id"]]})
    assert ok["divergencias"][0]["transcricao_errou"] is True and ok["texto_final"] == fala and ok["divergencias"][0]["id"] == d["id"]
    assert relatorio.situacao({"divergencias": ok["divergencias"]}) == "pronto"
    (u,) = [u for u in ok["legenda"] if u["texto"] == "25."]
    assert (u["ini"], u["fim"]) == (ws[4]["inicio"], ws[4]["fim"])


def test_a_transcricao_errou_marca_a_divergencia_pelo_conteudo_e_nunca_cai_em_outra():
    """O robô alinha de novo a cada rodada, com as Configurações do momento. O administrador cadastra a variante "ce be esse" para a CBS
    (como o LEIAME sugere) e marca "A transcrição errou" só no termo: na rodada da montagem o termo deixa de ser divergência e a lista
    vira só o valor — que a pessoa disse errado ("seiscentos reais" contra R$ 500,00). A marca do termo não cai no valor: ele continua
    pedindo regravar, e a legenda nunca diz um valor que o áudio não diz."""
    fala = "Bom dia. A CBS começa a valer em 2027 e a multa mínima é de R$ 500,00 para quem atrasar a entrega."
    ws = falas("bom dia a ce be esse começa a valer em dois mil e vinte e sete e a multa mínima é de seiscentos reais para quem atrasar a "
               "entrega")
    r1 = alinhar.alinhar(fala, ws, [], CFG)
    termo, valor = r1["divergencias"]
    assert [(d["k"], d["tipo"], d["falado"], d["roteiro"]) for d in (termo, valor)] == [
        (0, "termo", "A ce be esse", "A CBS"), (1, "numero", "de R$ 600", "de R$ 500,00")]
    cfg2 = {**CFG, "variantes": {**VARIANTES, "CBS": VARIANTES["CBS"] + ["ce be esse"]}}
    r2 = alinhar.alinhar(fala, ws, [], cfg2, {"transcricao_errou": [termo["id"]]})
    (d,) = r2["divergencias"]
    assert (d["k"], d["id"], d["transcricao_errou"]) == (0, valor["id"], False)                 # o mesmo valor, o mesmo id, aberto
    assert relatorio.situacao({"divergencias": r2["divergencias"]}) == "regravar"
    assert "R$ 600" in r2["texto_final"] and "500,00" not in r2["texto_final"]
    # marcado o valor (o administrador ouviu "quinhentos"), vale o roteiro: o id da rodada anterior continua apontando para ele
    r3 = alinhar.alinhar(fala, ws, [], cfg2, {"transcricao_errou": [termo["id"], valor["id"]]})
    assert r3["divergencias"][0]["transcricao_errou"] is True and "R$ 500,00" in r3["texto_final"]
    # o mesmo instante com outro texto (o roteiro mudou ali) é outra divergência: a marca antiga não vale
    r4 = alinhar.alinhar(fala.replace("500,00", "400,00"), ws, [], cfg2, {"transcricao_errou": [valor["id"]]})
    assert r4["divergencias"][0]["id"] != valor["id"] and r4["divergencias"][0]["transcricao_errou"] is False


def test_manter_este_trecho_aponta_o_corte_pela_chave_e_nao_pelo_numero():
    """"A transcrição errou" na data põe a pontuação do roteiro ("30/10.") naquele trecho, e a pausa de 0,9 s depois dela passa a ser
    entre frases (limite de 0,8 s): entra um corte novo, ANTES do que o administrador mandou manter no mesmo ajuste (a pausa de 1,2 s
    depois de "juros"), e o número dos cortes seguintes anda uma casa. A chave do corte ("<clipe>:<quadro>" de onde começa o silêncio)
    não muda: o trecho escolhido fica, e o corte novo não é mantido por engano."""
    fala = "Atenção. O prazo vence em 30/10. Depois disso, há multa e juros todo mês."
    pal, sil, t = [], [(0.0, 0.5)], 0.5
    for w in "atenção o prazo vence em trinta e um de outubro depois disso há multa e juros todo mês".split():
        pal.append({"texto": w, "inicio": round(t, 2), "fim": round(t + 0.3, 2), "confianca": 0.9})
        t += 0.3
        vao = {"outubro": 0.9, "juros": 1.2}.get(w, 0.1)
        if vao > 0.5:
            sil.append((round(t, 2), round(t + vao, 2)))
        t += vao
    sil.append((round(t, 2), round(t + 1.0, 2)))
    partes = [{"n": 1, "inicio_q": 0, "quadros": int((t + 1.0) * 30)}]
    cfg = {"glossario": [], "variantes": {}, "pausa_max_s": 1.0, "pausa_bloco_s": 0.8}

    def rodada(aj):
        a = alinhar.alinhar(fala, pal, [], cfg, aj)
        return a, cortes.planejar(partes, sil, cfg, a["palavras"], a["remover"], aj.get("manter") or [])
    a1, p1 = rodada({})
    (div,) = a1["divergencias"]
    assert [(c["k"], c["tipo"]) for c in p1["cortes"]] == [(0, "inicio"), (1, "pausa"), (2, "fim")]
    juros = p1["cortes"][1]
    assert juros["dur_s"] == pytest.approx(0.9) and re.fullmatch(r"1:\d+", juros["chave"])
    a2, p2 = rodada({"transcricao_errou": [div["id"]], "manter": [juros["chave"]]})
    meio = [c for c in p2["cortes"] if "chave" in c]
    assert [(c["k"], c["dur_s"], c["mantido"]) for c in meio] == [(1, pytest.approx(0.5), False), (2, pytest.approx(0.9), True)]
    assert meio[1]["chave"] == juros["chave"] and meio[0]["chave"] != juros["chave"]
    # o número de antes (1) não mantém nada: só a chave
    assert all(not c["mantido"] for c in rodada({"transcricao_errou": [div["id"]], "manter": [1]})[1]["cortes"] if "chave" in c)
    assert p2["fala_q"] - p1["fala_q"] == pytest.approx(27 - 15, abs=1)                       # +0,9 s mantido, −0,5 s do corte novo


@pytest.mark.parametrize("velho, novo, tipo, falado, roteiro", [
    ("dia trinta", "dia quinze", "numero", "dia 15", "dia 30"),                             # troca
    ("dois mil e vinte e sete", "dois mil e vinte e seis", "data", "para 2026", "para 2027"),
    ("primeiro semestre", "segundo semestre", "numero", "no 2º", "no 1º"),
    ("a cbs fora", "a fora", "termo", "a", "a CBS"),                                          # falta
    ("dia trinta para", "dia trinta de outubro para", "data", "dia 30/10", "dia 30"),          # sobra (o mês a mais)
    ("o ibs e a cbs", "o ibs e a cps", "termo", "a cps", "a CBS"),                             # "cps" é variante da CBS, não do IBS…
])
def test_divergencia_de_numero_prazo_ou_termo_em_qualquer_posicao(velho, novo, tipo, falado, roteiro):
    al = alinhar.alinhar(fala_de("simples"), falas(troca_lexica("simples", velho, novo)), [], CFG)
    if velho == "o ibs e a cbs":                                                              # …mas é da CBS: aqui casa
        assert al["divergencias"] == [] and al["trocas"][-1]["motivo"] == "variante"
        return
    (d,) = al["divergencias"]
    assert (d["tipo"], d["falado"], d["roteiro"], d["regravar"]) == (tipo, falado, roteiro, True), d


def test_palavra_comum_diferente_nao_e_divergencia_e_a_legenda_nao_inventa():
    al = alinhar.alinhar(fala_de("simples"), falas(troca_lexica("simples", "para regularizar", "para resolver")), [], CFG)
    assert al["divergencias"] == [] and [x["texto"] for x in al["fora_do_roteiro"]] == ["resolver"]
    assert [x["texto"] for x in al["omitido"]] == ["regularizar"]
    assert "resolver" in al["texto_final"] and "regularizar" not in al["texto_final"]      # só o que foi dito
    # artigo trocado por "um" não é número (não pede regravação)
    al = alinhar.alinhar("Toda segunda, o assunto da sua empresa.", falas("toda segunda um assunto da sua empresa"), [], CFG)
    assert al["divergencias"] == [] and [x["texto"] for x in al["fora_do_roteiro"]] == ["um"]
    # a fala que não tem nada a ver com o roteiro: aviso
    al = alinhar.alinhar(fala_de("lucro"), falas(ROTEIROS["reforma"][2]), [], CFG)
    assert "fala_diferente_do_roteiro" in al["avisos"] and al["cobertura"] < 0.6 and al["divergencias"]


# ------------------------------------------------------------------ grafia: termos, variantes e palavras parecidas
def test_ips_vira_ibs_so_onde_o_roteiro_tem_ibs():
    fala = "O IBS entra em teste. O imposto novo é simples."
    ws = falas("o ips entra em teste o ips novo é simples")
    al = alinhar.alinhar(fala, ws, [], CFG)
    assert al["divergencias"] == [] and al["trocas"] == [{"t": ws[1]["inicio"], "de": "ips", "para": "IBS", "motivo": "variante"}]
    assert al["texto_final"] == "O IBS entra em teste. O ips novo é simples."
    assert [x["texto"] for x in al["fora_do_roteiro"]] == ["ips"] and [x["texto"] for x in al["omitido"]] == ["imposto"]
    # sem a variante nas Configurações, o IBS não foi dito: divergência de termo
    sem = alinhar.alinhar(fala, ws, [], {**CFG, "variantes": {}})
    assert [(d["tipo"], d["roteiro"]) for d in sem["divergencias"]] == [("termo", "O IBS")]


def test_e_social_vira_esocial_e_as_outras_grafias_do_glossario():
    fala = "O prazo do eSocial e da DCTFWeb muda. Fale com a Artecon sobre o PIS e a Cofins, fora do DAS."
    ws = falas("o prazo do é social e da dctf web muda fale com a arte com sobre o piz e a confins fora do das")
    al = alinhar.alinhar(fala, ws, [], CFG)
    assert al["divergencias"] == [] and al["fora_do_roteiro"] == [] and al["texto_final"] == fala
    assert [(t["de"], t["para"], t["motivo"]) for t in al["trocas"]] == [
        ("é social", "eSocial", "termo"), ("dctf web", "DCTFWeb", "termo"), ("arte com", "Artecon", "variante"),
        ("piz", "PIS", "variante"), ("confins", "Cofins", "variante")]
    # "é social" é uma palavra só na legenda, no tempo das duas
    (u,) = [u for u in al["legenda"] if u["texto"] == "eSocial"]
    assert (u["ini"], u["fim"]) == (ws[3]["inicio"], ws[4]["fim"])
    # o DAS do roteiro casa com o "das" da forma léxica; o termo trocado por outro, não
    al = alinhar.alinhar("Pague no DAS até sexta.", falas("pague no darf até sexta"), [], CFG)
    assert [(d["tipo"], d["falado"], d["roteiro"]) for d in al["divergencias"]] == [("termo", "no DARF", "no DAS")]


def test_palavra_parecida_sai_na_grafia_do_roteiro_e_vai_para_as_trocas():
    al = alinhar.alinhar("Quem ficou com pendência tem até sexta para regularizar.",
                         falas("quem ficou com pendencia tem até sexta pra regularisar"), [], CFG)
    assert al["divergencias"] == [] and al["texto_final"] == "Quem ficou com pendência tem até sexta para regularizar."
    assert [(t["de"], t["para"], t["motivo"]) for t in al["trocas"]] == [("pra", "para", "grafia"), ("regularisar", "regularizar", "grafia")]


def test_forma_de_exibicao_fora_do_roteiro():
    """A palavra fora do roteiro sai na forma de exibição da frase (Display), com pontuação e algarismos; sem ela, com os números em
    algarismos. A número a mais na fala é divergência (sobra)."""
    fala = "O prazo vence em 2027."
    ws = falas("o prazo final vence em dois mil e vinte e sete dia trinta")
    frases = [{"display": "O prazo final vence em 2027, dia 30.", "inicio": ws[0]["inicio"], "fim": ws[-1]["fim"]}]
    al = alinhar.alinhar(fala, ws, frases, CFG)
    assert al["texto_final"] == "O prazo final vence em 2027. dia 30."
    assert [x["texto"] for x in al["fora_do_roteiro"]] == ["final"]
    assert [(d["tipo"], d["falado"], d["roteiro"]) for d in al["divergencias"]] == [("numero", "2027 dia 30", "2027")]
    sem = alinhar.alinhar(fala, ws, [], CFG)
    assert sem["texto_final"] == "O prazo final vence em 2027. dia 30"


def test_hesitacao_repeticao_e_falso_inicio():
    """Os sons de hesitação ficam fora do alinhamento (cortes.py os corta); a palavra repetida e o começo de palavra viram
    sugestão — nunca corte automático — e ficam na legenda, porque foram ditos."""
    fala = "As empresas devem pagar até sexta."
    al = alinhar.alinhar(fala, falas("hum as empresas ééé devem devem pagar até sexta"), [], CFG)
    assert al["divergencias"] == [] and al["fora_do_roteiro"] == [] and al["omitido"] == []
    assert [(r["tipo"], r["texto"], r["automatico"]) for r in al["remover"]] == [("repeticao", "devem devem", False)]
    assert al["texto_final"] == "As empresas devem devem pagar até sexta."
    assert [(w["texto"], w["rot_de"]) for w in al["palavras"] if w["texto"] in ("hum", "ééé")] == [("hum", None), ("ééé", None)]
    al = alinhar.alinhar(fala, falas("as empresas de devem pagar até sexta"), [], CFG)
    assert [(r["tipo"], r["texto"]) for r in al["remover"]] == [("falso_inicio", "de devem")]


def test_unidade_do_roteiro_nunca_se_quebra_na_legenda(tmp_path):
    import legenda
    fala = "O limite anual do faturamento do microempreendedor é de R$ 81.000,00 por ano, até 31 de dezembro de 2026."
    lexica = ("o limite anual do faturamento do microempreendedor é de oitenta e um mil reais por ano até trinta e um de dezembro "
              "de dois mil e vinte e seis")
    al = alinhar.alinhar(fala, falas(lexica, passo=0.25, dur=0.2), [], CFG)
    assert al["divergencias"] == [] and al["texto_final"] == fala
    assert [u["texto"] for u in al["legenda"]][-6:] == ["de", "R$ 81.000,00", "por", "ano,", "até", "31 de dezembro de 2026."]
    info = legenda.gravar(tmp_path / "l.ass", al["legenda"], GLOSSARIO)
    linhas = [l for e in (tmp_path / "l.ass").read_text(encoding="utf-8").splitlines() if e.startswith("Dialogue:")
              for l in e.split(",,0,0,0,,", 1)[1].split("\\N")]
    assert any("R$\\h81.000,00" in l for l in linhas) and any("31\\hde\\hdezembro\\hde\\h2026." in l for l in linhas)
    assert not any(l.endswith(("R$", "31")) or l.startswith(("81.000", "dezembro", "de 2026")) for l in linhas), linhas
    assert [b["u"] for b in info["lista"]] == sorted(b["u"] for b in info["lista"]) and info["lista"][0]["u"] == 0
    assert sum(b["palavras"] for b in info["lista"]) == len(fala.split())
    # cada bloco leva as palavras do roteiro perto dele (as letras), para a tela recusar o que o robô recusaria
    for b in info["lista"]:
        assert b["perto"] == sorted({numeros.letras(w) for w in b["texto"].split()} - {""}), b


# ------------------------------------------------------------------ editor de legenda (administrador)
def test_editor_de_legenda_troca_palavra_a_palavra_e_recusa_o_resto():
    fala = "Quem ficou com pendência tem até sexta, dia 30, para regularizar o MEI em outubro de 2026."
    ws = falas("quem ficou com pendência tem até sexta dia trinta para resolver o mei em outubro de dois mil e vinte e seis")
    base = alinhar.alinhar(fala, ws, [], CFG)
    u = {x["texto"]: x["u"] for x in base["legenda"]}
    casos = {
        f"{u['resolver']}:1": "regularizar",                     # a palavra do roteiro naquele trecho: aceita
        f"{u['pendência']}:1": "pendências",                     # parecida (≥ 0,6) com a que estava: aceita
        f"{u['Quem']}:2": "quem fica",                           # maiúscula e palavra parecida ("ficou" → "fica"): aceita
        f"{u['sexta,']}:1": "sexta-feira,",                      # hífen une: a mesma palavra
        f"{u['30,']}:1": "31,",                                  # número: recusa
        f"{u['MEI']}:1": "CBS",                                  # termo: recusa
        f"{u['outubro de 2026.']}:3": "outubro de 2027.",        # ano (parecido nas letras, mas é número): recusa
        f"{u['com']}:1": "com a",                                # palavra a mais: recusa
        f"{u['tem']}:1": "multa",                                # outra palavra: recusa
        f"{u['até']}:1": "{\\an8}até",                           # comando do ASS: recusa
        "999": "nada",                                           # bloco que não existe
    }
    al = alinhar.alinhar(fala, ws, [], CFG, {"legenda": casos})
    assert sorted((r["bloco"], r["motivo"]) for r in al["legenda_ajustes"]["recusados"]) == sorted([
        (f"{u['30,']}:1", "numero_ou_termo"), (f"{u['MEI']}:1", "numero_ou_termo"), (f"{u['outubro de 2026.']}:3", "numero_ou_termo"),
        (f"{u['com']}:1", "numero_de_palavras"), (f"{u['tem']}:1", "palavra_diferente"), (f"{u['até']}:1", "texto_invalido"),
        ("999", "bloco_inexistente")])
    assert al["legenda_ajustes"]["editados"] == 4 and "legenda_recusada" in al["avisos"]
    assert al["texto_final"] == "quem fica com pendências tem até sexta-feira, dia 30, para regularizar o MEI em outubro de 2026."
    # só a chave "u" (sem n): as palavras novas têm de fechar unidades inteiras
    so_u = alinhar.alinhar(fala, ws, [], CFG, {"legenda": {str(u["com"]): "com a", str(u["dia"]): "Dia 30,"}})
    assert so_u["legenda_ajustes"] == {"editados": 1, "recusados": [{"bloco": str(u["com"]), "motivo": "palavra_diferente"}]}
    assert "Dia 30," in so_u["texto_final"]


def test_edicoes_da_legenda_valem_na_ordem_da_lista_e_a_nova_vence():
    """A edição antiga ("1:1", de uma montagem anterior) cai dentro do bloco que o administrador editou agora ("0:4"). No objeto, o jsonb
    devolve as chaves em outra ordem (as curtas primeiro, depois por byte: "0:4" antes de "1:1") e a antiga desfazia a nova sem
    aparecer em recusados; na lista, o robô aplica na ordem da tela e a nova, no fim, vale."""
    fala = "Quem atrasar paga multa."
    ws = falas("quem atrasar paga multa")
    antiga, nova = ["1:1", "atrasa"], ["0:4", "Quem atrasará paga multa."]
    al = alinhar.alinhar(fala, ws, [], CFG, {"legenda": [antiga, nova]})
    assert al["texto_final"] == "Quem atrasará paga multa." and al["legenda_ajustes"] == {"editados": 2, "recusados": []}
    # a mesma coisa num objeto na ordem que o jsonb devolve: a antiga, aplicada depois, desfaz a nova (o defeito da forma antiga)
    assert alinhar.alinhar(fala, ws, [], CFG, {"legenda": dict([nova, antiga])})["texto_final"] == "Quem atrasa paga multa."
    # cada unidade da legenda leva as palavras do roteiro perto dela (a tela confere a palavra nova como o robô)
    assert [u["perto"] for u in al["legenda"]] == [["quem"], ["atrasar"], ["paga"], ["multa"]]


# ------------------------------------------------------------------ cortes: o que nunca sai e o que sai sozinho
def test_um_uma_e_e_nunca_saem_nem_ditos_devagar():
    """"é dia 30", "e o MEI", "um milhão", "um salário mínimo", "uma parcela", "é social": ditos devagar, com pausa dos dois lados;
    a pausa longa encurta, a palavra fica. Um pedido de corte automático sobre o "um" (de um alinhamento errado) vira sugestão."""
    fala = "O prazo é dia 30. E o MEI fatura até um milhão. Uma parcela de um salário mínimo vai ao eSocial."
    ws = com_tempos([("o", 0.50, 0.62), ("prazo", 0.72, 1.10), ("é", 1.45, 1.95), ("dia", 2.45, 2.70), ("trinta", 2.80, 3.20),
                     ("e", 4.40, 4.85), ("o", 4.95, 5.05), ("mei", 5.15, 5.50), ("fatura", 5.60, 6.00), ("até", 6.10, 6.40),
                     ("um", 7.70, 8.05), ("milhão", 8.15, 8.60), ("uma", 9.90, 10.30), ("parcela", 10.40, 10.90), ("de", 11.00, 11.10),
                     ("um", 11.70, 12.10), ("salário", 12.70, 13.20), ("mínimo", 13.30, 13.80), ("vai", 13.90, 14.10),
                     ("ao", 14.20, 14.35), ("é", 14.45, 14.80), ("social", 15.50, 16.00)])
    dur = 17.0
    al = alinhar.alinhar(fala, ws, [], CFG)
    assert al["divergencias"] == [] and al["fora_do_roteiro"] == [] and al["texto_final"] == fala
    sil = silencios([(w["inicio"], w["fim"]) for w in ws], dur)
    plano = cortes.planejar(parte(dur), sil, CFG, al["palavras"], al["remover"])
    assert [c["tipo"] for c in plano["cortes"]] == ["inicio", "pausa", "pausa", "pausa", "fim"], plano["cortes"]
    assert all(ficou(plano, w["inicio"], w["fim"]) for w in ws)                               # nenhuma palavra cai num corte
    # o pedido automático sobre o "um" (7,70 a 8,05) vira sugestão; o plano não muda
    pedido = cortes.planejar(parte(dur), sil, CFG, al["palavras"], [{"ini": 7.62, "fim": 8.10, "tipo": "hesitacao", "automatico": True}])
    assert pedido["trechos"] == plano["trechos"] and [s["tipo"] for s in pedido["sugestoes"]] == ["hesitacao"]
    # "é", "e", "um" e "uma" nunca são som de hesitação; "ééé", "hum", "ãh", "hã", "hm", "ahn" são
    assert not any(cortes.e_hesitacao(w) for w in ("um", "uma", "e", "é", "É", "éé", "há", "ah", "eh", "humano", "o"))
    assert all(cortes.e_hesitacao(w) for w in ("ééé", "eee", "Hum,", "hmm", "ãh", "hã", "ahn", "aaa"))


def test_voz_entre_palavras_seguidas_do_roteiro_sai_e_fora_disso_vira_sugestao():
    fala = "O prazo do eSocial vence em 30/10."
    lista = [("o", 0.50, 0.62), ("prazo", 0.72, 1.10), ("do", 1.20, 1.30), ("e", 1.40, 1.50), ("social", 1.60, 2.00),
             ("vence", 2.10, 2.45), ("em", 3.55, 3.70), ("trinta", 3.80, 4.15), ("de", 4.25, 4.35), ("outubro", 4.45, 4.95)]
    ws, dur = com_tempos(lista), 6.0
    eee = (2.75, 3.15)                                                                        # "ééé" que a transcrição não escreveu
    sil = silencios([(w["inicio"], w["fim"]) for w in ws] + [eee], dur)
    al = alinhar.alinhar(fala, ws, [], CFG)
    plano = cortes.planejar(parte(dur), sil, CFG, al["palavras"], al["remover"])
    (c,) = [c for c in plano["cortes"] if c["tipo"] == "voz_entre_palavras"]
    assert c["automatico"] is True and c["dur_s"] == pytest.approx(0.80, abs=0.01)           # 2,60 a 3,40: fica 0,30 s de silêncio
    assert not cortes.remapear(plano, 2.95)[1] and all(ficou(plano, w["inicio"], w["fim"]) for w in ws)
    depois_de_vence = cortes.remapear(plano, 3.55)[0] - cortes.remapear(plano, 2.45)[0]
    assert depois_de_vence == pytest.approx(0.30, abs=1 / 30 + 1e-6)
    # "Manter este trecho", pela chave do corte (o vão depois de "vence", em quadros): a voz fica
    assert c["chave"] == "1:73"                                                              # o quadro de 2,45 s (para baixo)
    mantido = cortes.planejar(parte(dur), sil, CFG, al["palavras"], al["remover"], manter=[c["chave"]])
    assert cortes.remapear(mantido, 2.95)[1] and mantido["fala_q"] - plano["fala_q"] == pytest.approx(24, abs=1)
    # o roteiro tem uma palavra ali ("hoje") que a transcrição não tem: pode ser ela — só sugestão, a voz fica
    al2 = alinhar.alinhar("O prazo do eSocial vence hoje em 30/10.", ws, [], CFG)
    assert [x["texto"] for x in al2["omitido"]] == ["hoje"]
    p2 = cortes.planejar(parte(dur), sil, CFG, al2["palavras"], al2["remover"])
    assert [s["tipo"] for s in p2["sugestoes"]] == ["voz_entre_palavras"] and cortes.remapear(p2, 2.95)[1]
    # sem o alinhamento (as palavras sem rot): também só sugestão
    p3 = cortes.planejar(parte(dur), sil, CFG, [{"texto": w["texto"], "ini": w["inicio"], "fim": w["fim"]} for w in ws])
    assert [s["tipo"] for s in p3["sugestoes"]] == ["voz_entre_palavras"] and cortes.remapear(p3, 2.95)[1]
    # intervalo comprido demais (2,5 s) com voz: pode ser fala que a transcrição perdeu — sugestão, mesmo entre palavras seguidas
    longe = com_tempos(lista[:6] + [(w, a + 1.4, b + 1.4) for w, a, b in lista[6:]])
    sil4 = silencios([(w["inicio"], w["fim"]) for w in longe] + [(2.75, 3.75)], dur + 1.4)
    al4 = alinhar.alinhar(fala, longe, [], CFG)
    p4 = cortes.planejar(parte(dur + 1.4), sil4, CFG, al4["palavras"], al4["remover"])
    assert [s["tipo"] for s in p4["sugestoes"]] == ["voz_entre_palavras"] and cortes.remapear(p4, 3.2)[1]
    # voz curta (abaixo de 0,15 s somados) num intervalo curto: nada
    sil5 = silencios([(w["inicio"], w["fim"]) for w in ws] + [(2.90, 3.00)], dur)
    p5 = cortes.planejar(parte(dur), sil5, CFG, al["palavras"], al["remover"])
    assert not [c for c in p5["cortes"] if c["tipo"] == "voz_entre_palavras"]


def test_som_de_hesitacao_que_veio_como_palavra_sai_e_ee_fica():
    fala = "Fale com a gente."
    ws = com_tempos([("fale", 0.5, 0.9), ("hum", 1.2, 1.5), ("com", 1.8, 2.0), ("ééé", 2.3, 2.8), ("a", 3.1, 3.2), ("éé", 3.5, 3.8),
                     ("gente", 4.1, 4.6)])
    dur = 5.5
    sil = silencios([(w["inicio"], w["fim"]) for w in ws], dur)
    al = alinhar.alinhar(fala, ws, [], CFG)
    plano = cortes.planejar(parte(dur), sil, CFG, al["palavras"], al["remover"])
    hes = [c for c in plano["cortes"] if c["tipo"] == "hesitacao"]
    assert [(c["texto"], c["automatico"]) for c in hes] == [("hum", True), ("ééé", True)]
    assert not cortes.remapear(plano, 1.35)[1] and not cortes.remapear(plano, 2.55)[1]
    assert all(ficou(plano, w["inicio"], w["fim"]) for w in ws if w["texto"] not in ("hum", "ééé"))   # "éé" fica (não é hesitação)
    # a legenda não tem os sons de hesitação; "éé" foi dito (fora do roteiro)
    assert al["texto_final"] == "Fale com a éé gente." and [x["texto"] for x in al["fora_do_roteiro"]] == ["éé"]
    leg = cortes.no_video(plano, al["legenda"])
    assert [u["texto"] for u in leg] == ["Fale", "com", "a", "éé", "gente."] and all(b["ini"] >= a["fim"] for a, b in zip(leg, leg[1:]))
    # voz no intervalo que o "hum" não explica: pode ser fala — sugestão
    ws2 = com_tempos([("fale", 0.5, 0.9), ("hum", 1.2, 1.4), ("com", 2.4, 2.6), ("a", 2.7, 2.8), ("gente", 2.9, 3.3)])
    sil2 = silencios([(w["inicio"], w["fim"]) for w in ws2] + [(1.7, 2.1)], 4.0)
    al2 = alinhar.alinhar(fala, ws2, [], CFG)
    p2 = cortes.planejar(parte(4.0), sil2, CFG, al2["palavras"], al2["remover"])
    assert [s["tipo"] for s in p2["sugestoes"]] == ["hesitacao"] and cortes.remapear(p2, 1.9)[1]


def test_palavra_dita_colada_no_hum_e_perdida_pela_transcricao_nao_sai_com_ele():
    """"você hum não precisa", com o "não" dito colado no "hum" e perdido pela transcrição (omissão de palavra curta): o corte do "hum"
    levaria o "não" junto, e o vídeo diria "você precisa declarar". Só sai sozinho entre palavras seguidas do roteiro e com toda a voz
    DENTRO do som de hesitação; fora disso, sugestão, e a voz fica."""
    fala = "Neste caso você não precisa declarar o imposto."
    lista = [("neste", 0.5, 0.8), ("caso", 0.9, 1.2), ("você", 1.3, 1.55), ("hum", 1.65, 1.95), ("precisa", 2.35, 2.8), ("declarar", 2.9, 3.4),
             ("o", 3.5, 3.55), ("imposto", 3.65, 4.1)]
    ws, dur, nao = com_tempos(lista), 5.0, (1.95, 2.2)
    sil = silencios([(w["inicio"], w["fim"]) for w in ws] + [nao], dur)
    al = alinhar.alinhar(fala, ws, [], CFG)
    assert [x["texto"] for x in al["omitido"]] == ["não"] and al["divergencias"] == []
    plano = cortes.planejar(parte(dur), sil, CFG, al["palavras"], al["remover"])
    assert [c["tipo"] for c in plano["cortes"]] == ["inicio", "fim"]
    assert [(s["tipo"], s["texto"]) for s in plano["sugestoes"]] == [("hesitacao", "hum")] and ficou(plano, *nao)
    # a transcrição deu ao "hum" o tempo do "não" também (a voz cabe nele), mas "você" e "precisa" não são seguidas: sugestão
    largo = com_tempos([(w, a, 2.2 if w == "hum" else b) for w, a, b in lista])
    al2 = alinhar.alinhar(fala, largo, [], CFG)
    p2 = cortes.planejar(parte(dur), sil, CFG, al2["palavras"], al2["remover"])
    assert [s["tipo"] for s in p2["sugestoes"]] == ["hesitacao"] and ficou(p2, *nao)
    # palavras seguidas do roteiro ("você não precisa", tudo transcrito), mas a voz passa do "hum" (o "você" repetido que a
    # transcrição não escreveu): sugestão
    fala3 = "Você não precisa declarar."
    ws3 = com_tempos([("você", 0.5, 0.8), ("hum", 0.95, 1.2), ("não", 1.75, 1.95), ("precisa", 2.05, 2.5), ("declarar", 2.6, 3.1)])
    sil3 = silencios([(w["inicio"], w["fim"]) for w in ws3] + [(1.2, 1.5)], 4.0)
    al3 = alinhar.alinhar(fala3, ws3, [], CFG)
    p3 = cortes.planejar(parte(4.0), sil3, CFG, al3["palavras"], al3["remover"])
    assert [s["tipo"] for s in p3["sugestoes"]] == ["hesitacao"] and ficou(p3, 1.2, 1.5)
    # e o "hum" sozinho entre "você" e "não" (a voz dentro dele) continua saindo
    sil4 = silencios([(w["inicio"], w["fim"]) for w in ws3], 4.0)
    p4 = cortes.planejar(parte(4.0), sil4, CFG, al3["palavras"], al3["remover"])
    assert [(c["tipo"], c["automatico"]) for c in p4["cortes"] if c["tipo"] == "hesitacao"] == [("hesitacao", True)] and p4["sugestoes"] == []


def test_repeticao_vira_sugestao_com_o_texto():
    fala = "As empresas devem pagar até sexta."
    ws = falas("as empresas devem devem pagar até sexta")
    dur = ws[-1]["fim"] + 1.0
    al = alinhar.alinhar(fala, ws, [], CFG)
    plano = cortes.planejar(parte(dur), silencios([(w["inicio"], w["fim"]) for w in ws], dur), CFG, al["palavras"], al["remover"])
    assert [(s["tipo"], s.get("texto")) for s in plano["sugestoes"]] == [("repeticao", "devem devem")]
    assert [c["tipo"] for c in plano["cortes"]] == ["inicio", "fim"] and all(ficou(plano, w["inicio"], w["fim"]) for w in ws)


# ------------------------------------------------------------------ relatório
def test_relatorio_parcial_e_final_no_tempo_do_video_corrigido(capfd):
    fala = "O prazo vence dia 25. Fale com a Ana Teste."
    ws = falas("o prazo vence dia quinze fale com a ana teste", pausas={5: 1.5})              # pausa de 1,6 s entre as frases
    dur = ws[-1]["fim"] + 1.0
    infos = [{"n": 1, "inicio_q": 0, "quadros": int(dur * 30), "w": 1080, "h": 1920, "fps": 30, "hdr": None, "girado": False,
              "dur": dur}]
    al = alinhar.alinhar(fala, ws, [], CFG)
    plano = cortes.planejar(infos, silencios([(w["inicio"], w["fim"]) for w in ws], dur), CFG, al["palavras"], al["remover"])
    par = relatorio.parcial(al, plano, infos, {"servico": "azure_f0", "segundos_audio": dur, "palavras": len(ws)})
    assert par["parcial"] is True and par["versao"] == 2 and par["robo"] == "0.22.0"
    assert set(par) == {"versao", "robo", "modo", "parcial", "gerado_em", "divergencias", "fora_do_roteiro", "omitido", "avisos",
                        "transcricao"}
    (d,) = par["divergencias"]
    assert "t" not in d and d["clipe"] == 1 and d["em_s"] == pytest.approx(cortes.remapear(plano, ws[4]["inicio"])[0], abs=0.01)
    assert d["em_s"] < ws[4]["inicio"]                                                         # o começo foi cortado
    assert par["transcricao"] == {"servico": "azure_f0", "segundos_audio": round(dur, 1), "palavras": len(ws)}
    leg = {"blocos": 2, "estilo": "normal", "gancho": False, "avisos": [], "lista": [{"u": 0, "em_s": 0.12, "palavras": 5, "texto": "x"}]}
    fim = relatorio.final(al, plano, infos, {"saida": {"duracao_s": 48.0, "fala_s": 45.4}, "audio": {"linear": True},
                                             "quadros_ms": [1, 2, 3, 4]}, {"lufs": -14.1, "pico_dbtp": -2.0, "sem_gps": True}, leg,
                          {"servico": "azure_f0", "segundos_audio": dur, "palavras": len(ws)}, cfg={**CFG, "cartela_extra": "Fale com a gente"})
    assert fim["saida"]["lufs"] == -14.1 and fim["saida"]["pico_dbtp"] == -2.0 and "duracao_acima_do_limite" in fim["avisos"]
    assert fim["cartela_extra"] == "Fale com a gente"                       # o texto extra que foi gravado (o banco confere este)
    assert fim["texto_final"] == "O prazo vence dia 15 Fale com a Ana Teste." and fim["legenda"]["lista"] == leg["lista"]
    assert [c["tipo"] for c in fim["cortes"]] == ["inicio", "pausa", "fim"] and fim["entrada"]["clipes"] == 1
    assert relatorio.situacao(fim) == "regravar"
    json.dumps(fim)
    # o log: só contagens (nada da fala, do roteiro ou do nome)
    segredo.log("relatorio", pedido="00000000-0000-0000-0000-000000000003", **relatorio.resumo_log(fim))
    saida = capfd.readouterr().out
    assert saida.startswith("corretor: relatorio pedido=00000000-0000-0000-0000-000000000003 cortes=3 ")
    for proibido in ("Ana", "Teste", "prazo", "15", "25", "?"):
        assert proibido not in saida.split("cobertura=")[0].split("pedido=")[1].replace("00000000-0000-0000-0000-000000000003", ""), proibido


def test_relatorio_cabe_na_coluna_e_as_divergencias_ficam():
    al = {"divergencias": [{"k": k, "t": 1.0, "falado": "x" * 120, "roteiro": "y" * 120, "tipo": "numero", "regravar": True,
                            "transcricao_errou": False} for k in range(30)],
          "fora_do_roteiro": [{"t": 1.0, "texto": "z" * 120}] * 2000, "omitido": [{"t": 1.0, "texto": "w" * 120}] * 2000,
          "trocas": [], "texto_final": "palavra " * 3000, "avisos": []}
    plano = {"trechos": [[0, 300]], "cortes": [], "sugestoes": []}
    infos = [{"n": 1, "inicio_q": 0, "quadros": 300}]
    rel = relatorio.parcial(al, plano, infos)
    assert len(json.dumps(rel, ensure_ascii=False)) <= relatorio.LIMITE and "relatorio_resumido" in rel["avisos"]
    assert len(rel["divergencias"]) == 30 and relatorio.situacao(rel) == "regravar"


# ------------------------------------------------------------------ de ponta a ponta, com o ffmpeg
E2E_ROTEIRO = '''| Tempo | Fala | Texto na tela |
|---|---|---|
| 0 a 5 s | "O prazo do eSocial vence em 30/10." | PRAZO: 30/10 |
| 5 a 9 s | "Fale com a gente." | cartela final |'''
E2E_PALAVRAS = [("o", 0.50, 0.62), ("prazo", 0.75, 1.10), ("do", 1.22, 1.35), ("e", 1.48, 1.60), ("social", 1.72, 2.10),
                ("vence", 2.22, 2.55), ("em", 3.65, 3.80), ("trinta", 3.92, 4.25), ("de", 4.37, 4.50), ("outubro", 4.62, 5.10),
                ("fale", 6.10, 6.45), ("com", 6.57, 6.75), ("hum", 7.05, 7.40), ("a", 7.70, 7.82), ("gente", 7.95, 8.45)]
E2E_EEE = ("ééé", 2.85, 3.25)                                                                # voz sem palavra entre "vence" e "em"


@pytest.mark.skipif(not sint.tem_ffmpeg(), reason="ffmpeg e ffprobe não instalados (o CI instala pelo apt)")
def test_de_ponta_a_ponta_tira_o_eee_e_o_hum_e_a_legenda_e_o_roteiro(tmp_path, monkeypatch, capfd):
    """Vídeo sintético (o alto da imagem pisca durante cada palavra; a "voz" tem também um "ééé" que a transcrição não escreveu e um
    "hum" que ela escreveu): o alinhamento com a tabela do roteiro manda tirar os dois; na saída, cada subida da voz vem com uma
    subida do branco (até 1 quadro) — se o "ééé" ou o "hum" ficassem, haveria voz sem branco —, a legenda gravada tem "eSocial" e
    "30/10." (nunca "trinta" nem "hum") e o relatório final sai sem divergência."""
    monkeypatch.setenv("RADAR_VIDEO_ISOLADO", "local")
    import audio
    import cartela
    import conferir
    import isolado
    import legenda
    import montar
    import sondar
    reais = [p for p in E2E_PALAVRAS if p[0] != "hum"]
    dur = 9.5
    wav = sint.voz(tmp_path / "voz.wav", E2E_PALAVRAS + [E2E_EEE], dur)
    sint.video(tmp_path / "clipe.mp4", wav, 1080, 1920, 30, dur, piscar=reais)
    (tmp_path / "ent").mkdir()
    pastas = isolado.Pastas(tmp_path / "ent", tmp_path / "sai", ROBO / "fontes")
    isolado.preparar(pastas)
    shutil.copy(tmp_path / "clipe.mp4", pastas.ent / "1")
    infos = sondar.sondar_todas([{"n": 1, "tipo": "video/mp4", "bytes": (pastas.ent / "1").stat().st_size}], pastas)
    audio.extrair(infos, pastas)
    sil = audio.silencios("/sai/fala48k.wav", pastas, audio.limiar_silencio(audio.piso_ruido(audio.amostras("/sai/fala48k.wav", pastas))))
    fala, formato = alinhar.extrair_fala(E2E_ROTEIRO)
    al = alinhar.alinhar(fala, com_tempos(E2E_PALAVRAS), [], CFG)
    plano = cortes.planejar(infos, sil, CFG, al["palavras"], al["remover"])
    assert [c["tipo"] for c in plano["cortes"]] == ["inicio", "voz_entre_palavras", "pausa", "hesitacao", "fim"], plano["cortes"]
    par = relatorio.parcial(al, plano, infos, {"servico": "azure_f0", "segundos_audio": dur, "palavras": len(E2E_PALAVRAS)})
    assert par["divergencias"] == [] and par["omitido"] == [] and par["fora_do_roteiro"] == []
    leg = legenda.gravar(pastas.sai / "legenda.ass", cortes.no_video(plano, al["legenda"]), GLOSSARIO, "normal", None)
    ass = (pastas.sai / "legenda.ass").read_text(encoding="utf-8")
    assert "eSocial" in ass and "30/10." in ass and not re.search(r"trinta|outubro|hum|ééé", ass)
    assert leg["lista"][0]["u"] == 0 and sum(b["palavras"] for b in leg["lista"]) == len(fala.split())
    cartela.desenhar(pastas.sai / "cartela.png", ["Artecon Artes Contábeis · CNPJ 00.000.000/0001-00 · CRC-SC 000000/O-0"])
    mont = montar.montar(infos, plano, pastas, CFG, preset="veryfast")
    conf = conferir.conferir(pastas, CFG)
    saida = pastas.sai / "reel.mp4"
    luz, voz = sint.subidas([x > 150 for x in sint.luz_do_alto(saida)]), sint.subidas(sint.voz_por_quadro(saida))
    assert len(luz) == len(voz) == len(reais) and all(abs(a - b) <= 1 for a, b in zip(luz, voz)), (luz, voz)
    rel = relatorio.final(al, plano, infos, mont, conf, leg, {"servico": "azure_f0", "segundos_audio": dur, "palavras": 15},
                          cfg=CFG)
    assert relatorio.situacao(rel) == "pronto" and rel["texto_final"] == fala == "O prazo do eSocial vence em 30/10. Fale com a gente."
    assert [(c["tipo"], c.get("automatico")) for c in rel["cortes"] if "em_s" in c] == [("voz_entre_palavras", True), ("pausa", True),
                                                                                          ("hesitacao", True)]
    assert rel["saida"]["lufs"] == conf["lufs"] and rel["conferencia"]["sem_gps"] is True and formato == "tabela"
    assert len(json.dumps(rel, ensure_ascii=False)) <= relatorio.LIMITE
    assert capfd.readouterr() == ("", "")
