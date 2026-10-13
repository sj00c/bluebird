-- 외부 공유 가능 여부 = 소스마다 사람이 적는 값(TOML share). 라이선스 문구 추정 없음.
-- 공유 xlsx 1파일에 전체 수록, ideas.share 열로 구분. 공개(public_ok)·LLM 반출(export_grade)과 별개.

ALTER TABLE core.source ADD COLUMN share_ok boolean NOT NULL DEFAULT false;
