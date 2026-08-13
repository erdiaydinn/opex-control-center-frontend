self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/workforce/app";
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const existing = windows.find((client) => "focus" in client);
    if (existing) {
      if ("navigate" in existing) await existing.navigate(url);
      return existing.focus();
    }
    return self.clients.openWindow?.(url);
  })());
});
