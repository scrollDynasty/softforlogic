# Troubleshooting Guide

## Fixed Issues

### 1. Service Worker Registration Failed (Status code: 15)
**Problem**: The extension failed to register the service worker properly.

**Solutions applied**:
- Added `contextMenus` permission to manifest.json
- Added proper error handling for chrome.contextMenus API
- Removed `type: "module"` from background service worker configuration
- Added checks for API availability before using it

### 2. Background.js Error on Line 330
**Problem**: Error when trying to add context menu listener without checking if API is available.

**Solutions applied**:
- Wrapped contextMenus.onClicked listener in a conditional check
- Added try-catch blocks for better error handling
- Added callback function to handle context menu creation errors

### 3. Missing Sound File
**Problem**: Extension expected alert.mp3 file that didn't exist.

**Solutions applied**:
- Created sounds directory
- Added placeholder alert.mp3 file
- Created README in sounds directory with instructions

## How to Install the Fixed Extension

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" in the top right corner
3. Click "Load unpacked"
4. Select the extension directory (containing manifest.json)
5. The extension should load without errors

## Additional Notes

- The alert.mp3 file is currently empty. You should replace it with an actual sound file (1-3 seconds, under 1MB)
- If you don't want sound alerts, disable them in the extension options
- Make sure you're on https://freightpower.schneider.com/* for the extension to work
- The extension will only activate after successful login to FreightPower

## Common Issues and Solutions

1. **Extension doesn't activate**
   - Make sure you're logged into FreightPower
   - Check that the URL matches the pattern in manifest.json
   - Look for errors in chrome://extensions/

2. **No notifications**
   - Check Chrome notification settings
   - Make sure notifications are enabled in extension options
   - Check that profitable loads match your criteria

3. **Context menu not showing**
   - Right-click on a FreightPower page
   - Look for "Toggle FreightPower Monitoring" option
   - If not visible, reload the extension