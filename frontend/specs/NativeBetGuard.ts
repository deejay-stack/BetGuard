import type { TurboModule, CodegenTypes } from 'react-native';
import { TurboModuleRegistry } from 'react-native';

export interface Spec extends TurboModule {
  getBridgeVersion(): number;
  getThemePreference(): string;
  setThemePreference(mode: string): Promise<void>;
  getSnapshot(): Promise<string>;
  configureDetection(baseUrl: string): Promise<void>;
  startProtection(): Promise<void>;
  stopProtection(): Promise<void>;
  saveRule(
    input: string,
    action: string,
    includeSubdomains: boolean,
  ): Promise<string>;
  removeRule(domain: string): Promise<void>;
  checkLink(input: string): Promise<string>;
  resolveLink(input: string): Promise<string>;
  clearHistory(): Promise<void>;
  readonly onSnapshot: CodegenTypes.EventEmitter<string>;
}

// iOS can display an honest unsupported state while native support is pending.
export default TurboModuleRegistry.get<Spec>('NativeBetGuard');
