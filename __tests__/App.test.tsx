/**
 * @format
 */

import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import App from '../App';

test('renders all tabs without claiming protection when the native module is unavailable', async () => {
  let renderer: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(() => {
    renderer = ReactTestRenderer.create(<App />);
  });
  const rendered = JSON.stringify(renderer!.toJSON());
  for (const label of [
    'Home',
    'Check link',
    'Sites',
    'History',
    'Settings',
    'Android build required',
  ]) {
    expect(rendered).toContain(label);
  }
  expect(rendered).not.toContain('DNS filter is running');
  await ReactTestRenderer.act(() => renderer!.unmount());
});
