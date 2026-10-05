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
