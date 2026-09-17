"""Color evidence from object masks. Region estimates are not garment recognition."""
import re
import cv2
import numpy as np

COLOR_NAMES = ('black', 'grey', 'white', 'red', 'orange', 'yellow', 'green', 'blue', 'purple', 'pink', 'brown', 'beige')


def color_distribution(image, mask):
    if image is None or mask is None or np.count_nonzero(mask) < 40:
        return {}
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    h, s, v = (hsv[:, :, i] for i in range(3))
    labels = np.full(h.shape, 'grey', dtype='<U8')
    chromatic = (s >= 45) & (v >= 65)
    labels[chromatic & ((h < 10) | (h >= 170))] = 'red'
    labels[chromatic & (h >= 10) & (h < 23)] = 'orange'
    labels[chromatic & (h >= 23) & (h < 35)] = 'yellow'
    labels[chromatic & (h >= 35) & (h < 86)] = 'green'
    labels[chromatic & (h >= 86) & (h < 131)] = 'blue'
    labels[chromatic & (h >= 131) & (h < 170)] = 'purple'
    # Preserve pure/dark red near hue zero; brown occupies the warmer orange-red band.
    labels[chromatic & (h >= 5) & (h < 25) & (v < 160)] = 'brown'
    labels[chromatic & ((h < 10) | (h >= 160)) & (v > 180) & (s < 150)] = 'pink'
    labels[(s < 45) & (v >= 205)] = 'white'
    labels[(h >= 10) & (h < 35) & (s >= 25) & (s < 100) & (v >= 160)] = 'beige'
    labels[v < 65] = 'black'
    selected = labels[mask > 0]
    return {name: round(float(np.count_nonzero(selected == name)) / selected.size, 5) for name in COLOR_NAMES}


def expected_colors(text):
    words = set(re.findall(r'\b[a-z]+\b', (text or '').lower()))
    if 'gray' in words:
        words.add('grey')
    if 'dark' in words and not words.intersection(COLOR_NAMES):
        words.add('black')
    return words.intersection(COLOR_NAMES)


def color_match_score(expected, distribution):
    """Return calibrated support for a requested color family, not a probability.

    Garments contain shadows, highlights, skin gaps, buttons and logos, so requiring the
    requested label to occupy the full mask rejects correct clothing. A 55% supported
    fraction is treated as full color support after visibility and multi-view checks.
    """
    text = (expected or '').lower()
    colors = expected_colors(text)
    raw = sum(distribution.get(color, 0.0) for color in colors)
    if 'khaki' in text:
        raw = distribution.get('beige', 0.0) + distribution.get('brown', 0.0)
    elif 'dark' in text and 'blue' in colors:
        blue = distribution.get('blue', 0.0)
        raw = blue + min(distribution.get('black', 0.0), blue)
    # Chromatic garments are commonly diluted by highlights/background leakage inside a
    # segmentation mask. Compare their share of informative pixels while neutral-color
    # searches continue to use the full mask.
    neutral_request = bool(colors.intersection({'black', 'grey', 'white'})) and not (
        'dark' in text and len(colors) > 0
    )
    informative = 1.0 if neutral_request else max(raw, 1.0 - distribution.get('white', 0.0) - distribution.get('grey', 0.0))
    return min(1.0, raw / max(.01, informative)), raw


def masked_regions(image, person_mask, backpack_mask=None):
    """Partition a detected silhouette, excluding detected bag pixels from clothing.

    Upper/lower bands remain approximate for an upright view. Short/wide silhouettes
    cannot support body-part localization and return unknown clothing attributes.
    A missing bag detection is unknown, never evidence of no bag.
    """
    features, visibility = {}, {'upper': 'not_visible', 'lower': 'not_visible', 'backpack': 'not_visible'}
    if person_mask is None or np.count_nonzero(person_mask) < 80:
        return features, visibility
    ys, xs = np.where(person_mask > 0)
    x1, x2, y1, y2 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    height, width = y2 - y1, x2 - x1
    if backpack_mask is not None and np.count_nonzero(backpack_mask) >= 40:
        features['backpack'] = color_distribution(image, backpack_mask)
        visibility['backpack'] = 'partial'  # Detector masks do not establish complete visibility.
    if height < 60 or height / max(1, width) < 1.25:
        return features, visibility
    clothing = person_mask.copy()
    if backpack_mask is not None:
        bag_exclusion = cv2.dilate(backpack_mask, np.ones((3, 3), np.uint8))
        clothing[bag_exclusion > 0] = 0
    for name, start, end in [('upper', .20, .58), ('lower', .62, .90)]:
        region = np.zeros_like(clothing)
        a, b = y1 + int(height * start), y1 + int(height * end)
        region[a:b] = clothing[a:b]
        visible_pixels = np.count_nonzero(region)
        total_pixels = np.count_nonzero(person_mask[a:b])
        if visible_pixels >= 80 and visible_pixels / max(1, total_pixels) >= .12:
            features[name] = color_distribution(image, region)
            visibility[name] = 'partial'
    return features, visibility
