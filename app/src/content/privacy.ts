// The privacy policy, in every supported language. Plain text on purpose: it renders in the app
// (/privacy, also the public web page the stores link to) and must stay readable without styling.
// Facts here mirror the backend (docs/AI-00-foundation.md §9): change both when one changes.
import { APP_NAME, SUPPORT_EMAIL } from '@/lib/brand';
import { Lang } from '@/lib/langs';

export const PRIVACY_UPDATED = '2026-10-21';

export type PolicySection = { heading: string; paragraphs: string[] };
export type Policy = { title: string; updated: string; intro: string; sections: PolicySection[] };

const en: Policy = {
  title: 'Privacy policy',
  updated: `Last updated ${PRIVACY_UPDATED}`,
  intro: `${APP_NAME} helps you dress from the clothes you already own. To do that it keeps a small amount of data about you and your wardrobe. This page says what, why, for how long, and what you can do about it.`,
  sections: [
    {
      heading: 'What we keep',
      paragraphs: [
        'Account: your e-mail address, your name, a hashed password (never the password itself), your language, your time zone and, if you set one, your city for the weather.',
        'Wardrobe: the photos you add, the tags describing each piece (category, colours, pattern, warmth, formality, seasons, brand and material if you fill them in), and when you wore them.',
        'Outfits and feedback: the outfits suggested to you or built by you, which ones you liked, disliked or wore, and the occasion, note and weather they were made for.',
        'Style answers: what you told us in the short style questionnaire, and a short written summary of your taste that we build from your wardrobe and feedback.',
        'Usage: how many AI requests you made each day (to apply the daily limits of your plan) and, for a limited time, which request belonged to which account.',
      ],
    },
    {
      heading: 'How the AI part works',
      paragraphs: [
        'When you add a photo, we send a reduced copy of it to an AI model to describe the piece. When you ask for an outfit, we send the descriptions of your pieces (not the photos), the occasion, the weather and your style answers, and the model returns outfit ideas. Any note you type is checked for e-mail addresses and phone numbers, which are masked before the text leaves our servers.',
        'These models are run by third-party providers (currently Anthropic and Groq) under their API terms. We do not use your data to train models, and we do not sell it.',
        'The AI never changes your data directly: everything it returns is checked by our servers before it is saved.',
      ],
    },
    {
      heading: 'Where it lives',
      paragraphs: [
        'Your data is stored on cloud infrastructure we rent (a managed database and a private object store for photos). Photos are private: the app receives short-lived links that expire within minutes.',
        'We use a transactional e-mail service only to send you the confirmation and password-reset links you ask for.',
      ],
    },
    {
      heading: 'How long we keep it',
      paragraphs: [
        'As long as your account exists. When you delete your account, your account, wardrobe, photos, outfits and feedback are deleted. Records of AI usage lose their link to your account at that moment and remain only as anonymous statistics.',
        'Even without deletion, the link between an AI usage record and an account is removed after 90 days.',
        'An account whose e-mail is never confirmed and that is not used for 14 days is deleted automatically. A sample ("demo") wardrobe is deleted 24 hours after it was opened.',
      ],
    },
    {
      heading: 'Your rights',
      paragraphs: [
        'You can see and change your data in the app at any time. From your profile you can download everything we hold about you as one file, and you can delete your account; both take effect immediately.',
        'For anything else — a question, a correction, a complaint — write to us and we will answer.',
      ],
    },
    {
      heading: 'Children',
      paragraphs: [`${APP_NAME} is not intended for children under 16. If you believe a child has created an account, tell us and we will delete it.`],
    },
    {
      heading: 'Changes',
      paragraphs: ['If this policy changes in a way that matters, we will say so in the app before the change applies. The date at the top is the version you are reading.'],
    },
    {
      heading: 'Contact',
      paragraphs: [SUPPORT_EMAIL],
    },
  ],
};

