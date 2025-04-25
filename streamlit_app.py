import streamlit as st
import fitz  # PyMuPDF
from io import BytesIO

# Utility: convert millimeters to points
def mm_to_pt(mm):
    return mm * 72 / 25.4

st.set_page_config(page_title="PDF Staff Extractor", layout="wide")
st.title("PDF Staff Extraction Tool")

# Sidebar inputs
st.sidebar.header("Settings")
uploaded_file = st.sidebar.file_uploader("Upload PDF file", type=["pdf"])
labels_input = st.sidebar.text_area(
    "Staff labels to search (one per line)",
    value="Tenor II\nTen II\nTen. II",
    height=100
)
margin_mm = st.sidebar.number_input("Page margin (mm)", min_value=0.0, value=5.0, step=1.0)
shift_mm = st.sidebar.number_input("Shift up (mm)", min_value=0.0, value=5.0, step=1.0)
shrink_mm = st.sidebar.number_input("Shrink total height (mm)", min_value=0.0, value=5.0, step=1.0)
fallback_height_mm = st.sidebar.number_input("Fallback height if no next label (mm)", min_value=10.0, value=100.0, step=10.0)

if uploaded_file:
    labels = [line.strip() for line in labels_input.splitlines() if line.strip()]
    if not labels:
        st.error("Please enter at least one staff label to search for.")
    else:
        # Convert settings to points
        margin_pt = mm_to_pt(margin_mm)
        shift_up = mm_to_pt(shift_mm)
        shrink = mm_to_pt(shrink_mm)
        fallback_height_pt = mm_to_pt(fallback_height_mm)
        a4 = fitz.paper_rect("a4")
        W, H = a4.width, a4.height

        # Load PDF
        src_doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        dst_doc = fitz.open()

        # Begin extraction
        out_page = dst_doc.new_page(width=W, height=H)
        y_offset = margin_pt

        for pno in range(len(src_doc)):
            page = src_doc[pno]
            found = None
            for lbl in labels:
                hits = page.search_for(lbl)
                if hits:
                    found = hits[0]
                    label_used = lbl
                    break
            if not found:
                continue

            # Compute top boundary
            y0_orig = max(0, found.y0 - margin_pt - shift_up)

            # Find next 'Bass I' section boundary (or use fallback)
            bass_hits = [r for r in page.search_for("Bass I") if r.y0 > found.y0 + 1e-3]
            if bass_hits:
                y1_orig = bass_hits[0].y0 - shift_up
            else:
                y1_orig = found.y1 + fallback_height_pt - shift_up

            # Ensure bounds are valid
            if y1_orig <= y0_orig:
                st.warning(f"Page {pno+1}: invalid bounds for '{label_used}' (y0>=y1), skipping.")
                continue

            # Center & shrink vertically
            center = (y0_orig + y1_orig) / 2
            half_new = max(0, (y1_orig - y0_orig - shrink) / 2)
            y0 = center - half_new
            y1 = center + half_new
            clip = fitz.Rect(0, y0, page.rect.width, y1)

            # Skip empty clips
            if clip.is_empty:
                st.warning(f"Page {pno+1}: empty clip for '{label_used}', skipping.")
                continue

            # Scale to fit width
            scale = (W - 2 * margin_pt) / page.rect.width
            scaled_h = (y1 - y0) * scale

            # New page?
            if y_offset + scaled_h > H - margin_pt:
                out_page = dst_doc.new_page(width=W, height=H)
                y_offset = margin_pt

            # Draw
            dest = fitz.Rect(margin_pt, y_offset, margin_pt + (W - 2 * margin_pt), y_offset + scaled_h)
            out_page.show_pdf_page(dest, src_doc, pno, clip=clip)
            y_offset += scaled_h + margin_pt

        # Output
        pdf_bytes = dst_doc.write()
        st.success("Extraction complete! 🎉")
        st.download_button(
            label="Download Extracted PDF",
            data=pdf_bytes,
            file_name="extracted_staves.pdf",
            mime="application/pdf",
        )
else:
    st.info("Upload a PDF and configure labels & settings in the sidebar to get started.")
