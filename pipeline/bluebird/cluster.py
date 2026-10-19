"""비지도 2단계 계층 군집(2026-10-13 사용자 결정). 결과 = core.cluster_run·cluster·idea_cluster.

- 입력: 한 임베딩 키의 대표 기록(core.idea_duplicate에 없는 행) 벡터 → PCA(pca_dims) → 방법별 적합
- kmeans_ward: 세부 = KMeans(sub_k), 대분류 = 세부 중심 Ward(top_k)
- umap_hdbscan: UMAP(cosine, min_dist 0) → HDBSCAN 미세 군집(노이즈 = 가장 가까운 미세 중심),
  미세가 sub_k보다 많으면 Ward(sub_k)로 세부, 대분류 = Ward(top_k)
- 파라미터 = Params. `tune`이 격자 탐색 표(seed 안정성 ARI·실루엣·노이즈·크기)를 내고, 고른 값으로 `run`/`compare`
- duplicate_record는 학습에서 빠지고 대표 기록의 세부 군집을 상속(inherited_from)
- 이전 run은 그대로 둔다. 개수를 바꾸려면 새 run(AC5)
- 군집 이름·요약 = 상용 LLM, egress 용도 analysis
"""

from __future__ import annotations

import json
import resource
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path

from openpyxl import Workbook

from . import db, embed, llm
from .egress import Egress

METHODS = ("kmeans_ward", "umap_hdbscan")
REPS = 5


@dataclass(frozen=True)
class Params:
    """run 하나의 설정. 전부 cluster_run.params에 남는다."""
    top_k: int = 15
    sub_k: int = 300
    pca_dims: int = 128
    n_init: int = 4                 # kmeans_ward
    umap_neighbors: int = 15        # umap_hdbscan(기본 = BERTopic 구성)
    umap_dims: int = 5
    min_cluster_size: int = 50
    min_samples: int = 5
    selection: str = "eom"          # HDBSCAN cluster_selection_method: eom | leaf


# 2026-10-14 탐색(cluster tune, 76k, seed 0·1; .runtime/export/cluster-tune/) 뒤 방법별 기본값.
# kmeans_ward: sub_k 300에서 PCA 256이 128보다 대분류 ARI 0.589→0.638, 실루엣 0.0447→0.0474. n_init 10은 이득 없음.
# umap_hdbscan: UMAP 10차원·min_samples 15가 BERTopic 기본(5차원·5)보다 세부·대분류 ARI 0.681·0.612→0.755·0.723,
#   노이즈 0.40→0.45. min_cluster_size ≥100은 KIPRIS 전체(37.7k, 49.6%)가 한 군집이 되므로 제외.
DEFAULTS = {"kmeans_ward": Params(pca_dims=256),
            "umap_hdbscan": Params(pca_dims=128, umap_neighbors=15, umap_dims=10, min_cluster_size=50,
                                   min_samples=15)}

METHOD_FIELDS = {"kmeans_ward": ("pca_dims", "sub_k", "n_init"),
                 "umap_hdbscan": ("pca_dims", "umap_neighbors", "umap_dims", "min_cluster_size", "min_samples",
                                  "selection")}

DUPS_SQL = "SELECT idea_id, canonical_id FROM core.idea_duplicate"



def orphans(conn) -> list[str]:
    """대상 duplicate 중 canonical이 대상 밖인 id. 있으면 상속할 군집이 없으므로 멈춘다."""
    tgt = {r[0] for r in embed.target_rows(conn)}
    return sorted(d for d, c in conn.execute(DUPS_SQL) if d in tgt and c not in tgt)

INFO_SQL = """
    SELECT i.id, i.source_id, coalesce(s.record_kind, ''), i.title, i.body, i.year
      FROM core.idea i JOIN core.source s ON s.id = i.source_id WHERE i.id = ANY(%s)
"""