const tr: Policy = {
  title: 'Gizlilik politikası',
  updated: `Son güncelleme ${PRIVACY_UPDATED}`,
  intro: `${APP_NAME}, elindeki kıyafetlerle giyinmene yardım eder. Bunun için senin ve gardırobun hakkında az miktarda veri tutar. Bu sayfa neyi, neden, ne kadar süre tuttuğumuzu ve senin neler yapabileceğini anlatır.`,
  sections: [
    {
      heading: 'Neleri tutuyoruz',
      paragraphs: [
        'Hesap: e-posta adresin, adın, şifrenin özetlenmiş hâli (şifrenin kendisi asla), dilin, saat dilimin ve ayarladıysan hava durumu için şehrin.',
        'Gardırop: eklediğin fotoğraflar, her parçayı tanımlayan etiketler (kategori, renkler, desen, sıcaklık, resmiyet, mevsimler; doldurursan marka ve kumaş) ve ne zaman giydiğin.',
        'Kombinler ve geri bildirim: sana önerilen ya da senin kurduğun kombinler, hangilerini beğendiğin, beğenmediğin ya da giydiğin; hangi durum, not ve hava için hazırlandıkları.',
        'Stil cevapları: kısa stil anketinde söylediklerin ve gardırobunla geri bildiriminden oluşturduğumuz kısa bir zevk özeti.',
        'Kullanım: planının günlük sınırlarını uygulamak için her gün kaç yapay zekâ isteği yaptığın ve sınırlı bir süre için hangi isteğin hangi hesaba ait olduğu.',
      ],
    },
    {
      heading: 'Yapay zekâ kısmı nasıl çalışır',
      paragraphs: [
        'Bir fotoğraf eklediğinde, parçayı tanımlaması için küçültülmüş bir kopyasını bir yapay zekâ modeline gönderiyoruz. Kombin istediğinde parçalarının tanımlarını (fotoğrafları değil), durumu, havayı ve stil cevaplarını gönderiyoruz; model kombin fikirleri döndürüyor. Yazdığın notlarda e-posta adresi ve telefon numarası aranır; bunlar metin sunucularımızdan çıkmadan maskelenir.',
        'Bu modeller üçüncü taraf sağlayıcılar (şu an Anthropic ve Groq) tarafından, kendi API koşulları altında çalıştırılır. Verini model eğitmek için kullanmıyor, satmıyoruz.',
        'Yapay zekâ verini doğrudan değiştirmez: döndürdüğü her şey kaydedilmeden önce sunucularımızda kontrol edilir.',
      ],
    },
    {
      heading: 'Nerede duruyor',
      paragraphs: [
        'Verin kiraladığımız bulut altyapısında saklanır (yönetilen bir veritabanı ve fotoğraflar için özel bir nesne deposu). Fotoğraflar gizlidir: uygulama, dakikalar içinde geçerliliğini yitiren kısa ömürlü bağlantılar alır.',
        'Bir e-posta servisini yalnızca istediğin doğrulama ve şifre sıfırlama bağlantılarını göndermek için kullanıyoruz.',
      ],
    },
    {
      heading: 'Ne kadar süre tutuyoruz',
      paragraphs: [
        'Hesabın var olduğu sürece. Hesabını sildiğinde hesabın, gardırobun, fotoğrafların, kombinlerin ve geri bildirimin silinir. Yapay zekâ kullanım kayıtlarının hesabınla bağı o anda kopar; yalnızca anonim istatistik olarak kalırlar.',
        'Silmesen de, bir yapay zekâ kullanım kaydıyla hesap arasındaki bağ 90 gün sonra kaldırılır.',
        'E-postası hiç doğrulanmayan ve 14 gün kullanılmayan hesaplar otomatik silinir. Örnek ("demo") gardırop açıldıktan 24 saat sonra silinir.',
      ],
    },
    {
      heading: 'Hakların',
      paragraphs: [
        'Verini uygulamada istediğin zaman görebilir ve değiştirebilirsin. Profilinden, hakkında tuttuğumuz her şeyi tek dosya olarak indirebilir ve hesabını silebilirsin; ikisi de anında geçerli olur.',
        'Bunun dışındaki her şey için — soru, düzeltme, şikâyet — bize yaz, cevaplayalım.',
      ],
    },
    {
      heading: 'Çocuklar',
      paragraphs: [`${APP_NAME} 16 yaşından küçükler için tasarlanmamıştır. Bir çocuğun hesap açtığını düşünüyorsan bize bildir, silelim.`],
    },
    {
      heading: 'Değişiklikler',
      paragraphs: ['Bu politika önemli bir şekilde değişirse, değişiklik geçerli olmadan önce uygulamada söyleyeceğiz. Üstteki tarih okuduğun sürümdür.'],
    },
    {
      heading: 'İletişim',
      paragraphs: [SUPPORT_EMAIL],
    },
  ],
};

// Every supported language needs an entry; a missing one is a type error.
export const PRIVACY: Record<Lang, Policy> = { en, tr };
