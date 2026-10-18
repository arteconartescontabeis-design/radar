"""v0.22.0 — corretor de vídeo, a transcrição pelo robô (robo/video/transcrever.py; ajustes do dono, item 1): o F0 pelo Speech SDK
(reconhecimento contínuo, pt-BR, saída detalhada com o tempo de cada palavra, palavrão sem máscara, lista de frases), a espera pela
vaga única do F0 (até ~10 min, depois "transcrição ocupada") e pela cota, as falhas de rede e de chave, o modo rápido (fast
transcription REST, só com AZURE_FALA_MODO=rapido) e a chave, que nunca aparece em saída, log ou exceção.

A Azure é SIMULADA: um módulo falso no lugar do SDK, um servidor HTTP local no lugar da REST e, quando o SDK de verdade está instalado
(pip install --require-hashes --no-deps -r robo/video/requirements.txt, como o CI faz), o próprio SDK falando com um servidor local do
protocolo de fala (ws://127.0.0.1, sem rede). Os WAV são gerados aqui (não precisa do ffmpeg). Nomes fictícios.
"""
from __future__ import annotations

import email.parser
import email.policy
import importlib
import inspect
import json
import os
import re
import subprocess
import sys
import threading
import traceback
from types import SimpleNamespace

import pytest

from conftest import RAIZ

ROBO = RAIZ / "robo" / "video"
sys.path.insert(0, str(ROBO))

import radar_video_fala_falsa as falsa  # noqa: E402
from radar_video_fala_falsa import QUEBRADO, SEM_FALA, frase_sdk  # noqa: E402

import alinhar  # noqa: E402
import segredo  # noqa: E402
import transcrever  # noqa: E402
from segredo import ErroVideo  # noqa: E402

CHAVE = "ChaveFalsaDaAzure0123456789abcdefXYZ"     # 36 letras e algarismos: tem a forma de uma chave, não é uma
GLOSSARIO = ["eSocial", "DCTFWeb", "IBS", "CBS", "Simples Nacional", "MEI", "CNPJ", "DAS", "DARF", "FGTS", "Cofins", "PIS", "PGDAS-D"]
VARIANTES = {"eSocial": ["e social", "é social"], "DCTFWeb": ["dctf web"], "IBS": ["ips", "ibis"]}
ROTEIRO = "Bom dia! Eu sou a Ana Teste, da Artecon. O eSocial muda dia 30/10: confira com o Bruno Exemplo."
LEXICO = "bom dia eu sou a ana teste da artecon o e social muda dia trinta de outubro confira com o bruno exemplo".split()
# os detalhes de cancelamento como o SDK 1.52.0 os escreve (medidos com o SDK de verdade contra um servidor local)
D429 = "WebSocket upgrade failed: Too many requests (429). Please check subscription information and region name. SessionId: 25d2"
D401 = "WebSocket upgrade failed: Authentication error (401). Please check subscription information and region name. SessionId: fdf9"
D403 = "WebSocket upgrade failed: Authentication error (403). Please check subscription information and region name. SessionId: 2e81"
DREDE = ("Connection failed (no connection to the remote host). Internal error: 1. Error details: Failed with error: "
         "WS_OPEN_ERROR_UNDERLYING_IO_OPEN_FAILED\nwss://brazilsouth.stt.speech.microsoft.com/speech/recognition/conversation/"
         "cognitiveservices/v1?format=detailed&language=pt-BR")


def _tempos(palavras: list[str], ini: float = 0.40, passo: float = 0.30) -> list[tuple]:
    return [(p, round(ini + k * passo, 2), round(ini + k * passo + 0.24, 2), 0.9) for k, p in enumerate(palavras)]


