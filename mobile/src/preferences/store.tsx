import { SQLiteStorage } from 'expo-sqlite/kv-store';
import { createContext, useCallback, useContext, useEffect, useState, type PropsWithChildren } from 'react';

export type HistoryKey = { source: string; record: string };
type Settings = { language: 'ar' | 'en'; keepHistory: boolean; history: HistoryKey[] };
type UpdateSettings = (change: (settings: Settings) => Settings) => Promise<void>;

const storage = new SQLiteStorage('medguide-user.db');
const key = 'preferences-v1';
const defaults: Settings = { language: 'ar', keepHistory: false, history: [] };
const preferences = createContext<{ settings: Settings; ready: boolean; update: UpdateSettings } | null>(null);
let pendingWrite: Promise<void> = Promise.resolve();

function parse(raw: string | null): Settings {
  try {
    const value = JSON.parse(raw ?? 'null') as Partial<Settings> | null;
    return {
      language: value?.language === 'en' ? 'en' : 'ar',
      keepHistory: value?.keepHistory === true,
      history: Array.isArray(value?.history) ? value.history.filter(
        item => typeof item?.source === 'string' && typeof item?.record === 'string',
      ).slice(0, 50) : [],
    };
  } catch {
    return defaults;
  }
}

export function PreferencesProvider({ children }: PropsWithChildren) {
  const [settings, setSettings] = useState(defaults);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let active = true;
    storage.getItemAsync(key).then(raw => {
      if (active) setSettings(parse(raw));
    }).catch(() => {}).finally(() => {
      if (active) setReady(true);
    });
    return () => { active = false; };
  }, []);

  const update = useCallback<UpdateSettings>(change => {
    const write = pendingWrite.then(async () => {
      let next = defaults;
      await storage.setItemAsync(key, raw => {
        next = change(parse(raw));
        return JSON.stringify(next);
      });
      setSettings(next);
    });
    pendingWrite = write.catch(() => {});
    return write;
  }, []);

  return <preferences.Provider value={{ settings, ready, update }}>{children}</preferences.Provider>;
}

export function usePreferences() {
  const value = useContext(preferences);
  if (!value) throw new Error('PreferencesProvider is required');
  return value;
}

export function useLanguage() {
  const { settings: { language } } = usePreferences();
  const t = useCallback((ar: string, en: string) => language === 'ar' ? ar : en, [language]);
  const direction = { textAlign: language === 'ar' ? 'right' : 'left', writingDirection: language === 'ar' ? 'rtl' : 'ltr' } as const;
  return { language, direction, t };
}

export function remember(settings: Settings, item: HistoryKey): Settings {
  if (!settings.keepHistory) return settings;
  return {
    ...settings,
    history: [item, ...settings.history.filter(old => old.source !== item.source || old.record !== item.record)].slice(0, 50),
  };
}
