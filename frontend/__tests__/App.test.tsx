/**
 * @format
 */

import React from 'react';
import { AccessibilityInfo } from 'react-native';
import ReactTestRenderer from 'react-test-renderer';
import App from '../App';

test('renders all tabs without claiming protection when the native module is unavailable', async () => {
  const motion = jest
    .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
    .mockResolvedValue(true);
  let renderer: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    renderer = ReactTestRenderer.create(<App />);
  });
  const rendered = JSON.stringify(renderer!.toJSON());
  for (const label of [
    'Home',
    'Check a link',
    'Protection',
    'Activity',
    'Settings',
    'Android build required',
  ]) {
    expect(rendered).toContain(label);
  }
  expect(rendered).not.toContain('DNS filter is running');
  await ReactTestRenderer.act(() => renderer!.unmount());
  motion.mockRestore();
});
