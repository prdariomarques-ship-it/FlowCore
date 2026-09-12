module.exports = function (api) {
  api.cache(true);
  return {
    presets: [["babel-preset-expo", { jsxImportSource: "nativewind" }], "nativewind/babel"],
    // Required by react-native-reanimated 4.x (pulled in by nativewind via
    // react-native-css-interop). Must stay last in the plugin list.
    plugins: ["react-native-worklets/plugin"],
  };
};
