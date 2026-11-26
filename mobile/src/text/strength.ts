/**
 * Strength parsing and comparison — mirror of engine/medguide_engine/text/strength.py.
 * Both are tested against shared/fixtures/strength.json. Change them together.
 */
import { normalizeArabic } from './normalize';

// Arabic spellings as they look AFTER normalizeArabic. Longer spellings first.
const UNIT_ALIASES: readonly (readonly [string, string])[] = [
  ['ميكروغرام', 'MCG'],
  ['ميكروجرام', 'MCG'],
  ['مكجم', 'MCG'],
  ['مكغ', 'MCG'],
  ['ملجم', 'MG'],
  ['ملغ', 'MG'],
  ['مجم', 'MG'],
  ['مغ', 'MG'],
  ['غرام', 'G'],
  ['جرام', 'G'],
  ['جم', 'G'],
  ['غم', 'G'],
  ['مليلتر', 'ML'],
  ['ملل', 'ML'],
  ['مل', 'ML'],
  ['وحده دوليه', 'IU'],
  ['٪', '%'],
  ['I.U.', 'IU'],
  ['MCG', 'MCG'],
  ['UG', 'MCG'],
  ['MG', 'MG'],
  ['GM', 'G'],
  ['ML', 'ML'],
  ['IU', 'IU'],
  ['G', 'G'],
  ['%', '%'],
];
const UNIT_LOOKUP: ReadonlyMap<string, string> = new Map(UNIT_ALIASES);
const escapeRe = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const UNIT_PATTERN = UNIT_ALIASES.map(([alias]) => escapeRe(alias)).join('|');
const NUM = '(\\d+(?:\\.\\d+)?)';
const NOT_LETTER = '(?![A-Z\\u0621-\\u064A])';
const AMOUNT_SOURCE =
  `${NUM}\\s*(${UNIT_PATTERN})${NOT_LETTER}` +
  `(?:\\s*/\\s*${NUM}?\\s*(${UNIT_PATTERN})${NOT_LETTER})?`;
const THOUSANDS = /(\d),(\d{3})(?!\d)/g;
const DECIMAL_COMMA = /(\d),(\d)/g;

const MASS_TO_MG: Readonly<Record<string, number>> = { MG: 1, G: 1000, MCG: 0.001 };
const VOLUME_OR_MASS_DENOMINATOR: ReadonlySet<string> = new Set(['ML', 'G']);

export interface StrengthComponent {
  value: string;
  unit: string;
  perValue: string | null;
  perUnit: string | null;
}

function componentText(c: StrengthComponent): string {
  const base = `${c.value} ${c.unit}`;
  if (c.perUnit === null) return base;
  const per = c.perValue ? `${c.perValue} ${c.perUnit}` : c.perUnit;
  return `${base}/${per}`;
}

function cleanNumber(num: string): string {
  return num.includes('.') ? num.replace(/0+$/, '').replace(/\.$/, '') : num;
}

function prepare(text: string): string {
  let t = normalizeArabic(text).toUpperCase();
  t = t.replace(/[µμΜ]/g, 'MC');
  t = t.replace(THOUSANDS, '$1$2');
  return t.replace(DECIMAL_COMMA, '$1.$2');
}

function lookupUnit(alias: string): string {
  const unit = UNIT_LOOKUP.get(alias);
  if (unit === undefined) throw new Error(`unknown unit alias: ${alias}`);
  return unit;
}

export function parseComponents(text: string): StrengthComponent[] {
  const components: StrengthComponent[] = [];
  const re = new RegExp(AMOUNT_SOURCE, 'g');
  for (const m of prepare(text).matchAll(re)) {
    const value = cleanNumber(m[1] ?? '');
    const unit = lookupUnit(m[2] ?? '');
    const perValue = m[3] ? cleanNumber(m[3]) : null;
    const perUnit = m[4] ? lookupUnit(m[4]) : null;
    if (perUnit !== null && !VOLUME_OR_MASS_DENOMINATOR.has(perUnit)) {
      // "500mg/125mg": two ingredients, not a concentration.
      components.push({ value, unit, perValue: null, perUnit: null });
      if (perValue !== null) components.push({ value: perValue, unit: perUnit, perValue: null, perUnit: null });
      continue;
    }
    if (perUnit === null && unit === 'ML') continue; // standalone volume = pack size
    components.push({ value, unit, perValue, perUnit });
  }
  return components;
}

/** Normalized strength string, e.g. '250 MG/5 ML' or '500 MG + 125 MG'; '' if none. */
export function parseStrength(text: string): string {
  return parseComponents(text).map(componentText).join(' + ');
}

type Key = readonly [string, number];

function key(c: StrengthComponent): Key {
  const value = Number(c.value);
  const factor = MASS_TO_MG[c.unit];
  if (c.perUnit !== null) {
    const per = c.perValue ? Number(c.perValue) : 1;
    const kind = `conc_${factor === undefined ? c.unit : 'mass'}_${c.perUnit}`;
    return [kind, (value * (factor ?? 1)) / per];
  }
  if (factor !== undefined) return ['mass', value * factor];
  return [c.unit, value];
}

function compareKeys(a: Key, b: Key): number {
  if (a[0] !== b[0]) return a[0] < b[0] ? -1 : 1;
  return a[1] - b[1];
}

/** True if both strengths describe the same amounts (unit-converted, order-insensitive). */
export function strengthsEquivalent(a: string, b: string): boolean {
  const ka = parseComponents(a).map(key).sort(compareKeys);
  const kb = parseComponents(b).map(key).sort(compareKeys);
  if (ka.length === 0 || ka.length !== kb.length) return false;
  return ka.every((x, i) => {
    const y = kb[i];
    if (y === undefined || x[0] !== y[0]) return false;
    return Number.isFinite(x[1]) && Number.isFinite(y[1]) && Math.abs(x[1] - y[1]) <= 1e-9 * Math.max(1, Math.abs(x[1]), Math.abs(y[1]));
  });
}
