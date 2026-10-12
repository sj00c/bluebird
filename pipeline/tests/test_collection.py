import httpx
import pytest

from bluebird.collection import collect_contests
from bluebird.egress import Egress, Policy


@pytest.fixture
def collection_inputs(tmp_path):
    config = tmp_path / "sources.toml"
    config.write_text('''[[source]]
id = "official"
adapter = "mapped_contest_csv"
collector = "data_go_csv"
dataset_id = "15105816"
file = "official.csv"
name = "공식 우수제안"
license = "공공데이터 이용정책"
url = "https://www.data.go.kr/data/15105816/fileData.do"
layer = 2
public_ok = false
export_grade = "pending"
record_kind = "contest_award"
contest_name = "우수제안"
[source.columns]
title = "제안명"
year = "선정시기"
award = "등급"
''', encoding="utf-8")
    secret = tmp_path / "secret"
    secret.write_bytes(b"s" * 32)
    out = tmp_path / "contests"
    out.mkdir()
    return config, secret, out


def _egress(payload, calls):
    # Shape observed in the official dataset's JSON-LD. Broken description
    # quoting must not hide its independently valid attachment URL.
    metadata = '''<script type="application/ld+json">{
      "@type":"Dataset", "description":"a "quoted" description",
      "distribution":[{"@type":"DataDownload", "encodingFormat":"CSV",
      "contentUrl":"https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000003206312&fileDetailSn=1&insertDataPrcus=N"}]
    }</script>'''

    def handler(request):
        if request.url.path.endswith("/fileData.do"):
            return httpx.Response(200, text=metadata)
        return httpx.Response(200, content=payload, headers={"content-type": "application/octet-stream"})

    return Egress(policy=Policy(grades={}, rules={}), recorder=lambda call: calls.append(call),
                  proxy="", transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("payload", [
    b"<html>temporary portal error</html>",
    '제안명,등급,선정시기\n"닫히지 않은 제목,우수,2022\n'.encode(),
    "바뀐제목,등급,선정시기\n작품,우수,2022\n".encode(),
    "제안명,등급,선정시기\n,우수,2022\n".encode(),
])
def test_bad_download_preserves_last_good(collection_inputs, payload):
    config, secret, out = collection_inputs
    original = "제안명,등급,선정시기\n빗물 회수,우수,2022\n".encode("cp949")
    target = out / "official.csv"
    target.write_bytes(original)
    calls = []
    with _egress(payload, calls) as eg:
        result, = collect_contests(configs=[config], out_dir=out, secret_path=secret,
                                   dsn="unused", egress=eg, download_only=True)
    assert result["status"] == "error"
    assert target.read_bytes() == original
    assert len(calls) == 2 and all(c.purpose == "collect" and not c.fields_sent for c in calls)
    assert sorted(p.name for p in out.iterdir()) == ["official.csv"]


def test_valid_download_is_idempotent_and_audited(collection_inputs):
    config, secret, out = collection_inputs
    payload = "제안명,등급,선정시기\n빗물 회수,우수,21년 상반기\n빗물 회수,우수,21년 상반기\n".encode("cp949")
    calls = []
    with _egress(payload, calls) as eg:
        first, = collect_contests(configs=[config], out_dir=out, secret_path=secret,
                                  dsn="unused", egress=eg, download_only=True)
        second, = collect_contests(configs=[config], out_dir=out, secret_path=secret,
                                   dsn="unused", egress=eg, download_only=True)
    assert first["status"] == "downloaded" and first["download_rows"] == 1
    assert second["status"] == "unchanged"
    assert (out / "official.csv").read_bytes() == payload
    assert len(calls) == 4 and all(not c.fields_sent for c in calls)


def test_ingestion_rejection_preserves_last_good(collection_inputs, monkeypatch):
    from bluebird import ingest

    config, secret, out = collection_inputs
    original = "제안명,등급,선정시기\n이전 프로젝트,우수,2021\n".encode()
    (out / "official.csv").write_bytes(original)

    def reject(**kwargs):
        raise ingest.IngestError("source would retire too many rows")

    monkeypatch.setattr(ingest, "ingest", reject)
    payload = "제안명,등급,선정시기\n새 프로젝트,우수,2022\n".encode()
    with _egress(payload, []) as eg:
        result, = collect_contests(configs=[config], out_dir=out, secret_path=secret, dsn="unused", egress=eg)
    assert result["status"] == "error" and "retire" in result["error"]
    assert (out / "official.csv").read_bytes() == original


def test_design_gallery_omits_untitled_entries_and_masks_named_projects(tmp_path, monkeypatch):
    import csv

    from bluebird import collect_design

    monkeypatch.setattr(collect_design.time, "sleep", lambda _: None)
    common = {"year_info": "2024", "cdGubun": "대한민국디자인전람회",
              "exhibitCate1": "제품디자인", "cd_prize": "6", "tp_awards": "3",
              "apply_nm": "김하나"}
    records = [{**common, "idx_exhibit": 1, "exhibit_title": None},
               {**common, "idx_exhibit": 2, "exhibit_title": "김하나의 빗물 회수 장치"}]

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(200, json={"page": 1, "total": 1, "realTotal": 2, "rows": records})

    destination = tmp_path / "design.csv"
    with Egress(policy=Policy({}), recorder=lambda call: None, proxy="",
                transport=httpx.MockTransport(handler)) as eg:
        result = collect_design.download(
            source={"design_group": "2", "url": "https://award.kidp.or.kr/Exhibit/winners.do?cd_gubun=2"},
            destination=destination, egress=eg)
    with destination.open() as handle:
        row, = csv.DictReader(handle)
    assert row["key"] == "2" and row["title"] == "○○의 빗물 회수 장치"
    assert row["award"] == "입선" and row["year"] == "2024"
    assert "김하나" not in destination.read_text()
    assert result["rows"] == 1 and result["excluded_without_title"] == 1
