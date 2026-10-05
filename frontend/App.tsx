import React from 'react';
import { StatusBar } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import {
  DarkTheme,
  DefaultTheme,
  NavigationContainer,
} from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import {
  House,
  Link,
  ListFilter,
  History,
  Settings,
} from 'lucide-react-native';
import { BetGuardProvider } from './src/state/BetGuardContext';
import { HomeScreen } from './src/screens/HomeScreen';
import { CheckScreen } from './src/screens/CheckScreen';
import { SitesScreen } from './src/screens/SitesScreen';
import { HistoryScreen } from './src/screens/HistoryScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';
import { ThemeProvider, useTheme } from './src/state/ThemeContext';

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
  Check: Link,
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
              tabBarActiveBackgroundColor: colors.primarySoft,
              tabBarItemStyle: { borderRadius: 16, marginHorizontal: 3 },
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
              tabBarIcon: ({ color, size }) => {
                const Icon = icons[route.name];
                return <Icon color={color} size={size} strokeWidth={1.8} />;
              },
            })}
          >
            <Tab.Screen name="Home" component={HomeScreen} />
            <Tab.Screen
              name="Check"
              component={CheckScreen}
              options={{ title: 'Check link' }}
            />
            <Tab.Screen name="Sites" component={SitesScreen} />
            <Tab.Screen name="History" component={HistoryScreen} />
            <Tab.Screen name="Settings" component={SettingsScreen} />
          </Tab.Navigator>
        </NavigationContainer>
      </BetGuardProvider>
    </SafeAreaProvider>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <ThemedApp />
    </ThemeProvider>
  );
}
