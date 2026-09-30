# Contract Management Starter

Minimal React frontend with a FastAPI document service and local SQLite storage.

## Requirements

Install Python 3.11+ and Node.js/npm. Python includes the `sqlite3` module, so the application does not need a separate SQLite server. On restricted PowerShell systems, Node.js is assumed to be extracted to `$env:USERPROFILE\nodejs`.

The backend creates `backend/documents.db` automatically on first start. It contains `users` and `documents` tables. Uploaded files are stored in `backend/uploads`.

## First-time setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..\frontend
$env:Path = "$env:USERPROFILE\nodejs;$env:Path"
npm.cmd install
```

If PowerShell blocks activation, run the backend with the virtual environment's executable directly:

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

## Start the backend

Open a terminal in the project folder and run:

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

The document service runs at `http://localhost:8000`.

## Start the frontend

Open a second terminal in the project folder and run:

```powershell
cd frontend
$env:Path = "$env:USERPROFILE\nodejs;$env:Path"
npm.cmd run dev
```

Open `http://localhost:5173`.

Use **Create account** once, then use **Sign in** with the same email and password. Accounts and document metadata remain available after restarting the backend because they are stored in SQLite.

## Restart the system

1. Stop each running terminal with `Ctrl+C`.
2. Start the backend again:

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

3. In a second terminal, start the frontend again:

```powershell
cd frontend
$env:Path = "$env:USERPROFILE\nodejs;$env:Path"
npm.cmd run dev
```

4. Reopen `http://localhost:5173` and sign in.

## Optional SQLite inspection

From the project folder, the SQLite command-line tool can inspect the database:

```powershell
cd backend
sqlite3 documents.db
```

Then run SQL commands such as:

```sql
.tables
SELECT email, created_at FROM users;
SELECT filename, status, uploaded_at FROM documents;
.quit
```

Do not delete `documents.db` unless you intentionally want to remove all registered users and document metadata.

## API behavior

React handles the sign-in, account creation, upload form, and document list. FastAPI handles password hashing, SQLite queries, file validation, and storage. Passwords are stored as salted PBKDF2-SHA256 hashes rather than plain text.

## Starter SOW chatbot dataset

The file `datasets/sow_qa.jsonl` contains six synthetic Statements of Work with grounded question-answer examples. It is safe for development testing and includes scope, deliverables, timelines, fees, assumptions, exclusions, and service terms.

This is a starter dataset, not legal advice or a substitute for approved company contracts. For production use, add only contracts that you are authorized to process, remove confidential personal information, and preserve document identifiers so chatbot answers can cite their source.

For a document question-answering chatbot, use the uploaded SOW text as the retrieval source and use the included QA pairs for evaluation. Retrieval-augmented generation (RAG) is generally a better fit than training a model from scratch for a small or changing contract library.

## Contract chatbot

The chatbot is implemented in `backend/chatbot.py` and uses local/open-source components. Sentence Transformers creates embeddings, ChromaDB stores vectors locally, and an optional hosted Hugging Face open-source model generates the final answer. It follows this order:

```text
Upload document
	-> extract PDF/DOCX/text content
	-> split content into overlapping chunks
	-> create embeddings
	-> store chunks and embeddings in ChromaDB (`backend/chroma_db`)
User question
	-> create a question embedding
	-> retrieve the closest ChromaDB chunks
	-> send retrieved chunks plus the question to the Hugging Face LLM
	-> display the answer and source IDs in the React UI
```

No OpenAI, Pinecone, or Ollama setup is required. Sentence Transformers downloads `all-MiniLM-L6-v2` once and caches it locally. A Hugging Face access token enables hosted open-source generation; if it is unavailable, the chatbot returns a grounded extractive answer from retrieved chunks.

CUAD is indexed once by `backend/index_cuad.py`, not when the backend starts and not for every chatbot question. The script downloads the streamed CUAD records, extracts their PDF text, chunks it, creates local embeddings, and stores the chunks in ChromaDB.

Create the private credentials file once:

```powershell
cd backend
Copy-Item .env.example .env
```

Open `backend/.env` and set the local model values. No API keys are required.

Run the indexer from the `backend` folder:

```powershell
.venv\Scripts\python.exe index_cuad.py
```

The default `CUAD_LIMIT=0` processes the full dataset. For a smaller test run, set a limit first:

```powershell
$env:CUAD_LIMIT = "10"
.venv\Scripts\python.exe index_cuad.py
```

After indexing finishes, normal backend restarts and chatbot questions use the existing ChromaDB directory and do not contact Hugging Face. Uploaded documents are indexed immediately when upload completes.

To regenerate ChromaDB chunks for the existing contract PDFs after changing the chunking algorithm, run this from the `backend` folder:

```powershell
.venv\Scripts\python.exe -c "import sqlite3; from pathlib import Path; import chatbot; db=sqlite3.connect('documents.db'); rows=db.execute('SELECT contract_id, stored_name FROM contracts').fetchall(); total=sum(chatbot.replace_source(f'contract:{row[0]}', None, chatbot.extract_file_text(Path('data/contracts') / row[1])) for row in rows); print(f'Reindexed {len(rows)} contracts into {total} chunks.')"
```

This reuses the current `chunks()` implementation, replaces each contract's existing ChromaDB chunks, and preserves the SQLite contracts and approval data. `generate_contracts.py` is a one-time generator and exits when contracts already exist.
To enable hosted open-source LLM answers, create a Hugging Face access token and set these values in `backend/.env`:

```text
HF_TOKEN=your-huggingface-token
HF_MODEL=HuggingFaceH4/zephyr-7b-beta
HF_API_URL=https://api-inference.huggingface.co/models
```

If the Hugging Face service is blocked or unavailable, the local retrieval fallback remains available.


The document list includes an **Ask a question** form. Only documents with `Pending` status can be deleted; deletion removes both the stored file and its database metadata.

The Approval Stages report includes a **Create shareable link** action. The recipient can open the link without signing in, review the assigned contract stage, and submit it. The link is signed using `SECRET_KEY` and remains usable only while that stage is `In Progress`. Set `FRONTEND_URL` in `backend/.env` when the frontend is not running at `http://localhost:5173`.

## Contract expiration email alerts

`backend/alert.py` sends an email for each contract that expires exactly 30 days from the run date. It reads the existing `contracts` table and does not create or update another database table.

Add SMTP settings to `backend/.env`:

```text
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-email@example.com
SMTP_PASSWORD=your-email-password-or-app-password
SMTP_FROM=your-email@example.com
SMTP_USE_SSL=false
ALERT_RECIPIENT=recipient@example.com
ALERT_DAYS_BEFORE=30
```

Run the alert check from the `backend` folder:

```powershell
.venv\Scripts\python.exe alert.py
```

For multiple recipients, separate addresses with commas. Use `--dry-run` to check which alerts would be sent without connecting to SMTP. Schedule this command once per day with Windows Task Scheduler or another job scheduler.

## Legacy manual startup

The backend can also be started after activating the environment:

```powershell
cd backend
.venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload --port 8000
```
