module.exports = {
  preset: '@react-native/jest-preset',
  transform: { '^.+\\.(js|jsx|mjs|ts|tsx)$': 'babel-jest' },
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react-native|@react-native(-community)?|@react-navigation|react-native-safe-area-context|react-native-screens|react-native-svg|lucide-react-native)/)',
  ],
  setupFilesAfterEnv: ['./jest.setup.js'],
};