PALAVRAS = _tempos(LEXICO)
FRASES = [("Bom dia! Eu sou a Ana Teste, da Artecon.", PALAVRAS[:9]),
          ("O eSocial muda dia 30 de outubro: confira com o Bruno Exemplo.", PALAVRAS[9:])]


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch):
    monkeypatch.setenv("AZURE_FALA_CHAVE", CHAVE)
    monkeypatch.setenv("AZURE_FALA_REGIAO", "brazilsouth")
    for k in ("AZURE_FALA_MODO", "AZURE_FALA_ENDPOINT"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture()
def relogio(monkeypatch):
    """O relógio da espera: _dormir não dorme, só anda o relógio e anota (e chama `ao_dormir`, se houver)."""
    r = SimpleNamespace(t=1000.0, esperas=[], ao_dormir=None)

    def dormir(s):
        r.esperas.append(s)
        r.t += s
        if r.ao_dormir:
            r.ao_dormir()

    monkeypatch.setattr(transcrever, "_dormir", dormir)
    monkeypatch.setattr(transcrever, "_relogio", lambda: r.t)
    return r


@pytest.fixture()
def fala(tmp_path):
    return falsa.wav(tmp_path / "fala16k.wav", 12.0)


def _sdk(monkeypatch, passos):
    m = falsa.sdk_falso(passos)
    monkeypatch.setitem(sys.modules, "azure.cognitiveservices.speech", m)
    return m


def _erro(funcao) -> ErroVideo:
    with pytest.raises(ErroVideo) as e:
        funcao()
    return e.value


# ------------------------------------------------------------------ F0: Speech SDK
def test_f0_reconhecimento_continuo_com_o_tempo_de_cada_palavra(monkeypatch, fala, relogio, capfd):
    """O F0: pt-BR, saída detalhada, tempo por palavra, palavrão sem máscara, a lista de frases; os tempos (100 ns) viram segundos na
    linha do WAV; frase sem fala, resultado quebrado e palavra fora do áudio ficam de fora; o resultado alinha com o roteiro."""
    estranha = json.dumps({"RecognitionStatus": "Success", "Offset": 130_000_000, "Duration": 5_000_000, "DisplayText": "Fora.",
                           "NBest": [{"Confidence": 0.5, "Words": [{"Word": "fora", "Offset": 150_000_000, "Duration": 5_000_000},
                                                                    {"Word": "", "Offset": 0, "Duration": 1},
                                                                    {"Word": "neg", "Offset": -5, "Duration": 1}]}]})
    m = _sdk(monkeypatch, [("ok", [frase_sdk(*FRASES[0]), SEM_FALA, "{não é json", frase_sdk(*FRASES[1]),
                                   frase_sdk("Silêncio", [], status="InitialSilenceTimeout"), estranha])])
    r = transcrever.transcrever(fala, GLOSSARIO, ROTEIRO)
    assert len(m.feitos) == 1
    cfg = m.feitos[0]["config"]
    assert (cfg.subscription_key, cfg.region, cfg.speech_recognition_language) == (CHAVE, "brazilsouth", "pt-BR")
    assert cfg.output_format == m.OutputFormat.Detailed and cfg.tempos_por_palavra and cfg.palavrao == m.ProfanityOption.Raw
    assert m.feitos[0]["audio"].filename == str(fala)
    assert m.feitos[0]["frases"] == [*GLOSSARIO, "Ana Teste", "Artecon", "Bruno Exemplo"]
    assert r["palavras"] == [{"texto": p, "inicio": a, "fim": b, "confianca": c} for p, a, b, c in PALAVRAS]
    assert r["frases"] == [{"display": FRASES[0][0], "inicio": 0.4, "fim": PALAVRAS[8][2]},
                           {"display": FRASES[1][0], "inicio": PALAVRAS[9][1], "fim": PALAVRAS[-1][2]}]
    assert r["transcricao"] == {"servico": "azure_f0", "segundos_audio": 12.0, "palavras": len(LEXICO)}
    assert relogio.esperas == [] and capfd.readouterr() == ("", "")
    # sem a confiança da palavra, vale a da frase
    _sdk(monkeypatch, [("ok", [json.dumps({"RecognitionStatus": "Success", "Offset": 4_000_000, "Duration": 3_000_000,
                                           "DisplayText": "Bom.", "NBest": [{"Confidence": 0.77, "Words": [
                                               {"Word": "bom", "Offset": 4_000_000, "Duration": 3_000_000}]}]})])])
    assert transcrever.transcrever(fala)["palavras"] == [{"texto": "bom", "inicio": 0.4, "fim": 0.7, "confianca": 0.77}]
    # a forma léxica (números por extenso, "e social") casa com o roteiro: nenhuma divergência e a legenda na grafia do roteiro
    al = alinhar.alinhar(alinhar.extrair_fala(ROTEIRO)[0], r["palavras"], r["frases"],
                         {"glossario": GLOSSARIO + ["Artecon"], "variantes": VARIANTES})
    assert al["divergencias"] == [] and al["texto_final"] == ROTEIRO and al["avisos"] == []


def test_f0_ocupado_espera_e_tenta_de_novo(monkeypatch, fala, relogio, capfd):
    """O F0 atende 1 pedido por vez (dividido com o WhatsApp da Agenda): o 429 espera, cada vez mais, e tenta de novo."""
    m = _sdk(monkeypatch, [("erro", "TooManyRequests", D429), ("erro", "TooManyRequests", D429), ("ok", [frase_sdk(*FRASES[0])])])
    r = transcrever.transcrever(fala, GLOSSARIO, ROTEIRO)
    assert len(r["palavras"]) == 9 and len(m.feitos) == 3
    assert 5 <= relogio.esperas[0] <= 7 and 10 <= relogio.esperas[1] <= 12
    linhas = capfd.readouterr().out.splitlines()
    assert [re.sub(r"espera=[\d.]+", "espera=X", l) for l in linhas] == [
        "corretor: transcrever rapido=não motivo=ocupada tentativa=1 espera=X",
        "corretor: transcrever rapido=não motivo=ocupada tentativa=2 espera=X"]


def test_f0_ocupado_por_mais_de_10_minutos_da_erro_claro(monkeypatch, fala, relogio, capfd):
    m = _sdk(monkeypatch, [("erro", "TooManyRequests", D429)] * 200)
    e = _erro(lambda: transcrever.transcrever(fala))
    assert (e.codigo, e.etapa) == ("transcricao_ocupada", "transcrever")
    assert 600 - 62 < sum(relogio.esperas) <= transcrever.ESPERA_MAX                  # usou os ~10 min, sem passar
    assert max(relogio.esperas) <= transcrever.ESPERA_TETO + 2 and len(m.feitos) == len(relogio.esperas) + 1
    assert len(capfd.readouterr().out.splitlines()) == len(relogio.esperas)


def test_f0_cota_espera_e_depois_da_erro_de_cota(monkeypatch, fala, relogio):
    """Forbidden ("the free subscription … ran out of quota") e o 403 na abertura: espera e tenta, como o limite; no fim, azure_cota."""
    _sdk(monkeypatch, [("erro", "AuthenticationFailure", D403), ("ok", [frase_sdk(*FRASES[1])])])
    assert len(transcrever.transcrever(fala)["palavras"]) == len(LEXICO) - 9 and len(relogio.esperas) == 1
    relogio.esperas.clear()
    _sdk(monkeypatch, [("erro", "Forbidden", "Quota exceeded.")] * 200)
    assert _erro(lambda: transcrever.transcrever(fala)).codigo == "azure_cota"
    assert 600 - 62 < sum(relogio.esperas) <= 600


def test_f0_chave_recusada_e_pedido_invalido_nao_tentam_de_novo(monkeypatch, fala, relogio):
    for passo, codigo in ((("erro", "AuthenticationFailure", D401), "azure_chave"), (("erro", "BadRequest", "Bad request (400)"), "azure_erro"),
                          (("erro", "RuntimeError", "x"), "azure_erro"), (("excecao", "falhou"), "azure_erro"),
                          (("ok", [frase_sdk(*FRASES[0]), QUEBRADO]), "azure_erro")):
        m = _sdk(monkeypatch, [passo, ("ok", [frase_sdk(*FRASES[0])])])
        assert _erro(lambda: transcrever.transcrever(fala)).codigo == codigo, passo
        assert len(m.feitos) == 1 and relogio.esperas == [], passo


def test_f0_falha_de_rede_tenta_3_vezes(monkeypatch, tmp_path, fala, relogio):
    m = _sdk(monkeypatch, [("erro", "ConnectionFailure", DREDE), ("erro", "ServiceUnavailable", "Service unavailable (503)"),
                           ("ok", [frase_sdk(*FRASES[0])])])
    assert len(transcrever.transcrever(fala)["palavras"]) == 9 and relogio.esperas == [5.0, 15.0] and len(m.feitos) == 3
    relogio.esperas.clear()
    m = _sdk(monkeypatch, [("erro", "ServiceTimeout", "t"), ("erro", "ServiceError", "s"), ("erro", "ConnectionFailure", DREDE),
                           ("ok", [])])
    assert _erro(lambda: transcrever.transcrever(fala)).codigo == "azure_fora" and relogio.esperas == [5.0, 15.0] and len(m.feitos) == 3
    # o SDK que nunca termina: o tempo-limite de cada tentativa (TEMPO_BASE + 3 × a duração) conta como falha de rede
    monkeypatch.setattr(transcrever, "TEMPO_BASE", 0.2)
    curta = falsa.wav(tmp_path / "curta.wav", 0.05)
    relogio.esperas.clear()
    m = _sdk(monkeypatch, [("trava",)] * 3)
    assert _erro(lambda: transcrever.transcrever(curta)).codigo == "azure_fora" and len(m.feitos) == 3
    assert all(f["config"] is not None for f in m.feitos)


def test_configuracao_audio_e_cota_do_radar_conferidos_antes_de_chamar(monkeypatch, tmp_path, fala, relogio):
    m = _sdk(monkeypatch, [("ok", [frase_sdk(*FRASES[0])])] * 5)
    casos = [("AZURE_FALA_CHAVE", None, "azure_sem_chave"), ("AZURE_FALA_CHAVE", "curta123", "azure_sem_chave"),
             ("AZURE_FALA_CHAVE", CHAVE + "\r\nX-Outro: 1", "azure_sem_chave"), ("AZURE_FALA_REGIAO", None, "azure_config"),
             ("AZURE_FALA_REGIAO", "brazil south", "azure_config"), ("AZURE_FALA_MODO", "turbo", "azure_config")]
    for var, valor, codigo in casos:
        with monkeypatch.context() as mp:
            mp.delenv(var) if valor is None else mp.setenv(var, valor)
            assert _erro(lambda: transcrever.transcrever(fala)).codigo == codigo, (var, valor)
    ruins = [falsa.wav(tmp_path / "estereo.wav", 1.0, canais=2), falsa.wav(tmp_path / "48k.wav", 1.0, taxa=48000),
             falsa.wav(tmp_path / "8bits.wav", 1.0, largura=1), falsa.wav(tmp_path / "longo.wav", 971.0),   # v0.33.0: o teto subiu para 970 s
             falsa.wav(tmp_path / "vazio.wav", 0.0), tmp_path / "nao_existe.wav"]
    (tmp_path / "nao_e_wav.wav").write_bytes(b"ftypisom" * 100)
    for w in [*ruins, tmp_path / "nao_e_wav.wav"]:
        assert _erro(lambda: transcrever.transcrever(w)).codigo == "audio_invalido", w.name
    assert _erro(lambda: transcrever.transcrever(fala, restante_s=11.9)).codigo == "cota_radar"      # a cota do Radar no mês
    assert m.feitos == []                                                                             # nada chegou à Azure
    assert transcrever.transcrever(fala, restante_s=12.0)["transcricao"]["segundos_audio"] == 12.0
    for valor in ("", "f0", " F0 "):
        monkeypatch.setenv("AZURE_FALA_MODO", valor)
        assert transcrever.modo() == "f0"
    monkeypatch.delenv("AZURE_FALA_MODO")
    monkeypatch.setitem(sys.modules, "azure.cognitiveservices.speech", None)                        # SDK não instalado
    assert _erro(lambda: transcrever.transcrever(fala)).codigo == "azure_sem_sdk"


def test_lista_de_frases_tem_glossario_nomes_e_siglas():
    assert transcrever.lista_de_frases(GLOSSARIO, ROTEIRO) == [*GLOSSARIO, "Ana Teste", "Artecon", "Bruno Exemplo"]
    rot = ("Hoje: o DCTFWeb e a PGDAS-D. Bruno Exemplo explica o IBS, a CBS e o Simples Nacional em 2027 — R$ 50 mil. "
           "Com a Ana Teste e {\\b1}X | Y.")
    assert transcrever.lista_de_frases((), rot) == ["DCTFWeb", "PGDAS-D", "Bruno Exemplo", "IBS", "CBS", "Simples Nacional", "Ana Teste"]
    # o que abre a frase só entra com maiúscula no meio ou abrindo um nome ("Hoje", "Com", "O IBS" não); algarismos e marcação nunca
    assert transcrever.lista_de_frases((), "O IBS sobe. Bom dia. Ana. Fala Bruno Exemplo!") == ["IBS", "Bruno Exemplo"]
    muitos = transcrever.lista_de_frases([f"Termo{k}" for k in range(400)] + ["termo1", "x" * 60, 5, "A"])
    assert len(muitos) == transcrever.LISTA_MAX and muitos[:2] == ["Termo0", "Termo1"]


def test_palavras_json_ida_e_volta(monkeypatch, fala):
    _sdk(monkeypatch, [("ok", [frase_sdk(*FRASES[0]), frase_sdk(*FRASES[1])])])
    r = transcrever.transcrever(fala)
    assert transcrever.de_json(transcrever.para_json(r)) == r
    for ruim in (b"", b"[]", b"{\"versao\": 2}", json.dumps({"versao": 1, "palavras": {}, "frases": [], "transcricao": {}}).encode(),
                 b"x" * (transcrever.JSON_MAX + 1)):
        assert _erro(lambda: transcrever.de_json(ruim)).codigo == "palavras_invalidas"
    lixo = json.dumps({"versao": 1, "transcricao": {"servico": "outro", "segundos_audio": 2},
                       "palavras": [{"texto": "a", "inicio": 0.1, "fim": 0.2}, {"texto": "b", "inicio": 9, "fim": 9.5},
                                    {"texto": 5, "inicio": 0.3, "fim": 0.4}, "x"], "frases": [{"display": "A.", "inicio": 0, "fim": 0.2}]})
    assert transcrever.de_json(lixo.encode()) == {"palavras": [{"texto": "a", "inicio": 0.1, "fim": 0.2, "confianca": None}],
                                                  "frases": [{"display": "A.", "inicio": 0.0, "fim": 0.2}],
                                                  "transcricao": {"servico": None, "segundos_audio": 2.0, "palavras": 1}}


def test_passo_do_workflow_le_o_pedido_e_grava_palavras_ou_o_codigo(monkeypatch, tmp_path, relogio, capfd):
    """O passo "Transcrever" do workflow (só com AZURE_FALA_* no ambiente): fala16k.wav e pedido_fala.json → palavras.json, ou
    transcricao_erro.txt com o código fixo; no log, só números e o código."""
    for alvo, nome in ((sys, "excepthook"), (sys, "unraisablehook"), (threading, "excepthook")):
        monkeypatch.setattr(alvo, nome, getattr(alvo, nome))                 # main() instala os do robô; o teste devolve os do pytest
    pasta = tmp_path / "trabalho"
    pasta.mkdir()
    falsa.wav(pasta / "fala16k.wav", 12.0)
    pedido = {"pedido": "00000000-0000-0000-0000-000000000004", "glossario": GLOSSARIO, "fala_roteiro": ROTEIRO, "restante_s": 600}
    (pasta / "pedido_fala.json").write_text(json.dumps(pedido), encoding="utf-8")
    (pasta / "transcricao_erro.txt").write_text("azure_fora", encoding="utf-8")       # de uma tentativa anterior: sai
    m = _sdk(monkeypatch, [("ok", [frase_sdk(*FRASES[0]), frase_sdk(*FRASES[1])])])
    assert transcrever.main([str(pasta)]) == 0 and not (pasta / "transcricao_erro.txt").exists()
    r = transcrever.de_json((pasta / "palavras.json").read_bytes())
    assert len(r["palavras"]) == len(LEXICO) and r["transcricao"]["servico"] == "azure_f0"
    assert m.feitos[0]["frases"] == [*GLOSSARIO, "Ana Teste", "Artecon", "Bruno Exemplo"]
    assert capfd.readouterr() == (f"corretor: transcrever palavras={len(LEXICO)} segundos=12.00 rapido=não\n", "")
    (pasta / "palavras.json").unlink()
    for passos, restante, codigo in (([("erro", "AuthenticationFailure", D401)], 600, "azure_chave"), ([], 11.0, "cota_radar")):
        _sdk(monkeypatch, passos)
        (pasta / "pedido_fala.json").write_text(json.dumps({**pedido, "restante_s": restante}), encoding="utf-8")
        assert transcrever.main([str(pasta)]) == 1 and not (pasta / "palavras.json").exists()
        assert (pasta / "transcricao_erro.txt").read_text(encoding="utf-8") == codigo
        assert capfd.readouterr() == (f"corretor: transcrever erro={codigo}\n", "")
    assert transcrever.main([str(tmp_path / "nao_existe")]) == 2 and transcrever.main([]) == 2
    for ruim in ("", "[]", json.dumps({**pedido, "glossario": "eSocial"}), json.dumps({**pedido, "restante_s": "600"}),
                 json.dumps({k: v for k, v in pedido.items() if k != "fala_roteiro"})):
        (pasta / "pedido_fala.json").write_text(ruim, encoding="utf-8")
        assert transcrever.main([str(pasta)]) == 1 and (pasta / "transcricao_erro.txt").read_text(encoding="utf-8") == "pedido_invalido"
    (pasta / "pedido_fala.json").unlink()
    assert transcrever.main([str(pasta)]) == 1 and (pasta / "transcricao_erro.txt").read_text(encoding="utf-8") == "pedido_invalido"
    capfd.readouterr()
    # o arquivo rodado direto com python -I, num ambiente só com a Azure (região inválida: para antes de qualquer chamada)
    (pasta / "pedido_fala.json").write_text(json.dumps(pedido), encoding="utf-8")
    r = subprocess.run([sys.executable, "-I", str(ROBO / "transcrever.py"), str(pasta)], capture_output=True, text=True,
                       env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "AZURE_FALA_CHAVE": CHAVE, "AZURE_FALA_REGIAO": "brazil south"})
    assert (r.returncode, r.stdout, r.stderr) == (1, "corretor: transcrever erro=azure_config\n", "")
    assert (pasta / "transcricao_erro.txt").read_text(encoding="utf-8") == "azure_config"


