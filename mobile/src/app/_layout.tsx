import { Stack } from 'expo-router';
import { SQLiteProvider, type SQLiteDatabase } from 'expo-sqlite';
import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Text } from 'react-native';
import { PreferencesProvider, useLanguage } from '../preferences/store';

export default function RootLayout() {
  return <PreferencesProvider><CatalogLayout/></PreferencesProvider>;
}

function CatalogLayout() {
  const { t } = useLanguage();
  const [error, setError] = useState(false);
  if (error) return (
    <SafeAreaView style={{ flex: 1, padding: 20 }}>
      <Text accessibilityRole="alert">{t('تعذّر فتح قاعدة الأدوية. أغلقي التطبيق ثم افتحيه مرة أخرى.', 'Could not open the catalog. Close and reopen the app.')}</Text>
    </SafeAreaView>
  );
  return (
    <SQLiteProvider databaseName={require('../../assets/db/version.json').databaseName}
      assetSource={{ assetId: require('../../assets/db/medguide.db') }}
      onInit={(db: SQLiteDatabase) => db.execAsync('PRAGMA query_only=ON')}
      onError={() => setError(true)}>
      <StatusBar style="dark" />
      <Stack>
        <Stack.Screen name="index" options={{ headerShown: false }} />
        <Stack.Screen name="scan" options={{ title: t('التعرف على العلبة', 'Scan package') }} />
        <Stack.Screen name="product" options={{ title: t('تفاصيل السجل', 'Product details') }} />
        <Stack.Screen name="sources" options={{ title: t('مصادر البيانات', 'Data sources') }} />
        <Stack.Screen name="settings" options={{ title: t('الإعدادات', 'Settings') }} />
        <Stack.Screen name="history" options={{ title: t('السجل', 'History') }} />
      </Stack>
    </SQLiteProvider>
  );
}
