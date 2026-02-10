import streamlit as st
import fitz  # PyMuPDF
import requests
from PIL import Image
import io
import pandas as pd
import os
import time  # Rate limit handling
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import re

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")

# Brave Search

def brave_search(query):
    url = f"https://api.search.brave.com/res/v1/web/search?q={query}"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY
    }
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        results = res.json()
        web_results = results.get("web", {}).get("results", [])
        return "\n\n".join([
            f"{r['title']}\n{r['description']}" for r in web_results[:5]
        ]) if web_results else "No relevant web research found."
    return f"❌ Brave Search failed. Status code: {res.status_code}\nResponse: {res.text}"

# Extract Keywords

def extract_research_keywords(text):
    prompt = f"""
You are a helpful AI agent working for a venture capital analyst.

Read the following pitch deck content, then generate 3–5 **short, high-quality research keywords or search queries** that would help us investigate:
- the company and its technology,
- market dynamics,
- competitors,
- business model,
- and regional context.

**Important:** Each search phrase should be short (7–9 words max), general enough to produce results in public search engines, and not overly specific to niche terms. Avoid unnecessary repetition of country names or long product names.

Respond ONLY with a bulleted list of search phrases.

Pitch deck:
{text}
"""
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 512,
        "messages": [{"role": "user", "content": prompt}]
    }
    res = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
    if "content" in res.json():
        text_block = res.json()["content"][0]["text"]
        return [line.strip("\u2022*- ").strip() for line in text_block.splitlines() if line.strip()]
    return ["no keywords found"]

# Extract Financials
@st.cache_data
def extract_all_text_from_excels(file_list):
    combined_summary = ""
    for file in file_list:
        try:
            if file.name.endswith(".csv"):
                df = pd.read_csv(file)
                combined_summary += f"\n📂 File: {file.name}\n"
                combined_summary += df.to_markdown(index=False) + "\n"
            elif file.name.endswith(".pdf"):
                combined_summary += f"\n📂 File: {file.name}\n"
                file.seek(0)
                with fitz.open(stream=file.read(), filetype="pdf") as doc:
                    for page in doc:
                        combined_summary += page.get_text()
            else:
                xls = pd.read_excel(file, sheet_name=None)
                combined_summary += f"\n📂 File: {file.name}\n"
                for sheet, df in xls.items():
                    combined_summary += f"\n### Sheet: {sheet}\n"
                    combined_summary += df.to_markdown(index=False) + "\n"
        except Exception as e:
            combined_summary += f"\n Failed to read {file.name}: {e}\n"
    return combined_summary

# Claude Memo Generator

def ask_claude(text, research, financial_summary):
    combined_memo = ""
    for filename in sorted(os.listdir("prompts")):
        if (
            not filename.endswith(".txt")
            or filename.startswith("00_due_diligence_summary")
            or filename.startswith("dd_")  # skip POEM prompts
        ):
            continue

        section_name = filename.replace(".txt", "").replace("_", " ").title()
        st.info(f"✏️ Generating section: {section_name}")

        try:
            with open(os.path.join("prompts", filename)) as f:
                section_prompt = f.read()

            section_prompt = section_prompt.replace("{text}", text).replace("{research}", research).replace("{financial_summary}", financial_summary)


            headers = {
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
            payload = {
                "model": CLAUDE_MODEL,
                "max_tokens": 8000,
                "messages": [{"role": "user", "content": section_prompt}]
            }
            res = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)

            if res.status_code != 200:
                st.error(f"Claude API failed for {filename}: {res.status_code} {res.text}")
                continue

            section_result = res.json().get("content", [{"text": f"❌ No response for {filename}"}])[0]["text"]

        except Exception as e:
            section_result = f"❌ Could not process {filename}: {e}"

        combined_memo += f"\n\n## {section_name}\n{section_result.strip()}\n"
        time.sleep(30)  # avoid hitting rate limits
    return combined_memo

# PDF Extractors
@st.cache_data
def extract_text_from_pdf(uploaded_file):
    text = ""
    with fitz.open(stream=uploaded_file.read(), filetype="pdf") as doc:
        for page in doc:
            text += page.get_text()
    return text

def extract_images_from_pdf(uploaded_file):
    uploaded_file.seek(0)
    images = []
    with fitz.open(stream=uploaded_file.read(), filetype="pdf") as doc:
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image = Image.open(io.BytesIO(image_bytes))
                images.append(image)
    return images

# Save memo as PDF

def save_memo_as_pdf(memo_text, filename="investment_memo.pdf"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=40, leftMargin=40,
                            topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    story = []

    for line in memo_text.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 12))
        else:
            # Clean Claude's formatting: convert <br> to newlines and remove weird tags
            line = line.replace("<br>", "\n").replace("<br/>", "\n")
            line = re.sub(r"<[^>]+>", "", line)  # remove all other tags like <b> or <i>
            line = line.replace("  ", "&nbsp;&nbsp;")
            para = Paragraph(line, styles["Normal"])
            story.append(para)
            story.append(Spacer(1, 8))

    doc.build(story)
    buffer.seek(0)
    return buffer

