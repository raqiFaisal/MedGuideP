import { Link } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text } from 'react-native';
import { productColumns, productTables, type Product } from '../catalog/queries';
import { useLanguage, usePreferences } from '../preferences/store';

export default function History() {
  const { settings: { history }, ready } = usePreferences();
  const { language, direction, t } = useLanguage();
  const db = useSQLiteContext();
  const [rows, setRows] = useState<Product[]>();
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    if (!ready || !history.length) return;
    const keys = history.map(() => '(?,?,?)').join(',');
    db.getAllAsync<Product>(`WITH recent(position, source, record) AS (VALUES ${keys})
      ${productColumns}${productTables}
      JOIN data_sources s ON s.id=p.source_id
      JOIN recent r ON r.source=s.code AND r.record=p.source_record_id
      ORDER BY r.position`, history.flatMap((value, index) => [index, value.source, value.record]))
      .then(items => { if (active) { setRows(items); setError(false); } })
      .catch(() => { if (active) { setRows([]); setError(true); } });
    return () => { active = false; };
  }, [db, history, ready]);

  const empty = !history.length && ready ? t('السجل فارغ.', 'History is empty.') : error ? t('تعذّر تحميل السجل.', 'Could not load history.') :
    rows ? t('السجل فارغ.', 'History is empty.') : t('جارٍ تحميل السجل…', 'Loading history…');
  return <FlatList data={history.length ? rows : []} contentContainerStyle={styles.list} accessibilityLanguage={language}
    keyExtractor={item => String(item.id)}
    ListEmptyComponent={<Text style={direction}>{empty}</Text>}
    renderItem={({ item }) => <Link href={{ pathname: '/product', params: { id: item.id } }} asChild>
      <Pressable style={styles.card}>
        <Text style={[styles.name, direction]}>{language === 'ar' ? item.brand_name_ar || item.brand_name_en :
          item.brand_name_en || item.brand_name_ar}</Text>
        <Text style={direction}>{[item.strength_normalized, item.manufacturer, item.country_code].filter(Boolean).join(' · ')}</Text>
      </Pressable>
    </Link>}/>;
}

const styles = StyleSheet.create({
  list: { flexGrow: 1, padding: 20, gap: 10, backgroundColor: '#F2FAF8' },
  card: { padding: 14, gap: 6, borderRadius: 12, backgroundColor: '#FFF' },
  name: { fontSize: 18, fontWeight: '700', color: '#0B2545' },
});
