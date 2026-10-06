import {
  Ban,
  Check,
  Search,
  RotateCcw,
  ShieldCheck,
  ShieldAlert,
  ShieldX,
} from 'lucide-react-native';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  BackHandler,
  Linking,
  Text,
  TextInput,
  View,
} from 'react-native';
import type { BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import type { Tabs } from '../../App';
import { useBetGuard } from '../state/BetGuardContext';
import { BackendStatus } from '../components/BackendStatus';
import type { LinkResult } from '../state/types';
import { Badge, Button, Card, Notice, Page } from '../components/ui';
import { logFailure } from '../state/nativeContract';
import { useTheme } from '../state/ThemeContext';
import { CatalogError, checkCatalog, type CatalogResult } from '../api/catalog';
import { checkDomain, type DomainDecision } from '../api/domain';
import { API_BASE_URL } from '../api/config';

type RemoteState =
  | { status: 'idle' | 'loading' | 'cancelled' }
  | { status: 'local' }
  | { status: 'done'; result: CatalogResult }
  | { status: 'error'; message: string };

export function CheckScreen({
  navigation,
}: {
  navigation?: BottomTabNavigationProp<Tabs, 'Check'>;
}) {
  const { colors, styles, mode } = useTheme();
  const [input, setInput] = useState('');
  const [focused, setFocused] = useState(false);
  const [result, setResult] = useState<LinkResult | null>(null);
  const [remote, setRemote] = useState<RemoteState>({ status: 'idle' });
  const [detection, setDetection] = useState<DomainDecision | null>(null);
  const [detectionError, setDetectionError] = useState(false);
  const generation = useRef(0);
  const localPending = useRef(false);
  const pending = useRef<AbortController | null>(null);
  const { check, resolve, save, remove, snapshot, available, busy } =
    useBetGuard();
  const inspectedDomain = result?.domain;
  const rulesKey = JSON.stringify(snapshot?.rules ?? []);
  const invalidate = useCallback(() => {
    generation.current++;
    pending.current?.abort();
    pending.current = null;
  }, []);
  useEffect(() => invalidate, [invalidate]);
  useEffect(
    () =>
      navigation?.addListener('blur', () => {
        invalidate();
        setRemote(current =>
          current.status === 'loading' ? { status: 'cancelled' } : current,
        );
      }),
    [navigation, invalidate],
  );
  useEffect(() => {
    let current = true;
    const revision = generation.current;
    if (inspectedDomain) {
      void resolve(inspectedDomain).then(next => {
        if (current && revision === generation.current) setResult(next ?? null);
      });
    }
    return () => {
      current = false;
    };
  }, [inspectedDomain, rulesKey, resolve]);

  async function lookup(domain: string, revision: number) {
    if (!API_BASE_URL) {
      setRemote({ status: 'local' });
      setDetection(null);
      setDetectionError(false);
      return;
    }
    const controller = new AbortController();
    pending.current = controller;
    setRemote({ status: 'loading' });
    setDetection(null);
    setDetectionError(false);
    try {
      // Both use the existing HTTP client. Catalog availability does not gate
      // the independent finalized runtime or silently change a local rule.
      const [catalogCheck, domainCheck] = await Promise.allSettled([
        checkCatalog(domain, controller.signal),
        checkDomain(domain, controller.signal),
      ]);
      if (revision !== generation.current) return;
      if (domainCheck.status === 'fulfilled') setDetection(domainCheck.value);
      else setDetectionError(true);
      if (catalogCheck.status === 'rejected') throw catalogCheck.reason;
      const next = catalogCheck.value;
      if (revision === generation.current)
        setRemote({ status: 'done', result: next });
    } catch (error) {
      if (revision !== generation.current) return;
      if (error instanceof CatalogError && error.code === 'cancelled') {
        setRemote({ status: 'cancelled' });
      } else {
        const message =
          error instanceof CatalogError && error.code === 'timeout'
            ? 'The website check took too long to respond. Try again when your connection is ready.'
            : error instanceof CatalogError && error.code === 'invalid'
            ? 'The service could not validate this hostname. Edit the link and try again.'
            : error instanceof CatalogError && error.code === 'configuration'
            ? 'The classification service is not configured. Local manual rules still work.'
            : 'Online classification is temporarily unavailable. Local protection and manual rules remain available.';
        setRemote({ status: 'error', message });
      }
    } finally {
      if (revision === generation.current) pending.current = null;
    }
  }
  async function inspect() {
    // Keyboard and button share a synchronous guard before React commits state.
    // A repeated submit must not record another history row.
    if (
      !available ||
      busy ||
      !input.trim() ||
      localPending.current ||
      pending.current
    )
      return;
    localPending.current = true;
    invalidate();
    const revision = generation.current;
    setResult(null);
    setRemote({ status: 'idle' });
    setDetection(null);
    setDetectionError(false);
    let next: LinkResult | undefined;
    try {
      next = await check(input);
    } finally {
      localPending.current = false;
    }
    if (revision !== generation.current) return;
    setResult(next ?? null);
    if (next) await lookup(next.domain, revision);
  }
  async function retry() {
    if (!result || pending.current) return;
    invalidate();
    await lookup(result.domain, generation.current);
  }
  async function change(action: 'block' | 'allow') {
    if (!result) return;
    const revision = generation.current;
    const existing = snapshot?.rules.find(
      rule => rule.domain === result.domain,
    );
    const domain = await save(
      result.domain,
      action,
      existing?.includeSubdomains ?? false,
    );
    if (domain) {
      const next = await resolve(domain);
      if (revision === generation.current) setResult(next ?? null);
    }
  }
  const catalog = remote.status === 'done' ? remote.result : null;
  const hasOverride =
    !!result && !!snapshot?.rules.some(rule => rule.domain === result.domain);
  async function removeOverride() {
    if (!result) return;
    const revision = generation.current;
    if (await remove(result.domain)) {
      const next = await resolve(result.domain);
      if (revision === generation.current) setResult(next ?? null);
    }
  }
  const [details, setDetails] = useState(false);
  const [openError, setOpenError] = useState<string | null>(null);
  const localBlock =
    result?.matchedDomain !== null && result?.action === 'block';
  const localAllow =
    result?.matchedDomain !== null && result?.action === 'allow';
  const warning =
    detection?.intervention === 'WARN' && !localBlock && !localAllow;
  const recommendedBlock =
    !localAllow && (localBlock || detection?.enforcement_action === 'BLOCK');
  const ResultIcon = recommendedBlock
    ? ShieldX
    : warning
    ? ShieldAlert
    : ShieldCheck;
  const resultColor = recommendedBlock
    ? colors.blocked
    : warning
    ? colors.review
    : colors.allowed;
  const enforced =
    snapshot?.state === 'active' && (localBlock || !!snapshot.detectionEnabled);
  async function continueOnce() {
    if (!result || localBlock) return;
    setOpenError(null);
    try {
      await Linking.openURL(`https://${result.domain}`);
    } catch (error) {
      logFailure('open website', error);
      setOpenError(
        'This website could not be opened. Try again in your browser.',
      );
    }
  }
  function resetCheck() {
    invalidate();
    setResult(null);
    setInput('');
    setRemote({ status: 'idle' });
    setDetection(null);
    setDetectionError(false);
    setDetails(false);
    setOpenError(null);
  }
  function goBack() {
    resetCheck();
    navigation?.navigate('Home');
  }
  useEffect(() => {
    if (!navigation) return;
    const subscription = BackHandler.addEventListener(
      'hardwareBackPress',
      () => {
        if (!navigation.isFocused()) return false;
        invalidate();
        navigation.navigate('Home');
        return true;
      },
    );
    return () => subscription.remove();
  }, [navigation, invalidate]);
  return (
    <Page title="Check a website" subtitle="Check first. Make your own choice.">
      <Card>
        <TextInput
          accessibilityLabel="Link to check"
          style={[styles.input, focused && { borderColor: colors.primary }]}
          value={input}
          onChangeText={value => {
            invalidate();
            setInput(value);
            setResult(null);
            setRemote({ status: 'idle' });
            setDetection(null);
            setDetectionError(false);
            setOpenError(null);
            setDetails(false);
          }}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder="example.com or paste a link"
          placeholderTextColor={colors.textMuted}
          keyboardType="url"
          keyboardAppearance={mode}
          selectionColor={colors.primary}
          autoCapitalize="none"
          autoCorrect={false}
          maxLength={2048}
          editable={!busy}
          returnKeyType="search"
          onSubmitEditing={() => {
            void inspect();
          }}
        />
        <Button
          title="Check link"
          icon={Search}
          busy={busy}
          disabled={!available || !input.trim() || remote.status === 'loading'}
          onPress={() => {
            void inspect();
          }}
        />
        <Text style={styles.small}>
          Checking does not turn protection on. Only the website hostname is
          checked; page paths and private query details are not sent.
        </Text>
      </Card>
      {!result && (
        <View style={styles.stack}>
          <Text style={styles.heading}>Your choice comes first</Text>
          <Text style={styles.body}>
            Your saved rule is checked on this phone. Smart advice needs the
            online service. A warning keeps access allowed. To block a website,
            save a Block rule and enable protection on Home.
          </Text>
        </View>
      )}
      {result && (
        <>
          <Card>
            {(detection || result.matchedDomain) && (
              <View style={styles.resultIcon}>
                <ResultIcon size={64} color={resultColor} strokeWidth={1.5} />
              </View>
            )}
            <Text selectable style={styles.title}>
              {result.domain}
            </Text>
            <View accessibilityLiveRegion="polite" style={styles.stack}>
              {remote.status === 'loading' && (
                <View style={styles.row}>
                  <ActivityIndicator color={colors.primary} />
                  <Text style={styles.body}>Checking the website...</Text>
                </View>
              )}
              {remote.status === 'cancelled' && (
                <Text style={styles.body}>
                  Website check cancelled. No new classification was returned.
                </Text>
              )}
              {remote.status === 'local' && (
                <>
                  <Badge text="LOCAL RULE CHECK" />
                  <Text style={styles.body}>
                    {result.matchedDomain
                      ? 'Your saved choice is shown below.'
                      : 'No saved rule for this website. On-device protection allows it unless you add a Block rule.'}
                  </Text>
                  <Text style={styles.small}>
                    Smart advice is not set up in this APK. This local check
                    does not assess whether a website is safe.
                  </Text>
                </>
              )}
              {(detection || result.matchedDomain) && (
                <>
                  <Badge
                    text={
                      localAllow
                        ? 'ALLOWED BY YOUR RULE'
                        : localBlock
                        ? 'BLOCK RULE'
                        : `DETECTION: ${
                            detection?.intervention === 'NONE'
                              ? 'ALLOW'
                              : detection?.intervention
                          }`
                    }
                    tone={
                      recommendedBlock
                        ? 'error'
                        : warning
                        ? 'warning'
                        : 'success'
                    }
                  />
                  <Text style={styles.heading}>
                    {recommendedBlock
                      ? localBlock
                        ? enforced
                          ? 'This site is blocked'
                          : 'Block rule saved'
                        : enforced
                        ? 'This site is blocked'
                        : 'Blocking recommended'
                      : warning
                      ? 'Review recommended'
                      : localAllow
                      ? 'Your allow rule takes priority'
                      : 'Low gambling risk'}
                  </Text>
                  {warning ? (
                    <Notice text="BetGuard detected characteristics associated with gambling websites. This is uncertain; network access remains allowed. This does not identify the website as gambling." />
                  ) : (
                    <Text style={styles.body}>
                      {recommendedBlock
                        ? localBlock
                          ? 'Your saved rule blocks supported DNS requests while protection is on.'
                          : detection?.decision_source ===
                            'verified_gambling_blocklist'
                          ? 'This hostname matches the verified gambling blocklist. BetGuard is helping you stay in control.'
                          : 'Automated detection found a high gambling-risk score. Smart protection blocks supported DNS requests unless your rule allows the site.'
                        : 'This result does not guarantee that a website is safe.'}
                    </Text>
                  )}
                  {detection?.decision_source ===
                    'verified_gambling_blocklist' &&
                    !localAllow &&
                    !localBlock && (
                      <Text style={styles.small}>
                        Source: Verified gambling blocklist
                      </Text>
                    )}
                  {recommendedBlock && (
                    <Text style={styles.small}>
                      This check is a policy result. Actual blocked requests
                      appear in Activity.{' '}
                      {snapshot?.state !== 'active'
                        ? 'Protection is not currently confirmed on.'
                        : !snapshot?.detectionEnabled && !localBlock
                        ? 'Enable online detection on Home to apply this decision.'
                        : ''}
                    </Text>
                  )}
                </>
              )}
              {detectionError && remote.status !== 'cancelled' && (
                <Notice text="Smart advice could not connect. Your saved rule is still shown below; no online safety decision was returned." />
              )}
            </View>
            {remote.status === 'loading' && (
              <Button
                title="Cancel lookup"
                secondary
                onPress={() => {
                  invalidate();
                  setRemote({ status: 'cancelled' });
                  setDetection(null);
                  setDetectionError(false);
                }}
              />
            )}
            {(remote.status === 'cancelled' || detectionError) && (
              <Button
                title="Retry website check"
                icon={RotateCcw}
                secondary
                onPress={() => {
                  void retry();
                }}
              />
            )}
            {warning && (
              <View style={styles.row}>
                <View style={styles.flex}>
                  <Button title="Go back" secondary onPress={goBack} />
                </View>
                <View style={styles.flex}>
                  <Button
                    title="Continue once"
                    onPress={() => {
                      void continueOnce();
                    }}
                  />
                </View>
              </View>
            )}
            {warning && (
              <Text style={styles.small}>
                Continue once opens this hostname in your browser and saves no
                rule.
              </Text>
            )}
            {openError && <Notice text={openError} />}
            {recommendedBlock && (
              <Button title="Back to safety" onPress={goBack} />
            )}
            <Button title="Check another link" secondary onPress={resetCheck} />
          </Card>
          <View style={styles.stack}>
            <Text style={styles.eyebrow}>YOUR LOCAL RULE</Text>
            <Badge
              text={
                result.matchedDomain
                  ? `EFFECTIVE RULE: ${result.action.toUpperCase()}`
                  : 'NO SAVED RULE'
              }
              tone={localBlock ? 'error' : 'primary'}
            />
            <Text style={styles.body}>
              {result.matchedDomain
                ? result.reason
                : 'No matching rule is saved. Online detection applies when enabled; manual mode allows unmatched hostnames.'}
            </Text>
            <View style={styles.row}>
              <View style={styles.flex}>
                <Button
                  title="Block site"
                  icon={Ban}
                  disabled={busy}
                  onPress={() => {
                    void change('block');
                  }}
                />
              </View>
              <View style={styles.flex}>
                <Button
                  title={warning ? 'Always allow' : 'Allow site'}
                  icon={Check}
                  secondary
                  disabled={busy}
                  onPress={() => {
                    void change('allow');
                  }}
                />
              </View>
            </View>
            {hasOverride && (
              <Button
                title="Remove override"
                secondary
                disabled={busy}
                onPress={() => {
                  Alert.alert(
                    'Remove this override?',
                    'Other matching rules or Smart protection can still apply.',
                    [
                      { text: 'Cancel', style: 'cancel' },
                      {
                        text: 'Remove override',
                        style: 'destructive',
                        onPress: () => {
                          void removeOverride();
                        },
                      },
                    ],
                  );
                }}
              />
            )}
            <Text style={styles.small}>
              New rules match this exact hostname. Existing subdomain scope is
              preserved; manage scope in Rules.
            </Text>
          </View>
          <Button
            title={
              details ? 'Hide technical details' : 'Show technical details'
            }
            secondary
            onPress={() => setDetails(!details)}
          />
          {details && (
            <Card>
              <Text style={styles.heading}>Decision details</Text>
              {detection && (
                <Text selectable style={styles.small}>
                  Detection source: {detection.decision_source}
                  {'\n'}ML score: {detection.ml_score ?? 'Not used'}
                  {'\n'}Intervention: {detection.intervention}
                </Text>
              )}
              <Text style={styles.small}>
                Reviewed catalog labels are separate from the network detection
                policy.
              </Text>
              {remote.status === 'error' && <Notice text={remote.message} />}
              {catalog && (
                <View style={styles.stack}>
                  <Badge
                    text={
                      catalog.classification === 'gambling'
                        ? 'GAMBLING'
                        : catalog.classification === 'non_gambling'
                        ? 'NON-GAMBLING'
                        : 'CLASSIFICATION UNKNOWN'
                    }
                  />
                  <Text style={styles.body}>{catalog.explanation}</Text>
                  <Text style={styles.small}>
                    Catalog source: {catalog.source}
                    {catalog.model_version
                      ? ` · Model ${catalog.model_version}`
                      : ''}
                    {catalog.reviewed_at
                      ? ` · Reviewed ${new Date(
                          catalog.reviewed_at,
                        ).toLocaleDateString()}`
                      : ''}
                  </Text>
                </View>
              )}
              <Text style={styles.small}>
                Checked {new Date(result.checkedAt).toLocaleString()}. Saving a
                rule is separate from observing a blocked DNS request.
              </Text>
            </Card>
          )}
        </>
      )}
      {__DEV__ && <BackendStatus />}
    </Page>
  );
}
