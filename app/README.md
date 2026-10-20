# SmartWardrobe app

Expo (React Native) app for iOS, Android and the web, in English and Turkish.

```bash
npm install
cp .env.example .env.local   # point EXPO_PUBLIC_API_URL at the API
npx expo start               # i = iOS simulator, a = Android, w = web; or scan the QR with Expo Go
npm run typecheck && npm run lint
```

| Path | |
|---|---|
| `src/app/` | screens (Expo Router): `welcome`, `sign-in`, `sign-up`, `(tabs)/today · wardrobe · saved · profile`, `item/new`, `item/[id]` |
| `src/components/` | UI kit (`ui.tsx`), outfit board and item tiles, tag editor, city picker, icons |
| `src/lib/` | API client, auth (token in Keychain/Keystore, localStorage on web), EN/TR strings, theme |

The product name is set in `src/lib/brand.ts` and `app.json` (`name`).

**Web**: `npm run export:web` → `dist/` (Vercel config in `vercel.json`). Live at https://wardrobe.fomertech.com; Vercel builds every push to `main`. Production builds read the API address from `.env.production` (public values, committed); put local overrides in `.env.local`.
**Stores**: `npx eas-cli@latest build --profile preview` (internal APK / TestFlight-ready iOS), `--profile production` for store builds; see `eas.json`.
