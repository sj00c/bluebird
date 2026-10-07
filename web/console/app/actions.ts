"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { apiTry, post, TOKEN_COOKIE } from "@/lib/api";

function str(f: FormData, k: string): string {
  const v = f.get(k);
  return typeof v === "string" ? v.trim() : "";
}

function back(path: string, error: string | null, ok = "저장했습니다."): never {
  const q = new URLSearchParams(error ? { error } : { ok });
  redirect(`${path}${path.includes("?") ? "&" : "?"}${q.toString()}`);
}

export async function login(formData: FormData) {
  const token = str(formData, "token");
  if (!token) redirect("/login?error=" + encodeURIComponent("접근 토큰을 입력하세요."));
  const jar = await cookies();
  jar.set(TOKEN_COOKIE, token, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production" && process.env.CONSOLE_SECURE_COOKIE === "1",
    path: "/",
    maxAge: 60 * 60 * 12,
  });
  const err = await apiTry("/api/me");
  if (err) {
    jar.delete(TOKEN_COOKIE);
    redirect("/login?error=" + encodeURIComponent("접근 토큰을 확인할 수 없습니다."));
  }
  redirect("/");
}

export async function logout() {
  (await cookies()).delete(TOKEN_COOKIE);
  redirect("/login");
}

export async function review(formData: FormData) {
  const id = str(formData, "idea_id");
  const round = str(formData, "round");
  const decision = str(formData, "decision");
  const note = str(formData, "note");
  const path = `/ideas/${encodeURIComponent(id)}`;
  if (!["final", "expert", "audit"].includes(round) || !["approve", "reject"].includes(decision)) {
    back(path, "잘못된 요청입니다.");
  }
  if (decision === "reject" && !note) back(path, "반려 사유를 입력하세요.");
  const err = await apiTry(`/api/ideas/${encodeURIComponent(id)}/review`, post({ round, decision, note }));
  back(path, err, decision === "approve" ? "승인을 기록했습니다." : "반려를 기록했습니다.");
}

export async function code(formData: FormData) {
  const id = str(formData, "idea_id");
  const c = str(formData, "code");
  const note = str(formData, "note");
  if (!/^[TDRMCOU]$/.test(c)) back("/coding", "막힌 이유를 선택하세요.");
  const err = await apiTry(`/api/coding/${encodeURIComponent(id)}`, post({ code: c, note }));
  back("/coding", err, "코드를 저장했습니다.");
}

export async function resolveObjection(formData: FormData) {
  const id = str(formData, "objection_id");
  const decision = str(formData, "decision");
  const resolution = str(formData, "resolution");
  const withhold = formData.get("withhold") === "on";
  if (!/^\d+$/.test(id)) back("/objections", "잘못된 요청입니다.");
  if (!["accepted", "rejected"].includes(decision)) back("/objections", "처리 결정을 선택하세요.");
  if (!resolution) back("/objections", "처리 내용을 입력하세요.");
  const err = await apiTry(`/api/objections/${id}/resolve`, post({ decision, resolution, withhold }));
  back("/objections", err, "이의를 처리했습니다.");
}
