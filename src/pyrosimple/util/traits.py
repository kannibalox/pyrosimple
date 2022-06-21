# pylint: disable=too-many-nested-blocks
""" Classification.

    Copyright (c) 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""


import logging
import os
import re

from collections import defaultdict

from pyrosimple import config


log = logging.getLogger(__name__)


KIND_AUDIO = {"flac", "mp3", "ogg", "wav", "dts", "ac3", "alac", "wma"}
KIND_VIDEO = {
    "avi",
    "mkv",
    "m4v",
    "vob",
    "mp4",
    "mpg",
    "mpeg",
    "m2ts",
    "ts",
    "ogv",
    "wmv",
}
KIND_IMAGE = {"jpg", "png", "gif", "tif", "bmp", "svg"}
KIND_DOCS = {
    "chm",
    "pdf",
    "cbr",
    "cbz",
    "odt",
    "ods",
    "doc",
    "xls",
    "ppt",
    "epub",
    "mobi",
    "azw3",
    "djvu",
}
KIND_ARCHIVE = {"rar", "zip", "tgz", "bz2", "iso", "bin"}


_i = _k = None
_VIDEO_EXT = "|".join(re.escape("." + _i) for _i in KIND_VIDEO)
_TV_TRAIL = (
    r"(?:[._ ](?P<release_tags>PREAIR|READNFO))?"
    r"(?:[._ ](?P<release>REPACK|PROPER|REAL|REALPROPER|INTERNAL))?"
    r"(?:[._ ](?P<aspect>WS))?"
    r"(?:[._ ](?P<format>HDTV|PDTV|DSR|DVD[59]?|DVDSCR|480p|576p|720p|1080p|1080i|2160p))?"
    r"(?:[._ ](?P<release2>WEB-DL|WEB\.DL|WEBRip))?"
    r"(?:[._ ](?P<format2>HDTV|PDTV|DSR|DVD[59]?|DVDSCR|480p|576p|720p|1080p|1080i|2160p))?"
    r"(?:[._ ](?P<codec>[XH]\.?264|XviD|VTS|ISO|NTSC|PAL))?"
    r"(?:[._ ](?P<sound>MP3|AC3|DD5\.1|L?PCM|AAC 2\.0))?"
    r"(?:[._ ](?P<codec2>[XH]\.?264|XviD|VTS|ISO|NTSC|PAL))?"
    r"(?:[-. ](?P<group>.+?))?(?P<extension>" + _VIDEO_EXT + ")?$"
)
_DEFINITELY_TV = ["hdtv", "pdtv", "dsr"]

TV_PATTERNS = [
    (_k, re.compile(_i, re.I))
    for _k, _i in (
        (
            "Normal TV Episodes",
            r"^(?P<show>.+?)[._ ]S?(?P<season>\d{1,2})[xE](?P<episode>\d{2}(?:-?E\d{2})?)"
            r"(?:[._ ](?P<title>.+?[a-zA-Z]{1,2}.+?))?" + _TV_TRAIL,
        ),
        (
            "Normal TV Episodes (all-numeric season+episode)",
            r"^(?P<show>.+?)[._ ](?P<season>\d)(?P<episode>\d{2})"
            r"(?:[._ ](?P<title>.+?[a-zA-Z]{1,2}.+?))?" + _TV_TRAIL,
        ),
        (
            "Daily Shows",
            r"^(?P<show>.+?)[._ ](?P<date>\d{4}\.\d{2}\.\d{2})"
            r"(?:[._ ](?P<title>.+?[a-zA-Z]{1,2}.+?))?" + _TV_TRAIL,
        ),
        ("Full Seasons", r"^(?P<show>.+?)[._ ]S?(?P<season>\d{1,2})" + _TV_TRAIL),
        (
            "Mini Series",
            r"^(?P<show>.+?)" r"(?:[._ ](?:Part(?P<part>\d+?)|Pilot)){1,2}"
            #         (?P<year>\d{4})| creates false positives for movies!
            r"(?:[._ ](?P<title>.+?[a-z]{1,2}.+?))??" + _TV_TRAIL,
        ),
        (
            "Mini Series (Roman numerals)",
            r"^(?P<show>.+?)"
            r"(?:[._ ]Pa?r?t[._ ](?P<part>[ivxIVX]{1,3}?))"
            r"(?:[._ ](?P<title>.+?[a-z]{1,2}.+?))??" + _TV_TRAIL,
        ),
    )
]

MOVIE_PATTERNS = [
    (_k, re.compile(_i, re.I))
    for _k, _i in (
        (
            "Scene tagged movie",
            r"^(?P<title>.+?)[. ][\[(]?(?P<year>\d{4})[)\]]?"
            r"(?:[._ ](?P<release>UNRATED|REPACK|INTERNAL|MULTI|PROPER|LIMITED|RERiP))*"
            r"(?:[._ ](?P<format>480p|576p|720p|1080p|1080i|2160p))?"
            r"(?:[._ ](?P<source>BDRip|BRRip|HDRip|DVDRip|PAL|NTSC))"
            r"(?:[._ ](?P<sound1>MP3|AC3|AAC|FLAC|DTS(?:-HD)?))?"
            r"(?:[._ ](?P<codec1>xvid|divx|avc|x264|hevc|h265))?"
            r"(?:[._ ](?P<sound2>MP3|AC3|AAC|FLAC|DTS(?:-HD)?))?"
            # r"(?:[._ ](?P<channels>6ch))?"
            r"(?:[-.](?P<group>.+?))?" r"(?P<extension>" + _VIDEO_EXT + ")?$",
        ),
        (
            "Blu-ray movie",
            r"^(?P<title>.+?)[. ][\[(]?(?P<year>\d{4})[)\]]?"
            r"(?:[._ ](?P<release>UNRATED|REPACK|INTERNAL|MULTI|PROPER|LIMITED|RERiP))*"
            r"(?:[._ ](?P<format0>720p|1080p|1080i|2160p))?"
            r"(?:[._ ](?P<source>Blu-ray|BluRay|BD25|BD50))"
            r"(?:[._ ](?P<format>720p|1080p|1080i|2160p))?"
            r"(?:[._ ](?P<codec1>avc|x264|hevc|h265))?"
            r"(?:[._ ](?P<sound>AC3|AAC|FLAC|DTS(?:-HD)?))*"
            r"(?:[._ ](?P<channels>6ch|MA.5.1))?"
            r"(?:[._ ](?P<codec2>avc|x264|hevc|h265))?"
            r"(?:[-.](?P<group>.+?))?"
            r"(?P<extension>" + _VIDEO_EXT + ")?$",
        ),
    )
]

BAD_TITLE_WORDS = {
    "bdrip",
    "brrip",
    "hdrip",
    "dvdrip",
    "ntsc",
    "hdtv",
    "dvd-r",
    "dvdr",
    "dvd5",
    "dvd9",
    "web-dl",
    "blu-ray",
    "bluray",
    "bd25",
    "bd50",
    "480p",
    "576p",
    "720p",
    "1080p",
    "2160p",
    "mp3",
    "ac3",
    "dts",
}

del _k, _i


def get_filetypes(filelist, path=None, size=os.path.getsize):
    """Get a sorted list of file types and their weight in percent
    from an iterable of file names.

    @return: List of weighted file extensions (no '.'), sorted in descending order
    @rtype: list of (weight, filetype)
    """
    path = path or (lambda _: _)

    # Get total size for each file extension
    histo = defaultdict(int)
    for entry in filelist:
        ext = os.path.splitext(path(entry))[1].lstrip(".").lower()
        if ext and ext[0] == "r" and ext[1:].isdigit():
            ext = "rar"
        elif ext == "jpeg":
            ext = "jpg"
        elif ext == "mpeg":
            ext = "mpg"
        histo[ext] += size(entry)

    # Normalize values to integer percent
    total = sum(histo.values())
    if total:
        for ext, val in histo.items():
            histo[ext] = int(val * 100.0 / total + 0.499)

    return sorted(zip(histo.values(), histo.keys()), reverse=True)


def name_trait(name, add_info=False):
    """Determine content type from name."""
    kind, info = None, {}

    # Anything to check against?
    if name and not name.startswith("VTS_"):
        lower_name = name.lower()
        trait_patterns = (
            ("tv", TV_PATTERNS, "show"),
            ("movie", MOVIE_PATTERNS, "title"),
        )

        # TV check
        if any(i in lower_name for i in _DEFINITELY_TV):
            kind = "tv"
            trait_patterns = trait_patterns[:1]

        # Regex checks
        re_name = ".".join([i.lstrip("[(").rstrip(")]") for i in name.split(" .")])
        for trait, patterns, title_group in trait_patterns:
            matched, patname = None, None

            for patname, pattern in patterns:
                matched = pattern.match(re_name)
                ##print matched, patname, re_name; print "   ", pattern.pattern
                if matched and not any(
                    i in matched.groupdict()[title_group].lower()
                    for i in BAD_TITLE_WORDS
                ):
                    kind, info = trait, matched.groupdict()
                    break

            if matched:
                info["pattern"] = patname

                # Fold auxiliary groups into main one
                for key, val in list(info.items()):
                    if key[-1].isdigit():
                        del info[key]
                        if val:
                            key = re.sub("[0-9]+$", "", key)
                            info[key] = f"{info.get(key) or ''} {val}".strip()
                break

        # TODO: Split by "dvdrip", year, etc. to get to the title and then
        # do a imdb / tvdb lookup; cache results, hits for longer, misses
        # for a day at max.

    # Return requested result
    return (kind, info) if add_info else kind


def detect_traits(name=None, alias=None, filetype=None):
    """Build traits list from passed attributes.

    The result is a list of hierarchical classifiers, the top-level
    consisting of "audio", "movie", "tv", "video", "document", etc.
    It can be used as a part of completion paths to build directory
    structures.
    """
    result = []
    if filetype:
        filetype = filetype.lstrip(".")

    # Check for "themed" trackers
    if alias and alias in config.settings.ALIAS_TRAITS:
        result = [config.settings.ALIAS_TRAITS[alias], filetype or "other"]

    # Guess from file extensionn and name
    elif filetype in KIND_AUDIO:
        result = ["audio", filetype]
    elif filetype in KIND_VIDEO:
        result = ["video", filetype]

        contents = name_trait(name)
        if contents:
            result = [contents, filetype]
    elif filetype in KIND_IMAGE:
        result = ["img", filetype]
    elif filetype in KIND_DOCS:
        result = ["docs", filetype]
    elif filetype in KIND_ARCHIVE:
        result = ["misc", filetype]

        contents = name_trait(name)
        if contents:
            result = [contents, filetype]

    return result
