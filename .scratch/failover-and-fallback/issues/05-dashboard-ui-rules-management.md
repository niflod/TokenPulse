# 05: Dashboard UI Rules Management and Visual Highlights

**What to build:** An intuitive user interface inside the TokenPulse Dashboard for viewing, adding, toggling, and deleting fallback rules in Settings, and rendering visual `[Fallback]` badges on rerouted calls in the Request Log view.

**Blocked by:** 01: Fallback Rules Model and CRUD, 04: Telemetry, Response Headers, and Audit Tracking.

**Status:** ready-for-agent

- [ ] Add Fallback Rules management card in `frontend/index.html` within the Settings section.
- [ ] Implement API methods in `frontend/js/api.js` for `/api/fallback-rules` (get, create, delete, toggle).
- [ ] Render rules list, creation modal/form, toggle switch, and delete button in `frontend/js/app.js`.
- [ ] Add visual badge `[Fallback]` and tooltip in the Request Log table when `log.fallback_triggered` is true.
- [ ] Manual and automated verification of UI interactions.
