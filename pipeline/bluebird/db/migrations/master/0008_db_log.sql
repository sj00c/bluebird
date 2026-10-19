-- DB 작업 기록. git을 공유하지 않는 쪽(배포 서버)도 이 표로 서로 한 일을 확인한다. 덤프에 같이 실려 간다.
-- 1행 = 작업 1건(이관 덤프·복원, 마이그레이션, 수집·정제·재계산). 쓰기 = bluebird master log, master 명령은 자동 기록.
CREATE TABLE db_log (
    id      serial PRIMARY KEY,
    at      timestamptz NOT NULL DEFAULT now(),
    place   text NOT NULL,          -- 어디서: local / server 등(BB_LOG_PLACE)
    action  text NOT NULL,          -- dump · restore · migrate · files · api · detail · refine · fill · reasons · classify · drop · note
    note    text NOT NULL,          -- 한 일·결과
    master  integer,                -- 기록 시점 master 행 수
    raw     integer,                -- 기록 시점 raw 행 수
    file    text,                   -- 덤프 파일 이름(있을 때)
    sha256  text                    -- 그 파일 sha256
);

-- 이 표 이전 이력(git 기록·덤프 RESTORE.txt·migrations.applied 기준)
INSERT INTO db_log (at, place, action, note, master, raw, file, sha256) VALUES
('2026-10-14 15:00+09', 'local', 'files',
 '로컬 Docker DB bluebird_master 생성. raw 적재(파일·API·상세 본문) → refine → fill(LLM). master 0001·0002', NULL, NULL, NULL, NULL),
('2026-10-15 09:40+09', 'local', 'dump',
 'bluebird_master 전체(raw·master·migrations) pg_dump -Fc → xz → 7z 암호·19MB 5분할, 메일 전달. 임시 DB 복원으로 행 수·내용 해시 일치 확인',
 141827, 170500, 'bluebird_master-2026-10-15.dump.xz', '6f1d8a7e1fe5f8240137f8fd838ef6558d97961dc969cbb0a414a3c60842ae10'),
('2026-10-15 10:55+09', 'server', 'restore',
 '서버 161.122.152.68에 DB 이름 parangsae로 복원(시각 = 다음 마이그레이션 0003 적용 시각, 복원 자체 기록 없음)', 141827, 170500, NULL, NULL),
('2026-10-16 16:18+09', 'server', 'migrate',
 'master 0003~0007(award·전처리 사유·program·no_body). detail 6소스 상세 본문 +20,319행(과학관 아카이브 2·광주·경기·울산·유성). reasons·classify 재계산. 코드 e281ea4', 141827, 190819, NULL, NULL),
('2026-10-16 16:19+09', 'server', 'dump',
 'parangsae 전체 pg_dump(16.13) → xz → 7z 5분할 전달. 기대값 program 86 · master_dedup 140,173 · master_clean 132,323',
 141827, 190819, 'parangsae-2026-10-16.dump.xz', '2a498cbd3e8b1e5756d039d3caf5d517babf3725cbb5746f335e0e8098b61c15'),
('2026-10-19 12:16+09', 'local', 'restore',
 '로컬 Docker DB에 parangsae로 복원. sha256·기대값 전부 일치. 로컬 bluebird_master raw 170,500행 = 같은 키·같은 내용으로 전부 포함(로컬에만 있는 행 0). 로컬 .env BB_DB_URL = 이 DB',
 141827, 190819, 'parangsae-2026-10-16.dump.xz', '2a498cbd3e8b1e5756d039d3caf5d517babf3725cbb5746f335e0e8098b61c15'),
('2026-10-19 21:40+09', 'local', 'drop',
 '로컬 bluebird_master 삭제(parangsae에 전부 포함). 백업 = .runtime/export/bluebird_master-2026-10-15.dump.xz', NULL, NULL, NULL, NULL);
