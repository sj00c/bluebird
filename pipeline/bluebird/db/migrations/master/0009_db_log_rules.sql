-- db_log 적는 방식. 서버(git 없음)도 DB 주석으로 같은 규칙을 본다. 기존 행은 그대로(NOT VALID = 새 행부터 검사).

ALTER TABLE db_log
    ADD CONSTRAINT db_log_action CHECK (action IN ('dump', 'restore', 'migrate', 'files', 'api', 'detail', 'refine',
                                                   'fill', 'reasons', 'classify', 'drop', 'note')) NOT VALID,
    ADD CONSTRAINT db_log_place CHECK (place ~ '^[a-z0-9][a-z0-9_-]*$') NOT VALID,
    ADD CONSTRAINT db_log_note CHECK (length(btrim(note)) > 0) NOT VALID,
    ADD CONSTRAINT db_log_file CHECK (action NOT IN ('dump', 'restore') OR file IS NOT NULL) NOT VALID,
    ADD CONSTRAINT db_log_sha CHECK ((action <> 'restore' OR sha256 IS NOT NULL) AND (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$')) NOT VALID;

-- 쌓기만 한다. 고칠 일 = 새 행(action note, "정정 #<id>: …")
CREATE FUNCTION db_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'db_log = 추가만(정정은 action note 새 행: "정정 #<id>: …")';
END $$;
CREATE TRIGGER db_log_append_only BEFORE UPDATE OR DELETE ON db_log FOR EACH ROW EXECUTE FUNCTION db_log_append_only();
CREATE TRIGGER db_log_no_truncate BEFORE TRUNCATE ON db_log FOR EACH STATEMENT EXECUTE FUNCTION db_log_append_only();

COMMENT ON TABLE db_log IS
'DB 작업 기록. 1행 = 작업 1건, 추가만(수정·삭제 불가). 덤프에 같이 실려 간다.
이관 순서(보내는 쪽 → 받는 쪽):
  a) 보내는 쪽: dump 행 먼저(--file <만들 파일 이름>, sha256 없음) → pg_dump. 그래야 이 행이 덤프에 실린다
  b) 받는 쪽: 새 이름 DB로 복원 → restore 행(--file, sha256 필수) → 기존 DB 기록 옮김(bluebird master log --merge-from <기존 DB>) → 기존 DB 정리(drop 행)
적는 법:
1) 코드 있음: bluebird master log --action <작업> --note "<내용>" [--file <덤프>] [--at <시각>]. master 명령·migrate = 자동
2) 코드 없음(SQL):
   INSERT INTO db_log (place, action, note, master, raw, file, sha256)
   VALUES (''server'', ''restore'', ''<내용>'', (SELECT count(*) FROM master), (SELECT count(*) FROM raw), ''<파일>'', ''<sha256>'');
note 형식(작업별):
  dump    = "<DB> 전체 pg_dump(<버전>) → <압축·분할> → <전달 경로>"
  restore = "<파일> → <DB 이름>(<호스트>). 확인: sha256·행 수 <일치/불일치>"
  drop    = "<대상> 삭제. 이유: <이유>. 백업: <파일 또는 없음>"
  note    = "<한 일>. 이유: <이유>" / 정정 = "정정 #<id>: <바른 내용>"
  자동(migrate·files·api·detail·refine·fill·reasons·classify) = 옵션 + 소스별 상태·숫자, 손으로 적지 않음
공통: 한 줄, 문장 끝 마침표 없이 "· "로 잇기 가능, 숫자는 쉼표 없이, 시각 추정이면 note에 "(시각 추정: <근거>)"';
COMMENT ON COLUMN db_log.at IS '작업 시각. 기본 = 기록 시각. 지난 일을 나중에 적을 때만 지정 + note에 (시각 추정: 근거)';
COMMENT ON COLUMN db_log.place IS '어디서. 소문자·숫자·-_ (local, server). 기계마다 고정: .env BB_LOG_PLACE';
COMMENT ON COLUMN db_log.action IS 'dump · restore · migrate · files · api · detail · refine · fill · reasons · classify · drop · note';
COMMENT ON COLUMN db_log.note IS '작업별 형식 = 표 주석(COMMENT ON TABLE db_log)';
COMMENT ON COLUMN db_log.master IS '기록 시점 master 행 수(자동)';
COMMENT ON COLUMN db_log.raw IS '기록 시점 raw 행 수(자동)';
COMMENT ON COLUMN db_log.file IS '덤프 파일 이름. dump·restore 필수';
COMMENT ON COLUMN db_log.sha256 IS '그 파일 sha256(소문자 64자). restore 필수, dump = 덤프 전에 적으므로 비움';
