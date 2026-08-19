"""EWL301: a second explicit 10*log10() conversion on already-dB COPERNICUS/S1_GRD."""

import ee


def to_db(image):
    return image.log10().multiply(10)


collection = ee.ImageCollection("COPERNICUS/S1_GRD").select("VV")
converted = collection.map(to_db)
