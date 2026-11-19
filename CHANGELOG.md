# Changelog

## 0.1.0a3 — 2026-11-19

Third alpha: a studio to find one's way around, media flashes and the Data Helper's WMS
layers. Needs ClimWeb 1.1.7 or later; two migrations (`0005`, `0006`). Frontend:
bulletin-studio-js `d290e95`.

- Navigation: Home, Templates and Bulletins tabs, and "New publication" from anywhere.
  The home lists the drafts the task prepared until someone publishes them (the bell
  counts them), what is left to publish and the latest publications. A template's page
  shows its cadence, its next automatic draft and its issues by year. Bulletins: search,
  filters by kind, status and template, kept when coming back from the editor.
- "New publication": an issue of a template for the current period, the next one or the
  one of another day — the studio warns when that issue exists already — or a one-off
  bulletin or flash without template, whose day the author sets.
- Editor: breadcrumbs, and a bar saying what is being edited (issue, flash, template,
  one-off) with its period, number and status. The main button follows the state:
  "Publish", "Publish the changes", "Published".
- Media flashes: a second kind of template, one square image for social networks (logo
  and flag, a map or an image, a title with the date) and the text of its post, written
  as WhatsApp formats it, with an emoji picker. Shared from the studio (share sheet, copy
  the image, copy the text, download); publishing keeps the image in the "Media flashes"
  collection and puts it on the flash's page.
- Link previews: a shared link shows the bulletin's first image or forecast map, or the
  flash's image (ClimWeb's `search_image`, set on each save).
- Map block: the Data Helper's WMS layers, their dates and legend read from the service.
  The map says whether a layer is loading, refused, or empty where the map looks.
- API: the bulletin list gives each page its template, publication and preparation
  times, and a template's issue count and next draft, in a constant number of queries;
  `date` on POST and PUT for one-offs.
- Upgrades load the new frontend: the studio and the public page add the bundle's
  modification time to its url, and the chunks it loads have hashed names.
- Image uploads no longer fail when the user may add to more than one collection.

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
- The admin menu names the pre-release a site runs: "Bulletin Studio (alpha 2)".

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
