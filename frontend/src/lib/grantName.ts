"use client";

// A grant's name on screen. Real grants read "Untitled grant" until the award
// letter gives a title or an award number. A sample grant reads its sample's
// own name instead (the name the Sample dropdown lists), only until then.

import { useSamples, type GrantSummary, type SampleOption } from "./api";

export const UNTITLED_GRANT = "Untitled grant";

/** The grant's title, else its award number, else a sample's own name, else "Untitled grant". */
export function grantDisplayName(summary: GrantSummary, samples?: SampleOption[]): string {
  const { grant } = summary;
  if (grant.title) return grant.title;
  if (grant.award_number) return grant.award_number;
  const sample = grant.sample;
  if (sample) {
    const option = samples?.find((o) => o.choice === sample.choice);
    if (option?.name) return option.name;
  }
  return UNTITLED_GRANT;
}

/** grantDisplayName with the sample choices loaded from GET /samples. */
export function useGrantDisplayName(): (summary: GrantSummary) => string {
  const samples = useSamples().data;
  return (summary) => grantDisplayName(summary, samples);
}
