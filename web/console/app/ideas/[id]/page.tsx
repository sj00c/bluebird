import { api, requireMe } from "@/lib/api";
import type { Changes, Detail } from "@/lib/contracts";
import { IdeaWorkspace } from "@/features/ideas/idea-workspace";

export const dynamic = "force-dynamic";

export default async function IdeaPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ change_q?: string }>;
}) {
  const { id } = await params;
  const { change_q } = await searchParams;
  const [detail, me] = await Promise.all([
    api<Detail>(`/api/ideas/${encodeURIComponent(id)}`),
    requireMe(),
  ]);
  const canAuthor = me.roles.includes("reviewer") && !detail.idea.withheld_at;
  const changeQuery = (change_q ?? "").slice(0, 200);
  const changes = canAuthor
    ? await api<Changes>(
        `/api/changes?${new URLSearchParams({ q: changeQuery, limit: "50" })}`,
      )
    : { items: [] };

  return (
    <IdeaWorkspace
      detail={detail}
      me={me}
      canAuthor={canAuthor}
      changeQuery={changeQuery}
      changes={changes}
    />
  );
}
