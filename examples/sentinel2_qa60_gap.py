"""EWL501: QA60 cloud masking entirely inside the documented QA60 availability gap."""

import ee


def mask_clouds(image):
    qa = image.select("QA60")
    return image.updateMask(qa.eq(0))


collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterDate(
    "2023-01-01", "2024-01-01"
)
clean = collection.map(mask_clouds)
