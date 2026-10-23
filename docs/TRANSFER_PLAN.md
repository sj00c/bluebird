# 서버 이관 계획: 로컬 검색 자료 → 서버 정제 DB

대상: 서버 `161.122.152.68:5432/parangsae` ← 로컬 `localhost:15450/parangsae`(bb-local).

## 1. 지금 상태(2026-10-23 확인)

| 항목 | 서버 | 로컬 |
|---|---|---|
| PostgreSQL | 16.13 | 16.15 |
| pgvector | **없음**(이미지에 없음) | 0.8.7 |
| 마이그레이션(master) | ~0015 | ~0019 |
| master 기본 19칸·raw | 같음(체크섬 일치) | 같음 |
| master 검색 칸(embedding_input·embedding·search_tokens) | 없음 | 114,781행 |
| external.law / external.doc | 없음 | 66,121 / 21,455행 |
| db_log | 23줄(23 = 이관 전 백업) | 37줄(23~37 = 로컬 작업) |

서버 접속 계정 `aix` = DB 주인이지만 superuser 아님. pgvector는 trusted 확장이 아니라 `aix`가 만들 수 없음 → 관리자 작업 필요.

## 2. 준비된 것

| 파일 | 내용 | sha256 앞 12자 |
|---|---|---|
| `C:/dev/parangsae/backup/parangsae-before-0016.dump` | 서버 이관 전 백업(pg_dump -Fc, 150MB). 서버 db_log 23번 | 7e9ea401e393 |
| `C:/dev/parangsae/backup/transfer-2026-10-23/` | 옮길 자료(바이너리 COPY 3개 + `manifest.json`, 약 500MB) | manifest 안에 파일별 |

옮길 자료 만든 명령: `bluebird master transfer export --dsn <로컬> --dir <빈 폴더>`.
`manifest.json` = 파일별 행 수·sha256, 체크섬(바탕 master 19칸 + 옮길 내용 3개), 원본 마이그레이션 목록, 원본 db_log 전체.

## 3. 관리자 작업(서버, 먼저)

1. 서버 PostgreSQL 컨테이너 이미지를 `pgvector/pgvector:pg16`으로 교체. 같은 메이저(16)라 데이터 볼륨 그대로 사용
   - compose면 `image:` 한 줄 교체 후 `docker compose up -d`, `docker run`이면 같은 볼륨·포트·환경변수로 이미지만 바꿔 다시 실행
2. superuser로 확장 생성: `psql -U <superuser> -d parangsae -c "CREATE EXTENSION IF NOT EXISTS vector;"`
3. 확인: `SELECT extversion FROM pg_extension WHERE extname = 'vector';` → 0.8 이상

## 4. 이관(이 PC에서, Git Bash)

```bash
cd /c/dev/parangsae/bluebird && eval "$(./demo.sh env)" && cd pipeline
S=postgresql://aix:<비밀번호>@161.122.152.68:5432/parangsae
D=/c/dev/parangsae/backup/transfer-2026-10-23
uv run bluebird master transfer check   --dsn $S --dir $D   # pgvector·마이그레이션 없음만 나와야 함
BB_LOG_PLACE=local uv run bluebird migrate --target master --dsn $S          # 0016~0019 (db_log 자동 기록)
uv run bluebird master transfer check   --dsn $S --dir $D   # status ok
BB_LOG_PLACE=local uv run bluebird master transfer import --dsn $S --dir $D  # 한 트랜잭션 + db_log restore 1줄
uv run bluebird master transfer verify  --dsn $S --dir $D   # 체크섬 4개 모두 true
```

`import`가 확인하는 것(하나라도 걸리면 아무것도 안 바꿈): 파일 sha256, pgvector, 원본 마이그레이션 전부 적용, 서버 master 19칸 체크섬 = 원본, external 두 표가 빔.
가져오는 중 행 수가 하나라도 다르면 전체 되돌림.

## 5. 이관 뒤 확인

1. `bluebird master search "강아지" --awarded --top 5 --dsn $S --config …` → 로컬과 같은 결과 나오는지
2. 검색 API를 서버 DB로: `bluebird master serve --dsn $S --config …`(데모 `.env.local` 그대로 127.0.0.1:8100)
3. `bluebird master log --dsn $S` → migrate·restore 기록, 로컬 작업 기록(23~37) 합쳐졌는지

## 6. 되돌리기

- `import` 실패 = 자동 되돌림(서버 그대로). `migrate` 실패 = 0016~0019 한 트랜잭션이라 자동 되돌림
- 이관 뒤 되돌려야 하면: 관리자가 `parangsae-before-0016.dump`를 새 DB에 pg_restore → 확인 → 이름 바꿔치기. 행 삭제·칸 삭제로 되돌리지 않음

## 7. 리허설(로컬, 2026-10-23)

서버 백업(`parangsae-before-0016.dump`)을 로컬 `parangsae_rehearsal`에 복원 → 4장 명령 그대로. 두 번 실행, 같은 결과.

| 단계 | 결과 | 걸린 시간 |
|---|---|---|
| check(전) | 막힘: pgvector 없음 + 0016~0019 없음 (서버와 같은 상황) | 몇 초 |
| migrate | 0016~0019 적용 | 몇 초 |
| check | ok | 몇 초 |
| import | master 114,781 · external.law 66,121 · external.doc 21,455 · 원본 db_log 15줄 + restore 1줄 | 약 6.5분(392초, 대부분 HNSW 색인 갱신) |
| verify | 체크섬 4개(바탕·master 검색 칸·law·doc) 모두 같음 | 몇 초 |
| import 다시 | 막힘: external 두 표에 이미 행 있음(아무것도 안 바뀜) | 몇 초 |
| 검색 비교 | `master search … --awarded --no-rerank` 상위 5개 = 로컬과 같음 | – |

서버는 `maintenance_work_mem` 64MB·`shared_buffers` 128MB라 import가 이보다 오래 걸릴 수 있음 [추정]. 진행 중 master 행이 잠기므로 이관 중 다른 master 작업 금지.
