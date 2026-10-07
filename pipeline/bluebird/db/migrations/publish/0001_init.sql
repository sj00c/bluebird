-- DMZ 공개용 DB의 고정 스키마(bb_migrator가 적용).
-- publish 스키마 자체는 여기서 만들지 않는다. 매 주기 publisher가 체크섬 등록된 템플릿(publish_schema.sql)으로
-- publish_next를 만들고 RENAME으로 교체한다(bluebird.publish).
--   meta   : 교체 대상 밖. snapshot_log, 템플릿 등록
--   inbox  : 국민 이의 제기. portal은 INSERT만, 업무망 inbox_reader가 SELECT·DELETE(pull 후 삭제)
CREATE SCHEMA meta;
CREATE SCHEMA inbox;

CREATE TABLE meta.publish_template (
    version       text PRIMARY KEY,
    sha256        text NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE meta.snapshot_log (
    snapshot_id      bigint PRIMARY KEY,           -- core.publish_snapshot.id, 단조 증가
    template_version text NOT NULL REFERENCES meta.publish_template(version),
    created_at       timestamptz NOT NULL,
    applied_at       timestamptz NOT NULL DEFAULT now(),
    stats            jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE inbox.objection (
    id           bigserial PRIMARY KEY,
    idea_id      text NOT NULL CHECK (idea_id ~ '^ID-[0-9]{4}-[0-9a-f]{10}$'),
    kind         text NOT NULL CHECK (kind IN ('fact', 'cause', 'change', 'privacy', 'other')),
    body         text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 2000),
    submitted_at timestamptz NOT NULL DEFAULT now()
);

GRANT USAGE ON SCHEMA meta TO bb_publisher, bb_portal;
GRANT SELECT ON meta.publish_template TO bb_publisher;
GRANT SELECT, INSERT ON meta.snapshot_log TO bb_publisher;
GRANT SELECT ON meta.snapshot_log TO bb_portal;

GRANT USAGE ON SCHEMA inbox TO bb_portal, bb_inbox_reader;
GRANT INSERT ON inbox.objection TO bb_portal;
GRANT USAGE ON SEQUENCE inbox.objection_id_seq TO bb_portal;
GRANT SELECT, DELETE ON inbox.objection TO bb_inbox_reader;
