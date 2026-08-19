"""EWL201: normalizedDifference() over encoded Landsat Collection 2 SR digital numbers."""

import ee

image = ee.Image("LANDSAT/LC08/C02/T1_L2/LC08_044034_20210508")
ndvi = image.normalizedDifference(["SR_B5", "SR_B4"])
