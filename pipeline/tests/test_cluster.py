"""cluster: 합성 계층 blob에서 두 방법의 전원 배정·개수·결정성."""

import numpy as np
import pytest

from bluebird import cluster


def _blobs(seed=0, tops=4, subs=5, per=30, dims=32):
    """대분류 tops개 × 세부 subs개 × per점. 대분류 중심은 멀리, 세부는 그 주변."""
    rng = np.random.default_rng(seed)
    out, top_true = [], []
    for t in range(tops):
        c = rng.normal(0, 20, dims)
        for _ in range(subs):
            s = c + rng.normal(0, 4, dims)
            out.append(s + rng.normal(0, 0.5, (per, dims)))
            top_true += [t] * per
    return np.vstack(out).astype("float32"), np.array(top_true)


def test_kmeans_ward_assigns_all_with_exact_counts_and_recovers_tops():
    from sklearn.metrics import adjusted_rand_score

    z, truth = _blobs()
    fit = cluster.fit_kmeans_ward(z, cluster.Params(top_k=4, sub_k=20), seed=0)
    assert len(fit.sub) == len(z) and set(fit.sub) == set(range(20))
    assert len(fit.top_of_sub) == 20 and set(fit.top_of_sub) == set(range(4))
    assert adjusted_rand_score(truth, fit.top_of_sub[fit.sub]) > 0.95
    again = cluster.fit_kmeans_ward(z, cluster.Params(top_k=4, sub_k=20), seed=0)
    assert (again.sub == fit.sub).all() and (again.top_of_sub == fit.top_of_sub).all()


def test_umap_hdbscan_assigns_noise_and_caps_sub_count():
    z, _ = _blobs(per=40)
    fit = cluster.fit_umap_hdbscan(z, cluster.Params(top_k=4, sub_k=6, min_cluster_size=15), seed=0)
    assert len(fit.sub) == len(z) and fit.sub.min() >= 0          # 노이즈도 배정
    assert len(fit.top_of_sub) <= 6 and set(fit.top_of_sub) == set(range(4))
    assert 0.0 <= fit.noise_ratio < 1.0 and fit.n_micro >= 4


def test_umap_hdbscan_stops_when_too_few_micro_clusters():
    z, _ = _blobs(tops=1, subs=1, per=80)
    with pytest.raises(cluster.ClusterError):
        cluster.fit_umap_hdbscan(z, cluster.Params(top_k=5, sub_k=10, min_cluster_size=15), seed=0)


def test_ward_cut_refuses_more_tops_than_clusters():
    with pytest.raises(cluster.ClusterError):
        cluster.ward_cut(np.zeros((3, 2), dtype="float32"), 4)


def test_reduce_caps_dims_and_reports_variance():
    z, _ = _blobs(dims=200)
    out, explained = cluster.reduce(z, 128)
    assert out.shape == (len(z), 128) and out.dtype == np.float32 and 0.9 < explained <= 1.0001


def test_grid_expands_cartesian_product_in_order():
    assert cluster._grid({"a": [1, 2], "b": ["x"]}) == [{"a": 1, "b": "x"}, {"a": 2, "b": "x"}]


def test_tune_rejects_parameters_of_the_other_method():
    with pytest.raises(ValueError, match="no parameters"):
        cluster.tune("dsn", "k", "kmeans_ward", "/tmp/x", grid={"min_cluster_size": [10]})
