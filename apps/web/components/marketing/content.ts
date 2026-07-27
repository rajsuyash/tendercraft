/**
 * Landing-page copy, in one file.
 *
 * Marketing copy changes far more often than markup, and it is the part a non-engineer will
 * want to edit. Keeping it here means a wording change never means touching JSX.
 *
 * ─────────────────────────────────────────────────────────────────────────────────────────
 * CLAIMS THAT ARE NOT TRUE YET — read before publishing.
 *
 * The designer's comp carried several factual assertions this product cannot currently
 * support. They are collected in `CLAIMS` below with honest stand-ins, because a compliance
 * product that overstates its own compliance is the worst possible first impression, and two
 * of them carry real legal exposure:
 *
 *   "ISO 27001 Certified"  → tendercraft-PRD.md §9 lists ISO 27001 and SOC 2 as ROADMAP
 *                            items. Publishing a certification you do not hold is a false
 *                            statement about a security credential, made to government
 *                            buyers who verify exactly that.
 *   "Join 200+ companies"  → there is no customer base yet.
 *   80% / 3x / 100% / 10k+ → these are PRD TARGETS (§7 success metrics), not measurements.
 *                            "80% less time" in the hero is the same target.
 *
 * Every one is a one-line edit here the moment it becomes true. Do not move them back into
 * the components — the point of this block is that they are impossible to ship by accident.
 * ─────────────────────────────────────────────────────────────────────────────────────────
 */

export const NAV = [
  { label: "Product", href: "#features" },
  { label: "Solutions", href: "#workflow" },
  { label: "Industries", href: "#sectors" },
  { label: "Pricing", href: "#pricing" },
  { label: "Resources", href: "/guide" },
] as const;

export const HERO = {
  badge: "Next-Gen AI for Public Procurement",
  titleLead: "Win More Government Tenders with",
  titleAccent: "Precision AI",
  // Reworded from "in 80% less time": the comp stated a measured outcome; this states the
  // ambition without asserting a result nobody has measured.
  subtitle:
    "Automate your entire bid lifecycle — from RFP analysis to compliance matrices and " +
    "technical writing. Built to cut the weeks that complex government bids consume today.",
  primaryCta: "Book a Demo",
  secondaryCta: "Watch Product Tour",
} as const;

export const PIPELINE = [
  { icon: "document", label: "Tender" },
  { icon: "insights", label: "Analysis" },
  { icon: "shield", label: "Compliance" },
  { icon: "edit", label: "Writing" },
  { icon: "review", label: "Review" },
  { icon: "send", label: "Submission" },
] as const;

export const PROBLEMS = {
  title: "Bidding is hard. AI makes it easy.",
  subtitle: "The biggest bottlenecks in government procurement, solved.",
  items: [
    {
      icon: "alert",
      title: "Manual Compliance Checks",
      body:
        "Hours spent reading 500-page RFPs just to check eligibility. Don't let a missed " +
        "'Appendix C' disqualify you.",
    },
    {
      icon: "timer",
      title: "Tight Deadlines",
      body:
        "Struggling to find technical experts and legal teams in time for a midnight " +
        "submission? We automate the grind.",
    },
    {
      icon: "hidden",
      title: "Missed Opportunities",
      body:
        "Finding relevant tenders across 20+ portals is a nightmare. Our AI agents monitor " +
        "GeM and CPP portals for you.",
    },
  ],
} as const;

export const FEATURES = {
  title: "Powerful Features for Complex Bids",
  premiumTag: "PREMIUM FEATURE",
  rfp: {
    title: "AI RFP Analysis",
    body:
      "Our models extract key requirements, technical specs and financial criteria in " +
      "seconds, highlighting high-risk clauses automatically.",
    cta: "Learn more",
  },
  matrix: {
    title: "Compliance Matrix Generator",
    body:
      "Automatically map RFP requirements to your proposal chapters to ensure full " +
      "technical compliance.",
  },
  writer: {
    title: "Technical Bid Generator",
    body:
      "Generates drafting starting points based on your company's past project credentials " +
      "and domain expertise.",
  },
  portal: {
    title: "Secure Portal Integration",
    // The comp said "Direct integration with GeM, CPP and State Tendering portals". The
    // product holds NO portal write credentials by design (PRD G-1) — it is export-assist
    // only. "Direct integration" would promise the one thing we deliberately never do.
    body:
      "Export-ready documents for GeM, CPP and state tendering portals, with tracking " +
      "across every submission.",
  },
} as const;

