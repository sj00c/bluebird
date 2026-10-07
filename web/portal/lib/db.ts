import "server-only";
import { Pool } from "pg";

// 공개존 DB(publish 스키마) 읽기 전용 계정. 쓰기 권한이 없다.
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

export async function poolStats() {
  const r = await pool.query<{ ideas: string; sources: string; snapshot_at: Date | null }>(
    `SELECT (SELECT count(*) FROM publish.idea) AS ideas,
            (SELECT count(*) FROM publish.source) AS sources,
            (SELECT max(created_at) FROM publish.snapshot_log) AS snapshot_at`,
  );
  const row = r.rows[0];
  return { ideas: Number(row.ideas), sources: Number(row.sources), snapshotAt: row.snapshot_at };
}
