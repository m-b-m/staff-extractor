import streamlit as st
import fitz  # PyMuPDF
import io
from typing import List, Tuple

st.set_page_config(page_title="Music Staff Extractor", page_icon="🎼", layout="centered")


# ------------------------- Helpers ------------------------- #

def parse_label_lines(text: str) -> List[str]:
    """Return non‑empty, stripped lines (labels)."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def collect_crops(
    src_doc: fitz.Document,
    labels: List[str],
    offset: float,
    height: float,
    y_overlap_tol: float = 6.0,
) -> List[Tuple[int, fitz.Rect, float]]:
    """Find *exact* label occurrences and build crop rectangles.

    Steps per label per page:
    1. search_for → candidate rectangles.
    2. Read the visible text inside that rectangle.
    3. Accept the hit only if the extracted text (collapsed whitespace) *exactly* equals the
       label (case‑sensitive).  This prevents "Bass I" from matching "Bass II".
    4. Skip if another accepted label already occupies ~same y‑band (dedup).
    """
    crops: List[Tuple[int, fitz.Rect, float]] = []
    taken_by_page: dict[int, List[float]] = {}

    labels_sorted = sorted(labels, key=len, reverse=True)

    for label in labels_sorted:
        for page_number in range(src_doc.page_count):
            page = src_doc.load_page(page_number)
            try:
                cand_rects = page.search_for(label, flags=3)  # case & whole‑word
            except TypeError:
                cand_rects = page.searchFor(label, 9999)       # very old fallback

            for rect in cand_rects:
                # 2️⃣ exact text check inside the rectangle
                raw_txt = page.get_text("text", clip=rect).strip()
                # Collapse consecutive whitespace to a single space for reliable compare
                norm_txt = " ".join(raw_txt.split())
                if norm_txt != label:
                    continue  # not an exact match

                y_cent = (rect.y0 + rect.y1) / 2
                if any(abs(y_cent - prev) <= y_overlap_tol for prev in taken_by_page.get(page_number, [])):
                    continue  # already have a label here

                top = max(rect.y0 - offset, 0)
                bottom = min(top + height, page.rect.height)
                crop_rect = fitz.Rect(0, top, page.rect.width, bottom)
                crops.append((page_number, crop_rect, bottom - top))
                taken_by_page.setdefault(page_number, []).append(y_cent)

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
        if current_page is None or cursor_y + seg_height > a4_height - 20:
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
Upload a PDF score that contains labeled music staffs (e.g. **T1**, **Tenor II**, **Baritone**).
Enter one label **per line** in the box below – this prevents accidental substring
matches (``Bass I`` no longer hits ``Bass II``).  Adjust the cropping parameters and
click **Extract** to download a new PDF with only the selected staffs.
    """
)

uploaded_pdf = st.file_uploader("**1. Upload PDF score**", type=["pdf"])
label_text = st.text_area(
    "**2. Staff labels (one per line, case‑sensitive)**",
    value="T1\nBass I\nBass II",
    height=120,
)

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

    labels = parse_label_lines(label_text)
    if not labels:
        st.error("Please enter at least one staff label.")
        st.stop()

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
