"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { apiTry, getMe, post, TOKEN_COOKIE } from "@/lib/api";
import type { ActionState } from "@/lib/action-state";

function str(f: FormData, k: string): string {
  const v = f.get(k);
  return typeof v === "string" ? v.trim() : "";
}
async function allowed(role: string): Promise<boolean> {
  const me = await getMe();
  if (!me)
    redirect("/login?error=" + encodeURIComponent("인증 만료 · 재로그인 필요"));
  return me.roles.includes(role);
}
async function save(
  path: string,
  body: unknown,
  page: string,
  ok: string,
): Promise<ActionState> {
  const error = await apiTry(path, post(body));
  if (error) return { error };
  revalidatePath(page);
  revalidatePath("/");
  revalidatePath("/overview");
  return { ok };
}
const denied = { error: "작업 권한 없음 · 현재 역할 확인" };

export async function login(formData: FormData) {
  const token = str(formData, "token");
  if (!token) redirect("/login?error=" + encodeURIComponent("접근 토큰 필수"));
  const jar = await cookies();
  jar.set(TOKEN_COOKIE, token, {
    httpOnly: true,
    sameSite: "strict",
    secure:
      process.env.NODE_ENV === "production" &&
      process.env.CONSOLE_SECURE_COOKIE === "1",
    path: "/",
    maxAge: 60 * 60 * 12,
  });
  const me = await getMe();
  if (!me) {
    jar.delete(TOKEN_COOKIE);
    redirect(
      "/login?error=" +
        encodeURIComponent("로그인 실패 · 토큰 유효성·API 연결 확인"),
    );
  }
  redirect(
    me.roles.some((r) => ["reviewer", "expert", "auditor"].includes(r))
      ? "/overview"
      : "/coding",
  );
}
export async function logout() {
  (await cookies()).delete(TOKEN_COOKIE);
  redirect("/login");
}
export async function review(
  _state: ActionState,
  f: FormData,
): Promise<ActionState> {
  const id = str(f, "idea_id"),
    round = str(f, "round"),
    decision = str(f, "decision"),
    note = str(f, "note");
  const role = (
    { final: "reviewer", expert: "expert", audit: "auditor" } as Record<
      string,
      string
    >
  )[round];
  if (!role || !["approve", "reject"].includes(decision))
    return { error: "검토 요청 오류 · 라운드·결정 확인" };
  if (!(await allowed(role))) return denied;
  if (decision === "reject" && !note) return { error: "반려 사유 필수" };
  return save(
    `/api/ideas/${encodeURIComponent(id)}/review`,
    { round, decision, note },
    `/ideas/${encodeURIComponent(id)}`,
    decision === "approve" ? "승인 기록 완료" : "반려 기록 완료",
  );
}
export async function code(
  _state: ActionState,
  f: FormData,
): Promise<ActionState> {
  if (!(await allowed("coder"))) return denied;
  const id = str(f, "idea_id"),
    c = str(f, "code"),
    note = str(f, "note");
  if (!/^[TDRMCOU]$/.test(c)) return { error: "원인 코드 선택 필수" };
  return save(
    `/api/coding/${encodeURIComponent(id)}`,
    { code: c, note },
    "/coding",
    "코드 저장 완료 · 다른 코더에게 비공개",
  );
}
export async function author(
  _state: ActionState,
  f: FormData,
): Promise<ActionState> {
  if (!(await allowed("reviewer"))) return denied;
  const id = str(f, "idea_id"),
    kind = str(f, "kind");
  let body: unknown;
  if (kind === "trace") {
    const status = str(f, "status");
    if (
      !["realized", "pivot", "similar_unlinked", "award_only", "none"].includes(
        status,
      )
    )
      return { error: "흔적 판정 선택 필수" };
    if (status !== "none" && !str(f, "url"))
      return {
        error: "흔적 발견 판정: 확인 가능한 근거 URL 필수",
      };
    body = {
      result: status === "none" ? "none" : "found",
      status,
      url: str(f, "url") || undefined,
      note: str(f, "note"),
    };
  } else if (kind === "diagnosis") {
    const urls = f.getAll("evidence_url"),
      excerpts = f.getAll("evidence_excerpt");
    body = {
      cause: str(f, "cause"),
      secondary: str(f, "secondary") || null,
      rationale: str(f, "rationale"),
      evidence: urls
        .map((url, i) => ({
          url: String(url).trim(),
          excerpt: String(excerpts[i] ?? "").trim() || null,
        }))
        .filter((e) => e.url),
    };
  } else if (kind === "match") {
    body = {
      change_id: str(f, "change_id"),
      verdict: str(f, "verdict"),
      what_changed: str(f, "what_changed")
        .split(/\r?\n/)
        .map((v) => v.trim())
        .filter(Boolean),
      how_now: str(f, "how_now"),
    };
  } else if (kind === "score") {
    const scores: Record<string, number | null> = {},
      evidence: Record<string, string> = {};
    for (const axis of ["tech", "data", "regulation", "policy"]) {
      const value = str(f, axis);
      scores[axis] = value === "" ? null : Number(value);
      if (
        value &&
        (!Number.isInteger(scores[axis]) ||
          Number(value) < 0 ||
          Number(value) > 5)
      )
        return { error: "점수 형식: 0~5 정수 또는 미평가" };
      const url = str(f, `${axis}_evidence`);
      if (url) evidence[axis] = url;
    }
    body = { scores, evidence, as_of: str(f, "as_of") || undefined };
  } else return { error: "지원하지 않는 작성 요청" };
  return save(
    `/api/ideas/${encodeURIComponent(id)}/${kind}`,
    body,
    `/ideas/${encodeURIComponent(id)}`,
    "저장 완료 · 재검토·승인 필요 · 자동 공개 없음",
  );
}
