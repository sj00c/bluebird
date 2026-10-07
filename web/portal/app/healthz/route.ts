import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    await pool.query("SELECT 1 FROM publish.snapshot_log LIMIT 1");
    return NextResponse.json({ status: "ok" });
  } catch {
    return NextResponse.json({ status: "db_unavailable" }, { status: 503 });
  }
}
