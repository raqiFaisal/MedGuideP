import type { SQLiteDatabase } from 'expo-sqlite';
import rules from '../../../shared/recognition.json';
import { type Product, productColumns, productTables, searchQuery } from '../catalog/queries';
import { detectDosageForm } from '../text/dosageForm';
import { toGtin14 } from '../text/gtin';
import { normalizeText } from '../text/normalize';
import { parseStrength, strengthsEquivalent } from '../text/strength';

export type Barcode = { gtin: string; expiry?: string; lot?: string; serial?: string };
export type Line = { language: 'arabic' | 'latin'; text: string; confidence: number; polygon: number[][] };
type Candidate = { product: Product & { dosage_form?: string }; score: number; evidence: string[]; conflict: boolean };
export type Result = {
  status: 'IDENTIFIED' | 'NEEDS_CONFIRMATION' | 'NOT_IDENTIFIED';
  reason: string;
  candidates: Candidate[];
  barcodes: Barcode[];
  lines: Line[];
};

const separator = '\x1d';
const widths: Readonly<Record<string, number>> = { '01': 14, '17': 6, '10': 0, '21': 0 };

export function parseBarcode(raw: string): Barcode | null {
  let value = raw.trim().replace(/^\](?:d2|C1)/, '').replace(/^\x1d+/, '');
  const direct = toGtin14(value);
  if (direct) return { gtin: direct };
  const fields: [string, string][] = [];
  if (value.startsWith('(')) {
    const matches = [...value.matchAll(/\((\d{2,4})\)/g)];
    matches.forEach((m, i) => fields.push([m[1]!, value.slice(m.index! + m[0].length, matches[i + 1]?.index)]));
  } else {
    while (value) {
      const ai = value.slice(0, 2);
      const width = widths[ai];
      if (width === undefined) break;
      value = value.slice(2);
      const end = width || (value.includes(separator) ? value.indexOf(separator) : value.length);
      fields.push([ai, value.slice(0, end)]);
      value = value.slice(end).replace(/^\x1d/, '');
    }
  }
  const out: Partial<Barcode> = {};
  const seen = new Set<string>();
  for (const [ai, field] of fields) {
    if (widths[ai] === undefined) continue;
    if (seen.has(ai)) return null;
    seen.add(ai);
    if (ai === '01') {
      const gtin = /^\d{14}$/.test(field) ? toGtin14(field) : null;
      if (!gtin) return null;
      out.gtin = gtin;
    } else if (ai === '17' && /^\d{6}$/.test(field)) {
      const year = 2000 + Number(field.slice(0, 2));
      const month = Number(field.slice(2, 4));
      const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
      const day = Number(field.slice(4)) || last;
      if (month >= 1 && month <= 12 && day <= last) {
        out.expiry = new Date(Date.UTC(year, month - 1, day)).toISOString().slice(0, 10);
      }
    } else if (/^[A-Za-z0-9!%&'*+,./:;=<>?_-]{1,20}$/.test(field)) {
      if (ai === '10') out.lot = field;
      if (ai === '21') out.serial = field;
    }
  }
  return out.gtin ? { ...out, gtin: out.gtin } : null;
}

const common = new Set('THE EACH REG MFG EXP BATCH CONTAINS TABLETS TABLET CAPSULES CAPSULE FILM COATED MG MCG G ML IU FOR ORAL USE PACK LOT كل يحتوي اقراص قرص كبسوله كبسولات مغ مل مجم ملجم ملغ شراب دواء'.split(' '));
function terms(value: string) {
  return normalizeText(value).split(' ').filter(t => t && !common.has(t) && /[^0-9]/.test(t));
}

function indelSimilarity(a: string, b: string) {
  let previous = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const current = [i];
    for (let j = 1; j <= b.length; j++) {
      current[j] = Math.min(previous[j]! + 1, current[j - 1]! + 1, previous[j - 1]! + (a[i - 1] === b[j - 1] ? 0 : 2));
    }
    previous = current;
  }
  return 1 - previous[b.length]! / (a.length + b.length);
}

function jaroWinkler(a: string, b: string) {
  const range = Math.max(0, Math.floor(Math.max(a.length, b.length) / 2) - 1);
  const matched = Array<boolean>(b.length).fill(false);
  const fromA: string[] = [];
  for (let i = 0; i < a.length; i++) {
    for (let j = Math.max(0, i - range); j <= Math.min(i + range, b.length - 1); j++) {
      if (!matched[j] && a[i] === b[j]) {
        matched[j] = true;
        fromA.push(a[i]!);
        break;
      }
    }
  }
  const count = fromA.length;
  if (!count) return 0;
  const fromB = b.split('').filter((_, i) => matched[i]);
  const transposed = fromA.filter((letter, i) => letter !== fromB[i]).length / 2;
  const jaro = (count / a.length + count / b.length + (count - transposed) / count) / 3;
  let prefix = 0;
  while (prefix < Math.min(4, a.length, b.length) && a[prefix] === b[prefix]) prefix++;
  return jaro > .7 ? jaro + prefix * .1 * (1 - jaro) : jaro;
}

