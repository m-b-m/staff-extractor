import streamlit as st
import fitz  # PyMuPDF
import io

# Convert mm to points
def mm_to_pt(mm):
    return mm * 72 / 25.4

# Core extraction function
def extract_voice(input_bytes, voice_label, shift_mm, shrink_mm, margin_pt):
    src = fitz.open(stream=input_bytes, filetype="pdf")
    dst = fitz.open()
    a4 = fitz.paper_rect("a4")
    w, h = a4.width, a4.height

    shift = mm_to_pt(shift_mm)
    shrink = mm_to_pt(shrink_mm)

    # Start first output page
    current_page = dst.new_page(width=w, height=h)
    y_offset = margin_pt

    # Define TTBB hierarchy for finding next voice
    hierarchy = ["Tenor I", "Tenor II", "Bass I", "Bass II"]

    for page_num in range(len(src)):
        page = src[page_num]
        # Search for voice label
        instances = page.search_for(voice_label) or page.search_for(voice_label.replace(" ", ". "))
        if not instances:
            continue
        t = instances[0]
        # Determine boundary using hierarchy
        try:
            idx = hierarchy.index(voice_label)
            next_label = hierarchy[idx + 1]
            b_list = page.search_for(next_label)
        except (ValueError, IndexError):
            b_list = []

        y0_orig = max(0, t.y0 - margin_pt - shift)
        if b_list:
            y1_orig = b_list[0].y0 - shift
        else:
            y1_orig = t.y1 + mm_to_pt(100) - shift

        # Center and shrink
        center = (y0_orig + y1_orig) / 2
        half_h_new = (y1_orig - y0_orig - shrink) / 2
        y0 = center - half_h_new
        y1 = center + half_h_new

        clip = fitz.Rect(0, y0, page.rect.width, y1)
        scale = (w - 2 * margin_pt) / page.rect.width
        scaled_h = (y1 - y0) * scale

        # New A4 page if needed
        if y_offset + scaled_h > h - margin_pt:
            current_page = dst.new_page(width=w, height=h)
            y_offset = margin_pt

        dest = fitz.Rect(margin_pt, y_offset,
                         margin_pt + (w - 2 * margin_pt),
                         y_offset + scaled_h)
        current_page.show_pdf_page(dest, src, page_num, clip=clip)
        y_offset += scaled_h + margin_pt

    # Write to bytes buffer
    output_buffer = io.BytesIO()
    dst.save(output_buffer)
    return output_buffer.getvalue()

# Streamlit UI
st.title("TTBB Voice Extractor & A4 Stacker")

uploaded_file = st.file_uploader("Upload TTBB Score PDF", type=["pdf"] )
voice_label = st.text_input("Voice Label", value="Tenor II")

col1, col2, col3 = st.columns(3)
with col1:
    shift_mm = st.number_input("Shift Up (mm)", min_value=0.0, value=5.0)
with col2:
    shrink_mm = st.number_input("Shrink Height (mm)", min_value=0.0, value=5.0)
with col3:
    margin_pt = st.number_input("Margin (pt)", min_value=0.0, value=20.0)

if uploaded_file and st.button("Extract & Generate PDF"):
    with st.spinner("Processing..."):
        input_bytes = uploaded_file.read()
        result_pdf = extract_voice(input_bytes, voice_label, shift_mm, shrink_mm, margin_pt)
    st.success("Done! Download below.")
    st.download_button(
        label="Download Extracted PDF",
        data=result_pdf,
        file_name=f"extracted_{voice_label.replace(' ', '_')}.pdf",
        mime="application/pdf"
    )
