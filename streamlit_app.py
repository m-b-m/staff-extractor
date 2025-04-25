import streamlit as st
import fitz  # PyMuPDF
import io
from typing import List, Tuple

st.set_page_config(page_title="Music Staff Extractor", page_icon="🎼", layout="centered")


def parse_labels(text: str) -> List[str]:
    """Turn a comma‑separated string into a list of non‑empty labels."""
    return [lbl.strip() for lbl in text.split(",") if lbl.strip()]


def collect_crops(src_doc: fitz.Document, labels: List[str], offset: float, height: float) -> List[Tuple[int, fitz.Rect, float]]:
    """Return a sorted list of (page_number, crop_rect, segment_height)."""
    crops = []
    for page_number in range(src_doc.page_count):
        page = src_doc.load_page(page_number)
        for label in labels:
            rects = page.search_for(label, hit_max=9999)
            for rect in rects:
                top = max(rect.y0 - offset, 0)
                bottom = min(top + height, page.rect.height)
                crop_rect = fitz.Rect(0, top, page.rect.width, bottom)
                crops.append((page_number, crop_rect, bottom - top))
    # Sort by page then vertical position (top‑to‑bottom)
    crops.sort(key=lambda x: (x[0], x[1].y0))
    return crops


def assemble_pdf(src_doc: fitz.Document, crops: List[Tuple[int, fitz.Rect, float]]) -> io.BytesIO:
    """Create an A4 PDF with the cropped staff segments and return it as BytesIO."""
    out_doc = fitz.open()
    a4_width, a4_height = fitz.paper_size("a4")

    current_page = None
    cursor_y = 20  # top margin in points
    gap = 10       # gap between snippets

    for page_number, crop_rect, seg_height in crops:
        if current_page is None or cursor_y + seg_height > a4_height - 20:  # new page if needed
            current_page = out_doc.new_page(width=a4_width, height=a4_height)
            cursor_y = 20

        target_rect = fitz.Rect(0, cursor_y, a4_width, cursor_y + seg_height)
        current_page.show_pdf_page(target_rect, src_doc, page_number, clip=crop_rect)
        cursor_y += seg_height + gap

    buffer = io.BytesIO()
    out_doc.save(buffer, garbage=4, deflate=True)
    out_doc.close()
    buffer.seek(0)
    return buffer


# -------------------------- Streamlit UI ---------------------------- #

st.title("🎼 Music Staff Extractor")

st.markdown(
    """
Upload a PDF score that contains labeled music staffs (e.g. **T1**, **Tenor II**, **Baritone**).
Enter one or more labels to extract, adjust the cropping parameters, and click **Extract**
to download a new PDF that contains only the selected staffs.
    """
)

uploaded_pdf = st.file_uploader("**1. Upload PDF score**", type=["pdf"])
label_text = st.text_input("**2. Staff labels (comma‑separated)**", value="T1, Baritone")

st.write("**3. Cropping options** (points)")
col1, col2 = st.columns(2)
with col1:
    offset_val = st.slider("Vertical offset ↑", min_value=0, max_value=120, value=10, step=2)
with col2:
    height_val = st.slider("Crop height", min_value=40, max_value=300, value=80, step=2)

extract_btn = st.button("🚀 Extract Staffs")

if extract_btn:
    if uploaded_pdf is None:
        st.error("Please upload a PDF score first.")
        st.stop()

    labels = parse_labels(label_text)
    if not labels:
        st.error("Please enter at least one staff label.")
        st.stop()

    # Read uploaded PDF into memory once so we can re‑open several times if needed
    pdf_bytes = uploaded_pdf.read()

    try:
        with st.spinner("Processing… this may take a moment for large files"):
            src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            crops = collect_crops(src_doc, labels, offset_val, height_val)
            if not crops:
                st.warning("No matching labels were found in the document.")
                st.stop()
            out_buffer = assemble_pdf(src_doc, crops)
            src_doc.close()

        st.success(f"Done! Extracted {len(crops)} staff segment{'s' if len(crops)!=1 else ''}.")
        st.download_button(
            label="💾 Download extracted PDF",
            data=out_buffer,
            file_name="extracted_staffs.pdf",
            mime="application/pdf",
        )

    except Exception as e:
        st.error(f"Something went wrong: {e}")
