#!/usr/bin/env python3

"""
Builds per-DRUID metadata .json files and a catalog.json file listing rolls
available for consumption by the Pianolatron app, downloading metadata files
(if not already cached) and incorporating data from the rolls' MIDI files, if
available. Writes JSON and MIDI files to the proper locations to be used by
the app.
"""

import argparse
import json
import logging
import re
from csv import DictReader
from pathlib import Path
from shutil import copy

import requests
from lxml import etree
from mido import MidiFile, tempo2bpm

WRITE_TEMPO_MAPS = False

# These are either duplicates of existing rolls, or rolls that are listed in
# the DRUIDs files but have since disappeared from the library catalog,
# or rolls that were accessioned incorrectly (hm136vg1420)
# Note: All Duo-Art rolls are currently unusable because their primary images
# are upside-down on the server.
ROLLS_TO_SKIP = [
    "rr052wh1991",  # Duplicate of gn803sk7089
    "hm136vg1420",  # Incorrectly mirrored, but replaced by rg676ym0376 - should be de-accessioned
    "df354sy6634",  # Needs to be flipped vertically
    "xc735nd8093",  # Needs to be flipped vertically
    "sh954gz9635",  # Large section of white paper from repair makes it unparsable
    "wb477ky1555",  # Green W (T-98) incorrectly cataloged as Red (T-100)
    "pz737tz3677",  # Licensee incorrectly cataloged as Green (T-98)
    "yj176wj3359",  # Licensee incorrectly cataloged as Green (T-98)
    "sm367hr9769",  # Image(s) seem to be corrupted
]

ROLL_TYPES = {
    "Welte-Mignon red roll (T-100)": "welte-red",
    "Welte-Mignon red roll (T-100).": "welte-red",
    "Welte-Mignon red roll (T-100)..": "welte-red",
    "Scale: 88n": "88-note",
    "Scale: 88n.": "88-note",
    "Scale: 65n.": "65-note",
    "88n": "88-note",
    "65n": "65-note",
    "standard": "88-note",
    "non-reproducing": "88-note",
    "Welte-Mignon green roll (T-98)": "welte-green",
    "Welte-Mignon green roll (T-98).": "welte-green",
    "Welte-Mignon licensee roll": "welte-licensee",
    "Welte-Mignon licensee roll.": "welte-licensee",
    "Welte-Mignon licensee roll (T-98).": "welte-licensee",
    "Duo-Art piano rolls": "duo-art",
    "Duo-Art piano rolls.": "duo-art",
}

PURL_BASE = "https://purl.stanford.edu/"
STACKS_BASE = "https://stacks.stanford.edu/file/"

MIDI_DIR = "midi"
TXT_DIR = "input/txt"
NS = {"x": "http://www.loc.gov/mods/v3"}


