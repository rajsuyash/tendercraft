import Link from "next/link";

import {
  CLAIMS, CLOSING, FEATURES, FOOTER, HERO, NAV, PIPELINE, PRICING, PROBLEMS, SECTORS, WORKFLOW,
} from "./content";
import { Icon, type IconName } from "./Icon";

export function Header({ signedIn }: { signedIn: boolean }) {
  return (
    <header className="m-glass sticky top-0 z-50 border-b" style={{ borderColor: "var(--m-outline)" }}>
      <nav className="m-shell flex h-16 items-center justify-between" aria-label="Main">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <span
            className="grid h-7 w-7 place-items-center rounded-md text-white"
            style={{ background: "var(--m-primary)" }}
          >
            <Icon name="verified" size={16} />
          </span>
          <span style={{ color: "var(--m-primary)" }}>TenderCraft AI</span>
        </Link>

        <ul className="hidden items-center gap-8 text-sm md:flex">
          {NAV.map((n) => (
            <li key={n.label}>
              <Link
                href={n.href}
                className="transition-colors hover:opacity-70"
                style={{ color: "var(--m-ink-soft)" }}
              >
                {n.label}
              </Link>
            </li>
          ))}
        </ul>

        <div className="flex items-center gap-3">
          {/* The comp always said "Sign In". Showing that to someone who already has a
              session sends them through a redirect to the page they were entitled to. */}
          <Link
            href={signedIn ? "/dashboard" : "/login"}
            className="text-sm font-medium"
            style={{ color: "var(--m-ink)" }}
          >
            {signedIn ? "Dashboard" : "Sign in"}
          </Link>
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
    <section className="m-shell pt-16 pb-12 text-center md:pt-24">
      <span
        className="m-label inline-flex items-center gap-2 rounded-full px-3 py-1.5"
        style={{ background: "var(--m-surface-high)", color: "var(--m-primary-deep)" }}
      >
        <Icon name="spark" size={13} />
        {HERO.badge}
      </span>

      <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-bold leading-tight md:text-6xl">
        {HERO.titleLead}{" "}
        <em className="not-italic" style={{ color: "var(--m-primary)" }}>
          {HERO.titleAccent}
        </em>
      </h1>

      <p
        className="mx-auto mt-5 max-w-2xl text-base leading-7 md:text-lg"
        style={{ color: "var(--m-ink-soft)" }}
      >
        {HERO.subtitle}
      </p>

      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <Link href="#demo" className="m-btn m-btn-primary">
          {HERO.primaryCta}
        </Link>
        <Link href="#workflow" className="m-btn m-btn-ghost">
          <Icon name="play" size={18} />
          {HERO.secondaryCta}
        </Link>
      </div>
    </section>
  );
}

