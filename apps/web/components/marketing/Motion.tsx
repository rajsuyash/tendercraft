"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Motion primitives for the landing page — no animation library.
 *
 * The reference components these are ported from drive everything through GSAP +
 * ScrollTrigger. Adding ~70 kB of animation runtime to a marketing page for a fade, a
 * counter and a marquee is a bad trade: IntersectionObserver plus CSS transitions produce
 * the same result, ship nothing, and degrade correctly on their own.
 *
 * Shared rules across all three:
 *   - transform/opacity only, so frames composite instead of forcing layout
 *   - every observer disconnects after firing once; nothing keeps running after it is done
 *   - content is VISIBLE by default and only hidden once JS confirms it can reveal it again
 *   - prefers-reduced-motion is honoured in JS as well as CSS, so the work is skipped
 *     entirely rather than merely being fast
 */

const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Fade + 14px lift when the element first scrolls into view. */
export function Reveal({
  children,
  delay = 0,
  className = "",
  as: Tag = "div",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
  as?: "div" | "section" | "li" | "article" | "header";
}) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    // No observer support, or the user asked for less motion: leave it visible. Hiding it
    // first and relying on a callback that may never come is how content disappears.
    if (!el || prefersReducedMotion() || typeof IntersectionObserver === "undefined") return;

    // Never hide something that is already on screen. Without this the whole first viewport
    // animates in on every load, which is noise, not polish.
    if (el.getBoundingClientRect().top < window.innerHeight * 0.9) return;

    el.classList.add("is-hidden");
    const reveal = () => el.classList.remove("is-hidden");

    const io = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting) return;
        reveal();
        io.disconnect();
      },
      // Fire slightly before the element reaches the fold, so it has finished animating by
      // the time it is properly in view rather than starting as it arrives.
      { rootMargin: "0px 0px -12% 0px", threshold: 0.05 },
    );
    io.observe(el);

    // FAILSAFE. Anything that renders the page without scrolling it never triggers the
    // observer, and every hidden section stays invisible: full-page screenshots, print, social
    // preview bots, and crawlers that snapshot at viewport height. A blank landing page in a
    // link preview is worse than no animation at all, so reveal unconditionally after 2.5s.
    const failsafe = window.setTimeout(() => {
      reveal();
      io.disconnect();
    }, 2500);

    return () => {
      window.clearTimeout(failsafe);
      io.disconnect();
    };
  }, []);

  return (
    <Tag
      ref={ref as never}
      className={`m-reveal ${className}`}
      style={{ ["--m-delay" as string]: `${delay}ms` }}
    >
      {children}
    </Tag>
  );
}

/**
 * Rolling digit counter. Renders the final value as real text on the server, then swaps to
 * the animated strips on the client — so the number is correct for search engines, for
 * screen readers, and for anyone whose JS never runs.
 */
export function Odometer({ value, className = "" }: { value: string; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [animate, setAnimate] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion() || typeof IntersectionObserver === "undefined") return;
    // Nothing to roll: "Hours" has no digits, and a single "0" rolling to itself is not an
    // animation. Leave those as plain text rather than building strips that cannot move.
    if (!/\d/.test(value) || value.replace(/\D/g, "") === "0") return;

    setAnimate(true);

    const settle = () =>
      el.querySelectorAll<HTMLElement>(".m-odo-strip").forEach((strip, i) => {
        const target = Number(strip.dataset.target ?? 0);
        strip.style.setProperty("--m-delay", `${i * 90}ms`);
        strip.style.transform = `translateY(-${target * 1.06}em)`;
      });

    const io = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting) return;
        settle();
        io.disconnect();
      },
      { threshold: 0.4 },
    );
    io.observe(el);

    // FAILSAFE, and here it matters more than on a fade. An un-fired odometer does not render
    // nothing — every strip sits on digit 0, so "100%" displays as "000%" and "1 pass" as
    // "0 pass". Silently showing the WRONG NUMBER on a page selling accuracy is the worst
    // outcome available, so snap to the real value if the observer has not fired.
    const failsafe = window.setTimeout(() => {
      settle();
      io.disconnect();
    }, 2500);

    return () => {
      window.clearTimeout(failsafe);
      io.disconnect();
    };
  }, [value]);

  // Split so non-digits (%, +, ×, commas) stay put and only real digits roll.
  const chars = value.split("");

  return (
    <span ref={ref} className={className} aria-label={value}>
      {animate ? (
        <span className="m-odo" aria-hidden="true">
          {chars.map((c, i) =>
            /\d/.test(c) ? (
              <span key={i} className="m-odo-digit">
                <span className="m-odo-strip" data-target={c}>
                  {Array.from({ length: 10 }, (_, n) => (
                    <span key={n}>{n}</span>
                  ))}
                </span>
              </span>
            ) : (
              <span key={i} className="m-odo-char">
                {c}
              </span>
            ),
          )}
        </span>
      ) : (
        value
      )}
    </span>
  );
}

/**
 * Pointer-tracked highlight. Writes two CSS variables on the hovered card — no React state,
 * so moving the mouse never triggers a re-render. Skipped entirely on coarse pointers, where
 * there is no hover and the listener would be dead weight.
 */
export function Spotlight({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || !window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;

    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${e.clientX - r.left}px`);
      el.style.setProperty("--my", `${e.clientY - r.top}px`);
    };
    el.addEventListener("pointermove", onMove);
    return () => el.removeEventListener("pointermove", onMove);
  }, []);

  return (
    <div ref={ref} className={`m-spot ${className}`}>
      {children}
    </div>
  );
}

/** Seamless ticker. The track is duplicated so a -50% translate loops with no visible seam. */
export function Marquee({ items }: { items: readonly string[] }) {
  return (
    <div className="m-marquee" role="presentation">
      <div className="m-marquee-track">
        {[0, 1].map((copy) => (
          <ul key={copy} className="flex shrink-0" aria-hidden={copy === 1}>
            {items.map((item) => (
              <li
                key={item}
                className="m-label flex items-center gap-3 whitespace-nowrap px-7 py-3"
                style={{ color: "var(--m-ink-soft)" }}
              >
                <span
                  className="inline-block h-1.5 w-1.5 rounded-full"
                  style={{ background: "var(--m-primary)" }}
                />
                {item}
              </li>
            ))}
          </ul>
        ))}
      </div>
    </div>
  );
}
