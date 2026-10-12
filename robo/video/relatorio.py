"""Radar Artecon — corretor de vídeo (v0.22.0): o relatório (radar_videos.relatorio, versão 2; desenho 4.4).

  * parcial(): logo depois do alinhamento e do plano de cortes, antes da montagem, com `parcial: true` — as divergências, o falado
    fora do roteiro, o que do roteiro não foi dito e os avisos: a equipe sabe se precisa regravar sem esperar o vídeo;
  * final(): tudo, depois da montagem e da conferência — entrada, saída (com o volume e o pico medidos na conferência), cortes e
    sugestões, trocas de grafia, divergências, legenda (com a lista dos blocos para o editor do administrador), avisos, texto final,
    áudio, conferência, quadros e a transcrição (o serviço e os segundos de áudio: a cota do F0 é de 5 h por mês, dividida com a
    Agenda — sem nomes);
  * os tempos (em_s) são os do VÍDEO CORRIGIDO (cortes.remapear), como a tela mostra, e `clipe` é o número da parte enviada;
  * situacao(): "regravar" se sobrou divergência que o administrador não marcou "a transcrição errou"; senão "pronto";
  * caber(): o relatório cabe em radar_videos.relatorio (check length(relatorio::text) <= 60000): as listas longas são resumidas,
    com o aviso `relatorio_resumido` (as divergências ficam sempre);
  * resumo_log(): só contagens e códigos, para o log do GitHub.
O relatório tem a fala e o roteiro: vai só para o banco (RLS de admin e editor), nunca para o log.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone

import cortes
import sondar
from sondar import FPS

ROBO = "0.22.0"
VERSAO = 2
LIMITE = 55000                         # folga sobre os 60000 (o jsonb::text do Postgres separa com ", " e ": ", como o json.dumps)
LISTAS = ("fora_do_roteiro", "omitido", "trocas", "sugestoes", "cortes")
SERVICO = re.compile(r"^[a-z0-9_]{3,40}$")


def _agora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _em(plano: dict, t: float) -> float:
    return round(cortes.remapear(plano, float(t))[0], 2)


def _clipe(infos: list[dict], t: float) -> int | None:
    q = float(t) * FPS
    for i in infos:
        if i["inicio_q"] <= q < i["inicio_q"] + i["quadros"]:
            return i["n"]
    return infos[-1]["n"] if infos else None


def _num(v, casas: int = 1) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, casas) if math.isfinite(x) else None


def _transcricao(t: dict | None) -> dict:
    """{servico, segundos_audio, palavras}: o código do serviço (azure_f0, azure_rapido) e quanto áudio foi transcrito."""
    t = t if isinstance(t, dict) else {}
    servico = t.get("servico")
    return {"servico": servico if isinstance(servico, str) and SERVICO.match(servico) else None,
            "segundos_audio": _num(t.get("segundos_audio")), "palavras": int(_num(t.get("palavras"), 0) or 0)}


def _no_video(al: dict, plano: dict, infos: list[dict]) -> dict:
    """As listas do alinhamento com os tempos do vídeo corrigido (em_s) e o clipe."""
    conv = lambda x: {**{k: v for k, v in x.items() if k != "t"}, "em_s": _em(plano, x["t"]), "clipe": _clipe(infos, x["t"])}
    return {k: [conv(x) for x in al.get(k) or []] for k in ("trocas", "divergencias", "fora_do_roteiro", "omitido")}


def parcial(al: dict, plano: dict, infos: list[dict], transcricao: dict | None = None, modo: str = "completo") -> dict:
    """O relatório parcial (radar_video_parcial), antes da montagem."""
    rel = {"versao": VERSAO, "robo": ROBO, "modo": modo, "parcial": True, "gerado_em": _agora(),
           **{k: v for k, v in _no_video(al, plano, infos).items() if k != "trocas"},
           "avisos": sorted(set(al.get("avisos") or [])), "transcricao": _transcricao(transcricao)}
    return caber(rel)


def final(al: dict, plano: dict, infos: list[dict], montagem: dict, conferencia: dict, legenda_info: dict,
          transcricao: dict | None = None, modo: str = "completo", cfg: dict | None = None) -> dict:
    """O relatório final (radar_video_concluir). montagem: montar.montar; conferencia: conferir.conferir; legenda_info:
    legenda.gravar (com a lista dos blocos)."""
    cfg = cfg or {}
    saida = dict(montagem.get("saida") or {})
    for k in ("lufs", "pico_dbtp"):                      # medidos na conferência, sobre o arquivo final
        if conferencia.get(k) is not None:
            saida[k] = conferencia[k]
    leg = legenda_info or {}
    avisos = set(al.get("avisos") or []) | set(leg.get("avisos") or [])
    if (saida.get("duracao_s") or 0) > float(cfg.get("duracao_max_s", 45)):
        avisos.add("duracao_acima_do_limite")
    listas = _no_video(al, plano, infos)
    rel = {"versao": VERSAO, "robo": ROBO, "modo": modo, "parcial": False, "gerado_em": _agora(),
           "entrada": sondar.resumo(infos), "saida": saida, "cortes": plano.get("cortes") or [],
           "sugestoes": plano.get("sugestoes") or [], **listas,
           "legenda": {"blocos": leg.get("blocos", 0), "estilo": leg.get("estilo", "normal"), "gancho": bool(leg.get("gancho")),
                       **(al.get("legenda_ajustes") or {"editados": 0, "recusados": []}), "lista": leg.get("lista") or []},
           "avisos": sorted(avisos), "texto_final": al.get("texto_final") or "", "cobertura": al.get("cobertura"),
           "audio": montagem.get("audio") or {}, "imagem": montagem.get("imagem") or {}, "conferencia": conferencia,
           "quadros_ms": montagem.get("quadros_ms") or [], "transcricao": _transcricao(transcricao)}
    return caber(rel)


def situacao(rel: dict) -> str:
    """"regravar" se há divergência (número, prazo ou termo) que o administrador não marcou "a transcrição errou"."""
    return "regravar" if any(d.get("regravar") and not d.get("transcricao_errou") for d in rel.get("divergencias") or []) else "pronto"


def _tam(rel: dict) -> int:
    return len(json.dumps(rel, ensure_ascii=False))


def _resumir(rel: dict, passo: int) -> None:
    if passo < 3:                                       # as listas longas: 100, 20 e 5 itens
        for k in LISTAS:
            if isinstance(rel.get(k), list):
                rel[k] = rel[k][:(100, 20, 5)[passo]]
    elif passo == 3 and isinstance(rel.get("legenda"), dict):
        rel["legenda"].pop("lista", None)
    elif passo == 4:                                    # as divergências ficam (são o que pede a regravação), com texto curto
        rel["divergencias"] = [{**d, "falado": str(d.get("falado") or "")[:40], "roteiro": str(d.get("roteiro") or "")[:40]}
                               for d in (rel.get("divergencias") or [])[:50]]
    elif passo == 5:
        rel["texto_final"] = str(rel.get("texto_final") or "")[:20000]


def caber(rel: dict) -> dict:
    """O relatório em tipos do JSON e dentro do limite da coluna: corta as listas longas, depois a lista dos blocos da legenda, os
    textos das divergências e, por último, o texto final; o aviso relatorio_resumido diz que algo ficou de fora."""
    rel = json.loads(json.dumps(rel, ensure_ascii=False, default=str))
    passo = 0
    while _tam(rel) > LIMITE and passo < 6:
        _resumir(rel, passo)
        rel["avisos"] = sorted(set(rel.get("avisos") or []) | {"relatorio_resumido"})
        passo += 1
    return rel


def resumo_log(rel: dict) -> dict:
    """Só números e sim/não, para segredo.log (nunca a fala, o roteiro ou um nome)."""
    ds = rel.get("divergencias") or []
    return {"cortes": len(rel.get("cortes") or []), "sugestoes": len(rel.get("sugestoes") or []), "divergencias": len(ds),
            "regravar": situacao(rel) == "regravar", "fora": len(rel.get("fora_do_roteiro") or []),
            "omitido": len(rel.get("omitido") or []), "blocos": int((rel.get("legenda") or {}).get("blocos") or 0),
            "duracao": float((rel.get("saida") or {}).get("duracao_s") or 0.0), "cobertura": float(rel.get("cobertura") or 0.0)}
