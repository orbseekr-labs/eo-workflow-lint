"""EWL203: normalizedDifference() over correctly scaled Landsat Collection 2 SR.

The scaling is correct, so this is CONDITIONAL rather than FAIL: Earth Engine
masks output pixels where either scaled input is negative, and whether that is
wanted is a workflow choice the author should make explicit.
"""

import ee

image = ee.Image("LANDSAT/LC08/C02/T1_L2/LC08_044034_20210508")
optical = image.select("SR_B.").multiply(0.0000275).add(-0.2)
image = image.addBands(optical, None, True)

ndvi = image.normalizedDifference(["SR_B5", "SR_B4"])
