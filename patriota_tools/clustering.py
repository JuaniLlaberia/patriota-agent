"""Semantic clustering for editorial source items.

Two-phase hybrid approach:
  1. Embeddings phase: text-embedding-3-small → cosine distance matrix → HDBSCAN
  2. LLM validation: HDBSCAN clusters are sent in batches to an editor LLM that
     reorganises or discards items before they become confirmed clusters.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
import openai

logger = logging.getLogger(__name__)

_BATCH_SIZE = 10  # HDBSCAN clusters per LLM validation call

_BATCH_VALIDATION_PROMPT = """\
Sos un editor de noticias argentino. Te doy varios grupos de noticias y tweets \
(CLUSTER_0, CLUSTER_1, etc.) que un algoritmo agrupó por similitud semántica. \
Tu tarea es revisar cada grupo y reorganizarlos en historias noticiosas CONCRETAS.

REGLAS ESTRICTAS:
1. Un cluster es válido SOLO si todos sus ítems cubren el MISMO hecho concreto y reciente.
   "Mismo hecho" = mismo actor + misma acción + mismo momento (no el mismo tema general).
2. Si el grupo mezcla eventos distintos (aunque sean del mismo rubro) → separarlos, un cluster por evento.
3. Si un cluster tiene más de 6 ítems → casi seguro es una bolsa de categoría; dividilo en eventos específicos.
4. Ítems sin relación con ningún evento concreto compartido → descartarlos.
5. El campo "tema" DEBE describir el evento específico (actores + acción + contexto), NUNCA la categoría.

DIFERENCIA CLAVE — evento vs categoría:
  ✅ VÁLIDO — mismo evento: varias fuentes sobre el mismo voto en el Congreso de hoy
  ✅ VÁLIDO — mismo evento: tres fuentes sobre la misma suba del dólar de hoy
  ✅ VÁLIDO — mismo evento: tweets y notas sobre el mismo partido de la selección argentina
  ❌ BOLSA DE CATEGORÍA (dividir): artículo sobre inflación + tweet sobre el FMI + nota sobre el dólar
  ❌ BOLSA DE CATEGORÍA (dividir): cinco ítems sobre "política argentina" de eventos distintos
  ❌ DESCARTAR: ítem de farándula o irrelevante que quedó mezclado

6. Si el cluster trata sobre un hecho extranjero SIN conexión con Argentina (no involucra actores \
argentinos, no afecta la economía/política/sociedad argentina, no es un evento regional \
latinoamericano de primer orden) → descartar todos sus ítems. Deportes y cultura con \
participación argentina SÍ son válidos (selección nacional, clubes en torneos internacionales, \
atletas/artistas argentinos en el exterior).

RELEVANCIA ARGENTINA — ejemplos:
  ✅ INCLUIR: decisiones del BCRA, voto en el Congreso, selección argentina, River/Boca en Copa \
Libertadores, precio de soja/commodities que afectan exportaciones, acuerdo con el FMI, \
conflictos con vecinos
  ❌ DESCARTAR: elecciones internas en España, escándalo corporativo en Alemania, deportes \
extranjeros sin ningún participante argentino, farándula internacional sin conexión argentina

CAMPO "tema" — tiene que ser titular-ready, no etiqueta. Usá el actor real de la historia:
  ✅ BIEN: "El Congreso aprueba el presupuesto con votos de la oposición"
  ✅ BIEN: "El dólar blue sube a $1.350 tras declaraciones del BCRA"
  ✅ BIEN: "La selección argentina golea a Brasil y clasifica al Mundial"
  ❌ MAL: "política", "economía", "crisis en argentina", "noticias del día", "situación actual"

{clusters_block}

