import dictionary from '../../shared/dictionaries/dosage_forms.json';
import { DOSAGE_FORMS, detectDosageForm } from '../src/text/dosageForm';
import { normalizeText } from '../src/text/normalize';

describe('detectDosageForm (shared dictionary)', () => {
  test.each(dictionary.cases)('"$input" -> $expected', ({ input, expected }) => {
    expect(detectDosageForm(input)).toBe(expected);
  });

  test('phrases are already normalized', () => {
    for (const entry of dictionary.forms) {
      for (const phrase of entry.phrases) expect(normalizeText(phrase)).toBe(phrase);
    }
  });

  test('codes are unique', () => {
    const codes = DOSAGE_FORMS.map((f) => f.code);
    expect(new Set(codes).size).toBe(codes.length);
  });
});
