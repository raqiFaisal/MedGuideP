import { useEffect, useState } from 'react';
import { useSQLiteContext } from 'expo-sqlite';
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLanguage } from '../preferences/store';

type Source = { code: string; name: string; url: string; license: string; attribution: string | null };

const sourceListQuery = 'SELECT code,name,url,license,attribution FROM data_sources ORDER BY id';

export default function SourcesScreen() {
  const { language, direction, t } = useLanguage();
  const db = useSQLiteContext();
  const [sources, setSources] = useState<Source[]>([]);
  const [status, setStatus] = useState(t('جارٍ تحميل المصادر…', 'Loading sources…'));
  const [failedLink, setFailedLink] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    db.getAllAsync<Source>(sourceListQuery)
      .then((rows: Source[]) => {
        if (!active) return;
        setSources(rows);
        setStatus(rows.length ? '' : t('لا توجد مصادر في هذه النسخة.', 'This build has no data sources.'));
      })
      .catch(() => { if (active) setStatus(t('تعذّر تحميل المصادر.', 'Could not load sources.')); });
    return () => { active = false; };
  }, [db, t]);

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} accessibilityLanguage={language}>
      {status ? <Text style={[styles.body, direction]} accessibilityLiveRegion="polite">{status}</Text> : null}
      {sources.map(source => (
        <View key={source.code} style={styles.card}>
          <Text accessibilityRole="header" style={[styles.title, direction]}>{source.name}</Text>
          <Text style={[styles.body, direction]}>{source.license}</Text>
          {source.attribution && <Text style={[styles.body, direction]}>{source.attribution}</Text>}
          {/^https:\/\//i.test(source.url) && (
            <Pressable accessibilityRole="link" onPress={() => {
              setFailedLink(null);
              Linking.openURL(source.url).catch(() => setFailedLink(source.code));
            }}>
              <Text style={[styles.link, direction]}>{t('فتح موقع المصدر', 'Open source website')}</Text>
            </Pressable>
          )}
          {failedLink === source.code && <Text style={[styles.body, direction]}>{t('تعذّر فتح الرابط.', 'Could not open the link.')}</Text>}
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
