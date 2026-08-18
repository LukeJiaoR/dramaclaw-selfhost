// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { beforeEach, describe, expect, it } from "vitest";

import {
  DEFAULT_REWRITE_SETTINGS,
  loadRewriteSettings,
  normalizeRewriteSettings,
  rewriteSettingsStorageKey,
  saveRewriteSettings,
} from "@/lib/rewrite-settings";

describe("rewrite settings persistence", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("restores settings independently for each project episode", () => {
    saveRewriteSettings("project-a", 1, {
      targetBeats: 6,
      beatCharsMin: 40,
      beatCharsMax: 70,
    });

    expect(loadRewriteSettings("project-a", 1)).toEqual({
      targetBeats: 6,
      beatCharsMin: 40,
      beatCharsMax: 70,
    });
    expect(loadRewriteSettings("project-a", 2)).toEqual(DEFAULT_REWRITE_SETTINGS);
    expect(loadRewriteSettings("project-b", 1)).toEqual(DEFAULT_REWRITE_SETTINGS);
  });

  it("normalizes corrupt and out-of-range persisted values", () => {
    window.localStorage.setItem(
      rewriteSettingsStorageKey("demo", 1),
      JSON.stringify({ targetBeats: 999, beatCharsMin: 40, beatCharsMax: 20 }),
    );

    expect(loadRewriteSettings("demo", 1)).toEqual({
      targetBeats: 80,
      beatCharsMin: 40,
      beatCharsMax: 40,
    });
    expect(normalizeRewriteSettings({ targetBeats: Number.NaN })).toEqual(
      DEFAULT_REWRITE_SETTINGS,
    );
  });

  it("falls back to defaults for malformed storage", () => {
    window.localStorage.setItem(rewriteSettingsStorageKey("demo", 1), "not-json");
    expect(loadRewriteSettings("demo", 1)).toEqual(DEFAULT_REWRITE_SETTINGS);
  });
});
