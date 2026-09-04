import "./scripts/load-env.js";
import type { ExpoConfig } from "expo/config";

const env = {
  appName: "FlowCore Mobile",
  appSlug: "flowcore-mobile",
  scheme: "flowcoremobile",
  iosBundleId: "com.flowcore.mobile",
  androidPackage: "com.flowcore.mobile",
};

const config: ExpoConfig = {
  name: env.appName, slug: env.appSlug, version: "1.0.0", owner: "dmn0712", orientation: "portrait", icon: "./assets/images/icon.png", scheme: env.scheme, userInterfaceStyle: "dark", newArchEnabled: true,
  ios: { supportsTablet: true, bundleIdentifier: env.iosBundleId, infoPlist: { ITSAppUsesNonExemptEncryption: false } },
  android: { adaptiveIcon: { backgroundColor: "#08111F", foregroundImage: "./assets/images/android-icon-foreground.png", backgroundImage: "./assets/images/android-icon-background.png", monochromeImage: "./assets/images/android-icon-monochrome.png" }, edgeToEdgeEnabled: true, predictiveBackGestureEnabled: false, package: env.androidPackage, versionCode: 1, permissions: ["POST_NOTIFICATIONS"], intentFilters: [{ action: "VIEW", autoVerify: true, data: [{ scheme: env.scheme, host: "*" }], category: ["BROWSABLE", "DEFAULT"] }] },
  web: { bundler: "metro", output: "static", favicon: "./assets/images/favicon.png" },
  plugins: ["expo-router", ["expo-splash-screen", { image: "./assets/images/splash-icon.png", imageWidth: 200, resizeMode: "contain", backgroundColor: "#08111F", dark: { backgroundColor: "#08111F" } }], ["expo-build-properties", { android: { buildArchs: ["armeabi-v7a", "arm64-v8a"], minSdkVersion: 24 } }]],
  experiments: { typedRoutes: true, reactCompiler: true },
};

export default config;
