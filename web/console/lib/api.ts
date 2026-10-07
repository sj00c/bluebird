import "server-only";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";

export const TOKEN_COOKIE = "bb_console_token";

export type Me = { user: string; roles: string[] };

type Raw = { ok: boolean; status: number; data: unknown; detail: string };

async function raw(path: string, init?: RequestInit): Promise<Raw> {
  const token = (await cookies()).get(TOKEN_COOKIE)?.value ?? "";
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init?.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const res = await fetch(`${process.env.BB_API_URL ?? ""}${path}`, { ...init, headers, cache: "no-store" });
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  let detail = "";
  if (!res.ok) {
    const d = (data as { detail?: unknown } | null)?.detail;
    detail = typeof d === "string" ? d : d !== undefined ? JSON.stringify(d) : `요청 실패 (${res.status})`;
  }
  return { ok: res.ok, status: res.status, data, detail };
}

/** 성공 시 JSON 반환. 401은 로그인, 403은 권한 안내, 404는 없음 화면. 그 외 오류는 detail 메시지로 던진다. */
export async function api<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const r = await raw(path, init);
  if (r.status === 401) redirect("/login?error=" + encodeURIComponent("로그인이 필요합니다."));
  if (r.status === 403) redirect("/forbidden");
  if (r.status === 404) notFound();
  if (!r.ok) throw new Error(r.detail);
  return r.data as T;
}

/** 서버 액션용: 오류를 던지지 않고 메시지로 돌려준다. 401만 로그인으로 이동. */
export async function apiTry(path: string, init?: RequestInit): Promise<string | null> {
  let r: Raw;
  try {
    r = await raw(path, init);
  } catch {
    return "백엔드 API에 연결하지 못했습니다.";
  }
  if (r.status === 401) redirect("/login");
  return r.ok ? null : r.detail;
}

/** 레이아웃용: 실패하면 null. 리다이렉트하지 않는다. */
export async function getMe(): Promise<Me | null> {
  if (!(await cookies()).get(TOKEN_COOKIE)?.value) return null;
  try {
    const r = await raw("/api/me");
    return r.ok ? (r.data as Me) : null;
  } catch {
    return null;
  }
}

export function post(body: unknown): RequestInit {
  return { method: "POST", body: JSON.stringify(body) };
}
