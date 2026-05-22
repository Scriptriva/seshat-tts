from seshat_tts.ocr import extract_text_from_lines


def test_selected_text_does_not_skip_first_line() -> None:
    lines = ["A large group of humanoids came from the foothills", "and headed north not long ago."]

    assert (
        extract_text_from_lines(lines)
        == "A large group of humanoids came from the foothills and headed north not long ago."
    )


def test_selected_text_includes_choice_marker_text_when_inside_region() -> None:
    lines = ["Line to read.", "|. Continue"]

    assert extract_text_from_lines(lines) == "Line to read. |. Continue"


def test_selected_text_includes_pipe_marker_without_dot_when_inside_region() -> None:
    lines = ["Line to read.", "| Continue"]

    assert extract_text_from_lines(lines) == "Line to read. | Continue"
