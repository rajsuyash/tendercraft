import { notFound } from "next/navigation";

import { DocumentMatrix, type DocumentMatrixState } from "@/components/DocumentMatrix";
import { engineJson, getTender } from "@/lib/engine";

export default async function DocumentsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [det, matrix] = await Promise.all([
    getTender(id),
    engineJson<DocumentMatrixState>(`/api/tenders/${id}/documents`),
  ]);
  if (!det.ok || !det.data) notFound();

  const state: DocumentMatrixState = matrix.data ?? {
    requirements: [], bids: [], frozen: false, unresolved_files: 0, complete: 0, total_cells: 0,
  };
  return <DocumentMatrix tenderId={id} state={state} />;
}
