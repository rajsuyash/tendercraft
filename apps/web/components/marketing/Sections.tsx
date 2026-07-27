import Image from "next/image";
import Link from "next/link";

import {
  CLAIMS, CLOSING, FEATURES, FOOTER, HERO, NAV, PIPELINE, PROBLEMS, SECTORS, WORKFLOW,
} from "./content";
import { Icon, type IconName } from "./Icon";
import { Marquee, Odometer, Reveal, Spotlight } from "./Motion";

/** Portals the product reads. Concrete and verifiable — the honest substitute for the
 *  customer-logo carousel this pattern normally opens with, which we cannot populate. */
const PORTALS = [
  "GeM Government e-Marketplace", "CPPP / eProcure", "Maharashtra Mahatenders",
  "Karnataka e-Procurement", "Gujarat nProcure", "Tamil Nadu Tenders",
  "Rajasthan SPPP", "Kerala e-Tenders", "PSU & Corporate RFPs",
] as const;

export function Header({ signedIn }: { signedIn: boolean }) {
  return (
    <header
      className="m-glass sticky top-0 z-30 border-b"
      style={{ borderColor: "var(--m-hairline)" }}
    >
      <nav className="m-shell flex h-16 items-center justify-between" aria-label="Main">
        <Link href="/" className="flex items-center gap-2.5 font-semibold">
          <span
            className="grid h-8 w-8 place-items-center rounded-lg text-white"
            style={{ background: "var(--m-primary)", boxShadow: "var(--m-shadow-sm)" }}
          >
            <Icon name="verified" size={17} />
          </span>
          <span style={{ color: "var(--m-ink)" }}>
            TenderCraft <span style={{ color: "var(--m-primary)" }}>AI</span>
          </span>
        </Link>

        <ul className="hidden items-center gap-8 text-sm md:flex">
          {NAV.map((n) => (
            <li key={n.label}>
              <Link
                href={n.href}
                className="transition-colors hover:text-[var(--m-primary)]"
                style={{ color: "var(--m-ink-soft)" }}
              >
                {n.label}
              </Link>
            </li>
          ))}
        </ul>

        <div className="flex items-center gap-2 sm:gap-3">
          {/* The comp always said "Sign In". Showing that to someone who already has a session
              sends them through a redirect to the page they were already entitled to. */}
          <Link
            href={signedIn ? "/dashboard" : "/login"}
            className="hidden px-2 text-sm font-medium transition-colors hover:text-[var(--m-primary)] sm:block"
            style={{ color: "var(--m-ink)" }}
          >
            {signedIn ? "Dashboard" : "Sign in"}
          </Link>
          {/* Compact padding, but the 44px min-height stays: this is the most-tapped control on
              the page and shrinking it below the touch-target floor costs taps on mobile. */}
          <Link href="#demo" className="m-btn m-btn-primary !px-4 !py-2 !text-sm">
            Book a Demo
          </Link>
        </div>
      </nav>
    </header>
  );
}

