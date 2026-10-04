"""The forecast map: a country map of forecastmanager's city forecasts, drawn on the
server so a bulletin can carry the day's forecast as an image.

The one place where this package renders something itself. Everything else about
layout belongs to the JS editor, but this map is composed without a browser (from a
Celery task, after each forecast pull), and the editor consumes it as an ordinary
image. `render` is the drawing engine: pure Python, no Django, no file paths.
"""

# The library collection the maps are promoted into, for bulletins to reference. A
# plain name: the image picker must recognise it without forecastmanager installed.
MAPS_COLLECTION = "Forecast maps"
