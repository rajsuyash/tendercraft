import {
  Closing, Features, Footer, Header, Hero, PipelineVisual, PortalTicker, Pricing, Problems,
  ProductShot, Sectors, Workflow,
} from "@/components/marketing/Sections";
import { createClient } from "@/lib/supabase/server";

/**
 * `/` — the public landing page.
 *
 * Replaces the old redirect to /dashboard. The only session-dependent bit is the header CTA:
 * a signed-in visitor gets "Dashboard" instead of "Sign in", so the front door does not send
 * someone who is already authenticated through a login round trip.
 */
export default async function LandingPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <>
      <Header signedIn={Boolean(user)} />
      <main>
        <Hero />
        <PipelineVisual />
        <PortalTicker />
        <Problems />
        <ProductShot />
        <Features />
        <Workflow />
        <Sectors />
        <Pricing />
        <Closing />
      </main>
      <Footer />
    </>
  );
}