# ------------------------------------------------------------------ rápido: fast transcription (REST simulada)
def _rapido(monkeypatch, respostas):
    srv = falsa.ServidorRapido(respostas)
    monkeypatch.setenv("AZURE_FALA_MODO", "rapido")
    monkeypatch.setenv("AZURE_FALA_ENDPOINT", srv.url)
    monkeypatch.setattr(transcrever, "_ENDPOINT", re.compile(r"^http://127\.0\.0\.1:\d+$"))  # só o teste aponta para o local
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(k, "http://127.0.0.1:9")    # um proxy morto: o REST não pode usar o proxy do ambiente
    for k in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(k, raising=False)
    return srv


def _resposta_rapida() -> bytes:
    def ph(display, ws):
        return {"channel": 0, "offsetMilliseconds": int(ws[0][1] * 1000), "durationMilliseconds": int((ws[-1][2] - ws[0][1]) * 1000),
                "text": display, "locale": "pt-BR", "confidence": 0.93,
                "words": [{"text": t, "offsetMilliseconds": int(round(a * 1000)), "durationMilliseconds": int(round((b - a) * 1000))}
                          for t, a, b, _ in ws]}
    exib = _tempos("Bom dia! Eu sou a Ana Teste, da Artecon.".split())
    return json.dumps({"durationMilliseconds": 12000, "combinedPhrases": [{"text": "…"}],
                       "phrases": [ph("Bom dia! Eu sou a Ana Teste, da Artecon.", exib), {**ph("x", exib), "channel": 1}]}).encode()


