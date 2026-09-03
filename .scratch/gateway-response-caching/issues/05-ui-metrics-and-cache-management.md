# 05: UI Metrics, Settings Management and Visual Badges

**What to build:**
Expose cache performance and controls in the frontend dashboard: render an accumulated cost savings metric and hit rate, add a cache control panel in Settings (toggle, TTL input, and flush button), and display a distinctive `⚡ Cache HIT` badge on cached entries in the Request Log table.

**Blocked by:** 02: Gateway JSON Cache Interception, Bypass Headers and Telemetry; 04: Cache Management REST API (Stats, Flush, Configuration)

**Status:** ready-for-agent

- [ ] Add cache API methods in `frontend/js/api.js` (`getCacheStats`, `flushCache`, `updateCacheConfig`).
- [ ] Render savings metric ("Economia com Cache") and Cache Hit % in dashboard stat cards.
- [ ] Add Cache Management card in Settings tab (`index.html`, `app.js`) with Flush Cache button and TTL selector.
- [ ] Render `⚡ Cache HIT` badge on corresponding rows in the Request Log table (`metrics.js`).
- [ ] Handle toast notifications for successful cache flushes and config changes.
