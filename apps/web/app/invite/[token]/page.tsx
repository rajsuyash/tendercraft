import { AcceptInvite } from "@/components/AcceptInvite";

// Redeeming an invitation is the one authenticated action that happens BEFORE the user has
// any workspace, so this page lives outside the (app) shell — that layout would otherwise
// bounce them for having no workspace to render.
export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <AcceptInvite token={token} />;
}
