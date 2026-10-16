import { Tabs } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { HangerIcon, HeartIcon, PersonIcon, TodayIcon } from '@/components/icons';
import { useI18n } from '@/lib/i18n';
import { font, usePalette } from '@/lib/theme';

export default function TabsLayout() {
  const p = usePalette();
  const { t } = useI18n();
  const insets = useSafeAreaInsets();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: p.ink,
        tabBarInactiveTintColor: p.muted,
        tabBarStyle: {
          backgroundColor: p.surface,
          borderTopColor: p.line,
          height: 66 + insets.bottom,
          paddingTop: 4,
          paddingBottom: Math.max(insets.bottom, 6),
        },
        tabBarLabelStyle: { fontFamily: font.medium, fontSize: 12, lineHeight: 16 },
        sceneStyle: { backgroundColor: p.bg },
      }}
    >
      <Tabs.Screen name="today" options={{ title: t.tabs.today, tabBarIcon: ({ color }) => <TodayIcon color={String(color)} /> }} />
      <Tabs.Screen
        name="wardrobe"
        options={{ title: t.tabs.wardrobe, tabBarIcon: ({ color }) => <HangerIcon color={String(color)} /> }}
      />
      <Tabs.Screen name="saved" options={{ title: t.tabs.saved, tabBarIcon: ({ color }) => <HeartIcon color={String(color)} /> }} />
      <Tabs.Screen
        name="profile"
        options={{ title: t.tabs.profile, tabBarIcon: ({ color }) => <PersonIcon color={String(color)} /> }}
      />
    </Tabs>
  );
}
