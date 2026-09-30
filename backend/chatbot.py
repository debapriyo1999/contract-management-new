from pathlib import Path
import os
import re
import sqlite3
from typing import Any
import json
import chromadb
import requests
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).parent
DATABASE = BASE_DIR / "documents.db"
UPLOAD_DIR = BASE_DIR / "uploads"
CHROMA_DIR = BASE_DIR / "chroma_db"
CHUNK_SIZE = 900
CHUNK_OVERLAP = 120
RETRIEVAL_LIMIT = 10
COLLECTION_NAME = "contract_chunks"

load_dotenv(BASE_DIR / ".env")
RETRIEVAL_THRESHOLD = float(os.getenv("RETRIEVAL_THRESHOLD", "0.02"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
HF_MODEL = os.getenv("HF_MODEL", "HuggingFaceH4/zephyr-7b-beta")
HF_API_URL = os.getenv("HF_API_URL", "https://api-inference.huggingface.co/models")
HF_TOKEN = os.getenv("HF_TOKEN")
_embedding_model = None


def connection() -> sqlite3.Connection:
    database = sqlite3.connect(DATABASE)
    database.row_factory = sqlite3.Row
    return database


def initialize_index() -> None:
    chroma_client().get_or_create_collection(COLLECTION_NAME)


def chroma_collection():
    return chroma_client().get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def chroma_client():
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def chunks(text: str) -> list[str]:
    # Fixed-size chunking with overlap (active algorithm).
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    result = []
    for paragraph in paragraphs:
        clean = re.sub(r"\s+", " ", paragraph)
        if len(clean) <= CHUNK_SIZE:
            result.append(clean)
        else:
            result.extend(
                clean[start:start + CHUNK_SIZE]
                for start in range(0, len(clean), CHUNK_SIZE - CHUNK_OVERLAP)
            )
    return [part for part in result if part.strip()]
    r"""
    delimiter_pattern = r"\n\s*\n|(?<=[.!?])\s+"
    delimiter_chunks = [
        re.sub(r"\s+", " ", part).strip()
        for part in re.split(delimiter_pattern, text)
        if part.strip()
    ]
    print(f"Delimiter chunks:")
    return delimiter_chunks
    """

def embeddings(texts: list[str]) -> list[list[float]]:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    #print(f"Loading embedding model: {_embedding_model.encode(texts, normalize_embeddings=True).tolist()}")
    return _embedding_model.encode(texts, normalize_embeddings=True).tolist()


def replace_source(source: str, owner: str | None, text: str) -> int:
    parts = chunks(text)
    if not parts:
        return 0
    owner_value = owner or "public"
    collection = chroma_collection()
    collection.delete(where={
        "$and": [
            {"source": {"$eq": source}},
            {"owner": {"$eq": owner_value}},
        ]
    })
    vectors = embeddings(parts)
    collection.upsert(
        ids=[f"{source}:{index}" for index in range(len(parts))],
        embeddings=vectors,
        documents=parts,
        metadatas=[
            {"source": source, "owner": owner_value, "chunk_index": index}
            for index in range(len(parts))
        ],
    )
    return len(parts)


def extract_file_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    if path.suffix.lower() == ".docx":
        from docx import Document
        return "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
    return path.read_text(encoding="utf-8", errors="ignore")


def index_uploaded_document(document_id: int, owner: str, stored_name: str) -> int:
    return replace_source(
        f"document:{document_id}",
        owner,
        extract_file_text(UPLOAD_DIR / stored_name),
    )


def index_user_documents(owner: str) -> int:
    with connection() as database:
        documents = database.execute(
            "SELECT document_id, stored_name FROM documents WHERE owner = ?",
            (owner,),
        ).fetchall()
    return sum(
        index_uploaded_document(document["document_id"], owner, document["stored_name"])
        for document in documents
    )


def delete_source(source: str, owner: str) -> None:
    chroma_collection().delete(where={
        "$and": [
            {"source": {"$eq": source}},
            {"owner": {"$eq": owner}},
        ]
    })


def record_text(record: dict[str, Any]) -> str:
    pdf = record.get("pdf")
    if hasattr(pdf, "pages"):
        return "\n".join(page.extract_text() or "" for page in pdf.pages)
    return " ".join(str(value) for value in record.values() if isinstance(value, str))


def retrieve(owner: str, question: str, limit: int = RETRIEVAL_LIMIT) -> list[tuple[float, dict]]:
    collection = chroma_collection()
    total = collection.count()
    if total == 0:
        return []
    result = collection.query(
        query_embeddings=embeddings([question]),
        n_results=total,
        include=["documents", "metadatas", "distances"],
    )
    #question_terms = set(re.findall(r"[a-z0-9]+", question.lower()))
    matches = []
    documents = result.get("documents", [[]])[0]
    metadata_rows = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    tokenized_docs = [re.findall(r"[a-z0-9]+", doc.lower())for doc in documents]
    bm25 = BM25Okapi(tokenized_docs)
    query_tokens = re.findall(r"[a-z0-9]+",question.lower())
    bm25_scores = bm25.get_scores(query_tokens)
   # print(f"BM25 Scores: {bm25_scores},distances: {distances}")
    vector_ranks = {idx: rank for rank, idx in enumerate(sorted(range(len(distances)),key=lambda i: distances[i]), start=1)}
    bm25_ranks = {idx: rank for rank, idx in enumerate(sorted(range(len(bm25_scores)),key=lambda i: bm25_scores[i],reverse=True), start=1)}
    #K = 60
    # = max(bm25_scores) if len(bm25_scores) > 0 else 1
    for idx,(document, metadata, distance,bm25_score) in enumerate(zip(documents, metadata_rows, distances, bm25_scores)):
        if metadata.get("owner") not in (owner, "public"):
            continue
        #semantic_score = max(0.0, 1.0 - distance)
        #normalized_bm25 = (bm25_score / max_bm25 if max_bm25 > 0 else 0)
        #document_terms = set(re.findall(r"[a-z0-9]+", document.lower()))
        #lexical_score = len(question_terms & document_terms) / max(len(question_terms), 1)
        #score = (semantic_score * 0.7) + (normalized_bm25 * 0.3)
        score = 1 / (60 + vector_ranks[idx])+ 1 / (60 + bm25_ranks[idx])
        matches.append((score, {"source": metadata["source"], "content": document}))
    return sorted(matches, key=lambda item: item[0], reverse=True)[:limit]


def fallback_answer(question: str, matches: list[tuple[float, dict]]) -> str:
    broad_question = bool(re.search(
        r"\b(what is this|what's this|what does this|summari[sz]e|overview|about this|describe)\b",
        question.lower(),
    ))
    terms = set(re.findall(r"[a-z0-9]+", question.lower()))
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(row["content"] for _, row in matches))
    ranked = sorted(
        sentences,
        key=lambda sentence: len(terms.intersection(re.findall(r"[a-z0-9]+", sentence.lower()))),
        reverse=True,
    )
    if broad_question:
        return " ".join(ranked[:3])[:1000]
    return [ranked[0].strip()[:1000]] if ranked and ranked[0].strip() else matches[0][1]["content"][:1000]


def ask_huggingface(question: str, matches: list[tuple[float, dict]], conversation: str = "") -> str:
    context = "\n\n".join(f"[{row['source']}]\n{row['content']}" for _, row in matches)
    #prompt = (
     #   f"Answer with the help of the contract context below. If the answer is not directly supported, try to take support from the context provided and answer in your own terms . The answer should be concise ,relevant and clear to understand  "
      #  "\n\nConversation context:\n{conversation[-3000:]}\n\nContract context:\n{context}\n\nCurrent question: {question}"
    #)
    prompt = (f"""
    You are a contract analysis assistant.
    Use only the contract excerpts below to answer the question.
    Contract Excerpts:
    {context}
    Question:
    {question}
    Instructions:
    - Use only information found in the contract excerpts.
    - Do not make assumptions.
    - If the answer is not present, say:
    "The requested information could not be found in the provided contracts."
    - Combine information from multiple excerpts if necessary.
    - Explain the answer clearly and completely.
     Response Format:
     Summary:
     <direct answer>
     Details:
     <supporting explanation>
     """)
    #print(f"prompt before response :\n{prompt}")
    print("HF_API_URL =", HF_API_URL)
    print("HF_MODEL =", HF_MODEL)
    print("HF_TOKEN =", HF_TOKEN)
    print("FINAL URL =", f"{HF_API_URL.rstrip('/')}/{HF_MODEL}")
    try:
        print("BEFORE POST", flush=True)
        response = requests.post(
        f"{HF_API_URL.rstrip('/')}/{HF_MODEL}",
        headers={"Authorization": f"Bearer {HF_TOKEN}"},
        json={"inputs": prompt, "parameters": {"max_new_tokens": 950, "temperature": 0.1, "return_full_text": True}},
        timeout=120,
        )
        print("AFTER POST", flush=True)
    except Exception as e:
        print("POST EXCEPTION:", type(e))
        print("POST EXCEPTION DETAIL:", repr(e))
    print(f"prompt after response :\n{prompt}")
    #print(response.status_code)
    response.raise_for_status()
    payload = response.json()
    print("\n===== RAW PAYLOAD =====")
    print(f"payload values:{payload[0]["generated_text"].strip()}")
    print("=======================\n")
    if isinstance(payload, dict) and payload.get("error"):
        print("Error from Huggingface API:")
        raise RuntimeError(payload["error"])
    print(f"payload values newess:{payload[0]["generated_text"].strip()}")
    return payload[0]["generated_text"].strip()


def answer_question(owner: str, question: str, conversation: str = "") -> dict:
    initialize_index()
    retrieval_question = f"{conversation[-3000:]}\nCurrent question: {question}" if conversation else question
    matches = retrieve(owner, retrieval_question)
    print("\n===== TOP MATCHES =====")
    print(f"question:{retrieval_question}")
    for score, row in matches[:len(matches)]:
        print(f"Score: {score}")
        print(f"Source: {row['source']}")
        print(row['content'])
        print(len(row['content']))
        print("=" * 50)
    if not matches :
        return {"answer": "No relevant information was found in your indexed contracts.", "sources": []}
    #elif matches[0][0] < RETRIEVAL_THRESHOLD :
    #    return {"answer": "We were too uncertain to provide a reliable answer.", "sources": []}

    try:
        answer = ask_huggingface(question, matches, conversation)
        llm = True
    except (requests.RequestException, RuntimeError, KeyError, IndexError):
        answer = fallback_answer(question, matches)
        llm = False

    return {
        "answer": answer,
        "sources": [{"source": row["source"], "score": round(score, 3)} for score, row in matches],
        "llm": llm,
    }
