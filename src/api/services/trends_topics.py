from __future__ import annotations

import numpy as np

try:
    from sklearn.cluster import DBSCAN, KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.mixture import GaussianMixture
except Exception:  # pragma: no cover - fallback when sklearn is missing
    DBSCAN = KMeans = GaussianMixture = None
    TfidfVectorizer = None

from src.api.services.trends_engine import _tokenize, get_stopwords


def _build_docs(articles: list[dict]) -> list[str]:
    docs = []
    for art in articles:
        text = (art.get("title") or "") + " " + (art.get("content") or "")
        docs.append(text.strip())
    return docs


def _vectorize(docs: list[str]):
    if not TfidfVectorizer:
        return None, []
    stop_words = list(get_stopwords())
    n_docs = len(docs)
    min_df = 1 if n_docs < 20 else 2
    max_df = 0.85 if n_docs >= 10 else 1.0
    vectorizer = TfidfVectorizer(
        max_features=5000,
        tokenizer=_tokenize,
        preprocessor=None,
        token_pattern=None,
        lowercase=False,
        min_df=min_df,
        max_df=max_df,
        stop_words=stop_words,
        ngram_range=(1, 2),
    )
    matrix = vectorizer.fit_transform(docs)
    return matrix, vectorizer.get_feature_names_out().tolist()



def _cluster_labels(
    matrix,
    method: str,
    n_clusters: int,
    eps: float,
    min_samples: int,
    random_state: int,
):
    method = (method or "kmeans").lower()
    n_docs = matrix.shape[0]
    if n_docs <= 1:
        return np.zeros(n_docs, dtype=int)

    if method == "kmeans" and KMeans:
        k = max(1, min(n_clusters, n_docs))
        model = KMeans(n_clusters=k, n_init="auto", random_state=random_state)
        return model.fit_predict(matrix)

    if method in {"gmm", "gaussian"} and GaussianMixture:
        k = max(1, min(n_clusters, n_docs))
        model = GaussianMixture(n_components=k, random_state=random_state)
        return model.fit_predict(matrix.toarray())

    if method == "dbscan" and DBSCAN:
        model = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine")
        return model.fit_predict(matrix)

    return np.zeros(n_docs, dtype=int)


def _auto_cluster_labels(
    matrix,
    n_clusters: int,
    eps: float,
    min_samples: int,
    random_state: int,
):
    n_docs = matrix.shape[0]
    if n_docs <= 1:
        return np.zeros(n_docs, dtype=int), "single", 0.0

    # 1) Try DBSCAN for natural density clusters
    if DBSCAN:
        db_labels = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine").fit_predict(matrix)
        unique = [label for label in np.unique(db_labels) if label != -1]
        noise_ratio = float(np.sum(db_labels == -1)) / float(n_docs)
        if len(unique) >= 2 and noise_ratio <= 0.6:
            return db_labels, "dbscan", noise_ratio

    # 2) Fall back to KMeans for stable partitioning
    if KMeans:
        k = max(2, min(n_clusters, n_docs))
        return KMeans(n_clusters=k, n_init="auto", random_state=random_state).fit_predict(matrix), "kmeans", 0.0

    # 3) Final fallback: single cluster
    return np.zeros(n_docs, dtype=int), "single", 0.0

def build_topics(
    articles: list[dict],
    max_topics: int = 10,
    method: str = "auto",
    n_clusters: int = 8,
    eps: float = 0.35,
    min_samples: int = 3,
    random_state: int = 42,
) -> list[dict]:
    docs = _build_docs(articles)
    if not docs:
        return []

    matrix, terms = _vectorize(docs)
    if matrix is None or not terms:
        return []

    used_method = (method or "auto").lower()
    noise_ratio = 0.0
    if used_method == "auto":
        labels, used_method, noise_ratio = _auto_cluster_labels(
            matrix=matrix,
            n_clusters=n_clusters,
            eps=eps,
            min_samples=min_samples,
            random_state=random_state,
        )
    else:
        labels = _cluster_labels(
            matrix=matrix,
            method=method,
            n_clusters=n_clusters,
            eps=eps,
            min_samples=min_samples,
            random_state=random_state,
        )

    topics = []
    unique_labels = [label for label in np.unique(labels) if label != -1]
    for label in unique_labels:
        idxs = np.where(labels == label)[0].tolist()
        if not idxs:
            continue

        cluster_vec = matrix[idxs].sum(axis=0)
        if hasattr(cluster_vec, "A1"):
            scores = cluster_vec.A1
        else:
            scores = np.asarray(cluster_vec).ravel()

        top_idx = np.argsort(scores)[::-1][:6]
        top_terms = [terms[i] for i in top_idx if scores[i] > 0]

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


def build_topics_with_meta(
    articles: list[dict],
    max_topics: int = 10,
    method: str = "auto",
    n_clusters: int = 8,
    eps: float = 0.35,
    min_samples: int = 3,
    random_state: int = 42,
) -> tuple[list[dict], dict]:
    docs = _build_docs(articles)
    if not docs:
        return [], {"method_used": "none", "cluster_count": 0, "noise_ratio": 0.0}

    matrix, terms = _vectorize(docs)
    if matrix is None or not terms:
        return [], {"method_used": "none", "cluster_count": 0, "noise_ratio": 0.0}

    used_method = (method or "auto").lower()
    noise_ratio = 0.0
    if used_method == "auto":
        labels, used_method, noise_ratio = _auto_cluster_labels(
            matrix=matrix,
            n_clusters=n_clusters,
            eps=eps,
            min_samples=min_samples,
            random_state=random_state,
        )
    else:
        labels = _cluster_labels(
            matrix=matrix,
            method=method,
            n_clusters=n_clusters,
            eps=eps,
            min_samples=min_samples,
            random_state=random_state,
        )

    topics = []
    unique_labels = [label for label in np.unique(labels) if label != -1]
    for label in unique_labels:
        idxs = np.where(labels == label)[0].tolist()
        if not idxs:
            continue

        cluster_vec = matrix[idxs].sum(axis=0)
        if hasattr(cluster_vec, "A1"):
            scores = cluster_vec.A1
        else:
            scores = np.asarray(cluster_vec).ravel()

        top_idx = np.argsort(scores)[::-1][:6]
        top_terms = [terms[i] for i in top_idx if scores[i] > 0]

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
    topics = topics[:max_topics]
    return topics, {"method_used": used_method, "cluster_count": len(topics), "noise_ratio": noise_ratio}
