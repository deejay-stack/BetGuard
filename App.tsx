import React from 'react';
import { StatusBar } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { DefaultTheme, NavigationContainer } from '@react-navigation/native';
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
import { colors } from './src/theme';

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
const theme = {
  ...DefaultTheme,
  colors: {
    ...DefaultTheme.colors,
    primary: colors.blue,
    background: colors.background,
    card: colors.white,
    text: colors.ink,
    border: colors.border,
  },
};

export default function App() {
  return (
    <SafeAreaProvider>
      <StatusBar barStyle="dark-content" />
      <BetGuardProvider>
        <NavigationContainer theme={theme}>
          <Tab.Navigator
            screenOptions={({ route }) => ({
              headerShown: false,
              tabBarActiveTintColor: colors.blue,
              tabBarInactiveTintColor: colors.muted,
              tabBarStyle: { borderTopColor: colors.border, paddingTop: 8 },
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