def get_metadata_for_druid(druid, redownload_xml):
    """Obtains a .xml metadata file for the roll specified by DRUID either
    from the local input/xml/ folder or the Stanford Digital Repository, then
    parses the XML to build the metadata dictionary for the roll.
    """

    def get_value_by_xpath(xpath):
        try:
            return xml_tree.xpath(
                xpath,
                namespaces=NS,
            )[0]
        except IndexError:
            return None

    # Takes an array of potential xpaths, returns the first one that matches,
    # or None
    def get_value_by_xpaths(xpaths):
        for xpath in xpaths:
            value = get_value_by_xpath(xpath)
            if value is not None:
                return value
        return value

    xml_filepath = Path(f"input/xml/{druid}.xml")

    if not xml_filepath.exists() or redownload_xml:
        response = requests.get(f"{PURL_BASE}{druid}.xml")
        xml_data = response.text
        with xml_filepath.open("w", encoding="utf-8") as _fh:
            _fh.write(xml_data)
    else:
        xml_data = xml_filepath.open("r", encoding="utf-8").read()

    try:
        mods_xml = (
            "<mods" + xml_data.split(r"<mods")[1].split(r"</mods>")[0] + "</mods>"
        )
        xml_tree = etree.fromstring(mods_xml)
    except etree.XMLSyntaxError:
        logging.error(
            f"Unable to parse XML metadata for {druid} - record is likely missing."
        )
        return None

    # The representation of the roll type in the MODS metadata continues to
    # evolve. Hopefully this logic covers all cases.
    roll_type = "NA"
    type_note = get_value_by_xpath(
        "x:physicalDescription/x:note[@displayLabel='Roll type']/text()"
    )
    scale_note = get_value_by_xpath(
        "x:physicalDescription/x:note[@displayLabel='Scale']/text()"
    )
    if type_note is not None and type_note in ROLL_TYPES:
        roll_type = ROLL_TYPES[type_note]

    if (
        scale_note is not None
        and scale_note in ROLL_TYPES
        and (roll_type == "NA" or type_note == "standard")
    ):
        roll_type = ROLL_TYPES[scale_note]

    if roll_type == "NA" or type_note == "standard":
        for note in xml_tree.xpath("(x:note)", namespaces=NS):
            if (
                note is not None
                and note.text in ROLL_TYPES
                # Most rolls of any type are marked as "88n", so don't let this
                # setting overwrite a more specific roll type note.
                and (ROLL_TYPES[note.text] != "88-note" or roll_type == "NA")
            ):
                roll_type = ROLL_TYPES[note.text]

    metadata = {
        "title_prefix": get_value_by_xpath(
            "(x:titleInfo[@usage='primary']/x:nonSort)[1]/text()"
        ),
        "title": get_value_by_xpath(
            "(x:titleInfo[@usage='primary']/x:title)[1]/text()"
        ),
        "title_part_number": get_value_by_xpath(
            "(x:titleInfo[@usage='primary']/x:partNumber)[1]/text()"
        ),
        "title_part_name": get_value_by_xpath(
            "(x:titleInfo[@usage='primary']/x:partName)[1]/text()"
        ),
        "subtitle": get_value_by_xpath("(x:titleInfo/x:subTitle)[1]/text()"),
        "composer": get_value_by_xpaths(
            [
                "x:name[descendant::x:roleTerm[text()='composer']]/x:namePart[not(@type='date')]/text()",
                "x:name[descendant::x:roleTerm[text()='Composer']]/x:namePart[not(@type='date')]/text()",
                "x:name[descendant::x:roleTerm[text()='composer.']]/x:namePart[not(@type='date')]/text()",
                "x:name[descendant::x:roleTerm[text()='cmp']]/x:namePart[not(@type='date')]/text()",
            ]
        ),
        "performer": get_value_by_xpaths(
            [
                "x:name[descendant::x:roleTerm[text()='instrumentalist']]/x:namePart[not(@type='date')]/text()",
                "x:name[descendant::x:roleTerm[text()='instrumentalist.']]/x:namePart[not(@type='date')]/text()",
            ]
        ),
        "arranger": get_value_by_xpaths(
            [
                "x:name[descendant::x:roleTerm[text()='arranger of music']]/x:namePart[not(@type='date')]/text()",
                "x:name[descendant::x:roleTerm[text()='arranger']]/x:namePart[not(@type='date')]/text()",
            ]
        ),
        "original_composer": get_value_by_xpaths(
            [
                "x:relatedItem[@displayLabel='Based on (work) :']/x:name[@type='personal']/x:namePart[not(@type='date')]/text()",
                "x:relatedItem[@displayLabel='Based on']/x:name[@type='personal']/x:namePart[not(@type='date')]/text()",
                "x:relatedItem[@displayLabele='Adaptation of (work) :']/x:name[@type='personal']/x:namePart[not(@type='date')]/text()",
                "x:relatedItem[@displayLabel='Adaptation of']/x:name[@type='personal']/x:namePart[not(@type='date')]/text()",
                "x:relatedItem[@displayLabel='Arrangement of :']/x:name[@type='personal']/x:namePart[not(@type='date')]/text()",
                "x:relatedItem[@displayLabel='Arrangement of']/x:name[@type='personal']/x:namePart[not(@type='date')]/text()",
            ]
        ),
        "label": get_value_by_xpaths(
            [
                "x:identifier[@type='issue number' and @displayLabel='Roll number']/text()",
                "x:identifier[@type='issue number']/text()",
            ]
        ),
        "publisher": get_value_by_xpaths(
            [
                "x:identifier[@type='publisher']/text()",
                "x:originInfo[@eventType='publication']/x:publisher/text()",
                "x:name[@type='corporate']/x:nameType/text()",
                "x:name[descendant::x:roleTerm[text()='publisher.']]/x:namePart/text()",
            ]
        ),
        "number": get_value_by_xpath("x:identifier[@type='publisher number']/text()"),
        "publish_date": get_value_by_xpaths(
            [
                "x:originInfo[@eventType='publication']/x:dateIssued[@keyDate='yes']/text()",
                "x:originInfo[@eventType='publication']/x:dateIssued/text()",
                "x:originInfo/x:dateIssued[@point='start']/text()",
                "x:originInfo[@displayLabel='publisher']/x:dateIssued/text()",
            ]
        ),
        "publish_place": get_value_by_xpaths(
            [
                "x:originInfo[@eventType='publication']/x:place/x:placeTerm[@type='text']/text()",
                "x:originInfo[@displayLabel='publisher']/x:place/x:placeTerm/text()",
            ]
        ),
        "recording_date": get_value_by_xpaths(
            [
                "x:note[@type='venue']/text()",
                "x:originInfo[@eventType='publication']/x:dateCaptured/text()",
            ]
        ),
        # The call number is not consistently available in all MODS variants
        # "call_number": get_value_by_xpath("x:location/x:shelfLocator/text()"),
        "type": roll_type,
        "PURL": PURL_BASE + druid,
    }

    # Derive the value for the IIIF info.json file URL, which is eventually
    # used to display the roll image in a viewer such as OpenSeadragon
    image_id = re.search(
        r"^.*?<label>(?:display image|jp2|[Ii]mage \d)<\/label>.*?<file id=\"([^\.]*)\.jp2",
        xml_data,
        re.MULTILINE | re.DOTALL,
    ).group(1)
    metadata["image_url"] = (
        f"https://stacks.stanford.edu/image/iiif/{image_id.split('_')[0]}/{image_id}/info.json"
    )

    return metadata


