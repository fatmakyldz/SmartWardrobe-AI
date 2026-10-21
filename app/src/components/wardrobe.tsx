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
  onWorn,
  onEdit,
}: {
  outfit: Outfit;
  width: number;
  onRate?: (r: -1 | 1) => void;
  onOpenItem?: (item: Item) => void;
  onWorn?: () => void; // "wore it today"; the button turns into a state once worn_at is today
  onEdit?: () => void;
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
        {outfit.source === 'ai_edited' ? (
          <T variant="tiny" color="muted">
            {t.today.edited}
          </T>
        ) : null}
        <T variant="body" color="inkSoft" style={{ marginTop: space.xs }}>
          {outfit.reason}
        </T>
        {onWorn || onEdit ? (
          <View style={{ flexDirection: 'row', gap: space.sm, marginTop: space.lg }}>
            {onWorn ? (
              wornToday(outfit) ? (
                <View style={{ flex: 1, justifyContent: 'center' }}>
                  <T variant="small" color="muted">
                    {'\u2713'} {t.today.wornDone}
                  </T>
                </View>
              ) : (
                <Button label={t.today.worn} kind="secondary" onPress={onWorn} style={{ flex: 1 }} />
              )
            ) : null}
            {onEdit ? <Button label={t.today.edit} kind="ghost" onPress={onEdit} style={{ flex: 1 }} /> : null}
          </View>
        ) : null}
        {onRate ? (
          <View style={{ flexDirection: 'row', gap: space.sm, marginTop: onWorn || onEdit ? space.sm : space.lg }}>
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

/** Device-local day. The backend counts one wear per day in the user's timezone (services/outfits.py);
 *  around midnight with a mismatch this can disagree by one tap, in which case the server just returns
 *  the same worn_at. The app's User type has no timezone yet (AI-08). */
export function wornToday(outfit: Outfit): boolean {
  if (!outfit.worn_at) return false;
  const d = new Date(outfit.worn_at);
  const now = new Date();
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
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