export function Hero() {
  return (
    <section className="relative isolate overflow-hidden pb-8 pt-20 md:pt-28">
      <div className="m-aurora" aria-hidden="true">
        <span /><span /><span />
      </div>
      <div className="m-grid-bg" aria-hidden="true" />

      <div className="m-shell relative z-10 text-center">
        <Reveal>
          <span
            className="m-label inline-flex items-center gap-2 rounded-full border px-3.5 py-2"
            style={{
              background: "var(--m-surface)",
              borderColor: "var(--m-primary-soft)",
              color: "var(--m-primary-deep)",
            }}
          >
            <Icon name="spark" size={13} />
            {HERO.badge}
          </span>
        </Reveal>

        <Reveal delay={80}>
          <h1 className="mx-auto mt-7 max-w-4xl text-[2.6rem] font-bold md:text-[4.25rem]">
            {HERO.titleLead}{" "}
            <span style={{ color: "var(--m-primary)" }}>{HERO.titleAccent}</span>
          </h1>
        </Reveal>

        <Reveal delay={160}>
          <p
            className="m-measure mx-auto mt-6 text-[17px] md:text-lg"
            style={{ color: "var(--m-ink-soft)" }}
          >
            {HERO.subtitle}
          </p>
        </Reveal>

        <Reveal delay={240}>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Link href="#demo" className="m-btn m-btn-primary">
              {HERO.primaryCta}
              <Icon name="arrow" size={17} />
            </Link>
            <Link href="#tour" className="m-btn m-btn-ghost">
              <Icon name="play" size={18} />
              {HERO.secondaryCta}
            </Link>
          </div>
        </Reveal>

        <Reveal delay={320}>
          <p className="mt-5 text-sm" style={{ color: "var(--m-ink-soft)" }}>
            Every generated line traced to a document you own, or flagged. Never invented.
          </p>
        </Reveal>
      </div>
    </section>
  );
}