def test_rapido_fast_transcription_rest(monkeypatch, fala, relogio, capfd):
    srv = _rapido(monkeypatch, [(429, {"Retry-After": "7"}, b'{"error":"' + CHAVE.encode() + b'"}'), (200, {}, _resposta_rapida())])
    try:
        r = transcrever.transcrever(fala, GLOSSARIO, ROTEIRO)
    finally:
        srv.fechar()
    assert relogio.esperas == [7.0] and len(srv.pedidos) == 2
    caminho, cab, corpo = srv.pedidos[1]
    assert caminho == "/speechtotext/transcriptions:transcribe?api-version=2025-10-15"
    assert cab["Ocp-Apim-Subscription-Key"] == CHAVE and CHAVE not in caminho
    msg = email.parser.BytesParser(policy=email.policy.default).parsebytes(
        b"Content-Type: " + cab["Content-Type"].encode() + b"\r\n\r\n" + corpo)
    partes = {p.get_param("name", header="content-disposition"): p for p in msg.iter_parts()}
    assert partes["audio"].get_content() == fala.read_bytes() and partes["audio"].get_content_type() == "audio/wav"
    assert json.loads(partes["definition"].get_content()) == {
        "locales": ["pt-BR"], "profanityFilterMode": "None",
        "phraseList": {"phrases": [*GLOSSARIO, "Ana Teste", "Artecon", "Bruno Exemplo"]}}
    exib = _tempos("Bom dia! Eu sou a Ana Teste, da Artecon.".split())
    assert r["palavras"] == [{"texto": t, "inicio": a, "fim": b, "confianca": 0.93} for t, a, b, _ in exib]   # o canal 1 fica fora
    assert r["frases"] == [{"display": "Bom dia! Eu sou a Ana Teste, da Artecon.", "inicio": 0.4, "fim": exib[-1][2]}]
    assert r["transcricao"] == {"servico": "azure_rapido", "segundos_audio": 12.0, "palavras": 9}
    assert capfd.readouterr().out == "corretor: transcrever rapido=sim motivo=ocupada tentativa=1 espera=7.00\n"
    # a forma de exibição também alinha com o roteiro
    al = alinhar.alinhar("Bom dia! Eu sou a Ana Teste, da Artecon.", r["palavras"], r["frases"], {"glossario": GLOSSARIO})
    assert al["divergencias"] == [] and al["texto_final"] == "Bom dia! Eu sou a Ana Teste, da Artecon."


