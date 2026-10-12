import "server-only";
import { Pool } from "pg";

declare global {
  // Preserve the pool across development module reloads.
  var bbPool: Pool | undefined;
}

// bb_portal can read published records and insert inbox objections only.
export const pool =
  globalThis.bbPool ??
  new Pool({
    connectionString: process.env.PORTAL_DATABASE_URL,
    max: Number(process.env.PORTAL_DB_POOL_MAX ?? 10),
    statement_timeout: 5000,
  });
globalThis.bbPool = pool;
