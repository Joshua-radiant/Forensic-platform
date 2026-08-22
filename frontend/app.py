import os
import sys
import threading
import time
import requests
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit.errors import StreamlitSecretNotFoundError
import plotly.express as px
from pyvis.network import Network
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# BACKGROUND FASTAPI ORCHESTRATOR
# ==========================================
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_app_dir = os.path.join(base_dir, "backend", "app")

for path in [base_dir, backend_app_dir, os.path.join(base_dir, "backend")]:
    if path not in sys.path:
        sys.path.insert(0, path)

def run_uvicorn_in_thread():
    import uvicorn
    os.chdir(backend_app_dir)
    try:
        from backend.app.app import app as fastapi_app
    except ImportError:
        from app import app as fastapi_app

    config = uvicorn.Config(
        app=fastapi_app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        loop="asyncio"
    )
    server = uvicorn.Server(config)
    # Disable OS signal handlers so it runs smoothly in a secondary daemon thread
    server.install_signal_handlers = lambda: None
    server.run()

@st.cache_resource
def start_fastapi():
    try:
        if requests.get("http://127.0.0.1:8000/docs", timeout=1).status_code == 200:
            return True
    except Exception:
        pass

    th = threading.Thread(target=run_uvicorn_in_thread, daemon=True)
    th.start()

    for _ in range(12):
        time.sleep(1)
        try:
            if requests.get("http://127.0.0.1:8000/docs", timeout=1).status_code == 200:
                return True
        except Exception:
            continue
    return False

start_fastapi()

# ==========================================
# CONFIGURATION & SECRETS
# ==========================================
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API_URL = f"{BACKEND_URL}/api/v1"

GOOGLE_MAPS_API_KEY = ""
try:
    streamlit_secrets = dict(st.secrets)
except StreamlitSecretNotFoundError:
    streamlit_secrets = {}

if "GOOGLE_MAPS_API_KEY" in streamlit_secrets:
    GOOGLE_MAPS_API_KEY = streamlit_secrets["GOOGLE_MAPS_API_KEY"]
else:
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

if "GROQ_API_KEY" in streamlit_secrets:
    os.environ["GROQ_API_KEY"] = streamlit_secrets["GROQ_API_KEY"]
if "GOOGLE_MAPS_API_KEY" in streamlit_secrets:
    os.environ["GOOGLE_MAPS_API_KEY"] = streamlit_secrets["GOOGLE_MAPS_API_KEY"]

