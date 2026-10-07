import { NextRequest, NextResponse } from "next/server";
import { listIdeas, PAGE_SIZE } from "@/lib/db";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const q = (sp.get("q") ?? "").trim().slice(0, 100) || undefined;
  const yearRaw = sp.get("year") ?? "";
  const year = /^\d{4}$/.test(yearRaw) ? Number(yearRaw) : undefined;
  const page = Math.max(1, Number(sp.get("page")) || 1);
  const { total, rows } = await listIdeas({ q, year, page });
  return NextResponse.json({ total, page, page_size: PAGE_SIZE, items: rows });
}
