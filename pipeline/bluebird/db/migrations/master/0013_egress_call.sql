-- 외부 호출 기록(정제 DB 전용). master 명령(detail·api·fill·extract)이 core 없이 이 표에 기록. 형식 = core.egress_call과 같음
CREATE TABLE egress_call (
    id             bigserial PRIMARY KEY,
    purpose        text NOT NULL CHECK (purpose IN ('collect', 'signal', 'trace', 'llm', 'source_check')),
    dest_host      text NOT NULL,
    path_template  text NOT NULL,
    source_ids     text[] NOT NULL DEFAULT '{}',
    fields_sent    text[] NOT NULL DEFAULT '{}',
    payload_sha256 text,
    bytes_out      integer,
    bytes_in       integer,
    http_status    integer,
    decision       text NOT NULL CHECK (decision IN ('allowed', 'blocked')),
    reason         text,
    tokens_in      integer,
    tokens_out     integer,
    created_at     timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE egress_call IS '[기록] 외부 호출 1건 = 1행(크롤링·API·LLM). 허용·차단 모두. 보낸 내용 원문은 저장 안 함(칸 이름·sha256만). 만든 곳: egress.py(Egress.for_master)';
COMMENT ON COLUMN egress_call.id IS '[기록] 일련번호';
COMMENT ON COLUMN egress_call.purpose IS '[기록] 목적: collect(수집·크롤링) · llm(AI 호출) 등';
COMMENT ON COLUMN egress_call.dest_host IS '[기록] 호출한 호스트(허용 목록 = egress.ALLOWED_HOSTS)';
COMMENT ON COLUMN egress_call.path_template IS '[기록] 호출 경로';
COMMENT ON COLUMN egress_call.source_ids IS '[기록] 내용을 보낸 소스 id';
COMMENT ON COLUMN egress_call.fields_sent IS '[기록] 보낸 칸 이름(<소스>.<칸>)';
COMMENT ON COLUMN egress_call.payload_sha256 IS '[기록] 보낸 본문 sha256';
COMMENT ON COLUMN egress_call.bytes_out IS '[기록] 보낸 바이트';
COMMENT ON COLUMN egress_call.bytes_in IS '[기록] 받은 바이트';
COMMENT ON COLUMN egress_call.http_status IS '[기록] 응답 코드';
COMMENT ON COLUMN egress_call.decision IS '[기록] allowed · blocked';
COMMENT ON COLUMN egress_call.reason IS '[기록] 차단·실패 사유';
COMMENT ON COLUMN egress_call.tokens_in IS '[기록] LLM 입력 토큰';
COMMENT ON COLUMN egress_call.tokens_out IS '[기록] LLM 출력 토큰';
COMMENT ON COLUMN egress_call.created_at IS '[기록] 호출 시각';
