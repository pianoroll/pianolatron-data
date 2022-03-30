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
