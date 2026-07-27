import { notFound } from "next/navigation";

import { DraftWorkspace, type DraftState } from "@/components/DraftWorkspace";
import { engineJson } from "@/lib/engine";

export default async function DraftPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await engineJson<DraftState>(`/api/drafts/${id}`);
  if (!res.ok || !res.data) notFound();
  return <DraftWorkspace state={res.data} />;
}
