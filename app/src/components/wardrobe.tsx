import { Image } from 'expo-image';
import { useMemo } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Category, imageSource, Item, Outfit } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { useFreshItem } from '@/lib/queries';
import { radius, space, usePalette } from '@/lib/theme';

import { Button, T, tap } from './ui';

export function ItemTile({ item, onPress, size }: { item: Item; onPress?: () => void; size: number }) {
  const p = usePalette();
  const { t } = useI18n();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${item.name || t.categories[item.category]}`}
      onPress={() => {
        tap();
        onPress?.();
      }}
      style={({ pressed }) => [{ width: size, opacity: pressed ? 0.85 : 1 }]}
    >
      <Image
        source={imageSource(item.image_url, item.image_key)}
        style={{ width: size, height: size, borderRadius: radius.md, backgroundColor: p.surfaceAlt }}
        contentFit="cover"
        transition={150}
      />
      <T variant="small" numberOfLines={1} style={{ marginTop: 6 }}>
        {item.name || t.categories[item.category]}
      </T>
    </Pressable>
  );
}

// Garments are large on the board; small goods (shoes, bags, accessories) sit in a row beneath.
const ORDER: Category[] = ['outerwear', 'top', 'dress', 'bottom', 'shoes', 'bag', 'accessory'];
const SMALL = new Set<Category>(['shoes', 'bag', 'accessory']);
// A fixed, gentle tilt per slot so the board reads as a flat-lay, not a grid.
const TILT = [-2.5, 2, -1.5, 3, -3, 1.5, -1];

/** The outfit as a flat-lay: pieces laid on a board with a hang-tag holding the title and reason. */
export function OutfitBoard({
  outfit,
  width,
  onRate,
  onOpenItem,
}: {
  outfit: Outfit;
  width: number;
  onRate?: (r: -1 | 1) => void;
  onOpenItem?: (item: Item) => void;
}) {
  const p = usePalette();
  const { t } = useI18n();

  const { garments, goods } = useMemo(() => {
    const sorted = [...outfit.items].sort((a, b) => ORDER.indexOf(a.category) - ORDER.indexOf(b.category));
    return { garments: sorted.filter((i) => !SMALL.has(i.category)), goods: sorted.filter((i) => SMALL.has(i.category)) };
  }, [outfit.items]);

  const inner = width - space.lg * 2;
  const big = garments.length === 1 ? inner * 0.62 : (inner - space.md) / 2;
  const small = goods.length ? Math.min((inner - space.md * 2) / 3, big * 0.72) : 0;

  return (
    <View style={{ width }}>
      <View style={[styles.board, { backgroundColor: p.board, padding: space.lg, paddingBottom: space.lg + space.xl }]}>
        <View style={[styles.row, { justifyContent: 'center', columnGap: space.md }]}>
          {garments.map((item, i) => (
            <Piece key={item.id} item={item} size={big} tilt={TILT[i % TILT.length]} onPress={onOpenItem} />
          ))}
        </View>
        {goods.length ? (
          <View style={[styles.row, { justifyContent: 'center', gap: space.md, marginTop: space.md }]}>
            {goods.map((item, i) => (
              <Piece key={item.id} item={item} size={small} tilt={TILT[(i + 3) % TILT.length]} onPress={onOpenItem} />
            ))}
          </View>
        ) : null}
      </View>

      {/* hang-tag */}
      <View style={[styles.tag, { backgroundColor: p.surface, borderColor: p.line }]}>
        <View style={[styles.eyelet, { borderColor: p.line, backgroundColor: p.board }]} />
        <T variant="heading" accessibilityRole="header">
          {outfit.title}
        </T>
        <T variant="body" color="inkSoft" style={{ marginTop: space.xs }}>
          {outfit.reason}
        </T>
        {onRate ? (
          <View style={{ flexDirection: 'row', gap: space.sm, marginTop: space.lg }}>
            <Button
              label={outfit.rating === 1 ? t.today.liked : t.today.like}
              kind={outfit.rating === 1 ? 'primary' : 'secondary'}
              onPress={() => onRate(1)}
              style={{ flex: 1 }}
              accessibilityState={{ selected: outfit.rating === 1 }}
            />
            <Button
              label={t.today.skip}
              kind="ghost"
              onPress={() => onRate(-1)}
              style={{ flex: 1, opacity: outfit.rating === -1 ? 0.5 : 1 }}
            />
          </View>
        ) : null}
      </View>
    </View>
  );
}

function Piece({
  item,
  size,
  tilt,
  onPress,
}: {
  item: Item;
  size: number;
  tilt: number;
  onPress?: (item: Item) => void;
}) {
  const p = usePalette();
  const { t } = useI18n();
  // Outfits can sit in the cache longer than their image links live; the wardrobe list has fresher ones.
  const fresh = useFreshItem(item);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={item.name || t.categories[item.category]}
      onPress={() => onPress?.(item)}
      style={[
        styles.piece,
        { width: size, height: size, transform: [{ rotate: `${tilt}deg` }], backgroundColor: p.surface, shadowColor: '#2A1B26' },
      ]}
    >
      <Image source={imageSource(fresh.image_url, fresh.image_key)} style={{ flex: 1, borderRadius: radius.sm }} contentFit="cover" />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  board: { borderRadius: radius.lg, overflow: 'visible' },
  row: { flexDirection: 'row', flexWrap: 'wrap', rowGap: space.md },
  piece: {
    padding: 5,
    borderRadius: radius.sm + 2,
    shadowOpacity: 0.12,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 3 },
    elevation: 3,
  },
  tag: {
    marginTop: -space.lg,
    marginHorizontal: space.lg,
    padding: space.lg,
    paddingTop: space.xl,
    borderWidth: 1,
    borderRadius: radius.md,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
  },
  eyelet: {
    position: 'absolute',
    top: 10,
    alignSelf: 'center',
    left: '50%',
    marginLeft: -6,
    width: 12,
    height: 12,
    borderRadius: 6,
    borderWidth: 1,
  },
});
