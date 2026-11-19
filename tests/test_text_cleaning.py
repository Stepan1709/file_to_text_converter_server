from app.services.file_types import get_file_type
from app.services.text_cleaning import convert_unicode_escapes, remove_embedded_images


def test_unicode_escapes_are_converted() -> None:
    assert convert_unicode_escapes("/uni041F/uni0440/uni0438/uni0432/uni0435/uni0442") == "Привет"


def test_embedded_images_are_removed() -> None:
    assert remove_embedded_images("a![Image](data:image/png;base64,QUJD)b") == "ab"


def test_file_type_by_extension() -> None:
    assert get_file_type("A.JPG") == "image"
    assert get_file_type("page.htm") == "html"
    assert get_file_type("data.xml") == "xml_uspto"
    assert get_file_type("noext") == ""
