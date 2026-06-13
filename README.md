# Data for the Pianolatron player ([pianolatron.stanford.edu](https://pianolatron.stanford.edu))

The [Pianolatron web app](https://pianolatron.stanford.edu) provides
interactive playback on most standard web browsers of the latest MIDI
realizations of the scanned rolls in the Stanford University piano roll
collections.

Standard MIDI versions of these realizations are available in the [midi/](https://github.com/pianoroll/pianolatron-data/tree/main/midi)
folder of this repository. They are updated periodically to incorporate new
additions to the scanned roll collections as well as improvements to the roll
scanning and expression emulation software. MIDI files in the [exp/](https://github.com/pianoroll/pianolatron-data/tree/main/midi/exp)
sub-folder incorporate pedaling and emulated dynamics, if indications of these
were present on the roll, as well as simulated roll acceleration.

The [output/catalog.json](https://github.com/pianoroll/pianolatron-data/blob/main/output/catalog.json)
file provides a full listing of the rolls that are currently playable in the app.

## Installation

After creating a local copy of the repository

`git clone https://github.com/pianoroll/pianolatron-data.git`

the easiest way to ensure the scripts can be run is to make sure Pipenv is installed on your system. Then run

`pipenv install`

from within the pianolatron-data/ folder to set up a Python environment and install the necessary external Python modules.

## Generating the Pianolatron Files

Before running the `build-pianolatron-files.py` script, the necessary input files produced via the [roll-wrangler](https://github.com/pianoroll/roll-wrangler) tool must be made available for all rolls to be included in the Pianolatron data.

By default, the script will look for the input note and expression MIDI files in `midi/note/` and `midi/exp/`, respectively, and the .txt output files from `roll-wrangler`'s `process-roll-images.py` are expected to be in `input/txt/`.

The .xml metadata files from the processing also can be placed in `input/xml/`, but the script will download them if they are not available.

Finally, text or comma-separated lists (note that only the `Druid` column will be read) of the DRUIDs of the rolls to be batch-processed can be placed in `input/druids/`.

### Usage

`pipenv run python build-pianolatron-files.py --help`

will provide a full explanation of the options available. As an example, running

`pipenv run python build-pianolatron-files.py --spell-pitches`

will process all rolls whose DRUIDs are listed in the files under `input/druids/`, and will run the optional enharmonic spelling resolution model.

## Credits

The enharmonic spelling feature is made available thanks to the [pkspell](https://github.com/fosfrancesco/pkspell) project:  
Francesco Foscarin, Nicolas Audebert, and Raphaël Fournier S'niehotta, "PKSpell: Data-Driven Pitch Spelling and Key Signature Estimation," in _Proceedings of the International Society for Music Information Retrieval Conference (ISMIR)_, 2021.