# 세부(level 2) 지표 → 대분류(level 1)는 소속 세부의 행 전체로 같은 식. ratio 계열 = 대표 기록 기준
METRICS_SQL = """
WITH grp AS (   -- 묶음(대표 + duplicate 전체, 대상 밖 구성원 포함) 중 어느 기록에든 수상이 있으면 참
    SELECT coalesce(d.canonical_id, i.id) AS canonical_id, bool_or(nullif(i.award, '') IS NOT NULL) AS awarded
      FROM core.idea i LEFT JOIN core.idea_duplicate d ON d.idea_id = i.id
     GROUP BY 1
),
m AS (
    SELECT ic.idea_id, ic.inherited_from, s.id AS sub_id, s.parent_id AS top_id, i.year, i.source_id,
           c.audience, coalesce(grp.awarded, false) AS awarded
      FROM core.idea_cluster ic
      LEFT JOIN grp ON grp.canonical_id = ic.idea_id
      JOIN core.cluster s ON s.id = ic.sub_id
      JOIN core.idea i ON i.id = ic.idea_id
      JOIN core.contest c ON c.id = i.contest_id
     WHERE ic.run_id = %(run)s
),
g AS (
    SELECT unnest(ARRAY[sub_id, top_id]) AS cluster_id, * FROM m
)
UPDATE core.cluster k SET metrics = x.metrics
  FROM (SELECT cluster_id, jsonb_build_object(
            'count_ideas', count(*) FILTER (WHERE inherited_from IS NULL),
            'count_records', count(*),
            'year_min', min(year), 'year_max', max(year),
            'distinct_years', count(DISTINCT year), 'distinct_sources', count(DISTINCT source_id),
            'award_ratio', round(avg(awarded::int) FILTER (WHERE inherited_from IS NULL), 4),
            'student_contest_ratio', round(avg((audience = 'student')::int) FILTER (WHERE inherited_from IS NULL), 4)
        ) AS metrics
          FROM g GROUP BY cluster_id) x
 WHERE k.id = x.cluster_id AND k.run_id = %(run)s
"""


class ClusterError(RuntimeError):
    """멈추고 보고할 상황(폴백 없음)."""


@dataclass
class Data:
    key: str
    ids: list[str]                 # 학습 대상(대표 기록)
    z: object                      # PCA 결과 float32 (n, pca_dims)
    explained: float
    pca_dims: int
    dups: list[tuple[str, str]]    # (duplicate id, canonical id), 둘 다 임베딩된 것만
    load_seconds: float


@dataclass
class Fit:
    sub: object                    # (n,) 세부 번호 0..S-1
    top_of_sub: object             # (S,) 대분류 번호 0..K-1
    noise_ratio: float
    n_micro: int


def max_rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(r / (1024 * 1024) if sys.platform == "darwin" else r / 1024, 1)


def reduce(x, dims: int, seed: int = 0):
    from sklearn.decomposition import PCA

    pca = PCA(n_components=min(dims, x.shape[1], x.shape[0]), random_state=seed)
    z = pca.fit_transform(x).astype("float32")
    return z, float(pca.explained_variance_ratio_.sum())


def load_raw(dsn: str, key: str):
    """(대표 기록 id, 원 벡터 float32, [(duplicate, canonical)]). 고아 duplicate·대표 미임베딩이 있으면 멈춘다."""
    with db.connect(dsn) as conn:
        orph = orphans(conn)
        if orph:
            raise ClusterError(f"{len(orph)} target duplicates whose canonical is outside the target "
                               f"(e.g. {orph[:3]})")
        ids, x = embed.load(conn, key)
        dup = dict(conn.execute(DUPS_SQL).fetchall())
    if not ids:
        raise ClusterError(f"no embeddings for {key}; run `embed run --model {key}` first")
    have = set(ids)
    missing = [d for d in ids if d in dup and dup[d] not in have]
    if missing:
        raise ClusterError(f"{len(missing)} duplicate records whose canonical is not embedded (e.g. {missing[:3]})")
    keep = [n for n, i in enumerate(ids) if i not in dup]
    return [ids[n] for n in keep], x[keep], [(d, dup[d]) for d in ids if d in dup]


