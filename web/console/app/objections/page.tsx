import { api, requireMe } from "@/lib/api";
import type { Objections } from "@/lib/contracts";
import { OBJECTION_STATUS } from "@/lib/labels";
import { ObjectionWorkbench } from "@/features/objections/objection-workbench";

export const dynamic = "force-dynamic";

export default async function ObjectionsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const sp = await searchParams;
  const status =
    sp.status && Object.hasOwn(OBJECTION_STATUS, sp.status)
      ? sp.status
      : "open";
  const [{ items }, me] = await Promise.all([
    api<Objections>(`/api/objections?status=${status}`),
    requireMe(),
  ]);
  return (
    <ObjectionWorkbench
      items={items}
      status={status}
      canResolve={me.roles.includes("reviewer")}
    />
  );
}
