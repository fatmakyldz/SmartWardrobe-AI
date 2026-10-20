import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Platform, Pressable, View } from 'react-native';

import { CloseIcon } from '@/components/icons';
import { TagEditor } from '@/components/TagEditor';
import { Button, Notice, Screen, T } from '@/components/ui';
import { api, imageSource, PickedImage, Tags } from '@/lib/api';
import { useErrorText } from '@/lib/errors';
import { useI18n } from '@/lib/i18n';
import { useCreateItem } from '@/lib/queries';
import { radius, space, usePalette } from '@/lib/theme';

const close = () => (router.canGoBack() ? router.back() : router.replace('/wardrobe'));

type Draft = { key: string; url: string; isClothing: boolean; aiSkipped: boolean; tags: Tags };

export default function NewItem() {
  const p = usePalette();
  const { t, lang } = useI18n();
  const errorText = useErrorText();
  const create = useCreateItem();
  const [preview, setPreview] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      setDraft({ key: out.image_key, url: out.image_url, isClothing: out.is_clothing, aiSkipped: !!out.ai_skipped, tags: out.tags });
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
      await create.mutateAsync({ ...draft.tags, image_key: draft.key });
      close();
    } catch (e) {
      setError(errorText(e));
    }
  }

  const shown = draft ? imageSource(draft.url, draft.key) : preview ? { uri: preview } : null;

  return (
    <Screen edges={['top', 'bottom']}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: space.md }}>
        <T variant="heading" accessibilityRole="header">
          {t.add.title}
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
          <T variant="body" color="inkSoft">
            {t.add.tip}
          </T>
          {Platform.OS !== 'web' ? <Button label={t.add.camera} onPress={() => pick('camera')} /> : null}
          <Button label={t.add.library} kind={Platform.OS === 'web' ? 'primary' : 'secondary'} onPress={() => pick('library')} />
        </View>
      )}

      {error ? (
        <View style={{ marginTop: space.lg }}>
          <Notice tone="error">{error}</Notice>
        </View>
      ) : null}

      {draft ? (
        <View style={{ marginTop: space.xl, gap: space.xl }}>
          {draft.aiSkipped ? <Notice>{t.add.aiSkipped}</Notice> : !draft.isClothing ? <Notice>{t.add.notClothing}</Notice> : null}
          <TagEditor value={draft.tags} onChange={(tags) => setDraft({ ...draft, tags })} />
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
