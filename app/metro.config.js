// Sentry's Metro config adds debug ids so uploaded source maps match the bundle (EAS builds and the
// web export). It is Expo's default config underneath; with no DSN it changes nothing visible.
const { getSentryExpoConfig } = require('@sentry/react-native/metro');

// Errors only: the Session Replay and User Feedback code would otherwise ship in the web bundle.
module.exports = getSentryExpoConfig(__dirname, { includeWebReplay: false, includeWebFeedback: false });
