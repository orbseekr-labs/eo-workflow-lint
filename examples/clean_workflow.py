"""A Landsat workflow that triggers no v0.1.0 rule.

The normalized difference is computed with an explicit expression so that
negative surface-reflectance inputs are retained rather than masked (see
``eo-workflow-lint explain EWL203``). Retaining them is a workflow choice; the
denominator guard and its threshold are deliberate choices too.
"""

import ee

aoi = ee.Geometry.Point(-122.29, 37.90)
image = ee.Image("LANDSAT/LC08/C02/T1_L2/LC08_044034_20210508")

optical = image.select("SR_B.").multiply(0.0000275).add(-0.2)
thermal = image.select("ST_B10").multiply(0.00341802).add(149.0)
image = image.addBands(optical, None, True)
image = image.addBands(thermal, None, True)

nir = image.select("SR_B5")
red = image.select("SR_B4")

# A workflow choice for this data, not a universal constant.
DENOMINATOR_EPSILON = 1e-6

denominator = nir.add(red)
ndvi = image.expression(
    "(nir - red) / denominator",
    {"nir": nir, "red": red, "denominator": denominator},
)
# updateMask() only narrows the mask the inputs already carry, so previously
# masked pixels stay masked. The inputs are never unmask()ed.
ndvi = ndvi.updateMask(denominator.abs().gte(DENOMINATOR_EPSILON))

stats = ndvi.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi, scale=30)
