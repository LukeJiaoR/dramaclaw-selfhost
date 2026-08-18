// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { safeLocalStorageSet } from "@/lib/localStorageQuota";

export const REWRITE_TARGET_BEATS_MIN = 5;
export const REWRITE_TARGET_BEATS_MAX = 80;
export const REWRITE_BEAT_CHARS_MIN_MIN = 4;
export const REWRITE_BEAT_CHARS_MIN_MAX = 50;
export const REWRITE_BEAT_CHARS_MAX_MIN = 4;
export const REWRITE_BEAT_CHARS_MAX_MAX = 80;

export interface RewriteSettings {
  targetBeats: number;
  beatCharsMin: number;
  beatCharsMax: number;
}

export const DEFAULT_REWRITE_SETTINGS: RewriteSettings = {
  targetBeats: 18,
  beatCharsMin: 14,
  beatCharsMax: 20,
};

function clampInteger(value: unknown, fallback: number, min: number, max: number) {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, Math.round(parsed)));
}

export function normalizeRewriteSettings(value: Partial<RewriteSettings>): RewriteSettings {
  const targetBeats = clampInteger(
    value.targetBeats,
    DEFAULT_REWRITE_SETTINGS.targetBeats,
    REWRITE_TARGET_BEATS_MIN,
    REWRITE_TARGET_BEATS_MAX,
  );
  const beatCharsMin = clampInteger(
    value.beatCharsMin,
    DEFAULT_REWRITE_SETTINGS.beatCharsMin,
    REWRITE_BEAT_CHARS_MIN_MIN,
    REWRITE_BEAT_CHARS_MIN_MAX,
  );
  const requestedMax = clampInteger(
    value.beatCharsMax,
    DEFAULT_REWRITE_SETTINGS.beatCharsMax,
    REWRITE_BEAT_CHARS_MAX_MIN,
    REWRITE_BEAT_CHARS_MAX_MAX,
  );

  return {
    targetBeats,
    beatCharsMin,
    beatCharsMax: Math.max(beatCharsMin, requestedMax),
  };
}

export function rewriteSettingsStorageKey(project: string, episode: number) {
  return `st.episode.${encodeURIComponent(project)}.e${episode}.rewrite-settings`;
}

export function loadRewriteSettings(project: string, episode: number): RewriteSettings {
  if (typeof window === "undefined") return { ...DEFAULT_REWRITE_SETTINGS };
  try {
    const raw = window.localStorage.getItem(rewriteSettingsStorageKey(project, episode));
    if (!raw) return { ...DEFAULT_REWRITE_SETTINGS };
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { ...DEFAULT_REWRITE_SETTINGS };
    }
    return normalizeRewriteSettings(parsed as Partial<RewriteSettings>);
  } catch {
    return { ...DEFAULT_REWRITE_SETTINGS };
  }
}

export function saveRewriteSettings(
  project: string,
  episode: number,
  settings: RewriteSettings,
) {
  return safeLocalStorageSet(
    rewriteSettingsStorageKey(project, episode),
    JSON.stringify(normalizeRewriteSettings(settings)),
  );
}
