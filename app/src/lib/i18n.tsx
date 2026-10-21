import { getLocales } from 'expo-localization';
import { createContext, ReactNode, useCallback, useContext, useMemo, useState } from 'react';

import { APP_NAME } from './brand';

export type Lang = 'en' | 'tr';

const en = {
  welcome: {
    tagline: 'Outfits from the clothes you already own, for today’s weather.',
    points: [
      'Photograph a piece; we fill in colour, fabric and season.',
      'Pick where you’re going; get outfits built only from your wardrobe.',
      'Like or skip outfits and the next ones follow your taste.',
    ],
    demo: 'Try with a sample wardrobe',
    signIn: 'Sign in',
    signUp: 'Create account',
    demoNote: 'The sample account is private to you and deleted after 24 hours.',
  },
  auth: {
    signInTitle: 'Welcome back',
    signUpTitle: 'Create your account',
    name: 'Name',
    email: 'Email',
    password: 'Password',
    passwordHint: 'At least 8 characters',
    signIn: 'Sign in',
    signUp: 'Create account',
    haveAccount: 'Already have an account? Sign in',
    noAccount: 'New here? Create an account',
    forgot: 'Forgot your password?',
    forgotTitle: 'Reset your password',
    forgotIntro: 'Enter your account’s email and we’ll send you a link to choose a new password.',
    forgotSend: 'Send link',
    forgotSent: 'If an account uses this email, a link is on its way. It works for 1 hour.',
    resetTitle: 'Choose a new password',
    newPassword: 'New password',
    resetSave: 'Save password',
    resetDone: 'Password changed. You’re signed out everywhere; sign in with the new password.',
    verifyTitle: 'Confirming your email',
    verified: 'Your email is confirmed. Outfit suggestions and photo tagging are on.',
    continue: 'Continue',
    backToSignIn: 'Go to sign in',
    missingToken: 'This link is incomplete. Open it again from the email.',
  },
  onboarding: {
    title: 'Three quick questions',
    intro: 'So the first outfits already feel like you. You can change these any time.',
    q1: 'How would you describe your style?',
    q2: 'Which colour worlds do you live in?',
    q3: 'What matters most when you pick an outfit?',
    pickMany: 'Pick any that fit',
    go: 'Show me outfits',
    skip: 'Skip for now',
    step: (n: number, total: number) => `${n} of ${total}`,
  },
  claim: {
    title: 'Set up your own wardrobe',
    intro: 'Your answers move to your new account. Keep the sample pieces to start from something, or begin empty.',
    keepItems: 'Keep the 17 sample pieces',
    keepItemsHint: 'With them, the outfits you liked come along too.',
    startEmpty: 'Start with an empty wardrobe',
  },
  style: {
    title: 'Style preferences',
    intro: 'Everything here goes into every suggestion.',
    styles: 'Your style',
    palettes: 'Colour worlds',
    priority: 'What matters most',
    liked: 'Colours you love',
    disliked: 'Colours you avoid',
    avoid: 'Never suggest',
    summary: 'What we’ve learned from your likes',
    saved: 'Saved.',
  },
  styleNames: {
    minimal: 'Minimal', classic: 'Classic', casual: 'Relaxed', bold: 'Bold', sporty: 'Sporty',
    romantic: 'Romantic', streetwear: 'Streetwear', boho: 'Boho',
  },
  paletteNames: { neutral: 'Neutrals', dark: 'Dark tones', vivid: 'Vivid colour', pastel: 'Pastels' },
  priorityNames: { comfort: 'Comfort', elegance: 'Looking sharp', weather: 'The weather', variety: 'Variety' },
  tabs: { today: 'Today', wardrobe: 'Wardrobe', saved: 'Saved', profile: 'Profile' },
  today: {
    noCity: 'Where are you today?',
    setCity: 'Choose your city',
    weatherLine: (city: string, temp: number, sky: string) => `${temp}° and ${sky} in ${city}`,
    range: (min: number, max: number, rain: number) => `${min}° to ${max}° today, ${rain}% chance of rain`,
    occasion: 'Where are you going?',
    note: 'Anything else? (optional)',
    notePlaceholder: 'e.g. lots of walking, want to look sharp',
    suggest: 'Suggest outfits',
    suggesting: 'Putting outfits together…',
    again: 'Suggest again',
    firstDemo: 'Here’s a first look from the sample wardrobe, for today’s weather.',
    incomplete: 'Add at least a top and a bottom, or a dress, and outfits will appear here.',
    verifyBanner: (email: string) => `Confirm your email to get outfit suggestions. We sent a link to ${email}.`,
    resend: 'Send the link again',
    resent: 'Sent. Check your inbox (and spam).',
    addItems: 'Add clothes',
    like: 'Like',
    skip: 'Not for me',
    liked: 'Saved to liked',
  },
  sky: {
    clear: 'clear',
    cloudy: 'cloudy',
    overcast: 'overcast',
    fog: 'foggy',
    drizzle: 'drizzly',
    rain: 'rainy',
    snow: 'snowy',
    storm: 'stormy',
  },
  occasions: {
    casual: 'Everyday',
    work: 'Work',
    formal: 'Formal',
    date: 'Date',
    sport: 'Sport',
    party: 'Party',
    travel: 'Travel',
  },
  wardrobe: {
    title: 'Wardrobe',
    count: (n: number) => (n === 1 ? '1 piece' : `${n} pieces`),
    all: 'All',
    empty: 'Your wardrobe is empty. Add a photo of something you wear often to start.',
    add: 'Add a piece',
  },
  add: {
    title: 'Add a piece',
    camera: 'Take a photo',
    library: 'Choose from photos',
    tip: 'Lay the piece flat or hang it against a plain background.',
    analyzing: 'Reading the photo…',
    notClothing: 'This doesn’t look like clothing. Check the details or try another photo.',
    aiSkipped: 'Fill in the details yourself for now. Once your email is confirmed, new photos are tagged for you.',
    save: 'Save to wardrobe',
    retake: 'Use another photo',
  },
  item: {
    name: 'Name',
    category: 'Type',
    colors: 'Colours',
    pattern: 'Pattern',
    warmth: 'Warmth',
    formality: 'Dressiness',
    seasons: 'Seasons',
    save: 'Save changes',
    delete: 'Remove from wardrobe',
    deleteConfirm: 'Remove this piece? Outfits that used it will show without it.',
    warmthScale: ['Very light', 'Light', 'Medium', 'Warm', 'Very warm'],
    formalityScale: ['Sporty', 'Relaxed', 'Smart casual', 'Dressy', 'Formal'],
  },
  categories: {
    top: 'Top',
    bottom: 'Bottom',
    dress: 'Dress',
    outerwear: 'Outerwear',
    shoes: 'Shoes',
    accessory: 'Accessory',
    bag: 'Bag',
  },
  colors: {
    black: 'Black', white: 'White', grey: 'Grey', navy: 'Navy', blue: 'Blue', lightblue: 'Light blue',
    green: 'Green', olive: 'Olive', beige: 'Beige', cream: 'Cream', brown: 'Brown', khaki: 'Khaki',
    red: 'Red', burgundy: 'Burgundy', pink: 'Pink', purple: 'Purple', yellow: 'Yellow', orange: 'Orange',
    gold: 'Gold', silver: 'Silver', multi: 'Multicolour',
  },
  patterns: {
    solid: 'Plain', striped: 'Striped', checked: 'Checked', floral: 'Floral', printed: 'Printed',
    denim: 'Denim', knit: 'Knit', leather: 'Leather', other: 'Other',
  },
  seasons: { spring: 'Spring', summer: 'Summer', autumn: 'Autumn', winter: 'Winter' },
  saved: {
    title: 'Saved outfits',
    liked: 'Liked',
    all: 'Recent',
    empty: 'Outfits you like are kept here.',
  },
  profile: {
    title: 'Profile',
    city: 'City',
    useLocation: 'Use my location',
    searchCity: 'Search for a city',
    language: 'Language',
    demoBanner: 'You’re using a sample wardrobe. It will be deleted after 24 hours.',
    createReal: 'Create your own account',
    stylePrefs: 'Style preferences',
    signOut: 'Sign out',
    deleteAccount: 'Delete account',
    deleteConfirm: 'This permanently deletes your account, wardrobe photos and outfits.',
    privacy: 'Privacy policy',
    version: (v: string) => `${APP_NAME} ${v}`,
  },
  common: { cancel: 'Cancel', delete: 'Delete', ok: 'OK', retry: 'Try again', close: 'Close' },
  errors: {
    invalid_credentials: 'That email and password don’t match.',
    email_taken: 'An account with this email already exists. Sign in instead.',
    rate_limited: 'That’s a lot of requests. Wait a few minutes and try again.',
    ai_busy: 'The AI is busy right now. Try again in a minute.',
    ai_unavailable: 'The AI couldn’t answer. Try again.',
    ai_bad_reply: 'The AI answer didn’t make sense. Try again.',
    ai_not_configured: 'AI features aren’t set up on this server yet.',
    unsupported_image: 'This file isn’t a photo we can read. Use a JPG, PNG or HEIC.',
    image_too_large: 'This photo is over 10 MB. Choose a smaller one.',
    wardrobe_incomplete: 'Add at least a top and a bottom, or a dress, first.',
    email_unverified: 'Confirm your email first: we sent you a link.',
    invalid_token: 'This link has expired or was already used. Ask for a new one.',
    wardrobe_full: 'Your wardrobe has reached 300 pieces. Remove some to add more.',
    weather_unavailable: 'Weather isn’t available right now.',
    network: 'Can’t reach the server. Check your connection and try again.',
    validation: 'Check the highlighted fields.',
    unknown: 'Something went wrong. Try again.',
  },
};