def build_tempo_map_from_midi(druid):
    """Extracts the tempo events (if present) from the output MIDI file for the
    roll specified by the input DRUID and return it as a list of timings and
    tempos."""

    midi_filepath = Path(f"output/midi/{druid}.mid")
    midi = MidiFile(midi_filepath)

    tempo_map = []
    current_tick = 0

    for event in midi.tracks[0]:
        current_tick += event.time
        if event.type == "set_tempo":
            tempo_map.append((current_tick, tempo2bpm(event.tempo)))

    return tempo_map


def merge_midi_velocities(roll_data, hole_data, druid, roll_type):
    """Parses the output MIDI file for the roll specified by the input DRUID
    and aligns the velocities assigned to each note event to the detected holes
    in the provided hole_data input, which is derived from the roll image
    parsing output. This aligned data can then be provided in the roll JSON
    output file for use when highlighting the note holes in the roll when it is
    displayed in the Pianolatron app."""

    midi_filepath = Path(f"output/midi/exp/{druid}.mid")

    if not midi_filepath.exists():
        logging.info(
            f"MIDI file not found for {druid}, won't include velocities in .json"
        )
        return hole_data

    first_music_px = int(roll_data["FIRST_HOLE"].removesuffix("px"))

    midi = MidiFile(midi_filepath)

    tick_notes_velocities = {}

    total_note_tracks = 2
    if roll_type == "65-note":
        total_note_tracks = 1

    for note_track in midi.tracks[1 : 1 + total_note_tracks]:
        current_tick = 0
        for event in note_track:
            current_tick += event.time
            if event.type == "note_on":
                # XXX Not sure why some note events have velocity=1, but this
                # works with the in-app expression code
                if event.velocity > 1:
                    if current_tick in tick_notes_velocities:
                        tick_notes_velocities[current_tick][event.note] = event.velocity
                    else:
                        tick_notes_velocities[current_tick] = {
                            event.note: event.velocity
                        }

    for i, hole in enumerate(hole_data):
        hole_tick = int(hole["ORIGIN_ROW"]) - first_music_px
        hole_midi = int(hole["MIDI_KEY"])

        if (
            hole_tick in tick_notes_velocities
            and hole_midi in tick_notes_velocities[hole_tick]
        ):
            hole_data[i]["VELOCITY"] = tick_notes_velocities[hole_tick][hole_midi]

    return hole_data