def load(dsn: str, key: str, pca_dims: int) -> Data:
    """임베딩된 행 = 대상. 대표 기록만 학습."""
    t0 = time.monotonic()
    ids, x, dups = load_raw(dsn, key)
    z, explained = reduce(x, pca_dims)
    del x
    return Data(key, ids, z, explained, pca_dims, dups, round(time.monotonic() - t0, 1))


def ward_cut(centroids, k: int):
    from sklearn.cluster import AgglomerativeClustering

    if len(centroids) < k:
        raise ClusterError(f"{len(centroids)} clusters cannot be cut into {k}")
    return AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(centroids)


def centroids(z, labels, n: int):
    import numpy as np

    c = np.zeros((n, z.shape[1]), dtype=np.float32)
    np.add.at(c, labels, z)
    return c / np.bincount(labels, minlength=n)[:, None]


def fit_kmeans_ward(z, p: Params, seed: int) -> Fit:
    from sklearn.cluster import KMeans

    sub = KMeans(n_clusters=p.sub_k, n_init=p.n_init, random_state=seed).fit_predict(z)
    return Fit(sub, ward_cut(centroids(z, sub, p.sub_k), p.top_k), 0.0, p.sub_k)


def umap_embed(z, p: Params, seed: int):
    try:
        import umap
    except ImportError as e:   # 폴백 없음: 멈추고 보고
        raise ClusterError(f"umap-learn unavailable: {e}") from e
    return umap.UMAP(n_neighbors=p.umap_neighbors, n_components=p.umap_dims, min_dist=0.0, metric="cosine",
                     random_state=seed).fit_transform(z)


def hdbscan_fit(z, u, p: Params) -> Fit:
    """u = UMAP 결과. 세부·대분류 중심은 z(PCA 공간)에서 계산한다."""
    from sklearn.cluster import HDBSCAN

    micro = HDBSCAN(min_cluster_size=p.min_cluster_size, min_samples=p.min_samples,
                    cluster_selection_method=p.selection, copy=True).fit_predict(u)
    noise = micro < 0
    n_micro = int(micro.max()) + 1
    if n_micro < p.top_k:
        raise ClusterError(f"HDBSCAN found {n_micro} clusters, fewer than top-k {p.top_k}")
    mc = centroids(z[~noise], micro[~noise], n_micro)
    if noise.any():
        micro[noise] = _nearest(z[noise], mc)
    if n_micro > p.sub_k:
        sub = ward_cut(mc, p.sub_k)[micro]
        n_sub = p.sub_k
    else:
        sub, n_sub = micro, n_micro
    return Fit(sub, ward_cut(centroids(z, sub, n_sub), p.top_k), float(noise.mean()), n_micro)


def fit_umap_hdbscan(z, p: Params, seed: int) -> Fit:
    return hdbscan_fit(z, umap_embed(z, p, seed), p)


def _nearest(a, c, chunk: int = 4096):
    """a 각 행에 가장 가까운 c 행 번호(제곱 거리, 메모리 절약용 분할)."""
    import numpy as np

    out = np.empty(len(a), dtype=np.int64)
    cn = (c ** 2).sum(1)
    for s in range(0, len(a), chunk):
        out[s:s + chunk] = (cn[None, :] - 2 * a[s:s + chunk] @ c.T).argmin(1)
    return out


FITS = {"kmeans_ward": fit_kmeans_ward, "umap_hdbscan": fit_umap_hdbscan}


