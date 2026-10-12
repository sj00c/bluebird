import "server-only";
import { pool } from "./connection";
import { cleanQuery, PAGE_SIZE, parsePage } from "./input";
import type { IdeaRow, PoolFilter } from "./types";

export async function listIdeas(opts: PoolFilter, pageSize = PAGE_SIZE) {
  const where: string[] = [];
  const args: unknown[] = [];
  if (opts.source) {
    args.push(opts.source);
    where.push(`i.source_id = $${args.length}`);
  }
  if (opts.verified)
    where.push(
      `EXISTS (SELECT 1 FROM publish.diagnosis d WHERE d.idea_id = i.id)`,
    );
  const q = cleanQuery(opts.q);
  if (q) {
    args.push(`%${q}%`);
    where.push(`i.title ILIKE $${args.length}`);
  }
  if (opts.year) {
    args.push(opts.year);
    where.push(`i.year = $${args.length}`);
  }
  const cond = where.length ? `WHERE ${where.join(" AND ")}` : "";
  const total = await pool.query<{ n: string }>(
    `SELECT count(*) AS n FROM publish.idea i ${cond}`,
    args,
  );
  args.push(pageSize, (parsePage(opts.page) - 1) * pageSize);
  const rows = await pool.query<
    IdeaRow & { cause: string | null; verdict: string | null; s: number | null }
  >(
    `SELECT i.*, s.name AS source_name, s.license, d.cause, t.verdict, t.s
       FROM publish.idea i JOIN publish.source s ON s.id = i.source_id
       LEFT JOIN publish.diagnosis d ON d.idea_id = i.id
       LEFT JOIN publish.timeliness t ON t.idea_id = i.id
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
export async function sourceList() {
  const r = await pool.query<{ id: string; name: string }>(
    `SELECT id, name FROM publish.source ORDER BY name`,
  );
  return r.rows;
}
