import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import { router, useLocalSearchParams } from 'expo-router';
import { useRef, useState } from 'react';
import { ActivityIndicator, Platform, Pressable, View } from 'react-native';

import { CloseIcon } from '@/components/icons';
import { TagEditor } from '@/components/TagEditor';
import { Button, Notice, Screen, T } from '@/components/ui';
import { api, Category, imageSource, PickedImage, Tags } from '@/lib/api';
import { useErrorText } from '@/lib/errors';
import { useI18n } from '@/lib/i18n';
import { useAnalysis, useCreateItem, useItems } from '@/lib/queries';
import { radius, space, usePalette } from '@/lib/theme';


type Draft = { key: string; url: string; isClothing: boolean; aiSkipped: boolean; tags: Tags; uncertain: (keyof Tags)[]; confidence: number | null };

/**
 * One photo → AI tags → the user confirms → saved. With `?first=1` (right after sign-up) it chains:
 * three pieces in a row, a running count, then straight to Today for the first outfit. In both modes
 * every save shows what it unlocked ("+6 outfits"), from the deterministic analysis — no AI request.
 */
export default function NewItem() {
  const p = usePalette();
  const { t, lang } = useI18n();
  const errorText = useErrorText();
  const create = useCreateItem();
  const { first, category: hint } = useLocalSearchParams<{ first?: string; category?: string }>();
  const firstMode = first === '1';
  const items = useItems();
  const analysis = useAnalysis();
  const [preview, setPreview] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reward, setReward] = useState<string | null>(null);
  const [added, setAdded] = useState(0); // pieces saved in this visit
  const before = useRef<number | null>(null); // outfits possible before the last save

  const count = items.data?.length ?? 0;
  const step = firstMode ? Math.min(count + 1, 3) : 0; // survives a reload: counted from the wardrobe
  const ready = (() => {
    const cats = new Set((items.data ?? []).map((i) => i.category));
    return cats.has('dress') || (cats.has('top') && cats.has('bottom'));
  })();

  function close() {
    if (firstMode) return router.replace('/');
    if (router.canGoBack()) router.back();
    else router.replace('/wardrobe');
  }

  async function pick(source: 'camera' | 'library') {
    setError(null);
    const opts: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.8, allowsEditing: true, aspect: [1, 1] };
    if (source === 'camera' && Platform.OS !== 'web') {
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) return;
    }
    const res = source === 'camera' ? await ImagePicker.launchCameraAsync(opts) : await ImagePicker.launchImageLibraryAsync(opts);
    if (res.canceled || !res.assets?.[0]) return;
    const asset = res.assets[0];
    setPreview(asset.uri);
    setDraft(null);
    setAnalyzing(true);
    try {
      const out = await api.analyze(asset as PickedImage, lang);
      setDraft({ key: out.image_key, url: out.image_url, isClothing: out.is_clothing, aiSkipped: !!out.ai_skipped, tags: out.tags,
                 uncertain: out.uncertain ?? [], confidence: out.confidence ?? null });
    } catch (e) {
      setError(errorText(e));
      setPreview(null);
    } finally {
      setAnalyzing(false);
    }
  }

  async function save() {
    if (!draft) return;
    setError(null);
    try {
      const prev = before.current ?? analysis.data?.outfits_possible ?? 0;
      await create.mutateAsync({ ...draft.tags, image_key: draft.key, ai_confidence: draft.confidence });
      const fresh = await analysis.refetch();
      const now = fresh.data?.outfits_possible ?? 0;
      const gained = now - prev;
      before.current = now;
      const gap = fresh.data?.gaps.find((g) => g.code === 'missing_category');
      setReward(
        gained > 0
          ? t.first.unlocked(gained)
          : now === 0 && gap?.category
            ? t.first.starts(t.categories[gap.category].toLocaleLowerCase(lang))
            : t.first.noNew,
      );
      setAdded((n) => n + 1);
      setDraft(null);
      setPreview(null);
      if (!firstMode) return; // normal mode: stay for the reward line, close is one tap away
      if (count + 1 >= 3 && now > 0) router.replace('/'); // three in and an outfit exists: show it
    } catch (e) {
      setError(errorText(e));
    }
  }

  const shown = draft ? imageSource(draft.url, draft.key) : preview ? { uri: preview } : null;

  return (
    <Screen edges={['top', 'bottom']}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: space.md }}>
        <T variant="heading" accessibilityRole="header">
          {firstMode ? t.first.title(step) : t.add.title}
        </T>
        <Pressable accessibilityRole="button" accessibilityLabel={t.common.close} onPress={close} hitSlop={12}>
          <CloseIcon color={p.ink} />
        </Pressable>
      </View>

      {shown ? (
        <View style={{ marginTop: space.md }}>
          <Image
            source={shown}
            style={{ width: '100%', aspectRatio: 1, borderRadius: radius.lg, backgroundColor: p.surfaceAlt }}
            contentFit="cover"
          />
          {analyzing ? (
            <View
              style={{
                position: 'absolute',
                inset: 0,
                borderRadius: radius.lg,
                backgroundColor: 'rgba(42,27,38,0.45)',
                alignItems: 'center',
                justifyContent: 'center',
                gap: space.md,
              }}
            >
              <ActivityIndicator color="#F8F6F3" size="large" />
              <T variant="bodyStrong" style={{ color: '#F8F6F3' }}>
                {t.add.analyzing}
              </T>
            </View>
          ) : null}
        </View>
      ) : (
        <View style={{ marginTop: space.xl, gap: space.md }}>
          {reward ? <Notice>{reward}</Notice> : null}
          <T variant="body" color="inkSoft">
            {firstMode && !added ? t.first.intro : hint && !added ? t.add.forCategory(t.categories[hint as Category]) : t.add.tip}
          </T>
          {Platform.OS !== 'web' ? <Button label={t.add.camera} onPress={() => pick('camera')} /> : null}
          <Button label={t.add.library} kind={Platform.OS === 'web' ? 'primary' : 'secondary'} onPress={() => pick('library')} />
          {firstMode && ready ? <Button label={t.first.enough} kind="ghost" onPress={() => router.replace('/')} /> : null}
        </View>
      )}

      {error ? (
        <View style={{ marginTop: space.lg }}>
          <Notice tone="error">{error}</Notice>
        </View>
      ) : null}

      {draft ? (
        <View style={{ marginTop: space.xl, gap: space.xl }}>
          {draft.aiSkipped ? (
            <Notice>{t.add.aiSkipped}</Notice>
          ) : !draft.isClothing ? (
            <Notice>{t.add.notClothing}</Notice>
          ) : draft.uncertain.length ? (
            <Notice>{t.add.checkHint(draft.uncertain.length)}</Notice>
          ) : null}
          <TagEditor value={draft.tags} onChange={(tags) => setDraft({ ...draft, tags })} uncertain={draft.uncertain} />
          <Button label={t.add.save} onPress={save} loading={create.isPending} />
          <Button
            label={t.add.retake}
            kind="ghost"
            onPress={() => {
              setDraft(null);
              setPreview(null);
            }}
          />
        </View>
      ) : null}
    </Screen>
  );
}
