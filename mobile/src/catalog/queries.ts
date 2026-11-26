import { toGtin14 } from '../text/gtin';
import { normalizeText } from '../text/normalize';

export type Product = {
  id: number;
  brand_name_ar: string | null;
  brand_name_en: string | null;
  strength_normalized: string | null;
  country_code: string;
  manufacturer: string | null;
};

export const productColumns = `SELECT p.id, p.brand_name_ar, p.brand_name_en, p.strength_normalized,
p.country_code, m.name AS manufacturer`;
export const productTables = ' FROM products p LEFT JOIN manufacturers m ON m.id=p.manufacturer_id';
const products = productColumns + productTables;

export function searchQuery(input: string, country: string) {
  const normalized = normalizeText(input);
  if (!normalized) return null;
  const gtin = toGtin14(normalized);
  const filter = country ? ' AND p.country_code=?' : '';
  const countries = country ? [country] : [];
  if (gtin) {
    return {
      sql: products + " WHERE p.id IN (SELECT product_id FROM product_identifiers WHERE kind='GTIN14' AND value=? AND check_ok=1)" +
        filter + ' ORDER BY p.id LIMIT 51',
      parameters: [gtin, ...countries],
    };
  }
  const terms = normalized.split(/\s+/).map(token => '"' + token.replace(/"/g, '""') + '"*');
  return {
    sql: products + ' JOIN products_fts ON products_fts.rowid=p.id WHERE products_fts MATCH ?' +
      filter + ' ORDER BY bm25(products_fts), p.id LIMIT 51',
    parameters: [terms.join(' AND '), ...countries],
  };
}
