# Unified Digital Footprint & Forensic Analytics Platform
> Designed for Law Enforcement & Investigative Agencies (Chandigarh Police)

A multi-domain forensic intelligence platform that ingests, correlates, and analyzes **Telecom CDR/IPDR**, **Banking/Financial Records**, and **Social OSINT feeds** to detect anomalous criminal syndicates and generate court-admissible evidence dossiers.

---

## ⚡ Key Capabilities

- **Cross-Domain Topological Graph:** Dynamic visual correlation across phones, accounts, IP addresses, and social identities via PyVis.
- **Graph Neural Network (GNN) Risk Engine:** 2-hop Graph Convolutional Network (GCN) risk scoring for syndicate orchestrators and smurfing nodes.
- **Section 63 BSA (2023) Evidentiary PDF Export:** Automated generation of court-admissible forensic certificates featuring SHA-256 bitstream validation and chain-of-custody sign-offs.
- **Air-Gapped AI Forensic Copilot:** Dual-engine LLM querying with cloud inference (Groq `llama-3.1-8b-instant`) and offline local fallback (Ollama `llama3.1:8b`).
- **Geospatial Tracking:** Cell tower site mapping and movement reconstruction.

---

## 🛠️ Tech Stack

- **Backend:** FastAPI, SQLAlchemy, SQLite, NetworkX, PyTorch, ReportLab
- **Frontend:** Streamlit, PyVis, Plotly
- **AI & NLP:** Groq SDK, Ollama (Local LLM Fallback)

---

## 🚀 Quickstart

### 1. Setup & Installation
```bash
git clone [https://github.com/Joshua-radiant/Forensic-platform.git](https://github.com/Joshua-radiant/Forensic-platform.git)
cd Forensic-platform

python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r backend/app/requirements.txt

### 2. Configure the backend URL
The frontend loads `BACKEND_URL` from the root `.env` file. Keep the local value for normal development, or replace it with the current ngrok URL whenever the backend is forwarded:

```env
BACKEND_URL=https://your-current-ngrok-url.ngrok-free.app
```

Run the frontend from the repository root so it loads `.env`:

```bash
streamlit run frontend/app.py
```

The app appends `/api/v1` automatically. Update `BACKEND_URL` and rerun the command whenever ngrok gives you a new URL.