export function PipelineVisual() {
  return (
    <section className="m-shell relative z-10 pb-6">
      <Reveal delay={380}>
        <div
          className="m-card overflow-hidden !rounded-[var(--m-radius-xl)] p-3 md:p-4"
          style={{ boxShadow: "var(--m-shadow-lg)" }}
        >
          <div className="grid grid-cols-3 gap-2 lg:grid-cols-6 lg:gap-3">
            {PIPELINE.map((step, i) => {
              const last = i === PIPELINE.length - 1;
              return (
                <div
                  key={step.label}
                  className="group relative flex flex-col items-center gap-2.5 rounded-[var(--m-radius-md)] px-2 py-7 text-center transition-transform duration-200 hover:-translate-y-0.5"
                  style={{
                    background: last ? "var(--m-primary)" : "var(--m-surface-low)",
                    color: last ? "var(--m-on-primary)" : "var(--m-ink-soft)",
                  }}
                >
                  <Icon name={step.icon as IconName} size={21} />
                  <span className="m-label">{step.label}</span>
                  {/* Connector dots read as a pipeline rather than six unrelated tiles. */}
                  {!last && (
                    <span
                      className="absolute -right-1 top-1/2 hidden h-1 w-1 -translate-y-1/2 rounded-full lg:block"
                      style={{ background: "var(--m-outline)" }}
                      aria-hidden="true"
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </Reveal>
    </section>
  );
}

export function PortalTicker() {
  return (
    <section className="border-y py-7" style={{ borderColor: "var(--m-hairline)" }}>
      <p className="m-label mb-5 text-center" style={{ color: "var(--m-ink-soft)" }}>
        Reads the portals your bids actually come from
      </p>
      <Marquee items={PORTALS} />
    </section>
  );
}

/**
 * The product itself, photographed.
 *
 * The page had no imagery at all, which for a brand surface is a bug rather than restraint:
 * typography was carrying the entire visual weight. The right image here is not stock, it is
 * the actual compliance matrix for a real 81-page NABARD tender, with the real numbers on it.
 * A buyer who has shredded an RFP by hand knows immediately whether this is real.
 */
export function ProductShot() {
  return (
    <section className="m-shell py-24">
      <div className="grid items-center gap-12 lg:grid-cols-[5fr_7fr]">
        <Reveal>
          <div>
            <h2 className="text-[2rem] font-semibold md:text-[2.5rem]">
              Proof that nothing was dropped
            </h2>
            <p className="m-measure mt-5 text-[15px]" style={{ color: "var(--m-ink-soft)" }}>
              A hand-built compliance matrix has no denominator, so &ldquo;we covered
              everything&rdquo; is an assertion. TenderCraft counts every obligation sentence in
              the document, maps each one to a row, and shows you the ones nothing covers yet.
            </p>
            <dl className="mt-8 space-y-4">
              {[
                ["81 pages", "read and shredded in about a minute"],
                ["192 requirements", "each with its page and clause reference"],
                ["57 sentences", "carrying an obligation that no requirement covered"],
              ].map(([k, v]) => (
                <div key={k} className="flex gap-4 border-t pt-4" style={{ borderColor: "var(--m-hairline)" }}>
                  <dt className="w-36 shrink-0 font-semibold">{k}</dt>
                  <dd className="text-[15px]" style={{ color: "var(--m-ink-soft)" }}>{v}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-6 text-xs" style={{ color: "var(--m-ink-soft)" }}>
              Screenshot from a live run against a published NABARD tender.
            </p>
          </div>
        </Reveal>

        <Reveal delay={120}>
          <div
            className="overflow-hidden rounded-[var(--m-radius-lg)] border"
            style={{ borderColor: "var(--m-hairline)", boxShadow: "var(--m-shadow-lg)" }}
          >
            <Image
              src="/product-compliance-matrix.png"
              alt="TenderCraft compliance matrix for a NABARD tender, showing 192 requirements and 57 obligation sentences with no matching row"
              width={1440}
              height={900}
              sizes="(max-width: 1024px) 100vw, 60vw"
              className="h-auto w-full"
              priority={false}
            />
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/**
 * The product tour.
 *
 * `preload="none"` is the load-bearing attribute: the file is 2.6 MB, and most visitors will
 * never press play. Preloading it would spend their bandwidth and hurt the page's largest
 * contentful paint to serve a minority. The poster frame is a 97 kB still, so the section
 * looks finished before a single byte of video moves.
 *
 * Native <video controls> rather than a custom player: keyboard control, captions, picture-in
 * -picture, and playback speed all come free and correct, and no one has ever thanked a
 * marketing site for its bespoke scrubber.
 */
export function Tour() {
  return (
    <section id="tour" className="m-shell scroll-mt-24 py-24">
      <Reveal>
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-[2rem] font-semibold md:text-[2.5rem]">Watch it read a real tender</h2>
          <p className="mt-4 text-[15px]" style={{ color: "var(--m-ink-soft)" }}>
            Fifty-five seconds, on a published NABARD tender. No mockups.
          </p>
        </div>
      </Reveal>

      <Reveal delay={100}>
        <div
          className="mt-10 overflow-hidden rounded-[var(--m-radius-lg)] border"
          style={{ borderColor: "var(--m-hairline)", boxShadow: "var(--m-shadow-lg)" }}
        >
          <video
            className="block h-auto w-full"
            controls
            preload="none"
            playsInline
            poster="/tendercraft-demo-poster.jpg"
            width={1600}
            height={900}
          >
            <source src="/tendercraft-demo.mp4" type="video/mp4" />
            Your browser cannot play this video.{" "}
            <a href="/tendercraft-demo.mp4">Download it instead.</a>
          </video>
        </div>
      </Reveal>
    </section>
  );
}

export function Problems() {
  return (
    <section className="py-24" style={{ background: "var(--m-surface-low)" }}>
      <div className="m-shell">
        <Reveal>
          <h2 className="text-center text-[2rem] font-semibold md:text-[2.75rem]">
            {PROBLEMS.title}
          </h2>
          <p
            className="m-measure mx-auto mt-4 text-center"
            style={{ color: "var(--m-ink-soft)" }}
          >
            {PROBLEMS.subtitle}
          </p>
        </Reveal>

        <div className="mt-14 grid gap-5 md:grid-cols-3">
          {PROBLEMS.items.map((p, i) => (
            <Reveal key={p.title} delay={i * 90}>
              <Spotlight className="m-card m-card-hover h-full overflow-hidden p-7">
                <span
                  className="grid h-11 w-11 place-items-center rounded-[var(--m-radius)]"
                  style={{ background: "var(--m-accent-soft)", color: "var(--m-accent-ink)" }}
                >
                  <Icon name={p.icon as IconName} size={21} />
                </span>
                <h3 className="mt-5 text-lg font-semibold">{p.title}</h3>
                <p className="mt-2.5 text-[15px]" style={{ color: "var(--m-ink-soft)" }}>
                  {p.body}
                </p>
              </Spotlight>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

export function Features() {
  return (
    <section id="features" className="m-shell py-24">
      <Reveal>
        <h2 className="text-center text-[2rem] font-semibold md:text-[2.75rem]">
          {FEATURES.title}
        </h2>
      </Reveal>

      {/* Asymmetric bento: the hero capability gets 7 columns, the rest share 5. Equal thirds
          would say every feature matters equally, which is never true. */}
      <div className="mt-14 grid gap-5 lg:grid-cols-12">
        <Reveal className="lg:col-span-7" delay={40}>
          <Spotlight
            className="m-card m-card-hover relative h-full overflow-hidden p-8 md:p-10"
            /* Saffron top rule = AI-generated surface. The "Insight Card" signature. */
          >
            <span
              aria-hidden="true"
              className="absolute inset-x-0 top-0 h-[3px]"
              style={{ background: "linear-gradient(90deg, var(--m-accent), transparent)" }}
            />
            <span
              className="m-label inline-block rounded-full px-2.5 py-1.5"
              style={{ background: "var(--m-accent-soft)", color: "var(--m-accent-ink)" }}
            >
              {FEATURES.premiumTag}
            </span>
            <h3 className="mt-5 text-2xl font-semibold md:text-3xl">{FEATURES.rfp.title}</h3>
            <p className="m-measure mt-3.5 text-[15px]" style={{ color: "var(--m-ink-soft)" }}>
              {FEATURES.rfp.body}
            </p>
            <Link
              href="#demo"
              className="mt-7 inline-flex items-center gap-1.5 text-sm font-semibold transition-transform hover:translate-x-0.5"
              style={{ color: "var(--m-primary)" }}
            >
              {FEATURES.rfp.cta}
              <Icon name="arrow" size={16} />
            </Link>
            <Icon
              name="chart"
              size={200}
              className="pointer-events-none absolute -bottom-10 -right-8 opacity-[0.05]"
            />
          </Spotlight>
        </Reveal>

        <Reveal className="lg:col-span-5" delay={120}>
          <article
            className="relative h-full overflow-hidden rounded-[var(--m-radius-lg)] p-8 md:p-10"
            style={{
              background: "linear-gradient(155deg, var(--m-primary), var(--m-primary-deep))",
              color: "var(--m-on-primary)",
              boxShadow: "var(--m-shadow-lg)",
            }}
          >
            <Icon name="rule" size={26} />
            <h3 className="mt-5 text-2xl font-semibold">{FEATURES.matrix.title}</h3>
            <p className="mt-3.5 text-[15px] opacity-90">{FEATURES.matrix.body}</p>
            <span
              aria-hidden="true"
              className="pointer-events-none absolute -bottom-16 -right-10 h-52 w-52 rounded-full"
              style={{ background: "radial-gradient(circle, rgba(255,255,255,0.14), transparent 70%)" }}
            />
          </article>
        </Reveal>

        <Reveal className="lg:col-span-5" delay={160}>
          <Spotlight className="m-card m-card-hover relative h-full overflow-hidden p-8">
            <span
              aria-hidden="true"
              className="absolute inset-x-0 top-0 h-[3px]"
              style={{ background: "linear-gradient(90deg, var(--m-accent), transparent)" }}
            />
            <span style={{ color: "var(--m-accent-ink)" }}>
              <Icon name="draw" size={26} />
            </span>
            <h3 className="mt-5 text-xl font-semibold">{FEATURES.writer.title}</h3>
            <p className="mt-3 text-[15px]" style={{ color: "var(--m-ink-soft)" }}>
              {FEATURES.writer.body}
            </p>
          </Spotlight>
        </Reveal>

        <Reveal className="lg:col-span-7" delay={200}>
          <Spotlight
            className="m-card m-card-hover h-full p-8"
            /* Surface tint rather than white — breaks the grid of identical cards. */
          >
            <div className="flex items-start justify-between gap-6">
              <div>
                <h3 className="text-xl font-semibold">{FEATURES.portal.title}</h3>
                <p className="mt-3 text-[15px]" style={{ color: "var(--m-ink-soft)" }}>
                  {FEATURES.portal.body}
                </p>
              </div>
              <div className="flex shrink-0 gap-3" style={{ color: "var(--m-primary)" }}>
                <Icon name="cloud" size={24} />
                <Icon name="lock" size={24} />
              </div>
            </div>
          </Spotlight>
        </Reveal>
      </div>
    </section>
  );
}

export function Workflow() {
  return (
    <section
      id="workflow"
      className="relative overflow-hidden py-24"
      style={{ background: "var(--m-inverse)", color: "var(--m-on-inverse)" }}
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-px"
        style={{ background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.25), transparent)" }}
      />
      <div className="m-shell relative">
        <Reveal>
          <h2 className="text-center text-[2rem] font-semibold md:text-[2.75rem]">
            {WORKFLOW.title}
          </h2>
        </Reveal>

        <ol className="relative mt-16 grid grid-cols-2 gap-y-12 sm:grid-cols-4 lg:grid-cols-8">
          {/* One continuous rule behind the nodes — the line is what makes eight steps read as
              a single cycle instead of eight separate facts. */}
          <span
            aria-hidden="true"
            className="pointer-events-none absolute left-0 right-0 top-[18px] hidden h-px lg:block"
            style={{ background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.18) 8%, rgba(255,255,255,0.18) 92%, transparent)" }}
          />
          {WORKFLOW.steps.map((s, i) => {
            const last = i === WORKFLOW.steps.length - 1;
            return (
              <Reveal as="li" key={s.label} delay={i * 60} className="relative flex flex-col items-center gap-2.5 text-center">
                <span
                  className="grid h-9 w-9 place-items-center rounded-full text-[13px] font-semibold ring-4"
                  style={{
                    background: last ? "var(--m-accent)" : "var(--m-primary)",
                    color: last ? "var(--m-inverse)" : "var(--m-on-primary)",
                    // Ring in the section colour punches the node out of the connector line.
                    ["--tw-ring-color" as string]: "var(--m-inverse)",
                  }}
                >
                  {i + 1}
                </span>
                <span className="text-sm font-semibold">{s.label}</span>
                <span className="m-label opacity-55">{s.sub}</span>
              </Reveal>
            );
          })}
        </ol>
      </div>
    </section>
  );
}

export function Sectors() {
  return (
    <section id="sectors" className="m-shell py-24 text-center">
      <Reveal>
        <h2 className="text-2xl font-semibold md:text-3xl">{SECTORS.eyebrow}</h2>
      </Reveal>

      <Reveal delay={80}>
        <ul className="mt-9 flex flex-wrap justify-center gap-2.5">
          {SECTORS.items.map((s) => (
            <li
              key={s.label}
              className="flex cursor-default items-center gap-2 rounded-full border px-4 py-2.5 text-sm font-medium transition-all duration-200 hover:-translate-y-0.5"
              style={{
                background: "var(--m-surface)",
                borderColor: "var(--m-hairline)",
                color: "var(--m-ink)",
                boxShadow: "var(--m-shadow-sm)",
              }}
            >
              <span style={{ color: "var(--m-primary)" }}>
                <Icon name={s.icon as IconName} size={16} />
              </span>
              {s.label}
            </li>
          ))}
        </ul>
      </Reveal>

      <div className="mt-16 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {CLAIMS.stats.map((s, i) => (
          <Reveal key={s.label} delay={i * 80}>
            <div className="m-card m-card-hover px-6 py-9">
              <p
                className="text-[2.1rem] font-bold tabular-nums"
                style={{ color: "var(--m-primary)", fontFamily: "var(--font-marketing-display)" }}
              >
                <Odometer value={s.value} />
              </p>
              <p className="mt-1.5 text-sm" style={{ color: "var(--m-ink-soft)" }}>
                {s.label}
              </p>
            </div>
          </Reveal>
        ))}
      </div>

      <Reveal delay={120}>
        <div
          className="mt-9 flex flex-wrap items-center justify-center gap-x-7 gap-y-3 text-sm"
          style={{ color: "var(--m-ink-soft)" }}
        >
          <span className="inline-flex items-center gap-2">
            <Icon name="verified" size={16} /> {CLAIMS.badges[0]}
          </span>
          <span className="inline-flex items-center gap-2">
            <Icon name="heart" size={16} /> {CLAIMS.badges[1]}
          </span>
        </div>
      </Reveal>
    </section>
  );
}

export function Closing() {
  return (
    <section id="demo" className="m-shell py-24">
      <Reveal>
        <div
          className="relative overflow-hidden rounded-[var(--m-radius-xl)] px-6 py-16 text-center"
          style={{
            background: "linear-gradient(160deg, var(--m-inverse), #1b2540)",
            color: "var(--m-on-inverse)",
          }}
        >
          <span
            aria-hidden="true"
            className="pointer-events-none absolute -top-24 left-1/2 h-72 w-[36rem] -translate-x-1/2 rounded-full"
            style={{ background: "radial-gradient(circle, rgba(0,82,204,0.55), transparent 68%)", filter: "blur(52px)" }}
          />
          <div className="relative">
            <h2 className="text-[1.8rem] font-semibold md:text-[2.5rem]">{CLOSING.title}</h2>
            <p className="m-measure mx-auto mt-4 text-sm opacity-80">{CLAIMS.closingSubtitle}</p>
            <div className="mt-9 flex flex-wrap justify-center gap-3">
              <Link href="/login" className="m-btn m-btn-primary">
                {CLOSING.primaryCta}
                <Icon name="arrow" size={17} />
              </Link>
              <Link
                href="#"
                className="m-btn"
                style={{
                  background: "rgba(255,255,255,0.1)",
                  color: "var(--m-on-inverse)",
                  border: "1px solid rgba(255,255,255,0.2)",
                }}
              >
                {CLOSING.secondaryCta}
              </Link>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="border-t py-16" style={{ borderColor: "var(--m-hairline)" }}>
      <div className="m-shell grid gap-12 lg:grid-cols-[2fr_3fr]">
        <div>
          <div className="flex items-center gap-2.5 font-semibold">
            <span
              className="grid h-8 w-8 place-items-center rounded-lg text-white"
              style={{ background: "var(--m-primary)" }}
            >
              <Icon name="verified" size={17} />
            </span>
            TenderCraft <span style={{ color: "var(--m-primary)" }}>AI</span>
          </div>
          <p className="mt-4 max-w-xs text-sm" style={{ color: "var(--m-ink-soft)" }}>
            {FOOTER.blurb}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">
          {FOOTER.columns.map((col) => (
            <div key={col.title}>
              <p className="text-sm font-semibold">{col.title}</p>
              <ul className="mt-4 space-y-2.5 text-sm" style={{ color: "var(--m-ink-soft)" }}>
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link href={l.href} className="transition-colors hover:text-[var(--m-primary)]">
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      <div
        className="m-shell mt-14 flex flex-col gap-2 border-t pt-7 text-xs sm:flex-row sm:items-center sm:justify-between"
        style={{ borderColor: "var(--m-hairline)", color: "var(--m-ink-soft)" }}
      >
        <span>{FOOTER.legal}</span>
        {/* Same disclaimer the login screen carries — a buyer should see it before signing up. */}
        <span>{FOOTER.disclaimer}</span>
      </div>
    </footer>
  );
}
