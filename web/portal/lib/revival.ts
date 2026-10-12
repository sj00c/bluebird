import "server-only";
import { pool } from "./connection";
import type {
  ChangeRow,
  DiagnosisRow,
  EvidenceRow,
  TimelinessListRow,
  TimelinessRow,
  TopRow,
} from "./types";

export async function getRevival(id: string): Promise<{
  diagnosis: DiagnosisRow | null;
  changes: ChangeRow[];
  timeliness: TimelinessRow | null;
  evidence: EvidenceRow[];
}> {
  const [d, c, t] = await Promise.all([
    pool.query<DiagnosisRow>(
      `SELECT cause, secondary, rationale, COALESCE(evidence_ids, '{}')::text[] AS evidence_ids
         FROM publish.diagnosis WHERE idea_id = $1`,
      [id],
    ),
    pool.query<ChangeRow>(
      `SELECT id::text AS id, kind, tier, occurred_at::text AS occurred_at, registered_at::text AS registered_at,
              title, url,
              COALESCE(what_changed, '{}') AS what_changed, how_now,
              COALESCE(evidence_ids, '{}')::text[] AS evidence_ids
         FROM publish.change WHERE idea_id = $1
        ORDER BY occurred_at DESC NULLS LAST, id`,
      [id],
    ),
    pool.query<TimelinessRow>(
      `SELECT as_of::text AS as_of, tech, data, regulation, policy, n_scored, s, verdict, resolve_condition,
              COALESCE(evidence_ids, '{}')::text[] AS evidence_ids
         FROM publish.timeliness WHERE idea_id = $1`,
      [id],
    ),
  ]);
  const diagnosis = d.rows[0] ?? null;
  const changes = c.rows;
  const timeliness = t.rows[0] ?? null;
  const ids = new Set<string>(diagnosis?.evidence_ids ?? []);
  for (const ch of changes) for (const e of ch.evidence_ids) ids.add(e);
  for (const e of timeliness?.evidence_ids ?? []) ids.add(e);
  let evidence: EvidenceRow[] = [];
  if (ids.size > 0) {
    const e = await pool.query<EvidenceRow>(
      `SELECT id::text AS id, kind, url, title, excerpt
         FROM publish.evidence WHERE id = ANY($1::bigint[]) ORDER BY id`,
      [[...ids]],
    );
    evidence = e.rows;
  }
  return { diagnosis, changes, timeliness, evidence };
}
export async function getWeeklyTop(): Promise<{
  week: string | null;
  rows: TopRow[];
}> {
  const r = await pool.query<TopRow & { week: string }>(
    `SELECT w.week::text AS week, w.rank, w.idea_id, i.title, i.year, i.contest_name, w.s,
            t.verdict, d.cause, c.title AS change_title, c.kind AS change_kind
       FROM publish.weekly_top w
       JOIN publish.idea i ON i.id = w.idea_id
       LEFT JOIN publish.timeliness t ON t.idea_id = w.idea_id
       LEFT JOIN publish.diagnosis d ON d.idea_id = w.idea_id
       LEFT JOIN LATERAL (SELECT title, kind FROM publish.change x WHERE x.idea_id = w.idea_id
                           ORDER BY x.occurred_at DESC, x.id LIMIT 1) c ON true
      ORDER BY w.rank
      LIMIT 20`,
  );
  return { week: r.rows[0]?.week ?? null, rows: r.rows };
}
export async function timelinessList(): Promise<TimelinessListRow[]> {
  const r = await pool.query<TimelinessListRow>(
    `SELECT t.idea_id, i.title, i.year, i.contest_name, d.cause,
            t.as_of::text AS as_of, t.tech, t.data, t.regulation, t.policy, t.n_scored, t.s, t.verdict,
            t.resolve_condition, COALESCE(t.evidence_ids, '{}')::text[] AS evidence_ids
       FROM publish.timeliness t
       JOIN publish.idea i ON i.id = t.idea_id
       LEFT JOIN publish.diagnosis d ON d.idea_id = t.idea_id
      ORDER BY t.s DESC NULLS LAST, t.idea_id`,
  );
  return r.rows;
}
