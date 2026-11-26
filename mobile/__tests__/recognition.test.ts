import type { SQLiteDatabase } from 'expo-sqlite';
import { nameSimilarity, parseBarcode, recognize, type Line } from '../src/recognition/evidence';

const code = { gtin: '04006381333931' };
const line = (text: string): Line => ({ language: 'latin', text, confidence: .91, polygon: [] });
const p1 = { id: 1, brand_name_en: 'SAMPLEMED', strength_normalized: '500 MG' };
const p2 = { id: 2, brand_name_en: 'SAMPLEMED', strength_normalized: '250 MG' };

function catalog(shared = false, unknown = false) {
  return {
    getAllAsync: async (sql: string) => {
      if (unknown) return [];
      if (sql.includes('product_identifiers')) return shared ? [p1, p2] : [p1];
      return [p1, p2];
    },
  } as unknown as SQLiteDatabase;
}

test('checks GS1 GTIN, leap-month date, and separators', () => {
  expect(parseBarcode(']d201040063813339311728020010AB12\x1d21XYZ')).toEqual(
    { ...code, expiry: '2028-02-29', lot: 'AB12', serial: 'XYZ' },
  );
  expect(parseBarcode('(01)04006381333932')).toBeNull();
  expect(parseBarcode('(01)04006381333931(17)280230')).toEqual(code);
  expect(parseBarcode('4006381333931')).toEqual(code);
});

test('only the repeated unambiguous GTIN is confirmed', async () => {
  await expect(recognize(catalog(), [code], [], new Map())).resolves.toMatchObject({ status: 'NEEDS_CONFIRMATION' });
  await expect(recognize(catalog(), [code, code], [line('SAMPLEMED 500MG'), line('SAMPLEMED .5 G')], new Map()))
    .resolves.toMatchObject({ status: 'NEEDS_CONFIRMATION' }); // A leading decimal dot is unreliable OCR here.
  await expect(recognize(catalog(), [code, code], [line('SAMPLEMED 500MG'), line('SAMPLEMED 0.5 G')], new Map()))
    .resolves.toMatchObject({ status: 'IDENTIFIED' });
  await expect(recognize(catalog(true), [code, code], [], new Map())).resolves.toMatchObject({ reason: 'SHARED_GTIN' });
});

test('rejects unknowns and asks on strength conflicts or visual-only matches', async () => {
  await expect(recognize(catalog(), [code, code], [line('SAMPLEMED 250 MG')], new Map([[2, .96]])))
    .resolves.toMatchObject({ status: 'NEEDS_CONFIRMATION', reason: 'CONFLICTING_TEXT' });
  await expect(recognize(catalog(true, true), [code, code], [], new Map()))
    .resolves.toMatchObject({ status: 'NOT_IDENTIFIED' });
  await expect(recognize(catalog(), [], [], new Map([[1, .99]])))
    .resolves.toMatchObject({ status: 'NEEDS_CONFIRMATION' });
});

test('compares normalized token sets and spaced OCR variants', () => {
  expect(nameSimilarity('SAMPLEMED', 'SAMPLEMED EXTRA')).toBe(1);
  expect(nameSimilarity('SAMPLEMED', 'SAMPLED')).toBeGreaterThan(.83);
});

test('a damaged OCR concentration with a zero denominator can be processed', async () => {
  await expect(recognize(catalog(), [code, code], [line('SAMPLEMED 250 MG/0 ML')], new Map()))
    .resolves.toMatchObject({ status: 'NEEDS_CONFIRMATION' });
});
