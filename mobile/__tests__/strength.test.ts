import { readFileSync } from 'fs';
import { join } from 'path';

import { parseStrength, strengthsEquivalent } from '../src/text/strength';

interface ParseCase {
  input: string;
  expected: string;
}
interface EqCase {
  a: string;
  b: string;
  expected: boolean;
}

const cases = JSON.parse(
  readFileSync(join(__dirname, '..', '..', 'shared', 'fixtures', 'strength.json'), 'utf-8'),
) as { parse: ParseCase[]; equivalent: EqCase[] };

describe('parseStrength (shared fixture)', () => {
  test.each(cases.parse)('"$input" -> "$expected"', ({ input, expected }) => {
    expect(parseStrength(input)).toBe(expected);
  });
  test('stable on its own output', () => {
    for (const c of cases.parse) {
      const once = parseStrength(c.input);
      expect(parseStrength(once)).toBe(once);
    }
  });
});

describe('strengthsEquivalent (shared fixture)', () => {
  test.each(cases.equivalent)('$a ~ $b = $expected', ({ a, b, expected }) => {
    expect(strengthsEquivalent(a, b)).toBe(expected);
    expect(strengthsEquivalent(b, a)).toBe(expected);
  });
});