def save_run(dsn: str, data: Data, method: str, fit: Fit, params: dict, metrics: dict) -> int:
    import numpy as np

    n_sub = len(fit.top_of_sub)
    # AC5 불변 검사 기준: 저장한 행 수(duplicate 상속 포함)·군집 수(대분류+세부)
    metrics = {**metrics, "n_assigned": len(data.ids) + len(data.dups),
               "n_clusters": len({int(t) for t in fit.top_of_sub}) + n_sub}
    cen = centroids(data.z, fit.sub, n_sub)
    dist = np.sqrt(((data.z - cen[fit.sub]) ** 2).sum(1))
    with db.connect(dsn) as conn:
        run_id = conn.execute(
            "INSERT INTO core.cluster_run (method, embed_model, params, metrics) VALUES (%s,%s,%s,%s) RETURNING id",
            (method, data.key, json.dumps(params), json.dumps(metrics))).fetchone()[0]
        top_ids = {}
        for t in sorted({int(x) for x in fit.top_of_sub}):
            top_ids[t] = conn.execute("INSERT INTO core.cluster (run_id, level, label) VALUES (%s,1,%s) RETURNING id",
                                      (run_id, t)).fetchone()[0]
        sub_ids = [conn.execute(
            "INSERT INTO core.cluster (run_id, level, label, parent_id) VALUES (%s,2,%s,%s) RETURNING id",
            (run_id, s, top_ids[int(fit.top_of_sub[s])])).fetchone()[0] for s in range(n_sub)]
        own = {i: sub_ids[int(s)] for i, s in zip(data.ids, fit.sub, strict=True)}
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO core.idea_cluster (run_id, idea_id, sub_id, distance) VALUES (%s,%s,%s,%s)",
                            [(run_id, i, own[i], float(d)) for i, d in zip(data.ids, dist, strict=True)])
            cur.executemany(
                "INSERT INTO core.idea_cluster (run_id, idea_id, sub_id, inherited_from) VALUES (%s,%s,%s,%s)",
                [(run_id, d, own[c], c) for d, c in data.dups])
        conn.execute(METRICS_SQL, {"run": run_id})
        conn.commit()
    return run_id


def _fit(data: Data, method: str, p: Params, seed: int) -> tuple[Fit, float]:
    if method not in FITS:
        raise ValueError(f"unknown method {method}")
    if data.pca_dims != p.pca_dims:
        raise ValueError(f"data reduced to {data.pca_dims} dims, params want {p.pca_dims}")
    t0 = time.monotonic()
    fit = FITS[method](data.z, p, seed)
    return fit, round(time.monotonic() - t0, 1)


def _params(data: Data, method: str, p: Params, seed: int) -> dict:
    import sklearn

    params = {"top_k": p.top_k, "sub_k": p.sub_k, "seed": seed,
              **{f: getattr(p, f) for f in METHOD_FIELDS[method]},
              "explained_variance": round(data.explained, 4), "sklearn": sklearn.__version__,
              "prep_version": embed.PREP_VERSION}
    if method == "umap_hdbscan":
        import umap

        params |= {"umap_min_dist": 0.0, "umap": getattr(umap, "__version__", "?")}
    return params


def _run_metrics(fit: Fit, seconds: float, extra: dict | None = None) -> dict:
    import numpy as np

    sub_sizes = np.bincount(fit.sub)
    top_sizes = np.bincount(fit.top_of_sub[fit.sub])
    return {"n_fit": len(fit.sub), "n_top": len(top_sizes), "n_sub": len(sub_sizes),
            "n_micro": fit.n_micro, "noise_ratio": round(fit.noise_ratio, 4),
            "top_size_min_median_max": [int(top_sizes.min()), int(np.median(top_sizes)), int(top_sizes.max())],
            "sub_size_min_median_max": [int(sub_sizes.min()), int(np.median(sub_sizes)), int(sub_sizes.max())],
            "fit_seconds": seconds, "max_rss_mb": max_rss_mb(), **(extra or {})}


def run(dsn: str, key: str, method: str, p: Params, seed: int = 0) -> int:
    data = load(dsn, key, p.pca_dims)
    fit, seconds = _fit(data, method, p, seed)
    return save_run(dsn, data, method, fit, _params(data, method, p, seed), _run_metrics(fit, seconds))


