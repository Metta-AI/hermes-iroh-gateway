(function () {
  "use strict";
  // Hidden placeholder tab (tab.hidden: true in manifest.json). This plugin's
  // real UI is the native desktop pane in desktop/plugin.js, which talks to
  // this same directory's plugin_api.py backend. This file only exists
  // because the dashboard plugin loader requires an `entry` bundle; it
  // registers a no-op so a direct URL visit to /hermes-iroh-gateway doesn't
  // 404 inside the dashboard shell.
  window.__HERMES_PLUGINS__.register("hermes-iroh-gateway", function () {
    return null;
  });
})();
