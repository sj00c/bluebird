import { api, requireMe } from "@/lib/api";
import type { Overview } from "@/lib/contracts";
import { OverviewWorkbench } from "@/features/overview/overview-workbench";

export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const [overview, me] = await Promise.all([
    api<Overview>("/api/overview"),
    requireMe(),
  ]);
  return <OverviewWorkbench overview={overview} me={me} />;
}