st.set_page_config(
    page_title="Chandigarh Police - Digital Footprint Analytics",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ Chandigarh Police Digital Footprint & Forensic Analytics")
st.caption("Unified multi-domain investigative platform for Telecom, Banking, and OSINT records.")

# ==========================================
# SIDEBAR INGESTION & CONTROLS
# ==========================================
with st.sidebar:
    st.header("📂 Evidence Ingestion")
    
    st.subheader("1. Telecom CDR/IPDR (.csv)")
    cdr_file = st.file_uploader("Upload CDR Dump", type=["csv"], key="cdr")
    if cdr_file and st.button("Ingest CDR Records", use_container_width=True):
        files = {"file": (cdr_file.name, cdr_file.getvalue(), "text/csv")}
        res = requests.post(f"{API_URL}/upload/cdr", files=files)
        if res.status_code == 200:
            st.success(f"Ingested {res.json().get('records_ingested', 0)} records!")
            st.rerun()

    st.subheader("2. Bank Statements (.csv, .pdf)")
    bank_file = st.file_uploader("Upload Bank Statement", type=["csv", "pdf"], key="bank")
    if bank_file and st.button("Ingest Bank Records", use_container_width=True):
        files = {"file": (bank_file.name, bank_file.getvalue(), "application/octet-stream")}
        res = requests.post(f"{API_URL}/upload/bank", files=files)
        if res.status_code == 200:
            st.success(f"Ingested {res.json().get('records_ingested', 0)} records!")
            st.rerun()

    st.subheader("3. Social Activity (.json)")
    social_file = st.file_uploader("Upload Social Dump", type=["json"], key="social")
    if social_file and st.button("Ingest Social Data", use_container_width=True):
        files = {"file": (social_file.name, social_file.getvalue(), "application/json")}
        res = requests.post(f"{API_URL}/upload/social", files=files)
        if res.status_code == 200:
            st.success(f"Ingested {res.json().get('records_ingested', 0)} records!")
            st.rerun()

    st.divider()
    st.subheader("⚖️ Legal Dossier Export")
    case_num = st.text_input("Case FIR / Reference", value="CHD-CYBER-2026-0881")
    
    if st.button("📄 Generate Sec 63 BSA PDF Dossier", type="primary", use_container_width=True):
        with st.spinner("Generating Court-Admissible Forensic PDF..."):
            pdf_res = requests.get(f"{API_URL}/export/pdf?case_id={case_num}")
            if pdf_res.status_code == 200:
                st.download_button(
                    label="⬇️ Download Signed Forensic PDF",
                    data=pdf_res.content,
                    file_name=f"Dossier_{case_num}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            else:
                st.error("Failed to generate PDF dossier.")
                
    st.divider()
    if st.button("🗑️ Clear Active Session Data", type="secondary", use_container_width=True):
        try:
            requests.delete(f"{API_URL}/records/clear")
        except Exception as e:
            st.sidebar.error(f"Error clearing backend database: {e}")

        st.session_state.clear()
        st.session_state.copilot_messages = [
            {"role": "assistant", "content": "Hello Inspector. I have correlated all ingested case logs. How can I assist your investigation?"}
        ]
        st.session_state.copilot_preset_query = None
        st.rerun()

# ==========================================
# FETCH CURRENT STATE (DIRECT DB VIA BACKEND)
# ==========================================
try:
    records_res = requests.get(f"{API_URL}/records/all", timeout=6).json()
    graph_res = requests.get(f"{API_URL}/analytics/graph", timeout=6).json()
    anomalies_res = requests.get(f"{API_URL}/analytics/anomalies", timeout=6).json()
    timeline_res = requests.get(f"{API_URL}/analytics/timeline", timeout=6).json()
except Exception as e:
    st.error(f"Cannot connect to backend server at {BACKEND_URL}: {e}")
    st.info("FastAPI backend is spinning up. Please click Rerun in 5 seconds.")
    if st.button("🔄 Retry Connection"):
        st.rerun()
    st.stop()

# ==========================================
# KPI METRICS
# ==========================================
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("🚨 Active Alerts", anomalies_res.get("total_anomalies", 0))
kpi2.metric("🔗 Linked Entities", graph_res.get("summary", {}).get("total_nodes", 0))
kpi3.metric("📊 Total Footprint Logs", len(records_res) if isinstance(records_res, list) else 0)
kpi4.metric("📁 Case Status", "ACTIVE REVIEW")

st.divider()

# ==========================================
# DASHBOARD TABS
# ==========================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🕸️ Entity Relationship Graph",
    "🚨 Automated Fraud Alerts & GNN",
    "⏳ Chronological Timeline",
    "🗺️ Geospatial Analysis (Google Maps)",
    "💬 AI Forensic Copilot"
])

