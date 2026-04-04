import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import BookVisitorScreen from './src/screens/BookVisitorScreen';
import BookingSuccessScreen from './src/screens/BookingSuccessScreen';

const Stack = createNativeStackNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <StatusBar style="light" />
      <Stack.Navigator
        initialRouteName="BookVisitor"
        screenOptions={{ headerShown: false }}
      >
        <Stack.Screen name="BookVisitor" component={BookVisitorScreen} />
        <Stack.Screen name="BookingSuccess" component={BookingSuccessScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
