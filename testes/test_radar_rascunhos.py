"""v0.9.0 — rascunhos automáticos: a verificação do texto gerado é a mesma da função radar-ia (TypeScript)."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

import radar_rascunhos as rr
from conftest import RAIZ

AMOSTRAS = [
    ("A Receita prorrogou para 30/11/2026 o prazo da Instrução Normativa RFB nº 2.300, art. 5º, § 2º, com multa de 2% e "
     "R$ 1,5 milhão. Vale em março de 2027, por 60 dias, dia 15. [VERIFICAR: vigência]",
     "INSTRUÇÃO NORMATIVA RFB Nº 2.300, DE 2 DE OUTUBRO DE 2026. Art. 5º O prazo fica prorrogado até 30 de novembro de 2026. § 2º multa de 2%."),
    ("Lei Complementar 214/2025 e Decreto nº 12.700; 7,5% e 10 por cento; 01/2027; 3 meses; art. 10-A e arts. 3, 4 e 5; parágrafo único",
     "Lei Complementar nº 214, de 16 de janeiro de 2025, art. 10-A, parágrafo único"),
    ("O MEI tem até 31 de janeiro de 2027 para optar. Faturamento de R$ 81.000,00 e alíquota de 4,5%; prazo de 12 (doze) meses.",
     "O prazo de opção foi prorrogado até 31 de janeiro de 2027. Limite de R$ 81.000,00 por ano."),
    ("Texto sem nenhum número.", "Texto oficial sem números."),
    ("Vence no dia 1º, conforme o nº15 meses e o dia 2ª; art. 3º-A e §1º.", "O prazo vence no dia 1º de cada mês (art. 3º-A)."),   # º/ª e fronteira de palavra
]


def _node_le_typescript() -> bool:
    if shutil.which("node") is None:
        return False
    r = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", "-e", "1"], capture_output=True)
    return r.returncode == 0


@pytest.mark.skipif(not _node_le_typescript(), reason="node com --experimental-strip-types não disponível")
def test_verificacao_do_robo_e_identica_a_da_funcao_de_ia(tmp_path):
    ts = (RAIZ / "supabase" / "functions" / "radar-ia" / "index.ts").read_text(encoding="utf-8")
    codigo = ts[ts.index("const normalizarEspacos"):ts.index("// ------------------------------------------------------------------ IA Central")]
    arquivo = tmp_path / "conferir.ts"
    arquivo.write_text(codigo + "\nconst e = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
                       "console.log(JSON.stringify(e.map(([g, o, t]) => [conferirGerado(g, o, t), [...fatos(g, false).entries()], [...fatos(o, true).entries()]])));",
                       encoding="utf-8")
    entrada = [(g, o, i % 2 == 0) for i, (g, o) in enumerate(AMOSTRAS)]
    r = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", str(arquivo)], input=json.dumps(entrada),
                       capture_output=True, text=True, check=True)
    for (g, o, t), (avisos, f_gerado, f_oficial) in zip(entrada, json.loads(r.stdout)):
        assert rr.conferir_gerado(g, o, t) == avisos
        assert [list(x) for x in rr.fatos(g, False).items()] == f_gerado
        assert [list(x) for x in rr.fatos(o, True).items()] == f_oficial


def test_verificacao_aponta_o_que_nao_esta_no_texto_oficial():
    avisos = rr.conferir_gerado(*AMOSTRAS[2], False)
    assert avisos[0].startswith("Gerado sem nenhum trecho conferido")
    assert any("4,5%" in a and "12 (doze) meses" in a for a in avisos)
    assert not any("31 de janeiro de 2027" in a or "81.000" in a for a in avisos)       # estes estão no texto oficial
    assert any("[VERIFICAR]" in a for a in rr.conferir_gerado(*AMOSTRAS[0], True))


def test_configuracao_volta_ao_padrao_quando_o_valor_e_estranho():
    class B:
        def __init__(self, v): self.v = v
        def config(self, chave): assert chave == "rascunhos"; return self.v
    assert rr.configuracao(B(None)) == rr.CONFIG_PADRAO
    assert rr.configuracao(B({"ligado": "sim", "nota_minima": 50, "por_dia": True, "dias": 0, "formato": "poema"})) == dict(
        rr.CONFIG_PADRAO, nota_minima=10, dias=1)
    assert rr.configuracao(B({"ligado": False, "por_dia": 5, "formato": "flash"}))["ligado"] is False
    assert rr.configuracao(B([1, 2])) == rr.CONFIG_PADRAO


# ---------------------------------------------------------------- v0.16.0: o mesmo detector de cópia em três lugares
_CBS = "O contribuinte deverá destacar a CBS no documento fiscal à alíquota de nove décimos por cento em todas as operações realizadas"
_RFB = ["Receita Federal do Brasil", "Receita Federal"]
_ITC_A = "Na nossa avaliação a mudança exige atenção redobrada dos departamentos fiscais que ainda não revisaram os cadastros de produtos."
_B = "O contribuinte deverá destacar a CBS no documento fiscal em todas as operações realizadas a partir do mês de janeiro."
_PORTAL_C = "Os escritórios de contabilidade relatam muita dúvida dos clientes sobre como ajustar os sistemas emissores de notas a tempo."
_LZ = ("O programa Litígio Zero, que permite a negociação de débitos inscritos em dívida ativa com descontos sobre multas e juros para "
       "empresas de todos os portes, foi prorrogado até o fim de dezembro.")
_S = ["A empresa que aderir ao parcelamento especial poderá quitar o saldo devedor em até sessenta prestações mensais e sucessivas corrigidas.",
      "O pedido de adesão será feito exclusivamente pelo portal eletrônico, mediante a apresentação dos documentos que comprovem a regularidade.",
      "A falta de pagamento de três parcelas seguidas implicará a exclusão imediata do programa e a cobrança integral do valor remanescente."]
_IN = "Instrução Normativa RFB nº 2.229, de 15 de outubro de 2024"
_B27 = "O contribuinte deverá destacar a CBS no documento fiscal em todas as operações realizadas no território nacional"
_rfb = lambda t: {"texto": t, "nome": "Receita Federal do Brasil", "nomes": _RFB}
_min = lambda t: t[0].lower() + t[1:]
CASOS_COPIA = [
    ("A norma dispõe sobre a apuração da Contribuição Social sobre Bens e Serviços (CBS) no período de transição. "
     "Art. 2º O contribuinte deverá destacar a CBS no documento fiscal à alíquota de 0,9%.",
     ["Art. 1º Esta Instrução Normativa dispõe sobre a apuração da Contribuição Social sobre Bens e Serviços (CBS) no período de "
      "transição. Art. 2º O contribuinte deverá destacar a CBS no documento fiscal à alíquota de 0,9% (nove décimos por cento)."]),
    ('Segundo a Receita, “o contribuinte deverá destacar a CBS no documento fiscal à alíquota de 0,9%” desde já.',
     ["O contribuinte deverá destacar a CBS no documento fiscal à alíquota de 0,9% a partir de 2027 em todas as operações."]),
    ("O CONTRIBUINTE DEVERÁ DESTACAR A CBS NO DOCUMENTO FISCAL À ALÍQUOTA DE NOVE DÉCIMOS POR CENTO EM TODAS AS OPERAÇÕES",
     ["o contribuinte deverá destacar a CBS no documento fiscal à alíquota de nove décimos por cento em todas as operações"]),
    ("## Prazo\nAs empresas optantes pelo regime​ precisam entregar a declaração mensal até o último dia útil do mês seguinte ao da apuração.",
     ["As empresas optantes pelo regime precisam entregar a declaração mensal até o último dia útil do mês seguinte ao da apuração."]),
    ("Texto totalmente próprio, sem nada igual.", ["Outro texto qualquer da fonte oficial com várias palavras diferentes."]),
    ("", []),
] + [
    # v0.18.0: o trecho igual pode ficar quando o parágrafo cita a fonte pelo nome; o do boletim pago, nunca
    ("Segundo a Receita Federal, o contribuinte deverá destacar a CBS no documento fiscal à alíquota de nove décimos por cento "
     "em todas as operações realizadas.", [{"texto": f"{_CBS} no país.", "nome": "Receita Federal do Brasil", "nomes": _RFB}]),
    ("A Receita Federal publicou a norma.\n\nO contribuinte deverá destacar a CBS no documento fiscal à alíquota de nove décimos "
     "por cento em todas as operações realizadas.", [{"texto": f"{_CBS} no país.", "nome": "Receita Federal do Brasil", "nomes": _RFB}]),
    ("Conforme o Portal Contábil SC, as regras são:\n\n- o contribuinte deverá destacar a CBS no documento fiscal à alíquota de "
     "nove décimos por cento em todas as operações realizadas;\n- vale para todos.",
     [{"texto": f"{_CBS} no país.", "nome": "Portal Contábil SC", "nomes": ["Portal Contábil SC"]}]),
    ("## Segundo a Receita Federal\nO contribuinte deverá destacar a CBS no documento fiscal à alíquota de nove décimos por cento "
     "em todas as operações realizadas.", [{"texto": f"{_CBS} no país.", "nome": "Receita Federal do Brasil", "nomes": _RFB}]),
    ("Segundo a ITC, o contribuinte deverá destacar a CBS no documento fiscal à alíquota de nove décimos por cento em todas as "
     "operações realizadas.", [{"texto": f"{_CBS} no país.", "nome": "ITC Consultoria", "nomes": ["ITC Consultoria", "ITC"], "paga": True}]),
    ("Segundo a Receita Federal, o contribuinte deverá destacar a CBS no documento fiscal à alíquota de nove décimos por cento "
     "em todas as operações realizadas.", [{"texto": f"{_CBS} no país.", "nome": "ITC Consultoria", "nomes": ["ITC"], "paga": True},
                                           {"texto": f"{_CBS} desde já.", "nome": "Receita Federal do Brasil", "nomes": _RFB}]),
    ("Segundo a “Receita Federal”, o contribuinte deverá destacar a CBS no documento fiscal à alíquota de nove décimos por cento "
     "em todas as operações realizadas.", ["texto simples sem nomes: " + _CBS]),
    # da varredura da v0.18.0: frase só do boletim pago colada à frase oficial; frase só do portal colada à da Receita (citando só a Receita)
    ("Segundo a Receita Federal do Brasil, " + _min(_ITC_A) + " " + _B,
     [{"texto": _ITC_A + " " + _B, "nome": "ITC Consultoria", "nomes": ["ITC Consultoria"], "paga": True}, _rfb(_B)]),
    ("Segundo a Receita Federal do Brasil, " + _min(_PORTAL_C) + " " + _B,
     [{"texto": _PORTAL_C + " " + _B, "nome": "Portal Contábil SC", "nomes": ["Portal Contábil SC"]}, _rfb(_B)]),
    # aspas coladas em pontuação não atrapalham; cada parágrafo precisa da sua citação; a repetição vale pelo próprio parágrafo
    ("Segundo a Receita Federal do Brasil, " + _min(_LZ).replace("Litígio Zero,", "“Litígio Zero”,"), [_rfb(_LZ)]),
    ("Segundo a Receita Federal, " + _min(_S[0]) + "\n\n" + _S[1] + "\n\n" + _S[2], [_rfb(" ".join(_S))]),
    ("Segundo a Receita Federal, " + _min(_B) + "\n\nPor isso: " + _min(_B), [_rfb(_B)]),
    # o parágrafo logo depois da lista não herda a citação da frase que apresenta a lista
    ("Segundo a Receita Federal, as regras são:\n- prazo maior para todos;\n" + _B, [_rfb(_B)]),
    # segunda varredura: frase do boletim pago entre aspas; nome de norma comum com o oficial no meio da prosa do boletim
    ("Segundo a ITC Consultoria, “" + _ITC_A + "”", [{"texto": _ITC_A, "nome": "ITC Consultoria", "nomes": ["ITC"], "paga": True}]),
    ("Segundo a Receita Federal do Brasil, a mudança exige atenção redobrada dos departamentos fiscais, nos termos da " + _IN +
     ", que obriga quem não revisou os cadastros de produtos a agir.",
     [_rfb("Fica instituída a obrigação prevista na " + _IN + ", para as pessoas jurídicas."),
      {"texto": "Na nossa avaliação, a mudança exige atenção redobrada dos departamentos fiscais, nos termos da " + _IN +
                ", que obriga quem não revisou os cadastros de produtos a agir logo.", "nome": "ITC Consultoria", "nomes": ["ITC"], "paga": True}]),
    # data no fim do parágrafo anterior e subtítulo colados ao trecho citado não atrapalham
    ("A regra começa em 2027.\n\n" + _B27 + ", segundo a Receita Federal.", [_rfb("Em 2027, " + _min(_B27) + ".")]),
    ("## Prazo\nSegundo a Receita Federal, " + _min(_B27) + ".", [_rfb("Prazo. " + _B27 + ".")]),
    # frase do portal colada à da Receita, citando só a Receita: o nome que falta citar é o do portal
    ("Segundo a Receita Federal do Brasil, " + _B + " " + _PORTAL_C,
     [_rfb(_B), {"texto": _B + " " + _PORTAL_C, "nome": "Portal Contábil SC", "nomes": ["Portal Contábil SC"]}]),
]
NOMES_FONTE = [("Receita Federal — Notícias", "Receita Federal do Brasil"), ("PGFN — Notícias", "Procuradoria-Geral da Fazenda Nacional (PGFN)"),
               ("SEF/SC — Últimas legislações", "Secretaria de Estado da Fazenda de Santa Catarina"), ("Portal Contábil SC", "Portal Contábil SC"),
               ("", ""), (None, "Comitê Gestor do IBS"), ("DOU – Destaques", "Imprensa Nacional"),
               ("Receita Federal — Atos normativos (Normas)", "Receita Federal do Brasil (RFB)"),
               ("Simples Nacional — Notícias", "Comitê Gestor do Simples Nacional"), ("Diário Oficial da União — Destaques", "Imprensa Nacional")]


def _extrair(fonte: str, inicio: str, fim: str) -> str:
    i = fonte.index(inicio)
    return fonte[i:fonte.index(fim, i) + len(fim)]


def test_detector_de_copia_do_robo_e_igual_ao_da_tela_e_da_funcao(tmp_path):
    if shutil.which("deno") is None:
        pytest.skip("deno não instalado")
    raiz = RAIZ
    fim = "return achados.sort((a, b) => b.palavras - a.palavras);\n}"
    tela = _extrair((raiz / "index.html").read_text(encoding="utf-8"), "const COPIA_MINIMA = 12", fim)
    funcao = _extrair((raiz / "supabase/functions/radar-ia/index.ts").read_text(encoding="utf-8"), "const COPIA_MINIMA = 12", fim)
    (tmp_path / "casos.json").write_text(json.dumps({"copias": CASOS_COPIA, "nomes": NOMES_FONTE}, ensure_ascii=False), encoding="utf-8")
    esperado = {"copias": [rr.trechos_copiados(c, f) for c, f in CASOS_COPIA], "nomes": [rr.nomes_da_fonte(n, o) for n, o in NOMES_FONTE]}
    copias = esperado["copias"]
    assert copias[0] and copias[1] == [] and copias[2] and copias[3] and copias[4] == []      # os casos testam algo
    assert [(x[0]["citado"], x[0]["paga"], x[0]["fonte"]) for x in copias[6:13]] == [
        (True, False, "Receita Federal do Brasil"), (False, False, "Receita Federal do Brasil"), (True, False, "Portal Contábil SC"),
        (False, False, "Receita Federal do Brasil"), (False, True, "ITC Consultoria"), (True, False, "Receita Federal do Brasil"), (False, False, "")]
    assert esperado["nomes"][:3] == [["receita federal do brasil", "receita federal"], ["pgfn", "procuradoria geral da fazenda nacional"],
                                     ["secretaria de estado da fazenda de santa catarina", "sef sc"]]
    assert esperado["nomes"][-3] == ["rfb", "receita federal do brasil", "receita federal"]     # "(Normas)" não é sigla: não vira nome
    assert esperado["nomes"][-2:] == [["comite gestor do simples nacional"], ["imprensa nacional", "diario oficial da uniao"]]
    novos = copias[13:]
    assert [(len(x), [(t["citado"], t["paga"]) for t in x]) for x in novos] == [
        (1, [(False, True)]), (1, [(False, False)]), (1, [(True, False)]), (1, [(False, False)]),
        (2, [(True, False), (False, False)]), (1, [(False, False)]),
        (1, [(False, True)]), (1, [(False, True)]), (1, [(True, False)]), (1, [(True, False)]), (1, [(False, False)])]
    assert [x[0]["fonte"] for x in copias[13:15]] == ["ITC Consultoria", "Portal Contábil SC"]          # o nome de quem falta citar
    assert copias[-1][0]["fonte"] == "Portal Contábil SC"
    for nome, codigo in (("tela.ts", tela), ("funcao.ts", funcao)):
        arq = tmp_path / nome
        arq.write_text("// @ts-nocheck\n" + codigo + f"\nconst casos = JSON.parse(Deno.readTextFileSync({json.dumps(str(tmp_path / 'casos.json'))}));\n"
                       "console.log(JSON.stringify({copias: casos.copias.map(([c, f]) => trechosCopiados(c, f)), "
                       "nomes: casos.nomes.map(([n, o]) => nomesDaFonte(n, o))}));\n", encoding="utf-8")
        saida = subprocess.run(["deno", "run", "--allow-read", "--no-prompt", str(arq)], capture_output=True, text=True, timeout=60)
        assert saida.returncode == 0, saida.stderr
        assert json.loads(saida.stdout) == esperado, nome


DUVIDAS_SIM = ["(a fonte não especifica o ano)", "(a fonte não informou o ano)", "(o boletim não informa o ano)", "(ano não informado pela fonte)",
               "A fonte cita tanto ADI 5.161 quanto ADI nº 5.161/DF.", "a fonte indica 30/9 mas não especifica o ano", "o texto oficial não especifica o ano"]
DUVIDAS_NAO = ["Para o material de uso e consumo, a LC 87/96 não traz direito ao crédito antes de 2033.",
               "Quando a fonte não informa o CPF do beneficiário na EFD-Reinf, o rendimento fica sem vínculo.",
               "Se a fonte não confirma o valor retido, o beneficiário não pode compensar.",
               "O material de construção aplicado na obra não traz crédito de PIS/Cofins.",
               "A fonte pagadora não informa o valor retido.", "O imposto retido na fonte não informa nada.",
               "Segundo a fonte, o prazo vai até 31/10.", "[VERIFICAR: a fonte não especifica o ano]"]


def test_comentario_de_duvida_igual_no_robo_na_tela_e_na_funcao(tmp_path):
    assert all(rr.comentarios_duvida(t) for t in DUVIDAS_SIM)
    assert not any(rr.comentarios_duvida(t) for t in DUVIDAS_NAO)
    if shutil.which("deno") is None:
        pytest.skip("deno não instalado")
    casos = DUVIDAS_SIM + DUVIDAS_NAO
    esperado = [rr.comentarios_duvida(t) for t in casos]
    (tmp_path / "duvidas.json").write_text(json.dumps(casos, ensure_ascii=False), encoding="utf-8")
    fim = "slice(0, 160));"
    for nome, arquivo in (("tela.ts", "index.html"), ("funcao.ts", "supabase/functions/radar-ia/index.ts")):
        codigo = _extrair((RAIZ / arquivo).read_text(encoding="utf-8"), "const RE_DUVIDA", fim)
        arq = tmp_path / nome
        arq.write_text("// @ts-nocheck\n" + codigo + f"\nconsole.log(JSON.stringify(JSON.parse(Deno.readTextFileSync({json.dumps(str(tmp_path / 'duvidas.json'))}))"
                       ".map((t) => comentariosDuvida(t))));\n", encoding="utf-8")
        saida = subprocess.run(["deno", "run", "--allow-read", "--no-prompt", str(arq)], capture_output=True, text=True, timeout=60)
        assert saida.returncode == 0, saida.stderr
        assert json.loads(saida.stdout) == esperado, nome


def test_fontes_das_capturas_marca_o_boletim_pago_e_poe_a_oficial_antes():
    """v0.18.0: o robô reconhece o boletim pago pelo slug e manda à IA os nomes pelos quais a fonte pode ser citada."""
    grupo = [{"texto": "texto do boletim", "radar_fontes": {"slug": "itc-email", "nome": "ITC Consultoria — boletim por e-mail", "orgao": "ITC Consultoria"}},
             {"texto": None, "radar_fontes": {"slug": "rfb-noticias", "nome": "Receita Federal — Notícias", "orgao": "Receita Federal do Brasil"}},
             {"texto": "texto oficial", "radar_fontes": {"slug": "rfb-normas", "nome": "Receita Federal — Atos normativos (Normas)",
                                                          "orgao": "Receita Federal do Brasil", "oficial": True}}]
    fontes = rr.fontes_das_capturas(grupo)
    assert [(f["nome"], f["paga"]) for f in fontes] == [("Receita Federal do Brasil", False), ("ITC Consultoria", True)]
    assert fontes[0]["nomes"] == ["receita federal do brasil", "receita federal"]