export function nameSimilarity(a: string, b: string) {
  const left = new Set(a.split(' '));
  const right = new Set(b.split(' '));
  const common = [...left].filter(t => right.has(t)).sort().join(' ');
  const sorted = (tokens: Set<string>, other: Set<string>) =>
    [common, [...tokens].filter(t => !other.has(t)).sort().join(' ')].filter(Boolean).join(' ');
  const x = sorted(left, right);
  const y = sorted(right, left);
  return Math.max(indelSimilarity(x, y), common ? indelSimilarity(common, x) : 0,
    common ? indelSimilarity(common, y) : 0, jaroWinkler(a, b));
}

export async function recognize(db: SQLiteDatabase, barcodes: Barcode[], lines: Line[], visual: Map<number, number>): Promise<Result> {
  const codes = [...new Set(barcodes.map(b => b.gtin))];
  const repeated = codes.length === 1 && barcodes.length >= 2;
  const barcodeIds = new Set<number>();
  const wanted = new Set<number>();
  for (const code of codes) {
    const query = searchQuery(code, '')!;
    const products = await db.getAllAsync<Product>(query.sql, query.parameters);
    products.forEach(p => { barcodeIds.add(p.id); wanted.add(p.id); });
  }
  const usable = lines.filter(l => l.confidence >= rules.min_ocr_line).slice(0, 50);
  const text = usable.map(l => l.text).join(' ');
  const strengths: string[] = [];
  for (const line of usable) {
    const value = parseStrength(line.text);
    if (value && !strengths.some(old => strengthsEquivalent(value, old))) strengths.push(value);
  }
  const strength = strengths.join(" + ");
  const form = detectDosageForm(text);
  const queries = usable.map(l => ({ text: terms(l.text).join(' '), confidence: l.confidence }));
  const tokens = new Set(queries.slice(0, 12).flatMap(q => q.text.split(' ').filter(t => t.length >= 3)));
  for (const token of [...tokens].slice(0, 35)) {
    const query = searchQuery(token, '');
    if (!query) continue;
    const rows = await db.getAllAsync<Product>(query.sql.replace(/LIMIT 51$/, 'LIMIT 20'), query.parameters);
    rows.forEach(p => wanted.add(p.id));
  }
  visual.forEach((score, pid) => { if (score >= rules.min_visual_similarity) wanted.add(pid); });
  if (!wanted.size) return { status: 'NOT_IDENTIFIED', reason: 'NO_CATALOG_MATCH', candidates: [], barcodes, lines };
  const ids = [...wanted];
  const products: Candidate["product"][] = [];
  for (let offset = 0; offset < ids.length; offset += 500) {
    const batch = ids.slice(offset, offset + 500);
    products.push(...await db.getAllAsync<Candidate["product"]>(productColumns + ", p.dosage_form" +
      productTables + " WHERE p.id IN (" + batch.map(() => "?").join(",") + ")", batch));
  }
  const ranked: Candidate[] = [];
  for (const product of products) {
    const names = [product.brand_name_ar, product.brand_name_en].map(name => terms(name ?? '').join(' ')).filter(Boolean);
    let similarity = 0;
    let confidence = 0;
    for (const name of names) for (const query of queries) {
      if (!query.text) continue;
      const value = nameSimilarity(name, query.text);
      if (value > similarity || value === similarity && query.confidence > confidence) {
        similarity = value;
        confidence = query.confidence;
      }
    }
    const barcode = barcodeIds.has(product.id);
    const brand = similarity >= rules.min_name_similarity;
    const vector = visual.get(product.id) ?? 0;
    const visualMatch = vector >= rules.min_visual_similarity;
    if (!barcode && !brand && !visualMatch) continue;
    const expected = product.strength_normalized ?? '';
    const match = strengthsEquivalent(strength, expected);
    const conflict = Boolean(strength && parseStrength(expected) && !match);
    const company = normalizeText(product.manufacturer ?? '');
    const manufacturer = Boolean(company && (' ' + normalizeText(text) + ' ').includes(' ' + company + ' '));
    const formMatch = Boolean(form && form === product.dosage_form);
    const w = rules.weights;
    const score = w.barcode * Number(barcode) + w.name * similarity + w.ocr * confidence * Number(brand) +
      w.strength * (Number(match) - Number(conflict)) + w.manufacturer * Number(manufacturer) +
      w.form * Number(formMatch) + w.visual * Math.max(0, vector);
    const evidence = Object.entries({ barcode, text: brand, visual: visualMatch, strength: match, manufacturer, form: formMatch })
      .filter(([, present]) => present).map(([label]) => label);
    ranked.push({ product, score, evidence, conflict });
  }
  ranked.sort((a, b) => b.score - a.score || a.product.id - b.product.id);
  const first = ranked[0];
  const base = { candidates: ranked.slice(0, 3), barcodes, lines };
  if (!first) return { ...base, status: 'NOT_IDENTIFIED', reason: 'NO_CATALOG_MATCH' };
  if (repeated && barcodeIds.size === 1 && !first.conflict &&
      (first.evidence.includes('text') || !ranked.slice(1).some(item => item.evidence.includes('text')))) {
    return { ...base, status: 'IDENTIFIED', reason: 'UNIQUE_REPEATED_GTIN' };
  }
  const reason = barcodeIds.size > 1 ? 'SHARED_GTIN' : codes.length > 1 ? 'CONFLICTING_GTIN' :
    first.conflict || repeated && barcodeIds.size === 1 ? 'CONFLICTING_TEXT' : 'REVIEW_EVIDENCE';
  return { ...base, status: 'NEEDS_CONFIRMATION', reason };
}
