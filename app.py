# app.py
import streamlit as st
import pandas as pd
import re
from typing import List
import pdfplumber
import docx

st.set_page_config(page_title="Metadata Extractor", layout="wide")
st.title("PDF & Word Metadata Extractor")

# --- Helper functions ---

def extract_text_from_pdf(file) -> str:
    try:
        with pdfplumber.open(file) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except:
        return ""

def extract_text_from_docx(file) -> str:
    try:
        doc = docx.Document(file)
        return "\n".join(p.text for p in doc.paragraphs)
    except:
        return ""

def clean_line(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

ABSTRACT_HEAD_PAT = re.compile(r"^\s*abstract\b[:\-\u2013\u2014]?\s*$", re.IGNORECASE)
ABSTRACT_INLINE_PAT = re.compile(r"^\s*abstract\b[:\-\u2013\u2014]?\s*(.+)$", re.IGNORECASE)
KEYWORDS_PAT = re.compile(r"^\s*(keywords?|index\s*terms?)\b\s*[:\-\u2013\u2014]?\s*(.*)$", re.IGNORECASE)
NEXT_SECTION_PAT = re.compile(r"^\s*(keywords?|index\s*terms?|introduction|background|1[\.\s]|I[\.\s])\b", re.IGNORECASE)
EMAIL_PAT = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
NAME_PAT = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z]\.)?(?:\s+[A-Z][a-z]+)+)\b")

def find_abstract(text: str) -> str:
    lines = text.splitlines()
    abstract_lines: List[str] = []
    for i, line in enumerate(lines):
        if m := ABSTRACT_INLINE_PAT.match(line):
            abstract_lines.append(clean_line(m.group(1)))
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip() or NEXT_SECTION_PAT.match(nxt):
                    break
                abstract_lines.append(clean_line(nxt))
                j += 1
            break
        if ABSTRACT_HEAD_PAT.match(line):
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip() or NEXT_SECTION_PAT.match(nxt):
                    break
                abstract_lines.append(clean_line(nxt))
                j += 1
            break
    abstract = " ".join(abstract_lines).strip()
    abstract = re.split(r"\b(keywords?|index\s*terms?)\b[:\-\u2013\u2014]?", abstract, flags=re.IGNORECASE)[0].strip()
    return abstract

def find_keywords(text: str) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if m := KEYWORDS_PAT.match(line):
            collected = [clean_line(m.group(2))]
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip() or NEXT_SECTION_PAT.match(nxt):
                    break
                collected.append(clean_line(nxt))
                j += 1
            kws = " ".join(collected).strip().strip(";")
            parts = [p.strip(" .;") for p in re.split(r"[;,]", kws) if p.strip(" .;")]
            return ", ".join(parts)
    return ""

def find_authors(text: str) -> str:
    scope = text.splitlines()[:40]  # only first 40 lines
    filtered: List[str] = []
    for ln in scope:
        s = clean_line(ln)
        if not s:
            continue
        if EMAIL_PAT.search(s) or "http" in s.lower() or "doi" in s.lower():
            continue
        if len(s) > 6 and s.upper() == s:
            continue
        if re.search(r"\b(university|department|dept\.?|institute|laborator|school|college|center|centre)\b", s, re.IGNORECASE):
            continue
        filtered.append(s)

    for ln in filtered[:8]:
        names = NAME_PAT.findall(ln)
        if len(names) >= 2 or (len(names) == 1 and ("," in ln or " and " in ln.lower())):
            seen = set()
            ordered = []
            for n in names:
                nn = n.strip()
                if nn not in seen:
                    seen.add(nn)
                    ordered.append(nn)
            if ordered:
                return ", ".join(ordered)
    return ""

def parse_file(file, filename) -> dict:
    ext = filename.split(".")[-1].lower()
    if ext == "pdf":
        text = extract_text_from_pdf(file)
    elif ext == "docx":
        text = extract_text_from_docx(file)
    else:
        return {"filename": filename, "authors": "", "abstract": "", "keywords": "", "notes": "Unsupported file type"}
    authors = find_authors(text)
    abstract = find_abstract(text)
    keywords = find_keywords(text)
    notes = ""
    if ext == "pdf" and len(re.sub(r"\s+", "", text)) < 200:
        notes = "Possible scanned/non-searchable PDF."
    return {"filename": filename, "authors": authors, "abstract": abstract, "keywords": keywords, "notes": notes}

# --- Streamlit UI ---

uploaded_files = st.file_uploader(
    "Upload PDFs or Word files", type=["pdf", "docx"], accept_multiple_files=True
)

if uploaded_files:
    results = []
    for file in uploaded_files:
        data = parse_file(file, file.name)
        results.append(data)
    df = pd.DataFrame(results)
    st.dataframe(df)

    # Download CSV
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name="extracted_metadata.csv",
        mime="text/csv"
    )
