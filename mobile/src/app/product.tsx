import { useEffect, useState } from 'react';
import { useLocalSearchParams } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { remember, useLanguage, usePreferences } from '../preferences/store';

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
  const { t, direction } = useLanguage();
  const { id } = useLocalSearchParams<{ id: string }>();
  if (typeof id !== 'string' || !/^\d+$/.test(id) || !Number.isSafeInteger(Number(id))) {
    return <Text style={[styles.body, direction]}>{t('رقم السجل غير صالح.', 'Invalid product record.')}</Text>;
  }
  return <ProductDetails key={id} id={Number(id)} />;
}

function ProductDetails({ id }: { id: number }) {
  const { t, language, direction } = useLanguage();
  const { update, ready, settings: { keepHistory } } = usePreferences();
  const db = useSQLiteContext();
  const [result, setResult] = useState<Details | null>(null);
  const [status, setStatus] = useState(t('جارٍ تحميل السجل…', 'Loading record…'));
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
      .then((row: Details | null) => { if (active) { setResult(row); setStatus(row ? '' : t('السجل غير موجود.', 'Record not found.')); } })
      .catch(() => { if (active) setStatus(t('تعذّر تحميل السجل.', 'Could not load record.')); });
    return () => { active = false; };
  }, [db, id, t]);

  useEffect(() => {
    if (ready && keepHistory && result) {
      void update(current => remember(current, { source: result.source_code, record: result.source_record_id })).catch(() => {});
    }
  }, [keepHistory, ready, result, update]);

  if (!result) return <Text style={[styles.body, direction]} accessibilityLiveRegion="polite">{status}</Text>;

  const countries: Record<string, string> = { EG: t('مصر', 'Egypt'), SA: t('السعودية', 'Saudi Arabia') };
  const country = countries[result.country_code] ?? result.country_code;
  const fields = [
    [t('الاسم التجاري بالإنجليزية', 'English brand name'), result.brand_name_ar ? result.brand_name_en : null],
    [t('التركيز المستخرج من اسم المنتج', 'Strength parsed from product name'), result.strength_normalized],
    [t('الاسم العلمي أو المواد الفعالة', 'Scientific name or active ingredients'), result.scientific],
    [t('الشركة المصنّعة', 'Manufacturer'), result.manufacturer],
    [t('السوق في المصدر', 'Market in source'), country],
  ];

  const availabilityLabels: Record<string, string> = {
    REGISTERED: t('مسجّل وفق المصدر', 'Registered according to source'),
    MARKETED: t('مسوّق وفق المصدر', 'Marketed according to source'),
    IMPORTED: t('مذكور كمستورد في المصدر', 'Listed as imported'),
  };

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} accessibilityLanguage={language}>
      <Text style={[styles.title, direction]} accessibilityRole="header">{language === 'ar' ? result.brand_name_ar || result.brand_name_en : result.brand_name_en || result.brand_name_ar}</Text>
      {fields.filter(([, value]) => value).map(([label, value]) => (
        <View key={label} style={styles.card}>
          <Text style={[styles.label, direction]}>{label}</Text>
          <Text style={[styles.body, direction]}>{value}</Text>
        </View>
      ))}
      <View style={styles.card}>
        <Text style={[styles.label, direction]}>{t('حالة المنتج في مصدر البيانات', 'Product status in the source')}</Text>
        <Text style={[styles.body, direction]}>{availabilityLabels[result.availability ?? ''] ?? t('التوفر الحالي غير معلوم', 'Current availability unknown')}</Text>
        {result.source_code.startsWith('sfda-2023-') && result.registration_authority === 'SFDA' && (
          <Text style={[styles.body, direction]}>{t('ورد ضمن قائمة الأدوية المسجلة لدى الهيئة السعودية في ديسمبر 2023.', 'Listed in the December 2023 Saudi Food and Drug Authority snapshot.')}</Text>
        )}
      </View>
      <View style={styles.card}>
        <Text style={[styles.label, direction]}>{t('مصدر السجل', 'Record source')}</Text>
        <Text style={[styles.body, direction]}>{result.source_name}</Text>
        <Text style={[styles.body, direction]} selectable>{result.source_record_id}</Text>
        {/^https:\/\//.test(result.source_url) && (
          <Pressable accessibilityRole="link" onPress={() => {
            setLinkError(false);
            Linking.openURL(result.source_url).catch(() => setLinkError(true));
          }}>
            <Text style={[styles.link, direction]}>{t('فتح موقع المصدر', 'Open source website')}</Text>
          </Pressable>
        )}
        {linkError && <Text style={[styles.body, direction]}>{t('تعذّر فتح الرابط.', 'Could not open the link.')}</Text>}
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