# ------------------------------------------
# TAB 1: GRAPH VISUALIZATION
# ------------------------------------------
with tab1:
    st.subheader("🕸️ Cross-Domain Entity Relationship Graph")

    st.markdown(
        """
        <div style="display: flex; flex-wrap: wrap; gap: 15px; align-items: center; background: #1E1E1E; padding: 10px 16px; border-radius: 8px; margin-bottom: 12px; border: 1px solid #333;">
            <span style="font-weight: 600; font-size: 13px; color: #BBB;">NODE LEGEND:</span>
            <div style="display: flex; align-items: center; gap: 6px; font-size: 13px; color: #FFF;">
                <span style="height: 12px; width: 12px; background-color: #4CAF50; border-radius: 50%; display: inline-block;"></span>
                <b>Phone / Telecom</b>
            </div>
            <div style="display: flex; align-items: center; gap: 6px; font-size: 13px; color: #FFF;">
                <span style="height: 12px; width: 12px; background-color: #2196F3; border-radius: 50%; display: inline-block;"></span>
                <b>IP Address / Gateway</b>
            </div>
            <div style="display: flex; align-items: center; gap: 6px; font-size: 13px; color: #FFF;">
                <span style="height: 12px; width: 12px; background-color: #E91E63; border-radius: 50%; display: inline-block;"></span>
                <b>Social / OSINT Handle</b>
            </div>
            <div style="display: flex; align-items: center; gap: 6px; font-size: 13px; color: #FFF;">
                <span style="height: 12px; width: 12px; background-color: #FF9800; border-radius: 50%; display: inline-block;"></span>
                <b>Bank Account / Mule</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if graph_res and "nodes" in graph_res and len(graph_res["nodes"]) > 0:
        net = Network(height="580px", width="100%", bgcolor="#0E1117", font_color="#FFFFFF")
        net.force_atlas_2based()

        for node in graph_res["nodes"]:
            n_id = node["id"]
            n_type = node.get("type", "").upper()
            n_domain = node.get("source_domain", "").upper()

            if "PHONE" in n_type or "TELECOM" in n_domain:
                color = "#4CAF50"
            elif "IP" in n_type or "NETWORK" in n_domain:
                color = "#2196F3"
            elif "HANDLE" in n_type or "SOCIAL" in n_domain:
                color = "#E91E63"
            elif "BANK" in n_domain or "ACCOUNT" in n_type:
                color = "#FF9800"
            else:
                color = "#9C27B0"

            net.add_node(
                n_id,
                label=f"{n_id}\n({n_type})",
                color=color,
                size=22 if node.get("degree", 0) > 2 else 16,
                title=f"Entity: {n_id}<br>Type: {n_type}<br>Domain: {n_domain}"
            )

        for edge in graph_res.get("edges", []):
            net.add_edge(
                edge["source"],
                edge["target"],
                title=f"Action: {edge.get('relation', 'LINK')}",
                color="#757575",
                width=1.5
            )

        net.save_graph("graph.html")
        with open("graph.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        components.html(html_content, height=600, scrolling=True)
    else:
        st.info("No network entities available. Please ingest data sources using the sidebar.")

# ------------------------------------------
# TAB 2: FRAUD ALERTS & GNN
# ------------------------------------------
with tab2:
    st.subheader("🚨 Automated Anomaly & Fraud Detection Engine")
    
    st.markdown("### 🧠 GNN Graph Neural Topological Risk Scores")
    try:
        gnn_res = requests.get(f"{API_URL}/gnn/scores", timeout=5).json()
        scores = gnn_res.get("scores", [])
        if scores:
            gnn_cols = st.columns(min(len(scores[:4]), 4))
            for i, score_data in enumerate(scores[:4]):
                with gnn_cols[i]:
                    st.metric(
                        label=f"{score_data['entity']}",
                        value=f"{score_data['gnn_risk_score'] * 100:.1f}%",
                        delta=f"{score_data['classification']} RISK"
                    )
        else:
            st.info("Ingest evidence to calculate neural graph risk rankings.")
    except Exception as e:
        st.warning(f"Could not load GNN scores: {e}")

    st.markdown("---")
    st.markdown("### 📋 Rule-Based Heuristic Detections")
    alerts_list = anomalies_res.get("anomalies", [])
    if alerts_list:
        for alert in alerts_list:
            sev = alert.get("severity", "MEDIUM")
            cat = alert.get("category", "FRAUD_ALERT")
            desc = alert.get("description", "")
            time_flag = alert.get("timestamp", "")
            
            if sev in ["CRITICAL", "HIGH"]:
                st.error(f"**[{sev}] {cat}** ({time_flag})\n\n{desc}")
            else:
                st.warning(f"**[{sev}] {cat}** ({time_flag})\n\n{desc}")
    else:
        st.success("No critical heuristic anomalies detected in current evidence store.")

# ------------------------------------------
# TAB 3: TIMELINE
# ------------------------------------------
with tab3:
    st.subheader("⏳ Chronological Event Sequence & Audit Log")
    
    if timeline_res:
        if isinstance(timeline_res, list) and len(timeline_res) > 0:
            df_timeline = pd.json_normalize(timeline_res)
        elif isinstance(timeline_res, dict) and "detail" not in timeline_res:
            df_timeline = pd.DataFrame([timeline_res])
        else:
            df_timeline = pd.DataFrame()

        if not df_timeline.empty and "timestamp" in df_timeline.columns:
            df_timeline["timestamp_dt"] = pd.to_datetime(df_timeline["timestamp"])
            df_timeline = df_timeline.sort_values(by="timestamp_dt").reset_index(drop=True)

            def make_event_label(row):
                actor = row.get("actor", "Unknown")
                target = f" ➔ {row.get('target')}" if pd.notna(row.get('target')) and row.get('target') else ""
                amount = f" (₹{row.get('amount'):,.2f})" if pd.notna(row.get('amount')) and row.get('amount') else ""
                return f"{row.get('action', 'EVENT')}: {actor}{target}{amount}"

            df_timeline["event_label"] = df_timeline.apply(make_event_label, axis=1)

            domain_colors = {
                "TELECOM": "#2E7D32",
                "BANKING": "#E65100",
                "SOCIAL": "#C2185B",
                "NETWORK": "#1565C0"
            }

            fig_timeline = px.scatter(
                df_timeline,
                x="timestamp_dt",
                y="domain",
                color="domain",
                color_discrete_map=domain_colors,
                hover_name="event_label",
                hover_data={
                    "timestamp_dt": "|%Y-%m-%d %H:%M:%S",
                    "domain": True,
                    "actor": True,
                    "target": True,
                    "amount": True,
                    "ip": True
                },
                height=260,
                title="Cross-Domain Activity Sequence (Hover over markers for forensic details)"
            )

            fig_timeline.update_traces(
                marker=dict(size=16, symbol="circle", opacity=0.9, line=dict(width=2, color="#FFFFFF"))
            )

            fig_timeline.update_layout(
                xaxis_title="Timeline (UTC / IST)",
                yaxis_title="Source Domain",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0.03)",
                hovermode="closest",
                legend_title_text="Domain",
                margin=dict(l=10, r=10, t=40, b=10)
            )

            st.plotly_chart(fig_timeline, use_container_width=True)
            st.divider()

            st.markdown("#### 📋 Detailed Chronological Log Table")
            display_cols = [c for c in ["record_id", "timestamp", "domain", "action", "actor", "target", "amount", "ip"] if c in df_timeline.columns]
            st.dataframe(df_timeline[display_cols], use_container_width=True, height=350)
        else:
            st.info("No formatted timestamp records available for timeline rendering.")
    else:
        st.info("No timeline records available. Ingest evidence files to populate.")

# ------------------------------------------
# TAB 4: GEOSPATIAL MAPS
# ------------------------------------------
with tab4:
    st.subheader("🗺️ Cell Site & Geo-Location Tracking (Google Maps)")
    if isinstance(records_res, list) and len(records_res) > 0:
        markers = []
        coord_counts = {}

        for r in records_res:
            if isinstance(r, dict) and r.get("geo_lat") is not None and r.get("geo_lon") is not None:
                p_val = r.get("primary_entity", {}).get("value", "Unknown")
                action = r.get("action", "Activity")
                time_str = r.get("timestamp", "")[:19].replace("T", " ")
                domain = r.get("source_domain", "UNKNOWN").upper()
                
                raw_lat = float(r["geo_lat"])
                raw_lng = float(r["geo_lon"])
                
                coord_key = f"{round(raw_lat, 4)}_{round(raw_lng, 4)}"
                count = coord_counts.get(coord_key, 0)
                coord_counts[coord_key] = count + 1
                
                offset_lat = raw_lat + (count * 0.00035 if count > 0 else 0)
                offset_lng = raw_lng + (count * 0.00035 if count > 0 else 0)

                if "TELECOM" in domain:
                    icon_color = "green"
                elif "SOCIAL" in domain:
                    icon_color = "purple"
                elif "BANK" in domain:
                    icon_color = "yellow"
                else:
                    icon_color = "red"

                markers.append({
                    "lat": offset_lat,
                    "lng": offset_lng,
                    "raw_lat": raw_lat,
                    "raw_lng": raw_lng,
                    "entity": p_val,
                    "action": action,
                    "domain": domain,
                    "time": time_str,
                    "icon": f"http://maps.google.com/mapfiles/ms/icons/{icon_color}-dot.png"
                })
        
        if markers:
            markers_json = json.dumps(markers)
            
            gmap_html = f"""
            <!DOCTYPE html>
            <html>
              <head>
                <script src="https://maps.googleapis.com/maps/api/js?key={GOOGLE_MAPS_API_KEY}"></script>
                <style>
                  #map {{
                    height: 580px;
                    width: 100%;
                    border-radius: 10px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                  }}
                  html, body {{
                    margin: 0;
                    padding: 0;
                    background-color: transparent;
                  }}
                  .gm-style .gm-style-iw-c {{
                    padding: 14px !important;
                    border-radius: 8px !important;
                    box-shadow: 0 4px 16px rgba(0,0,0,0.2) !important;
                  }}
                </style>
              </head>
              <body>
                <div id="map"></div>
                <script>
                  function initMap() {{
                    const markersData = {markers_json};
                    const bounds = new google.maps.LatLngBounds();
                    
                    const map = new google.maps.Map(document.getElementById("map"), {{
                      zoom: 12,
                      center: {{ lat: 30.7333, lng: 76.7794 }},
                      mapTypeId: 'roadmap',
                      gestureHandling: 'greedy',
                      mapTypeControl: true,
                      streetViewControl: true,
                      fullscreenControl: true
                    }});

                    const infoWindow = new google.maps.InfoWindow();

                    markersData.forEach((item) => {{
                      const pos = {{ lat: item.lat, lng: item.lng }};
                      bounds.extend(pos);

                      const marker = new google.maps.Marker({{
                        position: pos,
                        map: map,
                        title: `${{item.entity}} (${{item.domain}})`,
                        icon: {{
                          url: item.icon
                        }}
                      }});

                      marker.addListener("click", () => {{
                        const contentString = `
                          <div style="font-family: Arial, sans-serif; font-size: 13px; color: #212121; line-height: 1.6;">
                            <span style="font-size: 14px; font-weight: bold; color: #0D47A1;">🎯 ${{item.entity}}</span><br>
                            <b>Domain:</b> <span style="badge; background: #EEE; padding: 2px 6px; border-radius: 4px;">${{item.domain}}</span><br>
                            <b>Action:</b> ${{item.action}}<br>
                            <b>Timestamp:</b> ${{item.time}}<br>
                            <b>Cell / Geo:</b> ${{item.raw_lat.toFixed(4)}}, ${{item.raw_lng.toFixed(4)}}
                          </div>
                        `;
                        infoWindow.setContent(contentString);
                        infoWindow.open(map, marker);
                      }});
                    }});

                    if (markersData.length > 1) {{
                      map.fitBounds(bounds);
                      google.maps.event.addListenerOnce(map, 'bounds_changed', function() {{
                        if (this.getZoom() > 15) {{
                          this.setZoom(15);
                        }}
                      }});
                    }} else if (markersData.length === 1) {{
                      map.setCenter(bounds.getCenter());
                      map.setZoom(14);
                    }}
                  }}
                  window.onload = initMap;
                </script>
              </body>
            </html>
            """
            components.html(gmap_html, height=600, scrolling=False)
        else:
            st.info("No geospatial coordinates present in current records.")
    else:
        st.info("Upload records to view geospatial mapping.")

# ------------------------------------------
# TAB 5: AI FORENSIC COPILOT
# ------------------------------------------
with tab5:
    col_t1, col_t2 = st.columns([5, 1])
    with col_t1:
        st.subheader("💬 AI Forensic Copilot (Evidence-Grounded Intelligence)")
        st.caption("Ask natural language questions about call logs, bank money trails, burner handles, or escape coordinates.")
    with col_t2:
        if st.button("🗑️ Reset Chat", key="btn_reset_copilot_chat", use_container_width=True):
            st.session_state.copilot_messages = [
                {"role": "assistant", "content": "Hello Inspector. I have correlated all ingested case logs. How can I assist your investigation?"}
            ]
            st.session_state.copilot_preset_query = None
            st.rerun()

    if "copilot_messages" not in st.session_state:
        st.session_state.copilot_messages = [
            {"role": "assistant", "content": "Hello Inspector. I have correlated all ingested case logs. How can I assist your investigation?"}
        ]

    st.markdown("**Quick Prompts:**")
    col_q1, col_q2, col_q3 = st.columns(3)
    with col_q1:
        if st.button("📞 Who called before the transfer?", key="qp_who_called", use_container_width=True):
            st.session_state.copilot_preset_query = "Who made calls right before the money transfer?"
            st.rerun()
    with col_q2:
        if st.button("💸 Trace money laundering mules", key="qp_trace_mules", use_container_width=True):
            st.session_state.copilot_preset_query = "Trace the bank money laundering flow and smurfing accounts"
            st.rerun()
    with col_q3:
        if st.button("📍 What was the escape route?", key="qp_escape_route", use_container_width=True):
            st.session_state.copilot_preset_query = "What was the suspect's escape route and GPS locations?"
            st.rerun()

    for msg in st.session_state.copilot_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("citations"):
                with st.expander("🔍 Verified Evidentiary Citations (Section 63 BSA Audit Trail)"):
                    for c in msg["citations"]:
                        st.markdown(f"- **Record `{str(c.get('record_id', ''))[:8]}`** | *{c.get('domain', 'N/A')}* | `{c.get('timestamp', 'N/A')}` | **Actor:** `{c.get('actor', 'N/A')}` | {c.get('details', '')}")

    chat_input_val = st.chat_input("Ask a case question (e.g. 'Show suspect contacts and IP links')...")
    active_query = None

    if st.session_state.get("copilot_preset_query"):
        active_query = st.session_state.copilot_preset_query
        st.session_state.copilot_preset_query = None
    elif chat_input_val:
        active_query = chat_input_val

    if active_query:
        st.session_state.copilot_messages.append({"role": "user", "content": active_query})
        with st.chat_message("user"):
            st.markdown(active_query)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing cross-domain evidentiary records & neural topology..."):
                try:
                    res = requests.post(f"{API_URL}/copilot/query", json={"query": active_query})
                    if res.status_code == 200:
                        data = res.json()
                        ans = data.get("answer", "No findings returned.")
                        cites = data.get("cited_records", [])

                        st.markdown(ans)
                        if cites:
                            with st.expander("🔍 Verified Evidentiary Citations (Section 65B Audit Trail)"):
                                for c in cites:
                                    st.markdown(f"- **Record `{str(c.get('record_id', ''))[:8]}`** | *{c.get('domain', 'N/A')}* | `{c.get('timestamp', 'N/A')}` | **Actor:** `{c.get('actor', 'N/A')}` | {c.get('details', '')}")

                        st.session_state.copilot_messages.append({
                            "role": "assistant",
                            "content": ans,
                            "citations": cites
                        })
                    else:
                        st.error(f"Backend returned status {res.status_code}: {res.text}")
                except Exception as e:
                    st.error(f"Copilot connection error: {e}")