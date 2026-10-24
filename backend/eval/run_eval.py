"""Retrieval evaluation harness.

Ingests the documents in eval/corpus into a fresh collection via the real HTTP API,
then runs every question in golden_set.json against three retrieval configurations -
vector-only, keyword-only, and hybrid+RRF - reporting recall@5, MRR, and mean
retrieval latency for each. No LLM call is involved, so this needs no GROQ_API_KEY.

Usage (from backend/):
    python eval/run_eval.py

Environment:
    EVAL_API_URL   Base URL of a running backend (default http://localhost:8000)
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

import httpx

API_URL = os.environ.get("EVAL_API_URL", "http://localhost:8000")
EVAL_DIR = Path(__file__).resolve().parent
CORPUS_DIR = EVAL_DIR / "corpus"
GOLDEN_SET_PATH = EVAL_DIR / "golden_set.json"
RESULTS_PATH = EVAL_DIR / "results.json"

MODES = ["vector", "keyword", "hybrid"]
TOP_K = 5
JOB_POLL_TIMEOUT_SECONDS = 60


def setup_account(client: httpx.Client) -> tuple[str, str]:
    """Signs up a fresh eval user and mints an API key. Returns (jwt, api_key)."""
    email = f"eval-{uuid.uuid4().hex[:10]}@example.com"
    password = "eval-harness-password"

    signup = client.post(f"{API_URL}/auth/signup", json={"email": email, "password": password})
    signup.raise_for_status()
    token = signup.json()["access_token"]

    key_resp = client.post(
        f"{API_URL}/keys", json={"name": "eval-harness"}, headers={"Authorization": f"Bearer {token}"}
    )
    key_resp.raise_for_status()
    return token, key_resp.json()["full_key"]


def create_collection(client: httpx.Client, api_key: str) -> str:
    resp = client.post(
        f"{API_URL}/collections",
        json={"name": f"eval-{uuid.uuid4().hex[:8]}"},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    resp.raise_for_status()
    return resp.json()["id"]


def upload_and_wait(client: httpx.Client, api_key: str, collection_id: str, path: Path) -> None:
    headers = {"Authorization": f"Bearer {api_key}"}
    with path.open("rb") as f:
        resp = client.post(
            f"{API_URL}/collections/{collection_id}/documents",
            files={"file": (path.name, f, "text/markdown")},
            headers=headers,
        )
    resp.raise_for_status()
    job_id = resp.json()["job_id"]

    deadline = time.monotonic() + JOB_POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        job = client.get(f"{API_URL}/jobs/{job_id}", headers=headers)
        job.raise_for_status()
        status = job.json()["status"]
        if status == "SUCCEEDED":
            return
        if status == "FAILED":
            raise RuntimeError(f"Ingestion failed for {path.name}: {job.json().get('error_message')}")
        time.sleep(0.5)
    raise TimeoutError(f"Ingestion for {path.name} did not finish within {JOB_POLL_TIMEOUT_SECONDS}s")


def search(client: httpx.Client, api_key: str, collection_id: str, query: str, mode: str) -> tuple[List[Dict[str, Any]], float]:
    """Runs one search, transparently honoring `Retry-After` on 429 like any
    well-behaved API client should - the eval harness makes far more requests per
    minute than a real caller would, so it is expected to occasionally hit the
    per-key rate limit and back off rather than treating that as a failure.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    for _attempt in range(10):
        start = time.perf_counter()
        resp = client.get(
            f"{API_URL}/collections/{collection_id}/search",
            params={"q": query, "top_k": TOP_K, "mode": mode},
            headers=headers,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "2"))
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        return resp.json()["results"], elapsed_ms
    raise RuntimeError(f"Gave up after repeated 429s for query: {query!r}")


def evaluate_mode(
    client: httpx.Client, api_key: str, collection_id: str, golden_set: List[Dict[str, str]], mode: str
) -> Dict[str, float]:
    hits = 0
    reciprocal_ranks: List[float] = []
    latencies: List[float] = []

    for item in golden_set:
        results, latency_ms = search(client, api_key, collection_id, item["question"], mode)
        latencies.append(latency_ms)

        rank = 0
        for i, r in enumerate(results, start=1):
            if item["expected_keyword"].lower() in r["content"].lower():
                rank = i
                break

        if rank > 0:
            hits += 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)

    n = len(golden_set)
    return {
        "recall_at_5": hits / n,
        "mrr": sum(reciprocal_ranks) / n,
        "mean_latency_ms": sum(latencies) / n,
    }


def main() -> None:
    golden_set = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    corpus_files = sorted(CORPUS_DIR.glob("*.md"))
    if not corpus_files:
        raise SystemExit(f"No corpus files found in {CORPUS_DIR}")

    print(f"API: {API_URL}")
    print(f"Corpus: {[p.name for p in corpus_files]}")
    print(f"Golden set: {len(golden_set)} questions\n")

    with httpx.Client(timeout=90.0) as client:
        health = client.get(f"{API_URL}/health")
        health.raise_for_status()
        print(f"Health: {health.json()}\n")

        _jwt, api_key = setup_account(client)
        collection_id = create_collection(client, api_key)
        print(f"Created eval collection: {collection_id}")

        for path in corpus_files:
            print(f"Ingesting {path.name}...")
            upload_and_wait(client, api_key, collection_id, path)
        print("Ingestion complete.\n")

        results: Dict[str, Dict[str, float]] = {}
        for mode in MODES:
            print(f"Evaluating mode={mode}...")
            results[mode] = evaluate_mode(client, api_key, collection_id, golden_set, mode)

    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\n" + format_table(results))
    print(f"\nRaw results written to {RESULTS_PATH}")


def format_table(results: Dict[str, Dict[str, float]]) -> str:
    header = f"{'Config':<14} {'Recall@5':>10} {'MRR':>8} {'Mean Latency (ms)':>20}"
    lines = [header, "-" * len(header)]
    label = {"vector": "vector-only", "keyword": "keyword-only", "hybrid": "hybrid+RRF"}
    for mode in MODES:
        r = results[mode]
        lines.append(
            f"{label[mode]:<14} {r['recall_at_5']:>10.2%} {r['mrr']:>8.3f} {r['mean_latency_ms']:>20.1f}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
