# Uhome (U-Tec) Home Assistant Integration

A Home Assistant integration for U-Tec smart home devices via the Uhome API that allows you to control your locks, lights, switches, and sensors through Home Assistant.

## Device Types
- Supports multiple U-tec device types:
    - Locks
    - Lights
    - Switches
    - Smart Plugs (Wifi)
 
### Features
- Secure API communication
- Locking and unlocking
- Lock states
- Door states
- Battery levels
- Switch on and off (Lightbulbs use the switch capabilitiy for some reason, so at very least they should have rudimentary functionality)
- SwitchLevel (Honestly, idk what this is actually for, but hopefully we can use it to control light brightness until they properly implement light controls)

## Limitations
- Currently the Utec API doesn't support the following devices:
	- Wifi bridge modules
	- Air Portal registration / devices

## Requirements
- API Credentials
- External Access Configured (ie., Nabu Casa)

## Ensure Home Assistant knows its own URL
For the Configuration step below to work, Home Assistant must know its own URL.

Navigate to Settings > System > Network and set the Home Assistant URL (Normally `http://homeassistant.local:8123`)

## Getting Your Credentials
#### Having your credentials is necessary to configure the integration, so get them before you install it.

API credentials are now available directly in the Xthings Home app (formerly U-Home) version 3.5.5 or later. No need to submit a request through the developer portal.

1. Open the Xthings Home app and go to **My Account**
2. Tap **OpenAPI**
3. Follow the prompts to activate OpenAPI — select your role and the products you are integrating with, then tap **Activate Openapi**

![Steps to enable OpenAPI in the app](images/api_enable_steps.png)

Once activated, you will see your `Client ID`, `Client Secret`, `Scope`, and `RedirectUri`.
- Set `RedirectUri` to `https://my.home-assistant.io/redirect/oauth` exactly as written — do not replace the hostname with your own Home Assistant URL
- Confirm `Scope` is set to `OpenAPI`
- Tap **Save**

![API credentials screen](images/api_credentials.png)

For the integration you will need `Client ID` and `Client Secret`.

For more information, see the [Developer API Documentation](https://doc.api.u-tec.com/#intro). If you run into issues with the API, you can [submit a support request](https://developer.xthings.com/hc/en-us/requests/new).

*See [issue #36](https://github.com/LF2b2w/Uhome-HA/issues/36) for more details. Screenshots courtesy of @geofox784.*

## Installation
### HACS (Recommended)
Open HACS in your Home Assistant instance\
Click add custom repo\
Paste the URL of this repo and choose type integration\
Search for "U-tec"\
Click "Install"

### Manual Installation
Download the repository\
Copy the custom_components/Homeassistant-utec folder to your Home Assistant's custom_components directory\
Restart Home Assistant

## Configuration
In Home Assistant, go to Settings > Devices & services > Integrations\
Click the "+ Add integration" button\
Search for "U-Tec"\
You will need to provide the credentials information from above:
- Client ID
- Client Secret

When you submit, you will be taken to the U-Tec [OAuth site](https://oauth.u-tec.com/login/auth) where you need to login with your U-Tec username and password.  That will then ask you to authorize the OAuth connection.  After that it will take you back to Home Assistant and ask you to link your account to Home Assistant.

If the credentials are ever rotated by U-Tec or you regenerate them in the Xthings app, you can update them in place via the integration's **Reconfigure** action (3-dot menu on the integration card) — no need to remove and re-add the integration.

## Configure options (UI)

After the integration is set up, open **Settings → Devices & services → U-Tec → Configure** to adjust runtime behaviour. None of these options require a full Home Assistant restart; they are saved to the config entry and applied as described below.

### Update Push Status

Enable or disable **push** state updates from U-Tec, and optionally choose which devices receive them.

- When push is **enabled**, the integration registers a webhook with U-Tec (preferring a Nabu Casa cloudhook when Home Assistant Cloud is active, otherwise an external URL) and applies lock/light/switch state as soon as the cloud sends it.
- When push is **disabled**, the webhook is unregistered; entities continue to update via polling only.
- You can limit push to a subset of devices; if none are selected, all known devices are eligible.

**Applied:** immediately on save (webhook registered or unregistered without reloading the integration).

### Select Active Devices

Choose which discovered U-Tec devices should be active in Home Assistant.

**Applied:** on save to the integration options. If a device does not appear or disappear as expected, reload the integration entry (or restart Home Assistant) so platforms re-run setup against the updated list.

### Configure Optimistic Updates

Control whether lock, light, and switch entities update their state in the UI as soon as you send a command, before the device (or a push/poll) confirms it.

- **All** — optimistic state for every device of that type.
- **None** — wait for confirmed state from the API or push.
- **Custom** — pick specific devices that should be optimistic.

Optimistic state is time-bounded so a command that never completes does not pin the entity forever.

**Caution (locks):** Be careful enabling optimistic updates for **locks**. The UI can show locked or unlocked before the physical lock has actually changed state. That false positive can be a **security concern** (for example assuming a door is locked when it is not, or the reverse). Whether that risk is acceptable depends on your setup, automations, and how you use the lock — every case is different. Prefer confirmed state for locks if you are unsure.

**Applied:** immediately on save; the next command uses the new setting.

### Polling Interval

How often Home Assistant polls the U-Tec API for device state (10–3600 seconds).

- Default is **10 seconds**, which suits installs that rely mainly on polling.
- With working push (especially cloudhooks), a longer interval (for example 300–600 seconds) reduces API traffic while push keeps state fresh.
- If you still have `scan_interval` under `u_tec:` in `configuration.yaml`, that value is used until you save a UI interval. YAML `scan_interval` is deprecated in favour of this option.

**Note:** U-Tec push notifications have been observed to **stop for extended periods** (multiple days) even when the webhook remains registered. Until the vendor addresses that reliability issue, it is reasonable to keep a **moderate polling interval** rather than relying on push alone, so entity state still refreshes during outages.

**Applied:** immediately on save (the coordinator reschedules its next poll; no reload required).

### Availability Threshold

How many **consecutive failed API polls** are required before entities are marked unavailable (1–5).

- **1** (default) — fail fast: the first failed poll marks entities unavailable (classic Home Assistant coordinator behaviour).
- **2–5** — tolerate short network or API blips; entities stay available until the threshold is reached. A successful poll resets the counter. Devices that report offline are still unavailable regardless of this setting.

Failed polls log a **warning** each time. When the threshold is reached, an **error** is logged stating that entities will report unavailable until a successful poll.

**Applied:** immediately on save; the next poll uses the new threshold.

## Troubleshooting
See [FAQ](https://github.com/LF2b2w/Uhome-HA/discussions/2)
    
## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.

#### License
This project is licensed under the MIT [License](./LICENSE).

Support
If you encounter any issues or have questions: Check the [Issues](https://github.com/LF2b2w/Uhome-HA/issues) page
Create a new issue if your problem isn't already reported

[Join](https://github.com/LF2b2w/Uhome-HA/discussions) the discussion in the Home Assistant community forums
---
Made with ❤️ by @LF2b2w
