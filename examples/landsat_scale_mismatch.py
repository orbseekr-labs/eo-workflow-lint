"""EWL202: the documented surface-reflectance pair applied to a thermal band."""

import ee

image = ee.Image("LANDSAT/LC08/C02/T1_L2/LC08_044034_20210508")
thermal = image.select("ST_B10").multiply(0.0000275).add(-0.2)