type Dict = typeof en;

const tr: Dict = {
  welcome: {
    tagline: 'Zaten sahip olduğun kıyafetlerden, bugünün havasına göre kombinler.',
    points: [
      'Bir parçanın fotoğrafını çek; rengini, kumaşını ve mevsimini biz dolduralım.',
      'Nereye gittiğini seç; sadece senin gardırobundan kombinler gelsin.',
      'Beğen ya da geç; sonraki öneriler zevkine göre şekillensin.',
    ],
    demo: 'Örnek gardıropla dene',
    signIn: 'Giriş yap',
    signUp: 'Hesap oluştur',
    demoNote: 'Örnek hesap sadece sana özel ve 24 saat sonra silinir.',
  },
  auth: {
    signInTitle: 'Tekrar hoş geldin',
    signUpTitle: 'Hesabını oluştur',
    name: 'Ad',
    email: 'E-posta',
    password: 'Şifre',
    passwordHint: 'En az 8 karakter',
    signIn: 'Giriş yap',
    signUp: 'Hesap oluştur',
    haveAccount: 'Hesabın var mı? Giriş yap',
    noAccount: 'Yeni misin? Hesap oluştur',
    forgot: 'Şifreni mi unuttun?',
    forgotTitle: 'Şifreni sıfırla',
    forgotIntro: 'Hesabının e-postasını yaz, yeni şifre belirlemen için bir bağlantı gönderelim.',
    forgotSend: 'Bağlantı gönder',
    forgotSent: 'Bu e-postayla bir hesap varsa bağlantı yolda. 1 saat geçerli.',
    resetTitle: 'Yeni şifre belirle',
    newPassword: 'Yeni şifre',
    resetSave: 'Şifreyi kaydet',
    resetDone: 'Şifren değişti. Tüm cihazlarda oturumun kapandı; yeni şifrenle giriş yap.',
    verifyTitle: 'E-postan doğrulanıyor',
    verified: 'E-postan doğrulandı. Kombin önerileri ve fotoğraf etiketleme açık.',
    continue: 'Devam et',
    backToSignIn: 'Girişe git',
    missingToken: 'Bu bağlantı eksik. E-postadaki bağlantıyı yeniden aç.',
  },
  onboarding: {
    title: 'Üç kısa soru',
    intro: 'İlk kombinler daha baştan sana benzesin diye. Bunları istediğin zaman değiştirebilirsin.',
    q1: 'Tarzını nasıl tanımlarsın?',
    q2: 'Hangi renk dünyalarında yaşıyorsun?',
    q3: 'Kombin seçerken en çok ne önemli?',
    pickMany: 'Uyanların hepsini seç',
    go: 'Kombinleri göster',
    skip: 'Şimdilik geç',
    step: (n, total) => `${n} / ${total}`,
  },
  claim: {
    title: 'Kendi gardırobunu kur',
    intro: 'Cevapların yeni hesabına taşınır. Örnek parçaları tutup bir yerden başlayabilir ya da boş başlayabilirsin.',
    keepItems: '17 örnek parçayı tut',
    keepItemsHint: 'Onlarla birlikte beğendiğin kombinler de gelir.',
    startEmpty: 'Boş gardıropla başla',
  },
  style: {
    title: 'Stil tercihleri',
    intro: 'Buradaki her şey her öneriye girer.',
    styles: 'Tarzın',
    palettes: 'Renk dünyaların',
    priority: 'En çok ne önemli',
    liked: 'Sevdiğin renkler',
    disliked: 'Kaçındığın renkler',
    avoid: 'Hiç önerme',
    summary: 'Beğenilerinden öğrendiklerimiz',
    saved: 'Kaydedildi.',
  },
  styleNames: {
    minimal: 'Minimal', classic: 'Klasik', casual: 'Rahat', bold: 'Cesur', sporty: 'Spor',
    romantic: 'Romantik', streetwear: 'Sokak', boho: 'Boho',
  },
  paletteNames: { neutral: 'Nötrler', dark: 'Koyu tonlar', vivid: 'Canlı renkler', pastel: 'Pasteller' },
  priorityNames: { comfort: 'Rahatlık', elegance: 'Şıklık', weather: 'Hava', variety: 'Çeşitlilik' },
  tabs: { today: 'Bugün', wardrobe: 'Gardırop', saved: 'Kayıtlı', profile: 'Profil' },
  today: {
    noCity: 'Bugün neredesin?',
    setCity: 'Şehrini seç',
    weatherLine: (city, temp, sky) => `${locativeTr(city)} ${temp}°, ${sky}`,
    range: (min, max, rain) => `Bugün ${min}° ile ${max}° arası, yağmur ihtimali %${rain}`,
    occasion: 'Nereye gidiyorsun?',
    note: 'Eklemek istediğin bir şey var mı? (isteğe bağlı)',
    notePlaceholder: 'ör. çok yürüyeceğim, şık görünmek istiyorum',
    suggest: 'Kombin öner',
    suggesting: 'Kombinler hazırlanıyor…',
    again: 'Yeniden öner',
    firstDemo: 'Örnek gardıroptan, bugünün havasına göre ilk bakış.',
    incomplete: 'En az bir üst ve bir alt ya da bir elbise ekle, kombinler burada görünsün.',
    verifyBanner: (email) => `Kombin önerileri için e-postanı doğrula. ${email} adresine bir bağlantı gönderdik.`,
    resend: 'Bağlantıyı tekrar gönder',
    resent: 'Gönderildi. Gelen kutunu (ve spam klasörünü) kontrol et.',
    addItems: 'Kıyafet ekle',
    like: 'Beğen',
    skip: 'Bu değil',
    liked: 'Beğenilenlere kaydedildi',
  },
  sky: {
    clear: 'açık',
    cloudy: 'parçalı bulutlu',
    overcast: 'kapalı',
    fog: 'sisli',
    drizzle: 'çisentili',
    rain: 'yağmurlu',
    snow: 'karlı',
    storm: 'fırtınalı',
  },
  occasions: {
    casual: 'Gündelik',
    work: 'İş',
    formal: 'Resmi',
    date: 'Buluşma',
    sport: 'Spor',
    party: 'Parti',
    travel: 'Seyahat',
  },
  wardrobe: {
    title: 'Gardırop',
    count: (n) => `${n} parça`,
    all: 'Tümü',
    empty: 'Gardırobun boş. Başlamak için sık giydiğin bir parçanın fotoğrafını ekle.',
    add: 'Parça ekle',
  },
  add: {
    title: 'Parça ekle',
    camera: 'Fotoğraf çek',
    library: 'Fotoğraflardan seç',
    tip: 'Parçayı düz bir zemine ser ya da sade bir arka plana as.',
    analyzing: 'Fotoğraf okunuyor…',
    notClothing: 'Bu bir kıyafete benzemiyor. Bilgileri kontrol et ya da başka bir fotoğraf dene.',
    aiSkipped: 'Şimdilik bilgileri sen doldur. E-postanı doğruladığında yeni fotoğraflar otomatik etiketlenir.',
    save: 'Gardıroba kaydet',
    retake: 'Başka fotoğraf seç',
  },
  item: {
    name: 'Ad',
    category: 'Tür',
    colors: 'Renkler',
    pattern: 'Desen',
    warmth: 'Sıcaklık',
    formality: 'Şıklık',
    seasons: 'Mevsimler',
    save: 'Değişiklikleri kaydet',
    delete: 'Gardıroptan çıkar',
    deleteConfirm: 'Bu parça çıkarılsın mı? Onu kullanan kombinler parça olmadan görünür.',
    warmthScale: ['Çok ince', 'İnce', 'Orta', 'Kalın', 'Çok kalın'],
    formalityScale: ['Spor', 'Rahat', 'Smart casual', 'Şık', 'Resmi'],
  },
  categories: {
    top: 'Üst',
    bottom: 'Alt',
    dress: 'Elbise',
    outerwear: 'Dış giyim',
    shoes: 'Ayakkabı',
    accessory: 'Aksesuar',
    bag: 'Çanta',
  },
  colors: {
    black: 'Siyah', white: 'Beyaz', grey: 'Gri', navy: 'Lacivert', blue: 'Mavi', lightblue: 'Açık mavi',
    green: 'Yeşil', olive: 'Haki yeşil', beige: 'Bej', cream: 'Krem', brown: 'Kahverengi', khaki: 'Haki',
    red: 'Kırmızı', burgundy: 'Bordo', pink: 'Pembe', purple: 'Mor', yellow: 'Sarı', orange: 'Turuncu',
    gold: 'Altın', silver: 'Gümüş', multi: 'Çok renkli',
  },
  patterns: {
    solid: 'Düz', striped: 'Çizgili', checked: 'Kareli', floral: 'Çiçekli', printed: 'Desenli',
    denim: 'Kot', knit: 'Triko', leather: 'Deri', other: 'Diğer',
  },
  seasons: { spring: 'İlkbahar', summer: 'Yaz', autumn: 'Sonbahar', winter: 'Kış' },
  saved: {
    title: 'Kayıtlı kombinler',
    liked: 'Beğenilenler',
    all: 'Son öneriler',
    empty: 'Beğendiğin kombinler burada durur.',
  },
  profile: {
    title: 'Profil',
    city: 'Şehir',
    useLocation: 'Konumumu kullan',
    searchCity: 'Şehir ara',
    language: 'Dil',
    demoBanner: 'Örnek bir gardırop kullanıyorsun. 24 saat sonra silinecek.',
    createReal: 'Kendi hesabını oluştur',
    stylePrefs: 'Stil tercihleri',
    signOut: 'Çıkış yap',
    deleteAccount: 'Hesabı sil',
    deleteConfirm: 'Hesabın, gardırop fotoğrafların ve kombinlerin kalıcı olarak silinir.',
    privacy: 'Gizlilik politikası',
    version: (v) => `${APP_NAME} ${v}`,
  },
  common: { cancel: 'Vazgeç', delete: 'Sil', ok: 'Tamam', retry: 'Tekrar dene', close: 'Kapat' },
  errors: {
    invalid_credentials: 'E-posta ya da şifre hatalı.',
    email_taken: 'Bu e-postayla bir hesap zaten var. Giriş yapmayı dene.',
    rate_limited: 'Çok fazla istek gönderildi. Birkaç dakika bekleyip tekrar dene.',
    ai_busy: 'Yapay zekâ şu an yoğun. Bir dakika sonra tekrar dene.',
    ai_unavailable: 'Yapay zekâ yanıt veremedi. Tekrar dene.',
    ai_bad_reply: 'Yapay zekânın yanıtı anlaşılamadı. Tekrar dene.',
    ai_not_configured: 'Yapay zekâ özellikleri bu sunucuda henüz kurulmadı.',
    unsupported_image: 'Bu dosya okunabilen bir fotoğraf değil. JPG, PNG ya da HEIC kullan.',
    image_too_large: 'Fotoğraf 10 MB’tan büyük. Daha küçük bir fotoğraf seç.',
    wardrobe_incomplete: 'Önce en az bir üst ve bir alt ya da bir elbise ekle.',
    email_unverified: 'Önce e-postanı doğrula: sana bir bağlantı gönderdik.',
    invalid_token: 'Bu bağlantının süresi dolmuş ya da kullanılmış. Yenisini iste.',
    wardrobe_full: 'Gardırobun 300 parçaya ulaştı. Yeni eklemek için bazılarını çıkar.',
    weather_unavailable: 'Hava durumu şu an alınamıyor.',
    network: 'Sunucuya ulaşılamıyor. Bağlantını kontrol edip tekrar dene.',
    validation: 'İşaretli alanları kontrol et.',
    unknown: 'Bir şeyler ters gitti. Tekrar dene.',
  },
};

