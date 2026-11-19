---
title: Speaker identification
---

When transcript of some audio or video file is generated you can identify speakers in the transcript. Double-click the transcript in the list of transcripts to see additional options for editing and exporting.

Transcription view screen has an option to identify speakers. Click on the "Identify speakers" button to see the available options. With the MSDD model, you can leave the number of speakers on **Auto** or select the known number of speakers. Providing the known number can help when automatic detection merges similar or quieter voices. Sortformer detects the number automatically.

If the audio file is still present on the system, speaker identification will mark each speaker's sentences with an appropriate label. You can preview 10 seconds of a random sentence from an identified speaker and rename the automatically identified label to the speaker's real name. If the "Merge speaker sentences" checkbox is selected when you save the speaker labels, all consecutive sentences from the same speaker will be merged into one segment. Speaker identification is not available on Intel macOS.

The result of the last identification and the names you gave the speakers are kept for each transcript. When you open speaker identification for the transcript again, the identified speakers are shown, so you can rename them and save without identifying them again. You can still run a new identification, for example with a different model or number of speakers; its result replaces the earlier one. This feature is available since `1.4.6`

Setting an exact count guarantees that MSDD creates that many speaker clusters, but it cannot guarantee that every sentence is assigned to the correct person. Recordings with overlapping speech, large differences in microphone distance, or very little speech from one participant can still require manual correction.

### Identify speakers while transcribing

To label speakers without opening the transcript afterwards, check **Identify speakers** in the "Speaker identification" section of the window that opens when you import files or a URL. Choose the model, the number of speakers and whether to merge speaker sentences there, the same way as in the transcript view. Speakers are then identified right after each file is transcribed, and the speaker labels are included in the transcript and in any exported files. Transcription takes longer with this option on. Buzz remembers your choice for the next import.

The speakers get automatic labels, such as "Speaker 0". To give them real names, open the transcript and click "Identify speakers". The result of that identification is shown, so you can rename the speakers without identifying them again.

Speakers can also be identified for [folder watch](../preferences.md) transcriptions and from the [command line](../cli.md) with the `--identify-speakers`, `--speaker-count` and `--speaker-diarizer` options.
