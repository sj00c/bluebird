import type { ChangeRow, EvidenceRow, TimelinessRow } from "@/lib/types";
import { AXES, CHANGE_KIND, tierText } from "@/lib/labels";
import { Verdict } from "../../components";
import { Evidence } from "./evidence";

export function RevivalReview({
  timeliness,
  changes,
  evidence,
}: {
  timeliness: TimelinessRow | null;
  changes: ChangeRow[];
  evidence: ReadonlyMap<string, EvidenceRow>;
}) {
  return (
    <section className="card" aria-label="변화와 현재의 조건">
      <h2 id="timeliness">
        시의성 재평가
        {timeliness?.as_of && <small>{timeliness.as_of} 기준</small>}
      </h2>
      {timeliness ? (
        <>
          <div className="score">
            <b>
              {timeliness.s != null ? Number(timeliness.s).toFixed(1) : "-"}
            </b>
            <span>/ 5.0</span>
            <Verdict value={timeliness.verdict} />
          </div>
          <p className="note">
            채점 축:{" "}
            {timeliness.n_scored != null
              ? `${timeliness.n_scored} / 4`
              : "미기록"}
            {" · "}미채점 ≠ 0점
          </p>
          {AXES.map((axis) => {
            const value = timeliness[axis.key];
            return (
              <div className="bar" key={axis.key}>
                <div>{axis.label}</div>
                <div className="tr" aria-hidden="true">
                  <div
                    className="fl"
                    style={{
                      width: value != null ? `${(value / 5) * 100}%` : 0,
                    }}
                  />
                </div>
                <div className={value != null ? "v" : "v na"}>
                  {value != null ? Number(value).toFixed(1) : "미채점"}
                </div>
              </div>
            );
          })}
          {timeliness.resolve_condition && (
            <details className="more">
              <summary>충족 조건</summary>
              <div className="desc">{timeliness.resolve_condition}</div>
            </details>
          )}
          {timeliness.evidence_ids.length > 0 && (
            <details className="more">
              <summary>채점 근거 {timeliness.evidence_ids.length}건</summary>
              <Evidence ids={timeliness.evidence_ids} byId={evidence} />
            </details>
          )}
        </>
      ) : (
        <div className="pending">평가 대기 · 진단 검증 후 채점</div>
      )}
      <h2 id="changes">확인된 변화</h2>
      {changes.length ? (
        <ul className="why">
          {changes.map((change) => (
            <li key={change.id}>
              <span className="tag g">
                {CHANGE_KIND[change.kind] ?? change.kind}
              </span>{" "}
              {change.url ? (
                <a href={change.url} target="_blank" rel="noopener noreferrer">
                  <strong>{change.title}</strong>
                </a>
              ) : (
                <strong>{change.title}</strong>
              )}
              <p className="muted">
                {tierText(change) ??
                  (change.occurred_at &&
                    `${change.kind === "law_effective" ? "시행" : "발생"} ${change.occurred_at}`)}
              </p>
              <details className="more">
                <summary>변화 내용·적용 조건·근거</summary>
                {change.what_changed.length > 0 && (
                  <ul className="checklist">
                    {change.what_changed.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                )}
                {change.how_now && (
                  <dl className="record-facts">
                    <div>
                      <dt>적용 조건</dt>
                      <dd>{change.how_now}</dd>
                    </div>
                  </dl>
                )}
                <Evidence
                  ids={change.evidence_ids.filter(
                    (id) => !change.url || evidence.get(id)?.url !== change.url,
                  )}
                  byId={evidence}
                />
              </details>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">확인된 변화 없음</p>
      )}
    </section>
  );
}
