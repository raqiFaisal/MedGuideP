import { useEffect, useState } from 'react';
import { useLocalSearchParams } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Product, productColumns, productTables } from '../catalog/queries';

type Details = Product & {
  source_name: string;
  source_url: string;
  scientific: string | null;
  availability: string | null;
  registration_authority: string | null;
  source_record_id: string;
  source_code: string;
};

export default function ProductScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  if (typeof id !== 'string' || !/^\d+$/.test(id) || !Number.isSafeInteger(Number(id))) {
    return <Text style={styles.body}>رقم السجل غير صالح.</Text>;
  }
  return <ProductDetails key={id} id={Number(id)} />;
}

function ProductDetails({ id }: { id: number }) {
  const db = useSQLiteContext();
  const [result, setResult] = useState<Details | null>(null);
  const [status, setStatus] = useState('جارٍ تحميل السجل…');
  const [linkError, setLinkError] = useState(false);

  useEffect(() => {
    let active = true;
    const select = productColumns + `,
      s.name AS source_name, s.url AS source_url, s.code AS source_code, p.source_record_id,
      (SELECT status FROM market_availability WHERE product_id=p.id AND country_code=p.country_code) AS availability,
      (SELECT authority FROM product_registrations WHERE product_id=p.id AND country_code=p.country_code ORDER BY id LIMIT 1) AS registration_authority,
      COALESCE((SELECT original_value FROM information_provenance WHERE table_name='products'
                AND row_id=p.id AND field='ScientificName'),
               (SELECT group_concat(ai.name_en, ' + ') FROM product_ingredients pi
                JOIN active_ingredients ai ON ai.id=pi.ingredient_id WHERE pi.product_id=p.id)) AS scientific
      ` + productTables;
    db.getFirstAsync<Details>(select + ' JOIN data_sources s ON s.id=p.source_id WHERE p.id=?', id)
      .then((row: Details | null) => { if (active) { setResult(row); setStatus(row ? '' : 'السجل غير موجود.'); } })
      .catch(() => { if (active) setStatus('تعذّر تحميل السجل.'); });
    return () => { active = false; };
  }, [db, id]);

  if (!result) return <Text style={styles.body} accessibilityLiveRegion="polite">{status}</Text>;

  const countries: Record<string, string> = { EG: 'مصر', SA: 'السعودية' };
  const country = countries[result.country_code] ?? result.country_code;
  const fields = [
    ['الاسم التجاري بالإنجليزية', result.brand_name_ar ? result.brand_name_en : null],
    ['التركيز المستخرج من اسم المنتج', result.strength_normalized],
    ['الاسم العلمي أو المواد الفعالة', result.scientific],
    ['الشركة المصنّعة', result.manufacturer],
    ['السوق في المصدر', country],
  ];

  const availabilityLabels: Record<string, string> = {
    REGISTERED: 'مسجّل وفق المصدر',
    MARKETED: 'مسوّق وفق المصدر',
    IMPORTED: 'مذكور كمستورد في المصدر',
  };

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} accessibilityLanguage="ar">
      <Text style={styles.title} accessibilityRole="header">{result.brand_name_ar || result.brand_name_en}</Text>
      {fields.filter(([, value]) => value).map(([label, value]) => (
        <View key={label} style={styles.card}>
          <Text style={styles.label}>{label}</Text>
          <Text style={styles.body}>{value}</Text>
        </View>
      ))}
      <View style={styles.card}>
        <Text style={styles.label}>حالة المنتج في مصدر البيانات</Text>
        <Text style={styles.body}>{availabilityLabels[result.availability ?? ''] ?? 'التوفر الحالي غير معلوم'}</Text>
        {result.source_code.startsWith('sfda-2023-') && result.registration_authority === 'SFDA' && (
          <Text style={styles.body}>ورد ضمن قائمة الأدوية المسجلة لدى الهيئة السعودية في ديسمبر 2023.</Text>
        )}
      </View>
      <View style={styles.card}>
        <Text style={styles.label}>مصدر السجل</Text>
        <Text style={styles.body}>{result.source_name}</Text>
        <Text style={styles.body} selectable>{result.source_record_id}</Text>
        {/^https:\/\//.test(result.source_url) && (
          <Pressable accessibilityRole="link" onPress={() => {
            setLinkError(false);
            Linking.openURL(result.source_url).catch(() => setLinkError(true));
          }}>
            <Text style={styles.link}>فتح موقع المصدر</Text>
          </Pressable>
        )}
        {linkError && <Text style={styles.body}>تعذّر فتح الرابط.</Text>}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#F2FAF8' },
  content: { padding: 20, gap: 12 },
  title: { color: '#0B2545', fontWeight: '800', fontSize: 26, textAlign: 'right' },
  card: { borderRadius: 12, backgroundColor: '#FFF', padding: 14, gap: 5, borderWidth: 1, borderColor: '#D5E6E3' },
  label: { fontSize: 16, color: '#4A5D70', textAlign: 'right' },
  body: { fontSize: 18, color: '#0B2545', textAlign: 'right' },
  link: { color: '#0F766E', minHeight: 44, paddingVertical: 10, textAlign: 'right', fontWeight: '700', fontSize: 16 },
});
