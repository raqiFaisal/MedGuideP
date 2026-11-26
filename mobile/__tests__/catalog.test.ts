import { searchQuery } from '../src/catalog/queries';

test('catalog builds parameterized Arabic prefix and country queries', () => {
  const query = searchQuery('بانادول 500', 'EG');
  expect(query?.parameters).toEqual(['"بانادول"* AND "500"*', 'EG']);
  expect(query?.sql).toContain('p.country_code=?');
});

test('catalog uses validated GTINs and keeps all matching product rows', () => {
  const query = searchQuery('6221000000010', '');
  expect(query?.parameters).toEqual(['06221000000010']);
  expect(query?.sql).toContain('check_ok=1');
  expect(searchQuery('*', '')).toBeNull();
});
