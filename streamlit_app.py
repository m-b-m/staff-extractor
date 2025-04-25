import streamlit as st
import fitz  # PyMuPDF
import io

# Convert millimeters to points
def mm_to_pt(mm):
    return mm * 72 / 25.4

# Generate label variants (exact, dotted, abbreviated)
def gen_variants(label):
    variants = {label}
    parts = label.split(' ', 1)
    if len(parts) == 2:
        first, rest = parts
        # dotted first word
        variants.add(f"{first}. {rest}")
        # abbreviated first part if endswith 'or'
        if first.endswith('or'):
            abbr = first[:-2]
            variants.add(f"{abbr} {rest}")
            variants.add(f"{abbr}. {rest}")
    return variants

# Core extraction function
# voice_labels: list of exact labels to search (e.g. ['Tenor II', 'Ten II'])
def extract_voice(input_bytes, voice_labels, shift_mm, shrink_mm, margin_pt):
    src = fitz.open(stream=input_bytes, filetype='pdf')
    dst = fitz.open()
    a4 = fitz.paper_rect('a4')
    w, h = a4.width, a4.height
    shift = mm_to_pt(shift_mm)
    shrink = mm_to_pt(shrink_mm)

    # Hierarchy for boundary detection
    hierarchy = ['Tenor I', 'Tenor II', 'Bass I', 'Bass II']
    # Determine canonical hierarchy label
    canonical = next((hl for hl in hierarchy if any(lbl in voice_labels for lbl in gen_variants(hl))), None)
    # Generate boundary variants for next label in hierarchy
    boundary_variants = set()
    if canonical:
        try:
            idx = hierarchy.index(canonical)
            next_lbl = hierarchy[idx + 1]
            for v in gen_variants(next_lbl):
                boundary_variants.add(v)
        except (ValueError, IndexError):
            pass

    # Start first output page
    current_page = dst.new_page(width=w, height=h)
    y_offset = margin_pt

    # Iterate through pages
    for page_num in range(len(src)):
        page = src[page_num]
        # Search for any voice label variant
        instances = None
        for user_lbl in voice_labels:
            for variant in gen_variants(user_lbl):
                inst = page.search_for(variant)
                if inst:
                    instances = inst
                    break
            if instances:
                break
        if not instances:
            continue
        # Top of snippet
        t = instances[0]

        # Determine bottom boundary via boundary_variants
        b_list = []
        for b_lbl in boundary_variants:
            b_inst = page.search_for(b_lbl)
            if b_inst:
                b_list = b_inst
                break
        y0 = max(0, t.y0 - margin_pt - shift)
        if b_list:
            y1 = b_list[0].y0 - shift
        else:
            # fallback if no boundary label
            y1 = t.y1 + mm_to_pt(100) - shift

        # Center and shrink the clip region
        center_y = (y0 + y1) / 2
        half_h = max(0, (y1 - y0 - shrink) / 2)
        y0_clip = center_y - half_h
        y1_clip = center_y + half_h

        clip = fitz.Rect(0, y0_clip, page.rect.width, y1_clip)
        scale = (w - 2 * margin_pt) / page.rect.width
        scaled_h = (y1_clip - y0_clip) * scale

        # New A4 page if not enough space
        if y_offset + scaled_h > h - margin_pt:
            current_page = dst.new_page(width=w, height=h)
            y_offset = margin_pt

        dest_rect = fitz.Rect(margin_pt, y_offset,
                              margin_pt + (w - 2 * margin_pt),
                              y_offset + scaled_h)
        current_page.show_pdf_page(dest_rect, src, page_num, clip=clip)
        y_offset += scaled_h + margin_pt

    # Save result to bytes
    buf = io.BytesIO()
    dst.save(buf)
    return buf.getvalue()

# Streamlit UI
st.title('TTBB Voice Extractor & A4 Stacker')
uploaded_file = st.file_uploader('Upload TTBB Score PDF', type=['pdf'])
voice_input = st.text_input('Voice Labels (comma-separated)', value='Tenor II, Ten II')
voice_labels = [v.strip() for v in voice_input.split(',') if v.strip()]

# Parameter inputs
col1, col2, col3 = st.columns(3)
with col1:
    shift_mm = st.number_input('Shift Up (mm)', min_value=0.0, max_value=100.0, value=5.0)
with col2:
    shrink_mm = st.number_input('Shrink Height (mm)', min_value=0.0, max_value=100.0, value=5.0)
with col3:
    margin_pt = st.number_input('Margin (pt)', min_value=0.0, max_value=200.0, value=20.0)

if uploaded_file and st.button('Extract & Generate PDF'):
    with st.spinner('Processing...'):
        pdf_bytes = extract_voice(uploaded_file.read(), voice_labels, shift_mm, shrink_mm, margin_pt)
    st.success('Done! Download below.')
    st.download_button('Download Extracted PDF',
                       data=pdf_bytes,
                       file_name='extracted_' + '_'.join([v.replace(' ', '_') for v in voice_labels]) + '.pdf',
                       mime='application/pdf')