def test_rapido_recusas_falhas_e_redirecionamento(monkeypatch, fala, relogio):
    casos = [([(401, {}, b"")], "azure_chave", []), ([(400, {}, b"")], "azure_erro", []),
             ([(500, {}, CHAVE.encode())] * 3, "azure_fora", [5.0, 15.0]), ([(200, {}, b"<html>")], "azure_erro", []),
             ([(200, {}, b'{"phrases": {}}')], "azure_erro", []), ([(200, {}, b"[" * 2000)], "azure_erro", [])]
    monkeypatch.setattr(transcrever, "RESPOSTA_MAX", 1000)
    for respostas, codigo, esperas in casos:
        relogio.esperas.clear()
        srv = _rapido(monkeypatch, respostas)
        try:
            assert _erro(lambda: transcrever.transcrever(fala)).codigo == codigo, respostas[0][:2]
        finally:
            srv.fechar()
        assert relogio.esperas == esperas, respostas[0][:2]
    # o 403 (cota ou recurso parado) espera como o limite
    relogio.esperas.clear()
    srv = _rapido(monkeypatch, [(403, {}, b""), (200, {}, b'{"phrases": []}')])
    try:
        assert transcrever.transcrever(fala)["palavras"] == [] and len(relogio.esperas) == 1
    finally:
        srv.fechar()
    # redirecionamento: a chave nunca vai para o outro endereço
    for status in (301, 302, 307, 308):
        outro = falsa.ServidorRapido([(200, {}, _resposta_rapida())])
        srv = _rapido(monkeypatch, [(status, {"Location": outro.url + "/roubar"}, b"")])
        try:
            assert _erro(lambda: transcrever.transcrever(fala)).codigo == "azure_erro", status
        finally:
            srv.fechar()
            outro.fechar()
        assert outro.pedidos == [], status
    # sem servidor (conexão recusada): falha de rede, 3 tentativas
    relogio.esperas.clear()
    srv = _rapido(monkeypatch, [])
    srv.fechar()
    assert _erro(lambda: transcrever.transcrever(fala)).codigo == "azure_fora" and relogio.esperas == [5.0, 15.0]


