import {
  Ban,
  Check,
  Globe2,
  Search,
  ShieldCheck,
  RotateCcw,
} from 'lucide-react-native';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Text, TextInput, View } from 'react-native';
import type { BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import type { Tabs } from '../../App';
import { useBetGuard } from '../state/BetGuardContext';
import { BackendStatus } from '../components/BackendStatus';
import type { LinkResult } from '../state/types';
import { Badge, Button, Card, Notice, Page } from '../components/ui';
import { useTheme } from '../state/ThemeContext';
import { CatalogError, checkCatalog, type CatalogResult } from '../api/catalog';
import { checkDomain, type DomainDecision } from '../api/domain';

type RemoteState =
  | { status: 'idle' | 'loading' | 'cancelled' }
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
  return (
    <Page
      title="Pause. Check. Choose."
      subtitle="Look up a website, then decide what works for you."
    >
      <Card>
        <View style={styles.row}>
          <View style={styles.iconTile}>
            <Globe2 size={24} color={colors.primary} accessible={false} />
          </View>
          <View style={styles.flex}>
            <Text style={styles.heading}>Check a link</Text>
            <Text style={styles.small}>A little context before you visit.</Text>
          </View>
        </View>
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
          Only the hostname is sent for classification. Page paths, passwords,
          and query tokens are not sent or stored.
        </Text>
      </Card>
      {__DEV__ && <BackendStatus />}
      {!result && (
        <Card>
          <Badge text="YOU STAY IN CONTROL" />
          <Text style={styles.heading}>Context, then a choice.</Text>
          <Text style={styles.body}>
            Reviewed catalog labels take priority. For other eligible hostnames,
            a validated model can help when available. Insufficient information
            stays unknown.
          </Text>
          <View style={styles.divider} />
          <View style={styles.row}>
            <ShieldCheck size={20} color={colors.accent} accessible={false} />
            <Text style={[styles.small, styles.flex]}>
              Your manual rules stay on this phone and work without the catalog
              connection.
            </Text>
          </View>
        </Card>
      )}
      {result && (
        <>
          <Card>
            <Text style={styles.eyebrow}>WEBSITE CLASSIFICATION</Text>
            <Text selectable style={styles.heading}>
              {result.domain}
            </Text>
            <View accessibilityLiveRegion="polite">
              {remote.status === 'loading' && (
                <View style={styles.row}>
                  <ActivityIndicator color={colors.primary} />
                  <Text style={styles.body}>Checking the website…</Text>
                </View>
              )}
              {remote.status === 'error' && <Notice text={remote.message} />}
              {remote.status === 'cancelled' && (
                <Text style={styles.body}>
                  Website check cancelled. No new classification was returned.
                </Text>
              )}
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
                    tone={
                      catalog.classification === 'gambling'
                        ? 'error'
                        : catalog.classification === 'non_gambling'
                        ? 'primary'
                        : 'warning'
                    }
                  />
                  <Text style={styles.small}>
                    {catalog.source === 'reviewed_catalog'
                      ? 'Source: reviewed catalog'
                      : catalog.source === 'model'
                      ? `Source: model · ${catalog.model_version}`
                      : 'Source: no classification available'}
                  </Text>
                  <Text style={styles.body}>
                    {catalog.classification === 'non_gambling'
                      ? 'Classified as non-gambling. '
                      : ''}
                    {catalog.explanation}
                  </Text>
                  {catalog.reviewed_at && (
                    <Text style={styles.small}>
                      Reviewed{' '}
                      {new Date(catalog.reviewed_at).toLocaleDateString()} ·
                      Provenance: {catalog.label_provenance}
                    </Text>
                  )}
                </View>
              )}
              {detection && (
                <View style={styles.stack}>
                  <Badge text={`DETECTION: ${detection.intervention === 'NONE' ? 'ALLOW' : detection.intervention}`}
                    tone={detection.enforcement_action === 'BLOCK' ? 'error' : detection.intervention === 'WARN' ? 'warning' : 'primary'} />
                  {detection.intervention === 'WARN' ? (
                    <Notice text="BetGuard detected characteristics associated with gambling websites. This is uncertain; network access remains allowed." />
                  ) : (
                    <Text style={styles.body}>
                      {detection.enforcement_action === 'BLOCK'
                        ? 'BetGuard recommends blocking this domain. Online detection applies this decision while protection runs, unless a local rule overrides it.'
                        : 'No detection intervention is needed.'}
                    </Text>
                  )}
                  <Text style={styles.small}>Source: {detection.decision_source}. Local rules take priority.</Text>
                </View>
              )}
              {detectionError && remote.status !== 'cancelled' && (
                <Notice text="Domain detection is unavailable. No detection decision was returned; local manual rules still work." />
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
            {(remote.status === 'error' || remote.status === 'cancelled') && (
              <Button
                title="Retry website check"
                icon={RotateCcw}
                secondary
                onPress={() => {
                  void retry();
                }}
              />
            )}
          </Card>
          <Card>
            <Text style={styles.eyebrow}>YOUR LOCAL RULE</Text>
            <Badge
              text={`EFFECTIVE RULE: ${result.action.toUpperCase()}`}
              tone={result.action === 'block' ? 'error' : 'primary'}
            />
            <Text style={styles.body}>
              {result.reason.replace(' Classification remains unknown.', '')}
            </Text>
            <Text style={styles.small}>
              Classification results do not change your rules. New overrides
              match this exact hostname. Existing subdomain scope is preserved;
              change scope in Sites.
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
                  title="Allow site"
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
                  void removeOverride();
                }}
              />
            )}
            <Text style={styles.small}>
              Rules filter supported requests while protection is running.
              Checked {new Date(result.checkedAt).toLocaleString()}.
            </Text>
          </Card>
        </>
      )}
    </Page>
  );
}