def compare(dsn: str, key: str, out: str, params: dict[str, Params], *, seeds: tuple[int, ...] = (0, 1, 2)) -> dict:
    """params = 방법 → 설정. 방법마다 seed 0 run을 저장하고 비교표(대분류당 대표 5개 + 참고 지표)를 쓴다."""
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    loaded: dict[int, Data] = {}
    info: dict = {}
    runs = {}
    for method, p in params.items():
        if p.pca_dims not in loaded:
            loaded[p.pca_dims] = load(dsn, key, p.pca_dims)
        data = loaded[p.pca_dims]
        if not info:
            with db.connect(dsn) as conn:
                info = {r[0]: r[1:] for r in conn.execute(INFO_SQL, (data.ids,))}
        src = [info[i][0] for i in data.ids]
        kind = [info[i][1] for i in data.ids]
        fits = {s: _fit(data, method, p, s) for s in seeds}
        base, seconds = fits[seeds[0]]
        top = base.top_of_sub[base.sub]
        others = [fits[s][0] for s in seeds[1:]]
        extra = {
            "ari_top": round(sum(adjusted_rand_score(top, f.top_of_sub[f.sub]) for f in others) / max(1, len(others)), 4),
            "ari_sub": round(sum(adjusted_rand_score(base.sub, f.sub) for f in others) / max(1, len(others)), 4),
            "nmi_source": round(normalized_mutual_info_score(src, top), 4),
            "nmi_record_kind": round(normalized_mutual_info_score(kind, top), 4),
            "seeds": list(seeds), "load_seconds": data.load_seconds,
        }
        run_id = save_run(dsn, data, method, base, _params(data, method, p, seeds[0]),
                          _run_metrics(base, seconds, extra))
        runs[method] = run_id
    write_compare(dsn, Path(out), runs)
    return {"runs": runs, "out": out}


TUNE_GRID = {
    "kmeans_ward": {"pca_dims": [64, 128, 256], "sub_k": [150, 300, 500], "n_init": [4, 10]},
    "umap_hdbscan": {"pca_dims": [128], "umap_neighbors": [15, 30], "umap_dims": [5, 10],
                     "min_cluster_size": [30, 50, 100, 150], "min_samples": [5, 15], "selection": ["eom"]},
}
_UMAP_FIELDS = ("pca_dims", "umap_neighbors", "umap_dims")
SIL_SAMPLE = 8000


def _grid(spec: dict[str, list]) -> list[dict]:
    import itertools

    keys = list(spec)
    return [dict(zip(keys, v, strict=True)) for v in itertools.product(*(spec[k] for k in keys))]


def tune(dsn: str, key: str, method: str, out: str, *, base: Params | None = None,
         grid: dict[str, list] | None = None, seeds: tuple[int, int] = (0, 1)) -> dict:
    """설정 격자를 seed 2개로 적합해 비교표만 쓴다(DB 쓰기 없음).

    지표: seed 간 ARI(세부·대분류, HDBSCAN은 둘 다 노이즈 아닌 행 ARI도), 원 벡터 cosine 실루엣(세부, 표본),
    노이즈 비율, 세부 수·크기 min/median/max, 최대 세부 비중, 소스 NMI(세부).
    """
    import numpy as np
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score, silhouette_score

    if method not in FITS:
        raise ValueError(f"unknown method {method}")
    base = base or DEFAULTS[method]
    spec = grid or TUNE_GRID[method]
    unknown = set(spec) - set(METHOD_FIELDS[method])
    if unknown:
        raise ValueError(f"{method} has no parameters {sorted(unknown)}")
    ids, x, _ = load_raw(dsn, key)
    with db.connect(dsn) as conn:
        src_of = dict(conn.execute("SELECT id, source_id FROM core.idea WHERE id = ANY(%s)", (ids,)).fetchall())
    src = np.array([src_of[i] for i in ids])
    rng = np.random.default_rng(0)
    sil_idx = rng.choice(len(ids), size=min(SIL_SAMPLE, len(ids)), replace=False)
    x_sil = x[sil_idx]
    reduced: dict[int, tuple] = {}
    umaps: dict[tuple, dict[int, object]] = {}
    rows = []
    for cfg in _grid(spec):
        p = replace(base, **cfg)
        if p.pca_dims not in reduced:
            reduced[p.pca_dims] = reduce(x, p.pca_dims)
        z, explained = reduced[p.pca_dims]
        t0 = time.monotonic()
        try:
            if method == "umap_hdbscan":
                uk = tuple(getattr(p, f) for f in _UMAP_FIELDS)
                if uk not in umaps:
                    umaps = {uk: {s: umap_embed(z, p, s) for s in seeds}}   # 같은 UMAP 설정끼리 연속(격자 순서)
                fits = {s: hdbscan_fit(z, umaps[uk][s], p) for s in seeds}
            else:
                fits = {s: fit_kmeans_ward(z, p, s) for s in seeds}
        except ClusterError as e:
            rows.append({**cfg, "error": str(e)})
            continue
        f0, f1 = fits[seeds[0]], fits[seeds[1]]
        sizes = np.bincount(f0.sub)
        row = {**cfg,
               "n_sub": len(sizes), "noise": round(f0.noise_ratio, 3),
               "ari_sub": round(adjusted_rand_score(f0.sub, f1.sub), 3),
               "ari_top": round(adjusted_rand_score(f0.top_of_sub[f0.sub], f1.top_of_sub[f1.sub]), 3),
               "silhouette": round(float(silhouette_score(x_sil, f0.sub[sil_idx], metric="cosine")), 4),
               "sub_min": int(sizes.min()), "sub_median": int(np.median(sizes)), "sub_max": int(sizes.max()),
               "max_share": round(float(sizes.max() / len(ids)), 3),
               "nmi_source": round(normalized_mutual_info_score(src, f0.sub), 3),
               "explained": round(explained, 3), "seconds": round(time.monotonic() - t0, 1)}
        rows.append(row)
        print("[tune]", method, row, flush=True)
    _write_tune(Path(out), method, key, len(ids), base, rows)
    return {"method": method, "configs": len(rows), "out": out}