def get_hole_report_data(druid, analysis_source_dir):
    """Extracts hole parsing data for the roll specified by DRUID from the roll
    image parsing output in the associated .txt analysis output file."""

    txt_filepath = Path(f"{analysis_source_dir}/{druid}.txt")

    roll_data = {}
    hole_data = []

    if not txt_filepath.exists():
        logging.info(
            f"Unable to find hole analysis output file for {druid} at {txt_filepath}."
        )
        return roll_data, hole_data

    roll_keys = [
        "AVG_HOLE_WIDTH",
        "FIRST_HOLE",
        "IMAGE_WIDTH",
        "IMAGE_LENGTH",
        # "TRACKER_HOLES",
        # "ROLL_WIDTH",
        # "HARD_MARGIN_BASS",
        # "HARD_MARGIN_TREBLE",
        # "HOLE_SEPARATION",
        # "HOLE_OFFSET",
    ]

    hole_keys = [
        "NOTE_ATTACK",
        "WIDTH_COL",
        "ORIGIN_COL",
        "ORIGIN_ROW",
        "OFF_TIME",
        "MIDI_KEY",
        # "TRACKER_HOLE",
    ]

    dropped_holes = 0

    with txt_filepath.open("r") as _fh:
        while (line := _fh.readline()) and line != "@@BEGIN: HOLES\n":
            if match := re.match(r"^@([^@\s]+):\s+(.*)", line):
                key, value = match.groups()
                if key in roll_keys:
                    roll_data[key] = value.replace("px", "").strip()

        # Out-of-spec holes are marked as "BAD" in a special section of the
        # @ATON .txt hole data file following the NOTES section, but are still
        # interpreted as note holes (and possibly as control holes ?) when
        # generating the MIDI file for the roll. So it seems best to include
        # their data in the output JSON file so that they'll be highlighted
        # properly in the player.
        # The .txt hole data file also can contain a TEARS section that follows
        # the BADHOLES section, so we need to check for the start of the TEARS
        # section and stop parsing there, to handle the case that a .txt file
        # has a TEARS section after the NOTES section but no BADHOLES section.

        in_badholes = False

        while (
            (line := _fh.readline())
            and line != "@@END: BADHOLES\n"
            and line != "@@BEGIN: TEARS\n"
        ):
            if line == "@@BEGIN: BADHOLES\n":
                in_badholes = True

            if line == "@@BEGIN: HOLE\n":
                hole = {}
            if in_badholes:
                hole["CATEGORY"] = "bad"
            if match := re.match(r"^@([^@\s]+):\s+(.*)", line):
                key, value = match.groups()
                if key in hole_keys:
                    hole[key] = int(value.removesuffix("px"))
            if line == "@@END: HOLE\n":
                if "NOTE_ATTACK" in hole:
                    assert "OFF_TIME" in hole
                    assert hole["NOTE_ATTACK"] == hole["ORIGIN_ROW"]
                    del hole["NOTE_ATTACK"]
                    if hole["ORIGIN_ROW"] >= hole["OFF_TIME"]:
                        # logging.info(f"WARNING: invalid note duration: {hole}")
                        dropped_holes += 1
                    else:
                        hole_data.append(hole)
                else:
                    assert "OFF_TIME" not in hole
                    dropped_holes += 1

    # logging.info(f"Dropped Holes: {dropped_holes}")
    return roll_data, hole_data


