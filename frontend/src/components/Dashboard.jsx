export function Dashboard({ user, documents, onSignOut, onUpload, file, busy, message, setFile }) {
  return (
    <main>
      <header className="header">
        <div>
          <p className="eyebrow">DOCUMENT DESK</p>
          <h1>Verification workspace</h1>
        </div>
        <button className="outline" onClick={onSignOut}>Sign out</button>
      </header>

      <section className="grid">
        <form className="card" onSubmit={onUpload}>
          <p className="eyebrow">NEW REVIEW</p>
          <h2>Upload a document</h2>
          <label className="drop">
            {file ? file.name : "Choose a PDF, DOCX, or image"}
            <input
              type="file"
              accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
              onChange={(event) => setFile(event.target.files[0])}
              required
            />
          </label>
          <small>Maximum size: 10 MB.</small>
          <button disabled={busy || !file}>Upload</button>
          {message && <p className="message">{message}</p>}
        </form>

        <section className="card">
          <div className="heading">
            <h2>Documents</h2>
            <strong>{documents.length}</strong>
          </div>

          {documents.length ? (
            <ul>
              {documents.map((doc) => (
                <li key={doc.document_id}>
                  <span>
                    <b>{doc.filename}</b>
                    <small>{doc.uploaded_at}</small>
                  </span>
                  <em>{doc.status}</em>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No documents yet.</p>
          )}
        </section>
      </section>
    </main>
  );
}
