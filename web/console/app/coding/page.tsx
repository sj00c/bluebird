import { api } from "@/lib/api";
import type { Coding } from "@/lib/contracts";
import { CodingWorkbench } from "@/features/coding/coding-workbench";

export const dynamic = "force-dynamic";

export default async function CodingPage() {
  const coding = await api<Coding>("/api/coding");
  return <CodingWorkbench coding={coding} />;
}
