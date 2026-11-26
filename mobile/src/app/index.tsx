import { useState } from 'react';
import { Link } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Product, searchQuery } from '../catalog/queries';

const markets: Record<string, string> = { EG: 'مصر', SA: 'السعودية' };

export default function Index() {
  const db = useSQLiteContext();
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<Product[]>([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  async function search() {
    if (busy) return;
    const statement = searchQuery(query, '');
    setItems([]);
    if (!statement) {
      setMessage('اكتبي اسم الدواء أو رقم الباركود.');
      return;
    }
    setBusy(true);
    setMessage('جارٍ البحث…');
    try {
      const rows = await db.getAllAsync<Product>(statement.sql, statement.parameters);
      setItems(rows.slice(0, 50));
      setMessage(rows.length === 0 ? 'لم نجد نتائج.' : rows.length > 50 ? 'أول 50 نتيجة. حددي الاسم أو التركيز لتضييق البحث.' : `النتائج · ${rows.length}`);
    } catch {
      setMessage('تعذّر البحث في قاعدة الأدوية. أعيدي المحاولة.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.screen} accessibilityLanguage="ar">
      <View style={styles.topBar}>
        <Text style={styles.brand}>MedGuide</Text>
        <Link href="/sources" style={styles.sources}>مصادر البيانات</Link>
      </View>
      <Link href={{ pathname: "/scan", params: { mode: "camera" } }} style={styles.scan}>صوّر الدواء</Link>
      <Link href={{ pathname: "/scan", params: { mode: "gallery" } }} style={styles.sources}>اختر صورة من المعرض</Link>
      <Text style={styles.title} accessibilityRole="header">البحث في دليل الأدوية</Text>
      <TextInput style={styles.input} value={query} onChangeText={setQuery}
        placeholder="اسم الدواء أو رقم الباركود" placeholderTextColor="#4A5D70"
        accessibilityLabel="اسم الدواء أو رقم الباركود" maxLength={120}
        returnKeyType="search" onSubmitEditing={search} editable={!busy} />
      <Pressable onPress={search} disabled={busy} accessibilityRole="button" style={styles.button}>
        <Text style={styles.buttonText}>بحث</Text>
      </Pressable>
      <Text accessibilityLiveRegion="polite" style={styles.meta}>{message}</Text>
      <FlatList data={items} keyExtractor={item => String(item.id)} keyboardShouldPersistTaps="handled"
        renderItem={({ item }) => (
          <Link href={{ pathname: '/product', params: { id: item.id } }} asChild>
            <Pressable style={styles.card}>
              <Text style={styles.name}>{item.brand_name_ar || item.brand_name_en}</Text>
              <Text style={styles.meta}>{[item.strength_normalized, item.manufacturer, markets[item.country_code] ?? item.country_code].filter(Boolean).join(' · ')}</Text>
            </Pressable>
          </Link>
        )}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scan: { minHeight: 48, backgroundColor: "#0F766E", color: "white", textAlign: "center", padding: 12, borderRadius: 12, fontSize: 18, fontWeight: "700" },
  screen: { flex: 1, backgroundColor: '#F2FAF8', padding: 20, gap: 12 },
  topBar: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap' },
  sources: { color: '#0F766E', fontWeight: '700', fontSize: 16, paddingVertical: 12 },
  brand: { color: '#0F766E', fontSize: 18, fontWeight: '800', textAlign: 'right' },
  title: { color: '#0B2545', fontSize: 30, fontWeight: '800', textAlign: 'right' },
  input: { minHeight: 52, backgroundColor: '#FFF', borderColor: '#D5E6E3', borderWidth: 1, borderRadius: 12, paddingHorizontal: 14, fontSize: 18, textAlign: 'right', color: '#0B2545' },
  button: { minHeight: 48, justifyContent: 'center', alignItems: 'center', borderRadius: 12, backgroundColor: '#0F766E' },
  buttonText: { color: '#FFF', fontWeight: '700', fontSize: 18 },
  card: { borderColor: '#D5E6E3', borderWidth: 1, backgroundColor: '#FFF', borderRadius: 12, marginBottom: 8, padding: 14, gap: 6 },
  name: { color: '#0B2545', fontSize: 18, fontWeight: '700', textAlign: 'right' },
  meta: { color: '#4A5D70', fontSize: 15, textAlign: 'right' },
});
