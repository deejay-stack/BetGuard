import React from 'react';
import { StatusBar, StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import {
  DarkTheme,
  DefaultTheme,
  NavigationContainer,
} from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { House, ListFilter, History, Settings } from 'lucide-react-native';
import { BetGuardProvider } from './src/state/BetGuardContext';
import { HomeScreen } from './src/screens/HomeScreen';
import { CheckScreen } from './src/screens/CheckScreen';
import { SitesScreen } from './src/screens/SitesScreen';
import { HistoryScreen } from './src/screens/HistoryScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';
import { ThemeProvider, useTheme } from './src/state/ThemeContext';
import { ErrorBoundary } from './src/components/ErrorBoundary';

export type Tabs = {
  Home: undefined;
  Check: undefined;
  Sites: undefined;
  History: undefined;
  Settings: undefined;
};
const Tab = createBottomTabNavigator<Tabs>();
const icons = {
  Home: House,
  Check: House,
  Sites: ListFilter,
  History,
  Settings,
};
function ThemedApp() {
  const { colors, mode, reducedMotion } = useTheme();
  const base = mode === 'dark' ? DarkTheme : DefaultTheme;
  const theme = {
    ...base,
    colors: {
      ...base.colors,
      primary: colors.primary,
      background: colors.background,
      card: colors.surface,
      text: colors.text,
      border: colors.border,
      notification: colors.error,
    },
  };
  return (
    <SafeAreaProvider>
      <StatusBar
        barStyle={mode === 'dark' ? 'light-content' : 'dark-content'}
      />
      <BetGuardProvider>
        <NavigationContainer theme={theme}>
          <Tab.Navigator
            backBehavior="history"
            screenOptions={({ route }) => ({
              headerShown: false,
              animation: reducedMotion ? 'none' : 'fade',
              transitionSpec: {
                animation: 'timing',
                config: { duration: reducedMotion ? 0 : 140 },
              },
              sceneStyle: { backgroundColor: colors.background },
              tabBarHideOnKeyboard: true,
              tabBarActiveTintColor: colors.primary,
              tabBarInactiveTintColor: colors.textMuted,
              tabBarItemStyle: {
                borderRadius: 16,
                marginHorizontal: 3,
              },
              tabBarStyle: {
                backgroundColor: colors.surface,
                borderTopColor: colors.border,
                paddingTop: 8,
              },
              tabBarLabelStyle: {
                fontSize: 11,
                fontWeight: '600',
                paddingBottom: 3,
              },
              tabBarIcon: ({ color, size, focused }) => {
                const Icon = icons[route.name];
                return (
                  <View
                    style={[
                      navigationStyles.icon,
                      {
                        backgroundColor: focused
                          ? colors.primarySoft
                          : colors.surface,
                      },
                    ]}
                  >
                    <Icon color={color} size={size} strokeWidth={1.8} />
                  </View>
                );
              },
            })}
          >
            <Tab.Screen name="Home" component={HomeScreen} />
            <Tab.Screen
              name="History"
              component={HistoryScreen}
              options={{ title: 'Activity' }}
            />
            <Tab.Screen
              name="Check"
              component={CheckScreen}
              options={{
                title: 'Check link',
                tabBarButton: () => null,
                tabBarItemStyle: { display: 'none' },
              }}
            />
            <Tab.Screen
              name="Sites"
              component={SitesScreen}
              options={{ title: 'Protection' }}
            />
            <Tab.Screen name="Settings" component={SettingsScreen} />
          </Tab.Navigator>
        </NavigationContainer>
      </BetGuardProvider>
    </SafeAreaProvider>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <ThemedApp />
      </ThemeProvider>
    </ErrorBoundary>
  );
}
const navigationStyles = StyleSheet.create({
  icon: {
    width: 52,
    height: 34,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
