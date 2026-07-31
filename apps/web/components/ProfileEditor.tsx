"use client";

import { useState } from "react";

import { translator, type Locale } from "@/lib/i18n";

import { ProfileForm, type ProfileData } from "./ProfileForm";

/** Toggles the read view into the edit form. Keeps the server-rendered profile page a
 *  server component while making "Update profile" actually do something. */
export function ProfileEditor({
  initial,
  locale = "en",
  market = "IN",
}: {
  initial: ProfileData;
  locale?: Locale;
  market?: string;
}) {
  const [editing, setEditing] = useState(false);
  const t = translator(locale);

  if (!editing) {
    return (
      <button
        type="button"
        data-edit-profile
        onClick={() => setEditing(true)}
        className="shrink-0 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover"
      >
        {t("Update profile")}
      </button>
    );
  }
  return (
    <div className="fixed inset-0 z-30 overflow-y-auto bg-ink/40 p-6">
      <div className="mx-auto max-w-3xl rounded-card bg-ground p-card shadow-xl">
        <h1 className="mb-4 font-heading text-xl font-semibold text-ink">
          {t("Update vendor profile")}
        </h1>
        <ProfileForm
          initial={initial}
          onClose={() => setEditing(false)}
          locale={locale}
          market={market}
        />
      </div>
    </div>
  );
}
