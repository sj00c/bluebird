import { api, requireMe } from "@/lib/api";
import type { Queue } from "@/lib/contracts";
import { QUEUE_STAGES } from "@/lib/labels";
import { QueueWorkbench } from "@/features/queue/queue-workbench";

export const dynamic = "force-dynamic";

export default async function QueuePage({
  searchParams,
}: {
  searchParams: Promise<{ stage?: string; q?: string; offset?: string }>;
}) {
  const sp = await searchParams;
  const stage = QUEUE_STAGES.find((item) => item === sp.stage) ?? "raw";
  const query = (sp.q ?? "").slice(0, 200);
  const parsed = Number(sp.offset ?? 0);
  const offset = Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : 0;
  const params = new URLSearchParams({
    stage,
    q: query,
    limit: "50",
    offset: String(offset),
  });
  const [queue, me] = await Promise.all([
    api<Queue>(`/api/queue?${params}`),
    requireMe(),
  ]);
  return (
    <QueueWorkbench
      queue={queue}
      stage={stage}
      query={query}
      canAuthor={me.roles.includes("reviewer")}
    />
  );
}
