-- 근거 확인 안 된 AI 가공 = 제외 사유 unverified → exclude_reasons = '{}' 하나로 사용 대상. 값 계산 = bluebird master reasons
ALTER TABLE master DROP CONSTRAINT master_exclude_reasons;
ALTER TABLE master ADD CONSTRAINT master_exclude_reasons CHECK (exclude_reasons <@ ARRAY['duplicate', 'no_body',
    'attachment_only', 'title_repeat', 'short_title_body', 'idea_thin', 'complaint', 'abusive', 'off_topic', 'unverified']);

COMMENT ON TABLE master IS '[정제] 최종 표. 1행 = 아이디어 1건. 행 삭제 없음, 사용 대상 = exclude_reasons = ''{}''. 만든 곳: bluebird master refine(refine.py·programs.py) → reasons(dedup.py·quality.py) → extract(extract.py) → reasons';
COMMENT ON COLUMN master.exclude_reasons IS '[계산] 제외 사유 코드. 빈 배열 = 사용 대상(이 칸 하나로 거름). 만든 곳: bluebird master reasons(dedup.py·quality.py). 코드 뜻 —
duplicate = 중복(대표 아닌 행). 같은 글: 제목+본문 완전 일치(공백 무시, 대구 참여예산 제외) → 먼저 낸 것을 남김 / 같은 장소: 제목+지번 일치(대구) → 나중 것을 남김 / 같은 출품작: 공모전 행 중 대회·제도명+제목(6자 이상)+수상 등급 일치, 연도 차 1 이내, 출처 다름 → 본문 긴 것을 남김
no_body = 본문 내용 0자(비었거나 섹션 라벨·공백·기호뿐)
attachment_only = 본문에서 섹션 라벨·첨부/별첨/붙임 참조 문구를 빼면 0자
title_repeat = 본문에서 제목을 빼면 0자
short_title_body = 제목 내용 5자 이하이고 본문 내용 10자 이하
idea_thin · complaint · abusive · off_topic = AI 판정(label) 그대로: 빈약 · 불만·항의뿐 · 욕설·비방 중심 · 광고·무의미
unverified = AI 판정 idea지만 근거 구절이 원문에 없음(verified 거짓)
(내용 글자 수 = 섹션 라벨 [..]·공백·기호 뺀 글자 수)';
