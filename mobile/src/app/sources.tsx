import { useEffect, useState } from 'react';
import { useSQLiteContext } from 'expo-sqlite';
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

type Source = { code: string; name: string; url: string; license: string; attribution: string | null };

const sourceListQuery = 'SELECT code,name,url,license,attribution FROM data_sources ORDER BY id';

export default function SourcesScreen() {
  const db = useSQLiteContext();
  const [sources, setSources] = useState<Source[]>([]);
  const [status, setStatus] = useState('جارٍ تحميل المصادر…');
  const [failedLink, setFailedLink] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    db.getAllAsync<Source>(sourceListQuery)
      .then((rows: Source[]) => {
        if (!active) return;
        setSources(rows);
        setStatus(rows.length ? '' : 'لا توجد مصادر في هذه النسخة.');
      })
      .catch(() => { if (active) setStatus('تعذّر تحميل المصادر.'); });
    return () => { active = false; };
  }, [db]);

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} accessibilityLanguage="ar">
      {status ? <Text style={styles.body} accessibilityLiveRegion="polite">{status}</Text> : null}
      {sources.map(source => (
        <View key={source.code} style={styles.card}>
          <Text accessibilityRole="header" style={styles.title}>{source.name}</Text>
          <Text style={styles.body}>{source.license}</Text>
          {source.attribution && <Text style={styles.body}>{source.attribution}</Text>}
          {/^https:\/\//i.test(source.url) && (
            <Pressable accessibilityRole="link" onPress={() => {
              setFailedLink(null);
              Linking.openURL(source.url).catch(() => setFailedLink(source.code));
            }}>
              <Text style={styles.link}>فتح موقع المصدر</Text>
            </Pressable>
          )}
          {failedLink === source.code && <Text style={styles.body}>تعذّر فتح الرابط.</Text>}
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#F2FAF8' },
  content: { padding: 20, gap: 12 },
  card: { backgroundColor: '#FFF', borderWidth: 1, borderColor: '#D5E6E3', borderRadius: 12, padding: 14, gap: 8 },
  title: { color: '#0B2545', fontSize: 18, fontWeight: '700' },
  body: { color: '#4A5D70', fontSize: 16 },
  link: { color: '#0F766E', minHeight: 44, paddingVertical: 10, textAlign: 'right', fontWeight: '700', fontSize: 16 },
});
