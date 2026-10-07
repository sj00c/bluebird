-- 이의 행마다 DMZ가 만드는 uuid. 업무망 pull은 이것으로 중복을 판정한다(DB를 다시 만들어 id가 겹쳐도 안전).
ALTER TABLE inbox.objection ADD COLUMN uid uuid NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE inbox.objection ADD CONSTRAINT objection_uid_key UNIQUE (uid);
