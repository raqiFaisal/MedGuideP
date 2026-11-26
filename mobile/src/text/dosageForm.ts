/**
 * Dosage-form detection — reads the same shared/dictionaries/dosage_forms.json
 * as engine/medguide_engine/text/dosage_form.py, so the rules are identical.
 */
import dictionary from '../../../shared/dictionaries/dosage_forms.json';
import { normalizeText } from './normalize';

export interface DosageForm {
  code: string;
  labelAr: string;
  labelEn: string;
  pattern: RegExp;
}

const escapeRe = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export const DOSAGE_FORMS: readonly DosageForm[] = dictionary.forms.map((entry) => {
  // Longest phrases first so "F C TABS" is preferred over "F C" inside one rule.
  const phrases = [...entry.phrases].sort((a, b) => b.length - a.length);
  return {
    code: entry.code,
    labelAr: entry.label_ar,
    labelEn: entry.label_en,
    pattern: new RegExp(`(?:^| )(?:${phrases.map(escapeRe).join('|')})(?= |$)`),
  };
});

/** Canonical dosage-form code, or null if no rule matches. */
export function detectDosageForm(text: string): string | null {
  const normalized = normalizeText(text);
  return DOSAGE_FORMS.find((f) => f.pattern.test(normalized))?.code ?? null;
}