def test_rapido_endereco_so_da_azure(monkeypatch):
    monkeypatch.setenv("AZURE_FALA_MODO", "rapido")
    for base, ok in (("https://artecon-radar-fala.cognitiveservices.azure.com/", "https://artecon-radar-fala.cognitiveservices.azure.com"),
                     ("https://brazilsouth.api.cognitive.microsoft.com", "https://brazilsouth.api.cognitive.microsoft.com"),
                     ("http://artecon-radar-fala.cognitiveservices.azure.com", None), ("https://exemplo.com", None),
                     ("https://x.cognitiveservices.azure.com.exemplo.com", None), ("https://x.cognitiveservices.azure.com/../a", None)):
        monkeypatch.setenv("AZURE_FALA_ENDPOINT", base)
        if ok:
            assert transcrever._endpoint() == ok
        else:
            assert _erro(transcrever._endpoint).codigo == "azure_config", base
    monkeypatch.delenv("AZURE_FALA_ENDPOINT")                                  # sem o endereço, o da região
    assert transcrever._endpoint() == "https://brazilsouth.api.cognitive.microsoft.com"


# ------------------------------------------------------------------ a chave nunca aparece
def _sem_chave(e: BaseException, saida: tuple[str, str]) -> None:
    textos = [str(e), repr(e), "".join(traceback.format_exception(e)), repr(e.args), *saida]
    for t in textos:
        assert CHAVE not in t and CHAVE[:12] not in t, t[:200]
    assert e.__cause__ is None and e.__context__ is None                    # nada encadeado (a exceção original teria a chave)


