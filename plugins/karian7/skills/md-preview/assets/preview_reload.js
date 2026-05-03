(() => {
  const endpoint = window.__MD_PREVIEW_VERSION_URL || "/__md_preview/version";
  let currentVersion = null;
  let inflight = false;

  const readVersion = async () => {
    if (inflight) {
      return;
    }
    inflight = true;
    try {
      const response = await fetch(endpoint, {
        cache: "no-store",
        headers: {
          "Cache-Control": "no-store",
        },
      });
      if (!response.ok) {
        return;
      }
      const nextVersion = (await response.text()).trim();
      if (!nextVersion) {
        return;
      }
      if (currentVersion === null) {
        currentVersion = nextVersion;
        return;
      }
      if (nextVersion !== currentVersion) {
        window.location.reload();
        return;
      }
      currentVersion = nextVersion;
    } catch (_error) {
      // Ignore transient polling failures and try again on the next interval.
    } finally {
      inflight = false;
    }
  };

  const sendUnload = () => {
    const unloadUrl = endpoint.replace(/\/version$/, "/unload");
    navigator.sendBeacon(unloadUrl);
  };

  readVersion();
  setInterval(readVersion, 750);
  window.addEventListener("focus", readVersion);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      // Tab hidden or closed — notify server so watchdog can start its countdown
      sendUnload();
    } else {
      // Tab visible again — resume polling immediately
      readVersion();
    }
  });
  // pagehide fires reliably on tab close, navigation, and page unload
  window.addEventListener("pagehide", sendUnload);
})();