const dicts: Record<Lang, Dict> = { en, tr };

// Turkish locative suffix with vowel harmony and consonant assimilation: İstanbul'da, İzmir'de, Kars'ta.
export function locativeTr(word: string): string {
  const lower = word.toLocaleLowerCase('tr');
  const vowels = [...lower].filter((c) => 'aeıioöuü'.includes(c));
  const last = vowels[vowels.length - 1] ?? 'a';
  const front = 'eiöü'.includes(last);
  const hard = 'çfhkpsşt'.includes(lower[lower.length - 1] ?? '');
  return `${word}'${hard ? 't' : 'd'}${front ? 'e' : 'a'}`;
}

export function deviceLang(): Lang {
  const code = getLocales()[0]?.languageCode;
  return code === 'tr' ? 'tr' : 'en';
}

type Ctx = { lang: Lang; t: Dict; setLang: (l: Lang) => void };
const I18nContext = createContext<Ctx | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(deviceLang());
  const setLang = useCallback((l: Lang) => setLangState(l), []);
  const value = useMemo(() => ({ lang, t: dicts[lang], setLang }), [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n outside I18nProvider');
  return ctx;
}

// WMO weather code → sky key
export function skyKey(code: number | null | undefined): keyof Dict['sky'] {
  if (code == null || code === 0) return 'clear';
  if (code <= 2) return 'cloudy';
  if (code === 3) return 'overcast';
  if (code === 45 || code === 48) return 'fog';
  if (code >= 51 && code <= 57) return 'drizzle';
  if ((code >= 61 && code <= 67) || (code >= 80 && code <= 82)) return 'rain';
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return 'snow';
  if (code >= 95) return 'storm';
  return 'cloudy';
}