export const WORKFLOW = {
  title: "The Win-Cycle Workflow",
  steps: [
    { label: "Find Tender", sub: "AI Portal Sync" },
    { label: "Analyse", sub: "Requirement Scan" },
    { label: "Qualify", sub: "Eligibility Score" },
    { label: "Collaborate", sub: "Team Assignment" },
    { label: "Draft", sub: "AI Text Gen" },
    { label: "Review", sub: "Legal Compliance" },
    { label: "Approve", sub: "Final Approval" },
    { label: "Submit", sub: "Ready for Portal" },
  ],
} as const;

export const SECTORS = {
  eyebrow: "Empowering Critical Sectors",
  items: [
    { icon: "chip", label: "IT & Software" },
    { icon: "shield", label: "Defence" },
    { icon: "train", label: "Railways" },
    { icon: "bolt", label: "Energy" },
    { icon: "health", label: "Healthcare" },
    { icon: "build", label: "Infrastructure" },
  ],
} as const;

/** See the header block. Every value here is a promise to a government buyer. */
export const CLAIMS = {
  stats: [
    { value: "Hours", label: "Not weeks, per bid" },
    { value: "1 pass", label: "Every requirement traced" },
    { value: "0", label: "Uncited claims at export" },
    { value: "100%", label: "Human-approved output" },
  ],
  // Was "ISO 27001 Certified". PRD §9 puts ISO 27001 and SOC 2 on the roadmap.
  badges: ["ISO 27001 — in progress", "Made in India"],
  // Was "Join 200+ companies using TenderCraft AI to dominate the public procurement space."
  closingSubtitle:
    "Built with bid teams who live inside GeM, CPPP and state portals every week.",
} as const;

export const PRICING = {
  title: "Transparent Pricing",
  subtitle: "Plans that scale with your contract volume.",
  plans: [
    {
      name: "Starter",
      price: "₹4,999",
      period: "/mo",
      blurb: "For boutique firms and freelancers.",
      features: ["3 Bids / Month", "AI Portal Monitoring", "Standard Email Support"],
      cta: "Start Free Trial",
      featured: false,
    },
    {
      name: "Professional",
      price: "₹14,999",
      period: "/mo",
      blurb: "For high-growth enterprise teams.",
      features: [
        "Unlimited Bids",
        "Compliance Matrix Gen",
        "Technical Writer AI",
        "24/7 Priority Support",
      ],
      cta: "Go Professional",
      featured: true,
      tag: "MOST POPULAR",
    },
    {
      name: "Enterprise",
      price: "Custom",
      period: "",
      blurb: "For Fortune 500 & PSU contractors.",
      features: [
        "Custom LLM Fine-tuning",
        "On-Premise Deployment",
        "Dedicated Account Manager",
        "API Access",
      ],
      cta: "Contact Sales",
      featured: false,
    },
  ],
} as const;

export const CLOSING = {
  title: "Ready to Win More Government Contracts?",
  primaryCta: "Book a Demo",
  secondaryCta: "Contact Us",
} as const;

export const FOOTER = {
  blurb:
    "The intelligent layer for high-stakes government procurement. Designed for precision, " +
    "built for winning.",
  columns: [
    {
      title: "Product",
      links: [
        { label: "Features", href: "#features" },
        { label: "RFP Analysis", href: "#features" },
        { label: "Compliance Matrix", href: "#features" },
        { label: "Pricing", href: "#pricing" },
      ],
    },
    {
      title: "Industries",
      links: [
        { label: "IT & Software", href: "#sectors" },
        { label: "Defence", href: "#sectors" },
        { label: "Railways", href: "#sectors" },
        { label: "Infrastructure", href: "#sectors" },
      ],
    },
    {
      title: "Company",
      links: [
        { label: "About Us", href: "#" },
        { label: "Security", href: "#" },
        { label: "Contact Us", href: "#" },
        { label: "Careers", href: "#" },
      ],
    },
    {
      title: "Legal",
      links: [
        { label: "Privacy Policy", href: "#" },
        { label: "Terms of Service", href: "#" },
        { label: "Cookie Policy", href: "#" },
      ],
    },
  ],
  legal: "© 2026 TenderCraft AI. Made in India with precision.",
  disclaimer: "Outputs are decision support, not legal advice.",
} as const;