def remap_hole_data(hole_data):
    """Abbreviates the keys in the supplied hole_data structure so that it uses
    less space when stored in a JSON file for use with the Pianolatron app."""

    new_hole_data = []

    for hole in hole_data:
        new_hole = {
            "x": hole["ORIGIN_COL"],
            "y": hole["ORIGIN_ROW"],
            "w": hole["WIDTH_COL"],
            "h": hole["OFF_TIME"] - hole["ORIGIN_ROW"],
            "m": hole["MIDI_KEY"],
            # "t": hole["TRACKER_HOLE"],
        }
        if "VELOCITY" in hole:
            new_hole["v"] = hole["VELOCITY"]
        if "CATEGORY" in hole:
            new_hole["c"] = hole["CATEGORY"]

        new_hole_data.append(new_hole)

    return new_hole_data


def write_json(druid, metadata):
    """Outputs the JSON data file for the roll specified by DRUID."""

    output_path = Path(f"output/json/{druid}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as _fh:
        json.dump(metadata, _fh)


def get_druids_from_csv_file(druids_fp):
    """Returns a list of the DRUIDs in the "Druid" column of the specified CSV
    file."""

    if not Path(druids_fp).exists():
        logging.error(f"Unable to find DRUIDs file {druids_fp}")
        return []
    druids_list = []
    with open(druids_fp, "r", newline="") as druid_csv:
        druid_reader = DictReader(druid_csv)
        for row in druid_reader:
            druids_list.append(row["Druid"])
    return druids_list


def get_druids_from_txt_file(druids_fp):
    """If the specified text input file contains one DRUID per line, parses it
    into a list of DRUIDS."""

    if not Path(druids_fp).exists():
        logging.error(f"Unable to find DRUIDs file {druids_fp}")
        return []
    druids_list = []
    with open(druids_fp, "r") as druid_txt:
        for line in druid_txt:
            druids_list.append(line.strip())
    return druids_list


def get_druids_from_csv_files():
    """Runs get_druids_from_csv_file() on all of the CSV files in the druids/
    input folder."""

    druids_list = []
    for druid_file in Path("input/druids/").glob("*.csv"):
        druids_list.extend(get_druids_from_csv_file(druid_file))
    return druids_list


def get_druids_from_txt_files():
    """Runs get_druids_from_txt_file() on all of the text files in the druids/
    input folder."""

    druids_list = []
    for druid_file in Path("input/druids/").glob("*.txt"):
        druids_list.extend(get_druids_from_txt_file(druid_file))
    return druids_list


def check_midi_profile(roll_data, roll_type, hole_data):
    column_hole_counts = {}
    # All currently supported roll types only use MIDI values between
    # 14 and 114.
    for i in range(10, 119):
        column_hole_counts[i] = 0

    last_hole_midi = 0
    last_hole_tick = 0
    last_hole_duration = 0

    first_music_px = int(roll_data["FIRST_HOLE"].removesuffix("px"))

    for hole in hole_data:
        hole_midi = int(hole["MIDI_KEY"])
        hole_tick = int(hole["ORIGIN_ROW"]) - first_music_px
        # Just skip these for now; they should only happen in weird cases like with 65-note rolls
        if hole_midi == -1:
            continue
        column_hole_counts[hole_midi] += 1
        if hole_tick > last_hole_tick:
            last_hole_midi = hole_midi
            last_hole_tick = hole_tick
            last_hole_duration = hole["OFF_TIME"] - hole["ORIGIN_ROW"]

    total_holes = len(hole_data)

    sus_midi = []
    sus_suffix = ""
    rewind_found = False

    # XXX When considering candidate rewind holes, consider determining its duration
    # by subtracting the NOTE_ATTACK (identical to ORIGIN_ROW) from the OFF_TIME
    # Minimum Red Welte rewind hole duration can be as low as 390 (px)

    if roll_type == "welte-red":
        # Left control: 14-23 (22 and 23 are questionable because many rolls do use the motor (fan) on/off switch)
        # C1: 24, C#1: 25, G7: 103
        # 104: rewind, 106: electric cutoff (rarely used). Right control ends at 113
        sus_midi = [10, 11, 12, 13, 24, 25, 103, 104, 105, 106, 114, 115, 116, 117, 118]
        if not (
            last_hole_midi == 104 or last_hole_midi == 14
        ):  # 113 is also pretty common
            logging.info(
                f"Roll type is Red Welte, but last hole MIDI is not the expected rewind hole: {last_hole_midi}",
            )
            sus_suffix += "!"
        else:
            rewind_found = True

    elif roll_type == "welte-green":
        # Left control: 16-20, A0: 21, A#0: 22, A#7: 106, B7: 107, C8: 108, Right control: 109-113
        # Green Welte rewind (16, shared with sfzp) holes tend to be longer.
        # Also sometimes there's a long C8 (108) after the rewind...
        sus_midi = [
            10,
            11,
            12,
            13,
            14,
            15,
            21,
            22,
            23,
            106,
            107,
            108,
            114,
            115,
            116,
            117,
            118,
        ]
        if last_hole_midi != 16:
            logging.info(
                f"Roll type is Green Welte, but last hole MIDI is not the expected rewind hole: {last_hole_midi}",
            )
            sus_suffix += "!"
        else:
            rewind_found = True

    elif roll_type == "welte-licensee":
        # Left control: 16-23, C1: 24, C#1: 25, F#7: 102, G7: 103, Rewind: 104, Blank: 105, Right control: 106-113
        sus_midi = [
            10,
            11,
            12,
            13,
            14,
            15,
            24,
            25,
            102,
            103,
            104,
            105,
            114,
            115,
            116,
            117,
            118,
        ]
        if last_hole_midi != 104:
            logging.info(
                f"Roll type is Licensee, but last hole MIDI is not the expected rewind hole: {last_hole_midi}",
            )
            sus_suffix += "!"
        else:
            rewind_found = True

    elif roll_type == "88-note":
        # Unused controls: 15-17, except 16 is sometimes the rewind hole
        # A0: 21, A#0: 22, B6: 107, C7: 108
        # Unused controls: 111-114
        sus_midi = [
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            21,
            22,
            107,
            108,
            111,
            112,
            113,
            114,
            115,
            116,
            117,
            118,
        ]

    elif roll_type == "duo-art":
        # Rewind (wide hole): 16, Empty (overlaps with rewind): 17, Left controls: 18-24
        # C#1: 25, D1: 26, G7: 103, G#7: 104
        # Right control: 105-110, 111-112 blank, 113 is sustain pedal
        sus_midi = [
            10,
            11,
            12,
            13,
            14,
            15,
            25,
            26,
            103,
            104,
            111,
            112,
            114,
            115,
            116,
            117,
            118,
        ]
        if last_hole_midi != 16:
            logging.info(
                f"Roll type is Duo-Art, but last hole MIDI is not the expected rewind hole: {last_hole_midi}",
            )
            sus_suffix += "!"
        else:
            rewind_found = True

    else:
        # 65-note not worth checking, ampico not supported yet
        return

    total_sus_holes = 0
    for midi in sus_midi:
        total_sus_holes += column_hole_counts[midi]

    sus_ratio = total_sus_holes / total_holes

    if sus_ratio > 0.01:
        sus_suffix += "!"
    if sus_ratio > 0.05:
        sus_suffix += "!"

    rewind_message = ""
    if rewind_found:
        rewind_message = "(at rewind hole location)"

    logging.info(f"Final hole duration: {last_hole_duration} {rewind_message}")

    logging.info(
        f"Total holes: {total_holes}, total sus holes: {total_sus_holes}, ratio: {sus_ratio:.3f} {sus_suffix}"
    )


def refine_metadata(metadata):
    """Applies various rules to massage the roll metadata extracted from its
    MODS file in get_metadata_for_druid() into formats that can be included
    in the catalog.json and per-roll JSON metadata files, accommodating missing
    fields and other oddities of the raw metadata."""

    # Note that the CSV files that list DRUIDs by collection/roll type also
    # provide descriptions for each roll with some of this metadata, but these
    # files (or descriptions) won't always be available.

    if metadata["publisher"] == "[publisher not identified]":
        metadata["publisher"] = "N/A"

    # Extract the publisher short name (e.g., Welte-Mignon) and issue number
    # from the label data, if available
    if metadata["label"] is not None:
        if len(metadata["label"].split(" ")) >= 2:
            metadata["number"], *publisher = metadata["label"].split(" ")
            metadata["publisher"] = " ".join(publisher)
        else:
            metadata["number"] = metadata["label"]
    if metadata["label"] is None and metadata["number"] is None:
        metadata["number"] = "----"

    # Construct a more user-friendly title from the contents of <titleInfo>
    fulltitle = metadata["title"].capitalize()
    if metadata["title_prefix"] is not None:
        fulltitle = f"{metadata['title_prefix']} {fulltitle}"
    if metadata["subtitle"] is not None:
        fulltitle = f"{fulltitle}: {metadata['subtitle']}"
    if metadata["title_part_number"] is not None:
        fulltitle = f"{fulltitle}: {metadata['title_part_number']}"
    if metadata["title_part_name"] is not None:
        fulltitle = f"{fulltitle}: {metadata['title_part_name']}"

    metadata["title"] = fulltitle.replace(" : ", ": ").replace(" ; ", "; ")

    # Construct a summary of the roll's music to use in the searchbar
    searchtitle = None

    composer_short = ""
    composer = ""
    arranger = ""
    performer = ""
    if metadata["composer"] is not None:
        composer_short = metadata["composer"].split(",")[0].strip()
        composer = metadata["composer"]

    if metadata["original_composer"] is not None:
        original_composer_short = metadata["original_composer"].split(",")[0].strip()
        if (
            metadata["composer"] is not None
            and original_composer_short != composer_short
        ):
            searchtitle = f"{original_composer_short}-{composer_short}"
            composer = metadata["original_composer"]
            arranger = metadata["composer"]

    elif metadata["composer"] is not None:
        searchtitle = composer_short

    if metadata["arranger"] is not None:
        arranger_short = metadata["arranger"].split(",")[0].strip()
        if searchtitle is not None and arranger_short != composer_short:
            searchtitle += f"-{arranger_short}"
        else:
            searchtitle = arranger_short
        arranger = metadata["arranger"]

    if metadata["performer"] is not None:
        performer_short = metadata["performer"].split(",")[0].strip()
        if searchtitle is not None:
            searchtitle += "/" + performer_short
        else:
            searchtitle = performer_short
        performer = metadata["performer"]

    if searchtitle is not None:
        searchtitle += " - " + fulltitle
    else:
        searchtitle = fulltitle

    metadata["searchtitle"] = searchtitle.replace(" : ", ": ").replace(" ; ", "; ")

    metadata["for_catalog"] = {
        "composer": composer,
        "arranger": arranger,
        "performer": performer,
        "work": fulltitle,
    }

    return metadata


def main():
    """Command-line entry-point."""

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    argparser = argparse.ArgumentParser(
        description="""Generate per-roll DRUID.json files as well as a
                       comprehensive catalog.json file that describes all rolls
                       processed, and place these files, along with the 
                       desired MIDI file type (_note or _exp) as DRUID.mid in
                       the local output/json/ and output/midi/ folders.
                       DRUIDs of rolls to be processed can be specified as a
                       space-delimited list on the command line, in a text file
                       with one DRUID per line (using the -f option), or in
                       a CSV file with DRUIDs in the column with the header
                       "Druid" (-c option). If no DRUIDs are supplied, the
                       script will search the input/druids/ folder for text or
                       CSV files and will process all of the DRUIDs it finds
                       listed there.
                    """
    )
    argparser.add_argument(
        "druids",
        nargs="*",
        help="DRUID(s) of one or more rolls to be processed, separated by spaces",
    )
    argparser.add_argument(
        "-c",
        "--druids-csv-file",
        help="Path to a CSV file listing rolls, with DRUIDs in the 'Druid' column",
    )
    argparser.add_argument(
        "-f",
        "--druids-txt-file",
        help="Path to a plain text file listing DRUIDs to be processed, one per line",
    )
    argparser.add_argument(
        "--no-catalog",
        action="store_true",
        help="Do not generate a new catalog.json (preexisting file will remain)",
    )
    argparser.add_argument(
        "--redownload-xml",
        action="store_true",
        help="Always download XML files, overwriting files in input/xml/",
    )
    argparser.add_argument(
        "--midi-source-dir",
        default=MIDI_DIR,
        help="Folder containg note (DIR/note/DRUID_note.mid) and expression (DIR/exp/DRUID_exp.mid) MIDI files",
    )
    argparser.add_argument(
        "--analysis-source-dir",
        default=TXT_DIR,
        help="Folder containg hole analysis output files (DRUID.txt)",
    )

    args = argparser.parse_args()

    druids = []

    if len(args.druids) > 0:
        druids = args.druids
    elif args.druids_csv_file is not None:
        druids = get_druids_from_csv_file(args.druids_csv_file)
    elif args.druids_txt_file is not None:
        druids = get_druids_from_txt_file(args.druids_txt_file)

    # If no DRDUIDS or .txt or .csv files containing DRUIDs are provided on the
    # command line, look for files listing DRUIDS in the local druids/ folder.
    if len(druids) == 0:
        druids.extend(get_druids_from_csv_files())
        druids.extend(get_druids_from_txt_files())

    # Override cmd line or CSV (or TXT) DRUIDs lists
    # druids = ["hb523vs3190"]

    catalog_entries = []

    for druid in druids:
        if druid in ROLLS_TO_SKIP:
            logging.info(f"Skipping DRUID {druid}")
            continue

        metadata = get_metadata_for_druid(druid, args.redownload_xml)
        if metadata is None:
            logging.info(f"Unable to get metadata for DRUID {druid}, skipping")
            continue

        metadata = refine_metadata(metadata)

        logging.info(f"Processing {druid}, roll type is {metadata['type']}...")

        copy(
            Path(f"{args.midi_source_dir}/note/{druid}_note.mid"),
            Path(f"output/midi/note/{druid}.mid"),
        )
        note_midi = MidiFile(Path(f"output/midi/note/{druid}.mid"))
        metadata["NOTE_MIDI_TPQ"] = note_midi.ticks_per_beat

        if metadata["type"] == "65-note":
            copy(
                Path(f"{args.midi_source_dir}/exp/{druid}_note.mid"),
                Path(f"output/midi/exp/{druid}.mid"),
            )
        else:
            copy(
                Path(f"{args.midi_source_dir}/exp/{druid}_exp.mid"),
                Path(f"output/midi/exp/{druid}.mid"),
            )

        if WRITE_TEMPO_MAPS:
            metadata["tempoMap"] = build_tempo_map_from_midi(druid)

        roll_data, hole_data = get_hole_report_data(druid, args.analysis_source_dir)

        # Add roll-level hole report info to the metadata
        for key in roll_data:
            metadata[key] = roll_data[key]

        if hole_data:
            hole_data = merge_midi_velocities(
                roll_data, hole_data, druid, metadata["type"]
            )

            # Check to see whether the parser output has a lot of holes in
            # columns where there shouldn't be holes; raise a warning if so
            check_midi_profile(roll_data, metadata["type"], hole_data)

            metadata["holeData"] = remap_hole_data(hole_data)
        else:
            metadata["holeData"] = None

        write_json(druid, metadata)

        if not args.no_catalog:
            catalog_entries.append(
                {
                    "druid": druid,
                    "title": metadata["searchtitle"],
                    "composer": metadata["for_catalog"]["composer"],
                    "performer": metadata["for_catalog"]["performer"],
                    "arranger": metadata["for_catalog"]["arranger"],
                    "work": metadata["for_catalog"]["work"],
                    "image_url": metadata["image_url"],
                    "type": metadata["type"],
                    "number": metadata["number"],
                    "publisher": metadata["publisher"],
                }
            )

    if not args.no_catalog:
        sorted_catalog = sorted(catalog_entries, key=lambda i: i["title"])
        with open("output/catalog.json", "w", encoding="utf8") as catalog_file:
            json.dump(
                sorted_catalog,
                catalog_file,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            catalog_file.write("\n")


if __name__ == "__main__":
    main()
