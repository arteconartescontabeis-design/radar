"""Radar Artecon — acesso ao Supabase (PostgREST) com a chave service_role."""
from __future__ import annotations

import requests

from radar_util import VERSAO, agora_iso


class ErroBanco(Exception):
    pass


class Banco:
    def __init__(self, url: str, chave: str, limite: int = 30, prefixo: str = "/rest/v1"):
        if not url or not chave:
            raise ErroBanco("SUPABASE_URL e SUPABASE_SERVICE_KEY são obrigatórios")
        url = url.rstrip("/")
        self.base = url if (prefixo and url.endswith(prefixo)) else url + prefixo
        self.limite = limite
        self.sessao = requests.Session()
        self.sessao.headers.update({
            "apikey": chave,
            "Authorization": f"Bearer {chave}",
            "Content-Type": "application/json",
        })

    def _pedir(self, metodo: str, caminho: str, *, params=None, corpo=None, prefer=None):
        cab = {"Prefer": prefer} if prefer else {}
        try:
            r = self.sessao.request(metodo, f"{self.base}/{caminho}", params=params, json=corpo,
                                    headers=cab, timeout=self.limite)
        except requests.RequestException as e:
            raise ErroBanco(f"{metodo} {caminho}: sem conexão com o banco — {type(e).__name__}: {e}") from e
        if r.status_code >= 300:
            raise ErroBanco(f"{metodo} {caminho}: HTTP {r.status_code} — {r.text[:400]}")
        return r.json() if r.text else None

    # ---------------------------------------------------------------- fontes
    def fontes_ativas(self, slug: str | None = None) -> list[dict]:
        params = {"select": "*", "ativo": "eq.true", "order": "id"}
        if slug:
            params["slug"] = f"eq.{slug}"
        return self._pedir("GET", "radar_fontes", params=params)

    # -------------------------------------------------------------- execuções
    def abrir_execucao(self, fonte_id: int) -> int:
        linhas = self._pedir("POST", "radar_execucoes",
                             corpo={"fonte_id": fonte_id, "versao_robo": VERSAO},
                             prefer="return=representation")
        return linhas[0]["id"]

    def fechar_execucao(self, execucao_id: int, **campos) -> None:
        campos["finalizado_em"] = agora_iso()
        if campos.get("erro"):
            campos["erro"] = str(campos["erro"])[:1000]
        self._pedir("PATCH", "radar_execucoes", params={"id": f"eq.{execucao_id}"}, corpo=campos)

    # --------------------------------------------------------------- capturas
    def capturas_da_fonte(self, fonte_id: int, limite: int = 1000) -> dict[str, dict]:
        linhas = self._pedir("GET", "radar_capturas", params={
            "select": "id,url,hash_conteudo,versao,capturado_em,verificado_em",
            "fonte_id": f"eq.{fonte_id}", "order": "capturado_em.desc", "limit": str(limite)})
        return {linha["url"]: linha for linha in linhas}

    def buscar_duplicata(self, fonte_id: int, hash_titulo: str, hash_conteudo: str | None) -> int | None:
        """Mesma notícia já capturada em OUTRA fonte (mesmo título ou mesmo texto)."""
        filtros = [f"hash_titulo.eq.{hash_titulo}"]
        if hash_conteudo:
            filtros.append(f"hash_conteudo.eq.{hash_conteudo}")
        linhas = self._pedir("GET", "radar_capturas", params={
            "select": "id", "fonte_id": f"neq.{fonte_id}", "duplicata_de": "is.null",
            "or": "(" + ",".join(filtros) + ")", "order": "id", "limit": "1"})
        return linhas[0]["id"] if linhas else None

    def gravar_captura(self, registro: dict) -> dict | None:
        """Insere a captura. Se a mesma (fonte, url) já existir, NÃO mexe nela e devolve None
        (nunca duplica e nunca sobrescreve texto guardado com vazio)."""
        linhas = self._pedir("POST", "radar_capturas", params={"on_conflict": "fonte_id,url"},
                             corpo=registro,
                             prefer="resolution=ignore-duplicates,return=representation")
        return linhas[0] if linhas else None

    def encerrar_execucoes_orfas(self, horas: int = 2) -> int:
        """Execuções que ficaram 'em_andamento' (job cancelado, queda) viram falha registrada."""
        from datetime import datetime, timedelta, timezone
        limite = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
        linhas = self._pedir("PATCH", "radar_execucoes",
                             params={"status": "eq.em_andamento", "iniciado_em": f"lt.{limite}"},
                             corpo={"status": "falha", "finalizado_em": agora_iso(),
                                    "erro": "execução interrompida antes de terminar"},
                             prefer="return=representation")
        return len(linhas or [])

    def atualizar_captura(self, captura_id: int, campos: dict) -> dict:
        linhas = self._pedir("PATCH", "radar_capturas", params={"id": f"eq.{captura_id}"},
                             corpo=campos, prefer="return=representation")
        if not linhas:
            raise ErroBanco(f"captura {captura_id} não encontrada para atualizar")
        return linhas[0]

    def limpar_imagens_sem_uso(self, horas: int = 24) -> int:
        """Apaga as imagens que nenhum conteúdo usa há mais de `horas` (v0.7.1). Devolve quantas."""
        return int(self._pedir("POST", "rpc/radar_limpar_imagens_sem_uso", corpo={"p_horas": horas}) or 0)

    def saude_fontes(self) -> list[dict]:
        """Situação de cada fonte (falhas seguidas, último erro), para os avisos de fonte com falha."""
        return self._pedir("GET", "radar_v_saude_fontes", params={
            "select": "slug,nome,ativo,saude,falhas_consecutivas,ultimo_erro,ultimo_sucesso_em", "order": "id"}) or []

    def links_publicados(self) -> list[dict]:
        """Links registrados em "Publicações no site", para conferir se continuam no ar."""
        return self._pedir("GET", "radar_divulgacoes", params={"select": "id,url,titulo", "order": "id"}) or []