def test_chave_nunca_aparece_em_saida_log_ou_excecao(monkeypatch, tmp_path, fala, relogio, capfd, caplog):
    com_chave = f"WebSocket upgrade failed (401) wss://brazilsouth.stt.speech.microsoft.com/x?key={CHAVE} Ocp-Apim-Subscription-Key: {CHAVE}"
    cenarios = [[("erro", "AuthenticationFailure", com_chave)], [("excecao", f"falhou com a chave {CHAVE}")],
                [("erro", "TooManyRequests", com_chave)] * 200, [("erro", "ConnectionFailure", com_chave)] * 3,
                [("erro", "BadRequest", com_chave)]]
    for passos in cenarios:
        _sdk(monkeypatch, passos)
        e = _erro(lambda: transcrever.transcrever(fala))
        _sem_chave(e, capfd.readouterr())
    for respostas in ([(401, {}, CHAVE.encode())], [(500, {"X-Chave": CHAVE}, CHAVE.encode())] * 3, [(302, {"Location": "/" + CHAVE}, b"")]):
        srv = _rapido(monkeypatch, respostas)
        try:
            e = _erro(lambda: transcrever.transcrever(fala))
        finally:
            srv.fechar()
        _sem_chave(e, capfd.readouterr())
    monkeypatch.delenv("AZURE_FALA_MODO")
    monkeypatch.setitem(sys.modules, "azure.cognitiveservices.speech", None)
    _sem_chave(_erro(lambda: transcrever.transcrever(fala)), capfd.readouterr())
    assert CHAVE not in caplog.text
    # o resultado (que vai para palavras.json e o relatório) não leva a chave; a última barreira do log também a tira
    _sdk(monkeypatch, [("ok", [frase_sdk(*FRASES[0])])])
    assert CHAVE.encode() not in transcrever.para_json(transcrever.transcrever(fala))
    for texto in (f"Ocp-Apim-Subscription-Key: {CHAVE}", f"Authorization: Bearer {CHAVE}", f"erro {CHAVE} no pedido",
                  "authorization=Bearer abcdefghijklmnop", "bearer abcdefghijklmnop", "Ocp-Apim-Subscription-Key: abcdefghijklmnop",
                  "ocp-apim-subscription-key=abcdefghijklmnop"):
        limpo = segredo.sem_segredo(texto)
        assert CHAVE not in limpo and "abcdefghijklmnop" not in limpo, limpo
    segredo.log("transcrever", rapido=False, chave=CHAVE, motivo=com_chave)
    assert capfd.readouterr().out == "corretor: transcrever rapido=não chave=? motivo=?\n"


def test_excecao_ignorada_e_de_outra_linha_sem_mensagem():
    """O SDK chama o robô das linhas dele: a exceção de outra thread, e a "ignorada" que o Python imprime sozinho (num __del__ ou numa
    chamada de volta do ctypes), também saem só com a etapa e o nome do tipo."""
    prog = ("import sys, threading; sys.path.insert(0, %r); import segredo; segredo.instalar_excepthook(); "
            "segredo.etapa('transcrever', '00000000-0000-0000-0000-000000000003')\n"
            "class X:\n    def __del__(self): raise ValueError('Ana Teste %s')\n"
            "x = X(); del x\n"
            "t = threading.Thread(target=lambda: (_ for _ in ()).throw(KeyError('Bruno Exemplo %s'))); t.start(); t.join()\n") % (
        str(ROBO), CHAVE, CHAVE)
    r = subprocess.run([sys.executable, "-I", "-c", prog], capture_output=True, text=True, env={**os.environ, "AZURE_FALA_CHAVE": CHAVE})
    linha = "corretor: erro inesperado na etapa transcrever do pedido 00000000-0000-0000-0000-000000000003 ({})\n"
    assert r.stdout == "" and r.stderr == linha.format("ValueError") + linha.format("KeyError"), r.stderr


# ------------------------------------------------------------------ o SDK de verdade, contra um servidor local (sem rede)
def _sdk_de_verdade():
    try:
        return importlib.import_module("azure.cognitiveservices.speech")
    except Exception:                                   # noqa: BLE001 — não instalado, ou sem a biblioteca nativa
        return None


SDK = _sdk_de_verdade()
COM_SDK = pytest.mark.skipif(SDK is None, reason="Speech SDK não instalado (pip install --require-hashes --no-deps -r "
                                                 "robo/video/requirements.txt; o CI instala)")


@COM_SDK
def test_falso_tem_os_mesmos_nomes_do_sdk_de_verdade():
    f = falsa.sdk_falso([])
    for nome in ("SpeechConfig", "SpeechRecognizer", "PhraseListGrammar", "ResultReason", "CancellationReason",
                 "CancellationErrorCode", "OutputFormat", "ProfanityOption", "EventSignal", "CancellationDetails"):
        real, falso = getattr(SDK, nome), getattr(f, nome)
        if isinstance(falso, type) and issubclass(falso, __import__("enum").Enum):
            assert set(falso.__members__) <= set(real.__members__), nome
            assert all(real[k].value == falso[k].value for k in falso.__members__), nome
        else:
            publicos = {k for k in vars(falso) if not k.startswith("_")}
            assert publicos <= set(dir(real)), (nome, publicos - set(dir(real)))
    assert set(inspect.signature(f.SpeechConfig).parameters) <= set(inspect.signature(SDK.SpeechConfig).parameters)
    assert set(inspect.signature(f.audio.AudioConfig).parameters) <= set(inspect.signature(SDK.audio.AudioConfig).parameters)
    assert {"recognized", "canceled", "session_started", "session_stopped"} <= set(dir(SDK.SpeechRecognizer))
    assert {"cancellation_details", "result"} <= set(dir(SDK.SpeechRecognitionCanceledEventArgs))
    assert {"reason", "code", "error_details"} <= set(dir(SDK.CancellationDetails))
    assert {"reason", "json"} <= set(dir(SDK.SpeechRecognitionResult))
    assert {"subscription_key", "region", "speech_recognition_language", "output_format"} <= set(dir(SDK.SpeechConfig))


