import { readFileSync } from 'fs';
import { join } from 'path';

import { gs1CheckDigit, isValidGtin, toGtin14 } from '../src/text/gtin';
import { normalizeArabic, normalizeText } from '../src/text/normalize';

interface TextCase {
  input: string;
  expected: string;
  rule: string;
}
interface GtinCase {
  input: string;
  valid: boolean;
  gtin14: string | null;
  note: string;
}

const FIXTURES = join(__dirname, '..', '..', 'shared', 'fixtures');
const load = <T>(name: string): T =>
  JSON.parse(readFileSync(join(FIXTURES, name), 'utf-8')) as T;

const textCases = load<{ normalize_arabic: TextCase[]; normalize_text: TextCase[] }>(
  'text_normalization.json',
);
const gtinCases = load<{ cases: GtinCase[] }>('gtin.json').cases;

describe('normalizeArabic (shared fixture)', () => {
  test.each(textCases.normalize_arabic)('$rule', ({ input, expected }) => {
    expect(normalizeArabic(input)).toBe(expected);
  });
});

describe('normalizeText (shared fixture)', () => {
  test.each(textCases.normalize_text)('$rule', ({ input, expected }) => {
    expect(normalizeText(input)).toBe(expected);
  });

  test('is idempotent', () => {
    for (const c of [...textCases.normalize_arabic, ...textCases.normalize_text]) {
      const once = normalizeText(c.input);
      expect(normalizeText(once)).toBe(once);
    }
  });
});

describe('GTIN (shared fixture)', () => {
  test.each(gtinCases)('isValidGtin: $note', ({ input, valid }) => {
    expect(isValidGtin(input)).toBe(valid);
  });
  test.each(gtinCases)('toGtin14: $note', ({ input, gtin14 }) => {
    expect(toGtin14(input)).toBe(gtin14);
  });
  test('check digit examples', () => {
    expect(gs1CheckDigit('400638133393')).toBe(1);
    expect(gs1CheckDigit('03600029145')).toBe(2);
  });
});