def _write_tune(out: Path, method: str, key: str, n: int, base: Params, rows: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    cols = list(dict.fromkeys(k for r in rows for k in r))
    wb = Workbook()
    ws = wb.active
    ws.title = method
    ws.append(cols)
    for r in rows:
        ws.append([r.get(c) for c in cols])
    wb.save(out / f"tune-{method}.xlsx")
    md = [f"# 군집 파라미터 탐색: {method}", "",
          f"- 임베딩 {key}, 학습 {n}건, 고정값 top_k={base.top_k} sub_k={base.sub_k}(HDBSCAN은 상한)",
          ("- ari_* = seed 0·1 결과 일치도(1 = 같음), silhouette = 원 벡터 cosine(세부, 표본), "
          "max_share = 가장 큰 세부의 비중, nmi_source = 세부와 출처의 겹침(낮을수록 출처를 넘어 섞임)"), "",
          "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + " |" for r in rows]
    (out / f"tune-{method}.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def representatives(dsn: str, run_id: int, per: int, level: int) -> dict[int, list[tuple]]:
    """군집(label) → 대표 기록 (title, body, year, source_id, idea_id). 세부 = 중심 거리 순, 대분류 = 큰 세부부터 하나씩."""
    with db.connect(dsn) as conn:
        rows = conn.execute(
            """SELECT t.label, s.label, s_size.n, ic.distance, i.title, i.body, i.year, i.source_id, i.id
                 FROM core.idea_cluster ic
                 JOIN core.cluster s ON s.id = ic.sub_id
                 JOIN core.cluster t ON t.id = s.parent_id
                 JOIN core.idea i ON i.id = ic.idea_id
                 JOIN (SELECT sub_id, count(*) n FROM core.idea_cluster WHERE run_id = %(r)s GROUP BY 1) s_size
                   ON s_size.sub_id = ic.sub_id
                WHERE ic.run_id = %(r)s AND ic.inherited_from IS NULL
                ORDER BY ic.distance""", {"r": run_id}).fetchall()
    out: dict[int, list[tuple]] = {}
    if level == 2:
        for _, s, _, _, *rec in rows:
            if len(out.setdefault(s, [])) < per:
                out[s].append(tuple(rec))
        return out
    best: dict[tuple[int, int], tuple] = {}
    size: dict[tuple[int, int], int] = {}
    for t, s, n, _, *rec in rows:
        best.setdefault((t, s), tuple(rec))
        size[(t, s)] = n
    for (t, s) in sorted(best, key=lambda ts: -size[ts]):
        if len(out.setdefault(t, [])) < per:
            out[t].append(best[(t, s)])
    return out


def write_compare(dsn: str, out: Path, runs: dict[str, int]) -> None:
    """저장된 run들(방법 → run id)의 비교표. run이 이미 있으면 다시 적합하지 않고 표만 다시 쓴다."""
    out.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)
    with db.connect(dsn) as conn:
        meta = {m: conn.execute("SELECT params, metrics, embed_model FROM core.cluster_run WHERE id = %s",
                                (r,)).fetchone() for m, r in runs.items()}
    first = next(iter(meta.values()))
    md = ["# 군집 방법 비교 (AC3)", "", (f"- 임베딩 {first[2]}, 배정 {first[1]['n_assigned']}건"
          f"(학습 {first[1]['n_fit']}건 + duplicate 상속)"), ""]
    for m, r in runs.items():
        prm = meta[m][0]
        md.append(f"- {m} run {r}: " + ", ".join(f"{k}={prm.get(k)}" for k in dict.fromkeys(("top_k", "sub_k", *METHOD_FIELDS[m])))
                  + f", PCA 설명 분산 {prm['explained_variance']}")
    md.append("")
    with db.connect(dsn) as conn:
        sizes = {m: dict(conn.execute(
            """SELECT t.label, count(*) FROM core.idea_cluster ic JOIN core.cluster s ON s.id = ic.sub_id
                 JOIN core.cluster t ON t.id = s.parent_id WHERE ic.run_id = %s GROUP BY 1""", (r,)))
            for m, r in runs.items()}
    ws = wb.create_sheet("metrics")
    keys = ["run_id", "n_top", "n_sub", "n_micro", "noise_ratio", "top_size_min_median_max", "sub_size_min_median_max",
            "ari_top", "ari_sub", "nmi_source", "nmi_record_kind", "fit_seconds", "max_rss_mb"]
    ws.append(["method", *keys])
    md += ["| method | " + " | ".join(keys) + " |", "|" + "---|" * (len(keys) + 1)]
    for m, r in runs.items():
        vals = [r, *[meta[m][1].get(k) for k in keys[1:]]]
        ws.append([m, *[json.dumps(v) if isinstance(v, list) else v for v in vals]])
        md.append(f"| {m} | " + " | ".join(str(v) for v in vals) + " |")
    md.append("")
    for m, r in runs.items():
        reps = representatives(dsn, r, REPS, level=1)
        ws = wb.create_sheet(m)
        ws.append(["대분류", "크기", "대표 제목", "본문 앞 80자", "연도", "소스", "idea_id"])
        md += [f"## {m} (run {r})", ""]
        for t in sorted(reps, key=lambda t: -sizes[m][t]):
            md.append(f"### 대분류 {t} ({sizes[m][t]}건)")
            for title, body, year, sid, iid in reps[t]:
                short = embed.clean(body)[:80]
                ws.append([t, sizes[m][t], title, short, year, sid, iid])
                md.append(f"- {title} — {short} ({year}, {sid})")
            md.append("")
    md += ["## 결정", "", "(사용자 결정 후 기록: 날짜, run id·방법·개수, 요지)", ""]
    wb.save(out / "cluster-compare.xlsx")
    (out / "cluster-compare.md").write_text("\n".join(md), encoding="utf-8")


NAME_SYSTEM = "너는 아이디어 군집에 짧은 한국어 이름을 붙이는 분류 담당자다. JSON 객체만 답한다."
NAME_INSTRUCTION = (
    "아래 <idea>들은 비지도 군집 하나에서 중심에 가까운 대표 아이디어다. 공통 주제를 보고 "
    '{"name": "군집 이름(15자 이내, 명사구)", "summary": "어떤 아이디어들이 모였는지 한 문장(60자 이내)"} 을 답하라. '
    "개별 아이디어 하나의 제목을 그대로 쓰지 말고, 평가·추천 표현을 넣지 마라."
)


def name(dsn: str, run_id: int, *, per: int = 8, eg: Egress | None = None) -> dict:
    """이름이 없는 군집에만 LLM 이름·요약을 붙인다(재실행 = 이어서)."""
    p = llm.provider()
    if p is None:
        raise ClusterError("no LLM key (OPENAI_API_KEY or ANTHROPIC_API_KEY)")
    own = eg is None
    eg = eg or Egress.from_dsn(dsn)
    out = {"named": 0, "skipped": 0}
    try:
        with db.connect(dsn) as conn:
            todo = conn.execute("SELECT id, level, label FROM core.cluster WHERE run_id = %s AND name IS NULL"
                                " ORDER BY level, label", (run_id,)).fetchall()
        reps = {lvl: representatives(dsn, run_id, per, lvl) for lvl in (1, 2)}
        for cid, level, label in todo:
            items = [("idea", sid, f"{title}\n{embed.clean(body)[:200]}") for title, body, _, sid, _ in reps[level][label]]
            data, _ = llm.ask_json(eg, p, system=NAME_SYSTEM, instruction=NAME_INSTRUCTION, fields=items,
                                   max_tokens=300, purpose="analysis")
            nm, sm = str(data.get("name") or "").strip()[:60], str(data.get("summary") or "").strip()[:300]
            if not nm or not sm:
                out["skipped"] += 1
                continue
            with db.connect(dsn) as conn:
                conn.execute("UPDATE core.cluster SET name = %s, summary = %s WHERE id = %s", (nm, sm, cid))
                conn.commit()
            out["named"] += 1
    finally:
        if own:
            eg.close()
    return out


def export_xlsx(dsn: str, run_id: int, out: str) -> str:
    from .export import _autosize

    metric_keys = ["count_ideas", "count_records", "year_min", "year_max", "distinct_years", "distinct_sources",
                   "award_ratio", "student_contest_ratio"]
    wb = Workbook()
    with db.connect(dsn) as conn:
        run = conn.execute("SELECT method, embed_model, params, metrics, created_at FROM core.cluster_run WHERE id = %s",
                           (run_id,)).fetchone()
        if run is None:
            raise ClusterError(f"no cluster run {run_id}")
        ws = wb.active
        ws.title = "top"
        ws.append(["label", "name", "summary", *metric_keys])
        for label, nm, sm, m in conn.execute(
                "SELECT label, name, summary, metrics FROM core.cluster WHERE run_id = %s AND level = 1 ORDER BY label",
                (run_id,)):
            ws.append([label, nm, sm, *[m.get(k) for k in metric_keys]])
        _autosize(ws, {"name": 24, "summary": 60})
        ws = wb.create_sheet("sub")
        ws.append(["top_label", "top_name", "label", "name", "summary", *metric_keys])
        for row in conn.execute(
                """SELECT t.label, t.name, s.label, s.name, s.summary, s.metrics FROM core.cluster s
                     JOIN core.cluster t ON t.id = s.parent_id WHERE s.run_id = %s ORDER BY t.label, s.label""",
                (run_id,)):
            ws.append([*row[:5], *[row[5].get(k) for k in metric_keys]])
        _autosize(ws, {"top_name": 24, "name": 24, "summary": 60})
        ws = wb.create_sheet("ideas")
        ws.append(["idea_id", "top_label", "top_name", "sub_label", "sub_name", "distance", "inherited_from",
                   "source_id", "year", "award", "title"])
        for row in conn.execute(
                """SELECT ic.idea_id, t.label, t.name, s.label, s.name, ic.distance, ic.inherited_from,
                          i.source_id, i.year, i.award, i.title
                     FROM core.idea_cluster ic JOIN core.cluster s ON s.id = ic.sub_id
                     JOIN core.cluster t ON t.id = s.parent_id JOIN core.idea i ON i.id = ic.idea_id
                    WHERE ic.run_id = %s ORDER BY t.label, s.label, ic.distance NULLS LAST""", (run_id,)):
            ws.append(list(row))
        _autosize(ws, {"title": 50, "top_name": 24, "sub_name": 24})
        ws = wb.create_sheet("params")
        ws.append(["key", "value"])
        for k, v in (("run_id", run_id), ("method", run[0]), ("embed_model", run[1]),
                     ("created_at", run[4].isoformat()), *run[2].items(), *run[3].items()):
            ws.append([k, json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v])
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out
