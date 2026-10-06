import React from 'react';
import Renderer, { act } from 'react-test-renderer';
import { Text } from 'react-native';
import { ErrorBoundary } from '../src/components/ErrorBoundary';

test('a screen failure renders recovery and retries without displaying the raw exception', async () => {
  const log = jest.spyOn(console, 'error').mockImplementation(() => {});
  let fail = true;
  function Screen() {
    if (fail) throw new Error('private rendering detail');
    return <Text>Recovered screen</Text>;
  }
  let renderer!: Renderer.ReactTestRenderer;
  await act(() => {
    renderer = Renderer.create(
      <ErrorBoundary>
        <Screen />
      </ErrorBoundary>,
    );
  });
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Try again');
  expect(tree).not.toContain('private rendering detail');
  fail = false;
  await act(() =>
    renderer.root
      .find(
        node =>
          node.props.accessibilityLabel === 'Try again' &&
          typeof node.props.onPress === 'function',
      )
      .props.onPress(),
  );
  expect(JSON.stringify(renderer.toJSON())).toContain('Recovered screen');
  await act(() => renderer.unmount());
  log.mockRestore();
});
