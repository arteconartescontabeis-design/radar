"""Radar Artecon — aviso de fonte com falha (v0.7.1).

Depois da coleta, abre um aviso (issue) no repositório do GitHub para cada fonte ativa que falhou
3 vezes seguidas. O GitHub manda e-mail ao dono do repositório quando um aviso é aberto, então não
é preciso serviço de e-mail. Um aviso por fonte: enquanto ele estiver aberto, nada novo é criado.
Quando a fonte volta a funcionar (ou é desligada na aba Fontes), o aviso é fechado com um comentário.

Uso (no workflow, depois da coleta):
    python radar_alertas.py
Variáveis: SUPABASE_URL, SUPABASE_SERVICE_KEY, GITHUB_TOKEN e GITHUB_REPOSITORY (o Actions preenche
as duas últimas). Sem elas, não faz nada. Nunca deixa a coleta vermelha: erros só vão para o log.
"""
from __future__ import annotations

import os
import sys

import requests

from radar_banco import Banco, ErroBanco

PREFIXO = "Radar: fonte com falha — "
FALHAS_PARA_AVISAR = 3
API = "https://api.github.com"


def titulo(slug: str) -> str:
    return PREFIXO + slug


def corpo_aviso(f: dict) -> str:
    sucesso = f.get("ultimo_sucesso_em") or "nunca"
    return (f"A fonte **{f.get('nome') or f['slug']}** (`{f['slug']}`) falhou nas últimas "
            f"**{f.get('falhas_consecutivas')}** coletas seguidas.\n\n"
            f"- Último erro: {str(f.get('ultimo_erro') or '—')[:500]}\n"
            f"- Último sucesso: {sucesso}\n\n"
            "O que fazer:\n"
            "1. No Radar, aba **Fontes**: veja a observação da fonte em \"Últimas execuções do robô\".\n"
            "2. GitHub → Actions → \"Radar — diagnóstico das fontes\" → Run workflow: o relatório mostra "
            "como a página está montada hoje.\n"
            "3. Se o site mudou, ajuste em Fontes → Configurar; se a fonte não serve mais, desmarque "
            "\"Fonte ativa\".\n\n"
            "Este aviso fecha sozinho quando a fonte voltar a funcionar ou for desligada.")


def decidir(saude: list[dict], abertos: dict[str, int]) -> tuple[list[dict], list[tuple[int, str]]]:
    """Devolve (fontes para abrir aviso, [(número do aviso, motivo do fechamento)])."""
    abrir, fechar = [], []
    por_slug = {f["slug"]: f for f in saude}
    for f in saude:
        if f.get("ativo") and (f.get("falhas_consecutivas") or 0) >= FALHAS_PARA_AVISAR and titulo(f["slug"]) not in abertos:
            abrir.append(f)
    for t, numero in abertos.items():
        slug = t[len(PREFIXO):]
        f = por_slug.get(slug)
        if f is None:
            fechar.append((numero, "A fonte não existe mais no Radar."))
        elif not f.get("ativo"):
            fechar.append((numero, "A fonte foi desligada na aba Fontes."))
        elif (f.get("falhas_consecutivas") or 0) == 0:
            fechar.append((numero, f"A fonte voltou a funcionar (último sucesso: {f.get('ultimo_sucesso_em')})."))
    return abrir, fechar


class GitHub:
    def __init__(self, repositorio: str, token: str, sessao: requests.Session | None = None):
        self.base = f"{API}/repos/{repositorio}"
        self.sessao = sessao or requests.Session()
        self.sessao.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                    "X-GitHub-Api-Version": "2022-11-28"})

    def _pedir(self, metodo: str, caminho: str, **kw):
        r = self.sessao.request(metodo, self.base + caminho, timeout=30, **kw)
        if r.status_code >= 300:
            raise RuntimeError(f"GitHub {metodo} {caminho}: HTTP {r.status_code} — {r.text[:300]}")
        return r.json() if r.text else None

    def avisos_abertos(self) -> dict[str, int]:
        abertos, pagina = {}, 1
        while True:
            lote = self._pedir("GET", "/issues", params={"state": "open", "per_page": 100, "page": pagina})
            for i in lote:
                if "pull_request" not in i and str(i.get("title", "")).startswith(PREFIXO):
                    abertos[i["title"]] = i["number"]
            if len(lote) < 100:
                return abertos
            pagina += 1

    def abrir(self, f: dict) -> int:
        return self._pedir("POST", "/issues", json={"title": titulo(f["slug"]), "body": corpo_aviso(f)})["number"]

    def fechar(self, numero: int, motivo: str) -> None:
        self._pedir("POST", f"/issues/{numero}/comments", json={"body": motivo})
        self._pedir("PATCH", f"/issues/{numero}", json={"state": "closed", "state_reason": "completed"})


def executar(banco: Banco, github: GitHub) -> list[str]:
    saude = banco.saude_fontes()
    abrir, fechar = decidir(saude, github.avisos_abertos())
    feito = []
    for f in abrir:
        feito.append(f"aviso #{github.abrir(f)} aberto: {f['slug']} ({f.get('falhas_consecutivas')} falhas seguidas)")
    for numero, motivo in fechar:
        github.fechar(numero, motivo)
        feito.append(f"aviso #{numero} fechado: {motivo}")
    return feito


def main() -> int:
    url, chave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (url and chave and token and repo):
        print("Avisos de fonte com falha: sem as variáveis necessárias; nada a fazer.")
        return 0
    try:
        feito = executar(Banco(url, chave), GitHub(repo, token))
    except (ErroBanco, RuntimeError, requests.RequestException) as e:
        print(f"! avisos de fonte com falha não foram atualizados: {e}", file=sys.stderr)
        return 0
    print("Avisos de fonte com falha: " + ("; ".join(feito) if feito else "nada a abrir nem fechar."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
