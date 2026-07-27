import { notFound } from "next/navigation";

import { FrameworkEditor } from "@/components/FrameworkEditor";
import { getTender } from "@/lib/engine";

/** The published framework: what every bid will be judged against, and the point after which
 *  it can no longer change. */
export default async function FrameworkPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await getTender(id);
  if (!res.ok || !res.data) notFound();
  const { tender, criteria, unconfirmed } = res.data;

  return (
    <FrameworkEditor
      tenderId={id}
      locked={!!tender.framework_locked_at}
      lockedAt={tender.framework_locked_at}
      unconfirmed={unconfirmed}
      criteria={criteria}
    />
  );
}
