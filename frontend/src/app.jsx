import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

const API = "http://127.0.0.1:8000";

async function request(path, options = {}) {
  try {
    const response = await fetch(`${API}${path}`, options);
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json") ? await response.json() : {};
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  } catch (error) {
    throw new Error(error instanceof TypeError ? "Cannot connect to the backend. Start FastAPI on port 8000." : error.message);
  }
}

const authenticate = (mode, email, password) => request(`/auth/${mode === "signup" ? "signup" : "login"}`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email, password })
});

const fetchDocuments = (owner) => request("/documents", {
  headers: { "X-User": owner }
});

const fetchApprovalReport = (owner) => request("/approvals/report", {
  headers: { "X-User": owner }
});

const createApprovalShare = (owner, contractId, stageName) => request("/approvals/share", {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-User": owner },
  body: JSON.stringify({ contract_id: contractId, stage_name: stageName })
});

const fetchSharedApproval = (token) => request(`/approvals/share/${encodeURIComponent(token)}`);

const submitSharedApproval = (token) => request(`/approvals/share/${encodeURIComponent(token)}/submit`, { method: "POST" });

const downloadUrl = (contractId) => `${API}/documents/${contractId}/download`;

const uploadContract = (owner, formData) => request("/documents/upload", {
  method: "POST",
  headers: { "X-User": owner },
  body: formData
});

const askQuestion = (owner, question, conversation = "") => request("/chat/question", {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-User": owner },
  body: JSON.stringify({ question, conversation })
});

function AuthPanel({ mode, setMode, email, password, busy, message, setEmail, setPassword, onSubmit }) {
  return (
    <form className="card auth-card" onSubmit={onSubmit}>
      <div className="auth-switch">
        {mode === "login" ? "New here?" : "Already have an account?"}
        <button type="button" className="link-button" onClick={() => setMode(mode === "login" ? "signup" : "login")}>
          {mode === "login" ? "Create account" : "Sign in"}
        </button>
      </div>
      <p className="eyebrow">{mode === "login" ? "WELCOME BACK" : "NEW ACCOUNT"}</p>
      <h2>{mode === "login" ? "Sign in" : "Register"}</h2>
      <label>Email address<input type="email" placeholder="you@company.com" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
      <label>Password<input type="password" placeholder="Enter your password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
      <button className="primary" disabled={busy}>{busy ? "Please wait..." : mode === "login" ? "Sign in" : "Create account"}</button>
      {message && <p className="message">{message}</p>}
      <small>{mode === "login" ? "Use your registered email and password." : "Your account is stored locally in SQLite."}</small>
    </form>
  );
}

function ChatCallout({ onOpenChat }) {
  return (
    <button type="button" className="chat-callout" onClick={onOpenChat} aria-label="Open contract chatbot">
      <span className="chat-callout-icon" aria-hidden="true">💬</span>
      <span>Open chatbot</span>
    </button>
  );
}

function StatCards({ documents }) {
  const counts = documents.reduce((accumulator, doc) => {
    const key = doc.status.toLowerCase();
    accumulator[key] = (accumulator[key] || 0) + 1;
    return accumulator;
  }, {});
  const cards = [
    { label: "Signed", value: counts.signed || 0, className: "status-signed" },
    { label: "Expiring soon", value: counts.expiring || 0, className: "status-expiring" },
    { label: "Pending approval", value: counts.pending || 0, className: "status-pending" },
    { label: "Expired", value: counts.expired || 0, className: "status-expired" },
  ];
  return (
    <section className="stat-row">
      {cards.map((card) => (
        <div className={`stat-card ${card.className}`} key={card.label}>
          <strong>{card.value}</strong>
          <span>{card.label}</span>
        </div>
      ))}
    </section>
  );
}