# UI
st.title("Fundie Ventures VC Analyst: Due Diligence & Memo Generator")
st.markdown("""
<div style="background-color: #1e1e1e; color: #f5f5f5; padding: 20px; border-radius: 10px; border-left: 6px solid #a5cd39;">
    <h3 style="margin-top: 0; color: #a5cd39;">🚀 Fundie Ventures VC Analyst Memo Generator (Experimental)</h3>
    <p>This internal tool was developed for <strong>Fundie Ventures</strong> to help quickly transform pitch decks, financials, and external research into structured <strong>draft investment memos</strong>.</p>
    <p>It combines AI models (Claude), web search (Brave), and PDF parsing to generate detailed due diligence memos aligned with our internal template. Analysts can use it to explore startup potential, risks, team quality, and market dynamics.</p>
    <p><strong>How to use:</strong> Upload a pitch deck and financial documents, generate a due diligence summary, then automatically build the memo section by section with editable outputs.</p>
    <p><strong>Note:</strong> This tool is <em>experimental</em> and intended for <strong>internal use only</strong>. All outputs should be reviewed by an investment team member before external sharing.</p>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<style>
button[kind="primary"] {
    font-size: 18px !important;
    padding: 0.75em 1.5em !important;
}
</style>
""", unsafe_allow_html=True)



uploaded_file = st.file_uploader("Upload a pitch deck (PDF)", type=["pdf"])
uploaded_financials = st.file_uploader(
    "Upload financials (Excel, CSV, or PDF)",
    type=["xlsx", "xls", "csv", "pdf"],
    accept_multiple_files=True,
    key="financial_uploader"
)

if uploaded_file is not None:
    with st.spinner("📖 Reading pitch deck..."):
        extracted_text = extract_text_from_pdf(uploaded_file)
        images = extract_images_from_pdf(uploaded_file)

    # st.subheader("📖 Full Extracted Pitch Deck Text")
    # st.text_area("Pitch Deck Text", extracted_text, height=600)

    if uploaded_financials:
        financial_summary_preview = extract_all_text_from_excels(uploaded_financials)
    else:
        financial_summary_preview = "⚠️ No financials uploaded."

    # st.subheader("📊 Full Extracted Financial Summary")
    # st.text_area("Financial Summary", financial_summary_preview, height=600)


    # 🔍 Generate Due Diligence Summary
    # 🧩 Generate POEM-Based Due Diligence
    if st.button("Generate POEM Due Diligence"):
        with st.spinner("🧠 Generating POEM-based due diligence..."):
            poem_sections = ["proposition", "organization", "economics", "milestones"]
            full_poem_output = ""

            for section in poem_sections:
                filename = f"prompts/dd_{section}.txt"
                section_name = section.capitalize()

                try:
                    with open(filename) as f:
                        prompt_template = f.read()

                    prompt_filled = (
                        prompt_template
                        .replace("{text}", extracted_text)
                        .replace("{research}", research if "research" in locals() else "")
                        .replace("{financial_summary}", financial_summary_preview)
                    )

                    headers = {
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": CLAUDE_MODEL,
                        "max_tokens": 3000,
                        "messages": [{"role": "user", "content": prompt_filled}]
                    }
                    res = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)

                    if res.status_code != 200:
                        section_result = f"❌ Claude API failed for {section_name}: {res.status_code}\n{res.text}"
                    else:
                        section_result = res.json().get("content", [{"text": "❌ No result returned"}])[0]["text"]

                except Exception as e:
                    section_result = f"❌ Error in {section_name}: {e}"

                full_poem_output += f"\n\n## {section_name}\n{section_result.strip()}\n"
                time.sleep(15)

            st.session_state.poem_dd = full_poem_output

    if "poem_dd" in st.session_state:
        st.subheader("🧩 POEM-Based Due Diligence Output")
        st.text_area("Edit the POEM due diligence summary below:", value=st.session_state.poem_dd, height=600)


       

    # 📝 Generate Investment Memo
    if "poem_dd" in st.session_state and st.button("Generate Investment Memo"):
        with st.spinner("🧠 Generating research keywords..."):
            keywords = extract_research_keywords(st.session_state.poem_dd)
            # st.success("Top keywords identified:")
            # for kw in keywords:
            #     st.markdown(f"🔎 **{kw}**")

        with st.spinner("🌐 Performing Brave search..."):
            research = ""
            for kw in keywords:
                research += f"🔍 {kw}\n" + brave_search(kw) + "\n\n"
                time.sleep(2) 
        # st.subheader("🔑 Research Keywords")
        # for kw in keywords:
        #     st.markdown(f"- **{kw}**")

        # st.subheader("🌐 Brave Search Results")
        # st.text_area("Brave Research Text", research, height=400)

        if uploaded_financials:
            financial_summary = extract_all_text_from_excels(uploaded_financials)
        else:
            st.warning("⚠️ No financials uploaded. Please upload a spreadsheet for best results.")
            financial_summary = "Financial data not provided. Please request from the startup."

        with st.spinner("📄 Generating investment memo..."):
            memo = ask_claude(st.session_state.poem_dd, research, financial_summary)
            st.session_state.generated_memo = memo


        if "generated_memo" in st.session_state:
            st.subheader("📄 Investment Memo")
            st.text_area("Full Memo Text", st.session_state.generated_memo, height=800)

            st.download_button("📅 Download Memo as Text", st.session_state.generated_memo, file_name="investment_memo.txt")
            

            pdf_bytes = save_memo_as_pdf(st.session_state.generated_memo)
            st.download_button("📄 Download Memo as PDF", data=pdf_bytes, file_name="investment_memo.pdf", mime="application/pdf")


        st.subheader("📊 Optional Images to Include in the Memo")
        for i, img in enumerate(images[:5]):
            st.image(img, caption=f"Slide {i+1}", use_container_width=True)
