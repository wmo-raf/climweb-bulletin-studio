# Changelog

## 0.1.0a2 — 2026-10-12

Second alpha: issues prepared from their template, forecast maps and city forecasts.
Needs ClimWeb 1.1.7 or later; the forecast features need forecastmanager
(`IS_METEOROLOGICAL`). Frontend: bulletin-studio-js `2583ba7`.

- A template has a cadence (daily, dekadal, monthly). "New bulletin" makes the issue of
  a period on the server: the template's document, the period's dates ("Effective
  from", "Effective until") and a title in the admin's language.
- Drafts: at the time set on a template, the issue of the current period is prepared
  on its first day, once per period (Celery beat task `bulletin-studio-daily-drafts`,
  every 15 minutes). A human always publishes, and Wagtail refuses to publish an issue
  the studio has not rendered yet.
- Dates inserted in the banner and in image captions, filled for each issue: `{start}`,
  `{end}`, `{period}`, `{previous}` (the period before), `{published}`, `{number}`
  (the period's rank in its year).
- Forecast map: a country map of the city forecasts, drawn on the server after each
  forecast pull, for the periods set in Settings > Forecast map. The forecast block
  freezes the map of its day in the issue, through the image library.
- City forecasts block: icon, maximum and minimum, wind for each city, frozen in the
  issue.
- Starting points: daily weather, and a dekadal agrometeorological bulletin following
  the review of 17 countries' bulletins.
- PDF: the organisation's letterhead (Settings > Organisation) above the bulletin.
- Public page: ClimWeb's share buttons under the bulletin.
- Bulletins are made in the studio only: Wagtail's "Add child page" no longer offers
  "Bulletin", which opened the plain product item form.

## 0.1.0a1 — 2026-10-02

First alpha, to try the studio on a real ClimWeb instance. Needs ClimWeb 1.1.7 or later.

- Bulletin Studio entry in the Wagtail admin, hosting the JS editor
  (frontend: bulletin-studio-js `8918d55`).
- `BulletinPage`, a ClimWeb `ProductItemPage`: templates as drafts under a product page,
  issues published into the native product listing.
- Publishing and deleting clear ClimWeb's page cache, as Wagtail's own editor does.
- Images uploaded into, and picked from, the ClimWeb image library.
- Map blocks built from geomanager layers, with the date frozen at authoring time,
  hydrated on the public page with ClimWeb's own maplibre.
- UI in English, French, Spanish, Portuguese and Arabic, following the admin language.
