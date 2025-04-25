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
        src_bytes = uploaded_file.read()
        src_doc = fitz.open(stream=src_bytes, filetype="pdf")
        dst_doc = fitz.open()

        # Start first output page
        out_page = dst_doc.new_page(width=W, height=H)
        y_offset = margin_pt

        # Process each page
        for pno in range(len(src_doc)):
            page = src_doc[pno]
            # Collect all start hits for given staff labels
            start_hits = []
            for lbl in labels:
                for r in page.search_for(lbl):
                    start_hits.append((r, lbl))
            if not start_hits:
                continue
            # Sort by vertical position
            start_hits.sort(key=lambda x: x[0].y0)

            for found, label_used in start_hits:
                # Compute top boundary
                y0_orig = max(0, found.y0 - margin_pt - shift_up)
                # Find next 'Bass I' as end boundary
                bass_hits = [r for r in page.search_for("Bass I") if r.y0 > found.y0 + 1e-3]
                if bass_hits:
                    y1_orig = bass_hits[0].y0 - shift_up
                else:
                    y1_orig = found.y1 + fallback_height_pt - shift_up
                # Validate bounds
                if y1_orig <= y0_orig:
                    st.warning(f"Page {pno+1}, '{label_used}': invalid bounds, skipping.")
                    continue
                # Center & shrink vertically
                center = (y0_orig + y1_orig) / 2
                half_new = max(0, (y1_orig - y0_orig - shrink) / 2)
                y0 = center - half_new
                y1 = center + half_new
                clip = fitz.Rect(0, y0, page.rect.width, y1)
                if clip.is_empty:
                    st.warning(f"Page {pno+1}, '{label_used}': empty clip, skipping.")
                    continue
                # Scale to fit width
                scale = (W - 2 * margin_pt) / page.rect.width
                scaled_h = (y1 - y0) * scale
                if scaled_h <= 0:
                    st.warning(f"Page {pno+1}, '{label_used}': zero scaled height, skipping.")
                    continue
                # New page if needed
                if y_offset + scaled_h > H - margin_pt:
                    out_page = dst_doc.new_page(width=W, height=H)
                    y_offset = margin_pt
                # Destination rectangle
                dest = fitz.Rect(margin_pt, y_offset,
                                 margin_pt + (W - 2 * margin_pt),
                                 y_offset + scaled_h)
                if dest.is_empty:
                    st.warning(f"Page {pno+1}, '{label_used}': empty destination rect, skipping.")
                    continue
                # Render the clip
                out_page.show_pdf_page(dest, src_doc, pno, clip=clip)
                y_offset += scaled_h + margin_pt

        # Generate output
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
