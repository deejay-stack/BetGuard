import React from 'react';
import {
  AccessibilityInfo,
  Alert,
  AppState,
  type AppStateStatus,
} from 'react-native';
import Renderer, { act } from 'react-test-renderer';
import { HoldButton, HOLD_DURATION } from '../src/components/HoldButton';
import { ThemeProvider } from '../src/state/ThemeContext';
jest.mock('../specs/NativeBetGuard', () => ({
  __esModule: true,
  default: null,
}));
let renderer: Renderer.ReactTestRenderer;
beforeEach(() => {
  jest.useFakeTimers();
  jest
    .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
    .mockResolvedValue(true);
  jest
    .spyOn(AccessibilityInfo, 'isScreenReaderEnabled')
    .mockResolvedValue(false);
});
afterEach(async () => {
  await act(() => renderer?.unmount());
  jest.useRealTimers();
  jest.restoreAllMocks();
});
async function mount(onComplete: () => void, disabled = false, cancelKey = 0) {
  await act(async () => {
    renderer = Renderer.create(
      <ThemeProvider>
        <HoldButton
          onComplete={onComplete}
          disabled={disabled}
          cancelKey={cancelKey}
        />
      </ThemeProvider>,
    );
  });
  return holdControl();
}
function holdControl() {
  return renderer.root.findAll(
    node => node.props.accessibilityLabel === 'Hold to pause protection',
  )[0];
}
test('releasing early clears progress and never stops protection', async () => {
  const stop = jest.fn();
  const button = await mount(stop);
  act(() => button.props.onPressIn());
  act(() => jest.advanceTimersByTime(1000));
  expect(JSON.stringify(renderer.toJSON())).toContain('40%');
  act(() => button.props.onPressOut());
  act(() => jest.advanceTimersByTime(HOLD_DURATION));
  expect(stop).not.toHaveBeenCalled();
  expect(JSON.stringify(renderer.toJSON())).not.toContain('40%');
});
test('a completed hold stops exactly once and cannot repeat while held', async () => {
  const stop = jest.fn();
  const button = await mount(stop);
  act(() => button.props.onPressIn());
  act(() => jest.advanceTimersByTime(HOLD_DURATION + 100));
  act(() => jest.advanceTimersByTime(5000));
  act(() => button.props.onPressOut());
  expect(stop).toHaveBeenCalledTimes(1);
});
test('a disabled or blurred control cannot complete a pending hold', async () => {
  const stop = jest.fn();
  const button = await mount(stop);
  act(() => button.props.onPressIn());
  act(() => jest.advanceTimersByTime(1000));
  await act(async () =>
    renderer.update(
      <ThemeProvider>
        <HoldButton onComplete={stop} cancelKey={1} />
      </ThemeProvider>,
    ),
  );
  act(() => jest.advanceTimersByTime(3000));
  expect(stop).not.toHaveBeenCalled();
  await act(async () =>
    renderer.update(
      <ThemeProvider>
        <HoldButton onComplete={stop} disabled />
      </ThemeProvider>,
    ),
  );
  act(() => holdControl().props.onPressIn());
  act(() => jest.advanceTimersByTime(3000));
  expect(stop).not.toHaveBeenCalled();
});
test('backgrounding the app cancels a hold', async () => {
  let change!: (state: AppStateStatus) => void;
  jest
    .spyOn(AppState, 'addEventListener')
    .mockImplementation((type, listener) => {
      if (type === 'change') change = listener;
      return { remove: jest.fn() };
    });
  const stop = jest.fn();
  const button = await mount(stop);
  act(() => button.props.onPressIn());
  act(() => change('background'));
  act(() => jest.advanceTimersByTime(3000));
  expect(stop).not.toHaveBeenCalled();
});
test('screen readers can confirm pausing without a timed gesture', async () => {
  (AccessibilityInfo.isScreenReaderEnabled as jest.Mock).mockResolvedValue(
    true,
  );
  const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  const stop = jest.fn();
  const button = await mount(stop);
  act(() => button.props.onPress());
  expect(stop).not.toHaveBeenCalled();
  act(() =>
    alert.mock.calls[0][2]
      ?.find(action => action.text === 'Pause protection')
      ?.onPress?.(),
  );
  expect(stop).toHaveBeenCalledTimes(1);
});