Respondé ÚNICAMENTE con JSON válido en este formato (un solo objeto con todos los clusters \
validados y todos los ítems descartados de todos los grupos):
{{
  "clusters": [
    {{
      "ids": ["id1", "id2"],
      "tema": "descripción específica del evento — actores + acción concreta"
    }}
  ],
  "descartar": ["id3", "id4"]
}}"""


class HybridClusterer:
    """Embed → HDBSCAN → batched LLM validation pipeline."""

    def __init__(
        self,
        openai_api_key: str,
        openrouter_api_key: str,
        llm_model: str = "deepseek/deepseek-v4-flash",
    ) -> None:
        self._embed_client = openai.OpenAI(api_key=openai_api_key)
        self._llm_client = openai.OpenAI(
            api_key=openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        self._llm_model = llm_model

    # ── Phase 1: Embeddings ──────────────────────────────────────────────────

    def embed_items(self, items: list[dict[str, Any]]) -> np.ndarray:
        texts = [
            (item.get("title") or "") + " " + (item.get("body") or "")[:300]
            for item in items
        ]
        response = self._embed_client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        vectors = [e.embedding for e in sorted(response.data, key=lambda e: e.index)]
        return np.array(vectors, dtype=np.float32)

    def cluster_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        """Return HDBSCAN cluster labels (-1 = noise)."""
        import hdbscan  # lazy import

        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-10, norms)
        normed = embeddings / norms
        dist = np.clip(1.0 - (normed @ normed.T), 0.0, 2.0).astype(np.float64)

        # "leaf" selects the finest-grained clusters in the condensed tree,
        # preventing large category bags. "eom" (the default) does the opposite:
        # it merges sub-clusters aggressively, producing fewer but broader groups.
        return hdbscan.HDBSCAN(
            min_cluster_size=2,
            metric="precomputed",
            cluster_selection_method="leaf",
        ).fit_predict(dist)

    # ── Phase 2: Batched LLM validation ─────────────────────────────────────

    def _format_item(self, item: dict[str, Any]) -> str:
        raw: dict = {}
        try:
            raw = json.loads(item.get("raw") or "{}")
        except (json.JSONDecodeError, TypeError):
            pass
        engagement = raw.get("likeCount") or raw.get("likes") or ""
        eng_str = f" | engagement: {engagement}" if engagement else ""
        # Tweets have no title — item['body'] is the tweet text and is the only content
        # the validator sees for them. Without it every tweet renders as "(sin título)"
        # with zero information, so the LLM validates them blind.
        texto = (item.get("body") or "")[:280]
        return (
            f"- id: {item['id']}\n"
            f"  titulo: {item.get('title') or '(sin título)'}\n"
            f"  texto: {texto}\n"
            f"  fuente: {item.get('source') or ''}\n"
            f"  url: {item.get('url') or ''}\n"
            f"  fecha: {item.get('published_at') or item.get('ingested_at') or ''}"
            f"{eng_str}"
        )

    def validate_clusters_batch(
        self, cluster_batch: list[list[dict[str, Any]]]
    ) -> dict[str, Any]:
        """Validate a batch of HDBSCAN clusters in a single LLM call.

        Sending N clusters together instead of N individual calls reduces API
        round-trips from O(clusters) to O(clusters / _BATCH_SIZE).
        Returns {"clusters": [...], "descartar": [...]} with IDs drawn from any
        cluster in the batch.
        """
        blocks = []
        for i, cluster_items in enumerate(cluster_batch):
            lines = [f"CLUSTER_{i}:"]
            lines.extend(self._format_item(it) for it in cluster_items)
            blocks.append("\n".join(lines))

        prompt = _BATCH_VALIDATION_PROMPT.format(clusters_block="\n\n".join(blocks))

        for attempt in range(2):
            try:
                resp = self._llm_client.chat.completions.create(
                    model=self._llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=2000,
                    timeout=60,
                )
                content = (resp.choices[0].message.content or "").strip()
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                return json.loads(content.strip())
            except Exception as exc:
                if attempt == 0:
                    logger.warning("LLM batch validation failed (retrying): %s", exc)
                else:
                    logger.error("LLM batch validation failed twice: %s", exc)
                    # Fallback: pass through all clusters with ≥2 items unvalidated
                    fallback: list[dict] = []
                    for cluster_items in cluster_batch:
                        if len(cluster_items) >= 2:
                            fallback.append({
                                "ids": [str(it["id"]) for it in cluster_items],
                                "tema": "cluster sin validar",
                            })
                    return {"clusters": fallback, "descartar": []}
        return {"clusters": [], "descartar": []}

    # ── Full pipeline ────────────────────────────────────────────────────────

    def run(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Run the full hybrid pipeline.

        Returns:
            {
                "validated_clusters": [{"item_ids": [int, ...], "tema": str}],
                "noise_item_ids": [int, ...],
            }
        """
        if not items:
            return {"validated_clusters": [], "noise_item_ids": []}
        if len(items) == 1:
            return {"validated_clusters": [], "noise_item_ids": [items[0]["id"]]}

        embeddings = self.embed_items(items)
        labels = self.cluster_embeddings(embeddings)

        by_label: dict[int, list[dict]] = {}
        for item, label in zip(items, labels):
            by_label.setdefault(int(label), []).append(item)

        noise_ids: list[int] = [it["id"] for it in by_label.pop(-1, [])]
        cluster_list = list(by_label.values())

        # Global ID → item lookup (IDs are unique across all clusters)
        id_to_item: dict[str, dict] = {
            str(it["id"]): it
            for cluster_items in cluster_list
            for it in cluster_items
        }

        validated: list[dict[str, Any]] = []

        # Send clusters in batches of _BATCH_SIZE to reduce LLM API round-trips
        for batch_start in range(0, len(cluster_list), _BATCH_SIZE):
            batch = cluster_list[batch_start : batch_start + _BATCH_SIZE]
            result = self.validate_clusters_batch(batch)

            for cluster in result.get("clusters", []):
                ids = [int(i) for i in cluster["ids"] if i in id_to_item]
                if len(ids) >= 2:
                    validated.append({"item_ids": ids, "tema": cluster.get("tema", "")})
                else:
                    noise_ids.extend(ids)

            for discarded_id in result.get("descartar", []):
                if discarded_id in id_to_item:
                    noise_ids.append(int(discarded_id))

        return {"validated_clusters": validated, "noise_item_ids": noise_ids}