@COM_SDK
def test_sdk_de_verdade_com_o_protocolo_de_fala_local(monkeypatch, fala, relogio, capfd):
    """O SDK de verdade (o mesmo do runner) contra um servidor local do protocolo de fala: a 1ª tentativa é recusada com 429 (o SDK
    insiste algumas vezes e cancela com TooManyRequests), o robô espera e tenta de novo, e a 2ª reconhece. Confere o pedido (pt-BR,
    detalhado, tempo e confiança por palavra, palavrão sem máscara, a lista de frases), a chave só no cabeçalho, e nada impresso."""
    srv = falsa.ServidorFala(FRASES, recusar="429 Too Many Requests")
    real, regioes = SDK.SpeechConfig, []

    def config(subscription=None, region=None, **kw):
        regioes.append(region)
        return real(subscription=subscription, host=f"ws://127.0.0.1:{srv.porta}")      # o endereço local no lugar da região

    monkeypatch.setattr(SDK, "SpeechConfig", config)
    relogio.ao_dormir = lambda: setattr(srv, "recusar", None)                         # depois da 1ª espera, a vaga abre
    try:
        r = transcrever.transcrever(fala, GLOSSARIO, ROTEIRO)
    finally:
        srv.fechar()
    assert regioes == ["brazilsouth", "brazilsouth"] and srv.recusadas >= 1 and len(relogio.esperas) == 1
    assert r["palavras"] == [{"texto": p, "inicio": a, "fim": b, "confianca": c} for p, a, b, c in PALAVRAS]
    assert [f["display"] for f in r["frases"]] == [FRASES[0][0], FRASES[1][0]]
    abertura = srv.aberturas[-1]
    pedido = abertura.splitlines()[0]
    for p in ("language=pt-BR", "format=detailed", "profanity=raw", "wordLevelTimestamps=true", "wordLevelConfidence=true"):
        assert p in pedido, pedido
    assert f"Ocp-Apim-Subscription-Key: {CHAVE}" in abertura and CHAVE not in pedido
    ctx = srv.contextos[-1]
    assert [i["Text"] for g in ctx["dgi"]["Groups"] for i in g["Items"]] == [*GLOSSARIO, "Ana Teste", "Artecon", "Bruno Exemplo"]
    assert ctx["phraseOutput"]["format"] == "Detailed" and ctx["phraseDetection"]["enrichment"]["profanity"] == "raw"
    out, err = capfd.readouterr()
    assert re.fullmatch(r"corretor: transcrever rapido=não motivo=ocupada tentativa=1 espera=[\d.]+\n", out) and err == ""


@COM_SDK
def test_sdk_de_verdade_chave_recusada(monkeypatch, fala, relogio, capfd):
    srv = falsa.ServidorFala(FRASES, recusar="401 Unauthorized")
    real = SDK.SpeechConfig
    monkeypatch.setattr(SDK, "SpeechConfig", lambda subscription=None, region=None: real(subscription=subscription,
                                                                                         host=f"ws://127.0.0.1:{srv.porta}"))
    try:
        e = _erro(lambda: transcrever.transcrever(fala))
    finally:
        srv.fechar()
    assert e.codigo == "azure_chave" and relogio.esperas == [] and srv.recusadas == 1
    _sem_chave(e, capfd.readouterr())


# ------------------------------------------------------------------ estático
def test_codigo_da_transcricao_sem_registro_de_audio_nem_log_do_sdk():
    codigo = (ROBO / "transcrever.py").read_text(encoding="utf-8")
    assert "ProfanityOption.Raw" in codigo and "request_word_level_timestamps()" in codigo and "OutputFormat.Detailed" in codigo
    assert not re.search(r"audio_logging|EnableAudioLogging|LogFilename|diagnostics|FileLogger|MemoryLogger|EventLogger|set_proxy"
                         r"|\bimport logging\b|print\(|subprocess|raise_for_status|getLogger", codigo)
    # a chave só sai do ambiente, na hora; nunca numa constante do módulo
    assert codigo.count('os.environ.get("AZURE_FALA_CHAVE")') == 1 and not re.search(r"^[A-Z_]+ = .*AZURE_FALA_CHAVE", codigo, re.M)
    # nenhum raise dentro de um except (a exceção original, com a mensagem, ficaria encadeada)
    for bloco in re.findall(r"\n(\s+)except[^\n]*:\n((?:\1\s+[^\n]*\n)+)", codigo):
        assert "raise" not in bloco[1], bloco[1]
    req = (ROBO / "requirements.txt").read_text(encoding="utf-8")
    for pacote in ("azure-cognitiveservices-speech==1.52.0", "azure-core==1.41.0", "typing-extensions==4.16.0"):
        assert re.search(rf"^{re.escape(pacote)} \\\n    --hash=sha256:[0-9a-f]{{64}}", req, re.M), pacote
    assert "requests" not in re.sub(r"(?m)^#.*$", "", req)
