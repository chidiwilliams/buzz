"""Dependency-free Microsoft Word writers used by Buzz exports."""

import zipfile
from xml.sax.saxutils import escape

from buzz.speaker_transcript import SPEAKER_COLORS, group_speaker_segments
from buzz.transcriber.file_transcriber import to_timestamp


PARAGRAPH_SPLIT_TIME = 2000

_CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.'
    'wordprocessingml.document.main+xml"/>'
    "</Types>"
)

_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)

_DOCUMENT_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body>{body}<w:sectPr/></w:body>"
    "</w:document>"
)


def write_plain_docx(
    out_path: str,
    title: str,
    segments,
    include_timestamps: bool,
) -> None:
    paragraphs = [_heading_xml(title)]

    if include_timestamps:
        for segment in segments:
            text = (segment.text or "").strip()
            if not text:
                continue
            stamp = (
                f"[{to_timestamp(segment.start_time)} --> "
                f"{to_timestamp(segment.end_time)}]"
            )
            paragraphs.append(
                _paragraph_xml([(stamp + " ", True, None), (text, False, None)])
            )
    else:
        current = []
        previous_end = None
        for segment in segments:
            if (
                previous_end is not None
                and segment.start_time - previous_end >= PARAGRAPH_SPLIT_TIME
                and current
            ):
                paragraphs.append(
                    _paragraph_xml([(" ".join(current), False, None)])
                )
                current = []
            text = (segment.text or "").strip()
            if text:
                current.append(text)
            previous_end = segment.end_time
        if current:
            paragraphs.append(
                _paragraph_xml([(" ".join(current), False, None)])
            )

    _write_docx_package(out_path, paragraphs)


def write_speaker_docx(
    out_path: str,
    title: str,
    segments,
    include_timestamps: bool,
    unassigned_label: str = "Unassigned",
) -> None:
    paragraphs = [_heading_xml(title)]
    groups, speaker_order = group_speaker_segments(
        segments,
        paragraph_split_time=PARAGRAPH_SPLIT_TIME,
    )
    colors = {
        speaker: SPEAKER_COLORS[index % len(SPEAKER_COLORS)].lstrip("#")
        for index, speaker in enumerate(speaker_order)
    }

    for group in groups:
        if not group.text:
            continue
        speaker_label = group.speaker or unassigned_label
        label_runs = [
            (
                f"● {speaker_label}",
                True,
                colors.get(group.speaker, "757575"),
            )
        ]
        if include_timestamps:
            label_runs.append(
                (
                    "  " + _timestamp_text(group.start_time, group.end_time),
                    False,
                    "666666",
                )
            )
        paragraphs.append(_paragraph_xml(label_runs, spacing_after=40))
        paragraphs.append(
            _paragraph_xml([(group.text, False, "000000")], spacing_after=220)
        )

    _write_docx_package(out_path, paragraphs)


def _timestamp_text(start_time: int, end_time: int) -> str:
    return f"[{to_timestamp(start_time)} – {to_timestamp(end_time)}]"


def _run_xml(text: str, bold: bool, color: str | None) -> str:
    properties = []
    if bold:
        properties.append("<w:b/>")
    if color:
        properties.append(f'<w:color w:val="{color.lstrip("#")}"/>')
    run_properties = (
        "<w:rPr>" + "".join(properties) + "</w:rPr>"
        if properties
        else ""
    )
    text_parts = text.split("\n")
    content = "<w:br/>".join(
        f'<w:t xml:space="preserve">{escape(part)}</w:t>'
        for part in text_parts
    )
    return f"<w:r>{run_properties}{content}</w:r>"


def _paragraph_xml(runs, spacing_after: int | None = None) -> str:
    paragraph_properties = (
        f'<w:pPr><w:spacing w:after="{spacing_after}"/></w:pPr>'
        if spacing_after is not None
        else ""
    )
    return (
        "<w:p>"
        + paragraph_properties
        + "".join(_run_xml(text, bold, color) for text, bold, color in runs)
        + "</w:p>"
    )


def _heading_xml(title: str) -> str:
    return (
        '<w:p><w:pPr><w:spacing w:after="200"/></w:pPr>'
        '<w:r><w:rPr><w:b/><w:sz w:val="36"/><w:szCs w:val="36"/></w:rPr>'
        f'<w:t xml:space="preserve">{escape(title)}</w:t></w:r></w:p>'
    )


def _write_docx_package(out_path: str, paragraphs: list[str]) -> None:
    document_xml = _DOCUMENT_TEMPLATE.format(body="".join(paragraphs))
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
        docx.writestr("_rels/.rels", _RELS_XML)
        docx.writestr("word/document.xml", document_xml)
