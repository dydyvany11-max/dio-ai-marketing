import math
from collections import Counter, defaultdict
from typing import Iterable

from src.api.services.trends_engine import _tokenize


def _tfidf_matrix(docs: list[list[str]]) -> list[dict[str, float]]:
    df = Counter()
    for doc in docs:
        for term in set(doc):
            df[term] += 1
    n = len(docs) or 1
    vectors: list[dict[str, float]] = []
    for doc in docs:
        tf = Counter(doc)
        vec = {}
        for term, count in tf.items():
            idf = math.log((n + 1) / (df[term] + 1)) + 1.0
            vec[term] = count * idf
        vectors.append(vec)
    return vectors


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = 0.0
    for k, v in a.items():
        if k in b:
            dot += v * b[k]
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_topics(articles: list[dict], max_topics: int = 10, sim_threshold: float = 0.25) -> list[dict]:
    # Use title+content tokens for topic vectors
    docs = []
    for art in articles:
        text = (art.get("title") or "") + " " + (art.get("content") or "")
        docs.append(_tokenize(text))
    vectors = _tfidf_matrix(docs)

    clusters: list[dict] = []  # each: {"indices": [], "centroid": vec}

    for i, vec in enumerate(vectors):
        if not vec:
            continue
        assigned = False
        for cluster in clusters:
            if _cosine(vec, cluster["centroid"]) >= sim_threshold:
                cluster["indices"].append(i)
                # update centroid (simple average)
                for k, v in vec.items():
                    cluster["centroid"][k] = cluster["centroid"].get(k, 0.0) + v
                assigned = True
                break
        if not assigned:
            clusters.append({"indices": [i], "centroid": dict(vec)})

    # Build topic summaries
    topics = []
    for cluster in clusters:
        idxs = cluster["indices"]
        if not idxs:
            continue
        # top terms from centroid
        terms = sorted(cluster["centroid"].items(), key=lambda x: x[1], reverse=True)
        top_terms = [t for t, _ in terms[:6]]
        titles = [articles[i].get("title") for i in idxs if articles[i].get("title")]
        sources = [articles[i].get("source") for i in idxs if articles[i].get("source")]
        urls = [articles[i].get("url") for i in idxs if articles[i].get("url")]
        topics.append(
            {
                "size": len(idxs),
                "terms": top_terms,
                "sample_titles": titles[:3],
                "sample_urls": urls[:3],
                "top_sources": list(dict.fromkeys(sources))[:3],
            }
        )

    topics.sort(key=lambda x: x["size"], reverse=True)
    return topics[:max_topics]