export function PipelineVisual() {
  return (
    <section className="m-shell pb-20">
      <div className="m-card p-4 md:p-6" style={{ boxShadow: "var(--m-shadow-lg)" }}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {PIPELINE.map((step, i) => {
            const last = i === PIPELINE.length - 1;
            return (
              <div
                key={step.label}
                className="flex flex-col items-center gap-2 rounded-xl px-3 py-6 text-center"
                style={{
                  background: last ? "var(--m-primary)" : "var(--m-surface-low)",
                  color: last ? "var(--m-on-primary)" : "var(--m-ink-soft)",
                }}
              >
                <Icon name={step.icon as IconName} size={20} />
                <span className="m-label">{step.label}</span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export function Problems() {
  return (
    <section className="py-20" style={{ background: "var(--m-surface-low)" }}>
      <div className="m-shell">
        <h2 className="text-center text-3xl font-semibold md:text-4xl">{PROBLEMS.title}</h2>
        <p className="mt-3 text-center text-base" style={{ color: "var(--m-ink-soft)" }}>
          {PROBLEMS.subtitle}
        </p>

        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {PROBLEMS.items.map((p) => (
            <article key={p.title} className="m-card p-6">
              <span
                className="grid h-10 w-10 place-items-center rounded-lg"
                style={{ background: "var(--m-accent-soft)", color: "var(--m-accent-ink)" }}
              >
                <Icon name={p.icon as IconName} size={20} />
              </span>
              <h3 className="mt-4 text-lg font-semibold">{p.title}</h3>
              <p className="mt-2 text-sm leading-6" style={{ color: "var(--m-ink-soft)" }}>
                {p.body}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

export function Features() {
  return (
    <section id="features" className="m-shell py-20">
      <h2 className="text-center text-3xl font-semibold md:text-4xl">{FEATURES.title}</h2>

      <div className="mt-12 grid gap-6 lg:grid-cols-2">
        {/* Saffron top rule marks the AI-generated surface — the "Insight Card" signature. */}
        <article
          className="m-card relative overflow-hidden p-8"
          style={{ borderTop: "3px solid var(--m-accent)" }}
        >
          <span
            className="m-label inline-block rounded-full px-2.5 py-1"
            style={{ background: "var(--m-accent-soft)", color: "var(--m-accent-ink)" }}
          >
            {FEATURES.premiumTag}
          </span>
          <h3 className="mt-4 text-2xl font-semibold">{FEATURES.rfp.title}</h3>
          <p className="mt-3 max-w-md text-sm leading-6" style={{ color: "var(--m-ink-soft)" }}>
            {FEATURES.rfp.body}
          </p>
          <Link
            href="#demo"
            className="mt-6 inline-flex items-center gap-1.5 text-sm font-semibold"
            style={{ color: "var(--m-primary)" }}
          >
            {FEATURES.rfp.cta}
            <Icon name="arrow" size={16} />
          </Link>
          <Icon
            name="chart"
            size={160}
            className="pointer-events-none absolute -bottom-8 -right-6 opacity-[0.06]"
          />
        </article>

        <article
          className="rounded-[1.5rem] p-8"
          style={{ background: "var(--m-primary)", color: "var(--m-on-primary)" }}
        >
          <Icon name="rule" size={24} />
          <h3 className="mt-4 text-2xl font-semibold">{FEATURES.matrix.title}</h3>
          <p className="mt-3 max-w-md text-sm leading-6 opacity-90">{FEATURES.matrix.body}</p>
        </article>

        <article
          className="m-card p-8"
          style={{ borderTop: "3px solid var(--m-accent)" }}
        >
          <span style={{ color: "var(--m-accent-ink)" }}>
            <Icon name="draw" size={24} />
          </span>
          <h3 className="mt-4 text-xl font-semibold">{FEATURES.writer.title}</h3>
          <p className="mt-3 text-sm leading-6" style={{ color: "var(--m-ink-soft)" }}>
            {FEATURES.writer.body}
          </p>
        </article>

        <article className="rounded-[1.5rem] p-8" style={{ background: "var(--m-surface-high)" }}>
          <h3 className="text-xl font-semibold">{FEATURES.portal.title}</h3>
          <p className="mt-3 text-sm leading-6" style={{ color: "var(--m-ink-soft)" }}>
            {FEATURES.portal.body}
          </p>
          <div className="mt-6 flex gap-3" style={{ color: "var(--m-primary)" }}>
            <Icon name="cloud" size={22} />
            <Icon name="lock" size={22} />
          </div>
        </article>
      </div>
    </section>
  );
}

export function Workflow() {
  return (
    <section
      id="workflow"
      className="py-20"
      style={{ background: "var(--m-inverse)", color: "var(--m-on-inverse)" }}
    >
      <div className="m-shell">
        <h2 className="text-center text-3xl font-semibold md:text-4xl">{WORKFLOW.title}</h2>
        <ol className="mt-12 grid grid-cols-2 gap-y-10 sm:grid-cols-4 lg:grid-cols-8">
          {WORKFLOW.steps.map((s, i) => {
            const last = i === WORKFLOW.steps.length - 1;
            return (
              <li key={s.label} className="flex flex-col items-center gap-2 text-center">
                <span
                  className="grid h-9 w-9 place-items-center rounded-full text-sm font-semibold"
                  style={{
                    background: last ? "var(--m-accent)" : "var(--m-primary)",
                    color: last ? "var(--m-ink)" : "var(--m-on-primary)",
                  }}
                >
                  {i + 1}
                </span>
                <span className="text-sm font-semibold">{s.label}</span>
                <span className="m-label opacity-60">{s.sub}</span>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}

export function Sectors() {
  return (
    <section id="sectors" className="m-shell py-20 text-center">
      <p className="m-label" style={{ color: "var(--m-ink-soft)" }}>
        {SECTORS.eyebrow}
      </p>
      <ul className="mt-8 flex flex-wrap justify-center gap-3">
        {SECTORS.items.map((s) => (
          <li
            key={s.label}
            className="flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-medium"
            style={{ background: "var(--m-surface-mid)", color: "var(--m-ink)" }}
          >
            <span style={{ color: "var(--m-primary)" }}>
              <Icon name={s.icon as IconName} size={16} />
            </span>
            {s.label}
          </li>
        ))}
      </ul>

      <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {CLAIMS.stats.map((s) => (
          <div key={s.label} className="m-card px-6 py-8">
            <p className="text-3xl font-bold" style={{ color: "var(--m-primary)" }}>
              {s.value}
            </p>
            <p className="mt-1 text-sm" style={{ color: "var(--m-ink-soft)" }}>
              {s.label}
            </p>
          </div>
        ))}
      </div>

      <div
        className="mt-8 flex flex-wrap items-center justify-center gap-6 text-sm"
        style={{ color: "var(--m-ink-soft)" }}
      >
        <span className="inline-flex items-center gap-2">
          <Icon name="verified" size={16} /> {CLAIMS.badges[0]}
        </span>
        <span className="inline-flex items-center gap-2">
          <Icon name="heart" size={16} /> {CLAIMS.badges[1]}
        </span>
      </div>
    </section>
  );
}

export function Pricing() {
  return (
    <section id="pricing" className="py-20" style={{ background: "var(--m-surface-low)" }}>
      <div className="m-shell">
        <h2 className="text-center text-3xl font-semibold md:text-4xl">{PRICING.title}</h2>
        <p className="mt-3 text-center text-base" style={{ color: "var(--m-ink-soft)" }}>
          {PRICING.subtitle}
        </p>

        <div className="mt-12 grid items-start gap-6 lg:grid-cols-3">
          {PRICING.plans.map((plan) => {
            const featured = plan.featured;
            return (
              <article
                key={plan.name}
                className={featured ? "rounded-[1.5rem] p-8 lg:-mt-4 lg:pb-12" : "m-card p-8"}
                style={
                  featured
                    ? {
                        background: "var(--m-primary)",
                        color: "var(--m-on-primary)",
                        boxShadow: "var(--m-shadow-lg)",
                      }
                    : undefined
                }
              >
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold">{plan.name}</h3>
                  {"tag" in plan && plan.tag && (
                    <span
                      className="m-label rounded-full px-2.5 py-1"
                      style={{ background: "var(--m-accent)", color: "var(--m-ink)" }}
                    >
                      {plan.tag}
                    </span>
                  )}
                </div>

                <p className="mt-5 text-4xl font-bold">
                  {plan.price}
                  {plan.period && (
                    <span className="text-base font-medium opacity-70">{plan.period}</span>
                  )}
                </p>
                <p
                  className="mt-2 text-sm"
                  style={{ color: featured ? undefined : "var(--m-ink-soft)" }}
                >
                  {plan.blurb}
                </p>

                <ul className="mt-6 space-y-3 text-sm">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-center gap-2.5">
                      <span style={{ color: featured ? "var(--m-accent)" : "var(--m-primary)" }}>
                        <Icon name="check" size={18} />
                      </span>
                      {f}
                    </li>
                  ))}
                </ul>

                <Link
                  href="#demo"
                  className="m-btn mt-8 w-full"
                  style={
                    featured
                      ? { background: "var(--m-surface)", color: "var(--m-primary)" }
                      : plan.name === "Enterprise"
                        ? { background: "var(--m-ink)", color: "var(--m-on-inverse)" }
                        : {
                            border: "1px solid var(--m-primary)",
                            color: "var(--m-primary)",
                            background: "transparent",
                          }
                  }
                >
                  {plan.cta}
                </Link>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export function Closing() {
  return (
    <section id="demo" className="m-shell py-20">
      <div
        className="rounded-[1.5rem] px-6 py-14 text-center"
        style={{ background: "var(--m-surface-high)" }}
      >
        <h2 className="text-2xl font-semibold md:text-3xl">{CLOSING.title}</h2>
        <p className="mx-auto mt-3 max-w-xl text-sm" style={{ color: "var(--m-ink-soft)" }}>
          {CLAIMS.closingSubtitle}
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link href="/login" className="m-btn m-btn-primary">
            {CLOSING.primaryCta}
          </Link>
          <Link href="#" className="m-btn m-btn-ghost">
            {CLOSING.secondaryCta}
          </Link>
        </div>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="border-t py-14" style={{ borderColor: "var(--m-outline)" }}>
      <div className="m-shell grid gap-10 lg:grid-cols-[2fr_3fr]">
        <div>
          <div className="flex items-center gap-2 font-semibold" style={{ color: "var(--m-primary)" }}>
            <Icon name="verified" size={18} />
            TenderCraft AI
          </div>
          <p className="mt-3 max-w-xs text-sm leading-6" style={{ color: "var(--m-ink-soft)" }}>
            {FOOTER.blurb}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">
          {FOOTER.columns.map((col) => (
            <div key={col.title}>
              <p className="text-sm font-semibold">{col.title}</p>
              <ul className="mt-3 space-y-2 text-sm" style={{ color: "var(--m-ink-soft)" }}>
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link href={l.href} className="hover:opacity-70">
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
        className="m-shell mt-12 flex flex-col gap-2 border-t pt-6 text-xs sm:flex-row sm:items-center sm:justify-between"
        style={{ borderColor: "var(--m-outline)", color: "var(--m-ink-soft)" }}
      >
        <span>{FOOTER.legal}</span>
        {/* Carried over from the product's own login screen — the same disclaimer a buyer
            sees inside the app should be visible before they sign up. */}
        <span>{FOOTER.disclaimer}</span>
      </div>
    </footer>
  );
}
