/**
 * Loads expression, mood, and style data from shared YAML files.
 * Converts snake_case keys to camelCase so React components work unchanged.
 *
 * Shared YAML lives in ../../shared/ and is maintained as the single source
 * of truth for both the Python runtime and this React design tool.
 */
import yaml from "js-yaml";

import expressionsRaw from "../../shared/expressions.yaml?raw";
import stylesRaw from "../../shared/styles.yaml?raw";
import moodsRaw from "../../shared/moods.yaml?raw";

/* ── snake_case → camelCase conversion ────────────────────── */

function snakeToCamel(str) {
  return str.replace(/_([a-z0-9])/g, (_, ch) => ch.toUpperCase());
}

/**
 * Recursively convert all object keys from snake_case to camelCase.
 * Arrays are traversed element-by-element; primitives pass through.
 */
function camelizeKeys(obj) {
  if (Array.isArray(obj)) {
    return obj.map(camelizeKeys);
  }
  if (obj !== null && typeof obj === "object") {
    return Object.fromEntries(
      Object.entries(obj).map(([key, value]) => [
        snakeToCamel(key),
        camelizeKeys(value),
      ]),
    );
  }
  return obj;
}

/* ── Parse YAML ───────────────────────────────────────────── */

const expressionsData = camelizeKeys(yaml.load(expressionsRaw));
const stylesData = camelizeKeys(yaml.load(stylesRaw));
const moodsData = camelizeKeys(yaml.load(moodsRaw));

/* ── Expressions ──────────────────────────────────────────── */

export const EXPRESSIONS = expressionsData.expressions ?? expressionsData;

export const MOOD_LIST = Object.keys(EXPRESSIONS);

/* ── Styles ───────────────────────────────────────────────── */

export const STYLES = stylesData.styles ?? stylesData;

export const STYLE_LIST = Object.keys(STYLES);

export const DEFAULT_STYLE =
  (stylesData.defaultStyle ?? stylesData.default ?? Object.keys(STYLES)[0]);

/* ── Mood icons (from moods.yaml) ─────────────────────────── */

export const MOOD_ICONS = moodsData.moodIcons ?? moodsData.icons ?? moodsData ?? {};
