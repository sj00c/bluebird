import "server-only";
import { cache } from "react";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";
import type { Me } from "./contracts";

export const TOKEN_COOKIE = "bb_console_token";

type Raw = { ok: boolean; status: number; data: unknown; detail: string };

async function raw(
  path: string,
  init?: RequestInit,
  authToken?: string,
): Promise<Raw> {
  const token = authToken ?? (await cookies()).get(TOKEN_COOKIE)?.value ?? "";
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init?.body && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  const res = await fetch(`${process.env.BB_API_URL ?? ""}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  let detail = "";
  if (!res.ok) {
    const d = (data as { detail?: unknown } | null)?.detail;
    if (typeof d === "string") detail = d;
    else if (Array.isArray(d)) {
      detail = d
        .map(
          (issue: { loc?: unknown[]; msg?: string }) =>
            `${issue.loc?.filter((part) => part !== "body").join(" · ") ?? "입력값"}: ${issue.msg ?? "값을 확인하세요."}`,
        )
        .join("\n");
    } else detail = `요청 실패 (${res.status})`;
  }
  return { ok: res.ok, status: res.status, data, detail };
}

/** 성공 시 JSON 반환. 401은 로그인, 403은 권한 안내, 404는 없음 화면. 그 외 오류는 detail 메시지로 던진다. */
function responseData<T>(r: Raw): T {
  if (r.status === 401)
    redirect("/login?error=" + encodeURIComponent("로그인이 필요합니다."));
  if (r.status === 403) redirect("/forbidden");
  if (r.status === 404) notFound();
  if (!r.ok) throw new Error(r.detail);
  return r.data as T;
}

export async function api<T = unknown>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  return responseData<T>(await raw(path, init));
}

// React cache is scoped to this server request. Key by the current cookie so
// a login action cannot reuse a result obtained before its token was changed.
const meResponse = cache((token: string) => raw("/api/me", undefined, token));

export async function requireMe(): Promise<Me> {
  const token = (await cookies()).get(TOKEN_COOKIE)?.value ?? "";
  return responseData<Me>(await meResponse(token));
}

/** 서버 액션용: 오류 throw 없이 메시지 반환. 401만 로그인 이동. */
export async function apiTry(
  path: string,
  init?: RequestInit,
): Promise<string | null> {
  let r: Raw;
  try {
    r = await raw(path, init);
  } catch {
    return "백엔드 API 연결 실패";
  }
  if (r.status === 401) redirect("/login");
  if (r.ok) return null;
  if (r.status === 403) return "작업 권한 없음 · 현재 역할 확인";
  if (r.status === 404) return "대상 자료 없음 · 삭제·운영 대상 제외 여부 확인";
  if (r.status === 422) return `입력 형식·필수 항목 오류 · ${r.detail}`;
  if (r.status === 409) return `저장 충돌 · ${r.detail}`;
  if (r.status >= 500)
    return "서버 처리 실패 · 입력 내용 유지 · 잠시 후 재시도";
  return r.detail;
}

/** 레이아웃용: 실패 → null. 리다이렉트 없음. */
export async function getMe(): Promise<Me | null> {
  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  if (!token) return null;
  try {
    const r = await meResponse(token);
    return r.ok ? responseData<Me>(r) : null;
  } catch {
    return null;
  }
}

export function post(body: unknown): RequestInit {
  return { method: "POST", body: JSON.stringify(body) };
}
