import io, os
from typing import List, Tuple

import cv2
import fitz  # PyMuPDF
import numpy as np
import pytesseract
import streamlit as st

st.set_page_config(page_title="Music Staff Extractor – OCR", page_icon="🎼")

# ------------------------- UI ------------------------- #
st.title("🎼 Music Staff Extractor – vision + OCR")

st.markdown(
    "Upload a choral score PDF, type staff labels (one per line).  The app "
    "detects each system visually, OCRs the label at the left, and keeps only "
    "systems whose label text matches one you entered."
)

pdf_file = st.file_uploader("PDF score", type=["pdf"])
labels_raw = st.text_area("Target staff labels – one per line", "Bass I\nBass II", height=120)
labels_set = {l.strip().lower() for l in labels_raw.splitlines() if l.strip()}

extra_pad = st.slider("Extra vertical padding around staff (px)", 0, 80, 20, 2)
run_btn = st.button("🚀 Extract")

# -------------------- Vision helpers -------------------- #

def page_to_img(page, zoom=2.0) -> np.ndarray:
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def detect_systems(img: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """Return (x,y,w,h) boxes for horizontal staff systems."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # emphasise horizontal lines
    sobel = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    sobel = cv2.convertScaleAbs(sobel)
    _, th = cv2.threshold(sobel, 0, 255, cv2.THRESH_OTSU | cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (gray.shape[1] // 4, 5))
    dil = cv2.dilate(th, kernel, iterations=2)

    contours, _ = cv2.findContours(dil, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    h_img, w_img = gray.shape
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w > 0.65 * w_img and 40 < h < 260:
            boxes.append((x, y, w, h))
    boxes.sort(key=lambda b: b[1])
    return boxes


def clean_text(txt: str) -> str:
    return " ".join(txt.strip().replace("\n", " ").split()).lower()


def ocr_strip(img: np.ndarray) -> str:
    if img.size == 0:
        return ""
    cfg = "--psm 7 --oem 3"
    txt = pytesseract.image_to_string(img, config=cfg)
    return clean_text(txt)


# -------------------- Extraction core -------------------- #

def extract_staffs(pdf_bytes: bytes, targets: set[str], pad: int) -> Tuple[bytes, List[str]]:
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    dst = fitz.open()
    a4w, a4h = fitz.paper_size("a4")

    found_labels = []
    y_cursor, dst_page = 20, None
    gap = 10

    for pno in range(src.page_count):
        page = src.load_page(pno)
        img = page_to_img(page, zoom=2.0)
        systems = detect_systems(img)
        scale = 0.5  # because zoom=2

        for (x, y, w, h) in systems:
            strip = img[y : y + h, 0 : min(220, w)]
            label_txt = ocr_strip(strip)
            if label_txt in targets:
                found_labels.append(label_txt)
            else:
                continue

            top = max(0, (y - pad) * scale)
            bottom = min(page.rect.height, (y + h + pad) * scale)
            clip = fitz.Rect(0, top, page.rect.width, bottom)
            seg_h = clip.height

            if dst_page is None or y_cursor + seg_h > a4h - 20:
                dst_page = dst.new_page(width=a4w, height=a4h)
                y_cursor = 20

            dest_rect = fitz.Rect(0, y_cursor, a4w, y_cursor + seg_h)
            dst_page.show_pdf_page(dest_rect, src, pno, clip=clip)
            y_cursor += seg_h + gap

    buf = io.BytesIO()
    if dst.page_count:
        dst.save(buf, deflate=True)
    dst.close()
    src.close()
    return buf.getvalue(), found_labels


# -------------------- Run on click -------------------- #
if run_btn:
    if not pdf_file:
        st.error("Upload a PDF first.")
        st.stop()
    if not labels_set:
        st.error("Enter at least one label.")
        st.stop()

    with st.spinner("Running computer vision + OCR …"):
        pdf_bytes, hits = extract_staffs(pdf_file.read(), labels_set, extra_pad)

    if not pdf_bytes:
        st.warning("No matching systems were found.")
        if hits:
            st.info("However, OCR did detect these labels on the pages: " + ", ".join(sorted(set(hits))))
        else:
            st.info("OCR saw no recognisable labels – try adjusting label text or check scan quality.")
    else:
        st.success(f"Done! Found {len(hits)} matching systems across the score.")
        st.download_button(
            "📥 Download extracted PDF",
            data=pdf_bytes,
            file_name="extracted_staffs.pdf",
            mime="application/pdf",
        )
