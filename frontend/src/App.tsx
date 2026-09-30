import { ChangeEvent, FormEvent, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
type DocumentItem = { filename: string; status: string; uploaded_at: string };

export default function App() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadDocuments(accessToken: string) {
    const response = await fetch(`${API_URL}/documents`, { headers: { Authorization: `Bearer ${accessToken}` } });
    if (response.ok) setDocuments(await response.json());
  }

  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const response = await fetch(`${API_URL}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? "Login failed");
      setToken(data.access_token); setMessage("Signed in successfully."); await loadDocuments(data.access_token);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to sign in."); }
    finally { setBusy(false); }
  }

  async function upload(event: FormEvent) {
    event.preventDefault(); if (!file || !token) return; setBusy(true); setMessage("");
    const formData = new FormData(); formData.append("file", file);
    try {
      const response = await fetch(`${API_URL}/documents/upload`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: formData });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? "Upload failed");
      setMessage(`${data.filename} uploaded and queued for verification.`); setFile(null); await loadDocuments(token);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to upload file."); }
    finally { setBusy(false); }
  }

  if (!token) return (
    <main className="auth-shell"><section className="intro-panel"><p className="eyebrow">DOCUMENT DESK / 01</p><h1>Verify every file with confidence.</h1><p className="intro-copy">A focused workspace for uploading contracts and tracking verification results.</p></section>
      <form className="auth-card" onSubmit={login}><p className="eyebrow">WELCOME BACK</p><h2>Sign in</h2><label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label><label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label><button disabled={busy}>{busy ? "Signing in..." : "Continue"}</button>{message && <p className="notice">{message}</p>}<p className="hint">Demo account: demo@example.com / password</p></form>
    </main>
  );

  return <main className="workspace-shell"><header className="topbar"><div><p className="eyebrow">DOCUMENT DESK / 02</p><h1>Verification workspace</h1></div><button className="secondary" onClick={() => { setToken(""); setDocuments([]); }}>Sign out</button></header><section className="upload-grid"><form className="upload-card" onSubmit={upload}><p className="eyebrow">NEW REVIEW</p><h2>Upload a document</h2><label className="dropzone">{file ? file.name : "Choose a PDF, DOCX, or image"}<input type="file" accept=".pdf,.doc,.docx,.png,.jpg,.jpeg" onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)} required /></label><p className="hint">Maximum size: 10 MB. Verification begins after upload.</p><button disabled={busy || !file}>{busy ? "Uploading..." : "Upload for verification"}</button>{message && <p className="notice">{message}</p>}</form><section className="list-card"><div className="section-heading"><div><p className="eyebrow">ACTIVITY</p><h2>Your documents</h2></div><span className="count">{documents.length}</span></div>{documents.length === 0 ? <p className="empty">No documents yet.</p> : <ul>{documents.map((document) => <li key={`${document.filename}-${document.uploaded_at}`}><span><strong>{document.filename}</strong><small>{new Date(document.uploaded_at).toLocaleString()}</small></span><span className="status">{document.status}</span></li>)}</ul>}</section></section></main>;
}
