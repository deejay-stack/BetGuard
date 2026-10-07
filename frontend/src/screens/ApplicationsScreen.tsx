import React, { useEffect, useRef, useState } from 'react';
import { BackHandler, Platform, Text, TextInput, View } from 'react-native';
import type { BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import { useIsFocused } from '@react-navigation/native';
import type { Tabs } from '../../App';
import Native from '../../specs/NativeBetGuard';
import { Badge, Button, Card, Empty, Notice, Page } from '../components/ui';
import { BottomSheet } from '../components/BottomSheet';
import { RuleEditor } from '../components/RuleEditor';
import { useTheme } from '../state/ThemeContext';
import { API_BASE_URL } from '../api/config';
import { ApiError } from '../api/client';
import {
  checkApplication,
  visibleApplications,
  type AppCheck,
  type VisibleApplication,
} from '../api/applications';

export function ApplicationsScreen({
  navigation,
}: {
  navigation?: BottomTabNavigationProp<Tabs, 'Apps'>;
}) {
  const { styles, colors, mode } = useTheme();
  const focused = useIsFocused();
  const [applications, setApplications] = useState<VisibleApplication[]>([]);
  const [inventory, setInventory] = useState(false);
  const [query, setQuery] = useState('');
  const [name, setName] = useState('');
  const [selected, setSelected] = useState<VisibleApplication | null>(null);
  const [description, setDescription] = useState('');
  const [keywords, setKeywords] = useState('');
  const [reviews, setReviews] = useState('');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AppCheck | null>(null);
  const [error, setError] = useState('');
  const [rules, setRules] = useState(false);
  const [permissionsOpen, setPermissionsOpen] = useState(false);
  const request = useRef<AbortController | null>(null);
  const revision = useRef(0);
  const mounted = useRef(true);
  const localInventoryAvailable =
    Platform.OS === 'android' &&
    typeof Native?.getVisibleApplications === 'function';

  function invalidate() {
    revision.current += 1;
    request.current?.abort();
    request.current = null;
    setBusy(false);
    setResult(null);
    setError('');
    setConsent(false);
  }
  function clear() {
    invalidate();
    setApplications([]);
    setSelected(null);
    setName('');
    setDescription('');
    setKeywords('');
    setReviews('');
    setQuery('');
    setInventory(false);
    setRules(false);
    setPermissionsOpen(false);
  }
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      revision.current += 1;
      request.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (!focused) {
      clear();
      return;
    }
    const subscription = BackHandler.addEventListener(
      'hardwareBackPress',
      () => {
        navigation?.navigate('Sites');
        return !!navigation;
      },
    );
    return () => subscription.remove();
    // Clear session metadata on navigation; never persist an app inventory.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focused, navigation]);

  async function listApplications() {
    if (!Native || !localInventoryAvailable) return;
    invalidate();
    const token = revision.current;
    setBusy(true);
    setInventory(false);
    try {
      const rows = visibleApplications(await Native.getVisibleApplications());
      if (mounted.current && token === revision.current) setApplications(rows);
    } catch {
      if (mounted.current && token === revision.current)
        setError(
          'The app list could not be read. You can enter public app information below.',
        );
    } finally {
      if (mounted.current && token === revision.current) setBusy(false);
    }
  }
  async function analyze() {
    if (busy || !name.trim() || !API_BASE_URL || !consent) return;
    const controller = new AbortController();
    request.current?.abort();
    request.current = controller;
    const token = ++revision.current;
    setBusy(true);
    setResult(null);
    setError('');
    try {
      const checked = await checkApplication(
        {
          app_name: name.trim(),
          package_name: selected?.package_name ?? '',
          description: description.trim(),
          keywords: keywords
            .split(',')
            .map(value => value.trim())
            .filter(Boolean),
          permissions: selected?.permissions ?? [],
          reviews: reviews
            .split('\n')
            .map(value => value.trim())
            .filter(Boolean),
        },
        controller.signal,
      );
      if (mounted.current && token === revision.current) setResult(checked);
    } catch (failure) {
      if (
        mounted.current &&
        token === revision.current &&
        !(failure instanceof ApiError && failure.code === 'cancelled')
      ) {
        setError(
          failure instanceof ApiError && failure.code === 'invalid'
            ? 'Use up to 40 keywords and 10 public reviews, with at most 1,000 characters per review.'
            : 'The app review service could not be reached. This app has not been evaluated. Try again when the server is available.',
        );
      }
    } finally {
      if (mounted.current && token === revision.current) setBusy(false);
    }
  }
  function select(application: VisibleApplication) {
    invalidate();
    setSelected(application);
    setName(application.app_name);
    setDescription('');
    setKeywords('');
    setReviews('');
    setApplications([]);
    setQuery('');
    setPermissionsOpen(false);
  }
  const displayed = applications.filter(application =>
    `${application.app_name} ${application.package_name}`
      .toLowerCase()
      .includes(query.trim().toLowerCase()),
  );
  return (
    <Page
      title="Review an app"
      subtitle="Understand an app and protect its website connections."
    >
      <Button
        title="Back to protection"
        secondary
        onPress={() => navigation?.navigate('Sites')}
        disabled={!navigation}
      />
      <Card>
        <Text style={styles.heading}>Student network protection</Text>
        <Text style={styles.body}>
          Smart protection automatically checks supported domain requests from
          browsers and apps. App review separately analyzes public app
          information; it does not stop an app from opening.
        </Text>
        <Button
          title="Choose an installed app"
          secondary
          disabled={!localInventoryAvailable || busy}
          onPress={() => setInventory(true)}
        />
        {!localInventoryAvailable && (
          <Text style={styles.small}>
            Install the updated Android build to choose an app, or enter its
            name below.
          </Text>
        )}
      </Card>
      <BottomSheet
        visible={inventory}
        title="Read app information on this phone?"
        onClose={() => setInventory(false)}
      >
        <Text style={styles.body}>
          BetGuard reads the names, package IDs and requested permission names
          of visible launchable apps. This list stays in this screen and is
          cleared when you leave.
        </Text>
        <Text style={styles.small}>
          No private messages, contacts, files, passwords or usage history are
          read. Listing apps does not upload the inventory. Android may hide
          some apps.
        </Text>
        <Button
          title="Continue with local app list"
          onPress={() => {
            void listApplications();
          }}
        />
        <Button
          title="Cancel app list"
          secondary
          onPress={() => setInventory(false)}
        />
      </BottomSheet>
      {applications.length > 0 && (
        <Card>
          <TextInput
            accessibilityLabel="Search installed apps"
            placeholder="Search installed apps"
            value={query}
            onChangeText={setQuery}
            style={styles.input}
            placeholderTextColor={colors.textMuted}
            keyboardAppearance={mode}
            autoCorrect={false}
          />
          <Text style={styles.small}>
            {applications.length} visible apps · Showing up to 30 matches
          </Text>
          {displayed.slice(0, 30).map(application => (
            <Button
              key={application.package_name}
              title={application.app_name}
              accessibilityLabel={`Review ${application.app_name} (${application.package_name})`}
              secondary
              onPress={() => select(application)}
            />
          ))}
          {displayed.length === 0 && (
            <Empty
              title="No matching apps"
              body="Try another name, or enter the app information below."
            />
          )}
        </Card>
      )}
      <Card>
        <Text style={styles.heading}>Public app information</Text>
        <TextInput
          accessibilityLabel="App name"
          placeholder="App name"
          value={name}
          maxLength={200}
          autoCorrect={false}
          onChangeText={value => {
            invalidate();
            setSelected(null);
            setName(value);
          }}
          style={styles.input}
          placeholderTextColor={colors.textMuted}
          keyboardAppearance={mode}
        />
        {selected && (
          <View style={styles.stack}>
            <Text style={styles.small}>{selected.package_name}</Text>
            <Text style={styles.small}>
              {selected.permissions.length} requested permission names. These
              are declarations, not proof of access or gambling.
            </Text>
            {selected.permissions.length > 0 && (
              <Button
                title={
                  permissionsOpen
                    ? 'Hide permission names'
                    : 'Show permission names'
                }
                secondary
                onPress={() => setPermissionsOpen(!permissionsOpen)}
              />
            )}
            {permissionsOpen && (
              <Text style={styles.small}>
                {selected.permissions.join('\n')}
              </Text>
            )}
          </View>
        )}
        <Text style={styles.small}>
          Android does not provide app-store descriptions or reviews. Paste
          public text below; omit personal information. A name alone is
          insufficient.
        </Text>
        <TextInput
          accessibilityLabel="Public app description"
          placeholder="Paste the public app-store description"
          value={description}
          onChangeText={value => {
            invalidate();
            setDescription(value);
          }}
          multiline
          maxLength={6000}
          style={styles.input}
          placeholderTextColor={colors.textMuted}
          keyboardAppearance={mode}
        />
        <TextInput
          accessibilityLabel="App keywords"
          placeholder="Keywords, separated by commas"
          value={keywords}
          maxLength={2000}
          onChangeText={value => {
            invalidate();
            setKeywords(value);
          }}
          style={styles.input}
          placeholderTextColor={colors.textMuted}
          keyboardAppearance={mode}
        />
        <TextInput
          accessibilityLabel="Public app reviews"
          placeholder="Public reviews (optional, one per line)"
          value={reviews}
          multiline
          maxLength={10000}
          onChangeText={value => {
            invalidate();
            setReviews(value);
          }}
          style={styles.input}
          placeholderTextColor={colors.textMuted}
          keyboardAppearance={mode}
        />
        <Text style={styles.small}>
          Online review sends only the app information shown here to your
          configured BetGuard server. The server does not save it. This is
          separate from website detection.
        </Text>
        <Button
          title={
            consent
              ? 'Selected: send this app information'
              : 'I agree to send this app information'
          }
          secondary
          selected={consent}
          disabled={busy || !API_BASE_URL}
          onPress={() => setConsent(!consent)}
        />
        {!API_BASE_URL && (
          <Notice text="Online app review needs a configured BetGuard server. Your saved network rules still work on this phone." />
        )}
        <Button
          title="Review app information"
          busy={busy}
          disabled={!consent || !name.trim() || !API_BASE_URL}
          onPress={() => {
            void analyze();
          }}
        />
        {busy && (
          <Button title="Cancel review" secondary onPress={invalidate} />
        )}
      </Card>
      {error && <Notice text={error} tone="error" />}
      {result && (
        <Card>
          <Badge
            text={
              result.classification === 'gambling'
                ? 'GAMBLING INDICATORS'
                : result.classification === 'non_gambling'
                ? 'CLASSIFIED NON-GAMBLING'
                : 'NOT EVALUATED'
            }
            tone={
              result.classification === 'gambling'
                ? 'error'
                : result.classification === 'non_gambling'
                ? 'success'
                : 'warning'
            }
          />
          <Text style={styles.body}>{result.explanation}</Text>
          {result.model_version && (
            <Text style={styles.small}>App model: {result.model_version}</Text>
          )}
          <Text style={styles.small}>
            A review does not create rules or activate protection. Confirm an
            app's website before blocking; shared domains can affect other apps.
          </Text>
        </Card>
      )}
      <Card>
        <Text style={styles.heading}>Restrict a known gambling website</Text>
        <Text style={styles.body}>
          If you know the app's gambling hostname, add a Block rule, then enable
          protection on Home. Rules affect supported DNS requests in any app.
          BetGuard does not infer a hostname from a package ID.
        </Text>
        <Button
          title="Add an app website rule"
          secondary
          onPress={() => setRules(true)}
        />
        <Button
          title="Enable network protection"
          secondary
          onPress={() => navigation?.navigate('Home')}
          disabled={!navigation}
        />
      </Card>
      <BottomSheet
        visible={rules}
        title="Block or allow an app website"
        onClose={() => setRules(false)}
      >
        <RuleEditor onSaved={() => setRules(false)} />
      </BottomSheet>
      <Button title="Clear app review information" secondary onPress={clear} />
    </Page>
  );
}
