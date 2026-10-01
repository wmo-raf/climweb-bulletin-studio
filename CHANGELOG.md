# Changelog

## 0.1.0a1 — unreleased

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
