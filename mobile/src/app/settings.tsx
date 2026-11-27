import { useState } from 'react';
import { Alert, Button, StyleSheet, Switch, Text, View } from 'react-native';
import { useLanguage, usePreferences } from '../preferences/store';

export default function Settings() {
  const { settings, ready, update } = usePreferences();
  const { language, direction, t } = useLanguage();
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  async function save(change: Parameters<typeof update>[0]) {
    setError(false);
    setBusy(true);
    try {
      await update(change);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return <View style={styles.screen} accessibilityLanguage={language}>
    <Text style={[styles.title, direction]}>{t('لغة التطبيق', 'App language')}</Text>
    <Button title="العربية" disabled={!ready || busy || language === 'ar'}
      onPress={() => void save(current => ({ ...current, language: 'ar' }))}/>
    <Button title="English" disabled={!ready || busy || language === 'en'}
      onPress={() => void save(current => ({ ...current, language: 'en' }))}/>
    <Text style={[styles.title, direction]}>{t('حفظ سجل الأدوية على الجهاز', 'Save medicine history on this device')}</Text>
    <Switch disabled={!ready || busy} value={settings.keepHistory}
      accessibilityLabel={t('حفظ السجل', 'Save history')}
      onValueChange={keepHistory => void save(current => ({ ...current, keepHistory }))}/>
    <Button title={t('حذف السجل', 'Clear history')} disabled={!settings.history.length || busy}
      onPress={() => Alert.alert(t('حذف السجل؟', 'Clear history?'), undefined, [
        { text: t('إلغاء', 'Cancel'), style: 'cancel' },
        { text: t('حذف', 'Clear'), style: 'destructive', onPress: () => void save(current => ({ ...current, history: [] })) },
      ])}/>
    {error && <Text style={direction} accessibilityRole="alert">{t('تعذّر حفظ الإعدادات.', 'Could not save settings.')}</Text>}
  </View>;
}

const styles = StyleSheet.create({
  screen: { flex: 1, padding: 20, gap: 14, backgroundColor: '#F2FAF8' },
  title: { fontSize: 19, fontWeight: '700', color: '#0B2545' },
});
