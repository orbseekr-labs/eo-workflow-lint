"""A Landsat workflow that triggers no v0.1.0 rule."""

import ee

aoi = ee.Geometry.Point(-122.29, 37.90)
image = ee.Image("LANDSAT/LC08/C02/T1_L2/LC08_044034_20210508")

optical = image.select("SR_B.").multiply(0.0000275).add(-0.2)
thermal = image.select("ST_B10").multiply(0.00341802).add(149.0)
image = image.addBands(optical, None, True)
image = image.addBands(thermal, None, True)

nir = image.select("SR_B5")
red = image.select("SR_B4")
ndvi = image.expression("(nir - red) / (nir + red)", {"nir": nir, "red": red})

stats = ndvi.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi, scale=30)
