import { Image } from 'expo-image';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Alert, Platform, Pressable, View } from 'react-native';

import { CloseIcon } from '@/components/icons';
import { TagEditor } from '@/components/TagEditor';
import { Button, Notice, Screen, T } from '@/components/ui';
import { imageSource, Item, Tags } from '@/lib/api';
import { useErrorText } from '@/lib/errors';
import { useI18n } from '@/lib/i18n';
import { useDeleteItem, useItems, useUpdateItem } from '@/lib/queries';
import { radius, space, usePalette } from '@/lib/theme';

const close = () => (router.canGoBack() ? router.back() : router.replace('/wardrobe'));

export default function ItemDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const p = usePalette();
  const { t } = useI18n();
  const errorText = useErrorText();
  const items = useItems();
  const item = items.data?.find((i) => i.id === id);

  return (
    <Screen edges={['top', 'bottom']}>
      <View style={{ flexDirection: 'row', justifyContent: 'flex-end', paddingVertical: space.md }}>
        <Pressable accessibilityRole="button" accessibilityLabel={t.common.close} onPress={close} hitSlop={12}>
          <CloseIcon color={p.ink} />
        </Pressable>
      </View>
      {item ? (
        <Editor key={item.id} item={item} />
      ) : items.isError ? (
        <Notice tone="error">{errorText(items.error)}</Notice>
      ) : (
        <T variant="body" color="muted">
          …
        </T>
      )}
    </Screen>
  );
}

function initialTags(item: Item): Tags {
  const { id: _id, image_key: _k, image_url: _u, created_at: _c, ...rest } = item;
  return rest;
}

function Editor({ item }: { item: Item }) {
  const p = usePalette();
  const { t } = useI18n();
  const errorText = useErrorText();
  const update = useUpdateItem();
  const remove = useDeleteItem();
  const [tags, setTags] = useState<Tags>(() => initialTags(item));
  const [error, setError] = useState<string | null>(null);
  const id = item.id;

  async function save() {
    setError(null);
    try {
      await update.mutateAsync({ id, ...tags });
      close();
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function del() {
    const ok =
      Platform.OS === 'web'
        ? globalThis.confirm?.(t.item.deleteConfirm) ?? false
        : await new Promise<boolean>((resolve) =>
            Alert.alert('', t.item.deleteConfirm, [
              { text: t.common.cancel, style: 'cancel', onPress: () => resolve(false) },
              { text: t.common.delete, style: 'destructive', onPress: () => resolve(true) },
            ]),
          );
    if (!ok) return;
    try {
      await remove.mutateAsync(id);
      close();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <View style={{ gap: space.xl }}>
      <Image
        source={imageSource(item.image_url, item.image_key)}
        style={{ width: '100%', aspectRatio: 1, borderRadius: radius.lg, backgroundColor: p.surfaceAlt }}
        contentFit="cover"
      />
      <TagEditor value={tags} onChange={setTags} />
      {error ? <Notice tone="error">{error}</Notice> : null}
      <Button label={t.item.save} onPress={save} loading={update.isPending} />
      <Button label={t.item.delete} kind="danger" onPress={del} loading={remove.isPending} />
    </View>
  );
}
