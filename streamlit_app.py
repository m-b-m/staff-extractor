import io, os, tempfile
from typing import List, Tuple

import cv2
import fitz  # PyMuPDF
import numpy as np
import pytesseract
import streamlit as st


# --------------- Streamlit UI --------------- #
st.set_page_config(page_title="Music Staff Extractor – OCR version", page_icon="🎼")
st.title("🎼 Music Staff Extractor – vision + OCR")

st.markdown(
    "Upload a choral score PDF, list staff labels (one per line), and "
    "download a PDF containing **only** those systems."
)

pdf_file = st.file_uploader("PDF score", type=["pdf"])
labels_raw = st.text_area(
    "Target staff labels – one per line (case-insensitive)",
    "Bass I\nBass II\nTenor II",
    height=120,
)
labels = {l.strip().lower() for l in labels_raw.splitlines() if l.strip()}

offset_px = st.slider("Extra vertical padding around staff (px)", 0, 60, 20, 2)
extract_btn = st.button("🚀 Extract Staffs")


# --------------- Vision helpers --------------- #
def page_to_img(page, zoom=2.0) -> np.ndarray:
    """Render a PyMuPDF page to a CV2 BGR image."""
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def detect_system_bboxes(img: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """
    Return bounding boxes (x,y,w,h) for staff systems on this page image.

    Heuristic: find wide horizontal contours of roughly staff height.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # edge-detect & dilate horizontal lines
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 5))
    dil = cv2.dilate(edges, kernel, iterations=2)

    contours, _ = cv2.findContours(dil, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bboxes = []
    h, w = gray.shape
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        # keep wide boxes occupying most of page width & reasonable height
        if cw > 0.7 * w and 40 < ch < 250:
            bboxes.append((x, y, cw, ch))
    # top-to-bottom order
    bboxes.sort(key=lambda b: b[1])
    return bboxes


def ocr_label(img: np.ndarray) -> str:
    """OCR a small color/BGR image strip -> cleaned lowercase text."""
    txt = pytesseract.image_to_string(img, config="--psm 7")
    return " ".join(txt.strip().split()).lower()  # collapse whitespace


# --------------- Extraction pipeline --------------- #
def extract_staffs_from_pdf(pdf_bytes: bytes, target_labels: set[str]) -> bytes:
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = fitz.open()  # new PDF
    a4w, a4h = fitz.paper_size("a4")

    y_cursor = 20
    page_out = None
    gap = 10

    for pno in range(src.page_count):
        page = src.load_page(pno)
        img = page_to_img(page, zoom=2.0)
        bboxes = detect_system_bboxes(img)

        for (x, y, w, h) in bboxes:
            # crop left-side label strip (first 180 px)
            label_strip = img[y : y + h, 0 : min(180, w)]
            txt = ocr_label(label_strip)
            if txt not in target_labels:
                continue  # not a wanted staff

            # convert bbox back to PDF coordinates
            # note: PyMuPDF image rendered at zoom=2 → scale = 1/2
            scale = 0.5
            top_pdf = (y - offset_px) * scale
            bottom_pdf = (y + h + offset_px) * scale
            clip = fitz.Rect(0, top_pdf, page.rect.width, bottom_pdf)
            seg_height = clip.height

            if page_out is None or y_cursor + seg_height > a4h - 20:
                page_out = out.new_page(width=a4w, height=a4h)
                y_cursor = 20

            dest = fitz.Rect(0, y_cursor, a4w, y_cursor + seg_height)
            page_out.show_pdf_page(dest, src, pno, clip=clip)
            y_cursor += seg_height + gap

    # save to bytes
    buf = io.BytesIO()
    out.save(buf, deflate=True)
    out.close()
    src.close()
    return buf.getvalue()


# --------------- Run extraction --------------- #
if extract_btn:
    if not pdf_file:
        st.error("Upload a PDF first.")
        st.stop()
    if not labels:
        st.error("Enter at least one label.")
        st.stop()

    with st.spinner("Detecting staffs and running OCR…"):
        try:
            result_bytes = extract_staffs_from_pdf(pdf_file.read(), labels)
        except Exception as exc:
            st.error(f"Failed: {exc}")
            st.stop()

    if result_bytes:
        st.success("Done!")
        st.download_button(
            "📥 Download extracted PDF",
            data=result_bytes,
            file_name="extracted_staffs.pdf",
            mime="application/pdf",
        )
    else:
        st.warning("No matching staffs found.")
