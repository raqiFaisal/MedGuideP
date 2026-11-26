/**
 * Text normalization — TypeScript mirror of engine/medguide_engine/text/normalize.py.
 * Both are tested against shared/fixtures/text_normalization.json. Change them together.
 */

const LETTER_MAP: Readonly<Record<string, string>> = {
  'أ': 'ا', // أ -> ا
  'إ': 'ا', // إ -> ا
  'آ': 'ا', // آ -> ا
  'ٱ': 'ا', // ٱ -> ا
  'ى': 'ي', // ى -> ي
  'ی': 'ي', // ی (Farsi yeh) -> ي
  'ک': 'ك', // ک (keheh) -> ك
  'ة': 'ه', // ة -> ه
  'ؤ': 'و', // ؤ -> و
  'ئ': 'ي', // ئ -> ي
  'ء': '', // ء removed
  '٫': '.', // ٫ Arabic decimal separator
  '٬': '', // ٬ Arabic thousands separator
  'ـ': '', // ـ tatweel
};

const TASHKEEL = /[ً-ٰٟ]/g;
const WHITESPACE = /\s+/g;
const DIGIT_LETTER = /([0-9])([A-Zء-ي])/g;
const LETTER_DIGIT = /([A-Zء-ي])([0-9])/g;

function mapDigit(ch: string): string | undefined {
  const code = ch.charCodeAt(0);
  if (code >= 0x0660 && code <= 0x0669) return String(code - 0x0660);
  if (code >= 0x06f0 && code <= 0x06f9) return String(code - 0x06f0);
  return undefined;
}

function isAsciiDigit(ch: string | undefined): boolean {
  return ch !== undefined && ch >= '0' && ch <= '9';
}

function isKept(ch: string): boolean {
  return (
    (ch >= 'A' && ch <= 'Z') ||
    (ch >= '0' && ch <= '9') ||
    (ch >= 'ء' && ch <= 'ي') ||
    ch === ' '
  );
}

/** Remove diacritics/tatweel, unify letter variants, convert digits, collapse spaces. */
export function normalizeArabic(text: string): string {
  const stripped = text.replace(TASHKEEL, '');
  let out = '';
  for (const ch of stripped) {
    const digit = mapDigit(ch);
    if (digit !== undefined) out += digit;
    else if (ch in LETTER_MAP) out += LETTER_MAP[ch];
    else out += ch;
  }
  return out.replace(WHITESPACE, ' ').trim();
}

/**
 * Full normalization for matching: Arabic rules, uppercase Latin, strip symbols,
 * keep decimal points between digits, split digits from letters.
 */
export function normalizeText(text: string): string {
  let t = normalizeArabic(text).toUpperCase();
  t = t.replace(/[µμΜ]/g, 'MC');
  const chars = Array.from(t);
  let kept = '';
  chars.forEach((ch, i) => {
    if (ch === '.') {
      kept += isAsciiDigit(chars[i - 1]) && isAsciiDigit(chars[i + 1]) ? '.' : ' ';
    } else {
      kept += isKept(ch) ? ch : ' ';
    }
  });
  kept = kept.replace(DIGIT_LETTER, '$1 $2').replace(LETTER_DIGIT, '$1 $2');
  return kept.replace(WHITESPACE, ' ').trim();
}
