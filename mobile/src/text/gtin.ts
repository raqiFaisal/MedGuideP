/**
 * GTIN check-digit validation and conversion to GTIN-14 (GS1 mod-10).
 * Mirror of engine/medguide_engine/text/gtin.py; tested against shared/fixtures/gtin.json.
 */

const SUPPORTED_LENGTHS: ReadonlySet<number> = new Set([8, 12, 13, 14]);

/** Check digit for a GTIN body (all digits except the last). */
export function gs1CheckDigit(body: string): number {
  let total = 0;
  for (let pos = 0; pos < body.length; pos++) {
    const digit = Number(body[body.length - 1 - pos]);
    total += digit * (pos % 2 === 0 ? 3 : 1);
  }
  return (10 - (total % 10)) % 10;
}

export function isValidGtin(code: string): boolean {
  const c = code.trim();
  if (!SUPPORTED_LENGTHS.has(c.length) || !/^[0-9]+$/.test(c)) return false;
  return gs1CheckDigit(c.slice(0, -1)) === Number(c[c.length - 1]);
}

/** Zero-padded GTIN-14, or null if the code is not a valid GTIN. */
export function toGtin14(code: string): string | null {
  const c = code.trim();
  return isValidGtin(c) ? c.padStart(14, '0') : null;
}
