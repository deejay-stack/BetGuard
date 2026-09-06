module.exports = {
  root: true,
  extends: '@react-native',
  ignorePatterns: ['build/**'],
  rules: {
    'no-void': ['warn', { allowAsStatement: true }],
    'react/no-unstable-nested-components': ['warn', { allowAsProps: true }],
  },
};
