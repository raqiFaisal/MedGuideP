import { Stack } from 'expo-router';
import { SQLiteProvider, type SQLiteDatabase } from 'expo-sqlite';
import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Text } from 'react-native';

export default function RootLayout() {
  const [error, setError] = useState(false);
  if (error) return (
    <SafeAreaView style={{ flex: 1, padding: 20 }}>
      <Text accessibilityRole="alert">تعذّر فتح قاعدة الأدوية. أغلقي التطبيق ثم افتحيه مرة أخرى.</Text>
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
        <Stack.Screen name="scan" options={{ title: "التعرف على العلبة" }} />
        <Stack.Screen name="product" options={{ title: 'تفاصيل السجل' }} />
        <Stack.Screen name="sources" options={{ title: "مصادر البيانات" }} />
      </Stack>
    </SQLiteProvider>
  );
}
