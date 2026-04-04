# Visit Booker - React Native App

A React Native (Expo) app for booking visitors, generating access tokens with QR codes, and sharing them via WhatsApp, SMS, or other channels.

## Features
- Contact picker (phone book access)
- Random visitor token generation
- QR code generation for tokens
- WhatsApp sharing with token details and QR code
- SMS and general sharing options
- Configurable code validity (1-6 hours)
- Date and time picker for visit scheduling

## Prerequisites
- Node.js >= 18
- npm or yarn
- Expo CLI: `npm install -g expo-cli`
- EAS CLI: `npm install -g eas-cli`
- Expo account (free): https://expo.dev/signup

## Quick Start (Development)
```bash
cd visit-booker-app
npm install
npx expo start
```
Scan the QR code with the Expo Go app on your phone.

## Build APK (for direct install on Android)

### Option 1: EAS Build (Recommended - Cloud Build)
```bash
# Install EAS CLI globally
npm install -g eas-cli

# Login to your Expo account
eas login

# Build APK (cloud build, no local Android SDK needed)
eas build -p android --profile preview

# The APK download link will be provided when the build completes
```

### Option 2: Local Build
```bash
# Requires Android SDK, Java 17+, and NDK installed locally
npx expo prebuild --platform android
cd android
./gradlew assembleRelease
# APK will be at: android/app/build/outputs/apk/release/app-release.apk
```

## Project Structure
```
visit-booker-app/
  App.js                    # Navigation setup
  app.json                  # Expo configuration
  eas.json                  # EAS Build configuration
  src/
    screens/
      BookVisitorScreen.js  # Main booking form
      BookingSuccessScreen.js # Success + token + sharing
    utils/
      codeGenerator.js      # Random token generation
      colors.js             # Theme colors
```

## Permissions
- **READ_CONTACTS** - To pick visitors from your phone book
- **INTERNET** - For WhatsApp deep linking
