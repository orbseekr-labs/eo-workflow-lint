"""EWL401: region reduction that relies on the implicit default analysis scale."""

import ee

aoi = ee.Geometry.Point(-122.29, 37.90)
image = ee.Image("LANDSAT/LC08/C02/T1_L2/LC08_044034_20210508")
stats = image.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi)
