# Contract Management Starter

Minimal React frontend with a FastAPI document service and local SQLite storage.

## Requirements

Install Python 3.11+ and Node.js/npm. Python includes the `sqlite3` module, so the application does not need a separate SQLite server. On restricted PowerShell systems, Node.js is assumed to be extracted to `$env:USERPROFILE\nodejs`.

The backend creates `backend/documents.db` automatically on first start, with `users`, `contracts`, and `approval_stages` tables ready immediately (see [Step 3](#step-3--uploading-contracts-remote-users) and [Step 4](#step-4--generating-bulk-contracts-for-testing) below for how contracts get added). Uploaded and generated contract files are stored in `backend/data/contracts`.

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

If PowerShell blocks activation, run the backend with the virtual environment's executable directly (used in every command below):

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

Create the private credentials file once, then fill in the values described in [Environment variables and credentials](#environment-variables-and-credentials):

```powershell
cd backend
Copy-Item .env.example .env
```

## Step 1 — Start the backend

Open a terminal in the project folder and run:

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

The document service runs at `http://localhost:8000`.

## Step 2 — Start the frontend

Open a second terminal in the project folder and run:

```powershell
cd frontend
$env:Path = "$env:USERPROFILE\nodejs;$env:Path"
npm.cmd run dev
```

Open `http://localhost:5173`. Use **Create account** once, then use **Sign in** with the same email and password. Accounts remain available after restarting the backend because they are stored in SQLite (`backend/documents.db`).

## Step 3 — Uploading contracts (remote users)

Signed-in users can upload their own contract files directly from the workspace:

1. Sign in, then fill out the **Upload a document** card (counterparty, department, contract type) and choose a `.pdf`, `.doc`, `.docx`, or `.txt` file (10 MB limit).
2. Submitting calls `POST /documents/upload` (`backend/main.py`), which:
   - validates the file extension and size,
   - inserts a `contracts` row with status `Pending` and a stored copy in `backend/data/contracts`,
   - creates the standard four-stage approval workflow (`Legal Review` → `Finance Review` → `Department Head Approval` → `Final Sign-off`), starting at `Legal Review`,
   - extracts the document text and indexes it into ChromaDB (via `chatbot.replace_source`) so the chatbot can answer questions about it immediately.
3. The new contract appears in **Documents** and the **Approval Stages** report right away; no backend restart is required.

Uploads are shared across all signed-in users (there is no per-user ownership column), the same as contracts created by the generator script below.

## Step 4 — Generating bulk contracts for testing

Use the generator scripts below when you want many contracts and reviewer/approver accounts at once (for example, before a demo or a load test) instead of uploading one file at a time through the UI:

```powershell
cd backend

# Create 50 test user accounts (testuser01@example.com ... testuser50@example.com)
$env:USER_COUNT = "50"
$env:USER_PASSWORD = "Password123!"
.venv\Scripts\python.exe generate_test_users.py

# Create 50 dummy contract PDFs, contract rows, approval stages, and chatbot index entries
$env:CONTRACT_COUNT = "50"
.venv\Scripts\python.exe generate_contracts.py
```

Notes:

- `generate_contracts.py` exits without changes if the `contracts` table already has rows. Delete `backend/documents.db` first (this also removes all users) if you want to regenerate from scratch.
- `generate_test_users.py` skips any email that already exists, so it is safe to re-run with a higher `USER_COUNT`.
- `backend/documents.db`, `backend/data/contracts/`, and `backend/chroma_db/` are all listed in `.gitignore`, so generated test data (and real uploads) never gets pushed to GitHub regardless of size.

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

## Environment variables and credentials

All backend credentials and tunable settings live in `backend/.env` (copied once from `backend/.env.example`, never committed — it is listed in `.gitignore`). `load_dotenv()` reads it on backend startup, so restart `uvicorn` after changing any value.

| Variable | Used by | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | `main.py` | Signs shareable approval links (`/approvals/share`). Replace the placeholder with a long random string before sharing links outside your machine. |
| `FRONTEND_URL` | `main.py` | Base URL embedded in generated shareable links. Set this when the frontend is not running at `http://localhost:5173`. |
| `EMBEDDING_MODEL` | `chatbot.py` | Sentence Transformers model used to embed chunks and questions. Defaults to `sentence-transformers/all-MiniLM-L6-v2`, downloaded and cached locally the first time it runs. |
| `RETRIEVAL_THRESHOLD` | `chatbot.py` | Minimum similarity score for a retrieved chunk to be used in an answer. Lower it if the chatbot responds "no relevant information found" too often. |
| `INCLUDE_PUBLIC_CONTRACTS` | `chatbot.py` | When `true`, lets chat answers cite the indexed CUAD dataset in addition to your own uploaded/generated contracts. |
| `HF_TOKEN` | `chatbot.py` | Optional Hugging Face access token. When set, the chatbot calls a hosted open-source model for generated answers instead of returning a grounded extractive answer. |
| `HF_MODEL` | `chatbot.py` | Hugging Face model id to call when `HF_TOKEN` is set (default `HuggingFaceH4/zephyr-7b-beta`). |
| `HF_API_URL` | `chatbot.py` | Base inference API URL for the Hugging Face model. |
| `SMTP_HOST`, `SMTP_PORT` | `alert.py` | SMTP server and port used to send contract-expiration emails. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | `alert.py` | Mailbox credentials for authenticating with the SMTP server. Use an app password rather than your real account password where the provider supports it. |
| `SMTP_FROM` | `alert.py` | "From" address on alert emails. |
| `SMTP_USE_SSL` | `alert.py` | Set to `true` for implicit SSL (e.g. port 465); leave `false` for STARTTLS (e.g. port 587). |
| `ALERT_RECIPIENT` | `alert.py` | Comma-separated list of recipient addresses for expiration alerts. |
| `ALERT_DAYS_BEFORE` | `alert.py` | How many days before `expiry_date` a contract qualifies for an alert (default `30`). |

No values are required just to run the app locally — if `HF_TOKEN` is unset the chatbot still works using local retrieval, and `alert.py` only needs real SMTP credentials when you actually run it.

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
SELECT filename, status, expiry_date FROM contracts;
.quit
```

Do not delete `documents.db` unless you intentionally want to remove all registered users and contract metadata.

## API behavior

React handles sign-in, account creation, the upload form, and the document list. FastAPI handles password hashing, SQLite queries, file validation and storage for uploads, and indexing new contract text for the chatbot. Passwords are stored as salted PBKDF2-SHA256 hashes rather than plain text. See [Step 3](#step-3--uploading-contracts-remote-users) above for upload details.

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

No OpenAI, Pinecone, or Ollama setup is required. See [Environment variables and credentials](#environment-variables-and-credentials) above for `EMBEDDING_MODEL`, `HF_TOKEN`, `HF_MODEL`, and `HF_API_URL`. If the Hugging Face service is blocked, unavailable, or `HF_TOKEN` is unset, the chatbot returns a grounded extractive answer from retrieved chunks instead.

CUAD is indexed once by `backend/index_cuad.py`, not when the backend starts and not for every chatbot question. The script downloads the streamed CUAD records, extracts their PDF text, chunks it, creates local embeddings, and stores the chunks in ChromaDB.

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

This reuses the current `chunks()` implementation, replaces each contract's existing ChromaDB chunks, and preserves the SQLite contracts and approval data.

The document list includes an **Ask a question** form. Only documents with `Pending` status can be deleted; deletion removes both the stored file and its database metadata.

The Approval Stages report includes a **Create shareable link** action. The recipient can open the link without signing in, review the assigned contract stage, and submit it. The link is signed using `SECRET_KEY` and remains usable only while that stage is `In Progress`.

## Contract expiration email alerts

`backend/alert.py` sends an email for each contract that expires exactly `ALERT_DAYS_BEFORE` days from the run date. It reads the existing `contracts` table and does not create or update another database table. Set the `SMTP_*` and `ALERT_*` values in `backend/.env` (see [Environment variables and credentials](#environment-variables-and-credentials)) before running it.

Run the alert check from the `backend` folder:

```powershell
.venv\Scripts\python.exe alert.py
```

Use `--dry-run` to check which alerts would be sent without connecting to SMTP. Schedule this command once per day with Windows Task Scheduler or another job scheduler.

## Legacy manual startup

The backend can also be started after activating the environment:

```powershell
cd backend
.venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload --port 8000
```
