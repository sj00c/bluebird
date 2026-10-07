import "server-only";
import { Pool } from "pg";

// DMZ 공개용 DB. bb_portal 계정: publish 읽기 + inbox 이의 INSERT만.
const globalForPool = globalThis as unknown as { bbPool?: Pool };

export const pool =
  globalForPool.bbPool ??
  new Pool({
    connectionString: process.env.PORTAL_DATABASE_URL,
    max: Number(process.env.PORTAL_DB_POOL_MAX ?? 10),
    statement_timeout: 5000,
  });
globalForPool.bbPool = pool;

export type IdeaRow = {
  id: string;
  source_id: string;
  source_name: string;
  license: string;
  contest_name: string;
  host_org: string;
  year: number | null;
  award: string | null;
  title: string;
  body: string | null;
  used_data: string[];
  category: string | null;
  source_url: string | null;
  card_kind: string | null;
  problem: string | null;
  solution: string | null;
  trace_status: string | null;
  external_search: string | null;
};

export const PAGE_SIZE = 50;

export async function listIdeas(opts: { q?: string; year?: number; page: number }) {
  const where: string[] = [];
  const args: unknown[] = [];
  if (opts.q) {
    args.push(`%${opts.q}%`);
    where.push(`i.title ILIKE $${args.length}`);
  }
  if (opts.year) {
    args.push(opts.year);
    where.push(`i.year = $${args.length}`);
  }
  const cond = where.length ? `WHERE ${where.join(" AND ")}` : "";
  const total = await pool.query<{ n: string }>(`SELECT count(*) AS n FROM publish.idea i ${cond}`, args);
  args.push(PAGE_SIZE, (opts.page - 1) * PAGE_SIZE);
  const rows = await pool.query<IdeaRow>(
    `SELECT i.*, s.name AS source_name, s.license
       FROM publish.idea i JOIN publish.source s ON s.id = i.source_id
       ${cond}
      ORDER BY i.year DESC NULLS LAST, i.id
      LIMIT $${args.length - 1} OFFSET $${args.length}`,
    args,
  );
  return { total: Number(total.rows[0].n), rows: rows.rows };
}

export async function getIdea(id: string): Promise<IdeaRow | null> {
  const r = await pool.query<IdeaRow>(
    `SELECT i.*, s.name AS source_name, s.license
       FROM publish.idea i JOIN publish.source s ON s.id = i.source_id
      WHERE i.id = $1`,
    [id],
  );
  return r.rows[0] ?? null;
}

export type DiagnosisRow = {
  cause: string;
  secondary: string | null;
  rationale: string | null;
  evidence_ids: string[];
};

export type ChangeRow = {
  id: string;
  kind: string;
  tier: string | null;
  occurred_at: string | null;
  registered_at: string | null;
  title: string;
  url: string | null;
  what_changed: string[];
  how_now: string | null;
  evidence_ids: string[];
};

export type TimelinessRow = {
  as_of: string | null;
  tech: number | null;
  data: number | null;
  regulation: number | null;
  policy: number | null;
  n_scored: number | null;
  s: number | null;
  verdict: string;
  resolve_condition: string | null;
  evidence_ids: string[];
};

export type EvidenceRow = {
  id: string;
  kind: string | null;
  url: string | null;
  title: string | null;
  excerpt: string | null;
};

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

// ---------------------------------------------------------------- 화면1: 이번 주 재조명
export type TopRow = {
  rank: number;
  idea_id: string;
  title: string;
  year: number | null;
  contest_name: string;
  s: number | null;
  verdict: string | null;
  cause: string | null;
  change_title: string | null;
  change_kind: string | null;
};

export async function getWeeklyTop(): Promise<{ week: string | null; rows: TopRow[] }> {
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

// ---------------------------------------------------------------- 화면2: 주제·공고 넣기
// pg_trgm 유사 조회(제목 가중). word_similarity 문턱은 이 트랜잭션에만 적용한다(SET LOCAL).
export const EXPLORE_LIMIT = 50;
export type ExploreIdea = {
  id: string;
  title: string;
  year: number | null;
  contest_name: string;
  award: string | null;
  score: number;
  cause: string | null;
  verdict: string | null;
  s: number | null;
};
export type ExploreAnnouncement = { id: string; title: string; org: string | null; apply_to: string | null; url: string };

export async function explore(q: string): Promise<{
  ideas: ExploreIdea[];
  causes: { cause: string; n: number }[];
  announcements: ExploreAnnouncement[];
}> {
  const client = await pool.connect();
  try {
    await client.query("BEGIN READ ONLY");
    await client.query("SET LOCAL pg_trgm.word_similarity_threshold = 0.3");
    const ideas = await client.query<ExploreIdea>(
      `WITH hit AS (
         SELECT i.id, i.title, i.year, i.contest_name, i.award,
                greatest(word_similarity($1, i.title), 0.7 * word_similarity($1, coalesce(i.body, ''))) AS score
           FROM publish.idea i
          WHERE $1 <% i.title OR $1 <% i.body
          ORDER BY score DESC, i.id
          LIMIT ${EXPLORE_LIMIT})
       SELECT h.id, h.title, h.year, h.contest_name, h.award, round(h.score::numeric, 2)::float AS score,
              d.cause, t.verdict, t.s
         FROM hit h
         LEFT JOIN publish.diagnosis d ON d.idea_id = h.id
         LEFT JOIN publish.timeliness t ON t.idea_id = h.id
        ORDER BY h.score DESC, h.id`,
      [q],
    );
    const ann = await client.query<ExploreAnnouncement>(
      `SELECT id, title, org, apply_to::text AS apply_to, url
         FROM publish.announcement
        WHERE $1 <% title
        ORDER BY word_similarity($1, title) DESC, id
        LIMIT 10`,
      [q],
    );
    await client.query("COMMIT");
    const counts = new Map<string, number>();
    for (const r of ideas.rows) if (r.cause) counts.set(r.cause, (counts.get(r.cause) ?? 0) + 1);
    const causes = [...counts].map(([cause, n]) => ({ cause, n })).sort((a, b) => b.n - a.n);
    return { ideas: ideas.rows, causes, announcements: ann.rows };
  } catch (e) {
    await client.query("ROLLBACK").catch(() => undefined);
    throw e;
  } finally {
    client.release();
  }
}

export const OBJECTION_KINDS = ["fact", "cause", "change", "privacy", "other"] as const;
export type ObjectionKind = (typeof OBJECTION_KINDS)[number];

// bb_portal은 inbox를 SELECT할 수 없으므로 RETURNING 없이 INSERT만 한다.
// 아이디어가 없으면 false.
export async function insertObjection(o: { ideaId: string; kind: ObjectionKind; body: string }): Promise<boolean> {
  const exists = await pool.query(`SELECT 1 FROM publish.idea WHERE id = $1`, [o.ideaId]);
  if (exists.rowCount === 0) return false;
  await pool.query(`INSERT INTO inbox.objection (idea_id, kind, body) VALUES ($1, $2, $3)`, [
    o.ideaId,
    o.kind,
    o.body,
  ]);
  return true;
}

export async function poolStats() {
  const r = await pool.query<{ ideas: string; sources: string; snapshot_at: Date | null }>(
    `SELECT (SELECT count(*) FROM publish.idea) AS ideas,
            (SELECT count(*) FROM publish.source) AS sources,
            (SELECT max(applied_at) FROM meta.snapshot_log) AS snapshot_at`,
  );
  const row = r.rows[0];
  return { ideas: Number(row.ideas), sources: Number(row.sources), snapshotAt: row.snapshot_at };
}