function UploadForm({ user, onUploaded }) {
  const [file, setFile] = useState(null);
  const [contractType, setContractType] = useState("");
  const [counterparty, setCounterparty] = useState("");
  const [department, setDepartment] = useState("Legal");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const handleUpload = async (event) => {
    event.preventDefault();
    if (!file || busy) return;
    setBusy(true);
    setMessage("");
    const formData = new FormData();
    formData.append("file", file);
    formData.append("contract_type", contractType || "Uploaded Document");
    formData.append("counterparty", counterparty || "Unspecified");
    formData.append("department", department);
    try {
      const result = await uploadContract(user, formData);
      setMessage(`${result.filename} uploaded and queued for verification.`);
      setFile(null);
      setContractType("");
      setCounterparty("");
      await onUploaded();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card upload-card">
      <div className="upload-heading">
        <div>
          <p className="eyebrow">NEW CONTRACT</p>
          <h2>Upload a document</h2>
        </div>
        <span className="file-limit">Max 10 MB</span>
      </div>
      <form onSubmit={handleUpload}>
        <label>Counterparty
          <input value={counterparty} onChange={(event) => setCounterparty(event.target.value)} placeholder="Company name" />
        </label>
        <label>Department
          <select value={department} onChange={(event) => setDepartment(event.target.value)}>
            {["Legal", "Finance", "IT", "Procurement", "Sales"].map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label>Contract type
          <input value={contractType} onChange={(event) => setContractType(event.target.value)} placeholder="e.g. Master Service Agreement" />
        </label>
        <label className="drop">
          <span className="upload-icon" aria-hidden="true">+</span>
          <strong>{file ? file.name : "Choose a PDF, DOC, DOCX, or TXT file"}</strong>
          <small>Verification begins automatically after upload.</small>
          <input type="file" accept=".pdf,.doc,.docx,.txt" onChange={(event) => setFile(event.target.files?.[0] ?? null)} required />
        </label>
        <button className="primary" disabled={busy || !file}>{busy ? "Uploading..." : "Upload for verification"}</button>
        {message && <p className="message">{message}</p>}
      </form>
    </section>
  );
}

function Documents({ documents }) {
  const [search, setSearch] = useState("");
  const [visibleCount, setVisibleCount] = useState(5);
  const statusClass = (status) => `status-badge status-${status.toLowerCase()}`;

  const filtered = documents.filter((doc) => {
    const term = search.trim().toLowerCase();
    if (!term) return true;
    return [doc.filename, doc.counterparty, doc.department, doc.status].some((field) => field.toLowerCase().includes(term));
  });
  const visible = search.trim() ? filtered : filtered.slice(0, visibleCount);

  return (
    <section className="card documents-card">
      <div className="heading"><div><p className="eyebrow">CONTRACT LIBRARY</p><h2>Documents</h2></div><strong className="count">{documents.length}</strong></div>
      <input
        className="search-input"
        placeholder="Search by contract, counterparty, or department..."
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      {visible.length ? <ul className="compact-list">{visible.map((doc) => (
        <li key={doc.contract_id}>
          <span>
            <b>{doc.filename}</b>
            <small>{doc.counterparty} · {doc.department} · Expires {doc.expiry_date}</small>
          </span>
          <span className="document-actions">
            <span className={statusClass(doc.status)}>{doc.status}</span>
            <a className="outline preview-link" href={downloadUrl(doc.contract_id)} target="_blank" rel="noreferrer">Preview</a>
          </span>
        </li>
      ))}</ul> : <p className="muted">No contracts match your search.</p>}
      {!search.trim() && filtered.length > visibleCount && (
        <button type="button" className="outline show-more" onClick={() => setVisibleCount((count) => count + 12)}>
          Show more ({filtered.length - visibleCount} remaining)
        </button>
      )}
    </section>
  );
}

function ApprovalSubmission({ user, report, onBack }) {
  const [department, setDepartment] = useState("");
  const [contractId, setContractId] = useState("");
  const [stageName, setStageName] = useState("");
  const [message, setMessage] = useState("");
  const [shareLink, setShareLink] = useState("");
  const [shareBusy, setShareBusy] = useState(false);
  const [copyMessage, setCopyMessage] = useState("");

  const pendingStages = (item) => item.stages.filter((stage) => stage.stage_status === "In Progress");
  const departments = [...new Set(report.flatMap((item) => pendingStages(item).map((stage) => stage.assigned_department)))].sort();
  const contracts = report.filter((item) => pendingStages(item).some((stage) => stage.assigned_department === department));
  const selectedContract = contracts.find((item) => String(item.contract_id) === contractId);
  const stages = selectedContract ? pendingStages(selectedContract).filter((stage) => stage.assigned_department === department) : [];

  const handleCreateShare = async () => {
    if (!contractId || !stageName || shareBusy) return;
    setShareBusy(true);
    setCopyMessage("");
    try {
      const result = await createApprovalShare(user, Number(contractId), stageName);
      setShareLink(result.url);
    } catch (error) {
      setCopyMessage(error.message);
    } finally {
      setShareBusy(false);
    }
  };

  const handleCopyShare = async () => {
    await navigator.clipboard.writeText(shareLink);
    setCopyMessage("Link copied.");
  };

  return (
    <main>
      <header className="header">
        <div>
          <button className="back-link" onClick={onBack}>← Back to workspace</button>
          <p className="eyebrow">APPROVAL WORKFLOW</p>
          <h1>Submit an approval</h1>
        </div>
        <span className="chat-user">{user}</span>
      </header>
      <section className="card approval-form">
        <p className="eyebrow">PENDING REVIEW</p>
        <h2>Choose the team and contract</h2>
        <p className="form-help">Legal, Finance, Procurement, and other teams are listed by the department assigned to the current approval stage.</p>
        <label>Approval department
          <select value={department} onChange={(event) => { setDepartment(event.target.value); setContractId(""); setStageName(""); setShareLink(""); }}>
            <option value="">Choose a department</option>
            {departments.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label>Contract
          <select value={contractId} disabled={!department} onChange={(event) => { setContractId(event.target.value); setStageName(""); setShareLink(""); }}>
            <option value="">{department ? "Choose a pending contract" : "Choose a department first"}</option>
            {contracts.map((item) => <option key={item.contract_id} value={item.contract_id}>{item.filename} · {item.counterparty}</option>)}
          </select>
        </label>
        <label>Pending approval stage
          <select value={stageName} disabled={!contractId} onChange={(event) => { setStageName(event.target.value); setShareLink(""); }}>
            <option value="">{contractId ? "Choose a stage" : "Choose a contract first"}</option>
            {stages.map((stage) => <option key={stage.stage_name} value={stage.stage_name}>{stage.stage_name}</option>)}
          </select>
        </label>
        <div className="share-controls">
          <button type="button" className="outline" disabled={!stageName || shareBusy} onClick={handleCreateShare}>{shareBusy ? "Creating link..." : "Create shareable link"}</button>
          {shareLink && <div className="share-link-row"><input aria-label="Shareable approval link" value={shareLink} readOnly /><button type="button" className="outline" onClick={handleCopyShare}>Copy link</button></div>}
        </div>
        {copyMessage && <p className="form-help">{copyMessage}</p>}
        {message && <p className="message">{message}</p>}
        {!departments.length && <p className="muted form-help">There are no in-progress approval stages available.</p>}
      </section>
    </main>
  );
}

function SharedApprovalPage({ token }) {
  const [details, setDetails] = useState(null);
  const [busy, setBusy] = useState(true);
  const [submitted, setSubmitted] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    fetchSharedApproval(token)
      .then(setDetails)
      .catch((error) => setMessage(error.message))
      .finally(() => setBusy(false));
  }, [token]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await submitSharedApproval(token);
      setSubmitted(true);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth">
      <section className="card approval-form shared-approval-form">
        <p className="eyebrow">SHARED APPROVAL</p>
        {busy && !details ? <h2>Loading approval request...</h2> : details ? (
          <>
            <h2>{submitted ? "Approval submitted" : "Review approval request"}</h2>
            {submitted ? <p className="form-help">The approval stage was submitted successfully and the contract dashboard will now show the updated stage.</p> : (
              <form onSubmit={handleSubmit}>
                <p className="form-help">You are submitting the current approval stage for this contract.</p>
                <div className="shared-contract-details"><strong>{details.filename}</strong><span>{details.counterparty}</span><span>{details.assigned_department} · {details.stage_name}</span></div>
                <button disabled={busy}>{busy ? "Submitting..." : "Submit approval"}</button>
              </form>
            )}
          </>
        ) : <h2>{message || "This approval link is unavailable."}</h2>}
        {message && details && <p className="message">{message}</p>}
      </section>
    </main>
  );
}

function StagePips({ stages }) {
  return (
    <div className="stage-pips">
      {stages.map((stage) => (
        <span
          key={stage.stage_name}
          className={`stage-pip stage-${stage.stage_status.toLowerCase().replace(" ", "-")}${stage.delayed ? " stage-delayed" : ""}`}
          data-tooltip={`${stage.stage_name} · ${stage.assigned_department} · ${stage.stage_status}${stage.actual_days !== null ? ` · ${stage.actual_days}d` : ""}${stage.delayed ? " · Delayed" : ""}`}
          aria-label={`${stage.stage_name}, ${stage.assigned_department}, ${stage.stage_status}`}
        >
          {stage.stage_name.split(" ")[0][0]}
        </span>
      ))}
    </div>
  );
}

function ApprovalReport({ report, onOpenSubmission }) {
  const [search, setSearch] = useState("");
  const [visibleCount, setVisibleCount] = useState(12);

  const filtered = report.filter((item) => {
    const term = search.trim().toLowerCase();
    if (!term) return true;
    return [item.filename, item.counterparty, item.department, item.status].some((field) => field.toLowerCase().includes(term));
  });
  const visible = search.trim() ? filtered : filtered.slice(0, visibleCount);

  return (
    <section className="card report-card">
      <div className="heading"><div><p className="eyebrow">WORKFLOW REPORT</p><h2>Approval Stages</h2></div><div className="heading-actions"><button type="button" className="outline submit-link" onClick={onOpenSubmission}>Approval form</button><strong className="count">{report.length}</strong></div></div>
      <input
        className="search-input"
        placeholder="Search by contract, counterparty, or department..."
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <div className="report-table-wrap">
        <table className="report-table">
          <thead>
            <tr><th>Contract</th><th>Department</th><th>Status</th><th>Stages</th></tr>
          </thead>
          <tbody>
            {visible.map((item) => (
              <tr key={item.contract_id}>
                <td><b>{item.filename}</b><small>{item.counterparty}</small></td>
                <td>{item.department}</td>
                <td><span className={`status-badge status-${item.status.toLowerCase()}`}>{item.status}</span></td>
                <td><StagePips stages={item.stages} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!visible.length && <p className="muted">No contracts match your search.</p>}
      </div>
      {!search.trim() && filtered.length > visibleCount && (
        <button type="button" className="outline show-more" onClick={() => setVisibleCount((count) => count + 12)}>
          Show more ({filtered.length - visibleCount} remaining)
        </button>
      )}
    </section>
  );
}

function ChatbotPage({ user, onBack }) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Ask me about the contracts in your workspace." }
  ]);
  const [busy, setBusy] = useState(false);

  const handleQuestion = async (event) => {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) return;
    const conversation = messages
      .slice(-6)
      .map((message) => `${message.role}: ${message.text}`)
      .join("\n");
    setQuestion("");
    setMessages((current) => [...current, { role: "user", text }]);
    setBusy(true);
    try {
      const result = await askQuestion(user, text, conversation);
      setMessages((current) => [...current, { role: "assistant", text: result.answer }]);
    } catch (error) {
      setMessages((current) => [...current, { role: "assistant", text: error.message, error: true }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="chat-page">
      <header className="header">
        <div>
          <button className="back-link" onClick={onBack}>← Back to workspace</button>
          <p className="eyebrow">CONTRACT ASSISTANT</p>
          <h1>Ask your documents</h1>
        </div>
        <span className="chat-user">{user}</span>
      </header>

      <section className="chat-panel card">
        <div className="chat-messages">
          {messages.map((message, index) => (
            <div className={`chat-message ${message.role}${message.error ? " error" : ""}`} key={`${message.role}-${index}`}>
              <span className="message-label">{message.role === "user" ? "You" : "Assistant"}</span>
              <p>{message.text}</p>
            </div>
          ))}
          {busy && <div className="chat-message assistant"><span className="message-label">Assistant</span><p className="typing">Searching your documents...</p></div>}
        </div>
        <form className="chat-composer" onSubmit={handleQuestion}>
          <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about payment terms, dates, or obligations..." disabled={busy} />
          <button className="primary" disabled={busy || !question.trim()}>Send</button>
        </form>
        <small className="chat-note">Answers are grounded in the indexed contract context.</small>
      </section>
    </main>
  );
}

function App() {
  const [user, setUser] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState("login");
  const [documents, setDocuments] = useState([]);
  const [report, setReport] = useState([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState("workspace");

  const loadWorkspace = async (owner = user) => {
    if (!owner) return;
    const [items, reportItems] = await Promise.all([fetchDocuments(owner), fetchApprovalReport(owner)]);
    setDocuments(items);
    setReport(reportItems);
  };

  useEffect(() => {
    if (!user || page !== "workspace") return undefined;
    const refresh = () => loadWorkspace(user).catch(() => {});
    const timer = setInterval(refresh, 15000);
    return () => clearInterval(timer);
  }, [user, page]);

  const handleLogin = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");

    try {
      const data = await authenticate(mode, email, password);
      setDocuments([]);
      setReport([]);
      setPage("workspace");
      setUser(data.user);
      await loadWorkspace(data.user);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  };

  const handleSignOut = () => {
    setUser("");
    setDocuments([]);
    setReport([]);
    setMessage("");
    setEmail("");
    setPassword("");
    setPage("workspace");
  };

  const sharedToken = new URLSearchParams(window.location.search).get("approval");

  if (!user && sharedToken) {
    return <SharedApprovalPage token={sharedToken} />;
  }

  if (!user) {
    return (
      <main className="auth">
        <AuthPanel {...{ mode, setMode, email, password, busy, message, setEmail, setPassword }} onSubmit={handleLogin} />
      </main>
    );
  }

  if (page === "chatbot") {
    return <ChatbotPage user={user} onBack={() => setPage("workspace")} />;
  }

  if (page === "approval-submit") {
    return (
      <ApprovalSubmission
        user={user}
        report={report}
        onBack={() => setPage("workspace")}
      />
    );
  }

  return (
    <main>
      <header className="header">
        <div className="header-left">
          <ChatCallout onOpenChat={() => setPage("chatbot")} />
          <div>
            <p className="eyebrow">CONTRACT DESK · {user}</p>
            <h1>Accounts manager workspace</h1>
          </div>
        </div>
        <button className="outline signout" onClick={handleSignOut}>Sign out</button>
      </header>

      <StatCards documents={documents} />

      <section className="grid">
        <ApprovalReport report={report} onOpenSubmission={() => setPage("approval-submit")} />
        <UploadForm user={user} onUploaded={() => loadWorkspace(user)} />
        <Documents documents={documents} />
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
