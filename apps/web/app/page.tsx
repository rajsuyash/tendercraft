import { redirect } from "next/navigation";

export default function Home() {
  // Middleware sends unauthenticated users to /login; authed users land on the dashboard.
  redirect("/dashboard");
}
